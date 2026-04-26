import netCDF4
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
import numpy as np
import datetime
import os
import sys
from scipy.ndimage import median_filter

def visualize_nc(file_path, output_dir="plots", max_height=6000, snr_threshold=-12):
    if not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    ds = netCDF4.Dataset(file_path)
    site_name = ds.getncattr("site_name")
    
    times = ds.variables['time'][:]
    ranges = ds.variables['range'][:]
    
    range_idx = np.where((ranges > 0) & (ranges <= max_height))[0]
    if len(range_idx) == 0:
        print(f"No valid data in {file_path}")
        return
    
    ranges_clipped = ranges[range_idx]
    dt_times = [datetime.datetime.fromtimestamp(t, datetime.timezone.utc) for t in times]
    
    # 检查 SNR (moment_7) 是否存在
    has_snr = "moment_7" in ds.variables
    snr_mask = None
    if has_snr:
        snr_data = ds.variables["moment_7"][:, range_idx]
        # 创建 SNR 掩码：SNR <= threshold 的点标记为 True (被掩盖)
        snr_mask = (snr_data <= snr_threshold) | (snr_data == -999.0)
        print(f"Using SNR filtering (threshold: {snr_threshold} dB)")
    else:
        print("Notice: moment_7 (SNR) not found. Skipping SNR filtering.")

    target_moments = {
        "moment_1": {"name": "Reflectivity", "unit": "dBZ", "cmap": "jet", "vmin": -30, "vmax": 30},
        "moment_2": {"name": "Velocity", "unit": "m/s", "cmap": "RdBu_r", "vmin": -6, "vmax": 6}
    }
    
    available_targets = [m for m in target_moments if m in ds.variables]
    fig, axes = plt.subplots(len(available_targets), 1, figsize=(15, 6 * len(available_targets)), sharex=True)
    if len(available_targets) == 1: axes = [axes]
        
    for i, var_name in enumerate(available_targets):
        config = target_moments[var_name]
        raw_data = ds.variables[var_name][:, range_idx]
        
        # --- 1. 基础掩码与 SNR 过滤 ---
        data = np.where(raw_data == -999.0, np.nan, raw_data)
        if snr_mask is not None:
            data[snr_mask] = np.nan
        
        # --- 2. 空间去噪 (增大到 5x5 中值滤波) ---
        # 5x5 窗口对抑制大片细碎噪声非常有效
        denoised_data = median_filter(data, size=(5, 5), mode='constant', cval=np.nan)
        
        # --- 3. 物理阈值微调 ---
        if var_name == "moment_1":
            denoised_data[denoised_data < -40] = np.nan
        
        ax = axes[i]
        X, Y = np.meshgrid(dt_times, ranges_clipped)
        
        im = ax.pcolormesh(X, Y, denoised_data.T, 
                          cmap=config["cmap"], 
                          vmin=config["vmin"], 
                          vmax=config["vmax"], 
                          shading='auto')
        
        ax.set_yscale('log')
        ax.set_ylim(ranges_clipped.min(), max_height)
        
        yticks = [100, 200, 500, 1000, 2000, 4000, 6000]
        ax.set_yticks([y for y in yticks if y <= max_height])
        ax.get_yaxis().set_major_formatter(plt.ScalarFormatter())
        
        ax.set_ylabel("Height (m, log scale)")
        filter_info = "SNR + 5x5 Median" if snr_mask is not None else "5x5 Median Filter"
        ax.set_title(f"{site_name} - {config['name']} ({filter_info})")
        cb = fig.colorbar(im, ax=ax, extend='both')
        cb.set_label(config['unit'])
        
        ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
        
    axes[-1].set_xlabel("Time (UTC) on 2025-10-10")
    plt.tight_layout()
    
    base_name = os.path.basename(file_path).replace(".nc", "_advanced_denoised.png")
    output_path = os.path.join(output_dir, base_name)
    plt.savefig(output_path, dpi=200, bbox_inches='tight')
    print(f"Saved advanced denoised visualization to {output_path}")
    ds.close()

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python visualize_radar_nc.py <nc_file>")
        sys.exit(1)
    visualize_nc(sys.argv[1])
