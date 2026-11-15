"""Streaming phone-line simulation: 16 kHz microphone -> 8 kHz frames.

The STT socket takes exactly 1024 bytes per frame at real-time cadence: 512
samples at 16 kHz (32 ms) or at 8 kHz (64 ms). Halving the rate therefore needs
*two* input frames per output frame — buffer until 64 ms is available, then
emit one 8 kHz frame. Sending 512-byte frames is rejected by the server.

The chain is the one measured by `harness/degrade.py`: band-limit to
300-3400 Hz, resample to 8 kHz, add noise at a chosen SNR, and round-trip
G.711 µ-law. Pure numpy, no sounddevice, no I/O.
"""
import numpy as np

from audio import FRAME_BYTES, pcm16_to_ulaw, ulaw_to_pcm16
from harness import degrade

IN_RATE = 16000
OUT_RATE = 8000


class PhoneLine:
    """One 16 kHz stream in, one 8 kHz stream out, one 1024-byte frame at a time."""

    def __init__(self, in_rate=IN_RATE, out_rate=OUT_RATE, snr_db=10.0, seed=0):
        if in_rate % out_rate:
            raise ValueError("in_rate must be a multiple of out_rate")
        self.in_rate = in_rate
        self.out_rate = out_rate
        self.snr_db = snr_db
        self.seed = seed
        self._buf = b""
        self._blocks = 0
        # one output frame needs this many input bytes of 16 kHz audio
        self._need = FRAME_BYTES * in_rate // out_rate

    def process(self, frame: bytes) -> list[bytes]:
        """Feed one 1024-byte input frame. Return 0 or 1 output frames of 1024 bytes."""
        if len(frame) != FRAME_BYTES:
            raise ValueError(
                f"frame must be {FRAME_BYTES} bytes, got {len(frame)}")
        self._buf += frame
        out = []
        while len(self._buf) >= self._need:
            block = self._buf[:self._need]
            self._buf = self._buf[self._need:]
            out.append(self._transform(block))
        return out

    def _transform(self, block: bytes) -> bytes:
        x = np.frombuffer(block, dtype=np.int16).astype(np.float64)
        x = degrade.band_limit(x, self.in_rate)
        x = degrade.resample(x, self.in_rate, self.out_rate)
        if self.snr_db is not None:
            x = degrade.add_noise(x, self.snr_db, seed=self.seed + self._blocks)
        self._blocks += 1
        pcm = np.clip(np.rint(x), -32768, 32767).astype(np.int16).tobytes()
        return ulaw_to_pcm16(pcm16_to_ulaw(pcm))   # 8-bit companding, both ways
