"""Replay a wav as if the page were the microphone (talk mode).

Talk mode (`?mode=talk`) takes 1024-byte frames from the browser and streams the
reply back as `audio` messages. This client speaks that same protocol, so the
path can be checked on a machine with no browser and no phone:

    cd divya/backend
    uv run python server.py                      # terminal 1
    uv run python talk_replay.py smoke.wav       # terminal 2

It sends the wav at real time (one 1024-byte frame every 32 ms), waits for the
transcript, then taps a reply and reports the chunks that came back. The reply
is cached by `tts`, so a second run reports `cached=True` and ~0 ms.

This is a manual harness, like `test_stream_file.py`: it needs a running server
and a key, so it is not part of the unit suite.
"""
import asyncio
import base64
import json
import os
import sys
import time
import wave

import aiohttp

URL = os.environ.get("TALK_URL", "ws://127.0.0.1:8080/ws?mode=talk")
FRAME = 1024                    # Prisma's rule: 1024 bytes = 512 samples = 32 ms
DEFAULT_REPLY = "हाँ, धन्यवाद।"


def frames(path):
    """The wav as whole 1024-byte frames, or fail loudly on the wrong format."""
    with wave.open(path) as w:
        rate, channels, width = w.getframerate(), w.getnchannels(), w.getsampwidth()
        if (rate, channels, width) != (16000, 1, 2):
            raise SystemExit(
                f"{path}: need 16 kHz mono s16le, got {rate} Hz, "
                f"{channels} ch, {width * 8}-bit")
        pcm = w.readframes(w.getnframes())
    return [pcm[i:i + FRAME] for i in range(0, len(pcm), FRAME)], len(pcm)


async def main(wav, reply):
    audio, transcripts, speaks, summaries = [], [], [], []
    sent = 0

    async with aiohttp.ClientSession() as session:
        async with session.ws_connect(URL) as ws:
            hello = json.loads((await ws.receive()).data)
            print("hello:", {k: hello[k] for k in ("mode", "mic", "models")})

            await ws.send_json({"type": "start_capture"})
            print("capture:", json.loads((await ws.receive()).data))

            pcm_frames, total = frames(wav)
            print(f"replaying {wav}: {total} bytes = {len(pcm_frames)} frames "
                  f"({total / 32000:.2f} s)")

            async def reader():
                async for msg in ws:
                    if msg.type != aiohttp.WSMsgType.TEXT:
                        continue
                    data = json.loads(msg.data)
                    kind = data["type"]
                    if kind in ("transcript", "retry", "speak", "error"):
                        print(f"  <- {kind}: {data.get('text') or data.get('message') or ''} "
                              f"lang={data.get('lang')} latency={data.get('latency_ms')} "
                              f"ttfa={data.get('ttfa_ms')}")
                    if kind == "transcript":
                        transcripts.append(data)
                    elif kind == "summary":
                        summaries.append(data)
                    elif kind == "capture":
                        print(f"  <- capture: {data['state']}")
                    elif kind == "speak":
                        speaks.append(data)
                    elif kind == "audio" and data.get("data"):
                        audio.append(base64.b64decode(data["data"]))

            task = asyncio.create_task(reader())

            t0 = time.monotonic()
            for frame in pcm_frames:
                await ws.send_bytes(frame)
                sent += 1
                delay = t0 + sent * 0.032 - time.monotonic()
                if delay > 0:
                    await asyncio.sleep(delay)
            print(f"sent {sent} frames of {FRAME} bytes in "
                  f"{time.monotonic() - t0:.2f} s")

            # silence closes the VAD segment, still at cadence
            for _ in range(40):
                await ws.send_bytes(b"\x00" * FRAME)
                await asyncio.sleep(0.032)

            deadline = time.monotonic() + 8
            while not transcripts and time.monotonic() < deadline:
                await asyncio.sleep(0.1)

            if transcripts and reply:
                await ws.send_json({"type": "reply", "text": reply})
                deadline = time.monotonic() + 15
                while not speaks and time.monotonic() < deadline:
                    await asyncio.sleep(0.1)

            # Ending the call must close the session: capture stopped, then the
            # card. A frame after that must not produce a transcript.
            await ws.send_json({"type": "end_call", "lang": "en"})
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline and not summaries:
                await asyncio.sleep(0.1)
            await ws.send_bytes(b"\x00" * FRAME)

            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

    print()
    if transcripts:
        t = transcripts[-1]
        print(f"transcript: {t['text']!r} lang={t['lang']} "
              f"latency={t['latency_ms']} ms")
    else:
        print("transcript: NONE")
    if speaks:
        s = speaks[-1]
        size = sum(len(c) for c in audio)
        print(f"reply: {s['text']!r} ttfa={s['ttfa_ms']} ms cached={s['cached']} "
              f"lang={s.get('lang')}")
        print(f"audio back: {len(audio)} chunks, {size} bytes, "
              f"{size / 32000:.2f} s at 16 kHz")
    elif reply:
        print("reply: NO AUDIO MESSAGE")
    if summaries:
        print(f"card: who={summaries[-1]['who']!r} turns={summaries[-1]['turns']} "
              f"duration={summaries[-1]['duration_s']}s")


if __name__ == "__main__":
    asyncio.run(main(sys.argv[1] if len(sys.argv) > 1 else "smoke.wav",
                     sys.argv[2] if len(sys.argv) > 2 else DEFAULT_REPLY))
