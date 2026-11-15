"""Text -> speech, streamed to the speaker, cached on disk.

Cost is per character, so every clip is cached by (text, voice, model, rate).
A repeat costs nothing and returns instantly — which is what makes rehearsal
and a live demo affordable.
"""
import asyncio
import base64
import hashlib
import json
import os
import time
from pathlib import Path

import numpy as np
import requests

import gnani
from gnani import BASE, HDR

# sounddevice initialises PortAudio the moment it is imported, and raises if the
# machine has no audio server. Import it lazily so the server can boot headless
# and report mic: false instead of dying at import time.

CACHE_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cache", "tts")
EMBEDDING_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)),
                              "embedding.json")
VOICE = "Shivani"
MODEL = "timbre-v3.0"
MODEL_CLONE = "vachana-vc-v1"
RATE = 16000

MODE_DEFAULT = "default"
MODE_CLONED = "cloned"
DEFAULT_LANG = "hi-IN"


def reply_language(lang: str | None) -> str:
    """The language Timbre should speak: the caller's, or Hindi by default.

    Prisma reports region-tagged codes (`hi-IN`); a bare code is completed with
    `-IN` because every language this app meets is Indian or English-in-India.
    """
    text = (lang or "").strip()
    if not text:
        return DEFAULT_LANG
    return text if "-" in text else f"{text}-IN"


def effective_mode(mode: str, lang: str | None) -> str:
    """Cloned only when a clone exists *and* the reply is Hindi.

    `vachana-vc-v1` takes an embedding, not a language, so a cloned reply is
    Hindi-shaped by construction. Timbre v3.0's default voices each speak all
    ten languages, so a non-Hindi reply uses the default voice instead of
    speaking Bengali with a Hindi clone (D-012 amendment).
    """
    if mode != MODE_CLONED or not has_clone():
        return MODE_DEFAULT
    return MODE_CLONED if reply_language(lang).lower().startswith("hi") else MODE_DEFAULT


def _load_embedding(path=EMBEDDING_PATH):
    """The cloned-voice embedding, or None when the file is absent or broken."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f).get("speaker_embedding")
    except (OSError, ValueError):
        return None


EMBEDDING = _load_embedding()


def has_clone():
    return EMBEDDING is not None


def _key(text, voice, model, rate, mode=MODE_DEFAULT, lang=DEFAULT_LANG):
    h = hashlib.sha1(
        f"{text}|{voice}|{model}|{rate}|{mode}|{reply_language(lang)}".encode()
    ).hexdigest()[:16]
    return os.path.join(CACHE_DIR, f"{h}.pcm")


_SESSION = requests.Session()      # reuse the TLS connection between replies


def parse_sse_lines(lines):
    """Timbre's SSE lines -> raw s16le chunks.

    A good stream closes with `{"is_final": true}`. One that stops without it is
    a dropped connection, not a short sentence, and one that carries no audio at
    all is a silent failure. Both are raised: a reply the caller never heard must
    not be cached, and must not be reported as spoken either.
    """
    final = False
    audio = False
    for raw in lines:
        if not raw or not raw.startswith(b"data:"):
            continue
        body = raw[5:].strip()
        if not body:
            continue
        try:
            d = json.loads(body)
        except json.JSONDecodeError:
            continue
        chunk = d.get("audio")
        if chunk:
            audio = True
            yield base64.b64decode(chunk)
        if d.get("is_final"):
            final = True
            break
    if not final:
        raise RuntimeError("TTS stream ended without is_final (truncated)")
    if not audio:
        raise RuntimeError("TTS produced no audio")


def _sse_stream(text, voice, model, rate, lang=DEFAULT_LANG):
    """Yield raw s16le chunks as the server produces them."""
    payload = {
        "text": text,
        "voice": voice,
        "model": model,
        "language": reply_language(lang),
        "speed": 1.0,
        "audio_config": {
            "sample_rate": rate,
            "num_channels": 1,
            "sample_width": 2,
            "encoding": "linear_pcm",
            "container": "raw",
        },
    }
    with _SESSION.post(f"{BASE}/api/v1/tts/sse", headers=HDR, json=payload,
                       stream=True, timeout=120) as r:
        if r.status_code != 200:
            raise RuntimeError(f"TTS {r.status_code}: {r.text[:200]}")
        yield from parse_sse_lines(r.iter_lines())


def _play_and_cache(text, voice, model, rate, mode=MODE_DEFAULT,
                    lang=DEFAULT_LANG):
    """Blocking: stream to the speaker and accumulate to the cache. -> ms."""
    import sounddevice as sd

    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _key(text, voice, model, rate, mode, lang)
    t0 = time.time()
    first = None
    pcm = bytearray()

    with sd.RawOutputStream(samplerate=rate, channels=1, dtype="int16") as out:
        for chunk in _sse_stream(text, voice, model, rate, lang):
            if first is None:
                first = (time.time() - t0) * 1000
            pcm.extend(chunk)
            out.write(chunk)
        out.write(b"\x00" * 32)          # drain

    with open(path, "wb") as f:
        f.write(bytes(pcm))
    return int(first or 0), path


def _wav_pcm(path):
    import wave

    with wave.open(path) as w:
        return w.readframes(w.getnframes())


def _clone_and_cache(text, rate=RATE, lang=DEFAULT_LANG):
    """Blocking: clone endpoint (non-streaming) -> pcm cache. -> pcm."""
    os.makedirs(CACHE_DIR, exist_ok=True)
    path = _key(text, MODE_CLONED, MODEL_CLONE, rate, MODE_CLONED, lang)
    tmp = f"{path}.wav"
    gnani.tts_cloned(text, EMBEDDING, out=tmp, rate=rate)
    pcm = _wav_pcm(tmp)
    os.remove(tmp)
    with open(path, "wb") as f:
        f.write(pcm)
    return pcm


def _play_and_cache_cloned(text, lang=DEFAULT_LANG):
    """Blocking: cloned pcm -> speaker. -> ms to first audio."""
    import sounddevice as sd

    t0 = time.time()
    pcm = _clone_and_cache(text, RATE, lang)
    ttfa = int((time.time() - t0) * 1000)
    sd.play(np.frombuffer(pcm, dtype=np.int16), RATE)
    sd.wait()
    return ttfa


def _play_cached(path, rate):
    import sounddevice as sd

    pcm = np.fromfile(path, dtype=np.int16)
    sd.play(pcm, rate)
    sd.wait()


async def speak(text, voice=VOICE, model=MODEL, rate=RATE,
                mode=MODE_DEFAULT, lang=DEFAULT_LANG):
    """Say `text` out loud. Returns (ttfa_ms, cached).

    `mode` is "cloned" only when an embedding was loaded; asking for the cloned
    voice without one falls back to the default voice instead of failing.
    `lang` is the language of the words, normally the caller's (`Call.reply_lang`).
    """
    effective = effective_mode(mode, lang)

    if effective == MODE_CLONED:
        path = _key(text, MODE_CLONED, MODEL_CLONE, rate, MODE_CLONED, lang)
        if os.path.exists(path):
            await asyncio.to_thread(_play_cached, path, rate)
            return 0, True
        ttfa = await asyncio.to_thread(_play_and_cache_cloned, text, lang)
        return ttfa, False

    path = _key(text, voice, model, rate, MODE_DEFAULT, lang)
    if os.path.exists(path):
        await asyncio.to_thread(_play_cached, path, rate)
        return 0, True
    ttfa, _ = await asyncio.to_thread(_play_and_cache, text, voice, model, rate,
                                      MODE_DEFAULT, lang)
    return ttfa, False


def _chunks(pcm, size=32 * 1024):
    for i in range(0, len(pcm), size):
        yield pcm[i:i + size]


def cached_path(text, lang=DEFAULT_LANG, rate=RATE):
    """The file `stream_pcm` would keep this text in, on the default voice.

    The carrier leg speaks with the default voice (`mode=MODE_DEFAULT`), so its
    cache key is this one. A cloned reply uses a different key.
    """
    return _key(text, VOICE, MODEL, rate, MODE_DEFAULT, lang)


def is_cached(text, lang=DEFAULT_LANG, rate=RATE):
    return os.path.exists(cached_path(text, lang, rate))


async def warm(text, lang=DEFAULT_LANG, rate=RATE):
    """Synthesise `text` into the cache without playing it. -> the path.

    Used for the acknowledgement the carrier leg speaks while the real reply is
    still being generated: one synthesis buys an instant first word on every
    later call, so the work is done off the critical path.
    """
    path = cached_path(text, lang, rate)
    if os.path.exists(path):
        return path

    async def discard(_chunk):
        pass

    await stream_pcm(text, discard, rate=rate, lang=lang)
    return path


async def stream_pcm(text, emit, voice=VOICE, model=MODEL, rate=RATE,
                     mode=MODE_DEFAULT, lang=DEFAULT_LANG):
    """Say `text` into an async sink instead of the speaker. -> (ttfa_ms, cached).

    Talk mode (`?mode=talk`) plays the reply on the phone, so the same Timbre
    stream goes out over the page's websocket as it arrives instead of into a
    `RawOutputStream`. Cached clips replay from disk and report 0 ms, exactly
    like `speak`. `emit` is awaited on the event loop with raw s16le chunks.
    """
    effective = effective_mode(mode, lang)

    if effective == MODE_CLONED:
        path = _key(text, MODE_CLONED, MODEL_CLONE, rate, MODE_CLONED, lang)
        if os.path.exists(path):
            for chunk in _chunks(await asyncio.to_thread(Path(path).read_bytes)):
                await emit(chunk)
            return 0, True
        t0 = time.time()
        pcm = await asyncio.to_thread(_clone_and_cache, text, rate, lang)
        ttfa = int((time.time() - t0) * 1000)
        for chunk in _chunks(pcm):
            await emit(chunk)
        return ttfa, False

    path = _key(text, voice, model, rate, MODE_DEFAULT, lang)
    if os.path.exists(path):
        for chunk in _chunks(await asyncio.to_thread(Path(path).read_bytes)):
            await emit(chunk)
        return 0, True
    return await _stream_sse_to(text, emit, voice, model, rate, path, lang)


async def _stream_sse_to(text, emit, voice, model, rate, path,
                         lang=DEFAULT_LANG):
    """Bridge the blocking SSE loop to the event loop without buffering it all.

    Retried once when a stream dies before any audio reached the caller: Timbre
    intermittently answers with a stream that carries no audio or stops early,
    and a reply the caller never hears is worse than a second attempt. Once
    audio has left, a retry would repeat the sentence, so the error is raised.
    """
    loop = asyncio.get_running_loop()
    t0 = time.time()

    for attempt in (1, 2):
        queue: asyncio.Queue = asyncio.Queue()
        done = object()
        first: list[int] = []
        pcm = bytearray()
        delivered = False

        def worker():
            ok = False
            try:
                for chunk in _sse_stream(text, voice, model, rate, lang):
                    if not first:
                        first.append(int((time.time() - t0) * 1000))
                    pcm.extend(chunk)
                    loop.call_soon_threadsafe(queue.put_nowait, chunk)
                ok = True
            except Exception as exc:                 # noqa: BLE001
                loop.call_soon_threadsafe(queue.put_nowait, exc)
            finally:
                # Only a complete stream is cached: a truncated clip would
                # replay as a half sentence and report 0 ms.
                if ok and pcm:
                    try:
                        os.makedirs(CACHE_DIR, exist_ok=True)
                        with open(path, "wb") as f:
                            f.write(bytes(pcm))
                    except OSError:
                        pass      # playback already happened; a miss is cheap
                loop.call_soon_threadsafe(queue.put_nowait, done)

        task = asyncio.create_task(asyncio.to_thread(worker))
        try:
            while True:
                item = await queue.get()
                if item is done:
                    break
                if isinstance(item, Exception):
                    raise item
                delivered = True
                await emit(item)
        except Exception:
            if not delivered and attempt == 1:
                continue                    # nothing was heard: try once more
            raise
        finally:
            if not task.done():
                # The socket went away mid-sentence. Do not hold the call open
                # for the rest of the stream; the worker finishes on its own.
                task.cancel()
        return int(first[0]) if first else 0, False

    raise RuntimeError("TTS produced no audio after a retry")



def cache_stats():
    if not os.path.isdir(CACHE_DIR):
        return 0, 0
    files = os.listdir(CACHE_DIR)
    total = sum(os.path.getsize(os.path.join(CACHE_DIR, f)) for f in files)
    return len(files), total
