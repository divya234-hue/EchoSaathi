"""Integration test: the server, wired end to end, with no external services.

No microphone and no Gnani calls: the microphone is a stub and `tts.speak` is
mocked, so this proves the wiring — routes, the websocket protocol, the reply
path, and half-duplex muting — without spending credits or needing audio
hardware. It is the test that fails when someone renames a message type.
"""
import asyncio
import base64
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import AsyncMock, patch

os.environ.setdefault("GNANI_API_KEY", "test-key-not-used")

from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

import llm  # noqa: E402
import server  # noqa: E402
import tts  # noqa: E402


class FakeMic:
    """Stands in for stt.MicSession: records what the server does to it."""

    instances: list["FakeMic"] = []

    def __init__(self, on_text, **kwargs):
        self.on_text = on_text
        self.kwargs = kwargs
        self.muted = False
        self.started = False
        self.stopped = False
        FakeMic.instances.append(self)

    def available(self) -> bool:
        return True

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True


class FakeBrowserMic(FakeMic):
    """Stands in for stt.BrowserMic: frames from the page, not a device."""

    instances: list["FakeBrowserMic"] = []

    def __init__(self, on_text, **kwargs):
        super().__init__(on_text, **kwargs)
        self.fed: list[bytes] = []
        FakeBrowserMic.instances.append(self)

    async def feed(self, data: bytes):
        self.fed.append(bytes(data))


class SocketTestBase(unittest.IsolatedAsyncioTestCase):
    """One app, one socket, no device and no Gnani call."""

    async def asyncSetUp(self):
        FakeMic.instances = []
        FakeBrowserMic.instances = []
        self.speaks: list[str] = []
        self.speak_kwargs: list[dict] = []
        self.streamed: list[str] = []
        self.stream_kwargs: list[dict] = []
        self.muted_during_speak: list[bool] = []
        self.muted_during_stream: list[bool] = []
        outer = self

        async def fake_speak(text, **kwargs):
            outer.speaks.append(text)
            outer.speak_kwargs.append(kwargs)
            outer.muted_during_speak.append(FakeMic.instances[-1].muted)
            return 123, False

        async def fake_stream_pcm(text, emit, **kwargs):
            outer.streamed.append(text)
            outer.stream_kwargs.append(kwargs)
            outer.muted_during_stream.append(FakeBrowserMic.instances[-1].muted)
            await emit(b"\x01\x02" * 512)
            await emit(b"\x03\x04" * 512)
            return 77, False

        self._patches = [
            patch.object(server, "MicSession", FakeMic),
            patch.object(server, "BrowserMic", FakeBrowserMic),
            patch.object(tts, "speak", fake_speak),
            patch.object(tts, "stream_pcm", fake_stream_pcm),
            # No test may reach the LLM: the real key is in .env.
            patch.object(llm, "available", return_value=False),
            patch.object(llm, "direct_reply", return_value=None),
        ]
        for p in self._patches:
            p.start()
        self.client = TestClient(TestServer(server.make_app()))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        for p in reversed(self._patches):
            p.stop()


class ServerIntegrationTest(SocketTestBase):
    # --- routing ---------------------------------------------------------

    async def test_index_is_served(self):
        resp = await self.client.get("/")
        self.assertEqual(resp.status, 200)
        self.assertIn("Pashyanti", await resp.text())

    # --- websocket protocol ----------------------------------------------

    async def test_hello_announces_models_and_mic(self):
        ws = await self.client.ws_connect("/ws")
        hello = await ws.receive_json()
        self.assertEqual(hello["type"], "hello")
        self.assertEqual(hello["models"],
                         {"stt": "prisma-v3.0", "tts": "timbre-v3.0"})
        self.assertTrue(hello["mic"])
        self.assertEqual(hello["voice"], "default")
        self.assertFalse(hello["cloned_voice"])
        self.assertFalse(hello["phone_line"])
        self.assertEqual(hello["mode"], "server")
        await ws.close()

    async def test_reply_walks_the_status_cycle(self):
        ws = await self.client.ws_connect("/ws")
        await ws.receive_json()                      # hello

        await ws.send_json({"type": "reply", "text": "हाँ, बोलिए।"})
        self.assertEqual(await ws.receive_json(),
                         {"type": "status", "state": "speaking"})

        spoken = await ws.receive_json()
        self.assertEqual(spoken["type"], "speak")
        self.assertEqual(spoken["text"], "हाँ, बोलिए।")
        self.assertEqual(spoken["ttfa_ms"], 123)

        self.assertEqual(await ws.receive_json(),
                         {"type": "status", "state": "listening"})
        self.assertEqual(self.speaks, ["हाँ, बोलिए।"])
        await ws.close()

    async def test_microphone_is_muted_while_speaking(self):
        """Half-duplex is a product rule: the mic hears our own speaker."""
        ws = await self.client.ws_connect("/ws")
        await ws.receive_json()
        await ws.send_json({"type": "reply", "text": "ठीक है।"})
        for _ in range(3):                           # speaking, speak, listening
            await ws.receive_json()
        await ws.close()

        self.assertEqual(self.muted_during_speak, [True])
        self.assertFalse(FakeMic.instances[-1].muted, "mic must be unmuted after")

    async def test_empty_reply_is_ignored(self):
        ws = await self.client.ws_connect("/ws")
        await ws.receive_json()
        await ws.send_json({"type": "reply", "text": "   "})
        await asyncio.sleep(0.05)
        self.assertEqual(self.speaks, [])
        await ws.close()

    async def test_unknown_message_type_does_not_kill_the_socket(self):
        ws = await self.client.ws_connect("/ws")
        await ws.receive_json()
        await ws.send_json({"type": "something-from-the-future"})
        await ws.send_json({"type": "reply", "text": "ठीक है।"})
        self.assertEqual((await ws.receive_json())["state"], "speaking")
        await ws.close()

    async def test_non_object_json_does_not_kill_the_socket(self):
        ws = await self.client.ws_connect("/ws")
        await ws.receive_json()  # hello

        for payload in ("null", "[]", '"hello"', "123"):
            await ws.send_str(payload)

        await ws.send_json({"type": "set_voice", "mode": "default"})
        response = await ws.receive_json()

        self.assertEqual(response["type"], "voice")
        self.assertEqual(response["mode"], "default")
        await ws.close()

    async def test_mic_is_stopped_when_the_page_disconnects(self):
        ws = await self.client.ws_connect("/ws")
        await ws.receive_json()
        await ws.close()
        for _ in range(20):
            if FakeMic.instances and FakeMic.instances[-1].stopped:
                break
            await asyncio.sleep(0.01)
        self.assertTrue(FakeMic.instances[-1].stopped)

    # --- voice ------------------------------------------------------------

    async def test_set_phone_line_restarts_the_mic_and_answers(self):
        ws = await self.client.ws_connect("/ws")
        hello = await ws.receive_json()
        self.assertFalse(hello["phone_line"])
        self.assertFalse(FakeMic.instances[-1].kwargs.get("telephony", False))

        await ws.send_json({"type": "set_phone_line", "enabled": True})
        self.assertEqual(await ws.receive_json(),
                         {"type": "phone_line", "enabled": True})
        self.assertTrue(FakeMic.instances[-1].kwargs.get("telephony"))
        self.assertTrue(FakeMic.instances[-2].stopped)

        await ws.send_json({"type": "set_phone_line", "enabled": False})
        self.assertEqual(await ws.receive_json(),
                         {"type": "phone_line", "enabled": False})
        self.assertFalse(FakeMic.instances[-1].kwargs.get("telephony"))
        await ws.close()

    async def test_set_voice_switches_this_calls_mode(self):
        ws = await self.client.ws_connect("/ws")
        await ws.receive_json()                      # hello

        with patch.object(tts, "EMBEDDING", {"embedding": "stub"}):
            await ws.send_json({"type": "set_voice", "mode": "cloned"})
            self.assertEqual(await ws.receive_json(),
                             {"type": "voice", "mode": "cloned"})
            self.assertEqual(await ws.receive_json(),
                             {"type": "cloned_voice", "enabled": True})

            await ws.send_json({"type": "set_voice", "mode": "default"})
            self.assertEqual(await ws.receive_json(),
                             {"type": "voice", "mode": "default"})
            self.assertEqual(await ws.receive_json(),
                             {"type": "cloned_voice", "enabled": False})
        await ws.close()

    async def test_set_voice_without_an_embedding_is_refused(self):
        ws = await self.client.ws_connect("/ws")
        await ws.receive_json()

        with patch.object(tts, "EMBEDDING", None):
            await ws.send_json({"type": "set_voice", "mode": "cloned"})
            error = await ws.receive_json()
            self.assertEqual(error["type"], "error")
            self.assertIn("cloned", error["message"])

            # the call stays in the default voice
            await ws.send_json({"type": "set_voice", "mode": "default"})
            self.assertEqual(await ws.receive_json(),
                             {"type": "voice", "mode": "default"})
        await ws.close()

    async def test_the_demo_toggle_alias_switches_the_voice(self):
        ws = await self.client.ws_connect("/ws")
        await ws.receive_json()

        with patch.object(tts, "EMBEDDING", {"embedding": "stub"}):
            await ws.send_json({"type": "set_cloned_voice", "enabled": True})
            self.assertEqual(await ws.receive_json(),
                             {"type": "voice", "mode": "cloned"})
            self.assertEqual(await ws.receive_json(),
                             {"type": "cloned_voice", "enabled": True})
        await ws.close()

    # --- reply chips in the caller's language -----------------------------

    async def _caller_line(self, text, lang, audio_ms=900):
        ws = await self.client.ws_connect("/ws")
        await ws.receive_json()                  # hello
        for _ in range(200):                     # probe + live session
            if len(FakeMic.instances) >= 2:
                break
            await asyncio.sleep(0.01)
        await FakeMic.instances[-1].on_text(text, lang, 40, audio_ms)
        self.assertEqual((await ws.receive_json())["type"], "transcript")
        return ws

    async def test_a_transcript_offers_chips_in_the_callers_language(self):
        with patch.object(llm, "available", return_value=True), \
             patch.object(llm, "direct_reply", return_value="ठीक है, दस बजे आऊँगी।"):
            ws = await self._caller_line("कल दस बजे आइए।", "hi-IN")
            suggest = await ws.receive_json()
        self.assertEqual(suggest["type"], "suggest")
        self.assertEqual(suggest["lang"], "hi-IN")
        self.assertEqual(suggest["chips"], [
            "ठीक है, दस बजे आऊँगी।",
            "कृपया दोहराइए।",
            "थोड़ा धीरे बोलिए।",
        ])
        await ws.close()

    async def test_a_bengali_caller_gets_bengali_chips(self):
        with patch.object(llm, "available", return_value=True), \
             patch.object(llm, "direct_reply", return_value="হ্যাঁ, বলুন।"):
            ws = await self._caller_line("আপনি কেমন আছেন?", "bn-IN")
            suggest = await ws.receive_json()
        self.assertEqual(suggest["lang"], "bn-IN")
        self.assertEqual(suggest["chips"][0], "হ্যাঁ, বলুন।")
        self.assertEqual(suggest["chips"][1:], ["অনুগ্রহ করে আবার বলুন।",
                                                "একটু ধীরে বলুন।"])
        await ws.close()

    async def test_no_llm_key_means_no_suggest_message(self):
        ws = await self._caller_line("कल दस बजे आइए।", "hi-IN")
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(server, "CACHE", Path(tmp) / "cache"):
            await ws.send_json({"type": "end_call"})
            frame = await ws.receive_json()
            self.assertEqual(frame["type"], "summary")
        await ws.close()

    async def test_an_unusable_llm_answer_sends_nothing(self):
        with patch.object(llm, "available", return_value=True), \
             patch.object(llm, "direct_reply", return_value=None):
            ws = await self._caller_line("कल दस बजे आइए।", "hi-IN")
            with tempfile.TemporaryDirectory() as tmp, \
                 patch.object(server, "CACHE", Path(tmp) / "cache"):
                await ws.send_json({"type": "end_call"})
                frame = await ws.receive_json()
                self.assertEqual(frame["type"], "summary")
        await ws.close()

    async def test_the_reply_is_spoken_in_the_callers_language(self):
        ws = await self._caller_line("আপনি কেমন আছেন?", "bn-IN")
        await ws.send_json({"type": "reply", "text": "ভালো আছি।"})
        self.assertEqual((await ws.receive_json())["state"], "speaking")
        spoken = await ws.receive_json()
        self.assertEqual(spoken["type"], "speak")
        self.assertEqual(spoken["lang"], "bn-IN")
        self.assertEqual(self.speak_kwargs[-1]["lang"], "bn-IN")
        await ws.close()

    async def test_a_hindi_caller_keeps_the_hindi_default(self):
        ws = await self._caller_line("कल दस बजे आइए।", "hi-IN")
        await ws.send_json({"type": "reply", "text": "ठीक है।"})
        await ws.receive_json()                  # speaking
        spoken = await ws.receive_json()
        self.assertEqual(spoken["lang"], "hi-IN")
        await ws.close()

    # --- end of call ------------------------------------------------------

    async def test_end_call_sends_summary_and_caches_it(self):
        ws = await self.client.ws_connect("/ws")
        await ws.receive_json()                      # hello
        for _ in range(200):                         # probe + live session
            if len(FakeMic.instances) >= 2:
                break
            await asyncio.sleep(0.01)
        mic = FakeMic.instances[-1]

        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(server, "CACHE", Path(tmp) / "cache"):
            await mic.on_text("I need an ambulance", "hi", 40, 800)
            await ws.receive_json()                  # transcript

            await ws.send_json({"type": "reply", "text": "Sending one now"})
            for _ in range(3):                       # speaking, speak, listening
                await ws.receive_json()

            await ws.send_json({"type": "end_call"})
            summary = await ws.receive_json()

            self.assertEqual(summary["type"], "summary")
            self.assertEqual(summary["turns"], 1)
            self.assertEqual(summary["who"], "I need an ambulance")
            self.assertEqual(summary["agreed"], "I need an ambulance")
            self.assertEqual(summary["next"], "Sending one now")
            self.assertIsInstance(summary["duration_s"], int)

            written = json.loads(
                (Path(tmp) / "cache" / "summary.json").read_text(encoding="utf-8")
            )
            self.assertEqual(written["turns"], 1)
            self.assertEqual(written["who"], "I need an ambulance")
            self.assertEqual(written["next"], "Sending one now")
        await ws.close()

    async def test_end_call_sends_the_extractive_card_then_the_rewrite(self):
        ws = await self.client.ws_connect("/ws")
        await ws.receive_json()
        for _ in range(200):
            if len(FakeMic.instances) >= 2:
                break
            await asyncio.sleep(0.01)
        await FakeMic.instances[-1].on_text("I need an ambulance", "hi-IN", 40, 800)
        await ws.receive_json()                  # transcript

        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(server, "CACHE", Path(tmp) / "cache"), \
             patch.object(llm, "available", return_value=True), \
             patch.object(llm, "summary", return_value={
                 "who": "the ambulance service",
                 "agreed": "an ambulance is on its way",
                 "next": "wait outside"}):
            await ws.send_json({"type": "end_call", "lang": "hi"})
            first = await ws.receive_json()
            second = await ws.receive_json()
            written = json.loads(
                (Path(tmp) / "cache" / "summary.json").read_text(encoding="utf-8"))

        # The pure function's card is first and unchanged; the model's follows.
        self.assertEqual(first["type"], "summary")
        self.assertEqual(first["who"], "I need an ambulance")
        self.assertEqual(second["type"], "summary")
        self.assertEqual(second["who"], "the ambulance service")
        self.assertEqual(second["turns"], first["turns"])
        self.assertEqual(second["duration_s"], first["duration_s"])
        self.assertEqual(written["next"], "wait outside")
        await ws.close()

    async def test_a_blank_model_summary_sends_only_one_card(self):
        ws = await self.client.ws_connect("/ws")
        await ws.receive_json()
        for _ in range(200):
            if len(FakeMic.instances) >= 2:
                break
            await asyncio.sleep(0.01)
        await FakeMic.instances[-1].on_text("I need an ambulance", "hi-IN", 40, 800)
        await ws.receive_json()

        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(server, "CACHE", Path(tmp) / "cache"), \
             patch.object(llm, "available", return_value=True), \
             patch.object(llm, "summary",
                          return_value={"who": "", "agreed": "", "next": ""}):
            await ws.send_json({"type": "end_call"})
            first = await ws.receive_json()
            # The next frame is the voice switch, not a second summary.
            await ws.send_json({"type": "set_voice", "mode": "default"})
            following = await ws.receive_json()

        self.assertEqual(first["type"], "summary")
        self.assertEqual(first["who"], "I need an ambulance")
        self.assertEqual(following["type"], "voice")
        await ws.close()

    async def test_the_summary_model_gets_the_ui_locale(self):
        seen = []

        def fake_summary(lines, lang):
            seen.append(lang)
            return {"who": "डॉ. मेहरा की क्लिनिक", "agreed": "कल दस बजे",
                    "next": "वह आएगी"}

        ws = await self.client.ws_connect("/ws")
        await ws.receive_json()
        for _ in range(200):
            if len(FakeMic.instances) >= 2:
                break
            await asyncio.sleep(0.01)
        await FakeMic.instances[-1].on_text("कल दस बजे आइए।", "hi-IN", 40, 900)
        await ws.receive_json()

        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(server, "CACHE", Path(tmp) / "cache"), \
             patch.object(llm, "available", return_value=True), \
             patch.object(llm, "summary", fake_summary):
            await ws.send_json({"type": "end_call", "lang": "hi"})
            await ws.receive_json()              # extractive
            rewritten = await ws.receive_json()

        self.assertEqual(seen, ["hi"])
        self.assertEqual(rewritten["who"], "डॉ. मेहरा की क्लिनिक")
        await ws.close()

    async def test_a_slow_summary_model_leaves_the_extractive_card(self):
        def timeout(*_a, **_k):
            raise TimeoutError("too slow")

        ws = await self.client.ws_connect("/ws")
        await ws.receive_json()
        for _ in range(200):
            if len(FakeMic.instances) >= 2:
                break
            await asyncio.sleep(0.01)
        await FakeMic.instances[-1].on_text("I need an ambulance", "hi-IN", 40, 800)
        await ws.receive_json()

        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(server, "CACHE", Path(tmp) / "cache"), \
             patch.object(llm, "available", return_value=True), \
             patch.object(llm, "summary", timeout):
            await ws.send_json({"type": "end_call"})
            first = await ws.receive_json()
            await ws.send_json({"type": "set_voice", "mode": "default"})
            following = await ws.receive_json()

        self.assertEqual(first["who"], "I need an ambulance")
        self.assertEqual(following["type"], "voice")
        await ws.close()

    async def test_end_call_stops_the_server_microphone(self):
        ws = await self.client.ws_connect("/ws")
        await ws.receive_json()
        for _ in range(200):
            if len(FakeMic.instances) >= 2:
                break
            await asyncio.sleep(0.01)
        mic = FakeMic.instances[-1]

        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(server, "CACHE", Path(tmp) / "cache"):
            await ws.send_json({"type": "end_call"})
            summary = await ws.receive_json()

        self.assertEqual(summary["type"], "summary")
        self.assertTrue(mic.stopped, "ending the call must close the microphone")
        await ws.close()

    async def test_new_call_starts_a_fresh_session(self):
        ws = await self.client.ws_connect("/ws")
        await ws.receive_json()
        for _ in range(200):
            if len(FakeMic.instances) >= 2:
                break
            await asyncio.sleep(0.01)
        first = FakeMic.instances[-1]
        await first.on_text("first call", "hi-IN", 40, 900)
        await ws.receive_json()                      # transcript

        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(server, "CACHE", Path(tmp) / "cache"):
            await ws.send_json({"type": "end_call"})
            await ws.receive_json()                  # summary (extractive)
            await ws.send_json({"type": "new_call"})

            for _ in range(200):                     # the microphone reopens
                if len(FakeMic.instances) >= 3:
                    break
                await asyncio.sleep(0.01)
            second = FakeMic.instances[-1]
            self.assertIsNot(second, first)
            self.assertTrue(second.started)
            self.assertFalse(second.stopped)

            await second.on_text("second call", "hi-IN", 40, 900)
            transcript = await ws.receive_json()
            self.assertEqual(transcript["text"], "second call")

            await ws.send_json({"type": "end_call"})
            summary = await ws.receive_json()

        # The new card counts the new call only: lines were not carried over.
        self.assertEqual(summary["turns"], 1)
        self.assertEqual(summary["who"], "second call")
        await ws.close()

    async def test_hallucinated_transcript_asks_to_repeat(self):
        ws = await self.client.ws_connect("/ws")
        await ws.receive_json()                      # hello
        for _ in range(200):
            if len(FakeMic.instances) >= 2:
                break
            await asyncio.sleep(0.01)
        mic = FakeMic.instances[-1]

        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(server, "CACHE", Path(tmp) / "cache"):
            # Four words out of 200 ms of noise: Prisma guessed, so ask again.
            await mic.on_text("Sir, क्या जमा करें?", "hi", 30, 200)
            self.assertEqual(await ws.receive_json(), {"type": "retry"})

            await ws.send_json({"type": "end_call"})
            frames = []
            while True:
                frame = await ws.receive_json()
                frames.append(frame)
                if frame.get("type") == "summary":
                    break

            self.assertNotIn("transcript", [f["type"] for f in frames])
            self.assertEqual(frames[-1]["turns"], 0)
            self.assertEqual(frames[-1]["who"], "unknown caller")
        await ws.close()


class TalkModeTest(SocketTestBase):
    """`?mode=talk`: the page is the microphone and the speaker (D-004)."""

    async def _talk(self):
        ws = await self.client.ws_connect("/ws?mode=talk")
        hello = await ws.receive_json()
        return ws, hello

    async def _ready(self, ws):
        await ws.send_json({"type": "start_capture"})
        frame = await ws.receive_json()
        self.assertEqual(frame, {"type": "capture", "state": "ready"})
        return FakeBrowserMic.instances[-1]

    async def test_hello_says_talk_mode_and_starts_no_server_mic(self):
        ws, hello = await self._talk()
        self.assertEqual(hello["mode"], "talk")
        self.assertTrue(hello["mic"])
        await asyncio.sleep(0.05)
        # `hello` constructs a probe to report availability; nothing is started.
        self.assertEqual([m for m in FakeMic.instances if m.started], [],
                         "talk mode must not open a device")
        self.assertEqual(FakeBrowserMic.instances, [],
                         "the page's mic opens only on its gesture")
        await ws.close()

    async def test_prisma_opens_on_the_start_listening_gesture(self):
        ws, _ = await self._talk()
        await asyncio.sleep(0.05)
        self.assertEqual(FakeBrowserMic.instances, [])
        mic = await self._ready(ws)
        self.assertIsInstance(mic, FakeBrowserMic)
        self.assertTrue(mic.started)
        self.assertFalse(mic.kwargs.get("telephony", False))
        await ws.close()

    async def test_binary_frames_reach_the_browser_mic(self):
        ws, _ = await self._talk()
        mic = await self._ready(ws)
        await ws.send_bytes(b"\x01" * 1024)
        await ws.send_bytes(b"\x02" * 1024)
        for _ in range(50):
            if len(mic.fed) >= 2:
                break
            await asyncio.sleep(0.01)
        self.assertEqual(mic.fed, [b"\x01" * 1024, b"\x02" * 1024])
        await ws.close()

    async def test_a_frame_before_the_gesture_is_dropped_quietly(self):
        ws, _ = await self._talk()
        await ws.send_bytes(b"\x01" * 1024)      # no capture session yet
        await asyncio.sleep(0.05)
        mic = await self._ready(ws)
        self.assertEqual(mic.fed, [])
        await ws.close()

    async def test_a_binary_frame_in_server_mode_does_not_kill_the_socket(self):
        ws = await self.client.ws_connect("/ws")
        await ws.receive_json()
        await ws.send_bytes(b"\x01" * 1024)
        await ws.send_json({"type": "reply", "text": "ठीक है।"})
        self.assertEqual((await ws.receive_json())["state"], "speaking")
        self.assertEqual(FakeBrowserMic.instances, [])
        await ws.close()

    async def test_the_reply_is_streamed_to_the_page(self):
        ws, _ = await self._talk()
        await self._ready(ws)
        await ws.send_json({"type": "reply", "text": "हाँ, बोलिए।"})

        self.assertEqual(await ws.receive_json(),
                         {"type": "status", "state": "speaking"})

        first = await ws.receive_json()
        self.assertEqual(first["type"], "audio")
        self.assertEqual(first["rate"], tts.RATE)
        self.assertEqual(base64.b64decode(first["data"]), b"\x01\x02" * 512)

        second = await ws.receive_json()
        self.assertEqual(base64.b64decode(second["data"]), b"\x03\x04" * 512)

        final = await ws.receive_json()
        self.assertEqual(final, {"type": "audio", "data": "",
                                 "rate": tts.RATE, "final": True})

        spoken = await ws.receive_json()
        self.assertEqual(spoken["type"], "speak")
        self.assertEqual(spoken["ttfa_ms"], 77)

        self.assertEqual(await ws.receive_json(),
                         {"type": "status", "state": "listening"})
        self.assertEqual(self.streamed, ["हाँ, बोलिए।"])
        self.assertEqual(self.speaks, [], "the server must not play it too")
        await ws.close()

    async def test_the_page_mic_is_muted_while_the_reply_streams(self):
        ws, _ = await self._talk()
        mic = await self._ready(ws)
        await ws.send_json({"type": "reply", "text": "ठीक है।"})
        for _ in range(5):                       # speaking, 2 audio, final, speak… 
            if (await ws.receive_json()).get("type") == "speak":
                break
        self.assertEqual(self.muted_during_stream, [True])
        self.assertFalse(mic.muted, "the mic must be unmuted after the reply")
        await ws.close()

    async def test_a_reply_can_be_ended_by_the_phone(self):
        ws, _ = await self._talk()
        mic = await self._ready(ws)
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(server, "CACHE", Path(tmp) / "cache"):
            await ws.send_json({"type": "end_call"})
            # The page is told first, so it can release the microphone...
            self.assertEqual(await ws.receive_json(),
                             {"type": "capture", "state": "stopped"})
            summary = await ws.receive_json()
            self.assertEqual(summary["type"], "summary")
        # ...and the server's session is gone with it.
        self.assertTrue(mic.stopped)
        await ws.close()

    async def test_nothing_is_transcribed_after_the_call_ends(self):
        ws, _ = await self._talk()
        mic = await self._ready(ws)
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(server, "CACHE", Path(tmp) / "cache"):
            await ws.send_json({"type": "end_call"})
            await ws.receive_json()                  # capture stopped
            await ws.receive_json()                  # summary
            await mic.on_text("a new sentence", "hi-IN", 40, 900)
            await ws.send_bytes(b"\x01" * 1024)      # a frame after the end
            await ws.send_json({"type": "set_voice", "mode": "default"})
            following = await ws.receive_json()
        self.assertEqual(following["type"], "voice",
                         "the ended session must not transcribe or reply")
        await ws.close()

    async def test_new_call_in_talk_mode_waits_for_the_gesture(self):
        ws, _ = await self._talk()
        await self._ready(ws)
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(server, "CACHE", Path(tmp) / "cache"):
            await ws.send_json({"type": "end_call"})
            await ws.receive_json()                  # capture stopped
            await ws.receive_json()                  # summary

            before = len(FakeBrowserMic.instances)
            await ws.send_json({"type": "new_call"})
            self.assertEqual(await ws.receive_json(),
                             {"type": "capture", "state": "stopped"})
            self.assertEqual(len(FakeBrowserMic.instances), before,
                             "a new call needs a fresh tap, not a silent open")
            await ws.send_json({"type": "start_capture"})
            self.assertEqual(await ws.receive_json(),
                             {"type": "capture", "state": "ready"})
            self.assertEqual(len(FakeBrowserMic.instances), before + 1)
        await ws.close()


class MissingMicTest(unittest.IsolatedAsyncioTestCase):
    """With no audio device the app must still boot and say so."""

    async def test_hello_reports_no_mic(self):
        with patch.object(server, "MicSession", FakeMic), \
             patch.object(FakeMic, "available", return_value=False):
            client = TestClient(TestServer(server.make_app()))
            await client.start_server()
            try:
                ws = await client.ws_connect("/ws")
                hello = await ws.receive_json()
                self.assertFalse(hello["mic"])
                await ws.close()
            finally:
                await client.close()


class SummaryLlmFlagTest(unittest.TestCase):
    """SUMMARY_LLM=0 is the demo's escape hatch: one card, no model."""

    def test_on_by_default(self):
        self.assertTrue(server._summary_llm_enabled({}))

    def test_zero_turns_it_off(self):
        self.assertFalse(server._summary_llm_enabled({"SUMMARY_LLM": "0"}))

    def test_one_keeps_it_on(self):
        self.assertTrue(server._summary_llm_enabled({"SUMMARY_LLM": "1"}))


class PhoneLineFlagTest(unittest.TestCase):
    """--phone-line / PHONE_LINE=1 is the only way the mode turns on."""

    def test_flag_comes_from_the_command_line(self):
        self.assertTrue(server._phone_line_enabled(["--phone-line"], {}))

    def test_flag_comes_from_the_environment(self):
        self.assertTrue(server._phone_line_enabled([], {"PHONE_LINE": "1"}))

    def test_clean_is_the_default(self):
        self.assertFalse(server._phone_line_enabled([], {}))
        self.assertFalse(server._phone_line_enabled([], {"PHONE_LINE": "0"}))


if __name__ == "__main__":
    unittest.main()
