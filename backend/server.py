"""Pashyanti server: one process, one port.

Serves the built React app, owns the microphone (or relays the page's), and
relays Gnani calls.

    cd pashyanti/backend
    uv run python server.py          # http://localhost:8080
    uv run python server.py --tls cert.pem key.pem   # https:// (talk mode off-LAN)

Talk mode (`?mode=talk`) reverses D-004: the page captures 16 kHz PCM in an
AudioWorklet, sends 1024-byte frames over /ws, and plays Timbre's reply itself.
That path needs a secure context (HTTPS or localhost) for `getUserMedia`.

Development (hot reload) runs Vite separately:
    cd pashyanti/web && bun run dev  # http://localhost:5173, proxies /ws here
"""
import asyncio
import base64
import json
import os
import ssl
import sys
import time
from pathlib import Path

from aiohttp import WSMsgType, web

import chips
import exotel
import llm
import tts
from gnani import KEY  # noqa: F401  (import validates the key early)
from stt import BrowserMic, MicSession, looks_unusable

WEB = Path(__file__).resolve().parent.parent / "web" / "dist"
CACHE = Path(__file__).resolve().parent / "cache"
PORT = int(os.environ.get("PORT", "8080"))
SUMMARY_CHARS = 60
MODE_SERVER = "server"
MODE_TALK = "talk"
# The chips are an extra, never a dependency: the page already has static chips,
# so a slow model may not hold the call open.
SUGGEST_TIMEOUT = 6.0
CONTEXT_LINES = 3
# The card is already on screen before this starts; a slow model just means the
# extractive card is the one the user keeps.
SUMMARY_LLM_TIMEOUT = 8.0


def _phone_line_enabled(argv=None, env=None):
    """--phone-line on the command line, or PHONE_LINE=1 in the environment."""
    argv = sys.argv[1:] if argv is None else argv
    env = os.environ if env is None else env
    return "--phone-line" in argv or env.get("PHONE_LINE") == "1"


PHONE_LINE = _phone_line_enabled()


def _summary_llm_enabled(env=None):
    """SUMMARY_LLM=0 keeps the card purely extractive (the demo's safe switch)."""
    env = os.environ if env is None else env
    return env.get("SUMMARY_LLM", "1") != "0"


SUMMARY_LLM = _summary_llm_enabled()

NO_BUILD = """<!doctype html><meta charset=utf-8><body style="font:16px system-ui;
padding:40px;background:#0f1115;color:#eef1f6">
<h2>Pashyanti</h2><p>Frontend not built yet.</p>
<pre>cd pashyanti/web &amp;&amp; bun run build</pre>
<p>Or run the dev server: <code>bun run dev</code> → http://localhost:5173</p>
"""


def _shorten(text: str, limit: int = SUMMARY_CHARS) -> str:
    """One flat line, at most `limit` characters, ellipsis included."""
    flat = " ".join(text.split())
    if len(flat) <= limit:
        return flat
    return flat[: limit - 1].rstrip() + "…"


def build_summary(lines: list[dict], started_at: float, ended_at: float) -> dict:
    """The first, instant end-of-call card, computed from the transcript alone.

    No model call: the same call always yields the same card, so it is safe to
    write and re-read after a reload, and it is the fallback if the rewrite
    never comes. `Call.end_call` sends this one before asking the model for a
    better `who/agreed/next`.
    """
    caller = [str(ln.get("text") or "").strip()
              for ln in lines if ln.get("who") == "caller"]
    mine = [str(ln.get("text") or "").strip()
            for ln in lines if ln.get("who") == "me"]
    return {
        "who": _shorten(caller[0]) if caller and caller[0] else "unknown caller",
        "agreed": caller[-1] if caller and caller[-1] else "—",
        "next": mine[-1] if mine and mine[-1] else "no reply yet",
        "turns": len(caller),
        "duration_s": max(0, int(round(ended_at - started_at))),
    }


def merge_summary(base: dict, better: dict | None) -> dict:
    """The model's non-empty fields over the extractive card.

    A field the model left empty keeps the deterministic value: a blank 'who'
    would be worse than the first caller line.
    """
    merged = dict(base)
    for key in ("who", "agreed", "next"):
        value = (better or {}).get(key)
        if isinstance(value, str) and value.strip():
            merged[key] = value.strip()
    return merged


def write_summary(summary: dict) -> Path:
    """Persist the card so a reload still has one to show."""
    CACHE.mkdir(parents=True, exist_ok=True)
    path = CACHE / "summary.json"
    tmp = path.with_name("summary.json.tmp")
    tmp.write_text(json.dumps(summary, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)
    return path


class Call:
    """One call = one websocket + one Prisma session.

    `mode` is "server" (the demo path: this machine's microphone and speaker)
    or "talk" (the page's microphone and speaker, an in-person conversation).
    """

    def __init__(self, ws: web.WebSocketResponse, mode=MODE_SERVER):
        self.ws = ws
        self.mode = mode
        self.lines: list[dict] = []
        self.started_at = time.time()
        self.speaking = asyncio.Lock()
        self.mic: MicSession | BrowserMic | None = None
        self.voice_mode = tts.MODE_DEFAULT
        self.telephony = PHONE_LINE
        self.last_lang: str | None = None
        self.suggest_task: asyncio.Task | None = None
        self.summary_task: asyncio.Task | None = None
        self.ended = False
        self.call_seq = 0          # bumped by new_call, so a late card cannot land
        self.carrier = None        # an inbound real call, when one is bound

    async def send(self, payload: dict):
        if not self.ws.closed:
            await self.ws.send_json(payload)

    async def set_voice(self, mode: str):
        """Switch this call's voice. Refuses the clone when none was loaded."""
        mode = tts.MODE_CLONED if mode == tts.MODE_CLONED else tts.MODE_DEFAULT
        if mode == tts.MODE_CLONED and not tts.has_clone():
            await self.send({"type": "error",
                             "message": "no cloned voice on this server"})
            return
        self.voice_mode = mode
        await self.send({"type": "voice", "mode": mode})
        # The demo toggle (#21) speaks the older shape; keep it in sync.
        await self.send({"type": "cloned_voice",
                         "enabled": mode == tts.MODE_CLONED})

    async def set_phone_line(self, enabled: bool):
        """Switch the call's microphone transform without touching the page socket.

        The Prisma socket has to be rebuilt because its rate and VAD headers are
        fixed per connection; the websocket to the phone stays open. Audio is
        briefly interrupted, which is the price of a demo switch.
        """
        enabled = bool(enabled)
        if enabled == self.telephony:
            await self.send({"type": "phone_line", "enabled": enabled})
            return
        if self.mic is not None:
            async with self.speaking:     # do not swap the mic mid-utterance
                was_muted = self.mic.muted
                await self.mic.stop()
                self.mic = None
                self.telephony = enabled
                await self.start_mic()
                if self.mic is not None:
                    self.mic.muted = was_muted
        else:
            self.telephony = enabled
        await self.send({"type": "phone_line", "enabled": enabled})

    async def on_transcript(self, text, lang, latency_ms, audio_ms):
        if self.ended:
            return
        if looks_unusable(text, audio_ms):
            await self.send({"type": "retry"})
            return
        self.lines.append({"who": "caller", "text": text})
        self.last_lang = lang or self.last_lang
        await self.send({"type": "transcript", "text": text,
                         "lang": lang, "latency_ms": latency_ms})
        self.offer_suggestions(text, lang)

    @property
    def reply_lang(self) -> str:
        """The language the reply is spoken in: the caller's, not the UI's.

        Recognition reports one language per line (`indic-auto`), so the reply
        follows the person being answered (D-012 amendment).
        """
        return tts.reply_language(self.last_lang)

    def offer_suggestions(self, text: str, lang: str | None):
        """Ask for reply chips in the caller's language, off the message path.

        Nothing is sent when the model is unavailable or slow: the page keeps
        its static locale chips, so a failure changes nothing on screen.
        """
        if not llm.available():
            return
        if self.suggest_task and not self.suggest_task.done():
            self.suggest_task.cancel()          # the latest line wins
        self.suggest_task = asyncio.create_task(self.suggest(text, lang))

    async def suggest(self, text: str, lang: str | None):
        context = [ln["text"] for ln in self.lines
                   if ln.get("who") == "caller"][-CONTEXT_LINES:]
        try:
            answer = await asyncio.wait_for(
                asyncio.to_thread(llm.direct_reply, text, lang, context),
                timeout=SUGGEST_TIMEOUT)
        except Exception:                    # noqa: BLE001  (timeout, network)
            return
        suggested = chips.for_transcript(lang, answer)
        if not suggested:
            return
        try:
            await self.send({"type": "suggest", "chips": suggested,
                             "lang": lang})
        except Exception:              # noqa: BLE001  (the page went away)
            pass

    async def attach_carrier(self, carrier):
        """A real call arrived: its audio is the source, not this room."""
        self.carrier = carrier
        await self.stop_mic()
        self.mic = carrier.mic

    async def detach_carrier(self, carrier):
        """The carrier call ended: back to the room, unless this call is over.

        In talk mode there is no local microphone to reopen, so the page just
        takes the call ended and goes back to its own (gesture-started) capture.
        """
        if self.carrier is carrier:
            self.carrier = None
        if self.mic is carrier.mic:
            self.mic = None
        if self.mode == MODE_SERVER and not self.ended:
            await self.start_mic()
        await self.send({"type": "carrier", "state": "ended"})

    async def on_reply(self, text: str):
        if self.ended:
            return
        async with self.speaking:
            self.lines.append({"who": "me", "text": text})
            await self.send({"type": "status", "state": "speaking"})
            if self.mic:
                self.mic.muted = True
            lang = self.reply_lang
            try:
                if self.carrier is not None:
                    # Down the real line, not the speaker and not the phone.
                    ttfa, cached = await self.carrier.speak(text, lang)
                elif self.mode == MODE_TALK:
                    ttfa, cached = await self.speak_to_page(text, lang)
                else:
                    ttfa, cached = await tts.speak(text, mode=self.voice_mode,
                                                  lang=lang)
                await self.send({"type": "speak", "text": text,
                                 "ttfa_ms": ttfa, "cached": cached,
                                 "lang": lang})
            except Exception as exc:                     # noqa: BLE001
                await self.send({"type": "error", "message": str(exc)[:200]})
            finally:
                if self.mic:
                    self.mic.muted = False
                await self.send({"type": "status", "state": "listening"})

    async def speak_to_page(self, text, lang):
        """Stream the reply to the phone instead of this machine's speaker.

        The page schedules the chunks through Web Audio and mutes its own
        capture until they have played, so the phone never transcribes itself.
        The mic is muted here for the stream window; the page owns the
        playback tail (D-005, both halves).
        """
        async def emit(chunk):
            await self.send({"type": "audio",
                             "data": base64.b64encode(chunk).decode("ascii"),
                             "rate": tts.RATE})

        ttfa, cached = await tts.stream_pcm(text, emit, mode=self.voice_mode,
                                           lang=lang)
        await self.send({"type": "audio", "data": "", "rate": tts.RATE,
                         "final": True})
        return ttfa, cached

    async def on_audio(self, data: bytes):
        """A binary websocket frame is capture audio, in talk mode only."""
        if self.ended:
            return
        if self.mode == MODE_TALK and self.mic is not None:
            await self.mic.feed(data)

    async def start_capture(self):
        """The page pressed "Start listening": open Prisma, then say ready.

        The page sends frames as soon as its own capture starts; they queue
        here while Prisma completes its handshake, so no speech is dropped.
        """
        if self.mode != MODE_TALK:
            await self.send({"type": "capture", "state": "ready"})
            return
        if self.mic is None:
            await self.start_mic()
        await self.send({"type": "capture",
                         "state": "ready" if self.mic else "error"})

    async def end_call(self, lang: str | None = None):
        """End the call for real, then send the card.

        Ending means: the page stops capturing (talk mode is told first), this
        machine's microphone closes, the Prisma socket closes, and nothing that
        arrives afterwards is transcribed or spoken. The card is built from the
        lines up to this moment.

        The extractive card is instant and is the fallback: `build_summary` is a
        pure function over the transcript, so a slow or dead model cannot delay
        it or make it worse. `lang` is the **UI** locale — the card is for the
        user, not for the caller (D-012). There is no telephone line to hang up
        in this build; in talk mode "the call" is the phone's capture, and this
        is what closes it.
        """
        if self.ended:
            return None
        self.ended = True
        seq = self.call_seq
        if self.carrier is not None:
            await self.carrier.hangup()      # the real line, best effort
        if self.mode == MODE_TALK:
            await self.send({"type": "capture", "state": "stopped"})
        await self.stop_mic()
        if self.suggest_task and not self.suggest_task.done():
            self.suggest_task.cancel()
        base = build_summary(self.lines, self.started_at, time.time())
        await self.send({"type": "summary", **base})
        self._write_summary(base)
        if not (SUMMARY_LLM and llm.available()):
            return base
        better = await self.better_summary(lang)
        if seq != self.call_seq:        # a new call started while we waited
            return base
        merged = merge_summary(base, better)
        if merged == base:
            return base
        await self.send({"type": "summary", **merged})
        self._write_summary(merged)
        return merged

    async def new_call(self):
        """Drop this session and start a new one (the card's "New call").

        In server mode the microphone reopens immediately. In talk mode the page
        is told to stop capturing; it needs a fresh tap on "Start listening",
        because `getUserMedia` needs a gesture.
        """
        if self.summary_task and not self.summary_task.done():
            self.summary_task.cancel()
        if self.suggest_task and not self.suggest_task.done():
            self.suggest_task.cancel()
        await self.stop_mic()
        self.call_seq += 1
        self.lines = []
        self.started_at = time.time()
        self.last_lang = None
        self.ended = False
        if self.mode == MODE_SERVER:
            await self.start_mic()
        else:
            await self.send({"type": "capture", "state": "stopped"})

    async def stop_mic(self):
        if self.mic:
            await self.mic.stop()
            self.mic = None

    async def better_summary(self, lang: str | None):
        try:
            return await asyncio.wait_for(
                asyncio.to_thread(llm.summary, self.lines, lang or "en"),
                timeout=SUMMARY_LLM_TIMEOUT)
        except Exception:                    # noqa: BLE001  (timeout, network)
            return None

    def _write_summary(self, summary: dict):
        try:
            write_summary(summary)
        except OSError:
            pass          # the card still reached the page; a full disk is not fatal

    async def start_mic(self):
        cls = BrowserMic if self.mode == MODE_TALK else MicSession
        self.mic = cls(self.on_transcript, telephony=self.telephony)
        try:
            await self.mic.start()
        except Exception as exc:                          # noqa: BLE001
            self.mic = None
            await self.send({"type": "error",
                             "message": f"microphone: {str(exc)[:160]}"})

    async def close(self):
        if self.suggest_task and not self.suggest_task.done():
            self.suggest_task.cancel()
        if self.carrier is not None:
            # Nobody left to show the call to: do not leave a line open.
            await self.carrier.hangup()
        mic = self.mic
        frames_in = getattr(mic, "frames_in", 0)
        await self.stop_mic()
        if isinstance(mic, BrowserMic) and frames_in:
            print(f"talk mode: {frames_in} frames in, "
                  f"{mic.frames_out} to Prisma, {mic.gaps} gaps")


async def ws_handler(request: web.Request):
    ws = web.WebSocketResponse(heartbeat=30, max_msg_size=4 * 1024 * 1024)
    await ws.prepare(request)

    mode = MODE_TALK if request.query.get("mode") == MODE_TALK else MODE_SERVER
    call = Call(ws, mode)
    exotel.bind_page(call)
    probe = MicSession(call.on_transcript, telephony=PHONE_LINE)
    await call.send({
        "type": "hello",
        "models": {"stt": "prisma-v3.0", "tts": "timbre-v3.0"},
        # In talk mode the page owns the device, so the server's input probe is
        # not the answer to "can this call hear?".
        "mic": True if mode == MODE_TALK else probe.available(),
        "mode": mode,
        "voice": call.voice_mode,
        "cloned_voice": call.voice_mode == tts.MODE_CLONED,
        "phone_line": call.telephony,
    })
    # Server-mic mode starts listening immediately; talk mode waits for the
    # page's "Start listening" gesture, because getUserMedia needs one.
    if mode == MODE_SERVER:
        await call.start_mic()

    try:
        async for msg in ws:
            if msg.type is WSMsgType.BINARY:
                await call.on_audio(msg.data)
                continue
            if msg.type is not WSMsgType.TEXT:
                continue
            try:
                data = json.loads(msg.data)
            except json.JSONDecodeError:
                continue
            if not isinstance(data, dict):
                continue
            if data.get("type") == "reply" and data.get("text", "").strip():
                asyncio.create_task(call.on_reply(data["text"].strip()))
            elif data.get("type") == "end_call":
                # The card must not wait on the socket: the extractive one goes
                # out inside the task, and a second may follow.
                call.summary_task = asyncio.create_task(
                    call.end_call(data.get("lang") or None))
            elif data.get("type") == "new_call":
                await call.new_call()
            elif data.get("type") == "start_capture":
                await call.start_capture()
            elif data.get("type") == "set_voice":
                await call.set_voice(str(data.get("mode") or tts.MODE_DEFAULT))
            elif data.get("type") == "set_phone_line":
                await call.set_phone_line(bool(data.get("enabled")))
            elif data.get("type") == "set_cloned_voice":
                await call.set_voice(
                    tts.MODE_CLONED if data.get("enabled") else tts.MODE_DEFAULT)
    finally:
        exotel.unbind_page(call)
        await call.close()
    return ws


async def index(_request: web.Request):
    page = WEB / "index.html"
    if page.exists():
        return web.FileResponse(page)
    return web.Response(text=NO_BUILD, content_type="text/html")


def make_app() -> web.Application:
    app = web.Application()
    app.router.add_get("/ws", ws_handler)
    # Carrier pilot: 503 unless EXOTEL_WS_TOKEN is set, so it is opt-in.
    app.router.add_get("/exotel/ws", exotel.ws_handler)
    # The same gate, with the token in the path: some consoles drop a query
    # string when the applet is saved (see `exotel.request_token`).
    app.router.add_get("/exotel/ws/{token}", exotel.ws_handler)
    app.router.add_get("/", index)
    if WEB.exists():
        app.router.add_static("/assets", WEB / "assets", show_index=False)
        app.router.add_static("/", WEB, show_index=False, follow_symlinks=False)
    return app


def tls_context(argv=None):
    """--tls cert.pem key.pem -> an SSLContext, or None for plain HTTP.

    Talk mode needs a secure context for `getUserMedia`. A tunnel (ngrok) is the
    usual answer on a LAN; this is the offline one, for a phone that already
    trusts a local certificate.
    """
    argv = sys.argv[1:] if argv is None else argv
    if "--tls" not in argv:
        return None
    i = argv.index("--tls")
    try:
        cert, key = argv[i + 1], argv[i + 2]
    except IndexError:
        raise SystemExit("--tls needs a certificate and a key: "
                         "--tls cert.pem key.pem")
    ctx = ssl.create_default_context(ssl.Purpose.CLIENT_AUTH)
    ctx.load_cert_chain(cert, key)
    return ctx


if __name__ == "__main__":
    mode = ("phone line (8 kHz, µ-law, 10 dB noise)" if PHONE_LINE
            else "clean (16 kHz)")
    ctx = tls_context()
    scheme = "https" if ctx else "http"
    print(f"Pashyanti on {scheme}://0.0.0.0:{PORT}  "
          f"(phone: {scheme}://<your-lan-ip>:{PORT})")
    print(f"microphone mode: {mode}")
    print(f"talk mode: {scheme}://<host>:{PORT}/?mode=talk "
          "(needs a secure context on the phone)")
    print(f"carrier bridge: {scheme}://<host>:{PORT}/exotel/ws "
          + ("(token set)" if exotel.enabled() else "(off: set EXOTEL_WS_TOKEN)"))
    web.run_app(make_app(), host="0.0.0.0", port=PORT, print=None,
                ssl_context=ctx)
