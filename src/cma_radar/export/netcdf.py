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


def _sort_and_dedup(
    all_data: list[CmaRadarData],
    source_filenames: list[str] | None,
) -> tuple[list[CmaRadarData], list[str], int]:
    """Sort by timestamp, deduplicate, and compute max range gates.

    Returns:
        deduped_data: Sorted list with duplicate timestamps removed (keeps first).
        deduped_filenames: Corresponding source filenames.
        max_n_gates: Maximum number of range gates across all files.
    """
    # Sort by timestamp
    sorted_data = sorted(
        all_data,
        key=lambda d: d.radials[0].header.Seconds if d and d.radials else float("inf"),
    )

    # Build timestamp -> filename map for dedup tracking
    file_map: dict[float, str] = {}
    if source_filenames is not None:
        file_map = {
            d.radials[0].header.Seconds: f
            for d, f in zip(sorted_data, source_filenames)
            if d and d.radials
        }

    # Deduplicate by timestamp (keep first)
    unique_data: list[CmaRadarData] = []
    unique_filenames: list[str] = []
    seen_timestamps: set[float] = set()

    for data in sorted_data:
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

    # Compute max range gates
    max_n_gates = 0
    for data in unique_data:
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

    return unique_data, unique_filenames, max_n_gates


def _write_merged_data(
    nc_or_grp,
    all_data: list[CmaRadarData],
    source_filenames: list[str] | None,
) -> None:
    """Shared helper that writes merged time-series data into a NetCDF Dataset or Group.

    Handles sorting by timestamp, deduplication, gate-count computation,
    dimension/variable creation, and moment data writing.

    Args:
        nc_or_grp: A netCDF4 Dataset or Group to write into.
        all_data: List of CmaRadarData objects (may contain duplicates or None entries).
        source_filenames: Optional list of source filenames corresponding to *all_data*
            entries.  When provided, a ``source_files`` attribute is set on the
            group/dataset.  Pass ``None`` when the caller already sets this attribute.
    """
    unique_data, unique_filenames, max_n_gates = _sort_and_dedup(
        all_data, source_filenames
    )

    first_data = unique_data[0]
    n_time = len(unique_data)

    # Dimensions
    nc_or_grp.createDimension("time", n_time)
    nc_or_grp.createDimension("range", max_n_gates)

    # Time variable
    time_var = nc_or_grp.createVariable("time", "f8", ("time",))
    time_var.units = "seconds since 1970-01-01 00:00:00 +00:00"
    time_var.long_name = "Time"

    # Range variable
    range_var = nc_or_grp.createVariable("range", "f4", ("range",))
    range_var.units = "m"
    range_var.long_name = "Range from instrument"
    range_var[:] = (
        first_data.cut_configs[0].StartRange
        + np.arange(max_n_gates) * first_data.radar_config.DistanceSolution
    )

    # Site attributes on group (used by cross-site groups)
    if first_data.site_config:
        site = first_data.site_config
        nc_or_grp.setncattr("site_name", site.SiteName)
        nc_or_grp.setncattr("site_code", site.SiteCode)
        nc_or_grp.setncattr("latitude", f"{site.Latitude:.4f}")
        nc_or_grp.setncattr("longitude", f"{site.Longitude:.4f}")
        nc_or_grp.setncattr("altitude", f"{site.AntennaHeight:.1f}")

    # Source files attribute (only when source_filenames provided)
    if source_filenames is not None:
        nc_or_grp.source_files = ", ".join(
            os.path.basename(f) for f in unique_filenames
        )

    # Moment variables
    all_moment_keys = sorted(
        list(set(key for data in unique_data for key in data.radials[0].variable.keys()))
    )

    moment_vars = {}
    for key in all_moment_keys:
        var_name = f"moment_{key}"
        moment_vars[key] = nc_or_grp.createVariable(
            var_name, "f4", ("time", "range"), fill_value=FILL_VALUE
        )
        first_occurrence_header = next(
            d.radials[0].variable[key].header
            for d in unique_data
            if key in d.radials[0].variable
        )
        moment_vars[key].setncattr("scale_factor", float(first_occurrence_header.Scale))
        moment_vars[key].setncattr("add_offset", float(first_occurrence_header.Offset))
        moment_vars[key].setncattr("comment", f"Original moment data for key {key}")

    # Write time and moment data
    time_values = []
    for i, data in enumerate(unique_data):
        time_values.append(data.radials[0].header.Seconds)
        for key, var in moment_vars.items():
            if key in data.radials[0].variable:
                moment_value = data.radials[0].variable[key].value
                n_gates_current = len(moment_value)
                var[i, :n_gates_current] = moment_value

    time_var[:] = time_values


def write_merged_nc(
    all_data: list[CmaRadarData],
    output_filename: str,
    source_filenames: list[str],
) -> None:
    """Aggregates data from multiple CmaRadarData objects into a single time-series NetCDF."""
    if not all_data:
        raise ValueError("No data to write.")

    with netCDF4.Dataset(output_filename, "w", format="NETCDF4_CLASSIC") as nc:
        nc.setncattr("Conventions", "CF-1.8")

        first_data = next((d for d in all_data if d and d.radials), None)
        if first_data and first_data.site_config:
            site = first_data.site_config
            nc.setncattr("site_name", site.SiteName)
            nc.setncattr("latitude", f"{site.Latitude:.4f}")
            nc.setncattr("longitude", f"{site.Longitude:.4f}")
            nc.setncattr("altitude", f"{site.AntennaHeight:.1f}")

        nc.history = f"{datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')} - File created"

        _write_merged_data(nc, all_data, source_filenames)


def write_cross_site_nc(
    grouped_data: dict[str, list[tuple[CmaRadarData, str]]],
    output_filename: str,
) -> None:
    """Merge all sites into a single NetCDF file, one group per site.

    Args:
        grouped_data: Dict mapping site_code to list of (CmaRadarData, source_filename).
        output_filename: Output NetCDF file path.
    """
    if not grouped_data:
        raise ValueError("No data to write.")

    sorted_sites = sorted(grouped_data.keys())

    with netCDF4.Dataset(output_filename, "w", format="NETCDF4") as nc:
        nc.setncattr("Conventions", "CF-1.8")
        nc.history = f"{datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')} - File created"

        # Root-level site index
        n_sites = len(sorted_sites)
        nc.createDimension("site", n_sites)

        site_names_var = nc.createVariable("site_name", str, ("site",))
        lat_var = nc.createVariable("latitude", "f4", ("site",))
        lon_var = nc.createVariable("longitude", "f4", ("site",))
        alt_var = nc.createVariable("altitude", "f4", ("site",))

        all_source_files = []
        for i, site_code in enumerate(sorted_sites):
            items = grouped_data[site_code]
            first_data = items[0][0]
            if first_data.site_config:
                site = first_data.site_config
                site_names_var[i] = site.SiteName
                lat_var[i] = site.Latitude
                lon_var[i] = site.Longitude
                alt_var[i] = site.AntennaHeight
            else:
                site_names_var[i] = site_code
            all_source_files.extend(fp for _, fp in items)

        nc.source_files = ", ".join(os.path.basename(f) for f in all_source_files)

        # One group per site
        for site_code in sorted_sites:
            items = grouped_data[site_code]
            data_list = [d for d, _ in items]
            grp = nc.createGroup(site_code)

            _write_merged_data(grp, data_list, None)
