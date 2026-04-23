#!/usr/bin/env python3
"""
LeaderBoard entry point.

Usage:
    python inference/main.py /data/input /data/output/result.geojson

The script walks *input_dir*, processes every supported raster/point-cloud
file it finds, and writes a GeoJSON FeatureCollection to *output_path*.

Output format (per Technical Regulations Appendix 1, Appendix 3):
  - type: FeatureCollection
  - Each Feature:
      geometry  : Polygon in EPSG:3857
      properties:
        class_name   : one of the 7 target classes (see CLASS_NAMES)
        confidence   : float 0.0–1.0
        region_name  : region identifier derived from the input path
                       (falls back to "default_source" if not determinable)
"""
import argparse
import json
import os
import sys


# Target classes from Technical Regulations Appendix 4.
CLASS_NAMES = (
    "kurgany_tselye",
    "kurgany_povrezhdennye",
    "gorodishcha",
    "fortifikatsii",
    "arkhitektury",
    "finds_points",
    "object_poly",
)

# Extensions the pipeline can ingest.
SUPPORTED_EXTENSIONS = {".tif", ".tiff", ".las", ".laz", ".geojson"}


def _region_from_path(path: str, input_dir: str) -> str:
    """Derive a region identifier from a file path relative to *input_dir*."""
    rel = os.path.relpath(path, input_dir)
    parts = rel.split(os.sep)
    # Convention: top-level subdirectory is the region folder.
    return parts[0] if len(parts) > 1 else "default_source"


def process_file(file_path: str, input_dir: str) -> list:
    """
    Run inference on a single input file and return a list of GeoJSON features.

    Replace the body of this function with your model's inference logic.
    The stub below returns an empty list (zero predictions for this file),
    which is valid and will score 0 on the metric – but the archive will pass
    all Platform format checks.
    """
    # TODO: load your model weights and run inference here.
    # Example skeleton:
    #   model = load_model("models/weights.pt")
    #   polygons, classes, scores = model.predict(file_path)
    #   features = build_features(polygons, classes, scores, region)
    #   return features

    region = _region_from_path(file_path, input_dir)  # noqa: F841  (used in real impl)
    return []


def collect_input_files(input_dir: str) -> list:
    """Return a sorted list of all supported input files under *input_dir*."""
    found = []
    for dirpath, _, filenames in os.walk(input_dir):
        for name in sorted(filenames):
            _, ext = os.path.splitext(name.lower())
            if ext in SUPPORTED_EXTENSIONS:
                found.append(os.path.join(dirpath, name))
    return found


def run(input_dir: str, output_path: str) -> None:
    if not os.path.isdir(input_dir):
        sys.exit(f"ERROR: input directory not found: {input_dir}")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    files = collect_input_files(input_dir)
    print(f"Found {len(files)} input file(s) in {input_dir}", flush=True)

    all_features = []
    for i, fp in enumerate(files, 1):
        print(f"  [{i}/{len(files)}] Processing: {os.path.relpath(fp, input_dir)}", flush=True)
        features = process_file(fp, input_dir)
        all_features.extend(features)
        print(f"             → {len(features)} object(s) detected", flush=True)

    geojson = {
        "type": "FeatureCollection",
        "features": all_features,
    }

    with open(output_path, "w", encoding="utf-8") as fh:
        json.dump(geojson, fh, ensure_ascii=False, indent=2)

    print(f"\nTotal detections : {len(all_features)}", flush=True)
    print(f"Output written to: {output_path}", flush=True)


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Xpedition DS – KOZ-2 inference entry point",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Example (Platform launch command):\n"
            "  python inference/main.py /data/input /data/output/result.geojson"
        ),
    )
    parser.add_argument("input_dir", help="Path to the directory with the validation dataset")
    parser.add_argument("output_path", help="Path for the output GeoJSON file")
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    run(args.input_dir, args.output_path)
