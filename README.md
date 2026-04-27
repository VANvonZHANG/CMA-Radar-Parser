# CMA Radar Parser

A CLI tool for parsing China Meteorological Administration (CMA) millimeter-wave cloud radar binary data into standard formats (NetCDF, text) with visualization support.

## Features

- **Binary parsing** — Decodes the proprietary CMA YCCR `.BIN` format including site/radar/task configurations, cut configs, and radial moment data
- **NetCDF export** — CF-1.8 compliant NetCDF4 with scale/offset metadata preservation; optional CfRadial-2.0 format
- **Batch processing** — Multiprocessing-based parallel parsing with automatic site grouping and time-series merging
- **Data quality control** — Optional `--quality-check` flag to mask physically unreasonable values
- **Visualization** — Time-height plots with SNR filtering and median denoising

## Installation

```bash
pip install cma-radar-parser
```

Or for development:

```bash
git clone https://github.com/<your-username>/cma-radar-parser.git
cd cma-radar-parser
pip install -e ".[dev]"
```

## Usage

### Parse a single file

```bash
cma-radar parse Z_RADA_I_58446_20251010000000_O_YCCR_ZHDKAZ_RAW_MM.BIN -f nc
cma-radar parse Z_RADA_I_58446_20251010000000_O_YCCR_ZHDKAZ_RAW_MM.BIN -f txt -o ./output/
```

### Batch process a folder

```bash
# Default: per-site time-series NetCDF (one file per station)
cma-radar batch ./data/ -f nc -o ./output/ -w 8

# CfRadial 2.0 format (one file per station, with sweep groups)
cma-radar batch ./data/ -f cfradial -o ./output/ -w 8

# Merge all sites into a single NetCDF with groups (only with -f nc)
cma-radar batch ./data/ --merged -o ./output/ -w 8

# Enable data quality control (mask out-of-range values)
cma-radar batch ./data/ -f nc -o ./output/ -w 8 --quality-check
```

### Visualize a NetCDF file

```bash
cma-radar visualize ./output/58446_merged.nc -o ./plots/
```

## Commands

| Command | Description | Key Options |
|---------|-------------|-------------|
| `parse` | Parse a single `.BIN` file | `-f nc\|txt`, `-o <dir>`, `--quality-check` |
| `batch` | Batch process a folder (default: per-site merge) | `-f nc\|cfradial\|txt`, `--merged` (cross-site, nc only), `-w <workers>`, `-o <dir>`, `--quality-check` |
| `visualize` | Create plots from `.nc` file | `-o <dir>` |

## Binary File Format

CMA cloud radar data files follow this structure:

```
GenericHeader (32 bytes, skipped)
├── SiteConfig (72 bytes)    — station name, location, altitude
├── RadarConfig (152 bytes)  — frequency, beam width, range resolution
├── TaskConfig (256 bytes)   — scan type, pulse width, calibration
├── CutConfig × N (256B ea)  — elevation cut parameters
└── RadialData blocks
    ├── RadialHeader (64B)   — azimuth, elevation, timestamp
    └── MomentData × M
        ├── MomentHeader (32B) — data type, scale, offset, bin count
        └── BinData (variable)  — raw values (1 or 2 bytes per gate)
```

File naming convention: `Z_RADA_I_<station_id><yyyymmddhhmmss>_O_YCCR_<site_code>_RAW_MM.BIN`

### Supported Radar Moments

| Key | Variable | Unit |
|-----|----------|------|
| 1 | Reflectivity (Z) | dBZ |
| 2 | Velocity (V) | m/s |
| 3 | Spectrum Width (W) | m/s |
| 4 | Signal-to-Noise Ratio (SNR) | dB |
| 7 | Signal-to-Noise Ratio (SNR) | dB |
| 10 | Linear Depolarization Ratio (LDR) | dB |
| 33 | Differential Reflectivity (ZDR) | dB |
| 34 | Linear Depolarization Ratio (LDR) | dB |

## Output NetCDF Structure

### Per-site merged (`{site_code}_merged.nc`)

```
Dimensions:
  time   — number of radial scans
  range  — number of range gates

Variables:
  time      (time)             — seconds since 1970-01-01 UTC
  range     (range)            — distance in meters
  moment_1  (time, range)      — reflectivity (scale_factor, add_offset as attributes)
  moment_2  (time, range)      — velocity
  ...

Global Attributes:
  Conventions: "CF-1.8"
  site_name, site_code, latitude, longitude, altitude
  source_files
```

### CfRadial 2.0 (`{site_code}_cfradial.nc`, `-f cfradial`)

```
Root:
  Dimensions:
    sweep     = 1
    frequency = 1

  Variables:
    volume_number         — scan volume index
    time_coverage_start   — ISO 8601 timestamp
    time_coverage_end     — ISO 8601 timestamp
    sweep_group_name      — ["sweep_0001"]
    sweep_fixed_angle     — fixed elevation angle
    frequency             — radar transmit frequency

  Attributes:
    Conventions: "CfRadial-2.0"
    instrument_name, site_name, latitude, longitude, altitude
    field_names — list of exported moments (e.g., ["DBZH", "VRADH", "WRADH", "SNR"])

  Group: sweep_0001:
    Dimensions:
      time   — number of rays (one per minute for vertical pointing)
      range  — number of range gates

    Coordinate variables:
      time      (time)     — seconds since first ray
      range     (range)    — distance to measurement volume (m)
      elevation (time)     — 90.0° for vertical pointing
      azimuth   (time)     — 0.0°

    Field variables:
      DBZH  (time, range)  — reflectivity (dBZ)
      VRADH (time, range)  — radial velocity (m/s)
      WRADH (time, range)  — spectrum width (m/s)
      SNR   (time, range)  — signal-to-noise ratio (dB)

  Group: radar_parameters (optional):
    radar_beam_width_h, radar_beam_width_v, radar_wavelength, radar_antenna_gain_h

  Group: calibration_parameters (optional):
    radar_measured_sky_noise, calibration_offset_h
```

### Cross-site merged (`all_sites_merged.nc`, `--merged` flag)

```
Root:
  Dimensions:
    site   — number of stations

  Variables:
    site_name  (site)   — station name
    latitude   (site)   — latitude
    longitude  (site)   — longitude
    altitude   (site)   — altitude

  Groups:
    /<site_code>/       — one group per station
      Dimensions: time, range
      Variables: time, range, moment_*, ...
      Attributes: site_name, site_code, latitude, longitude, altitude
```

## Data Quality Control

The dataset contains data from two radar manufacturers (`ZHDKAZ` and `HMBKPS`) with different conventions for invalid data:

- **ZHDKAZ**: Uses `-200` as a blind-zone marker (all moments) and `-100` as a no-reliable-signal marker (velocity and spectrum-width only). These are not physically valid values.
- **HMBKPS**: Uses `NaN` for invalid data.

Enable quality checking with `--quality-check`:

```bash
cma-radar batch ./data/ -f nc -o ./output/ --quality-check
cma-radar parse file.BIN -f nc -o ./output/ --quality-check
```

When enabled, values outside physically reasonable ranges are replaced with `_FillValue` (-999.0) and automatically masked by NetCDF readers.

| DataType | Variable | Range | Unit |
|----------|----------|-------|------|
| 1 | Reflectivity | [-50, 30] | dBZ |
| 2 | Velocity | [-30, 30] | m/s |
| 3 | Spectrum Width | [0, 20] | m/s |
| 4 / 7 | SNR | [-30, 60] | dB |
| 10 / 34 | LDR | [-40, 10] | dB |
| 33 | ZDR | [-10, 10] | dB |

## Requirements

- Python >= 3.10
- numpy
- netCDF4
- typer[rich] >= 0.12
- matplotlib
- scipy

## License

Apache-2.0
