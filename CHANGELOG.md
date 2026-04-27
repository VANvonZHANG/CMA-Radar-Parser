# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.3.0] - 2026-04-27

### Added

- **CfRadial 2.0 export** (`write_cfradial_nc()`) — Exports CMA radar data to CfRadial-2.0 compliant NetCDF:
  - Root group with global metadata: `Conventions: "CfRadial-2.0"`, `instrument_name`, `site_name`, `latitude`, `longitude`, `altitude`, `time_coverage_start/end`, `field_names`
  - Single sweep group `sweep_0001` containing all vertical-pointing time-series data
  - Coordinate variables: `time` (seconds since first ray), `range` (m), `elevation` (90°), `azimuth` (0°)
  - Field variables with CF standard names: `DBZH`, `VRADH`, `WRADH`, `SNR` (only exported if present in data)
  - Optional metadata groups: `radar_parameters` (beam width, wavelength, antenna gain) and `calibration_parameters` (sky noise, calibration offset)
  - Uses NETCDF4 format (groups require it)
  - CLI: `cma-radar batch <folder> --format cfradial`
- **Data quality control** (`--quality-check` flag) — Optional validation of moment values against physically reasonable ranges:
  - Defines `QUALITY_RANGES` for 8 DataType keys (Reflectivity, Velocity, Spectrum Width, SNR, LDR, ZDR)
  - Replaces out-of-range values with `_FillValue` (-999.0), automatically masked by NetCDF readers
  - Available for both `parse` and `batch` commands; off by default to preserve raw data
  - Handles manufacturer-specific marker values: ZHDKAZ uses `-200` (blind zone) and `-100` (no signal); HMBKPS uses `NaN`
- **`_sort_and_dedup()`** helper — Extracted shared sort/dedup logic for reuse across export functions

### Fixed

- Corrected `MOMENT_NAMES` DataType mapping: key `4` = SNR (was incorrectly ZDR)
- Added keys `33` (ZDR) and `34` (LDR) to `MOMENT_NAMES`
- Fixed `_sort_and_dedup()` to preserve first filename when duplicate timestamps exist

## [0.2.0] - 2026-04-26

### Changed

- **`batch` default behavior** — Per-site time-series merging is now the default output (previously required `--merged` flag)
- **`--merged` flag** — Repurposed to merge all sites into a single NetCDF file using NetCDF groups

### Added

- **`write_cross_site_nc()`** — Multi-site NetCDF export with one group per station:
  - Root level: `site` dimension with `site_name`, `latitude`, `longitude`, `altitude` index arrays
  - Per-site groups: independent `time`, `range` dimensions and moment variables
  - Uses NETCDF4 format (required for groups and variable-length strings)
- **`_write_merged_data()`** — Shared helper for per-site and cross-site merging, eliminating code duplication

### Fixed

- Restored early `--merged` format validation before parsing phase (prevents unnecessary wait on invalid flag combinations)

## [0.1.0] - 2026-04-26

Initial release. Refactored from 5 standalone scripts into a unified CLI tool.

### Added

- **Binary parser** (`cma_radar.reader`) — Decodes CMA YCCR proprietary binary format:
  - Parses GenericHeader, SiteConfig (72B), RadarConfig (152B), TaskConfig (256B), CutConfig (256B each), and RadialData blocks
  - Supports all radar moments: Reflectivity, Velocity, Spectrum Width, ZDR, SNR, LDR, and vendor-extended keys
  - Handles scale/offset decoding, NaN substitution for invalid/missing gates, and graceful error recovery for corrupted files
- **CLI** (`cma-radar`) — Typer-based command-line interface with 3 commands:
  - `cma-radar parse <file>` — Parse a single `.BIN` file, print rich summary table, export to NetCDF (default) or text
  - `cma-radar batch <folder>` — Parallel processing with `multiprocessing.Pool`, supports `--merged` to group by site into time-series NetCDF, `--workers` for concurrency control
  - `cma-radar visualize <file.nc>` — Time-height plots with SNR filtering (threshold -12 dB) and 5x5 median denoising
- **NetCDF export** (`cma_radar.export.netcdf`) — CF-1.8 compliant output:
  - `write_nc()` — Single-file NetCDF with per-moment scale/offset attributes
  - `write_merged_nc()` — Multi-file time-series merge with timestamp deduplication, variable gate count padding, and per-site grouping
- **Text export** (`cma_radar.export.text`) — Human-readable output with all config blocks and raw moment data arrays
- **Visualization** (`cma_radar.viz.plot`) — Matplotlib-based time-height plots for Reflectivity and Velocity with log-scale y-axis
- **Packaging** — `pyproject.toml` with hatchling build system, `pip install cma-radar-parser` support
- **Rich console output** — Colored summary tables, progress bars for batch processing, structured error messages via `rich`
- **Apache-2.0 license**

### Changed

- Replaced 5 standalone argparse scripts (`ReadParseSingleFile.py`, `BatchParse.py`, `ParseToRawNc.py`, `BatchToMergedNc.py`, `visualize_radar_nc.py`) with unified `cma-radar` CLI
- Project structure migrated to `src/` layout with `src/cma_radar/` package namespace

### Tested

- Validated against 22,299 real `.BIN` files across 17 radar sites
- Successfully produced 17 merged NetCDF files (26-44 MB each) with 8-worker parallel processing
- Confirmed graceful handling of 3 known corrupted files

[0.3.0]: https://github.com/VANvonZHANG/CMA-Radar-Parser/releases/tag/v0.3.0
[0.2.0]: https://github.com/VANvonZHANG/CMA-Radar-Parser/releases/tag/v0.2.0
[0.1.0]: https://github.com/VANvonZHANG/CMA-Radar-Parser/releases/tag/v0.1.0
