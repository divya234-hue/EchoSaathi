"""Live mic -> Prisma v3.0 streaming. Run this AFTER probe.py works.

  python stream_mic.py                    # laptop mic
  python stream_mic.py ta-IN              # force one language
  python stream_mic.py hi-IN --telephony  # 8 kHz phone line tuned VAD

Needs a microphone and PortAudio (often already installed on Fedora; if the
import fails, `sudo dnf install -y portaudio`).

    .venv/bin/pip install sounddevice numpy
    .venv/bin/python stream_mic.py

The key comes from ./.env via api.py — no export needed.
"""
import asyncio
import json
import sys

import sounddevice as sd
import websockets

from gnani import KEY

URL = "wss://api.vachana.ai/stt/v3/stream"
BLOCK = 512          # 512 samples * 2 bytes = 1024 bytes, exactly one frame

ARGS = [a for a in sys.argv[1:] if not a.startswith("--")]
LANG = ARGS[0] if ARGS else "indic-auto"
TELEPHONY = "--telephony" in sys.argv
RATE = 8000 if TELEPHONY else 16000   # 64 ms per frame at 8 kHz, 32 ms at 16 kHz

# Phone audio is narrower and noisier: fewer false triggers, but sentences take
# longer to close. Values follow the docs' telephony guidance.
VAD = ({"x-vad-threshold": "0.72", "x-min-silence-ms": "450",
        "x-min-speech-ms": "200", "x-min-segment-ms": "200"} if TELEPHONY else
       {"x-vad-threshold": "0.55", "x-min-silence-ms": "350",
        "x-min-speech-ms": "100", "x-min-segment-ms": "120"})

HDR = {
    "x-api-key-id": KEY,
    "model": "prisma-v3.0",
    "language_code": LANG,
    "format": "transcribe",     # digits and symbols, not spelled-out words
    "x-sample-rate": str(RATE),
    "x-max-speech-s": "15",
    **VAD,
    # Word boosting, same rules as REST. Non-ASCII must be
    # JSON-escaped, which is what ensure_ascii does.
    "keyterms": json.dumps(["पश्यन्ती", "divya"], ensure_ascii=True),
}


async def connect():
    """websockets renamed extra_headers -> additional_headers in v14."""
    for kw in ({"additional_headers": HDR}, {"extra_headers": HDR}):
        try:
            return await websockets.connect(URL, **kw)
        except TypeError:
            continue
    raise SystemExit("upgrade websockets: pip install -U websockets")


async def main():
    q: asyncio.Queue[bytes] = asyncio.Queue()
    loop = asyncio.get_running_loop()

    def on_audio(indata, frames, time_info, status):
        # audio thread -> event loop
        loop.call_soon_threadsafe(q.put_nowait, bytes(indata))

    ws = await connect()
    print("connected:", await ws.recv())
    print("bolna shuru karo, Ctrl-C to stop\n")

    with sd.RawInputStream(samplerate=RATE, channels=1, dtype="int16",
                           blocksize=BLOCK, callback=on_audio):
        async def pump():
            while True:
                frame = await q.get()
                await ws.send(frame)              # must be exactly 1024 bytes
                await asyncio.sleep(BLOCK / RATE)  # 32 ms — real-time cadence

        pump_task = asyncio.create_task(pump())
        try:
            async for msg in ws:
                d = json.loads(msg)
                kind = d.get("type")
                if kind == "transcript":
                    print(f">> {d.get('text')}   "
                          f"[{d.get('detected_language_code')} "
                          f"{d.get('latency')} ms]")
                elif kind == "error":
                    print("ERROR:", d)
        finally:
            pump_task.cancel()
            await ws.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        print("\nband.")
