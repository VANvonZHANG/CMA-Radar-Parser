# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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

[0.1.0]: https://github.com/VANvonZHANG/CMA-Radar-Parser/releases/tag/v0.1.0
