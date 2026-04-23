#!/usr/bin/env python3
"""
Preprocess raw sensor data (GeoTIFF / LAS / GeoJSON) for model training.

Usage:
    python scripts/preprocess.py --input dataset/source_data --output processed_data/
    python scripts/preprocess.py --input dataset/ --output processed_data/ --patch-size 512
"""
import argparse
import os
import sys
from pathlib import Path


SUPPORTED_EXTENSIONS = {".tif", ".tiff", ".las", ".laz", ".geojson"}


def collect_files(input_dir: str) -> list:
    """Return sorted list of supported files under input_dir."""
    found = []
    for dirpath, _, filenames in os.walk(input_dir):
        for name in sorted(filenames):
            ext = os.path.splitext(name.lower())[1]
            if ext in SUPPORTED_EXTENSIONS:
                found.append(os.path.join(dirpath, name))
    return found


def preprocess_raster(input_path: str, output_dir: str, patch_size: int) -> int:
    """
    Tile a GeoTIFF into fixed-size patches and save to output_dir.

    Replace this stub with your actual preprocessing logic.
    Returns the number of patches created.
    """
    # TODO: implement actual tiling, normalisation, and band selection
    name = Path(input_path).stem
    out_path = Path(output_dir) / f"{name}_patch_0.tif"
    print(f"    [raster] {os.path.basename(input_path)} → {out_path.name} (stub)")
    return 0


def preprocess_pointcloud(input_path: str, output_dir: str) -> int:
    """
    Convert a LAS/LAZ point cloud to a rasterised height map.

    Replace this stub with your actual preprocessing logic.
    Returns the number of output files created.
    """
    # TODO: implement ground normalisation, density filtering, CHM export
    name = Path(input_path).stem
    out_path = Path(output_dir) / f"{name}_chm.tif"
    print(f"    [lidar] {os.path.basename(input_path)} → {out_path.name} (stub)")
    return 0


def preprocess_geojson(input_path: str, output_dir: str) -> int:
    """
    Validate and reproject annotation GeoJSON to EPSG:3857.

    Replace this stub with your actual preprocessing logic.
    """
    # TODO: reproject, validate geometry, filter by class
    name = Path(input_path).stem
    out_path = Path(output_dir) / f"{name}_3857.geojson"
    print(f"    [vector] {os.path.basename(input_path)} → {out_path.name} (stub)")
    return 0


def run(input_dir: str, output_dir: str, patch_size: int) -> None:
    if not os.path.isdir(input_dir):
        sys.exit(f"ERROR: input directory not found: {input_dir}")

    Path(output_dir).mkdir(parents=True, exist_ok=True)

    files = collect_files(input_dir)
    print(f"Found {len(files)} file(s) in {input_dir}")

    total_outputs = 0
    for i, fp in enumerate(files, 1):
        ext = os.path.splitext(fp.lower())[1]
        print(f"  [{i}/{len(files)}] {os.path.relpath(fp, input_dir)}")
        if ext in {".tif", ".tiff"}:
            total_outputs += preprocess_raster(fp, output_dir, patch_size)
        elif ext in {".las", ".laz"}:
            total_outputs += preprocess_pointcloud(fp, output_dir)
        elif ext == ".geojson":
            total_outputs += preprocess_geojson(fp, output_dir)

    print(f"\nPreprocessing complete. Output files: {total_outputs}")
    print(f"Output directory: {output_dir}")


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Preprocess KOZ-2 sensor data for model training",
    )
    parser.add_argument("--input", required=True, metavar="DIR",
                        help="Directory containing raw sensor data")
    parser.add_argument("--output", required=True, metavar="DIR",
                        help="Directory for processed output files")
    parser.add_argument("--patch-size", type=int, default=512, metavar="N",
                        help="Raster patch size in pixels (default: 512)")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run(args.input, args.output, args.patch_size)
