"""Microphone (or the page's microphone) -> Prisma -> callback, per websocket.

The frame rules are the whole difficulty: exactly 1024 bytes, s16le mono, real
time cadence. Everything else is bookkeeping.

Two transports feed the same rules. `MicSession` reads a `sounddevice` mic on
this machine — the demo path. `BrowserMic` is fed whole 1024-byte frames by the
page in talk mode, where the phone is the microphone and the speaker
(`DECISIONS.md` D-004, amended). Both hand Prisma the same frame every 32 ms.
"""
import asyncio
import json

import websockets

from gnani import KEY
from harness.phone_line import PhoneLine

URL = "wss://api.vachana.ai/stt/v3/stream"
BLOCK = 512                  # 512 samples * 2 bytes = 1024 bytes
FRAME_BYTES = BLOCK * 2
# The page starts sending before its Prisma socket has finished its handshake
# (~2 s on the Exotel trial), so the browser queue holds a few seconds of audio.
# It is bounded: past that, cadence matters more than a lost frame.
BROWSER_QUEUE_FRAMES = 128


def headers(lang="indic-auto", rate=16000, telephony=False):
    vad = ({"x-vad-threshold": "0.72", "x-min-silence-ms": "450",
            "x-min-speech-ms": "200", "x-min-segment-ms": "200"} if telephony else
           {"x-vad-threshold": "0.55", "x-min-silence-ms": "350",
            "x-min-speech-ms": "100", "x-min-segment-ms": "120"})
    return {
        "x-api-key-id": KEY,
        "model": "prisma-v3.0",
        "language_code": lang,
        "format": "transcribe",
        "x-sample-rate": str(rate),
        "x-max-speech-s": "15",
        "keyterms": json.dumps(["पश्यन्ती", "divya"], ensure_ascii=True),
        **vad,
    }


async def _connect(hdr):
    for kw in ({"additional_headers": hdr}, {"extra_headers": hdr}):
        try:
            return await websockets.connect(URL, **kw)
        except TypeError:
            continue
    raise RuntimeError("unsupported websockets version")


async def _open_prisma(lang, rate, telephony):
    """One Prisma socket, past its `connected` frame. Shared by both mics."""
    ws = await _connect(headers(lang, rate, telephony))
    await ws.recv()          # {"type":"connected", ...}
    return ws


async def _read_transcripts(ws, on_text, stop):
    """Hand every final transcript to `on_text` until the socket ends."""
    async for msg in ws:
        if stop.is_set():
            break
        d = json.loads(msg)
        if d.get("type") == "transcript" and d.get("text"):
            await on_text(
                d["text"],
                d.get("detected_language_code"),
                int(d.get("latency") or 0),
                int(d.get("audio_duration_ms") or 0),
            )


class FrameParser:
    """Whatever the socket delivered -> whole 1024-byte Prisma frames.

    The page sends whole frames, but a websocket may split or coalesce a send,
    and a client bug can put two frames in one message. Buffering the bytes and
    yielding only complete frames means a partial frame never reaches Prisma and
    a short frame is never silently padded into the middle of the stream.
    The leftover is always under one frame, so this cannot grow without bound.
    """

    def __init__(self, size=FRAME_BYTES):
        self.size = size
        self._buf = bytearray()

    def feed(self, data: bytes) -> list[bytes]:
        self._buf.extend(data)
        out = []
        while len(self._buf) >= self.size:
            out.append(bytes(self._buf[:self.size]))
            del self._buf[:self.size]
        return out

    @property
    def pending(self) -> int:
        return len(self._buf)

    def reset(self):
        self._buf.clear()


def looks_unusable(text: str, audio_ms: int) -> bool:
    """True when a transcript is more likely a guess than a sentence.

    Three tells: no text, no words (punctuation only), or more words than the
    audio could hold. The last one catches Prisma inventing a sentence from
    noise — showing that to a deaf user is worse than asking them to repeat.
    """
    flat = (text or "").strip()
    if len(flat) <= 1:
        return True
    if not any(ch.isalnum() for ch in flat):
        return True
    return len(flat.split()) >= 4 and audio_ms < 400


class MicSession:
    """One microphone, one socket, one callback per sentence."""

    def __init__(self, on_text, lang="indic-auto", rate=16000, telephony=False):
        self.on_text = on_text
        self.lang = lang
        self.rate = rate                  # capture rate
        self.telephony = telephony
        # A phone line is narrower: capture stays 16 kHz, the socket asks for
        # 8 kHz, and every frame goes through the streaming transform.
        self.send_rate = 8000 if telephony else rate
        self.phone = (PhoneLine(in_rate=rate, snr_db=10.0)
                      if telephony and rate != 8000 else None)
        self._task = None
        self._stop = asyncio.Event()
        # While we speak, the microphone hears our own speaker. Send silence
        # instead of audio so the app never transcribes itself.
        self.muted = False

    def available(self):
        """True only if PortAudio initialises *and* has an input device."""
        try:
            import sounddevice as sd

            sd.query_devices(kind="input")
            return True
        except Exception:
            return False

    async def start(self):
        self._task = asyncio.create_task(self._run())

    async def stop(self):
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

    async def _run(self):
        import sounddevice as sd

        loop = asyncio.get_running_loop()
        queue: asyncio.Queue[bytes] = asyncio.Queue()

        def on_audio(indata, frames, time_info, status):
            loop.call_soon_threadsafe(queue.put_nowait, bytes(indata))

        ws = await _open_prisma(self.lang, self.send_rate, self.telephony)

        with sd.RawInputStream(samplerate=self.rate, channels=1, dtype="int16",
                               blocksize=BLOCK, callback=on_audio):
            silence = b"\x00" * FRAME_BYTES

            async def pump():
                while not self._stop.is_set():
                    frame = await queue.get()
                    if self.muted:
                        frame = silence
                    if self.phone is None:
                        await ws.send(frame)
                    else:
                        for out in self.phone.process(frame):
                            await ws.send(out)
                    await asyncio.sleep(BLOCK / self.rate)

            pump_task = asyncio.create_task(pump())
            try:
                await _read_transcripts(ws, self.on_text, self._stop)
            finally:
                pump_task.cancel()
                await ws.close()


class BrowserMic:
    """A Prisma session fed by the page instead of a device.

    Talk mode (`?mode=talk`) puts the microphone on the phone: the page captures
    16 kHz mono s16le, sends whole 1024-byte frames, and this forwards them at
    real-time cadence. There is no `sounddevice` here at all, so a headless or
    remote server works and the laptop is not the audio I/O.

    Cadence is re-created rather than inherited: a frame is sent every 32 ms
    from a bounded queue, silence fills a gap, and a burst on the wire never
    becomes a burst at Prisma. While `muted` (we are speaking) every frame is
    replaced by silence — the server half of D-005; the page mutes its own
    capture for the same window so the phone never hears itself.
    """

    def __init__(self, on_text, lang="indic-auto", rate=16000, telephony=False):
        self.on_text = on_text
        self.lang = lang
        self.rate = rate
        self.telephony = telephony
        self.send_rate = 8000 if telephony else rate
        self.phone = (PhoneLine(in_rate=rate, snr_db=10.0)
                      if telephony and rate != 8000 else None)
        self.parser = FrameParser()
        self.muted = False
        self.frames_in = 0           # whole frames the page delivered
        self.frames_out = 0          # frames actually sent to Prisma
        self.gaps = 0                # 32 ms ticks with no frame to send
        self._queue: asyncio.Queue[bytes] = asyncio.Queue(
            maxsize=BROWSER_QUEUE_FRAMES)
        self._task = None
        self._stop = asyncio.Event()

    def available(self):
        """The page provides the device, so there is nothing to probe here."""
        return True

    async def start(self):
        self._task = asyncio.create_task(self._run())

    async def stop(self):
        self._stop.set()
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):
                pass

    async def feed(self, data: bytes):
        """Accept bytes from the page; only whole frames are queued."""
        for frame in self.parser.feed(data):
            self.frames_in += 1
            if self._queue.full():
                try:
                    self._queue.get_nowait()      # drop the oldest, keep time
                except asyncio.QueueEmpty:
                    pass
            self._queue.put_nowait(frame)

    async def _run(self):
        ws = await _open_prisma(self.lang, self.send_rate, self.telephony)
        pump_task = asyncio.create_task(self._pump(ws))
        try:
            await _read_transcripts(ws, self.on_text, self._stop)
        finally:
            pump_task.cancel()
            await ws.close()

    async def _pump(self, ws):
        loop = asyncio.get_running_loop()
        period = BLOCK / self.rate          # 32 ms of captured audio per frame
        silence = b"\x00" * FRAME_BYTES
        while not self._stop.is_set():
            try:
                frame = self._queue.get_nowait()
            except asyncio.QueueEmpty:
                frame = silence
                self.gaps += 1
            if self.muted:
                frame = silence

            if self.phone is None:
                sent_at = loop.time()
                await ws.send(frame)
                self.frames_out += 1
            else:
                sent_at = loop.time()
                for out in self.phone.process(frame):
                    await ws.send(out)
                    self.frames_out += 1

            next_at = sent_at + period
            delay = next_at - loop.time()
            if delay > 0:
                await asyncio.sleep(delay)

