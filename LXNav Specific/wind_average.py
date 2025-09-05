#! /usr/bin/python3

import csv
import math
import sys
import os
from collections import deque

def main():
   if len(sys.argv) < 2:
       print("Usage: python wind_average.py <input.csv> [window_size]")
       sys.exit(1)

   input_file = sys.argv[1]
   window_size = int(sys.argv[2]) if len(sys.argv) > 2 else 30

   # Build output file name
   base, ext = os.path.splitext(input_file)
   output_file = f"{base}_ave{window_size}{ext}"

   # Rolling window buffers
   u_window = deque()
   v_window = deque()

   with open(input_file, "r", newline="") as infile, \
        open(output_file, "w", newline="") as outfile:

       reader = csv.DictReader(infile, delimiter=",")
       fieldnames = reader.fieldnames + ["WDI (deg)", "WVI (kt)", "u", "v", "avg_speed", "avg_dir_deg"]
       writer = csv.DictWriter(outfile, fieldnames=fieldnames)
       writer.writeheader()

       for row in reader:
           # Keep date string untouched
           date_str = row["date"]

           # Convert WDI and WVE to int
           WDI_raw = int(row["WDI"])
           WVE_raw = int(row["WVE"])

           # Convert raw values to real units
           WDI_deg = int(round(WDI_raw / 10))              # degrees
           WVI_kt = round(WVE_raw / 100 / 1.852, 2)        # km/h -> knots

           # Compute vector components
           theta = math.radians(WDI_deg)
           u = round(WVI_kt * math.sin(theta), 2)  # east
           v = round(WVI_kt * math.cos(theta), 2)  # north

           # Update rolling windows
           u_window.append(u)
           v_window.append(v)
           if len(u_window) > window_size:
               u_window.popleft()
               v_window.popleft()

           # Compute rolling averages
           u_avg = sum(u_window) / len(u_window)
           v_avg = sum(v_window) / len(v_window)

           avg_speed = round(math.sqrt(u_avg**2 + v_avg**2), 2)
           avg_dir_deg = round((math.degrees(math.atan2(u_avg, v_avg)) + 360) % 360, 2)

           # Write row
           out_row = {
               "date": date_str,
               "WDI": WDI_raw,
               "WVE": WVE_raw,
               "WDI (deg)": WDI_deg,
               "WVI (kt)": WVI_kt,
               "u": u,
               "v": v,
               "avg_speed": avg_speed,
               "avg_dir_deg": avg_dir_deg
           }
           writer.writerow(out_row)

   print(f"Output written to {output_file}")


if __name__ == "__main__":
   main()
