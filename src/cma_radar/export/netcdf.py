"""NetCDF export functions for CMA radar data."""

import datetime
import logging
import os

import netCDF4
import numpy as np

from cma_radar.reader import CmaRadarData

logger = logging.getLogger(__name__)

FILL_VALUE = -999.0


def write_nc(cma_data: CmaRadarData, output_filename: str, source_filename: str) -> None:
    """Writes parsed CMA radar data to a single-file NetCDF."""
    if not cma_data.radials:
        raise ValueError("No data to write.")

    first_radial = cma_data.radials[0]

    with netCDF4.Dataset(output_filename, "w", format="NETCDF4_CLASSIC") as nc:
        if cma_data.site_config:
            site = cma_data.site_config
            nc.setncattr("site_code", site.SiteCode)
            nc.setncattr("site_name", site.SiteName)
            nc.setncattr("latitude", f"{site.Latitude:.4f}")
            nc.setncattr("longitude", f"{site.Longitude:.4f}")
            nc.setncattr("altitude", f"{site.AntennaHeight:.1f}")

        nc.history = f"{datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')} - File created"
        nc.source_file = os.path.basename(source_filename)

        n_gates = next(iter(first_radial.variable.values())).header.BinNumber

        nc.createDimension("time", len(cma_data.radials))
        nc.createDimension("range", n_gates)

        time_var = nc.createVariable("time", "f8", ("time",))
        time_var.units = "seconds since 1970-01-01 00:00:00 +00:00"
        time_var.long_name = "Time"

        range_var = nc.createVariable("range", "f4", ("range",))
        range_var.units = "m"
        range_var.long_name = "Range from instrument"
        range_var[:] = cma_data.cut_configs[0].StartRange + np.arange(n_gates) * cma_data.radar_config.DistanceSolution

        all_moment_keys = sorted(
            list(set(key for radial in cma_data.radials for key in radial.variable.keys()))
        )

        moment_vars = {}
        for key in all_moment_keys:
            var_name = f"moment_{key}"
            moment_vars[key] = nc.createVariable(
                var_name, "f4", ("time", "range"), fill_value=FILL_VALUE
            )
            first_occurrence_header = next(
                radial.variable[key].header
                for radial in cma_data.radials
                if key in radial.variable
            )
            moment_vars[key].setncattr("scale_factor", float(first_occurrence_header.Scale))
            moment_vars[key].setncattr("add_offset", float(first_occurrence_header.Offset))
            moment_vars[key].setncattr("comment", f"Original moment data for key {key}")

        time_values = []
        for i, radial in enumerate(cma_data.radials):
            time_values.append(radial.header.Seconds)
            for key, var in moment_vars.items():
                if key in radial.variable:
                    var[i, :] = radial.variable[key].value
                else:
                    var[i, :] = np.full(n_gates, FILL_VALUE)

        time_var[:] = time_values


def write_merged_nc(
    all_data: list[CmaRadarData],
    output_filename: str,
    source_filenames: list[str],
) -> None:
    """Aggregates data from multiple CmaRadarData objects into a single time-series NetCDF."""
    if not all_data:
        raise ValueError("No data to write.")

    file_map = {
        d.radials[0].header.Seconds: f
        for d, f in zip(all_data, source_filenames)
        if d and d.radials
    }

    all_data.sort(
        key=lambda d: d.radials[0].header.Seconds if d and d.radials else float("inf")
    )

    unique_data = []
    unique_filenames = []
    seen_timestamps = set()

    for data in all_data:
        if not (data and data.radials):
            continue
        timestamp = data.radials[0].header.Seconds
        if timestamp not in seen_timestamps:
            unique_data.append(data)
            if timestamp in file_map:
                unique_filenames.append(file_map[timestamp])
            seen_timestamps.add(timestamp)
        else:
            logger.warning("Duplicate timestamp %s found, skipping.", timestamp)

    if not unique_data:
        raise ValueError("No data with unique timestamps to write.")

    all_data = unique_data
    source_filenames = unique_filenames

    max_n_gates = 0
    for data in all_data:
        try:
            current_max = max(
                mom.header.BinNumber for mom in data.radials[0].variable.values()
            )
            if current_max > max_n_gates:
                max_n_gates = current_max
        except (ValueError, IndexError):
            continue

    if max_n_gates == 0:
        raise ValueError("Could not determine a valid number of range gates from any file.")

    first_data = all_data[0]
    n_time = len(all_data)

    with netCDF4.Dataset(output_filename, "w", format="NETCDF4_CLASSIC") as nc:
        nc.setncattr("Conventions", "CF-1.8")
        if first_data.site_config:
            site = first_data.site_config
            nc.setncattr("site_name", site.SiteName)
            nc.setncattr("latitude", f"{site.Latitude:.4f}")
            nc.setncattr("longitude", f"{site.Longitude:.4f}")
            nc.setncattr("altitude", f"{site.AntennaHeight:.1f}")
        nc.history = f"{datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')} - File created"
        nc.source_files = ", ".join(os.path.basename(f) for f in source_filenames)

        nc.createDimension("time", n_time)
        nc.createDimension("range", max_n_gates)

        time_var = nc.createVariable("time", "f8", ("time",))
        time_var.units = "seconds since 1970-01-01 00:00:00 +00:00"
        time_var.long_name = "Time"

        range_var = nc.createVariable("range", "f4", ("range",))
        range_var.units = "m"
        range_var.long_name = "Range from instrument"
        range_var[:] = (
            first_data.cut_configs[0].StartRange
            + np.arange(max_n_gates) * first_data.radar_config.DistanceSolution
        )

        all_moment_keys = sorted(
            list(
                set(
                    key
                    for data in all_data
                    for key in data.radials[0].variable.keys()
                )
            )
        )

        moment_vars = {}
        for key in all_moment_keys:
            var_name = f"moment_{key}"
            moment_vars[key] = nc.createVariable(
                var_name, "f4", ("time", "range"), fill_value=FILL_VALUE
            )
            first_occurrence_header = next(
                d.radials[0].variable[key].header
                for d in all_data
                if key in d.radials[0].variable
            )
            moment_vars[key].setncattr("scale_factor", float(first_occurrence_header.Scale))
            moment_vars[key].setncattr("add_offset", float(first_occurrence_header.Offset))
            moment_vars[key].setncattr("comment", f"Original moment data for key {key}")

        time_values = []
        for i, data in enumerate(all_data):
            time_values.append(data.radials[0].header.Seconds)
            for key, var in moment_vars.items():
                if key in data.radials[0].variable:
                    moment_value = data.radials[0].variable[key].value
                    n_gates_current = len(moment_value)
                    var[i, :n_gates_current] = moment_value

        time_var[:] = time_values
