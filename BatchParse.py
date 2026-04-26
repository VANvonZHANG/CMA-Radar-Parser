import argparse
import os
import sys
import datetime
import numpy as np
from reader import read_cma_radar, CmaRadarData

def write_data_to_txt(cma_data: CmaRadarData, output_filename: str):
    """Writes the raw, parsed content of the CMA radar data to a text file."""
    with open(output_filename, 'w', encoding='utf-8') as f:
        all_configs = {
            "SiteConfig": cma_data.site_config,
            "RadarConfig": cma_data.radar_config,
            "TaskConfig": cma_data.task_config,
        }
        for name, config in all_configs.items():
            if config:
                f.write(f"[{name}]\n")
                for field in dataclasses.fields(config):
                    f.write(f"{field.name}: {getattr(config, field.name)}\n")
                f.write("\n")

        for i, cut_config in enumerate(cma_data.cut_configs):
            f.write(f"[CutConfig_{i+1}]\n")
            for field in dataclasses.fields(cut_config):
                f.write(f"{field.name}: {getattr(cut_config, field.name)}\n")
            f.write("\n")

        for i, radial in enumerate(cma_data.radials):
            f.write(f"[Radial_{i+1}]\n")
            if radial.header:
                for field in dataclasses.fields(radial.header):
                    f.write(f"header.{field.name}: {getattr(radial.header, field.name)}\n")
            
            for key, moment_data in radial.variable.items():
                f.write(f"\n  [Moment_{key}]\n")
                if moment_data.header:
                    for field in dataclasses.fields(moment_data.header):
                        f.write(f"  header.{field.name}: {getattr(moment_data.header, field.name)}\n")
                
                f.write("  data:\n")
                data_str = np.array2string(moment_data.value, separator=', ', threshold=sys.maxsize)
                f.write(f"    {data_str}\n")
            f.write("\n")

import multiprocessing
import itertools
from tqdm import tqdm

def process_single_file(input_file: str, output_path: str = None):
    """
    Parses a single file and saves the .txt output. This version is silent.
    """
    try:
        cma_data = read_cma_radar(input_file)

        base_filename = os.path.basename(input_file)
        output_basename = os.path.splitext(base_filename)[0] + ".txt"
        
        if output_path:
            output_filename = os.path.join(output_path, output_basename)
        else:
            output_filename = os.path.splitext(input_file)[0] + ".txt"
        
        write_data_to_txt(cma_data, output_filename)

    except Exception as e:
        # In a worker process, it's better to print errors to stderr
        # as stdout might be harder to track.
        print(f"Error processing {os.path.basename(input_file)}: {e}", file=sys.stderr)

import re

def main():
    """Main function to batch process all .BIN files in a directory using multiple processes."""
    parser = argparse.ArgumentParser(
        description="Batch reads all CMA radar binary files in a directory and saves full data to text files."
    )
    parser.add_argument("input_folder", type=str, help="Full path to the folder containing .BIN files.")
    parser.add_argument("--output-path", type=str, default=None, help="Optional. Path to save all output .txt files. Defaults to each input file's directory.")
    parser.add_argument("--workers", type=int, default=None, help="Optional. Number of worker processes to use. Defaults to all available CPU cores.")
    args = parser.parse_args()

    if not os.path.isdir(args.input_folder):
        print(f"Error: Input folder not found at {args.input_folder}", file=sys.stderr)
        sys.exit(1)

    if args.output_path and not os.path.exists(args.output_path):
        os.makedirs(args.output_path)
        print(f"Created output directory: {args.output_path}")

    # 1. Gather all files to be processed using a specific filename pattern
    # Pattern: Z_RADA_I_ddddd_yyyymmddhhmmss_O_YCCR_..._RAW_MM.BIN
    file_pattern = re.compile(
        r'Z_RADA_I_\d{5}_\d{14}_O_YCCR_.*_RAW_MM\.BIN',
        re.IGNORECASE
    )
    
    files_to_process = []
    for root, _, files in os.walk(args.input_folder):
        for file in files:
            if file_pattern.match(file):
                files_to_process.append(os.path.join(root, file))

    if not files_to_process:
        print("No files matching the specified format found in the directory.")
        return

    num_workers = args.workers if args.workers is not None else os.cpu_count()
    print(f"Found {len(files_to_process)} file(s) to process. Starting parallel processing with {num_workers} worker(s)...")

    # 2. Create a process pool and map tasks with a progress bar
    with multiprocessing.Pool(processes=num_workers) as pool:
        tasks = zip(files_to_process, itertools.repeat(args.output_path))
        
        # Use imap_unordered to get results as they complete, allowing for a smooth progress bar
        results = pool.imap_unordered(process_single_file_wrapper, tasks)
        
        # Use tqdm to display progress as we iterate through the results
        list(tqdm(results, total=len(files_to_process), desc="Processing files"))
    
    print(f"\n--- Batch processing complete. Processed {len(files_to_process)} file(s). ---")

def process_single_file_wrapper(args):
    """
    Helper function to unpack arguments for process_single_file,
    needed for imap/imap_unordered which only take one argument.
    """
    return process_single_file(*args)

if __name__ == "__main__":
    # Need to re-import dataclasses for the copied function
    import dataclasses
    main()
