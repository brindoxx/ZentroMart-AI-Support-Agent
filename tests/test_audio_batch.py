"""Batch audio contract checks; no provider calls or user recordings."""
from array import array
from importlib.util import find_spec
from io import BytesIO
import json
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace
import unittest
from unittest.mock import Mock, patch
import wave

from zentromart.audio_batch import (Turn, BudgetedSpeech, combine_speech, disclose_ai,
                                   load_turns, main, normalize_wav, run_batch, speech_parts)
from zentromart.contracts import AgentResponse
from zentromart.grounding import GroundingTrace
from zentromart.retrieval import SearchDocument
from zentromart.voice import VoiceError, pcm_from_wav


def wav_bytes(rate=48000, channels=2, seconds=0.1):
    stream = BytesIO()
    with wave.open(stream, 'wb') as audio:
        audio.setnchannels(channels)
        audio.setsampwidth(2)
        audio.setframerate(rate)
        audio.writeframes(array('h', [1000, -1000] * (int(rate * seconds) * channels // 2)).tobytes())
    return stream.getvalue()


class ManifestTests(unittest.TestCase):
    def test_order_and_session_ids_are_explicit(self):
        with TemporaryDirectory() as root:
            folder = Path(root)
            for name in ('a.wav', 'b.wav', 'c.wav'):
                (folder / name).touch()
            manifest = folder / 'cases.json'
            rows = [{'file': name, 'session': session, 'language': language}
                    for name, session, language in [('b.wav', 'one', 'en'), ('a.wav', 'two', 'en'), ('c.wav', 'two', 'hi')]]
            manifest.write_text(json.dumps({'turns': rows}), encoding='utf-8')
            self.assertEqual([t.file for t in load_turns(folder, manifest)], ['b.wav', 'a.wav', 'c.wav'])
            self.assertEqual([t.session for t in load_turns(folder, manifest)], ['one', 'two', 'two'])
            self.assertEqual(len({t.session for t in load_turns(folder)}), 3)

    def test_escaping_duplicate_and_interleaved_manifest_rejected(self):
        with TemporaryDirectory() as root:
            folder = Path(root) / 'input'
            folder.mkdir()
            for name in ('a.wav', 'b.wav', 'c.wav'):
                (folder / name).touch()
            (Path(root) / 'outside.wav').touch()
            manifest = Path(root) / 'cases.json'
            cases = [[('../outside.wav', 'one')], [('a.wav', 'one'), ('a.wav', 'two')],
                     [('a.wav', 'one'), ('b.wav', 'two'), ('c.wav', 'one')]]
            for case in cases:
                manifest.write_text(json.dumps({'turns': [{'file': name, 'session': session, 'language': 'en'}
                                                         for name, session in case]}), encoding='utf-8')
                with self.assertRaises(ValueError):
                    load_turns(folder, manifest)


@unittest.skipUnless(find_spec('numpy') and find_spec('scipy'), 'voice conversion extras required')
class AudioBatchTests(unittest.TestCase):
    def test_conversion_accepts_stereo_48k_and_bounds_bad_audio(self):
        with TemporaryDirectory() as root:
            path = Path(root) / 'input.wav'
            path.write_bytes(wav_bytes())
            normalized = normalize_wav(path)
            self.assertEqual(len(pcm_from_wav(normalized)), 3200)
            path.write_bytes(wav_bytes(seconds=16))
            with self.assertRaises(VoiceError):
                normalize_wav(path)
            path.write_bytes(b'not WAV')
            with self.assertRaises(VoiceError):
                normalize_wav(path)

    def test_speech_chunks_preserve_text_and_validate_wav(self):
        text = 'Useful answer. ' * 100
        parts = speech_parts(text)
        self.assertTrue(all(len(part) <= 700 for part in parts))
        self.assertEqual(' '.join(parts).split(), text.split())
        combined = combine_speech([wav_bytes(24000, 1), wav_bytes(24000, 1)])
        with wave.open(BytesIO(combined), 'rb') as clip:
            self.assertEqual(clip.getnframes(), 4800)
        with self.assertRaises(VoiceError):
            combine_speech([wav_bytes()])

    def make_agent(self, agents, phase='idle'):
        agent = SimpleNamespace(backend=SimpleNamespace(state=SimpleNamespace(phase=phase), clear_tool_trace=Mock()),
                                last_trace=GroundingTrace('accepted', 'dialogue_respond'), messages=[])
        def respond(request):
            agent.messages.append((request.session_id, request.message))
            return AgentResponse('answer', 'Here is the policy. [RET-1]', 'en', ('RET-1',), ('RET-1',))
        agent.respond = respond
        agents.append(agent)
        return agent

    def speech(self, *, fail_at=None, error='timeout'):
        state = SimpleNamespace(count=0)
        async def transcribe(audio, language):
            state.count += 1
            if fail_at == state.count:
                raise VoiceError(error)
            return 'My item is damaged'
        async def synthesize(text, language):
            return wav_bytes(24000, 1)
        return BudgetedSpeech(SimpleNamespace(transcribe=transcribe, synthesize=synthesize))

    def run_case(self, root, turns, factory, speech):
        folder = Path(root) / 'input'
        folder.mkdir()
        for turn in turns:
            (folder / turn.file).write_bytes(wav_bytes())
        docs = [SearchDocument('RET-1', 'Returns', 'Public policy text', 'kb/returns.md', {})]
        return run_batch(folder, turns, Path(root) / 'output', factory, speech, docs, progress=lambda text: None)

    def test_shared_session_outputs_and_independent_isolation(self):
        agents = []
        turns = [Turn('a.wav', 'one'), Turn('b.wav', 'two'), Turn('c.wav', 'two', 'hi')]
        with TemporaryDirectory() as root:
            output, summary = self.run_case(root, turns, lambda: self.make_agent(agents), self.speech())
            self.assertEqual(summary['counts']['completed'], 3)
            self.assertEqual([len(agent.messages) for agent in agents], [1, 2])
            self.assertEqual(summary['speech_attempts'], 6)
            self.assertIn('AI support assistant', (output / '002/reply.txt').read_text())
            self.assertNotIn('AI support assistant', (output / '003/reply.txt').read_text())
            source = json.loads((output / '001/sources.json').read_text())
            self.assertEqual(source['chunks'][0]['text'], 'Public policy text')
            self.assertTrue((output / '003/reply.wav').is_file())
            self.assertEqual(agents[-1].backend.clear_tool_trace.call_count, 2)

    def test_stt_failure_skips_dependent_turn_but_not_independent_case(self):
        with TemporaryDirectory() as root:
            output, summary = self.run_case(root, [Turn('a.wav', 'one'), Turn('b.wav', 'one'), Turn('c.wav', 'two')],
                lambda: self.make_agent([]), self.speech(fail_at=1))
            self.assertEqual([row['status'] for row in summary['turns']], ['failed', 'skipped', 'completed'])
            self.assertFalse((output / '001/reply.wav').exists())

    def test_auth_failure_stops_all_remaining_calls(self):
        with TemporaryDirectory() as root:
            _, summary = self.run_case(root, [Turn('a.wav', 'one'), Turn('b.wav', 'two')],
                lambda: self.make_agent([]), self.speech(fail_at=1, error='authentication'))
            self.assertEqual(summary['speech_attempts'], 1)
            self.assertEqual(summary['turns'][1]['status'], 'skipped')

    def test_pending_verification_never_uploads_next_clip(self):
        with TemporaryDirectory() as root:
            _, summary = self.run_case(root, [Turn('a.wav', 'one')],
                lambda: self.make_agent([], phase='proof'), self.speech())
            self.assertEqual(summary['speech_attempts'], 0)
            self.assertEqual(summary['turns'][0]['status'], 'needs_typed_verification')

    def test_tts_budget_does_not_claim_audio_success(self):
        speech = self.speech()
        speech.limit = 1
        with TemporaryDirectory() as root:
            output, summary = self.run_case(root, [Turn('a.wav', 'one')], lambda: self.make_agent([]), speech)
            self.assertTrue((output / '001/reply.txt').exists())
            self.assertFalse((output / '001/reply.wav').exists())
            self.assertFalse(summary['turns'][0]['speech_confirmed'])
            self.assertEqual(summary['turns'][0]['error'], 'speech_budget')

    def test_no_live_is_preflight_only(self):
        with TemporaryDirectory() as root:
            (Path(root) / 'test.wav').write_bytes(wav_bytes())
            with patch('zentromart.voice.load_voice_key', side_effect=AssertionError('must not load key')), \
                 patch('builtins.print'):
                self.assertEqual(main([root]), 0)
            self.assertEqual(len(list(Path(root).iterdir())), 1)

    def test_first_reply_disclosure_keeps_existing_ai_intro(self):
        self.assertEqual(disclose_ai('I am an AI assistant.', 'en'), 'I am an AI assistant.')
        self.assertIn('एआई', disclose_ai('नमस्ते।', 'hi'))
