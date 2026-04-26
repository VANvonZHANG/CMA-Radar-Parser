import argparse
import os
import sys
import datetime
import numpy as np
import netCDF4
import multiprocessing
import itertools
from tqdm import tqdm
import re

# We reuse the robust parser from the 'reader' module.
try:
    from reader import read_cma_radar, CmaRadarData
except ImportError:
    print("Error: Could not find the 'reader' module.", file=sys.stderr)
    print("Please ensure this script is in the 'cma_radar_parser' directory.", file=sys.stderr)
    sys.exit(1)

def write_merged_netcdf(all_data: list[CmaRadarData], output_filename: str, source_filenames: list[str]):
    """
    Aggregates data from a list of CmaRadarData objects and writes it
    to a single, time-series NetCDF file, handling varying numbers of range gates
    and removing duplicate timestamps.
    """
    if not all_data:
        raise ValueError("No data to write.")

    # Create a dictionary to easily map timestamps to filenames for sorting
    file_map = {d.radials[0].header.Seconds: f for d, f in zip(all_data, source_filenames) if d and d.radials}
    
    # Sort data by time to ensure chronological order
    all_data.sort(key=lambda d: d.radials[0].header.Seconds if d and d.radials else float('inf'))
    
    # --- Deduplication Step ---
    unique_data = []
    unique_filenames = []
    seen_timestamps = set()
    
    for data in all_data:
        if not (data and data.radials): continue
        timestamp = data.radials[0].header.Seconds
        if timestamp not in seen_timestamps:
            unique_data.append(data)
            if timestamp in file_map:
                unique_filenames.append(file_map[timestamp])
            seen_timestamps.add(timestamp)
        else:
            print(f"Warning: Duplicate timestamp {timestamp} found. Skipping file associated with it.", file=sys.stderr)
            
    if not unique_data:
        raise ValueError("No data with unique timestamps to write.")
        
    all_data = unique_data
    source_filenames = unique_filenames

    # --- Strategy A: Find the maximum n_gates and pad shorter arrays ---
    max_n_gates = 0
    for data in all_data:
        try:
            current_max = max(mom.header.BinNumber for mom in data.radials[0].variable.values())
            if current_max > max_n_gates:
                max_n_gates = current_max
        except (ValueError, IndexError):
            continue

    if max_n_gates == 0:
        raise ValueError("Could not determine a valid number of range gates from any file.")

    first_data = all_data[0]
    n_time = len(all_data)

    with netCDF4.Dataset(output_filename, "w", format="NETCDF4_CLASSIC") as nc:
        
        # --- Global Attributes ---
        nc.setncattr("Conventions", "CF-1.8")
        if first_data.site_config:
            site = first_data.site_config
            nc.setncattr("site_name", site.SiteName)
            nc.setncattr("latitude", f"{site.Latitude:.4f}")
            nc.setncattr("longitude", f"{site.Longitude:.4f}")
            nc.setncattr("altitude", f"{site.AntennaHeight:.1f}")
        nc.history = f"{datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')} - File created"
        nc.source_files = ", ".join(os.path.basename(f) for f in source_filenames)

        # --- Dimensions ---
        nc.createDimension("time", n_time)
        nc.createDimension("range", max_n_gates)

        # --- Coordinate Variables ---
        time_var = nc.createVariable("time", "f8", ("time",))
        time_var.units = "seconds since 1970-01-01 00:00:00 +00:00"
        time_var.long_name = "Time"
        
        range_var = nc.createVariable("range", "f4", ("range",))
        range_var.units = "m"
        range_var.long_name = "Range from instrument"
        range_var[:] = first_data.cut_configs[0].StartRange + np.arange(max_n_gates) * first_data.radar_config.DistanceSolution

        # --- Data Variables ---
        all_moment_keys = sorted(list(set(key for data in all_data for key in data.radials[0].variable.keys())))
        
        moment_vars = {}
        for key in all_moment_keys:
            var_name = f"moment_{key}"
            moment_vars[key] = nc.createVariable(var_name, "f4", ("time", "range"), fill_value=-999.0)
            first_occurrence_header = next(d.radials[0].variable[key].header for d in all_data if key in d.radials[0].variable)
            moment_vars[key].setncattr("scale_factor", float(first_occurrence_header.Scale))
            moment_vars[key].setncattr("add_offset", float(first_occurrence_header.Offset))
            moment_vars[key].setncattr("comment", f"Original moment data for key {key}")

        # Populate all variables by iterating through the collected data
        time_values = []
        for i, data in enumerate(all_data):
            time_values.append(data.radials[0].header.Seconds)
            for key, var in moment_vars.items():
                if key in data.radials[0].variable:
                    moment_value = data.radials[0].variable[key].value
                    n_gates_current = len(moment_value)
                    var[i, :n_gates_current] = moment_value
        
        time_var[:] = time_values

def parse_file_worker(filepath: str) -> tuple[str, CmaRadarData] | None:
    """
    A worker function for the process pool. It reads a single file and
    returns a tuple of (site_code, parsed_data_object).
    """
    try:
        data = read_cma_radar(filepath)
        if data and data.site_config and data.radials:
            return data.site_config.SiteCode, data
        return None
    except Exception as e:
        print(f"Error parsing {os.path.basename(filepath)}: {e}", file=sys.stderr)
        return None

def main():
    """Main function to batch process files by site and merge them into separate NetCDF files."""
    parser = argparse.ArgumentParser(
        description="Parses all CMA radar binary files in a directory, groups them by site, and merges each group into a separate NetCDF file."
    )
    parser.add_argument("input_folder", type=str, help="Full path to the folder containing .BIN files.")
    parser.add_argument("output_path", type=str, help="Path to save the output .nc files.")
    parser.add_argument("--workers", type=int, default=None, help="Optional. Number of worker processes. Defaults to all available CPU cores.")
    args = parser.parse_args()

    if not os.path.isdir(args.input_folder):
        print(f"Error: Input folder not found at {args.input_folder}", file=sys.stderr)
        sys.exit(1)

    if not os.path.exists(args.output_path):
        os.makedirs(args.output_path)
        print(f"Created output directory: {args.output_path}")

    # 1. Gather all files to be processed
    file_pattern = re.compile(r'Z_RADA_I_\d{5}_\d{14}_O_YCCR_.*_RAW_MM\.BIN', re.IGNORECASE)
    files_to_process = [os.path.join(root, file) for root, _, files in os.walk(args.input_folder) for file in files if file_pattern.match(file)]

    if not files_to_process:
        print("No files matching the specified format found in the directory.")
        return

    num_workers = args.workers if args.workers is not None else os.cpu_count()
    print(f"Found {len(files_to_process)} file(s). Parsing in parallel with {num_workers} worker(s)...")

    # 2. Parse all files in parallel and collect the data objects
    results = []
    with multiprocessing.Pool(processes=num_workers) as pool:
        results = list(tqdm(pool.imap(parse_file_worker, files_to_process), total=len(files_to_process), desc="Parsing files"))
    
    # 3. Group the parsed data by site_code
    grouped_data = {}
    for result in results:
        if result:
            site_code, data_obj = result
            if site_code not in grouped_data:
                grouped_data[site_code] = []
            grouped_data[site_code].append(data_obj)

    if not grouped_data:
        print("All files failed to parse or contained no data. No output files created.", file=sys.stderr)
        sys.exit(1)
        
    print(f"\nSuccessfully parsed {sum(len(v) for v in grouped_data.values())} files for {len(grouped_data)} site(s): {list(grouped_data.keys())}.")
    print("Now merging data for each site...")

    # 4. For each site, write a merged NetCDF file
    for site_code, data_list in grouped_data.items():
        try:
            output_filename = os.path.join(args.output_path, f"{site_code}_merged.nc")
            print(f"  - Creating merged file for site {site_code} at {output_filename}...")
            
            # We need to pass the original filenames for the source_files attribute
            site_filenames = [f for f in files_to_process if site_code in os.path.basename(f)]
            
            write_merged_netcdf(data_list, output_filename, site_filenames)
            print(f"    -> Successfully created merged file for site {site_code}.")
        except Exception as e:
            print(f"    -> An error occurred during NetCDF creation for site {site_code}: {e}", file=sys.stderr)
    
    print("\n--- Batch processing complete. ---")

if __name__ == "__main__":
    main()