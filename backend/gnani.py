"""Minimal Gnani client. One file, no abstractions, nothing clever.

Set your key in ./.env (or export it) first:
    GNANI_API_KEY=...
"""
import json
import os
import time

import requests

BASE = "https://api.vachana.ai"
RETRY_STATUS = {429, 500, 502, 503, 504}   # 500 is real: TTS returns it transiently


def _load_env(path=None):
    """Read KEY=VALUE lines from a .env next to this file (or the repo root).

    Real env vars always win, so `set -x GNANI_API_KEY ...` still works.
    """
    if path is None:
        here = os.path.dirname(os.path.abspath(__file__))
        for candidate in (os.path.join(here, ".env"),
                          os.path.join(os.path.dirname(here), ".env")):
            if os.path.exists(candidate):
                path = candidate
                break
    if path is None or not os.path.exists(path):
        return
    with open(path, encoding="utf-8-sig") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            if line.startswith("export "):
                line = line[len("export "):]
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip().strip('"').strip("'"))


_load_env()

if "GNANI_API_KEY" not in os.environ:
    raise SystemExit(
        "GNANI_API_KEY is not set.\n"
        "Put it in divya/.env (or the repo root .env), one line:\n"
        "    GNANI_API_KEY=your-key-here\n"
        "Or set it for this shell:  set -x GNANI_API_KEY your-key-here   (fish)\n"
        "                           export GNANI_API_KEY=your-key-here  (bash)"
    )

KEY = os.environ["GNANI_API_KEY"]
HDR = {"X-API-Key-ID": KEY}


def _request(fn, attempts=3):
    """Call fn() until it returns a 200, or give up on a non-retryable status.

    TTS intermittently answers 500 'technical difficulties' on perfectly valid
    input (seen on the first call of a session), so the app must not treat one
    500 as fatal — it would kill a demo take.
    """
    last = None
    for attempt in range(attempts):
        last = fn()
        if last.status_code == 200:
            return last
        if last.status_code not in RETRY_STATUS:
            break
        time.sleep(1.5 * (attempt + 1))
    return last


def _fail(kind, r):
    raise RuntimeError(f"{kind} {r.status_code}: {r.text[:400]}")


def stt_file(path, lang="indic-auto", fmt="transcribe", model="prisma-v3.0",
             keyterms=None):
    """Transcribe a clip up to 30 s. Returns the parsed JSON."""
    data = {"model": model, "language_code": lang, "format": fmt}
    if keyterms:
        data["keyterms"] = json.dumps(keyterms, ensure_ascii=True)

    def go():
        with open(path, "rb") as f:
            return requests.post(
                f"{BASE}/stt/v3", headers=HDR,
                files={"audio_file": (os.path.basename(path), f, "audio/wav")},
                data=data, timeout=120,
            )

    r = _request(go)
    if r.status_code != 200:
        _fail("STT", r)
    return r.json()


def tts(text, voice="Shivani", lang="hi-IN", out="out.wav",
        model="timbre-v3.0", rate=16000, container="wav"):
    """Synthesize and write to `out`. Returns the path.

    Timbre v3.0 voices: Shivani Lakshmi Kalpana Chetana Vasudha Riyaa Tarika
                        Avinash Shubham Prakash Devansh Yashraj Harshad
    Use container="mulaw", rate=8000 only for telephony.
    """
    payload = {
        "text": text,
        "voice": voice,
        "model": model,
        "language": lang,
        "speed": 1.0,
        "audio_config": {
            "sample_rate": rate,
            "num_channels": 1,
            "sample_width": 2,
            "encoding": "linear_pcm",
            "container": container,
        },
    }
    r = _request(lambda: requests.post(f"{BASE}/api/v1/tts/inference",
                                       headers=HDR, json=payload, timeout=120))
    if r.status_code != 200:
        _fail("TTS", r)
    with open(out, "wb") as f:
        f.write(r.content)
    if container == "wav":
        _fix_wav_sizes(out)
    return out


def clone_embedding(path, save="embedding.json"):
    """5-30 s of clean speech -> speaker_embedding. Cache it; costs a call."""
    def go():
        with open(path, "rb") as f:
            return requests.post(
                f"{BASE}/api/v1/tts/voice-clone/embeddings", headers=HDR,
                files={"audio_file": (os.path.basename(path), f, "audio/wav")},
                timeout=120,
            )

    r = _request(go)
    if r.status_code != 200:
        _fail("VC", r)
    body = r.json()
    # {"success":true,"message":...,"data":{"voice_clone_embedding":{
    #     "embedding":"<base64>","shape":[1,768],"dtype":"torch.bfloat16"}}}
    emb = (body.get("data") or {}).get("voice_clone_embedding") or body.get("speaker_embedding")
    if not emb:
        raise RuntimeError(f"VC: unexpected response {json.dumps(body)[:300]}")
    if save:
        with open(save, "w") as f:
            json.dump({"speaker_embedding": emb}, f)
    return emb


def tts_cloned(text, embedding, out="cloned.wav", rate=16000, container="wav"):
    """Same as tts() but in the cloned voice. `embedding` is what clone_embedding returns."""
    payload = {
        "text": text,
        "model": "vachana-vc-v1",
        "audio_config": {
            "sample_rate": rate,
            "num_channels": 1,
            "sample_width": 2,
            "encoding": "linear_pcm",
            "container": container,
        },
        "speaker_embedding": embedding,
    }
    r = _request(lambda: requests.post(f"{BASE}/api/v1/tts/inference",
                                       headers=HDR, json=payload, timeout=120))
    if r.status_code != 200:
        _fail("VC-TTS", r)
    with open(out, "wb") as f:
        f.write(r.content)
    if container == "wav":
        _fix_wav_sizes(out)
    return out


def _fix_wav_sizes(path):
    """Gnani returns WAVs whose RIFF and data size fields are left at
    0xFFFFFFFF (as if streamed, never backpatched). Players cope; python's
    `wave` module does not — getnframes() reports garbage. Patch the two
    fields to the real byte counts.
    """
    with open(path, "r+b") as fh:
        buf = fh.read()
        if len(buf) < 44 or buf[8:12] != b"WAVE":
            return
        pos, data_pos = 12, None
        while pos + 8 <= len(buf):
            cid = buf[pos:pos + 4]
            size = int.from_bytes(buf[pos + 4:pos + 8], "little")
            if cid == b"data":
                data_pos = pos
                break
            pos += 8 + size + (size & 1)
            if size == 0xFFFFFFFF:
                break
        if data_pos is None:
            return
        real_data = len(buf) - (data_pos + 8)
        fh.seek(4)
        fh.write((len(buf) - 8).to_bytes(4, "little"))
        fh.seek(data_pos + 4)
        fh.write(real_data.to_bytes(4, "little"))
