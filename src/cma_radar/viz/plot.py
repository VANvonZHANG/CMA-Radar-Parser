"""Visualization functions for CMA radar NetCDF data."""

import datetime
import logging
import os

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import matplotlib.ticker as mticker
import netCDF4
import numpy as np
from scipy.ndimage import median_filter

logger = logging.getLogger(__name__)


def visualize_nc(
    file_path: str,
    output_dir: str = "plots",
    max_height: int = 6000,
    snr_threshold: float = -12,
) -> str:
    """Creates time-height plots from a NetCDF radar file.

    Returns the output file path.
    """
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)

    with netCDF4.Dataset(file_path) as ds:
        site_name = ds.getncattr("site_name")

        times = ds.variables["time"][:]
        ranges = ds.variables["range"][:]

        range_idx = np.where((ranges > 0) & (ranges <= max_height))[0]
        if len(range_idx) == 0:
            raise ValueError(f"No valid range data in {file_path}")

        ranges_clipped = ranges[range_idx]
        dt_times = np.array([
            datetime.datetime.fromtimestamp(t, datetime.timezone.utc) for t in times
        ])

        has_snr = "moment_7" in ds.variables
        snr_mask = None
        if has_snr:
            snr_data = ds.variables["moment_7"][:, range_idx]
            snr_mask = (snr_data <= snr_threshold) | (snr_data == -999.0)
            logger.info("Using SNR filtering (threshold: %s dB)", snr_threshold)
        else:
            logger.info("moment_7 (SNR) not found. Skipping SNR filtering.")

        target_moments = {
            "moment_1": {"name": "Reflectivity", "unit": "dBZ", "cmap": "jet", "vmin": -30, "vmax": 30},
            "moment_2": {"name": "Velocity", "unit": "m/s", "cmap": "RdBu_r", "vmin": -6, "vmax": 6},
        }

        available_targets = [m for m in target_moments if m in ds.variables]
        fig, axes = plt.subplots(
            len(available_targets), 1, figsize=(15, 6 * len(available_targets)), sharex=True
        )
        if len(available_targets) == 1:
            axes = [axes]

        for i, var_name in enumerate(available_targets):
            config = target_moments[var_name]
            raw_data = ds.variables[var_name][:, range_idx]

            data = np.where(raw_data == -999.0, np.nan, raw_data)
            if snr_mask is not None:
                data[snr_mask] = np.nan

            denoised_data = median_filter(data, size=(5, 5), mode="constant", cval=np.nan)

            if var_name == "moment_1":
                denoised_data[denoised_data < -40] = np.nan

            ax = axes[i]
            X, Y = np.meshgrid(dt_times, ranges_clipped)

            im = ax.pcolormesh(
                X, Y, denoised_data.T,
                cmap=config["cmap"],
                vmin=config["vmin"],
                vmax=config["vmax"],
                shading="auto",
            )

            ax.set_yscale("log")
            ax.set_ylim(ranges_clipped.min(), max_height)

            yticks = [100, 200, 500, 1000, 2000, 4000, 6000]
            ax.set_yticks([y for y in yticks if y <= max_height])
            ax.yaxis.set_major_formatter(mticker.ScalarFormatter())

            ax.set_ylabel("Height (m, log scale)")
            filter_info = "SNR + 5x5 Median" if snr_mask is not None else "5x5 Median Filter"
            ax.set_title(f"{site_name} - {config['name']} ({filter_info})")
            cb = fig.colorbar(im, ax=ax, extend="both")
            cb.set_label(config["unit"])

            ax.xaxis.set_major_formatter(mdates.DateFormatter("%H:%M"))

        axes[-1].set_xlabel("Time (UTC)")

        plt.tight_layout()

        base_name = os.path.basename(file_path).replace(".nc", "_advanced_denoised.png")
        output_path = os.path.join(output_dir, base_name)
        plt.savefig(output_path, dpi=200, bbox_inches="tight")
        plt.close(fig)

    logger.info("Saved visualization to %s", output_path)
    return output_path
