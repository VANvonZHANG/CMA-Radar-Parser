import argparse
import os
import sys
import datetime
import numpy as np
import dataclasses
from reader import read_cma_radar, CmaRadarData

def write_data_to_txt(cma_data: CmaRadarData, output_filename: str):
    """Writes the raw, parsed content of the CMA radar data to a text file."""
    with open(output_filename, 'w', encoding='utf-8') as f:
        
        all_configs = {
            "SiteConfig": cma_data.site_config,
            "RadarConfig": cma_data.radar_config,
            "TaskConfig": cma_data.task_config,
        }
        for name, config in all_configs.items():
            if config:
                f.write(f"[{name}]\n")
                for field in dataclasses.fields(config):
                    f.write(f"{field.name}: {getattr(config, field.name)}\n")
                f.write("\n")

        for i, cut_config in enumerate(cma_data.cut_configs):
            f.write(f"[CutConfig_{i+1}]\n")
            for field in dataclasses.fields(cut_config):
                f.write(f"{field.name}: {getattr(cut_config, field.name)}\n")
            f.write("\n")

        for i, radial in enumerate(cma_data.radials):
            f.write(f"[Radial_{i+1}]\n")
            if radial.header:
                for field in dataclasses.fields(radial.header):
                    f.write(f"header.{field.name}: {getattr(radial.header, field.name)}\n")
            
            for key, moment_data in radial.variable.items():
                f.write(f"\n  [Moment_{key}]\n")
                if moment_data.header:
                    for field in dataclasses.fields(moment_data.header):
                        f.write(f"  header.{field.name}: {getattr(moment_data.header, field.name)}\n")
                
                f.write("  data:\n")
                data_str = np.array2string(moment_data.value, separator=', ', threshold=sys.maxsize)
                f.write(f"    {data_str}\n")
            f.write("\n")

def main():
    """Main function to parse a CMA radar file, print a detailed summary, and save raw data."""
    parser = argparse.ArgumentParser(
        description="Reads a CMA radar binary file, prints a summary, and saves full data to a text file."
    )
    parser.add_argument("input_file", type=str, help="Full path to the CMA radar .BIN file.")
    parser.add_argument("--output-path", type=str, default=None, help="Optional. Path to save the output .txt file. Defaults to the input file's directory.")
    args = parser.parse_args()

    if not os.path.exists(args.input_file):
        print(f"Error: Input file not found at {args.input_file}", file=sys.stderr)
        sys.exit(1)

    try:
        # --- On-screen summary ---
        print(f"Reading {args.input_file}...")
        cma_data = read_cma_radar(args.input_file)
        print("File parsed successfully.")
        print("\n" + "="*40)
        print("      CMA Radar File Summary")
        print("="*40)

        if cma_data.site_config:
            site = cma_data.site_config
            print("\n[Site Information]")
            print(f"  - Name:           {site.SiteName} ({site.SiteCode})")
            print(f"  - Location:       Lat {site.Latitude:.4f}, Lon {site.Longitude:.4f}")
            print(f"  - Altitude:       {site.AntennaHeight:.1f} m")

        if cma_data.radar_config:
            radar = cma_data.radar_config
            print("\n[Radar Configuration]")
            print(f"  - Frequency:      {radar.Frequency / 1e9:.2f} GHz")
            print(f"  - Range Res.:     {radar.DistanceSolution} m")

        if cma_data.radials:
            print(f"\n[Data Content]")
            print(f"  - Radials Found:  {len(cma_data.radials)}")
            
            first_radial = cma_data.radials[0]
            obs_time = datetime.datetime.utcfromtimestamp(first_radial.header.Seconds)
            print(f"  - First Radial Time (UTC): {obs_time.strftime('%Y-%m-%d %H:%M:%S')}")

            moment_map = {
                1: "Reflectivity (Z)", 2: "Velocity (V)", 3: "Spectrum Width (W)",
                4: "Differential Reflectivity (ZDR)", 7: "Signal-to-Noise Ratio (SNR)",
                10: "Linear Depolarization Ratio (LDR)",
            }
            
            print("\n  - Moments in First Radial:")
            available_moments = sorted(first_radial.variable.keys())
            for key in available_moments:
                name = moment_map.get(key, "Unknown")
                n_gates = first_radial.variable[key].header.BinNumber
                print(f"    - Key {key:<3}: {name:<28} ({n_gates} gates)")

            # Print details of the first few gates of the first available moment
            if available_moments:
                key = available_moments[0]
                moment_data = first_radial.variable[key]
                name = moment_map.get(key, "Unknown")
                print(f"\n  - Example Data (first 5 gates of '{name}'):")
                print(f"    {moment_data.value[:5]}")
        
        print("\n" + "="*40)

        # --- Write full data to text file ---
        base_filename = os.path.basename(args.input_file)
        output_basename = os.path.splitext(base_filename)[0] + ".txt"
        
        if args.output_path:
            if not os.path.exists(args.output_path):
                os.makedirs(args.output_path)
            output_filename = os.path.join(args.output_path, output_basename)
        else:
            output_filename = os.path.splitext(args.input_file)[0] + ".txt"

        print(f"\nWriting full parsed data to {output_filename}...")
        write_data_to_txt(cma_data, output_filename)
        print("Done.")

    except Exception as e:
        print(f"An error occurred: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
