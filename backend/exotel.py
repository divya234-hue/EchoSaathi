"""A real phone call: Exotel AgentStream in, Prisma/Timbre in the middle.

This is the **pilot** leg, behind `EXOTEL_WS_TOKEN`. Without that variable the
route answers 503 and nothing changes, which is why the demo path and the
60-second video are unaffected (D-014 amendment, `docs/EXOTEL-BRIDGE.md`).

Exotel's Voicebot applet opens one websocket per inbound call:

    wss://<public-host>/exotel/ws?token=<EXOTEL_WS_TOKEN>&sample-rate=8000
    wss://<public-host>/exotel/ws/<EXOTEL_WS_TOKEN>          (or in the path)

Events from Exotel: `connected`, `start`, `media`, `mark`, `dtmf`, `stop`.
Audio both ways: base64 raw PCM, 16-bit signed little-endian, mono, 8 kHz.

The call is attached to one page (`bind_page`), because this build has no
accounts: the most recently connected page is the user whose call it is. A
second simultaneous carrier call is refused rather than mixed into the first.

What is verified: the protocol below was tested against a **real Indian trial
call on 14 Nov** by the spike this module comes from (see EXOTEL-SPIKE.md), the
framing/parsing is covered by tests with a simulated Exotel client, and this
module itself ran a live call on 15 Nov: the masked caller reached the page, the
`start` event carried a call SID, the reply was heard without gaps, and the
hangup answered `200` with the handset dropping. What is **not** verified:
multi-user routing, and the two WAN latency legs.
"""
from __future__ import annotations

import asyncio
import base64
import hmac
import json
import os
import time

from aiohttp import WSMsgType, web

import chips
import tts
from stt import BrowserMic, FrameParser

RATE = 8000                      # Exotel's sample rate for a voice call
FRAME = 1024                     # what Prisma takes at 8 kHz: 64 ms
OUT_CHUNK = 3200                 # 200 ms outbound, the shape the trial used
OUT_PERIOD = OUT_CHUNK / (RATE * 2)   # 0.2 s: the play time of one chunk
PREFILL = 6400                   # 400 ms of audio before the first frame
MAX_BUFFERED = RATE            # 1 s of inbound audio; older chunks are dropped
WS_TOKEN = "EXOTEL_WS_TOKEN"

# The page this build shows the call on. One call, one page (no accounts).
_page = None
_live = False


def enabled() -> bool:
    """The bridge is opt-in: no token in the environment, no route."""
    return bool(os.environ.get(WS_TOKEN))


def token_ok(value: str | None) -> bool:
    expected = os.environ.get(WS_TOKEN, "")
    return bool(expected) and hmac.compare_digest(value or "", expected)


def bind_page(call) -> None:
    global _page
    _page = call


def unbind_page(call) -> None:
    global _page
    if _page is call:
        _page = None


def page():
    return _page


def busy() -> bool:
    return _live


def mask_number(value: str | None) -> str:
    """Last four digits only: a real number never reaches the page or a log."""
    digits = "".join(ch for ch in (value or "") if ch.isdigit())
    return f"••••{digits[-4:]}" if len(digits) >= 4 else "••••"


def media_pcm(payload: str | None) -> bytes | None:
    """One Exotel media payload -> PCM bytes, or None if it is not base64."""
    if not payload:
        return None
    try:
        pcm = base64.b64decode(payload, validate=True)
    except (ValueError, TypeError):
        return None
    return pcm or None


def out_chunks(pcm: bytes, size: int = OUT_CHUNK) -> list[bytes]:
    """Pad the tail to one Exotel chunk: the trial's sender expected 3200 B."""
    chunks = [pcm[i:i + size] for i in range(0, len(pcm), size)]
    if chunks and len(chunks[-1]) < size:
        chunks[-1] += b"\x00" * (size - len(chunks[-1]))
    return chunks


def start_fields(event: dict) -> dict:
    start = event.get("start") or {}
    return {
        "sid": (event.get("stream_sid") or event.get("streamSid")
                or start.get("stream_sid") or start.get("streamSid") or ""),
        # The REST API addresses the call by its call SID. Ending the line with
        # the stream SID is a hard 403, so the two ids are kept apart.
        "call_sid": (start.get("call_sid") or start.get("callSid")
                     or event.get("call_sid") or ""),
        "account_sid": (start.get("account_sid") or start.get("accountSid")
                        or event.get("account_sid") or ""),
        "from": start.get("from") or "",
        "to": start.get("to") or "",
    }


def api_host(subdomain: str) -> str:
    """`api` and `api.exotel.com` both mean the same host.

    The console shows the subdomain; pasting the whole hostname is the obvious
    mistake, and the doubled-domain URL is a 404 that looks like a bad key.
    """
    value = (subdomain or "").strip().rstrip("/")
    return value if "." in value else f"{value}.exotel.com"


def hangup_request(call_sid: str, account_sid: str = "") -> tuple[str, dict] | None:
    """Exotel's hangup: POST the call resource's `/Hangup`, or None when unset.

    Measured against the live API on 15 Nov: `POST .../Calls/{call_sid}` answers
    `403 Method not allowed` and `PUT` answers `405 Method not available`, while
    `POST .../Calls/{call_sid}/Hangup` answers `200 Hangup Successful`. The id is
    the **call SID** from the stream's `start` event; the stream SID is a
    different id and cannot end the line.
    """
    account = account_sid or os.environ.get("EXOTEL_ACCOUNT_SID")
    subdomain = os.environ.get("EXOTEL_SUBDOMAIN")
    path = os.environ.get("EXOTEL_HANGUP_PATH",
                          "/v1/Accounts/{account}/Calls/{sid}/Hangup")
    if not (call_sid and account and subdomain):
        return None
    return (f"https://{api_host(subdomain)}"
            + path.format(account=account, sid=call_sid)), {"Status": "completed"}


class CarrierCall:
    """One inbound call: carrier media -> Prisma, the page's replies -> carrier."""

    def __init__(self, ws: web.WebSocketResponse):
        self.ws = ws
        self.sid = ""              # the stream SID: what outbound media carries
        self.call_sid = ""         # the call SID: what the REST hangup needs
        self.account_sid = ""
        self.started_at = time.monotonic()
        self.mic: BrowserMic | None = None
        self.parser = FrameParser()
        self.in_bytes = 0
        self.out_bytes = 0
        self.closed = False
        self.muted = False
        self._out: asyncio.Queue[bytes | None] = asyncio.Queue()
        self._drained = asyncio.Event()
        self._drained.set()
        self._tasks: list[asyncio.Task] = []
        self._speaking = asyncio.Lock()

    # --- Exotel -> us ----------------------------------------------------

    async def run(self):
        global _live
        _live = True
        self._tasks.append(asyncio.create_task(self._pacer()))
        try:
            async for msg in self.ws:
                if msg.type is not WSMsgType.TEXT:
                    continue
                try:
                    event = json.loads(msg.data)
                except json.JSONDecodeError:
                    continue
                kind = event.get("event")
                if kind == "start":
                    await self.on_start(event)
                elif kind == "media":
                    await self.on_media(event)
                elif kind == "stop":
                    break
        finally:
            await self.close()

    async def on_start(self, event: dict):
        fields = start_fields(event)
        self.sid = fields["sid"]
        self.call_sid = fields["call_sid"]
        self.account_sid = fields["account_sid"]
        if self.mic is None:
            self.mic = BrowserMic(self._on_transcript, rate=RATE,
                                  telephony=True)
            await self.mic.start()
        target = page()
        if target is not None:
            await target.attach_carrier(self)
            await target.send({"type": "carrier", "state": "live",
                               "from": mask_number(fields["from"])})
        # Masked, never the number itself: this line is what says whether the
        # start event carried a caller and a call SID at all.
        print(f"carrier call live: from={mask_number(fields['from'])} "
              f"call_sid={'yes' if self.call_sid else 'MISSING'}")

    async def on_media(self, event: dict):
        pcm = media_pcm((event.get("media") or {}).get("payload"))
        if not pcm or self.mic is None:
            return
        self.in_bytes += len(pcm)
        for frame in self.parser.feed(pcm):
            await self.mic.feed(frame)

    async def _on_transcript(self, text, lang, latency_ms, audio_ms):
        # The caller's language is known from the first transcript, which is a
        # few seconds before the user can type a reply: enough time to buy the
        # acknowledgement, so the first reply already has an instant first word.
        if lang:
            phrase = chips.ack(lang)
            if not tts.is_cached(phrase, lang):
                asyncio.create_task(self._warm_ack(phrase, lang))
        target = page()
        if target is not None and not target.ended:
            await target.on_transcript(text, lang, latency_ms, audio_ms)

    # --- us -> Exotel ----------------------------------------------------

    async def _send_media(self, payload_b64: str) -> bool:
        if not self.sid or self.ws.closed:
            return False
        try:
            await self.ws.send_json({"event": "media", "stream_sid": self.sid,
                                     "media": {"payload": payload_b64}})
            return True
        except ConnectionError:
            return False

    async def _pacer(self):
        """One 3200-byte chunk every 200 ms, on a deadline, as the trial did.

        Sleeping a fixed 200 ms *after* each send makes the real cadence
        send-time + 200 ms, which slowly underruns the carrier's buffer and
        makes the reply break up. The schedule is absolute instead: chunk *n*
        goes at t0 + n*200 ms. A gap longer than one chunk (the latency before
        the first audio) resyncs rather than bursting to catch up.
        """
        loop = asyncio.get_running_loop()
        next_at: float | None = None
        while not self.closed:
            chunk = await self._out.get()
            if chunk is None:
                return
            self._drained.clear()
            now = loop.time()
            if next_at is None or now - next_at > OUT_PERIOD:
                next_at = now
            await asyncio.sleep(max(0.0, next_at - now))
            try:
                await self._send_media(base64.b64encode(chunk).decode("ascii"))
                self.out_bytes += len(chunk)
            finally:
                if self._out.empty():
                    self._drained.set()
            next_at += OUT_PERIOD

    def _queue_ack(self, lang: str) -> int:
        """Queue the cached acknowledgement; return the bytes queued (0 if none).

        Reads straight from the clip cache — a synthesis here would defeat the
        point. When the clip is missing this fires a background synthesis so the
        *next* reply has one, and this reply goes out unchanged.
        """
        phrase = chips.ack(lang)
        try:
            with open(tts.cached_path(phrase, lang), "rb") as f:
                pcm = f.read()
        except OSError:
            asyncio.create_task(self._warm_ack(phrase, lang))
            return 0
        queued_bytes = 0
        for piece in out_chunks(pcm, OUT_CHUNK):
            self._out.put_nowait(piece)
            queued_bytes += len(piece)
        return queued_bytes

    async def _warm_ack(self, phrase: str, lang: str):
        try:
            await tts.warm(phrase, lang, rate=RATE)
        except Exception:                 # noqa: BLE001 (an extra, never fatal)
            pass

    async def speak(self, text: str, lang: str):
        """Speak the page's reply down the line. -> (ttfa_ms, cached).

        The carrier microphone is muted from the first audio until the last of
        it has played, so the caller's phone echoing Timbre back is never
        transcribed (D-005, carrier version). It is not muted during synthesis:
        a reply can take seconds to start, and the caller should not go deaf
        while the model thinks.
        """
        async with self._speaking:
            # Clear before enqueuing: an `emit` can fill the whole queue without
            # yielding, so a pre-set event would claim the audio had played.
            self._drained.clear()
            buf = bytearray()
            started = False
            queued = 0

            async def emit(chunk: bytes):
                nonlocal started, queued
                if not started:
                    started = True
                    # Mute when audio is actually queued, not before: Timbre can
                    # take seconds, and muting through the whole generation cuts
                    # off whatever the caller says while it thinks.
                    if self.mic:
                        self.mic.muted = True
                # Carry the remainder across streamed chunks. Padding each one
                # to 3200 bytes with `out_chunks` would insert a silence gap
                # whenever the model's chunk size is not a multiple of it, and
                # that is what made the reply stutter on the handset.
                buf.extend(chunk)
                while len(buf) >= OUT_CHUNK:
                    self._out.put_nowait(bytes(buf[:OUT_CHUNK]))
                    del buf[:OUT_CHUNK]
                    queued += OUT_CHUNK

            # A one-word acknowledgement goes out first when it is already
            # cached and the reply itself is not: the pacer plays it while the
            # reply is still being synthesised, so the caller hears something in
            # ~0.3 s instead of 1.5-7 s of silence.
            acked = 0
            if not tts.is_cached(text, lang):
                acked = self._queue_ack(lang)
                queued += acked

            try:
                ttfa, cached = await tts.stream_pcm(text, emit, rate=RATE,
                                                    lang=lang)
                if buf:                  # the only pad: at the true end
                    tail = bytes(buf) + b"\x00" * (OUT_CHUNK - len(buf))
                    self._out.put_nowait(tail)
                    queued += OUT_CHUNK
                if not self._out.empty():
                    self._drained.clear()    # a stale "drained" must not shortcut
                # Let the pacer finish what is queued before unmuting.
                try:
                    await asyncio.wait_for(self._drained.wait(), timeout=30)
                except asyncio.TimeoutError:
                    pass
            except Exception as exc:          # noqa: BLE001 (surfaced to caller)
                print(f"carrier reply failed: {type(exc).__name__}: "
                      f"{str(exc)[:120]}")
                raise
            finally:
                if self.mic:
                    self.mic.muted = False
            print(f"carrier reply: ttfa={ttfa}ms cached={cached} "
                  f"ack={'yes' if acked else 'no'} "
                  f"audio={queued / (RATE * 2):.1f}s")
            return ttfa, cached

    async def hangup(self) -> bool:
        """End the call: Exotel REST hangup, then close the socket.

        Returns whether the carrier acknowledged. A refusal is printed rather
        than swallowed: "End call did nothing" was a silent 403 (wrong method,
        wrong id) for a whole evening, and the log is the only way to see it on
        a handset. The key never appears — only the status.
        """
        request = hangup_request(self.call_sid, self.account_sid)
        sent = False
        if request is not None:
            url, form = request
            key = os.environ.get("EXOTEL_API_KEY", "")
            token = os.environ.get("EXOTEL_API_TOKEN", "")
            try:
                import requests
                r = await asyncio.to_thread(
                    requests.post, url, data=form, auth=(key, token), timeout=5)
                sent = r.status_code in (200, 201, 202, 204)
                print(f"carrier hangup: call {self.call_sid[-4:].rjust(4, '*')} "
                      f"-> HTTP {r.status_code}")
            except Exception as exc:          # noqa: BLE001  (best effort)
                print(f"carrier hangup failed: {type(exc).__name__}")
        else:
            print("carrier hangup: no call_sid or credentials")
        await self.close()
        return sent

    async def close(self):
        global _live
        if self.closed:
            return
        self.closed = True
        _live = False
        self._drained.set()        # unblock a `speak` waiting on the pacer
        self._out.put_nowait(None)
        for task in self._tasks:
            task.cancel()
        if self.mic is not None:
            await self.mic.stop()
            self.mic = None
        target = page()
        if target is not None:
            await target.detach_carrier(self)
        try:
            await self.ws.close()
        except ConnectionError:
            pass


def request_token(request) -> str | None:
    """The bridge secret, from the query string or the path.

    Exotel's Voicebot applet stores one URL and some consoles drop its query
    string when the applet is saved. The call then arrives as a bare
    `/exotel/ws` and the gate refuses it, which looks exactly like a dead
    bridge from the handset. The path form (`/exotel/ws/<token>`) survives that,
    so both are accepted; the comparison is the same one either way.
    """
    return request.query.get("token") or request.match_info.get("token")


async def ws_handler(request: web.Request):
    """`/exotel/ws` — Exotel only, and only when the token is configured."""
    if not enabled():
        return web.Response(status=503,
                            text="carrier bridge disabled: set EXOTEL_WS_TOKEN")
    if not token_ok(request_token(request)):
        return web.Response(status=403, text="bad carrier token")
    target = page()
    if busy() or target is None or target.ended:
        # No accounts in this build: one call, on a page that is open and still
        # in a call. "New call" is what re-arms the screen for the next one.
        return web.Response(status=409,
                            text="no live page for the call, or a call is live")
    ws = web.WebSocketResponse(heartbeat=30, max_msg_size=8 * 1024 * 1024)
    await ws.prepare(request)
    call = CarrierCall(ws)
    await call.run()
    return ws
