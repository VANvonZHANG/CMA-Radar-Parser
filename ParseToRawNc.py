import argparse
import os
import sys
import datetime
import numpy as np
import netCDF4
from reader import read_cma_radar, CmaRadarData

def create_raw_netcdf(cma_data: CmaRadarData, output_filename: str, source_filename: str):
    """
    Writes the parsed CMA radar data to a NetCDF file, using the original
    moment keys as variable names.
    """
    if not cma_data.radials:
        raise ValueError("No data to write.")

    first_radial = cma_data.radials[0]
    obs_time = datetime.datetime.fromtimestamp(first_radial.header.Seconds, datetime.timezone.utc)

    with netCDF4.Dataset(output_filename, "w", format="NETCDF4_CLASSIC") as nc:
        
        # --- Global Attributes from SiteConfig ---
        if cma_data.site_config:
            site = cma_data.site_config
            nc.setncattr("site_code", site.SiteCode)
            nc.setncattr("site_name", site.SiteName)
            nc.setncattr("latitude", f"{site.Latitude:.4f}")
            nc.setncattr("longitude", f"{site.Longitude:.4f}")
            nc.setncattr("altitude", f"{site.AntennaHeight:.1f}")

        nc.history = f"{datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')} - File created"
        nc.source_file = os.path.basename(source_filename)
        
        # --- Find a representative n_gates ---
        n_gates = next(iter(first_radial.variable.values())).header.BinNumber

        # --- Dimensions ---
        nc.createDimension("time", len(cma_data.radials))
        nc.createDimension("range", n_gates)

        # --- Coordinate Variables ---
        time_var = nc.createVariable("time", "f8", ("time",))
        time_var.units = f"seconds since 1970-01-01 00:00:00 +00:00"
        time_var.long_name = "Time"
        
        range_var = nc.createVariable("range", "f4", ("range",))
        range_var.units = "m"
        range_var.long_name = "Range from instrument"
        range_var[:] = cma_data.cut_configs[0].StartRange + np.arange(n_gates) * cma_data.radar_config.DistanceSolution

        # --- Data Variables (using raw moment keys) ---
        # First, find all unique moment keys across all radials
        all_moment_keys = sorted(list(set(key for radial in cma_data.radials for key in radial.variable.keys())))

        # Create variables for each moment type
        moment_vars = {}
        for key in all_moment_keys:
            var_name = f"moment_{key}"
            moment_vars[key] = nc.createVariable(var_name, "f4", ("time", "range"), fill_value=-999.0)
            # Store scale and offset as variable attributes
            # (using the first occurrence, assuming they are constant for the type)
            first_occurrence_header = next(radial.variable[key].header for radial in cma_data.radials if key in radial.variable)
            moment_vars[key].setncattr("scale_factor", float(first_occurrence_header.Scale))
            moment_vars[key].setncattr("add_offset", float(first_occurrence_header.Offset))
            moment_vars[key].setncattr("comment", f"Original moment data for key {key}")

        # Populate the variables
        time_values = []
        for i, radial in enumerate(cma_data.radials):
            time_values.append(radial.header.Seconds)
            for key, var in moment_vars.items():
                if key in radial.variable:
                    var[i, :] = radial.variable[key].value
                else:
                    # If a radial is missing a moment, fill it
                    var[i, :] = np.full(n_gates, -999.0)
        
        time_var[:] = time_values


def main():
    """Main function to parse a single CMA radar file and save it to a raw NetCDF file."""
    parser = argparse.ArgumentParser(
        description="Reads a single CMA radar binary file and saves its raw parsed data to a NetCDF file."
    )
    parser.add_argument("input_file", type=str, help="Full path to the CMA radar .BIN file.")
    parser.add_argument("--output-path", type=str, default=None, help="Optional. Path to save the output .nc file. Defaults to the input file's directory.")
    args = parser.parse_args()

    if not os.path.exists(args.input_file):
        print(f"Error: Input file not found at {args.input_file}", file=sys.stderr)
        sys.exit(1)

    try:
        print(f"Reading {args.input_file}...")
        cma_data = read_cma_radar(args.input_file)
        print("File parsed successfully.")
        
        # Determine output filename
        base_filename = os.path.basename(args.input_file)
        output_basename = os.path.splitext(base_filename)[0] + ".nc"
        
        if args.output_path:
            if not os.path.exists(args.output_path):
                os.makedirs(args.output_path)
            output_filename = os.path.join(args.output_path, output_basename)
        else:
            output_filename = os.path.splitext(args.input_file)[0] + ".nc"

        print(f"\nCreating raw NetCDF file at {output_filename}...")
        create_raw_netcdf(cma_data, output_filename, args.input_file)
        print("Done.")

    except Exception as e:
        print(f"An error occurred: {e}", file=sys.stderr)
        import traceback
        traceback.print_exc()
        sys.exit(1)

if __name__ == "__main__":
    main()
