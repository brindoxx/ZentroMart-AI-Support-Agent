"""Retrieval configuration and runtime wiring without model downloads."""
import os
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch, MagicMock
from zentromart.config import load_retrieval_settings, RetrievalSettings
from zentromart.runtime import build_public_index


class RuntimeTests(unittest.TestCase):
    def test_defaults_and_explicit_configuration(self):
        with TemporaryDirectory() as path, patch.dict(os.environ, {}, clear=True):
            self.assertEqual(load_retrieval_settings(Path(path)), RetrievalSettings('hybrid', False))
            with patch.dict(os.environ, {'RETRIEVER': 'semantic', 'RETRIEVAL_OFFLINE': 'true'}):
                self.assertEqual(load_retrieval_settings(Path(path)), RetrievalSettings('semantic', True))
            for key, value in [('RETRIEVER', 'unknown'), ('RETRIEVAL_OFFLINE', 'yes')]:
                with patch.dict(os.environ, {key: value}), self.assertRaises(ValueError):
                    load_retrieval_settings(Path(path))

    def test_hybrid_runtime_uses_requested_index_and_keeps_search_ephemeral(self):
        index = MagicMock()
        with patch('zentromart.runtime.load_search_documents', return_value=['public']) as load, \
             patch('zentromart.runtime.build_indexes', return_value={'hybrid': index}) as build:
            shared = build_public_index('dataset', 'artifacts', 'hybrid', True)
        build.assert_called_once_with(['public'], Path('artifacts'), ('hybrid',), offline=True)
        shared.search('synthetic query', 4)
        index.search.assert_called_once_with('synthetic query', 4)
        self.assertNotIn('query', vars(shared))

    def test_index_failure_does_not_silently_fall_back_to_bm25(self):
        with patch('zentromart.runtime.load_search_documents', return_value=[]), \
             patch('zentromart.runtime.build_indexes', side_effect=ValueError('missing cache')):
            with self.assertRaises(ValueError):
                build_public_index('dataset', 'artifacts')
