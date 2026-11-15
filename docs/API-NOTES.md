# Gnani API notes

Behaviour we verified against the live API, not against the marketing pages.
Each entry is something that cost time or would have cost time.

Base URL `https://api.vachana.ai`, auth header `X-API-Key-ID`. One key, no
organisation id.

## Speech-to-text

| | Prisma v2.5 | Prisma v3.0 |
|---|---|---|
| How selected | default | `model=prisma-v3.0` — **opt-in** |
| Languages | one per request | 9 Indic + English, or `indic-auto` |
| Code-mixing | no | yes, via `format=codemix` |
| Context hints | `bias_list` (100 words) | `keyterms` (200), `topic`, `previous_text`, `speaker_names` |
| Output styles | `verbatim`, `transcribe` | + `codemix`, `transliterate` |

- The `3` in `/stt/v3` is the **URL** version, not the model version. Sending
  `POST /stt/v3` without `model` runs **v2.5**.
- Default output format differs: v2.5 returns words, v3.0 returns digits. Always
  send `format` explicitly.
- REST audio: 30 s hard cap, 8 kHz–44.1 kHz, mono, `wav mp3 ogg flac aac m4a`,
  format detected from the file extension.
- **Word boosting works on streaming too.** `keyterms` is a connection header,
  JSON-escaped for non-ASCII:

  ```
  keyterms: ["\u092a\u0936\u094d\u092f\u0928\u094d\u0924\u0940","divya"]
  ```

  This fixed the model writing our own product name as `पश्चिंती`.
- **No partials.** The `connected` frame advertises `partials_enabled: false` and
  `partial_interval_ms: 450`. We tried `partials_enabled: true` and
  `x-partials-enabled: true` as headers; both were ignored and no new message
  types appeared. One closed VAD segment = one final transcript.
- No word timestamps anywhere. No diarization except Batch. No translation.

### Streaming socket

`wss://api.vachana.ai/stt/v3/stream`

- Raw **s16le mono PCM**, frames of **exactly 1024 bytes** (512 samples), sent at
  real-time cadence: 32 ms at 16 kHz, 64 ms at 8 kHz. Bursting degrades the VAD.
- 15-minute session cap; 60 s idle timeout, `x-idle-timeout-sec` (5–900).
- VAD headers are fixed for the connection: `x-vad-threshold` (0.7 default),
  `x-min-silence-ms` (500), `x-min-speech-ms` (100), `x-min-segment-ms` (120),
  `x-max-speech-s` (disabled).
- Our presets: laptop mic `0.55 / 350 / 100 / 120`; telephony
  `0.72 / 450 / 200 / 200` at 8 kHz.
- Messages: `connected`, `speech_start`, `processing`, `transcript`, `error`.

## Text-to-speech

`POST /api/v1/tts/inference` (REST), `/api/v1/tts/sse` (streaming),
`wss://api.vachana.ai/api/v1/tts` (realtime).

- Timbre v3.0: 13 voices, each speaks all 10 languages, 13 inline tags
  (`<slow>`, `<whispers>`, `<excited>`, `<pauses>` …). Timbre v2.5: 42 voices,
  one preferred language each.
- **Voices do not cross models** — `Nalini` with `timbre-v3.0` is a 400.
- `container=mulaw` forces 8 kHz — that is the telephony path and needs no
  resampling on either side.
- **SSE is worth it.** Measured time-to-first-audio 764 ms streaming vs ~2.5 s
  for REST on the same one-sentence input. Use SSE for anything the user waits on.
- Tags are billed as characters, angle brackets included.
- Numbers, currency, phone numbers and IDs must be pre-formatted as spoken words
  or they are mispronounced. This is the most common "sounds amateur" failure.
- **TTS returns 500 on valid input, intermittently.** We hit it on a 161-character
  Hindi sentence; the identical request succeeded on retry. Retry 429/5xx.

### The WAV header bug

`container=wav` responses carry `0xFFFFFFFF` in the RIFF size and `data` chunk
size fields — the shape of a streamed file that was never backpatched. Players
cope; Python's `wave` does not (`getnframes()` reports 2³¹ samples). `gnani.py`
patches both fields after download (`_fix_wav_sizes`). If you write WAVs
yourself, verify the header.

## Voice cloning

Two calls:

1. `POST /api/v1/tts/voice-clone/embeddings` — multipart `audio_file`, 5–30 s of
   clean speech, one speaker. Response shape:

   ```json
   {"success": true, "message": "...", "data": {"voice_clone_embedding": {
      "embedding": "<base64>", "shape": [1, 768], "dtype": "torch.bfloat16"}}}
   ```

   The embedding is under `data.voice_clone_embedding`, not at the top level.
2. `POST /api/v1/tts/inference` with `model: "vachana-vc-v1"` and
   `speaker_embedding: {embedding, shape, dtype}`.

Cache the embedding to disk — one call per voice, forever.

## Billing

- STT bills **per audio second**; TTS bills **per character**. Batch bills every
  file.
- **No published rate.** `gnani.ai/pricing` is a demo-booking form. `probe.py`
  measures it: read the dashboard balance, make one 1,000-character TTS call and
  one 10-second STT call, read the balance again.
- 5,000 credits per registration, no top-up path. Running out returns `402`
  mid-demo with no warning.
- Therefore: cache every TTS output by hash, keep spoken replies short, and give
  the harness a transcript cache so re-runs are free.

## Not available

No PSTN/SIP/number provisioning. No WhatsApp. No agent builder API. No word
timestamps. No live diarization. No translation. Evon v3.3 is open weights on
Hugging Face only (H100-class GPU, and its released checkpoint drifts to English
on Indic prompts).

## Measured results

8 clips, `hi-IN`, clean TTS audio degraded to 8 kHz µ-law + noise:

| audio | WER | CER |
|---|---|---|
| clean 16 kHz | 0.0% | 0.0% |
| 10 dB SNR | 3.6% | 2.9% |
| 5 dB SNR | 27.8% | 23.0% |
| 0 dB SNR | 93.5% | 88.9% |

Reproduce with `uv run python -m harness.cli`. At 0 dB the model does not merely
fail — it hallucinates plausible text, which is why the UI must ask for a repeat
rather than present the guess.
