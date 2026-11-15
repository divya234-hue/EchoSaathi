"""Talk mode: the page's frames -> Prisma, with no browser and no network.

The Prisma socket is a stub that records what it was sent and when it was sent,
so the two rules that matter are asserted directly: every frame is exactly 1024
bytes, and frames leave at real-time cadence — never in a burst, even when the
page hands over a backlog. `BrowserMic.feed` is the same call `Call.on_audio`
makes from a binary websocket frame.
"""
import asyncio
import os
import sys
import unittest
from unittest.mock import patch

os.environ.setdefault("GNANI_API_KEY", "test-key-not-used")

import stt  # noqa: E402

FRAME = b"\x01\x02" * 512          # 1024 bytes, distinguishable from silence
SILENCE = b"\x00" * 1024


class FrameParserTest(unittest.TestCase):
    def test_whole_frames_pass_straight_through(self):
        parser = stt.FrameParser()
        self.assertEqual(parser.feed(FRAME), [FRAME])
        self.assertEqual(parser.pending, 0)

    def test_two_frames_in_one_send_become_two(self):
        parser = stt.FrameParser()
        self.assertEqual(parser.feed(FRAME + FRAME), [FRAME, FRAME])

    def test_a_split_frame_is_held_then_joined(self):
        parser = stt.FrameParser()
        self.assertEqual(parser.feed(FRAME[:700]), [])
        self.assertEqual(parser.pending, 700)
        self.assertEqual(parser.feed(FRAME[700:]), [FRAME])
        self.assertEqual(parser.pending, 0)

    def test_the_leftover_is_always_under_one_frame(self):
        parser = stt.FrameParser()
        parser.feed(FRAME + FRAME[:123])
        self.assertEqual(parser.pending, 123)
        self.assertLess(parser.pending, stt.FRAME_BYTES)

    def test_reset_drops_a_partial_frame(self):
        parser = stt.FrameParser()
        parser.feed(FRAME[:400])
        parser.reset()
        self.assertEqual(parser.pending, 0)
        self.assertEqual(parser.feed(FRAME[:100]), [])


class FakePrisma:
    """The websocket Prisma answers on, with send times recorded."""

    def __init__(self):
        self.sent: list[tuple[float, bytes]] = []
        self.closed = False

    async def send(self, frame):
        self.sent.append((asyncio.get_running_loop().time(), bytes(frame)))
        if hasattr(self, "tenth_send") and len(self.sent) >= 10:
            self.tenth_send.set()

    async def close(self):
        self.closed = True


class BrowserMicTest(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.prisma = FakePrisma()
        self.stop_read = asyncio.Event()

        async def fake_open(lang, rate, telephony):
            self.opened_with = (lang, rate, telephony)
            return self.prisma

        async def fake_read(ws, on_text, stop):
            await self.stop_read.wait()          # the pump is what is under test

        self._patches = [
            patch.object(stt, "_open_prisma", fake_open),
            patch.object(stt, "_read_transcripts", fake_read),
        ]
        for p in self._patches:
            p.start()

    async def asyncTearDown(self):
        self.stop_read.set()
        for p in reversed(self._patches):
            p.stop()

    async def _mic(self, **kwargs):
        mic = stt.BrowserMic(lambda *a: None, **kwargs)
        self.addAsyncCleanup(mic.stop)
        return mic

    # --- frame discipline ------------------------------------------------

    async def test_frames_are_forwarded_exactly_as_sent(self):
        mic = await self._mic()
        for _ in range(6):
            await mic.feed(FRAME)
        await mic.start()
        await asyncio.sleep(6 * 0.032 + 0.1)
        await mic.stop()

        sent = [frame for _, frame in self.prisma.sent]
        self.assertEqual(sent[:6], [FRAME] * 6)
        self.assertTrue(all(len(frame) == 1024 for frame in sent))
        self.assertEqual(mic.frames_in, 6)
        self.assertGreaterEqual(mic.frames_out, 6)

    async def test_cadence_is_never_a_burst(self):
        mic = await self._mic()
        self.prisma.tenth_send = asyncio.Event()
        for _ in range(10):
            await mic.feed(FRAME)
        await mic.start()
        await asyncio.wait_for(self.prisma.tenth_send.wait(), timeout=2)
        await mic.stop()

        times = [t for t, _ in self.prisma.sent[:10]]
        self.assertEqual(len(times), 10)
        gaps = [b - a for a, b in zip(times, times[1:])]
        # 32 ms apart with scheduling slack. The floor is the rule: a burst
        # would put two frames in ~0 ms and degrade Prisma's VAD.
        self.assertGreaterEqual(min(gaps), 0.020, f"burst detected: {gaps}")
        self.assertLess(max(gaps), 0.150, f"stalled pump: {gaps}")

    async def test_a_backlog_is_not_burst_into_prisma(self):
        mic = await self._mic()
        for _ in range(500):                     # ~16 s of audio in one go
            await mic.feed(FRAME)
        self.assertEqual(mic.frames_in, 500)
        self.assertLessEqual(mic._queue.qsize(), stt.BROWSER_QUEUE_FRAMES)
        await mic.start()
        await asyncio.sleep(0.12)
        await mic.stop()

        times = [t for t, _ in self.prisma.sent]
        gaps = [b - a for a, b in zip(times, times[1:])]
        self.assertGreaterEqual(min(gaps), 0.020, f"burst detected: {gaps}")
        self.assertLess(len(times), 20)          # paced, not flooded

    async def test_silence_fills_the_gap_so_prisma_keeps_its_clock(self):
        mic = await self._mic()
        await mic.feed(FRAME)
        await mic.start()
        await asyncio.sleep(4 * 0.032)
        await mic.stop()

        sent = [frame for _, frame in self.prisma.sent]
        self.assertEqual(sent[0], FRAME)
        self.assertTrue(all(frame == SILENCE for frame in sent[1:]))
        self.assertGreaterEqual(mic.gaps, 1)

    async def test_muted_forwards_silence_instead_of_the_room(self):
        """Half-duplex on the server side: we speak, so the room is not sent."""
        mic = await self._mic()
        await mic.feed(FRAME)
        mic.muted = True
        await mic.start()
        await asyncio.sleep(2 * 0.032 + 0.02)
        await mic.stop()

        self.assertTrue(self.prisma.sent)
        self.assertTrue(all(frame == SILENCE for _, frame in self.prisma.sent))

    async def test_a_partial_frame_never_reaches_prisma(self):
        mic = await self._mic()
        await mic.feed(FRAME[:300])
        await mic.start()
        await asyncio.sleep(2 * 0.032 + 0.02)
        await mic.stop()

        self.assertEqual([frame for _, frame in self.prisma.sent], [SILENCE] * len(self.prisma.sent))
        self.assertEqual(mic.frames_in, 0)

    async def test_the_normal_laptop_vad_preset_is_used(self):
        mic = await self._mic()
        await mic.feed(FRAME)
        await mic.start()
        await asyncio.sleep(0.05)
        await mic.stop()

        lang, rate, telephony = self.opened_with
        self.assertEqual(lang, "indic-auto")
        self.assertEqual(rate, 16000)
        self.assertFalse(telephony)

    async def test_it_does_not_touch_sounddevice(self):
        """The whole point of talk mode: no device on this machine."""
        mic = await self._mic()
        await mic.feed(FRAME)
        await mic.start()
        await asyncio.sleep(0.05)
        await mic.stop()
        self.assertNotIn("sounddevice", sys.modules)


class BrowserMicPhoneLineTest(unittest.IsolatedAsyncioTestCase):
    """The demo switch keeps working: two 16 kHz frames become one 8 kHz frame."""

    async def test_telephony_halves_the_rate_and_keeps_1024_byte_frames(self):
        prisma = FakePrisma()
        stop_read = asyncio.Event()

        async def fake_open(lang, rate, telephony):
            self.assertEqual(rate, 8000)
            self.assertTrue(telephony)
            return prisma

        async def fake_read(ws, on_text, stop):
            await stop_read.wait()

        with patch.object(stt, "_open_prisma", fake_open), \
             patch.object(stt, "_read_transcripts", fake_read):
            mic = stt.BrowserMic(lambda *a: None, telephony=True)
            try:
                for _ in range(4):
                    await mic.feed(FRAME)
                await mic.start()
                await asyncio.sleep(4 * 0.032 + 0.05)
            finally:
                stop_read.set()
                await mic.stop()

        sent = [frame for _, frame in prisma.sent]
        self.assertTrue(sent)
        self.assertTrue(all(len(frame) == 1024 for frame in sent))
        # two input frames per output frame, so fewer frames leave than arrive
        self.assertLessEqual(len(sent), mic.frames_out)


if __name__ == "__main__":
    unittest.main()
