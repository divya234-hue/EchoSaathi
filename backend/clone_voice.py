"""Voice cloning in two steps.

    python clone_voice.py build ref.wav          # once -> embedding.json
    python clone_voice.py say "नमस्ते, मैं पश्यन्ती हूँ।"   # -> cloned.wav

`ref.wav` must be 5-30 s of clean speech, one speaker, 16 kHz mono is ideal.
The embedding is cached on disk on purpose: generating it costs a call, and you
only ever need one per voice.
"""
import json
import sys
import wave

from gnani import clone_embedding, tts_cloned

EMB_FILE = "embedding.json"


def build(path):
    emb = clone_embedding(path, save=EMB_FILE)
    print(f"saved {EMB_FILE}  shape={emb['shape']} dtype={emb['dtype']} "
          f"b64={len(emb['embedding'])}")


def say(text, out="cloned.wav"):
    emb = json.load(open(EMB_FILE))["speaker_embedding"]
    path = tts_cloned(text, emb, out=out)
    with wave.open(path) as w:
        print(f"{path}  {w.getnframes() / w.getframerate():.2f}s  "
              f"{w.getframerate()} Hz")


if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    if sys.argv[1] == "build":
        build(sys.argv[2] if len(sys.argv) > 2 else "ref.wav")
    elif sys.argv[1] == "say":
        say(sys.argv[2] if len(sys.argv) > 2 else "नमस्ते, मैं पश्यन्ती हूँ।")
    else:
        raise SystemExit(__doc__)
