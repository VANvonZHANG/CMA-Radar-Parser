"""NetCDF export functions for CMA radar data."""

import datetime
import logging
import os

import netCDF4
import numpy as np

from cma_radar.reader import CmaRadarData

logger = logging.getLogger(__name__)

FILL_VALUE = -999.0

# CfRadial 2.0 field mapping for CMA DataType keys
CFRADIAL_FIELD_MAP = {
    1: {
        "var_name": "DBZH",
        "standard_name": "equivalent_reflectivity_factor",
        "long_name": "Equivalent reflectivity factor",
        "units": "dBZ",
    },
    2: {
        "var_name": "VRADH",
        "standard_name": "radial_velocity_of_scatterers_away_from_instrument",
        "long_name": "Radial velocity of scatterers away from instrument",
        "units": "m/s",
    },
    3: {
        "var_name": "WRADH",
        "standard_name": "doppler_spectrum_width",
        "long_name": "Doppler spectrum width",
        "units": "m/s",
    },
    4: {
        "var_name": "SNR",
        "standard_name": "signal_to_noise_ratio",
        "long_name": "Signal to noise ratio",
        "units": "dB",
    },
}


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

    # Build timestamp -> filename map for dedup tracking (keep first)
    file_map: dict[float, str] = {}
    if source_filenames is not None:
        for d, f in zip(sorted_data, source_filenames):
            if d and d.radials:
                ts = d.radials[0].header.Seconds
                if ts not in file_map:
                    file_map[ts] = f

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

def write_cfradial_nc(
    all_data: list[CmaRadarData],
    output_filename: str,
    source_filenames: list[str],
) -> None:
    """Export CMA radar data to CfRadial 2.0 format NetCDF.

    Creates a NetCDF4 file with a root group (global metadata) and a single
    sweep group (sweep_0001) containing all vertical-pointing time-series data.

    Only exports DataType keys present in CFRADIAL_FIELD_MAP (1, 2, 3, 4).
    Unknown DataType keys are silently ignored.
    """
    if not all_data:
        raise ValueError("No data to write.")

    unique_data, _, max_n_gates = _sort_and_dedup(all_data, source_filenames)
    first_data = unique_data[0]
    n_time = len(unique_data)

    # Validate all data is from the same site
    site_codes = {
        d.site_config.SiteCode for d in unique_data if d.site_config
    }
    if len(site_codes) > 1:
        raise ValueError(
            f"Mixed site codes found: {site_codes}. "
            "CfRadial export requires single-site data."
        )

    # Determine which fields are present in the data
    present_keys = set()
    for data in unique_data:
        if data.radials:
            present_keys.update(data.radials[0].variable.keys())

    export_keys = sorted(k for k in present_keys if k in CFRADIAL_FIELD_MAP)
    if not export_keys:
        raise ValueError("No recognized moment types found for CfRadial export.")

    field_names = [CFRADIAL_FIELD_MAP[k]["var_name"] for k in export_keys]

    with netCDF4.Dataset(output_filename, "w", format="NETCDF4") as nc:
        site = first_data.site_config
        radar = first_data.radar_config
        cut = first_data.cut_configs[0] if first_data.cut_configs else None

        # --- Root group global attributes ---
        nc.setncattr("Conventions", "CfRadial-2.0")
        nc.setncattr("version", "2.0")
        nc.setncattr("instrument_type", "radar")
        nc.setncattr("platform_type", "fixed")
        nc.setncattr("platform_is_mobile", "false")
        nc.setncattr("instrument_name", site.SiteName if site else "")
        nc.setncattr("site_name", site.SiteCode if site else "")
        nc.setncattr("latitude", float(site.Latitude) if site else 0.0)
        nc.setncattr("longitude", float(site.Longitude) if site else 0.0)
        nc.setncattr("altitude", float(site.AntennaHeight) if site else 0.0)

        # Time coverage
        first_time = datetime.datetime.fromtimestamp(
            unique_data[0].radials[0].header.Seconds, datetime.timezone.utc
        )
        last_time = datetime.datetime.fromtimestamp(
            unique_data[-1].radials[0].header.Seconds, datetime.timezone.utc
        )
        nc.setncattr("time_coverage_start", first_time.strftime("%Y-%m-%dT%H:%M:%SZ"))
        nc.setncattr("time_coverage_end", last_time.strftime("%Y-%m-%dT%H:%M:%SZ"))
        nc.setncattr("field_names", field_names)

        nc.history = f"{datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')} - File created"
        if source_filenames:
            nc.source_files = ", ".join(
                os.path.basename(f) for f in source_filenames
            )

        # --- Root group dimensions and variables ---
        nc.createDimension("sweep", 1)
        nc.createDimension("frequency", 1)

        nc.createVariable("volume_number", "i4")[:] = 0

        t_start_var = nc.createVariable("time_coverage_start", str)
        t_start_var[0] = first_time.strftime("%Y-%m-%dT%H:%M:%SZ")
        t_end_var = nc.createVariable("time_coverage_end", str)
        t_end_var[0] = last_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        sweep_names = nc.createVariable("sweep_group_name", str, ("sweep",))
        sweep_names[:] = np.array(["sweep_0001"], dtype=object)

        sweep_fixed = nc.createVariable("sweep_fixed_angle", "f4", ("sweep",))
        sweep_fixed[:] = [90.0]

        if radar and radar.Frequency and radar.Frequency > 0:
            freq_var = nc.createVariable("frequency", "f4", ("frequency",))
            freq_var[:] = [radar.Frequency]

        # --- Sweep group ---
        sweep_grp = nc.createGroup("sweep_0001")
        sweep_grp.createDimension("time", n_time)
        sweep_grp.createDimension("range", max_n_gates)

        # Reference time string for time coordinate
        ref_time_str = first_time.strftime("%Y-%m-%dT%H:%M:%SZ")

        # Time coordinate
        time_var = sweep_grp.createVariable("time", "f8", ("time",))
        time_var.setncattr("standard_name", "time")
        time_var.setncattr("units", f"seconds since {ref_time_str}")
        time_var.setncattr("calendar", "gregorian")

        # Range coordinate
        start_range = cut.StartRange if cut else 0
        gate_spacing = radar.DistanceSolution if radar else 30
        range_values = start_range + np.arange(max_n_gates) * gate_spacing

        range_var = sweep_grp.createVariable("range", "f4", ("range",))
        range_var.setncattr("standard_name", "projection_range_coordinate")
        range_var.setncattr("long_name", "range_to_measurement_volume")
        range_var.setncattr("units", "m")
        range_var.setncattr("axis", "radial_range_coordinate")
        range_var.setncattr("spacing_is_constant", "true")
        range_var.setncattr("meters_to_center_of_first_gate", float(start_range + gate_spacing / 2))
        range_var.setncattr("meters_between_gates", float(gate_spacing))
        range_var[:] = range_values

        # Elevation coordinate
        elev_var = sweep_grp.createVariable("elevation", "f4", ("time",))
        elev_var.setncattr("standard_name", "ray_elevation_angle")
        elev_var.setncattr("long_name", "elevation_angle_from_horizontal_plane")
        elev_var.setncattr("units", "degrees")
        elev_var.setncattr("axis", "radial_elevation_coordinate")

        # Azimuth coordinate
        az_var = sweep_grp.createVariable("azimuth", "f4", ("time",))
        az_var.setncattr("standard_name", "ray_azimuth_angle")
        az_var.setncattr("long_name", "azimuth_angle_from_true_north")
        az_var.setncattr("units", "degrees")
        az_var.setncattr("axis", "radial_azimuth_coordinate")

        # Sweep metadata variables
        sweep_num = sweep_grp.createVariable("sweep_number", "i4")
        sweep_num[:] = 0

        sweep_mode = sweep_grp.createVariable("sweep_mode", str)
        sweep_mode[0] = "vertical_pointing"

        fixed_angle = sweep_grp.createVariable("fixed_angle", "f4")
        fixed_angle.setncattr("units", "degrees")
        fixed_angle[:] = 90.0

        scan_rate = sweep_grp.createVariable("scan_rate", "f4", ("time",))
        scan_rate.setncattr("units", "degrees/s")

        nyq_var = sweep_grp.createVariable("nyquist_velocity", "f4", ("time",))
        nyq_var.setncattr("units", "m/s")

        prt_var = sweep_grp.createVariable("prt", "f4", ("time",))
        prt_var.setncattr("units", "seconds")

        # Pulse width
        pw_var = sweep_grp.createVariable("pulse_width", "f4", ("time",))
        pw_var.setncattr("units", "seconds")

        # --- Field data variables ---
        field_vars = {}
        for key in export_keys:
            cfg = CFRADIAL_FIELD_MAP[key]
            fv = sweep_grp.createVariable(
                cfg["var_name"],
                "f4",
                ("time", "range"),
                fill_value=np.nan,
            )
            fv.setncattr("standard_name", cfg["standard_name"])
            fv.setncattr("long_name", cfg["long_name"])
            fv.setncattr("units", cfg["units"])
            fv.setncattr("coordinates", "elevation azimuth range")
            field_vars[key] = fv

        # --- Write per-ray data ---
        time_values = []
        scan_rate_vals = []
        nyq_vals = []
        prt_vals = []
        pw_vals = []
        elev_vals = []
        az_vals = []

        for i, data in enumerate(unique_data):
            radial = data.radials[0]
            header = radial.header

            # Time: seconds since reference
            time_values.append(header.Seconds + header.Microseconds / 1e6)
            elev_vals.append(header.Elevation)
            az_vals.append(header.Azimuth)

            # Metadata from CutConfig
            data_cut = data.cut_configs[0] if data.cut_configs else None
            scan_rate_vals.append(data_cut.ScanSpeed if data_cut else 0.0)
            nyq_vals.append(data_cut.NyquistSpeed if data_cut else 0.0)

            if data_cut and data_cut.PRF1 and data_cut.PRF1 > 0:
                prt_vals.append(1.0 / data_cut.PRF1)
            else:
                prt_vals.append(np.nan)

            # Pulse width
            task = data.task_config
            pw_ns = 0
            if data_cut and task:
                mode = data_cut.PulseWidthCombinationMode
                if mode == 1:
                    pw_ns = task.PulseWidth1
                elif mode == 2:
                    pw_ns = task.PulseWidth2
                elif mode == 3:
                    pw_ns = task.PulseWidth3
                elif mode == 4:
                    pw_ns = task.PulseWidth4
            pw_vals.append(pw_ns / 1e9 if pw_ns > 0 else np.nan)

            # Field data
            for key, var in field_vars.items():
                if key in radial.variable:
                    moment_value = radial.variable[key].value
                    n_gates_current = len(moment_value)
                    var[i, :n_gates_current] = moment_value

        # Write coordinate data
        time_var[:] = np.array(time_values) - time_values[0]
        elev_var[:] = elev_vals
        az_var[:] = az_vals
        scan_rate[:] = scan_rate_vals
        nyq_var[:] = nyq_vals
        prt_var[:] = prt_vals
        pw_var[:] = pw_vals

        # --- Optional metadata groups ---
        if radar:
            rp = nc.createGroup("radar_parameters")
            rp.setncattr("comment", "Radar parameters from CMA binary configuration")

            if radar.BeamWidthHori and radar.BeamWidthHori > 0:
                bw_h = rp.createVariable("radar_beam_width_h", "f4")
                bw_h.setncattr("units", "degrees")
                bw_h[:] = radar.BeamWidthHori

            if radar.BeamWidthVert and radar.BeamWidthVert > 0:
                bw_v = rp.createVariable("radar_beam_width_v", "f4")
                bw_v.setncattr("units", "degrees")
                bw_v[:] = radar.BeamWidthVert

            if radar.Wavelength and radar.Wavelength > 0:
                wl = rp.createVariable("radar_wavelength", "f4")
                wl.setncattr("units", "m")
                wl[:] = radar.Wavelength

            if radar.AntennaGain and radar.AntennaGain > 0:
                ag = rp.createVariable("radar_antenna_gain_h", "f4")
                ag.setncattr("units", "dB")
                ag[:] = radar.AntennaGain

        if first_data.task_config:
            task = first_data.task_config
            cp = nc.createGroup("calibration_parameters")
            cp.setncattr("comment", "Calibration parameters from CMA binary task configuration")

            if task.HorizontalNoise and task.HorizontalNoise != 0.0:
                noise = cp.createVariable("radar_measured_sky_noise", "f4")
                noise.setncattr("units", "dB")
                noise[:] = task.HorizontalNoise

            if task.HorizontalCalibration1 and task.HorizontalCalibration1 != 0.0:
                cal = cp.createVariable("calibration_offset_h", "f4")
                cal.setncattr("units", "dB")
                cal[:] = task.HorizontalCalibration1
