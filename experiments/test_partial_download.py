#!/usr/bin/env python3
"""Tests for the select_partial_files() sampling logic."""

import sys
import os
import random
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Import constants and the function under test
from participant_download_s3_data import select_partial_files, TOP_MB, MIDDLE_MB, TAIL_MB, MB


def _make_files(count, size_each):
    return [(f"folder/{i:05d}.tif", f"./{i:05d}.tif", size_each) for i in range(count)]


class TestSelectPartialFiles(unittest.TestCase):

    def test_selects_fraction_of_large_dataset(self):
        """With small uniform files across a large dataset, selected size ≈ top+middle+tail."""
        random.seed(0)
        # ~140 GB dataset with 5 MB files
        count = 28_000
        size_each = 5 * MB
        all_files = _make_files(count, size_each)

        selected = select_partial_files(all_files)
        total_all = sum(s for _, _, s in all_files)
        total_sel = sum(s for _, _, s in selected)

        # Should be well under 10 % of the dataset
        self.assertLess(total_sel, total_all * 0.01)
        # Should include at least the three windows' worth of data
        expected_min = (TOP_MB + MIDDLE_MB + TAIL_MB) * MB
        self.assertGreaterEqual(total_sel, expected_min * 0.5)

    def test_no_duplicates(self):
        """Each file key appears at most once."""
        all_files = _make_files(1000, 1 * MB)
        selected = select_partial_files(all_files)
        keys = [k for k, _, _ in selected]
        self.assertEqual(len(keys), len(set(keys)))

    def test_small_dataset_returns_all(self):
        """Dataset smaller than total window size → all files selected."""
        # 10 MB total, windows are 65+20+65 = 150 MB
        all_files = _make_files(10, 1 * MB)
        selected = select_partial_files(all_files)
        self.assertEqual(len(selected), len(all_files))

    def test_top_files_present(self):
        """Files from the beginning of the dataset must be in the selection."""
        all_files = _make_files(10_000, 1 * MB)
        selected = select_partial_files(all_files)
        selected_keys = {k for k, _, _ in selected}
        # First file must always be selected (it is within top 65 MB)
        self.assertIn("folder/00000.tif", selected_keys)

    def test_tail_files_present(self):
        """Files from the end of the dataset must be in the selection."""
        count = 10_000
        all_files = _make_files(count, 1 * MB)
        selected = select_partial_files(all_files)
        selected_keys = {k for k, _, _ in selected}
        # Last file must be selected (tail window)
        self.assertIn(f"folder/{count-1:05d}.tif", selected_keys)

    def test_empty_input(self):
        """Empty input → empty output without error."""
        selected = select_partial_files([])
        self.assertEqual(selected, [])


if __name__ == "__main__":
    unittest.main(verbosity=2)
