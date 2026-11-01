"""Release allowlist and credential boundaries without a dataset or providers."""
from pathlib import Path
from tempfile import TemporaryDirectory
import hashlib
import json
import unittest
from unittest.mock import patch
import zipfile

from tools.package_submission import FILES, DIRECTORIES, package


class ReleaseTests(unittest.TestCase):
    def fixture(self, root):
        for name in FILES:
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_text('fixture', encoding='utf-8')
        for name in DIRECTORIES:
            (root / name).mkdir(exist_ok=True)
        for name in ('.env', '.streamlit/secrets.toml', 'docs/private.md',
                     'artifacts/models/weights.bin', 'dataset/data/customer.csv',
                     'src/zentromart/__pycache__/private.pyc'):
            path = root / name
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(b'must not package')
        (root / 'src/zentromart/test.py').write_text('public code', encoding='utf-8')
        (root / 'sample_outputs/example.txt').write_text('public sample', encoding='utf-8')
        (root / 'audio_samples/example.wav').write_bytes(b'consented input')

    def test_incomplete_release_refused_without_creating_zip(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            with self.assertRaises(ValueError):
                package(root, root / 'release.zip')
            self.assertFalse((root / 'release.zip').exists())

    def test_preview_is_labelled_and_secrets_caches_notes_excluded(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            package(root, root / 'preview.zip', allow_incomplete=True)
            with zipfile.ZipFile(root / 'preview.zip') as archive:
                status = json.loads(archive.read('SUBMISSION_STATUS.json'))
                self.assertFalse(status['structurally_complete'])
                self.assertEqual(status['missing_deliverables'], ['report.pdf', 'demo.mp4'])
                self.assertIn('audio_samples/example.wav', archive.namelist())
                self.assertNotIn('.env', archive.namelist())
                self.assertNotIn('docs/private.md', archive.namelist())
                self.assertFalse(any('artifacts/' in name or 'dataset/' in name or '__pycache__/' in name
                                     for name in archive.namelist()))

    def test_report_at_root_integrity_and_no_overwrite(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            (root / 'report.pdf').write_bytes(b'%PDF fixture')
            (root / 'demo.mp4').write_bytes(b'video fixture')
            package(root, root / 'release.zip')
            with zipfile.ZipFile(root / 'release.zip') as archive:
                self.assertIn('report.pdf', archive.namelist())
                self.assertIn('demo.mp4', archive.namelist())
                self.assertTrue(json.loads(archive.read('SUBMISSION_STATUS.json'))['structurally_complete'])
                for entry in json.loads(archive.read('FILE_MANIFEST.json')):
                    self.assertEqual(hashlib.sha256(archive.read(entry['path'])).hexdigest(), entry['sha256'])
            with self.assertRaises(FileExistsError):
                package(root, root / 'release.zip')

    def test_key_scan_blocks_before_archive_creation(self):
        with TemporaryDirectory() as directory:
            root = Path(directory)
            self.fixture(root)
            (root / 'README.md').write_text('AIza' + 'A' * 35, encoding='utf-8')
            with self.assertRaises(ValueError):
                package(root, root / 'blocked.zip', allow_incomplete=True)
            self.assertFalse((root / 'blocked.zip').exists())
