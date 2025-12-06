#! /usr/bin/python3

import csv
import argparse
import os
from datetime import datetime, timedelta

__version__ = "1.0"


def parse_lat_lon(lat_str, lat_dir, lon_str, lon_dir):
    """Convert IGC lat/lon format to decimal degrees."""
    lat_deg = int(lat_str[:2])
    lat_min = int(lat_str[2:4])
    lat_thousandths = int(lat_str[4:])
    lat = lat_deg + (lat_min + lat_thousandths / 1000.0) / 60.0
    if lat_dir == "S":
        lat = -lat

    lon_deg = int(lon_str[:3])
    lon_min = int(lon_str[3:5])
    lon_thousandths = int(lon_str[5:])
    lon = lon_deg + (lon_min + lon_thousandths / 1000.0) / 60.0
    if lon_dir == "W":
        lon = -lon

    return lat, lon


def parse_i_record(line):
    """
    Parse an I-record (B-record extension description).

    I-record format:
      I NN sssscccc ...
    where each extension is:
      start(2) end(2) code(3)
    start/end are 1-based, inclusive character positions in the B-record.
    We convert them to 0-based [start, end] inclusive indices.
    """
    num_extensions = int(line[1:3])
    extensions = {}
    for i in range(num_extensions):
        base = 3 + i * 7
        start_1 = int(line[base : base + 2])
        end_1 = int(line[base + 2 : base + 4])
        code = line[base + 4 : base + 7]
        # Convert to 0-based inclusive indices
        start_0 = start_1 - 1
        end_0 = end_1 - 1
        extensions[code] = (start_0, end_0)
    return extensions


def parse_j_record(line):
    """
    Parse a J-record (K-record extension description).

    Same format semantics as I-record.
    """
    num_extensions = int(line[1:3])
    extensions = {}
    for i in range(num_extensions):
        base = 3 + i * 7
        start_1 = int(line[base : base + 2])
        end_1 = int(line[base + 2 : base + 4])
        code = line[base + 4 : base + 7]
        start_0 = start_1 - 1
        end_0 = end_1 - 1
        extensions[code] = (start_0, end_0)
    return extensions


def parse_hfdte(line):
    """Extract flight date from HFDTE or HFDTEDATE record."""
    if line.startswith("HFDTEDATE:"):
        date_str = line.split(":")[1].strip()
    elif line.startswith("HFDTE"):
        date_str = line[5:11]
    else:
        return None

    dd, mm, yy = int(date_str[:2]), int(date_str[2:4]), int(date_str[4:6])
    year = 2000 + yy if yy < 80 else 1900 + yy
    return datetime(year, mm, dd).date()


def clean_extension_value(value: str):
    """Convert IGC field value to int/float if possible, else empty string."""
    value = value.strip()
    if not value or set(value) == {"-"}:
        return ""
    # Remove trailing filler dashes only
    while value.endswith("-") and set(value) != {"-"}:
        value = value[:-1]
    try:
        return int(value)
    except ValueError:
        pass
    try:
        return float(value)
    except ValueError:
        return value


def igc2csv(igc_file, csv_file_b=None, csv_file_k=None):
    extensions_b = {}
    extensions_k = {}
    flight_date = None

    # Default output names if not provided
    if csv_file_b is None or csv_file_k is None:
        base, _ = os.path.splitext(igc_file)
        if csv_file_b is None:
            csv_file_b = base + ".csv"
        if csv_file_k is None:
            csv_file_k = base + "_k.csv"

    # First pass: read headers for I, J, and HFDTEDATE/HFDTE
    with open(igc_file, "r") as infile:
        for line in infile:
            line = line.rstrip("\r\n")
            if line.startswith("I"):
                extensions_b = parse_i_record(line)
            elif line.startswith("J"):
                extensions_k = parse_j_record(line)
            elif line.startswith("HFDTEDATE:"):
                # Prefer HFDTEDATE if present
                flight_date = parse_hfdte(line)
            elif line.startswith("HFDTE") and not flight_date:
                # Only use plain HFDTE if HFDTEDATE not already found
                flight_date = parse_hfdte(line)

    if not flight_date:
        raise ValueError("No HFDTE or HFDTEDATE record found in IGC file")

    # Second pass: parse B- and K-records
    b_count = 0
    k_count = 0

    with open(igc_file, "r") as infile, open(csv_file_b, "w", newline="") as outfile_b:
        # B-record CSV
        fieldnames_b = ["date", "Latitude", "Longitude", "GPS Altitude", "Pressure Altitude"] + list(
            extensions_b.keys()
        )
        writer_b = csv.DictWriter(outfile_b, fieldnames=fieldnames_b, quoting=csv.QUOTE_MINIMAL)
        writer_b.writeheader()

        # K-record setup (only if J-records exist)
        writer_k = None
        outfile_k = None
        if extensions_k:
            outfile_k = open(csv_file_k, "w", newline="")
            fieldnames_k = ["date"] + list(extensions_k.keys())
            writer_k = csv.DictWriter(outfile_k, fieldnames=fieldnames_k, quoting=csv.QUOTE_MINIMAL)
            writer_k.writeheader()

        current_date = flight_date
        last_time = None

        for line in infile:
            line = line.rstrip("\r\n")
            if not line:
                continue

            if line.startswith("B"):
                if len(line) < 35:
                    continue

                time = line[1:7]
                lat_str = line[7:14]
                lat_dir = line[14]
                lon_str = line[15:23]
                lon_dir = line[23]
                gps_alt_raw = line[25:30]
                pres_alt_raw = line[30:35]

                gps_alt = clean_extension_value(gps_alt_raw)
                pres_alt = clean_extension_value(pres_alt_raw)

                lat, lon = parse_lat_lon(lat_str, lat_dir, lon_str, lon_dir)

                # Build datetime from base date + HHMMSS
                hh, mm, ss = int(time[:2]), int(time[2:4]), int(time[4:6])
                dt = datetime.combine(current_date, datetime.min.time()).replace(hour=hh, minute=mm, second=ss)

                # Midnight rollover: only if time goes backwards
                if last_time and dt < last_time:
                    current_date += timedelta(days=1)
                    dt = datetime.combine(current_date, datetime.min.time()).replace(hour=hh, minute=mm, second=ss)

                last_time = dt
                iso_time = dt.strftime("%Y-%m-%dT%H:%M:%SZ")

                row = {
                    "date": iso_time,
                    "Latitude": round(lat, 6),
                    "Longitude": round(lon, 6),
                    "GPS Altitude": gps_alt,
                    "Pressure Altitude": pres_alt,
                }

                # B extensions
                for code, (start, end) in extensions_b.items():
                    # start/end are 0-based inclusive; slice uses end+1
                    raw_val = line[start : end + 1] if end < len(line) else ""
                    row[code] = clean_extension_value(raw_val)

                writer_b.writerow(row)
                b_count += 1

            elif line.startswith("K") and writer_k:
                if len(line) < 7:
                    continue
                time = line[1:7]
                hh, mm, ss = int(time[:2]), int(time[2:4]), int(time[4:6])
                dt = datetime.combine(current_date, datetime.min.time()).replace(hour=hh, minute=mm, second=ss)

                if last_time and dt < last_time:
                    current_date += timedelta(days=1)
                    dt = datetime.combine(current_date, datetime.min.time()).replace(hour=hh, minute=mm, second=ss)

                last_time = dt
                iso_time = dt.strftime("%Y-%m-%dT%H:%M:%SZ")

                row = {"date": iso_time}
                for code, (start, end) in extensions_k.items():
                    raw_val = line[start : end + 1] if end < len(line) else ""
                    row[code] = clean_extension_value(raw_val)

                writer_k.writerow(row)
                k_count += 1

    # Close K-record file if opened
    if "outfile_k" in locals() and outfile_k:
        outfile_k.close()

    # Summary
    if k_count > 0:
        print(f"Conversion complete! {b_count} B-records → {csv_file_b}, {k_count} K-records → {csv_file_k}")
    else:
        print(f"Conversion complete! {b_count} B-records → {csv_file_b}, no K-records found.")


def main():
    parser = argparse.ArgumentParser(
        description=(
            "Convert IGC flight recorder files into CSV.\n\n"
            "B-records (fixes) are always exported; K-records (supplementary sensor data) "
            "are exported if J/K records exist. Timestamps are converted to ISO 8601 UTC, "
            "with midnight rollover handled automatically. HFDTEDATE (preferred) or HFDTE "
            "is used to determine the flight date."
        ),
        epilog=(
            "Examples:\n"
            "  igc2csv flight.igc\n"
            "      Convert flight.igc to flight.csv and flight_k.csv (if K-records exist).\n\n"
            "  igc2csv flight.igc fixes.csv sensors.csv\n"
            "      Write B-records to fixes.csv and K-records to sensors.csv."
        ),
        formatter_class=argparse.RawTextHelpFormatter,
    )

    parser.add_argument("igc_file", help="Input IGC file")
    parser.add_argument("csv_file_b", nargs="?", help="Output CSV for B-records (default: <input>.csv)")
    parser.add_argument(
        "csv_file_k",
        nargs="?",
        help="Output CSV for K-records (default: <input>_k.csv, skipped if no J/K records)",
    )

    parser.add_argument(
        "-v",
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    args = parser.parse_args()
    igc2csv(args.igc_file, args.csv_file_b, args.csv_file_k)


if __name__ == "__main__":
    main()
