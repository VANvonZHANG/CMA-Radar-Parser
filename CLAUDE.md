# CMA Radar Parser

## Project Overview

Parses CMA millimeter-wave cloud radar (YCCR) binary .BIN files into NetCDF/text formats.
Built as a Python package (`cma-radar-parser`) with a Typer CLI.

## Structure

- `src/cma_radar/cli.py` - Typer CLI entry point (`cma-radar` command)
- `src/cma_radar/reader/cma_reader.py` - Core binary parser (read_cma_radar → CmaRadarData)
- `src/cma_radar/export/netcdf.py` - NetCDF export (write_nc, write_merged_nc, write_cross_site_nc, write_cfradial_nc, _apply_quality_check)
- `src/cma_radar/export/text.py` - Text export (write_txt)
- `src/cma_radar/viz/plot.py` - Visualization (visualize_nc)

## CLI

`pip install -e .` to install, then:
- `cma-radar parse <file> -f nc|txt -o <dir>`
- `cma-radar parse <file> -f nc|txt -o <dir>`
- `cma-radar batch <folder> -f nc|cfradial|txt -w <n> -o <dir>` — default: per-site time-series NetCDF; `--format cfradial` produces CfRadial-2.0 per-site files
- `cma-radar batch <folder> --merged -w <n> -o <dir>` — all sites in one NetCDF with groups (only with `-f nc`)
- `cma-radar batch <folder> -f nc --quality-check -o <dir>` — replace out-of-range values with _FillValue (-999.0)
- `cma-radar visualize <file.nc> -o <dir>`

## Binary File Format

- GenericHeader (32 bytes, skipped) → SiteConfig (72B) → RadarConfig (152B) → TaskConfig (256B) → CutConfig×N (256B each) → RadialData blocks
- File pattern: `Z_RADA_I_<5-digit-id><14-digit-timestamp>_O_YCCR_*_RAW_MM.BIN`
- Moment keys: 1=Reflectivity, 2=Velocity, 3=SpectrumWidth, 4=SNR, 7=SNR, 10=LDR, 33=ZDR, 34=LDR

## Data Quality Notes

- **Two manufacturers** in the dataset: `ZHDKAZ` and `HMBKPS`
  - `ZHDKAZ`: Uses `-200` as blind-zone marker (all moments) and `-100` as no-reliable-signal marker (velocity/spectrum-width only). These fall outside physical ranges.
  - `HMBKPS`: Uses `NaN` for invalid data.
- `--quality-check` flag replaces values outside `QUALITY_RANGES` with `_FillValue` (-999.0). Off by default to preserve raw data.

## Environment

- Python 3.10+, hatchling build system
- Dependencies: numpy, netCDF4, typer[rich], matplotlib, scipy
- Test data: `/data/MountainObs/CloudRadar/20251010bin/` (22k+ RAW files, 17 sites)
- Some .BIN files may be corrupted (3 out of 22299 known bad) - parser handles gracefully
- NetCDF formats: `write_nc`/`write_merged_nc` use NETCDF4_CLASSIC; `write_cross_site_nc` uses NETCDF4 (groups require it); `write_cfradial_nc` uses NETCDF4 (groups require it)
