"""Audio plumbing: frame maths, µ-law, wav helpers.

Python 3.13 removed `audioop`, so µ-law conversion is a numpy lookup table.
"""
import wave

import numpy as np

FRAME_BYTES = 1024          # Prisma wants exactly 1024-byte frames
SAMPLES_PER_FRAME = FRAME_BYTES // 2


def frames(pcm: bytes):
    """Split raw s16le bytes into 1024-byte frames, padding the last one."""
    out = [pcm[i:i + FRAME_BYTES] for i in range(0, len(pcm), FRAME_BYTES)]
    if out and len(out[-1]) < FRAME_BYTES:
        out[-1] = out[-1] + b"\x00" * (FRAME_BYTES - len(out[-1]))
    return out


def read_wav(path):
    with wave.open(path) as w:
        pcm = w.readframes(w.getnframes())
        return pcm, w.getframerate()


def duration_s(path):
    pcm, rate = read_wav(path)
    return len(pcm) / (2 * rate)


# --- G.711 µ-law -----------------------------------------------------------

def _ulaw_table():
    """256-entry decode table: µ-law byte -> int16."""
    table = np.zeros(256, dtype=np.int16)
    for i in range(256):
        u = ~i & 0xFF
        sign = u & 0x80
        exponent = (u >> 4) & 0x07
        mantissa = u & 0x0F
        sample = ((mantissa << 3) + 0x84) << exponent
        sample -= 0x84
        table[i] = -sample if sign else sample
    return table


ULAW_DECODE = _ulaw_table()


def ulaw_to_pcm16(data: bytes) -> bytes:
    """µ-law bytes -> s16le PCM."""
    return ULAW_DECODE[np.frombuffer(data, dtype=np.uint8)].tobytes()


def pcm16_to_ulaw(pcm: bytes) -> bytes:
    """s16le PCM -> µ-law. Only needed if you answer back into a real line."""
    x = np.frombuffer(pcm, dtype=np.int16).astype(np.int32)
    sign = (x < 0).astype(np.int32)
    x = np.abs(x)
    x = np.clip(x, 0, 32635) + 0x84
    exponent = np.floor(np.log2(x)).astype(np.int32) - 7
    exponent = np.clip(exponent, 0, 7)
    mantissa = (x >> (exponent + 3)) & 0x0F
    out = (~(sign << 7 | exponent << 4 | mantissa)) & 0xFF
    return out.astype(np.uint8).tobytes()
