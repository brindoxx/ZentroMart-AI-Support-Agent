"""Live relay security, bounded PCM streaming and provider-error sanitization."""
import asyncio
import json
from types import SimpleNamespace
import unittest
from unittest.mock import AsyncMock, MagicMock, patch

from zentromart.live_voice import LeaseRegistry, relay_turn, same_local_origin, voice_socket, REGISTRY
from zentromart.voice import VoiceError


class LiveVoiceTests(unittest.TestCase):
    def test_strict_origin_and_single_use_leases(self):
        self.assertTrue(same_local_origin("http://127.0.0.1:8502", "127.0.0.1:8502"))
        for origin in ("https://evil.example", "http://localhost:9999", "null", "http://127.0.0.1:8503"):
            self.assertFalse(same_local_origin(origin, "127.0.0.1:8502"))
        registry = LeaseRegistry()
        token = registry.issue(object(), "en", "voice", "one")
        self.assertEqual(registry.claim(token).event_id, "one")
        with self.assertRaises(VoiceError): registry.claim(token)
        registry.revoke(token)
        with self.assertRaises(VoiceError): registry.claim(token)
        with self.assertRaises(VoiceError): registry.claim(["not-a-token"])
        registry.revoke(["not-a-token"])

    def test_expired_and_other_session_tokens_cannot_connect(self):
        first, second = LeaseRegistry(), LeaseRegistry()
        token = first.issue(object(), "en", "dictate", "one")
        with self.assertRaises(VoiceError): second.claim(token)
        first._leases[token].expires = 0
        with self.assertRaises(VoiceError): first.claim(token)

    def test_origin_rejected_before_authentication_or_provider_access(self):
        browser = SimpleNamespace(headers={"origin": "https://evil.example", "host": "127.0.0.1:8502"},
                                  close=AsyncMock(), accept=AsyncMock())
        asyncio.run(voice_socket(browser))
        browser.accept.assert_not_called()
        browser.close.assert_awaited_once_with(code=1008)

    def test_live_frames_are_forwarded_before_the_completed_transcript(self):
        async def run():
            forwarded = asyncio.Event()
            outgoing = []
            class Provider:
                first = True
                async def send(self, value):
                    outgoing.append(value)
                    forwarded.set()
                async def recv(self):
                    if self.first:
                        self.first = False
                        return json.dumps({"type": "connected"})
                    await forwarded.wait()
                    return json.dumps({"type": "transcript", "text": "hello there", "segment_id": "one"})
            messages = [{"type": "websocket.receive", "bytes": bytes(1024)}]
            async def receive():
                if messages: return messages.pop()
                await asyncio.sleep(10)
            browser = SimpleNamespace(receive=receive, send_json=AsyncMock())
            speech = SimpleNamespace(enabled=True, reserve=MagicMock(return_value="SECRET"))
            registry = LeaseRegistry()
            lease = registry.claim(registry.issue(speech, "hi-en", "voice", "event-one"))
            context = MagicMock()
            context.__aenter__ = AsyncMock(return_value=Provider())
            context.__aexit__ = AsyncMock(return_value=False)
            with patch("websockets.asyncio.client.connect", return_value=context) as connect:
                await relay_turn(browser, lease)
            self.assertEqual(outgoing, [bytes(1024)])
            events = [call.args[0] for call in browser.send_json.call_args_list]
            self.assertEqual(events[-1], {"type": "complete", "text": "hello there", "id": "event-one"})
            self.assertIn({"type": "transcript", "text": "hello there"}, events)
            self.assertNotIn("SECRET", json.dumps(events))
            self.assertEqual(connect.call_args.kwargs["additional_headers"]["lang_code"], "en-IN")
            speech.reserve.assert_called_once()
        asyncio.run(run())

    def test_bad_frame_is_rejected_and_never_forwarded(self):
        async def run():
            provider = SimpleNamespace(send=AsyncMock())
            calls = 0
            async def recv():
                nonlocal calls
                calls += 1
                if calls == 1: return '{"type":"connected"}'
                await asyncio.sleep(10)
            provider.recv = recv
            browser = SimpleNamespace(receive=AsyncMock(return_value={"type": "websocket.receive", "bytes": bytes(2048)}), send_json=AsyncMock())
            speech = SimpleNamespace(enabled=True, reserve=MagicMock(return_value="SECRET"))
            registry = LeaseRegistry()
            lease = registry.claim(registry.issue(speech, "en", "voice", "one"))
            context = MagicMock()
            context.__aenter__ = AsyncMock(return_value=provider)
            context.__aexit__ = AsyncMock(return_value=False)
            with patch("websockets.asyncio.client.connect", return_value=context):
                with self.assertRaisesRegex(VoiceError, "invalid_audio"):
                    await relay_turn(browser, lease)
            provider.send.assert_not_awaited()
        asyncio.run(run())

    def test_timeout_is_safe_consumes_one_request_and_revokes_capability(self):
        speech = SimpleNamespace(enabled=True, blocked=False, reserve=MagicMock(return_value="SECRET"))
        token = REGISTRY.issue(speech, "en", "voice", "one")
        browser = SimpleNamespace(headers={"origin": "http://127.0.0.1:8502", "host": "127.0.0.1:8502"},
            accept=AsyncMock(), close=AsyncMock(), receive_text=AsyncMock(return_value=json.dumps({"token": token})), send_json=AsyncMock())
        context = MagicMock()
        context.__aenter__ = AsyncMock(side_effect=TimeoutError("SECRET_PROVIDER_PAYLOAD"))
        with patch("websockets.asyncio.client.connect", return_value=context):
            asyncio.run(voice_socket(browser))
        browser.send_json.assert_awaited_with({"type": "error", "code": "timeout"})
        self.assertTrue(speech.blocked)
        speech.reserve.assert_called_once()
        with self.assertRaises(VoiceError): REGISTRY.claim(token)

    def test_disabled_speech_session_makes_no_provider_request(self):
        speech = SimpleNamespace(enabled=False, reserve=MagicMock(side_effect=VoiceError("consent_required")))
        registry = LeaseRegistry()
        lease = registry.claim(registry.issue(speech, "en", "voice", "one"))
        with patch("websockets.asyncio.client.connect") as connect:
            with self.assertRaises(VoiceError): asyncio.run(relay_turn(None, lease))
        connect.assert_not_called()
