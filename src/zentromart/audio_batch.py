"""Explicit, bounded audio-folder evaluation using the shared support agent."""
import argparse
import asyncio
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from io import BytesIO
import json
from math import gcd
from pathlib import Path
import re
import tempfile
import wave

from .contracts import AgentRequest
from .privacy import minimize
from .voice import VoiceError, pcm_from_wav


@dataclass(frozen=True)
class Turn:
    file: str
    session: str
    language: str = 'en'


def load_turns(folder, manifest=None):
    """Manifest order is authoritative; without it each WAV is independent."""
    folder = Path(folder).resolve(strict=True)
    if not folder.is_dir():
        raise ValueError('Input must be an audio folder')
    if manifest:
        path = Path(manifest)
        if path.stat().st_size > 100000:
            raise ValueError('Manifest is too large')
        value = json.loads(path.read_text(encoding='utf-8'))
        if not isinstance(value, dict) or set(value) != {'turns'} or not isinstance(value['turns'], list):
            raise ValueError('Manifest must contain a turns array')
        rows = value['turns']
    else:
        rows = [{'file': p.name, 'session': p.stem, 'language': 'en'}
                for p in sorted(folder.glob('*.wav'))]
    if not 1 <= len(rows) <= 50:
        raise ValueError('Use from 1 to 50 recordings')
    turns, seen, closed, previous = [], set(), set(), None
    for row in rows:
        if not isinstance(row, dict) or set(row) != {'file', 'session', 'language'}:
            raise ValueError('Each turn needs file, session and language')
        turn = Turn(**row)
        if (not isinstance(turn.file, str) or not isinstance(turn.session, str)
                or not re.fullmatch(r'[A-Za-z0-9_-]{1,80}', turn.session)
                or turn.language not in ('en', 'hi', 'hi-en')):
            raise ValueError('Invalid turn/session/language')
        target = (folder / turn.file).resolve(strict=True)
        if (not target.is_relative_to(folder) or target.suffix.lower() != '.wav'
                or not target.is_file() or target in seen):
            raise ValueError('Use unique WAV files inside the input folder')
        if turn.session != previous:
            if turn.session in closed:
                raise ValueError('Conversation turns must be contiguous')
            if previous is not None:
                closed.add(previous)
        previous = turn.session
        seen.add(target)
        turns.append(turn)
    return turns


def normalize_wav(path):
    """Convert bounded 16-bit PCM mono/stereo WAV to Gnani 16-kHz mono WAV."""
    path = Path(path)
    if not 44 <= path.stat().st_size <= 6_000_000:
        raise VoiceError('invalid_audio')
    try:
        with wave.open(str(path), 'rb') as wav:
            rate, channels, frames = wav.getframerate(), wav.getnchannels(), wav.getnframes()
            if (wav.getcomptype() != 'NONE' or wav.getsampwidth() != 2 or channels not in (1, 2)
                    or not 8000 <= rate <= 96000 or not 1 <= frames <= rate * 15):
                raise ValueError
            raw = wav.readframes(frames)
            if len(raw) != frames * channels * 2:
                raise ValueError
        import numpy as np
        from scipy.signal import resample_poly
        samples = np.frombuffer(raw, dtype='<i2').astype(np.float64).reshape(-1, channels).mean(axis=1)
        if rate != 16000:
            factor = gcd(rate, 16000)
            samples = resample_poly(samples, 16000 // factor, rate // factor)
        pcm = np.clip(np.rint(samples), -32768, 32767).astype('<i2').tobytes()
        output = BytesIO()
        with wave.open(output, 'wb') as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(16000)
            wav.writeframes(pcm)
        audio = output.getvalue()
        pcm_from_wav(audio)
        return audio
    except (wave.Error, EOFError, ValueError):
        raise VoiceError('invalid_audio') from None


def speech_parts(text, limit=700):
    """Bounded chunks; do not silently truncate a long answer."""
    if not isinstance(text, str) or not text.strip() or len(text) > 8000:
        raise VoiceError('invalid_text')
    text = re.sub(r'\[[^\]\n]+\]', '', text).strip()
    parts = []
    while len(text) > limit:
        cut = text.rfind(' ', 0, limit + 1)
        cut = cut if cut > 0 else limit
        parts.append(text[:cut])
        text = text[cut:].lstrip()
    if text:
        parts.append(text)
    return parts


def combine_speech(clips):
    output, pcm = BytesIO(), bytearray()
    for clip in clips:
        with wave.open(BytesIO(clip), 'rb') as wav:
            if (wav.getnchannels(), wav.getsampwidth(), wav.getframerate(), wav.getcomptype()) != (1, 2, 24000, 'NONE'):
                raise VoiceError('invalid_response')
            data = wav.readframes(wav.getnframes())
            if not data or len(data) != wav.getnframes() * 2:
                raise VoiceError('invalid_response')
            pcm.extend(data)
    if not pcm or len(pcm) > 30_000_000:
        raise VoiceError('invalid_response')
    with wave.open(output, 'wb') as wav:
        wav.setnchannels(1)
        wav.setsampwidth(2)
        wav.setframerate(24000)
        wav.writeframes(pcm)
    return output.getvalue()


class BudgetedSpeech:
    def __init__(self, speech, limit=30):
        if type(limit) is not int or not 1 <= limit <= 200:
            raise ValueError('Speech budget must be from 1 to 200')
        self.speech, self.limit, self.calls = speech, limit, 0

    async def _call(self, method, *args):
        if self.calls >= self.limit:
            raise VoiceError('speech_budget')
        self.calls += 1
        return await getattr(self.speech, method)(*args)

    async def transcribe(self, audio, language):
        return await self._call('transcribe', audio, language)

    async def synthesize(self, text, language):
        return await self._call('synthesize', text, language)


def write_json(path, value):
    with Path(path).open('x', encoding='utf-8') as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)


def disclose_ai(reply, language):
    if re.search(r'\bAI\b|एआई|ए\.आई', reply, re.I):
        return reply
    return {'en': "I'm ZentroMart's AI support assistant. ",
            'hi': 'मैं ZentroMart की एआई सहायता असिस्टेंट हूँ। ',
            'hi-en': "Main ZentroMart ka AI support assistant hoon. "}[language] + reply


def run_batch(folder, turns, output_root, agent_factory, speech, documents, *, configuration=None, progress=print):
    """Injected adapters make session isolation, failure paths and budgets testable."""
    output_root = Path(output_root).resolve()
    output_root.mkdir(parents=True, exist_ok=True)
    output = Path(tempfile.mkdtemp(prefix=datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ-'), dir=output_root))
    docs = {doc.evidence_id: doc for doc in documents}
    summary = {'schema_version': 1, 'run_kind': 'audio_batch', 'configuration': configuration or {},
               'outputs_contain_synthetic_content': True, 'turns': []}
    agent, current, stopped, fatal, replied = None, None, False, False, False
    for number, turn in enumerate(turns, 1):
        if turn.session != current:
            current, agent, stopped, replied = turn.session, None, False, False
        directory = output / f'{number:03d}'
        directory.mkdir()
        record = {**asdict(turn), 'status': 'failed', 'stage': 'prepare', 'error': None,
                  'speech_confirmed': False}
        try:
            if fatal or stopped:
                record.update(status='skipped', error='run_stopped' if fatal else 'conversation_stopped')
                continue
            audio = normalize_wav(Path(folder) / turn.file)
            if agent is None:
                agent = agent_factory()
            if agent.backend.state.phase in {'proof', 'locked'}:
                record.update(status='needs_typed_verification', error='audio_proof_not_accepted')
                stopped = True
                continue
            record['stage'] = 'stt'
            transcript = asyncio.run(speech.transcribe(audio, turn.language))
            if not isinstance(transcript, str) or not transcript.strip() or len(transcript) > 4000:
                raise VoiceError('invalid_response')
            # Never persist raw proofs or tool arguments. Inputs must be synthetic.
            record['transcript_minimized'] = minimize(transcript)
            record['stage'] = 'agent'
            response = agent.respond(AgentRequest(turn.session, transcript))
            reply = response.reply if replied else disclose_ai(response.reply, response.language)
            replied = True
            (directory / 'reply.txt').write_text(reply, encoding='utf-8')
            identifiers = tuple(dict.fromkeys(response.retrieved_evidence + response.evidence))
            write_json(directory / 'sources.json', {
                'cited_ids': list(response.evidence), 'agent_evidence_ids': list(response.retrieved_evidence),
                'chunks': [docs[identity].to_dict() for identity in identifiers if identity in docs],
                'unresolved_ids': [identity for identity in identifiers if identity not in docs]})
            trace = getattr(agent, 'last_trace', None)
            record.update(decision=response.decision, language=response.language,
                          trace=asdict(trace) if trace is not None else None,
                          tool_names=[call.name for call in response.tool_calls])
            record['stage'] = 'tts'
            clips = [asyncio.run(speech.synthesize(part, response.language)) for part in speech_parts(reply)]
            (directory / 'reply.wav').write_bytes(combine_speech(clips))
            record.update(status='completed', stage='done', speech_confirmed=True)
        except Exception as error:
            # No exception payload, response body or key is written to artifacts/logs.
            from .llm import ModelError
            code = error.code if isinstance(error, ModelError) else str(error) if isinstance(error, VoiceError) else 'stage_failed'
            if isinstance(error, RuntimeError) and str(error) == 'Evaluation generation budget reached':
                code = 'model_budget'
            allowed = {'timeout', 'authentication', 'quota', 'service_failed', 'speech_budget',
                       'invalid_audio', 'invalid_response', 'invalid_text', 'not_configured',
                       'model_unavailable', 'blocked', 'incomplete', 'request_failed', 'unavailable', 'stage_failed', 'model_budget'}
            record['error'] = code if code in allowed else 'stage_failed'
            stopped = True
            fatal = code in {'authentication', 'quota', 'speech_budget', 'model_budget', 'not_configured', 'model_unavailable'}
        finally:
            if agent is not None:
                agent.backend.clear_tool_trace()
            write_json(directory / 'result.json', record)
            summary['turns'].append(record)
            progress(f"Audio {number}/{len(turns)}: {record['status']} ({record['stage']})")
    summary['speech_attempts'] = speech.calls
    summary['counts'] = {status: sum(row['status'] == status for row in summary['turns'])
                         for status in ('completed', 'failed', 'skipped', 'needs_typed_verification')}
    write_json(output / 'summary.json', summary)
    return output, summary


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('folder', type=Path)
    parser.add_argument('--manifest', type=Path, help='Ordered turns with file/session/language; otherwise independent English WAVs')
    parser.add_argument('--output', type=Path, default=Path('artifacts/audio_runs'))
    parser.add_argument('--live', action='store_true', help='Upload synthetic audio/text and consume Gemini/Gnani quota; outputs are saved')
    parser.add_argument('--offline', action='store_true', help='Only the embedding cache is offline; speech/model calls still use the network')
    parser.add_argument('--max-generations', type=int, default=24)
    parser.add_argument('--max-speech-requests', type=int, default=30)
    parser.add_argument('--interval-seconds', type=float, default=5)
    args = parser.parse_args(argv)
    try:
        turns = load_turns(args.folder, args.manifest)
        # Preflight all recordings before keys, downloads, model loading or paid calls.
        for turn in turns:
            normalize_wav(args.folder / turn.file)
        if not args.live:
            print(json.dumps({'mode': 'preflight_only', 'cloud_calls': 0, 'turns': [asdict(t) for t in turns]}, indent=2))
            return 0
        from dataclasses import replace
        from .config import load_settings, load_llm_settings, load_retrieval_settings
        from .llm import GeminiModel
        from .voice import GnaniSpeech, load_voice_key
        from .evaluation.pacing import PacedModel
        from .runtime import build_public_index
        from .application import create_agent
        settings = load_settings()
        settings.validate_dataset_layout()
        model_settings = replace(load_llm_settings(), retries=0)
        model_settings.require_key()
        speech = BudgetedSpeech(GnaniSpeech(load_voice_key()), args.max_speech_requests)
        model = PacedModel(GeminiModel(model_settings), interval_seconds=args.interval_seconds,
                           max_generations=args.max_generations, input_tpm=250000)
        retrieval = load_retrieval_settings()
        index = build_public_index(settings.dataset_dir, settings.artifacts_dir, retrieval.method,
                                   args.offline or retrieval.offline, retrieval.embedding_model, retrieval.reranker)
        configuration = {'retrieval': index.configuration(), 'provider': model_settings.provider,
                         'model': model_settings.model, 'automatic_retries': 0,
                         'max_generations': args.max_generations, 'max_speech_requests': args.max_speech_requests,
                         'interval_seconds': args.interval_seconds, 'input_tpm': 250000}
        output, summary = run_batch(args.folder, turns, args.output,
            lambda: create_agent(settings, model, index=index), speech, index.documents, configuration=configuration)
        write_json(output / 'model_usage.json', model.configuration())
        print('Saved audio run: ' + str(output))
        print(json.dumps(summary['counts']))
        return 0 if summary['counts']['completed'] == len(turns) else 1
    except Exception:
        print('Audio batch setup failed. Check WAV format, manifest, dependencies, local configuration and model cache. No raw details displayed.')
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
