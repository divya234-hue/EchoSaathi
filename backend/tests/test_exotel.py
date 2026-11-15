"""The carrier pilot: Exotel framing, the token gate, and the page binding.

No real phone call here — a simulated Exotel client sends the same events the
trial call sent, and Prisma/Timbre are the usual stubs. The carrier itself (and
the hangup POST) cannot be proven in CI; `docs/EXOTEL-BRIDGE.md` says so.
"""
import asyncio
import base64
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

os.environ.setdefault("GNANI_API_KEY", "test-key-not-used")

from aiohttp.test_utils import TestClient, TestServer  # noqa: E402

import exotel  # noqa: E402
import llm  # noqa: E402
import server  # noqa: E402
import tts  # noqa: E402
from tests.test_server import FakeMic  # noqa: E402

TOKEN = "test-carrier-token"
PCM_3200 = b"\x01\x00" * 1600                    # 200 ms at 8 kHz, s16le


class FakeCarrierMic:
    """Stands in for exotel.BrowserMic: the carrier's Prisma feed."""

    instances: list["FakeCarrierMic"] = []

    def __init__(self, on_text, **kwargs):
        self.on_text = on_text
        self.kwargs = kwargs
        self.muted = False
        self.frames_in = 0
        self.frames_out = 0
        self.gaps = 0
        self.started = False
        self.stopped = False
        FakeCarrierMic.instances.append(self)

    async def start(self):
        self.started = True

    async def stop(self):
        self.stopped = True

    async def feed(self, frame: bytes):
        self.frames_in += 1


class MaskTest(unittest.TestCase):
    def test_only_the_last_four_digits_are_ever_returned(self):
        masked = exotel.mask_number("+919812345678")
        self.assertEqual(masked, "••••5678")
        self.assertNotIn("981234", masked)

    def test_a_short_or_missing_number_does_not_leak(self):
        self.assertEqual(exotel.mask_number(""), "••••")
        self.assertEqual(exotel.mask_number(None), "••••")
        self.assertEqual(exotel.mask_number("12"), "••••")


class MediaTest(unittest.TestCase):
    def test_a_media_payload_decodes(self):
        payload = base64.b64encode(PCM_3200).decode()
        self.assertEqual(exotel.media_pcm(payload), PCM_3200)

    def test_junk_is_not_audio(self):
        self.assertIsNone(exotel.media_pcm("not base64 !!"))
        self.assertIsNone(exotel.media_pcm(""))
        self.assertIsNone(exotel.media_pcm(None))

    def test_3200_bytes_become_exactly_the_frames_prisma_takes(self):
        parser = exotel.FrameParser()
        frames = parser.feed(PCM_3200)
        self.assertEqual([len(f) for f in frames], [1024, 1024, 1024])
        self.assertEqual(parser.pending, 3200 - 3 * 1024)

    def test_outbound_chunks_are_padded_to_200_ms(self):
        self.assertEqual([len(c) for c in exotel.out_chunks(b"\x01" * 7200)],
                         [3200, 3200, 3200])
        chunks = exotel.out_chunks(b"\x01" * 1000)
        self.assertEqual(len(chunks), 1)
        self.assertEqual(len(chunks[0]), 3200)


class StartTest(unittest.TestCase):
    def test_the_trial_call_shape_is_read(self):
        event = {"event": "start", "stream_sid": "s1",
                 "start": {"stream_sid": "s1", "from": "+910000000000",
                           "to": "+910000000001"}}
        fields = exotel.start_fields(event)
        self.assertEqual(fields["sid"], "s1")
        self.assertEqual(fields["from"], "+910000000000")

    def test_a_missing_start_does_not_crash(self):
        self.assertEqual(exotel.start_fields({})["sid"], "")


class TokenTest(unittest.TestCase):
    def test_without_the_variable_the_bridge_is_off(self):
        with patch.dict(os.environ, {"EXOTEL_WS_TOKEN": ""}):
            self.assertFalse(exotel.enabled())
            self.assertFalse(exotel.token_ok("anything"))

    def test_the_token_must_match(self):
        with patch.dict(os.environ, {"EXOTEL_WS_TOKEN": TOKEN}):
            self.assertTrue(exotel.enabled())
            self.assertTrue(exotel.token_ok(TOKEN))
            self.assertFalse(exotel.token_ok("nope"))
            self.assertFalse(exotel.token_ok(None))


class HangupTest(unittest.TestCase):
    def test_no_configuration_means_no_rest_call(self):
        with patch.dict(os.environ, {}, clear=False):
            for key in ("EXOTEL_ACCOUNT_SID", "EXOTEL_SUBDOMAIN"):
                os.environ.pop(key, None)
            self.assertIsNone(exotel.hangup_request("s1"))

    def test_a_missing_call_sid_means_no_rest_call(self):
        # The stream SID cannot end the line; without the call SID there is
        # nothing to post to and the route would be a 403 anyway.
        env = {"EXOTEL_ACCOUNT_SID": "acct", "EXOTEL_SUBDOMAIN": "api"}
        with patch.dict(os.environ, env):
            self.assertIsNone(exotel.hangup_request(""))

    def test_a_bare_subdomain_and_a_full_host_both_work(self):
        env = {"EXOTEL_ACCOUNT_SID": "acct", "EXOTEL_API_KEY": "k",
               "EXOTEL_API_TOKEN": "t"}
        for value, expected in (("api", "https://api.exotel.com/v1/x"),
                                ("api.exotel.com", "https://api.exotel.com/v1/x"),
                                ("api.exotel.com/", "https://api.exotel.com/v1/x")):
            with patch.dict(os.environ, {**env, "EXOTEL_SUBDOMAIN": value,
                                        "EXOTEL_HANGUP_PATH": "/v1/x"}):
                url, _ = exotel.hangup_request("CA1")
            self.assertEqual(url, expected)

    def test_the_default_route_is_the_hangup_resource(self):
        # Measured 15 Nov: POST .../Calls/{sid} is 403 "Method not allowed";
        # only .../Calls/{sid}/Hangup answers 200 "Hangup Successful".
        env = {"EXOTEL_ACCOUNT_SID": "acct", "EXOTEL_SUBDOMAIN": "api"}
        with patch.dict(os.environ, env):
            url, form = exotel.hangup_request("CA1234")
        self.assertEqual(
            url, "https://api.exotel.com/v1/Accounts/acct/Calls/CA1234/Hangup")
        self.assertEqual(form, {"Status": "completed"})

    def test_the_start_event_keeps_the_call_sid_apart_from_the_stream_sid(self):
        fields = exotel.start_fields({
            "event": "start",
            "stream_sid": "MZ_stream",
            "start": {"stream_sid": "MZ_stream", "call_sid": "CA_call",
                      "account_sid": "AC_acct"}})
        self.assertEqual(fields["sid"], "MZ_stream")
        self.assertEqual(fields["call_sid"], "CA_call")
        self.assertEqual(fields["account_sid"], "AC_acct")


class BridgeHttpTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        exotel._live = False
        exotel._page = None
        self._patches = [
            patch.object(server, "MicSession", FakeMic),
            patch.object(exotel, "BrowserMic", FakeCarrierMic),
            patch.object(llm, "available", return_value=False),
        ]
        for p in self._patches:
            p.start()
        self.client = TestClient(TestServer(server.make_app()))
        await self.client.start_server()

    async def asyncTearDown(self):
        await self.client.close()
        for p in reversed(self._patches):
            p.stop()
        exotel._live = False
        exotel._page = None

    async def test_disabled_without_a_token(self):
        with patch.dict(os.environ, {"EXOTEL_WS_TOKEN": ""}):
            resp = await self.client.get("/exotel/ws?token=x")
        self.assertEqual(resp.status, 503)

    async def test_a_wrong_token_is_refused(self):
        with patch.dict(os.environ, {"EXOTEL_WS_TOKEN": TOKEN}):
            resp = await self.client.get("/exotel/ws?token=wrong")
        self.assertEqual(resp.status, 403)

    async def test_no_open_page_means_no_call(self):
        with patch.dict(os.environ, {"EXOTEL_WS_TOKEN": TOKEN}):
            resp = await self.client.get(f"/exotel/ws?token={TOKEN}")
        self.assertEqual(resp.status, 409)

    async def test_the_token_may_arrive_in_the_path(self):
        # Some consoles drop an applet URL's query string on save, and the call
        # then arrives as a bare path. The gate must still see the secret.
        with patch.dict(os.environ, {"EXOTEL_WS_TOKEN": TOKEN}):
            resp = await self.client.get(f"/exotel/ws/{TOKEN}")
        self.assertEqual(resp.status, 409)      # past the gate: no page yet

    async def test_a_wrong_path_token_is_still_refused(self):
        with patch.dict(os.environ, {"EXOTEL_WS_TOKEN": TOKEN}):
            resp = await self.client.get("/exotel/ws/nope")
        self.assertEqual(resp.status, 403)


class BridgeCallTest(unittest.IsolatedAsyncioTestCase):
    """One page, one simulated carrier call, end to end through the app."""

    async def asyncSetUp(self):
        exotel._live = False
        exotel._page = None
        FakeCarrierMic.instances = []
        self.streamed = []

        async def fake_stream_pcm(text, emit, **kwargs):
            self.streamed.append((text, kwargs.get("lang"), kwargs.get("rate")))
            await emit(b"\x02\x00" * 3200)
            return 40, False

        self._patches = [
            patch.object(server, "MicSession", FakeMic),
            patch.object(exotel, "BrowserMic", FakeCarrierMic),
            patch.object(llm, "available", return_value=False),
            patch.object(tts, "stream_pcm", fake_stream_pcm),
            # The clip cache is real on this machine and would make the
            # acknowledgement appear in unrelated tests after the first run.
            patch.object(tts, "is_cached", return_value=True),
            patch.object(tts, "warm", unittest.mock.AsyncMock()),
            patch.dict(os.environ, {"EXOTEL_WS_TOKEN": TOKEN}),
        ]
        for p in self._patches:
            p.start()
        self.client = TestClient(TestServer(server.make_app()))
        await self.client.start_server()

        self.page = await self.client.ws_connect("/ws")
        await self.page.receive_json()               # hello

    async def asyncTearDown(self):
        await self.client.close()
        for p in reversed(self._patches):
            p.stop()
        exotel._live = False
        exotel._page = None

    async def _carrier(self, url: str | None = None):
        ws = await self.client.ws_connect(url or f"/exotel/ws?token={TOKEN}")
        await ws.send_json({"event": "connected"})
        await ws.send_json({
            "event": "start", "stream_sid": "s1",
            "start": {"stream_sid": "s1", "from": "+919812345678",
                      "to": "+919513886363",
                      "media_format": {"encoding": "audio/x-raw",
                                       "sample_rate": 8000}}})
        return ws

    async def test_a_call_binds_to_the_page_and_takes_over_the_mic(self):
        for _ in range(100):                     # the room mic is open first
            if len(FakeMic.instances) >= 2:
                break
            await asyncio.sleep(0.01)
        room = FakeMic.instances[-1]

        ws = await self._carrier()
        self.assertEqual(await self.page.receive_json(), {
            "type": "carrier", "state": "live", "from": "••••5678"})
        mic = FakeCarrierMic.instances[-1]
        self.assertTrue(mic.started)
        self.assertTrue(room.stopped,
                        "the room's microphone must give way to the call")
        await ws.close()

    async def test_a_path_token_also_binds_the_call(self):
        # The console-safe form: the same call, secret in the path instead.
        for _ in range(100):
            if len(FakeMic.instances) >= 2:
                break
            await asyncio.sleep(0.01)
        room = FakeMic.instances[-1]

        ws = await self._carrier(f"/exotel/ws/{TOKEN}")
        self.assertEqual(await self.page.receive_json(), {
            "type": "carrier", "state": "live", "from": "••••5678"})
        self.assertTrue(room.stopped,
                        "the room's microphone must give way to the call")
        await ws.close()

    async def test_a_call_is_refused_while_the_page_has_ended(self):
        ws = await self._carrier()
        await self.page.receive_json()           # carrier live
        await ws.send_json({"event": "stop"})
        await self.page.receive_json()           # carrier ended

        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(server, "CACHE", Path(tmp) / "cache"):
            await self.page.send_json({"type": "end_call"})
            await self.page.receive_json()       # summary

        with patch.dict(os.environ, {"EXOTEL_WS_TOKEN": TOKEN}):
            resp = await self.client.get(f"/exotel/ws?token={TOKEN}")
        self.assertEqual(resp.status, 409, "New call must re-arm the screen")

    async def test_closing_the_page_hangs_up_the_line(self):
        ws = await self._carrier()
        await self.page.receive_json()           # carrier live
        with patch.object(exotel.CarrierCall, "hangup",
                          new=unittest.mock.AsyncMock()) as hangup:
            await self.page.close()
            for _ in range(100):
                if hangup.called:
                    break
                await asyncio.sleep(0.01)
        self.assertTrue(hangup.called)
        await ws.close()

    async def test_media_becomes_1024_byte_frames_for_prisma(self):
        ws = await self._carrier()
        await self.page.receive_json()               # carrier live
        await ws.send_json({"event": "media",
                            "media": {"payload": base64.b64encode(PCM_3200).decode()}})
        mic = FakeCarrierMic.instances[-1]
        for _ in range(100):
            if mic.frames_in >= 3:
                break
            await asyncio.sleep(0.01)
        self.assertEqual(mic.frames_in, 3)
        await ws.close()

    async def test_a_callers_line_reaches_the_page(self):
        ws = await self._carrier()
        await self.page.receive_json()               # carrier live
        mic = FakeCarrierMic.instances[-1]
        await mic.on_text("नमस्ते, क्या मैं डॉक्टर से बात कर सकता हूँ?", "hi-IN",
                          40, 900)
        transcript = await self.page.receive_json()
        self.assertEqual(transcript["type"], "transcript")
        self.assertEqual(transcript["lang"], "hi-IN")
        await ws.close()

    async def test_the_page_reply_goes_down_the_line(self):
        ws = await self._carrier()
        await self.page.receive_json()               # carrier live
        await self.page.send_json({"type": "reply", "text": "हाँ, बोलिए।"})

        self.assertEqual((await self.page.receive_json())["state"], "speaking")
        media = await ws.receive_json()
        self.assertEqual(media["event"], "media")
        self.assertEqual(len(base64.b64decode(media["media"]["payload"])), 3200)
        self.assertEqual(self.streamed[-1], ("हाँ, बोलिए।", "hi-IN", 8000))
        spoken = await self.page.receive_json()
        self.assertEqual(spoken["type"], "speak")
        self.assertEqual(FakeCarrierMic.instances[-1].muted, False)
        await ws.close()

    async def test_a_cached_acknowledgement_goes_out_before_the_reply(self):
        # The caller hears a word in ~0.3 s instead of silence while Timbre
        # synthesises. It must be first, and the reply must follow intact.
        ack_pcm = b"\x07\x00" * 1600                 # one 3200-byte chunk
        with tempfile.TemporaryDirectory() as tmp:
            ack_path = Path(tmp) / "ack.pcm"
            ack_path.write_bytes(ack_pcm)
            with patch.object(tts, "is_cached", return_value=False), \
                 patch.object(tts, "cached_path", return_value=str(ack_path)):
                ws = await self._carrier()
                await self.page.receive_json()        # carrier live
                await self.page.send_json({"type": "reply", "text": "ok"})
                self.assertEqual((await self.page.receive_json())["state"],
                                 "speaking")
                first = base64.b64decode(
                    (await ws.receive_json())["media"]["payload"])
                second = base64.b64decode(
                    (await ws.receive_json())["media"]["payload"])
        self.assertEqual(first, ack_pcm,
                         "the acknowledgement is the first thing heard")
        self.assertEqual(second, b"\x02\x00" * 1600, "then the reply audio")
        await ws.close()

    async def test_a_cached_reply_gets_no_acknowledgement(self):
        # A cached reply is already instant; adding a word would delay it.
        with patch.object(tts, "is_cached", return_value=True):
            ws = await self._carrier()
            await self.page.receive_json()            # carrier live
            await self.page.send_json({"type": "reply", "text": "ok"})
            await self.page.receive_json()            # speaking
            first = base64.b64decode(
                (await ws.receive_json())["media"]["payload"])
        self.assertEqual(first, b"\x02\x00" * 1600,
                         "the reply starts immediately, with no acknowledgement")
        await ws.close()

    async def test_a_streamed_reply_has_no_silence_between_its_chunks(self):
        # Every model chunk used to be padded to 3200 bytes with zeros, so a
        # reply reached the handset as audio-gap-audio-gap. The remainder must
        # carry over, and only the true tail may be padded.
        piece = b"\x11\x22" * 500                    # 1000 bytes, not one zero

        async def ragged(text, emit, **kwargs):
            for _ in range(4):
                await emit(piece)
            return 40, False

        with patch.object(tts, "stream_pcm", ragged):
            ws = await self._carrier()
            await self.page.receive_json()           # carrier live
            await self.page.send_json({"type": "reply", "text": "ok"})
            self.assertEqual((await self.page.receive_json())["state"],
                             "speaking")
            first = base64.b64decode(
                (await ws.receive_json())["media"]["payload"])
            second = base64.b64decode(
                (await ws.receive_json())["media"]["payload"])

        audio = piece * 4                            # 4000 bytes spoken
        self.assertEqual(first, audio[:3200], "no gap inside a chunk")
        self.assertEqual(second[:800], audio[3200:])
        self.assertEqual(set(second[800:]), {0}, "only the true tail is padded")
        await ws.close()

    async def test_the_whole_reply_is_on_the_wire_before_speak(self):
        ws = await self._carrier()
        await self.page.receive_json()               # carrier live
        await self.page.send_json({"type": "reply", "text": "हाँ, बोलिए।"})
        await self.page.receive_json()               # status: speaking

        # 6400 bytes of fake TTS = two 3200-byte chunks. `speak` must not be
        # reported until the pacer has flushed both.
        for _ in range(2):
            media = await ws.receive_json()
            self.assertEqual(media["event"], "media")
            self.assertEqual(len(base64.b64decode(media["media"]["payload"])), 3200)
        self.assertEqual((await self.page.receive_json())["type"], "speak")
        await ws.close()

    async def test_ending_the_call_hangs_up_the_line(self):
        ws = await self._carrier()
        await self.page.receive_json()               # carrier live
        with tempfile.TemporaryDirectory() as tmp, \
             patch.object(server, "CACHE", Path(tmp) / "cache"), \
             patch.object(exotel, "hangup_request", return_value=None):
            await self.page.send_json({"type": "end_call", "lang": "hi"})
            frames = []
            for _ in range(4):
                frame = await self.page.receive_json()
                frames.append(frame["type"])
                if frame["type"] == "summary":
                    break
        self.assertIn("carrier", frames)
        self.assertIn("summary", frames)
        self.assertTrue(FakeCarrierMic.instances[-1].stopped)
        await ws.close()

    async def test_the_caller_hanging_up_returns_the_room_mic(self):
        ws = await self._carrier()
        await self.page.receive_json()               # carrier live
        await ws.send_json({"event": "stop"})
        self.assertEqual(await self.page.receive_json(),
                         {"type": "carrier", "state": "ended"})
        for _ in range(100):                         # the room is back
            if len(FakeMic.instances) >= 3 and FakeMic.instances[-1].started:
                break
            await asyncio.sleep(0.01)
        self.assertTrue(FakeMic.instances[-1].started)
        self.assertTrue(FakeCarrierMic.instances[-1].stopped)


if __name__ == "__main__":
    unittest.main()
