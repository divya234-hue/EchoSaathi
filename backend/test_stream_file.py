"""Replay a 16 kHz wav into the STT websocket at real-time cadence.

Same code path as stream_mic.py, minus the microphone — so you can test the
streaming protocol on a machine with no audio device (CI, a server, this box).

    python test_stream_file.py smoke.wav
"""
import asyncio
import json
import sys
import time
import wave

import websockets

from gnani import KEY

URL = "wss://api.vachana.ai/stt/v3/stream"
RATE = 16000
HDR = {
    "x-api-key-id": KEY,
    "model": "prisma-v3.0",
    "language_code": "indic-auto",
    "x-sample-rate": str(RATE),
    "x-vad-threshold": "0.7",
    "x-min-silence-ms": "350",
    "x-max-speech-s": "15",
    # Word boosting, same rules as REST. Non-ASCII must be
    # JSON-escaped, which is what ensure_ascii does.
    "keyterms": json.dumps(["पश्यन्ती", "divya"], ensure_ascii=True),
}


async def connect():
    for kw in ({"additional_headers": HDR}, {"extra_headers": HDR}):
        try:
            return await websockets.connect(URL, **kw)
        except TypeError:
            continue
    raise SystemExit("pip install -U websockets")


async def main(path):
    with wave.open(path) as w:
        assert w.getframerate() == RATE, f"need {RATE} Hz, got {w.getframerate()}"
        assert w.getnchannels() == 1 and w.getsampwidth() == 2, "need mono s16"
        pcm = w.readframes(w.getnframes())

    frames = [pcm[i:i + 1024] for i in range(0, len(pcm), 1024)]
    frames = [f for f in frames if len(f) == 1024] + [b"\x00" * 1024] * 25  # pad silence
    print(f"sending {len(frames)} frames of 1024 B ({len(frames) * 0.032:.1f} s of audio)")

    ws = await connect()
    print("connected:", (await ws.recv())[:100])

    async def pump():
        for f in frames:
            await ws.send(f)
            await asyncio.sleep(0.032)          # real-time cadence, never burst
        await asyncio.sleep(1.2)

    t0 = time.time()
    task = asyncio.create_task(pump())
    try:
        while True:
            d = json.loads(await asyncio.wait_for(ws.recv(), timeout=8))
            kind = d.get("type")
            elapsed = time.time() - t0
            if kind == "transcript":
                print(f"  [{elapsed:5.2f}s] {d.get('text')!r}  "
                      f"lang={d.get('detected_language_code')} "
                      f"latency={d.get('latency')} ms")
            elif kind == "error":
                print("  ERROR:", d)
                break
            else:
                print(f"  [{elapsed:5.2f}s] {kind}")
    except asyncio.TimeoutError:
        print("  (stream idle)")
    finally:
        task.cancel()
        await ws.close()


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "smoke.wav"))
