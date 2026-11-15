# divya — backend

Python 3.12+ / asyncio. Serves the built frontend, owns the microphone (or relays
the page's, in talk mode), relays Gnani.

```fish
cd divya/backend
cp .env.example .env      # paste your GNANI_API_KEY
uv sync
uv run python server.py   # http://localhost:8080
```

| File | Job |
|---|---|
| `server.py` | aiohttp app: static `../web/dist`, `/ws`, orchestration, half-duplex muting, `?mode=talk` |
| `stt.py` | microphone (or the page's 1024-byte frames) → Prisma v3.0 streaming → callback per sentence |
| `tts.py` | text → Timbre v3.0 SSE → speaker, or to the page in talk mode; cached by hash |
| `audio.py` | 1024-byte frame maths, G.711 µ-law (numpy; `audioop` is gone in 3.13+) |
| `gnani.py` | low-level REST client: `stt_file`, `tts`, `clone_embedding`, `tts_cloned` |
| `llm.py` | the chip/card model over OpenCode Go (non-Gnani): one reply, one card, or None |
| `chips.py` | caller-language "please repeat" / "a little slower" table |
| `exotel.py` | carrier pilot: Exotel AgentStream in, Prisma/Timbre in the middle, opt-in |
| `probe.py` | one 1,000-char TTS + one 10 s STT call, to read the credit rate |
| `stream_mic.py` | standalone mic → transcript terminal test |
| `test_stream_file.py` | replay a wav into the STT socket (no microphone needed) |
| `talk_replay.py` | replay a wav as the page in talk mode: 1024-byte frames in, the reply audio out |
| `clone_voice.py` | `build ref.wav` → `embedding.json`, then `say "..."` |
| `harness/` | Phone-line accuracy: degrade clean audio (band-limit, µ-law, noise) and measure WER against known text |

## Measuring phone-line accuracy

```fish
uv run python -m harness.cli            # 8 clips, 10/5/0 dB SNR sweep
uv run python -m harness.cli --levels 15,10 -n 10
uv run python -m harness.cli --rebuild  # ignore the transcript cache
```

Writes `harness_report.md` (the table) and `harness_report.json`. Every clip is
synthesised from known text, so the reference is exact; transcripts and audio
are cached by hash, so re-runs of the same level cost nothing.

| module | job |
|---|---|
| `degrade.py` | band-limit → 8 kHz → noise → µ-law round trip (pure numpy) |
| `wer.py` | Indic normalisation (nukta, candrabindu, digits), WER and CER |
| `corpus.py` | reference clips via TTS, cached |
| `cli.py` | the sweep, the table, the report |

Measured on 8 clips, `hi-IN`: 0.0% clean, 3.6% at 10 dB SNR, 27.8% at 5 dB,
93.5% at 0 dB. That last number is the point — at 0 dB the system should ask
for a repeat, not invent words.

A second corpus, `bn-IN` (ten sentences), is measured with
`uv run python -m harness.cli --lang bn-IN` and writes
`harness_report_bn-IN.md`. Its reference is **provisional**: no native speaker
has checked the Bengali sentences (#12), and `wer.normalize` folds Devanagari
only (D-015), so the Bengali number is not comparable with the Hindi one.


## Two facts that cost an evening

1. **Frame size is exact.** The STT socket takes raw PCM s16le mono in frames of
   *exactly* 1024 bytes — 512 samples, i.e. 32 ms at 16 kHz — at real-time cadence.
2. **Prisma v3.0 is opt-in.** Without `model=prisma-v3.0` you silently get v2.5.
   The `3` in `/stt/v3` is the URL version, not the model version.

Also: TTS intermittently returns `500` on perfectly valid input — `gnani.py` retries it.
