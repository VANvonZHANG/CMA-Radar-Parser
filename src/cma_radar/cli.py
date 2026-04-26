"""CLI entry point for CMA Radar Parser."""

import datetime
import logging
import multiprocessing
import os
import re
from enum import Enum
from typing import Annotated, Optional

import typer
from rich.console import Console
from rich.logging import RichHandler
from rich.progress import Progress, SpinnerColumn, TextColumn, BarColumn, TaskProgressColumn
from rich.table import Table

from cma_radar.reader import read_cma_radar, CmaRadarData
from cma_radar.export.text import write_txt
from cma_radar.export.netcdf import write_nc, write_merged_nc
from cma_radar.viz.plot import visualize_nc

app = typer.Typer(
    name="cma-radar",
    help="CMA millimeter-wave cloud radar data parser.",
    no_args_is_help=True,
)
console = Console()

FILE_PATTERN = re.compile(
    r"Z_RADA_I_\d{5}_\d{14}_O_YCCR_.*_RAW_MM\.BIN", re.IGNORECASE
)

MOMENT_NAMES = {
    1: "Reflectivity (Z)",
    2: "Velocity (V)",
    3: "Spectrum Width (W)",
    4: "Differential Reflectivity (ZDR)",
    7: "Signal-to-Noise Ratio (SNR)",
    10: "Linear Depolarization Ratio (LDR)",
}


class OutputFormat(str, Enum):
    nc = "nc"
    txt = "txt"


def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(message)s",
        datefmt="[%X]",
        handlers=[RichHandler(console=console, rich_tracebacks=True)],
    )


def _scan_bin_files(folder: str) -> list[str]:
    """Recursively find all matching .BIN files in folder."""
    files = []
    for root, _, filenames in os.walk(folder):
        for fname in filenames:
            if FILE_PATTERN.match(fname):
                files.append(os.path.join(root, fname))
    return sorted(files)


def _print_summary(cma_data: CmaRadarData) -> None:
    """Print a rich summary table of parsed radar data."""
    if not cma_data.radials:
        console.print("[yellow]No radial data found.[/yellow]")
        return

    table = Table(title="CMA Radar File Summary")
    table.add_column("Field", style="cyan")
    table.add_column("Value")

    if cma_data.site_config:
        site = cma_data.site_config
        table.add_row("Site Name", f"{site.SiteName} ({site.SiteCode})")
        table.add_row("Location", f"Lat {site.Latitude:.4f}, Lon {site.Longitude:.4f}")
        table.add_row("Altitude", f"{site.AntennaHeight:.1f} m")

    if cma_data.radar_config:
        radar = cma_data.radar_config
        table.add_row("Frequency", f"{radar.Frequency / 1e9:.2f} GHz")
        table.add_row("Range Resolution", f"{radar.DistanceSolution} m")

    table.add_row("Radials", str(len(cma_data.radials)))

    first_radial = cma_data.radials[0]
    obs_time = datetime.datetime.fromtimestamp(first_radial.header.Seconds, datetime.timezone.utc)
    table.add_row("First Radial Time (UTC)", obs_time.strftime("%Y-%m-%d %H:%M:%S"))

    available_moments = sorted(first_radial.variable.keys())
    if available_moments:
        moment_info = ", ".join(
            f"Key {k} ({MOMENT_NAMES.get(k, '?')})" for k in available_moments
        )
        table.add_row("Moments", moment_info)

    console.print(table)


def _parse_file_worker(filepath: str) -> tuple[str, CmaRadarData | None, str]:
    """Worker function for multiprocessing: parse one .BIN file."""
    try:
        data = read_cma_radar(filepath)
        if data and data.site_config and data.radials:
            return (data.site_config.SiteCode, data, filepath)
        return ("", None, filepath)
    except Exception:
        return ("", None, filepath)


# -- parse command ----------------------------------------------------------


@app.command()
def parse(
    file: Annotated[str, typer.Argument(help="Path to a .BIN radar file.")],
    format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format."),
    ] = OutputFormat.nc,
    output_dir: Annotated[
        Optional[str],
        typer.Option("--output-dir", "-o", help="Output directory."),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable debug logging."),
    ] = False,
) -> None:
    """Parse a single radar file and export to NetCDF or text."""
    _setup_logging(verbose)

    if not os.path.isfile(file):
        console.print(f"[red]Error:[/red] File not found: {file}")
        raise typer.Exit(1)

    with console.status("[bold green]Parsing file..."):
        cma_data = read_cma_radar(file)

    if not cma_data.radials:
        console.print("[red]Error:[/red] No radial data found in file.")
        raise typer.Exit(1)

    _print_summary(cma_data)

    ext = format.value
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)
        out_path = os.path.join(output_dir, f"{os.path.splitext(os.path.basename(file))[0]}.{ext}")
    else:
        out_path = f"{os.path.splitext(file)[0]}.{ext}"

    if format == OutputFormat.nc:
        write_nc(cma_data, out_path, file)
    else:
        write_txt(cma_data, out_path)

    console.print(f"[green]Output written to:[/green] {out_path}")


# -- batch command ----------------------------------------------------------


@app.command()
def batch(
    folder: Annotated[str, typer.Argument(help="Path to folder containing .BIN files.")],
    format: Annotated[
        OutputFormat,
        typer.Option("--format", "-f", help="Output format."),
    ] = OutputFormat.nc,
    output_dir: Annotated[
        Optional[str],
        typer.Option("--output-dir", "-o", help="Output directory."),
    ] = None,
    merged: Annotated[
        bool,
        typer.Option("--merged", help="Merge by site into single NetCDF per site."),
    ] = False,
    workers: Annotated[
        Optional[int],
        typer.Option("--workers", "-w", help="Number of worker processes."),
    ] = None,
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable debug logging."),
    ] = False,
) -> None:
    """Batch parse radar files in a folder."""
    _setup_logging(verbose)

    if merged and format != OutputFormat.nc:
        console.print("[red]Error:[/red] --merged only works with --format nc")
        raise typer.Exit(1)

    if not os.path.isdir(folder):
        console.print(f"[red]Error:[/red] Directory not found: {folder}")
        raise typer.Exit(1)

    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    files = _scan_bin_files(folder)
    if not files:
        console.print("[yellow]No matching .BIN files found.[/yellow]")
        raise typer.Exit(0)

    n_workers = workers or os.cpu_count()
    console.print(f"Found [bold]{len(files)}[/bold] file(s), using {n_workers} worker(s)...")

    # Parse all files in parallel
    results: list[tuple[str, CmaRadarData | None, str]] = []
    with multiprocessing.Pool(processes=n_workers) as pool:
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TaskProgressColumn(),
            console=console,
        ) as progress:
            task = progress.add_task("Parsing...", total=len(files))
            for result in pool.imap_unordered(_parse_file_worker, files):
                progress.update(task, advance=1)
                if result[1] is None:
                    console.print(f"[red]Error parsing {os.path.basename(result[2])}[/red]")
                results.append(result)

    parsed = [(code, data, fp) for code, data, fp in results if data is not None]
    if not parsed:
        console.print("[red]All files failed to parse.[/red]")
        raise typer.Exit(1)

    console.print(f"Successfully parsed [bold]{len(parsed)}[/bold] file(s).")

    if merged:
        grouped: dict[str, list[tuple[CmaRadarData, str]]] = {}
        for code, data, fp in parsed:
            grouped.setdefault(code, []).append((data, fp))

        for site_code, items in grouped.items():
            data_list = [d for d, _ in items]
            fp_list = [f for _, f in items]
            out = os.path.join(output_dir or folder, f"{site_code}_merged.nc")
            write_merged_nc(data_list, out, fp_list)
            console.print(f"[green]Merged NetCDF for {site_code}:[/green] {out}")
    elif format == OutputFormat.nc:
        for code, data, fp in parsed:
            base_name = os.path.splitext(os.path.basename(fp))[0]
            if output_dir:
                out = os.path.join(output_dir, f"{base_name}.nc")
            else:
                out = f"{os.path.splitext(fp)[0]}.nc"
            write_nc(data, out, fp)
            console.print(f"[green]Written:[/green] {out}")
    else:
        for code, data, fp in parsed:
            base_name = os.path.splitext(os.path.basename(fp))[0]
            if output_dir:
                out = os.path.join(output_dir, f"{base_name}.txt")
            else:
                out = f"{os.path.splitext(fp)[0]}.txt"
            write_txt(data, out)

    console.print("[bold green]Batch processing complete.[/bold green]")


# -- visualize command ------------------------------------------------------


@app.command()
def visualize(
    file: Annotated[str, typer.Argument(help="Path to a .nc NetCDF file.")],
    output_dir: Annotated[
        str,
        typer.Option("--output-dir", "-o", help="Output directory for plots."),
    ] = "plots",
    verbose: Annotated[
        bool,
        typer.Option("--verbose", "-v", help="Enable debug logging."),
    ] = False,
) -> None:
    """Create time-height visualization plots from a NetCDF file."""
    _setup_logging(verbose)

    if not os.path.isfile(file):
        console.print(f"[red]Error:[/red] File not found: {file}")
        raise typer.Exit(1)

    try:
        out_path = visualize_nc(file, output_dir=output_dir)
        console.print(f"[green]Plot saved to:[/green] {out_path}")
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        raise typer.Exit(1)


if __name__ == "__main__":
    app()
