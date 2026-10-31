"""Check the shared dataset date and path configuration boundaries."""

from datetime import date
from pathlib import Path
from tempfile import TemporaryDirectory
import os
import unittest
from unittest.mock import patch

from zentromart.config import load_settings


class ConfigurationTests(unittest.TestCase):
    def test_default_paths_are_relative_to_project_root(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            root = Path(directory).resolve()
            settings = load_settings(root)
            self.assertEqual(settings.dataset_dir, root / "dataset")
            self.assertEqual(settings.artifacts_dir, root / "artifacts")
            self.assertEqual(settings.reference_date, date(2026, 10, 20))

    def test_environment_can_select_another_dataset_location(self):
        with TemporaryDirectory() as directory, patch.dict(
            os.environ, {"DATASET_DIR": "custom-dataset"}, clear=True
        ):
            root = Path(directory).resolve()
            self.assertEqual(load_settings(root).dataset_dir, root / "custom-dataset")

    def test_different_reference_date_is_rejected(self):
        with patch.dict(os.environ, {"DATASET_REFERENCE_DATE": "2026-11-01"}):
            with self.assertRaisesRegex(ValueError, "2026-10-20"):
                load_settings()

    def test_incomplete_dataset_layout_is_rejected(self):
        with TemporaryDirectory() as directory, patch.dict(os.environ, {}, clear=True):
            with self.assertRaisesRegex(ValueError, "Missing dataset folders"):
                load_settings(Path(directory)).validate_dataset_layout()


if __name__ == "__main__":
    unittest.main()
