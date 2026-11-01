"""ASGI warm-up and same-cache reuse without starting a server or paid requests."""
import asyncio
from importlib.util import find_spec
import unittest
from unittest.mock import MagicMock, patch


@unittest.skipUnless(find_spec('streamlit'), 'UI dependencies required')
class StartupTests(unittest.TestCase):
    def setUp(self):
        from zentromart import ui_resources
        self.resources = ui_resources
        ui_resources.public_data.clear()
        ui_resources.public_index.clear()
        self.addCleanup(ui_resources.public_data.clear)
        self.addCleanup(ui_resources.public_index.clear)

    def test_index_is_warmed_once_and_ui_reuses_same_cached_object(self):
        index = MagicMock()
        with patch('zentromart.runtime.build_public_index', return_value=index) as build:
            one = self.resources.public_index('dataset', 'artifacts', 'hybrid', True, 'public-hash', 'bge-m3', 'none')
            two = self.resources.public_index('dataset', 'artifacts', 'hybrid', True, 'public-hash', 'bge-m3', 'none')
        self.assertIs(one, two)
        self.assertIs(one, index)
        build.assert_called_once()
        index.search.assert_called_once_with('support', 1)

    def test_failed_warmup_is_not_cached_as_ready(self):
        index = MagicMock()
        index.search.side_effect = ValueError('missing cache')
        with patch('zentromart.runtime.build_public_index', return_value=index) as build:
            for _ in range(2):
                with self.assertRaises(ValueError):
                    self.resources.public_index('dataset', 'artifacts', 'hybrid', True, 'hash', 'bge-m3', 'none')
        self.assertEqual(build.call_count, 2)

    def test_startup_loads_only_public_resources_and_imports_sdk_without_clients(self):
        settings, retrieval = MagicMock(), MagicMock()
        with patch.object(self.resources, 'load_settings', return_value=settings), \
             patch.object(self.resources, 'load_retrieval_settings', return_value=retrieval), \
             patch.object(self.resources, 'public_data', return_value=(['public'], 'calendar')) as data, \
             patch.object(self.resources, 'corpus_fingerprint', return_value='public-hash'), \
             patch.object(self.resources, 'public_index') as index, \
             patch.object(self.resources, 'import_module') as imports, \
             patch('zentromart.config.load_llm_settings', side_effect=AssertionError('No credential loading')), \
             patch('zentromart.voice.load_voice_key', side_effect=AssertionError('No speech key loading')):
            self.resources.warm_startup()
        settings.validate_dataset_layout.assert_called_once()
        data.assert_called_once_with(settings.dataset_dir)
        index.assert_called_once()
        self.assertEqual([call.args[0] for call in imports.call_args_list],
                         ['google.genai', 'websockets.asyncio.client'])

    def test_lifespan_waits_for_warmup_and_suppresses_raw_startup_errors(self):
        # Importing the launcher configures routes but does not run its lifespan.
        from streamlit_app import lifespan
        seen = []
        async def exercise():
            async with lifespan(None) as state:
                seen.append(state['resources_ready'])
        with patch.object(self.resources, 'warm_startup', side_effect=lambda: seen.append('warmed')):
            asyncio.run(exercise())
        self.assertEqual(seen, ['warmed', True])
        with patch.object(self.resources, 'warm_startup', side_effect=ValueError('SECRET_PAYLOAD')):
            with self.assertRaises(RuntimeError) as raised:
                asyncio.run(exercise())
        self.assertNotIn('SECRET_PAYLOAD', str(raised.exception))
