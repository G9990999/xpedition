#!/usr/bin/env python3
import boto3
import os
import argparse
import urllib3
import time
import threading
import logging
import random
import re
from pathlib import Path
from botocore.config import Config
from concurrent.futures import ThreadPoolExecutor, as_completed
from boto3.s3.transfer import TransferConfig

# Disable SSL warnings
urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

# S3 Configuration
ENDPOINT_URL = 'https://s3.ru-7.storage.selcloud.ru:443'
BUCKET_NAME = 'train-expds-2'
LOCAL_DIR = './'
LOG_FILE = 'download.log'

# Multipart transfer settings for large files.
# use_threads=False is critical: setting it True spawns a nested thread pool
# inside each worker thread, which crashes with "cannot schedule new futures
# after interpreter shutdown" when the outer ThreadPoolExecutor exits.
TRANSFER_CONFIG = TransferConfig(
    multipart_threshold=64 * 1024 * 1024,
    multipart_chunksize=16 * 1024 * 1024,
    max_concurrency=1,   # ignored when use_threads=False, but kept for clarity
    use_threads=False
)

MAX_FILE_RETRIES = 6      # per-file retry attempts before giving up
RETRY_BASE_DELAY = 3.0    # seconds; capped so threads don't all sleep 80s
RETRY_MAX_DELAY  = 30.0   # hard cap per retry wait

logging.basicConfig(
    filename=LOG_FILE,
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize S3 client with SSL verification disabled and optimized settings
s3_client = boto3.client(
    's3',
    endpoint_url=ENDPOINT_URL,
    aws_access_key_id='a064df53e320474396c1de1c82dd858e', 
    aws_secret_access_key='b1f66191dfe34927992afe3cc62a66ce', 
    verify=False,  # Disable SSL verification
    config=Config(
        signature_version='s3v4',
        max_pool_connections=20,
        connect_timeout=30,
        read_timeout=120,        # large files: allow 2 min between chunks
        # 'adaptive' mode backs off automatically on 429/503 responses
        retries={
            'max_attempts': 5,
            'mode': 'adaptive',
        }
    )
)

# Global counters for progress tracking
download_stats = {
    'completed': 0,
    'total': 0,
    'downloaded_bytes': 0,
    'total_bytes': 0,
    'start_time': None,
    'last_render_time': 0.0,
    'render_interval': 0.2,
    'lock': threading.Lock()
}


def format_bytes(bytes_size):
    """Format bytes to human readable format"""
    for unit in ['B', 'KB', 'MB', 'GB']:
        if bytes_size < 1024.0:
            return f"{bytes_size:.2f} {unit}"
        bytes_size /= 1024.0
    return f"{bytes_size:.2f} TB"


def render_progress(force=False):
    """Render current download progress to console"""
    with download_stats['lock']:
        now = time.time()
        if not force and (now - download_stats['last_render_time']) < download_stats['render_interval']:
            return

        download_stats['last_render_time'] = now
        
        elapsed = time.time() - download_stats['start_time']
        speed = download_stats['downloaded_bytes'] / elapsed if elapsed > 0 else 0
        progress = (download_stats['completed'] / download_stats['total']) * 100 if download_stats['total'] > 0 else 0
        
        print(f"\r  Progress: [{download_stats['completed']}/{download_stats['total']}] "
              f"{progress:.1f}% | {format_bytes(download_stats['downloaded_bytes'])}/{format_bytes(download_stats['total_bytes'])} | "
              f"Speed: {format_bytes(speed)}/s", end='', flush=True)


def add_downloaded_bytes(num_bytes):
    """Add transferred bytes from in-progress downloads"""
    with download_stats['lock']:
        download_stats['downloaded_bytes'] += num_bytes
    render_progress()


def complete_file(progress_bytes=0):
    """Mark one file as completed and optionally reconcile remaining bytes"""
    with download_stats['lock']:
        if progress_bytes > 0:
            download_stats['downloaded_bytes'] += progress_bytes
        download_stats['completed'] += 1
    render_progress(force=True)


class ProgressCallback:
    """Track bytes transferred for one file download"""

    def __init__(self):
        self.transferred = 0

    def __call__(self, bytes_amount):
        self.transferred += bytes_amount
        add_downloaded_bytes(bytes_amount)


def _rollback_bytes(n):
    """Subtract bytes that were counted during a failed/partial download attempt."""
    if n <= 0:
        return
    with download_stats['lock']:
        download_stats['downloaded_bytes'] = max(0, download_stats['downloaded_bytes'] - n)


# Pattern for boto3 TransferManager temp files: original name + '.' + 8 hex chars
_PARTIAL_SUFFIX_RE = re.compile(r'\.[0-9A-Fa-f]{8}$')


def _cleanup_partial_file(local_file, expected_size=None):
    """Remove partial/invalid local file and any boto3 hex-suffix temp siblings."""
    parent = os.path.dirname(local_file)
    basename = os.path.basename(local_file)

    # Remove the destination file itself if it is incomplete
    try:
        if os.path.exists(local_file):
            if expected_size is None or os.path.getsize(local_file) != expected_size:
                os.remove(local_file)
                logger.info(f"Removed partial file: {local_file}")
    except Exception as e:
        logger.warning(f"Failed to remove partial file {local_file}: {e}")

    # Remove boto3 temp siblings: <basename>.<8 hex chars>
    try:
        if os.path.isdir(parent):
            siblings = sorted(
                (f for f in os.listdir(parent)
                 if f.startswith(basename + '.') and _PARTIAL_SUFFIX_RE.search(f)),
                key=lambda f: f.rsplit('.', 1)[-1]
            )
            for name in siblings:
                sibling_path = os.path.join(parent, name)
                try:
                    os.remove(sibling_path)
                    logger.info(f"Removed boto3 temp file: {sibling_path}")
                except Exception as e:
                    logger.warning(f"Failed to remove boto3 temp file {sibling_path}: {e}")
    except Exception as e:
        logger.warning(f"Failed to scan for boto3 temp files in {parent}: {e}")


def cleanup_existing_partial_files(local_dir):
    """Scan *local_dir* recursively and remove all boto3 hex-suffix temp files.

    Files are processed sorted by their hex postfix so the log is deterministic.
    Returns the number of files removed.
    """
    removed = 0
    found = []
    for dirpath, _, filenames in os.walk(local_dir):
        for name in filenames:
            if _PARTIAL_SUFFIX_RE.search(name):
                found.append(os.path.join(dirpath, name))

    # Sort by the hex suffix so output is deterministic
    found.sort(key=lambda p: p.rsplit('.', 1)[-1])

    if found:
        print(f"  Found {len(found)} leftover boto3 temp file(s) — cleaning up...")
        for path in found:
            try:
                os.remove(path)
                logger.info(f"Removed existing temp file: {path}")
                print(f"    Removed: {os.path.relpath(path, local_dir)}")
                removed += 1
            except Exception as e:
                logger.warning(f"Failed to remove existing temp file {path}: {e}")
                print(f"    Failed to remove: {path}: {e}")
    return removed


def download_file(bucket, key, local_file, file_size):
    """Download a single file with per-file retry and exponential back-off."""
    # Create directory if needed
    local_file_dir = os.path.dirname(local_file)
    Path(local_file_dir).mkdir(parents=True, exist_ok=True)

    # Skip if file exists and has correct size
    if os.path.exists(local_file):
        if os.path.getsize(local_file) == file_size:
            logger.info(f"Skipped (already exists): {key}")
            complete_file(progress_bytes=file_size)
            return True
        else:
            logger.info(f"Found existing partial file, cleaning up before download: {local_file}")
            _cleanup_partial_file(local_file)

    for attempt in range(1, MAX_FILE_RETRIES + 1):
        progress_callback = ProgressCallback()
        try:
            logger.info(f"Downloading (attempt {attempt}): {key} -> {local_file}")
            s3_client.download_file(
                bucket,
                key,
                local_file,
                Config=TRANSFER_CONFIG,
                Callback=progress_callback
            )

            # Verify file size
            if os.path.getsize(local_file) != file_size:
                logger.warning(f"Size mismatch after download: {key}")
                _rollback_bytes(progress_callback.transferred)
                _cleanup_partial_file(local_file, expected_size=file_size)
                # treat as retriable
                raise ValueError(f"size mismatch (got {os.path.getsize(local_file)}, want {file_size})")

            missing_bytes = max(0, file_size - progress_callback.transferred)
            logger.info(f"Downloaded: {key}")
            complete_file(progress_bytes=missing_bytes)
            return True

        except Exception as e:
            # Roll back bytes that were already counted for this attempt
            _rollback_bytes(progress_callback.transferred)
            _cleanup_partial_file(local_file, expected_size=file_size)

            if attempt == MAX_FILE_RETRIES:
                print(f"\nFailed after {MAX_FILE_RETRIES} attempts: {key}: {e}")
                logger.error(f"Giving up on {key} after {MAX_FILE_RETRIES} attempts: {e}")
                return False

            delay = min(RETRY_BASE_DELAY * (2 ** (attempt - 1)), RETRY_MAX_DELAY) + random.uniform(0, 2)
            print(f"\nRetry {attempt}/{MAX_FILE_RETRIES - 1} for {os.path.basename(key)} in {delay:.1f}s: {e}")
            logger.warning(f"Retrying {key} (attempt {attempt}) in {delay:.1f}s: {e}")
            time.sleep(delay)


def download_folder_parallel(bucket, prefix, local_dir, max_workers=20):
    """Download all files from S3 folder using parallel downloads"""
    # Remove any leftover boto3 hex-suffix temp files before starting
    cleanup_existing_partial_files(local_dir)

    print(f"Scanning files in: {prefix}")
    logger.info(f"Starting scan for prefix: {prefix}")
    
    # Get file list
    paginator = s3_client.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=bucket, Prefix=prefix)
    
    files_to_download = []
    total_size = 0
    
    for page in pages:
        if 'Contents' not in page:
            print(f"No files found in {prefix}")
            return
            
        for obj in page['Contents']:
            key = obj['Key']
            if not key.endswith('/'):
                # Skip files inside excluded subfolders
                parts = key.split('/')
                if any(p in ('Старая', 'Архив') for p in parts):
                    logger.info(f"Skipped (excluded folder): {key}")
                    continue
                local_file = os.path.join(local_dir, key)
                files_to_download.append((key, local_file, obj['Size']))
                total_size += obj['Size']
    
    if not files_to_download:
        print(f"No files to download from {prefix}")
        logger.info(f"No files found for prefix: {prefix}")
        return
    
    # Initialize progress tracking
    download_stats['total'] = len(files_to_download)
    download_stats['completed'] = 0
    download_stats['downloaded_bytes'] = 0
    download_stats['total_bytes'] = total_size
    download_stats['start_time'] = time.time()
    download_stats['last_render_time'] = 0.0
    
    print(f"Downloading {len(files_to_download)} files ({format_bytes(total_size)}) using {max_workers} threads...")
    logger.info(
        f"Starting download: files={len(files_to_download)}, total_size={total_size} bytes, threads={max_workers}"
    )
    
    # Download files in parallel
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        future_to_file = {
            executor.submit(download_file, bucket, key, local_file, file_size): key
            for key, local_file, file_size in files_to_download
        }
        
        failed_files = []
        for future in as_completed(future_to_file):
            key = future_to_file[future]
            try:
                success = future.result()
                if not success:
                    failed_files.append(key)
            except Exception as e:
                print(f"\nUnexpected error with {key}: {e}")
                logger.exception(f"Unexpected future error for {key}")
                failed_files.append(key)
    
    render_progress(force=True)
    print()  # New line after progress
    
    if failed_files:
        print(f"Failed to download {len(failed_files)} files:")
        logger.error(f"Failed to download {len(failed_files)} files")
        for key in failed_files[:10]:  # Show first 10
            print(f"  - {key}")
            logger.error(f"Failed file: {key}")
        if len(failed_files) > 10:
            print(f"  ... and {len(failed_files) - 10} more")
            logger.error(f"... and {len(failed_files) - 10} more failed files")
    else:
        print("✓ All files downloaded successfully!")
        logger.info("All files downloaded successfully")


def verify_downloads(bucket, prefix, local_dir):
    """Verify downloaded files by comparing sizes"""
    print(f"\nVerifying files in: {prefix}")
    
    paginator = s3_client.get_paginator('list_objects_v2')
    pages = paginator.paginate(Bucket=bucket, Prefix=prefix)
    
    total_files = 0
    missing_files = 0
    size_mismatches = 0
    correct_files = 0
    
    for page in pages:
        if 'Contents' not in page:
            continue
            
        for obj in page['Contents']:
            key = obj['Key']
            if key.endswith('/'):
                continue
                
            total_files += 1
            remote_size = obj['Size']
            local_file = os.path.join(local_dir, key)
            
            if not os.path.exists(local_file):
                missing_files += 1
                print(f"Missing: {key}")
            else:
                local_size = os.path.getsize(local_file)
                if local_size != remote_size:
                    size_mismatches += 1
                    print(f"Size mismatch: {key} (local: {format_bytes(local_size)}, remote: {format_bytes(remote_size)})")
                else:
                    correct_files += 1
            
            # Show progress
            print(f"\r  Verified: {total_files} files | ✓ {correct_files} | ✗ {missing_files + size_mismatches}", end='', flush=True)
    
    print()  # New line
    print(f"\nVerification Summary:")
    print(f"  Total files: {total_files}")
    print(f"  Correct: {correct_files}")
    print(f"  Missing: {missing_files}")
    print(f"  Size mismatches: {size_mismatches}")
    
    if missing_files == 0 and size_mismatches == 0:
        print("✓ All files verified successfully!")
    else:
        print("✗ Some files have issues!")
    
    return missing_files + size_mismatches == 0


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description='Fast S3 downloader with verification')
    parser.add_argument('--folder', type=str, default='', 
                       help='Folder/prefix to download (default: all files in bucket)')
    parser.add_argument('--local-dir', type=str, default=LOCAL_DIR, 
                       help=f'Local directory path (default: {LOCAL_DIR})')
    parser.add_argument('--threads', type=int, default=4,
                       help='Number of download threads (default: 4)')
    parser.add_argument('--verify-only', action='store_true', 
                       help='Only verify existing files, don\'t download')
    parser.add_argument('--no-verify', action='store_true', 
                       help='Skip verification after download')
    args = parser.parse_args()

    local_directory = args.local_dir
    Path(local_directory).mkdir(parents=True, exist_ok=True)
    
    print("=" * 80)
    print(f"S3 Fast Downloader - {'ALL FILES' if not args.folder else args.folder.upper()} folder")
    print(f"Local directory: {local_directory}")
    print(f"Threads: {args.threads}")
    print(f"Log file: {LOG_FILE}")
    print("=" * 80)
    logger.info(
        f"Run started: folder='{args.folder}', local_dir='{local_directory}', threads={args.threads}, "
        f"verify_only={args.verify_only}, no_verify={args.no_verify}"
    )
    
    if args.verify_only:
        print("VERIFICATION MODE")
        verify_downloads(BUCKET_NAME, args.folder, local_directory)
    else:
        print("DOWNLOAD MODE")
        download_folder_parallel(BUCKET_NAME, args.folder, local_directory, args.threads)
        
        if not args.no_verify:
            verify_downloads(BUCKET_NAME, args.folder, local_directory)
    
    print("=" * 80)
    print("Complete!")
    print("=" * 80)
    logger.info("Run complete")