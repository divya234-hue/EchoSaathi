"""Credit probe — run ONCE, before you write any app code.

There is no published price for a credit. This script makes exactly two
paid calls so you can read the rate off your dashboard balance.

  Step 1. Open app.gnani.ai/voice, note your balance.
  Step 2. python probe.py
  Step 3. Note the balance again. Difference = cost of (1000 TTS chars + 10 s STT).
  Step 4. Write both numbers in README. Then design around them.

Writes: probe_tts.wav (1000 chars) and probe_stt_10s.wav (first 10 s of it).
"""
import wave

from gnani import stt_file, tts

TEXT = ("नमस्ते। यह एक परीक्षण है, जिससे हम कीमत मापेंगे। " * 60)[:1000]


def trim(src, dst, seconds=10):
    """Copy the first `seconds` of a wav. REST STT refuses anything over 30 s."""
    with wave.open(src) as r, wave.open(dst, "wb") as w:
        w.setnchannels(r.getnchannels())
        w.setsampwidth(r.getsampwidth())
        w.setframerate(r.getframerate())
        w.writeframes(r.readframes(int(r.getframerate() * seconds)))


def duration(path):
    with wave.open(path) as r:
        return r.getnframes() / r.getframerate()


def main():
    print("1/2  synthesizing 1000 characters ...")
    wav = tts(TEXT, out="probe_tts.wav")
    secs = duration(wav)
    print(f"     -> {wav}  {secs:.1f} s  = {1000 / secs:.1f} chars per second")

    trim(wav, "probe_stt_10s.wav", 10)
    print("2/2  transcribing 10 seconds ...")
    out = stt_file("probe_stt_10s.wav")
    print(f"     -> model={out.get('model')} "
          f"lang={out.get('detected_language_code')} "
          f"latency={out.get('end_to_end_latency')}")
    print(f"     -> {out.get('transcript', '')[:120]}")

    print("\nNow check the dashboard balance again and write down:")
    print("  credits per 1000 TTS characters = ?")
    print("  credits per 10 s of STT audio      = ?")
    print("If 5000 / (credits per 1000 chars) < 200, cache every TTS output.")


if __name__ == "__main__":
    main()
