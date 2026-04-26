# CMA Radar Parser

A CLI tool for parsing China Meteorological Administration (CMA) millimeter-wave cloud radar binary data into standard formats (NetCDF, text) with visualization support.

## Features

- **Binary parsing** — Decodes the proprietary CMA YCCR `.BIN` format including site/radar/task configurations, cut configs, and radial moment data
- **NetCDF export** — CF-1.8 compliant NetCDF4 with scale/offset metadata preservation
- **Batch processing** — Multiprocessing-based parallel parsing with automatic site grouping and time-series merging
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
# Export each file to individual NetCDF
cma-radar batch ./data/ -f nc -o ./output/ -w 8

# Merge all files per site into one time-series NetCDF per site
cma-radar batch ./data/ -f nc --merged -o ./output/ -w 8
```

### Visualize a NetCDF file

```bash
cma-radar visualize ./output/58446_merged.nc -o ./plots/
```

## Commands

| Command | Description | Key Options |
|---------|-------------|-------------|
| `parse` | Parse a single `.BIN` file | `-f nc\|txt`, `-o <dir>` |
| `batch` | Batch process a folder | `-f nc\|txt`, `--merged`, `-w <workers>`, `-o <dir>` |
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
| 4 | Differential Reflectivity (ZDR) | dB |
| 7 | Signal-to-Noise Ratio (SNR) | dB |
| 10 | Linear Depolarization Ratio (LDR) | dB |

## Output NetCDF Structure

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
  site_name, latitude, longitude, altitude
  source_file(s)
```

## Requirements

- Python >= 3.10
- numpy
- netCDF4
- typer[rich] >= 0.12
- matplotlib
- scipy

## License

Apache-2.0
