"""Text export functions for CMA radar data."""

import dataclasses
import sys

import numpy as np

from cma_radar.reader import CmaRadarData


def write_txt(cma_data: CmaRadarData, output_filename: str) -> None:
    """Writes the raw, parsed content of the CMA radar data to a text file."""
    with open(output_filename, "w", encoding="utf-8") as f:
        all_configs = {
            "SiteConfig": cma_data.site_config,
            "RadarConfig": cma_data.radar_config,
            "TaskConfig": cma_data.task_config,
        }
        for name, config in all_configs.items():
            if config:
                f.write(f"[{name}]\n")
                for fld in dataclasses.fields(config):
                    f.write(f"{fld.name}: {getattr(config, fld.name)}\n")
                f.write("\n")

        for i, cut_config in enumerate(cma_data.cut_configs):
            f.write(f"[CutConfig_{i + 1}]\n")
            for fld in dataclasses.fields(cut_config):
                f.write(f"{fld.name}: {getattr(cut_config, fld.name)}\n")
            f.write("\n")

        for i, radial in enumerate(cma_data.radials):
            f.write(f"[Radial_{i + 1}]\n")
            if radial.header:
                for fld in dataclasses.fields(radial.header):
                    f.write(f"header.{fld.name}: {getattr(radial.header, fld.name)}\n")

            for key, moment_data in radial.variable.items():
                f.write(f"\n  [Moment_{key}]\n")
                if moment_data.header:
                    for fld in dataclasses.fields(moment_data.header):
                        f.write(f"  header.{fld.name}: {getattr(moment_data.header, fld.name)}\n")

                f.write("  data:\n")
                data_str = np.array2string(moment_data.value, separator=", ", threshold=sys.maxsize)
                f.write(f"    {data_str}\n")
            f.write("\n")
