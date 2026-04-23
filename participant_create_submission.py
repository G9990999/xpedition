#!/usr/bin/env python3
"""
Build a Platform-compliant submission archive for KOZ #2 (Xpedition DS).

The script validates the mandatory structure, checks the archive size limit,
and writes <output>.zip ready to upload to the Platform leaderboard.

Required archive layout (Technical Regulations, Appendix 2 & 3):

    metadata.json          — Docker image + entry_point
    inference/
        main.py            — sole entry point (receives input_dir output_path)
    models/                — model weights / artefacts  (optional)
    configs/               — configuration files        (optional)
    requirements.txt       — pip dependencies           (optional but recommended)

Usage:
    python participant_create_submission.py
    python participant_create_submission.py --solution-dir /path/to/solution
    python participant_create_submission.py --output my_submission.zip --no-validate

Platform constraints (§7.9, Appendix 3):
    • Archive size ≤ 2 GB
    • Must NOT contain training / validation / test data
"""
import argparse
import json
import os
import sys
import zipfile
from pathlib import Path

# Maximum allowed archive size (bytes) — Technical Regulations §7.9
MAX_ARCHIVE_BYTES = 2 * 1024 ** 3  # 2 GiB

# Folders that must never be included in the submission archive
EXCLUDED_DATA_DIRS = {
    "train", "training", "val", "validation", "test", "data",
    "обучающая", "валидационная", "тестовая",
}

# Extensions that indicate raw sensor data (never pack these)
DATA_EXTENSIONS = {".las", ".laz", ".tif", ".tiff"}


def _load_metadata(solution_dir: Path) -> dict:
    meta_path = solution_dir / "metadata.json"
    if not meta_path.exists():
        sys.exit("ERROR: metadata.json not found in solution directory.")
    with open(meta_path, encoding="utf-8") as fh:
        try:
            meta = json.load(fh)
        except json.JSONDecodeError as exc:
            sys.exit(f"ERROR: metadata.json is not valid JSON: {exc}")
    return meta


def _validate_metadata(meta: dict) -> None:
    for key in ("image", "entry_point"):
        if key not in meta:
            sys.exit(f"ERROR: metadata.json is missing required key '{key}'.")
        if not isinstance(meta[key], str) or not meta[key].strip():
            sys.exit(f"ERROR: metadata.json['{key}'] must be a non-empty string.")
    print(f"  metadata.json  OK  (image={meta['image']!r}, entry_point={meta['entry_point']!r})")


def _validate_entrypoint(solution_dir: Path) -> None:
    entry = solution_dir / "inference" / "main.py"
    if not entry.exists():
        sys.exit("ERROR: inference/main.py not found.")
    print("  inference/main.py  OK")


def _check_forbidden_data(solution_dir: Path) -> None:
    """Warn if the solution directory contains raw sensor data files."""
    warnings = []
    for dirpath, dirnames, filenames in os.walk(solution_dir):
        # Skip the inference/ subtree — model code lives there
        dirnames[:] = [
            d for d in dirnames
            if d.lower() not in EXCLUDED_DATA_DIRS
        ]
        for name in filenames:
            _, ext = os.path.splitext(name.lower())
            if ext in DATA_EXTENSIONS:
                warnings.append(os.path.join(dirpath, name))

    if warnings:
        print(
            "\nWARNING: The following raw-data files were found and will be EXCLUDED "
            "from the archive (Technical Regulations §7.7):"
        )
        for w in warnings[:20]:
            print(f"    {w}")
        if len(warnings) > 20:
            print(f"    … and {len(warnings) - 20} more")
        print()


def _should_include(rel_path: str) -> bool:
    """Return False for paths that must not enter the archive."""
    parts = Path(rel_path).parts
    # Exclude top-level data folders
    if parts and parts[0].lower() in EXCLUDED_DATA_DIRS:
        return False
    # Exclude raw sensor-data files anywhere in the tree
    _, ext = os.path.splitext(rel_path.lower())
    if ext in DATA_EXTENSIONS:
        return False
    # Exclude hidden files / __pycache__ / .git
    for part in parts:
        if part.startswith(".") or part == "__pycache__":
            return False
    return True


def build_archive(solution_dir: Path, output_zip: Path, validate: bool) -> None:
    print(f"\nBuilding submission archive from: {solution_dir}")
    print(f"Output: {output_zip}\n")

    meta = _load_metadata(solution_dir)

    if validate:
        print("Validating solution structure …")
        _validate_metadata(meta)
        _validate_entrypoint(solution_dir)
        _check_forbidden_data(solution_dir)
        print()

    collected = []
    for dirpath, dirnames, filenames in os.walk(solution_dir):
        # Prune hidden and cache dirs in-place
        dirnames[:] = [
            d for d in sorted(dirnames)
            if not d.startswith(".") and d != "__pycache__"
        ]
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            rel = os.path.relpath(full, solution_dir)
            if _should_include(rel):
                collected.append((full, rel))

    print(f"Files to include: {len(collected)}")

    with zipfile.ZipFile(output_zip, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for full, rel in collected:
            zf.write(full, rel)
            print(f"  + {rel}")

    archive_size = output_zip.stat().st_size
    print(f"\nArchive size: {archive_size / 1024 / 1024:.2f} MB  "
          f"(limit: {MAX_ARCHIVE_BYTES / 1024 / 1024 / 1024:.0f} GB)")

    if archive_size > MAX_ARCHIVE_BYTES:
        sys.exit(
            "ERROR: Archive exceeds the 2 GB Platform limit. "
            "Remove large files and rebuild."
        )

    print("\nSubmission archive built successfully.")
    print(f"Upload {output_zip.name} to the Platform leaderboard to evaluate your solution.")


def _parse_args():
    parser = argparse.ArgumentParser(
        description="Package a KOZ-2 solution for Platform upload",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "Examples:\n"
            "  python participant_create_submission.py\n"
            "  python participant_create_submission.py --output v2.zip\n"
            "  python participant_create_submission.py --solution-dir ~/my_model\n"
        ),
    )
    parser.add_argument(
        "--solution-dir",
        default=".",
        metavar="DIR",
        help="Root directory of the solution (default: current directory)",
    )
    parser.add_argument(
        "--output",
        default="submission.zip",
        metavar="FILE",
        help="Path for the output archive (default: submission.zip)",
    )
    parser.add_argument(
        "--no-validate",
        action="store_true",
        help="Skip structure validation (not recommended)",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()
    solution_dir = Path(args.solution_dir).resolve()
    output_zip = Path(args.output).resolve()

    if not solution_dir.is_dir():
        sys.exit(f"ERROR: Solution directory not found: {solution_dir}")

    build_archive(solution_dir, output_zip, validate=not args.no_validate)
