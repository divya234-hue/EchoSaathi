# Architecture

Two processes in development, one in production. The split is not stylistic: the
API key must not leave the server.

There are two audio paths, and they differ in *where* the microphone and the
speaker are. The demo path puts both on the server (D-004). Talk mode
(`?mode=talk`, D-004 amendment) puts both on the phone so the user can hold it
between themselves and another person in the same room.

## Topology — the demo path (microphone on the server)

```
        caller (a person in the room, or a recorded clip)
                    │ voice
                    ▼
  ┌──────────────────────────────────────────┐
  │ LAPTOP / SERVER                          │
  │                                          │
  │  sounddevice mic ──► stt.MicSession      │
  │                          │ 1024-byte PCM │
  │                          ▼               │
  │                  Prisma v3.0 (wss)       │
  │                          │ transcript    │
  │  server.Call ◄───────────┘               │
  │      │  ▲                                │
  │      │  └── reply text ◄─────────────┐   │
  │      ▼                               │   │
  │  tts.speak ──► Timbre v3.0 (SSE) ──► speaker │
  └──────────────────┬───────────────────┼───┘
                     │ JSON over WebSocket│
                     ▼                    │
  ┌──────────────────────────────────────┴───┐
  │ PHONE / BROWSER: React app                │
  │  big text · reply chips · composer · pills │
  └───────────────────────────────────────────┘
```

In this mode the phone renders and sends replies. It captures no audio, so it
needs no HTTPS, no microphone permission and no tunnel — plain
`http://<lan-ip>:8080` works, and the reply comes out of the laptop's speaker.

## Topology — talk mode (microphone and speaker on the phone)

> ```
>   PHONE / BROWSER                              LAPTOP or VM (no audio I/O)
>   ┌──────────────────────────┐                ┌────────────────────────────┐
>   │ getUserMedia (48 kHz)    │                │  BrowserMic.feed            │
>   │ AudioWorklet → 16 kHz    │  1024-byte     │      │ FrameParser          │
>   │ 1024-byte frames ────────┼───binary──────►│      ▼ 32 ms pump           │
>   │                          │   over wss     │  Prisma v3.0 (wss)          │
>   │ Web Audio plays Timbre ◄─┼──base64 PCM───┤  Call.on_reply → tts        │
>   └──────────────────────────┘   `audio`      └────────────────────────────┘
> ```
>
> The server must be reachable but is not in the room: `sounddevice` is never
> opened, so a headless box or a remote VM works. The page needs a **secure
> context** (`https://` or `localhost`) for `getUserMedia`.

## Topology — the carrier pilot (a real phone line, opt-in)

```
   mobile ──PSTN──► Exotel ──wss /exotel/ws──► CarrierCall ──► Prisma v3.0
                      ▲                            │
                      └──── base64 8 kHz PCM ◄── Timbre v3.0 (the page's reply)
                                                   │
   PHONE / BROWSER: one page ◄── `carrier`, `transcript`, `speak`, `summary` ──┘
```

This leg is **off unless `EXOTEL_WS_TOKEN` is set**; without it `/exotel/ws`
answers 503. It exists because the owner wants to ship the real-call pilot, and
it cannot touch the demo path: the demo uses the server microphone, the carrier
bridge binds only to the latest open page and refuses a second call. See
[`EXOTEL-BRIDGE.md`](EXOTEL-BRIDGE.md) and D-014's second amendment.

## Request path, in order
2. `stt.MicSession` pushes them to the asyncio loop and sends them at real-time
   cadence (32 ms at 16 kHz) to `wss://api.vachana.ai/stt/v3/stream`.
3. Prisma closes a VAD segment when it hears ~350 ms of silence and returns one
   final transcript. There are no interim results.
4. `server.Call.on_transcript` appends the line, pushes it to the page, and
   starts a best-effort chip request for that line (see below).
5. The user taps a chip or types; the page sends `{"type":"reply","text":…}`.
6. `tts.speak` streams Timbre SSE into a `RawOutputStream`, so audio starts
   before synthesis finishes. Cached clips replay from disk in ~0 ms. The
   language is `Call.reply_lang` — the caller's last detected one. In talk
   mode `tts.stream_pcm` feeds the same SSE stream to the page as `audio`
   messages and Web Audio plays it on the phone.
7. `Call.on_reply` reports `speak` with the measured time-to-first-audio and the
   language used.

## Module ownership

| Module | Owns | Must not |
|---|---|---|
| `server.py` | HTTP + `/ws`, call state, half-duplex muting, the talk-mode handshake | do audio DSP |
| `stt.py` | microphone, frame cadence, Prisma socket, `FrameParser`/`BrowserMic` for talk mode | know about TTS |
| `llm.py` | the chip and card model calls (OpenCode Go), the stable session header, JSON parsing | ever raise into `Call`, or log the key |
| `exotel.py` | the carrier leg: Exotel AgentStream framing, the page binding, the hangup attempt | log a phone number or a call SID, or run without the token |
| `chips.py` | the caller-language table for "please repeat" / "a little slower", the 3-chip cap | call the network |
| `web/src/talk.ts` | AudioWorklet capture (16 kHz, 1024-byte frames) and Web Audio playback | call Gnani, or hold API state |
| `tts.py` | Timbre SSE, speaker playback, cache | know about the microphone |
| `audio.py` | frame maths, G.711 codecs | own state |
| `gnani.py` | HTTP calls, retries, key loading | touch audio devices |
| `harness/degrade.py` | simulating a phone line | call the network |
| `harness/wer.py` | normalisation, WER/CER | call the network |

`gnani.py` is the only module that talks to the API over HTTP. `stt.py` is the
only module that opens the streaming socket. Keep both true.

## WebSocket protocol

One socket at `/ws`, JSON both ways. `web/src/types.ts` is the source of truth.

| Direction | Message | Meaning |
|---|---|---|
| server | `hello` | model names, the call mode (`server` \| `talk`), microphone availability, voice mode and whether the stream is phone-line degraded |
| server | `transcript` | one final caller sentence, with language and latency |
| server | `suggest` | 3 reply chips in the caller's detected language: one direct answer, then "please repeat" and "a little slower". Absent when the model is unavailable or slow, so the page keeps its static chips |
| server | `retry` | a segment was too short or too noisy to trust; the caller is asked to repeat |
| server | `status` | `idle │ listening │ thinking │ speaking` |
| server | `speak` | a reply finished, with `ttfa_ms` and `cached` |
| server | `voice` | this call switched to `default` or `cloned` |
| server | `cloned_voice` | the same switch in the demo toggle's older shape (#21); mirrors `voice` so the switch survives a reload |
| server | `phone_line` | the microphone transform switched on or off; the page socket stays up (#32) |
| server | `summary` | end-of-call artefact: who called, what was agreed, what happens next; also written to `cache/summary.json`. The first one is extractive and instant; a second with the same shape may follow with `who/agreed/next` rewritten (same facts, UI language) |
| server | `audio` | talk mode: one base64 s16le chunk of the reply (16 kHz mono); `final: true` with empty data marks the end of the stream |
| server | `carrier` | a real inbound call is live on this page (`from` is the masked last four digits) or has ended; while live, its audio is the capture source and the room microphone is closed |
| server | `capture` | talk mode: `ready` once the Prisma session is open and the page may send frames; `stopped` after the call ends, so the page releases the microphone; `error` if Prisma could not open |
| server | `error` | human-readable failure, shown in a pill |
| client | `reply` | speak this text down the line |
| client | `start_capture` | talk mode's "Start listening" gesture: open the Prisma session, then answer `capture` |
| client | `set_voice` | switch this call between `default` and `cloned`; the server answers with `voice` and `cloned_voice` |
| client | `set_cloned_voice` | the demo toggle's older shape (#21); equivalent to `set_voice` |
| client | `set_phone_line` | switch the mic's phone-line transform for this call; answers `phone_line` |
| client | `end_call` | end the call for real: tell the page to stop capturing (talk mode), close the microphone and the Prisma socket, then answer `summary`. Nothing that arrives afterwards is transcribed or spoken |
| client | `new_call` | drop this session and start a fresh one with an empty transcript; server mode reopens the microphone, talk mode waits for a new `start_capture` gesture |

Every server message is additive: the UI ignores unknown `type` values, so
adding one does not require a coordinated deploy.

## Half-duplex

The microphone hears the speaker. Without a guard, the app transcribes its own
reply and shows it as the caller talking — an echo loop that is obvious on
camera. `Call.on_reply` therefore sets `mic.muted = True` for the duration of
playback, and `stt.MicSession.pump` sends digital silence instead of captured
audio while muted.

Talk mode needs both halves of the same rule, because the speaker is now in the
same hand as the microphone:

- **Server:** `BrowserMic._pump` sends silence while `muted`, which covers the
  window in which chunks are being sent to the page.
- **Page:** `talk.ts` drops outgoing frames (`setMuted(true)` on
  `status: speaking`) until the Web Audio player drains the last chunk, so the
  phone's own speaker output is never captured or sent. The drain callback is
  what re-opens it; a `status: listening` with an empty player is the fallback.

Consequence, accepted: the user cannot barge in, in either mode. Real echo
cancellation is out of scope for this build.

## Talk mode and HTTPS

`getUserMedia` and `AudioContext` need a **secure context**. `http://<lan-ip>:8080`
is not one, and the page's websocket becomes `wss://` when the page is `https://`
(`web/src/ws.ts` derives it from `location.protocol`). The chosen path is the
**ngrok tunnel**, documented in [`TALK-MODE.md`](TALK-MODE.md); `server.py --tls
cert.pem key.pem` serves HTTPS itself for a phone that already trusts a local
certificate, and `localhost` is a secure context for a desktop check.

Consequences, accepted and documented: a permission prompt the user must accept
once per origin; the tunnel URL changes on every restart, so the origin (and the
stored microphone permission) changes with it; iOS Safari needs the
`AudioContext` created/resumed inside the tap that starts listening, which is why
"Start listening" is a button and not an automatic start; and the first Prisma
handshake is ~2 s, so frames sent during it are queued (up to
`BROWSER_QUEUE_FRAMES` = 4 s) rather than dropped.

## Multiple users

State is per websocket, not per process: `ws_handler` builds one `Call` per
connection, and nothing in it is broadcast, listed or looked up by anyone else.
Two pages open two independent transcripts with two Prisma sessions — the
product does not show one person's call to another.

What *is* shared, deliberately:

- **The machine's microphone**, in server mode. Two pages on the demo URL open
  two capture sessions on the same device and hear the same room. That is the
  demo's topology, not a distribution model; talk mode gives every phone its own
  microphone.
- **`cache/summary.json`**, the last card written. It is an artefact for the
  demo; no page reads it and it is never sent to another page.
- **The TTS cache**, keyed by (text, voice, model, rate, language), so a shared
  clip is identical audio, not shared call data.

There is no auth, no database and no call registry (AGENTS.md, "Do not add").
A real multi-user deployment therefore runs one instance per user or room and
puts the routing in front of it; it must not be built by adding a global call
list to this process.

## Reply chips and the reply language

The chips are for the **caller's** language, not the UI locale. After a
transcript, `Call.offer_suggestions` asks the chip model (`llm.py`,
[`LLM-NOTES.md`](LLM-NOTES.md)) for one short direct answer in
`detected_language_code`; `chips.py` puts it first and appends the two safety
options from a reviewed table for that language. The request runs off the
message path, is capped at 6 s, and is cancelled when a newer line arrives. If
it fails, **no `suggest` message is sent** and the page shows `m.chips`, the
static locale row, exactly as before the feature.

The reply is spoken in `Call.reply_lang`, the caller's last detected language,
not the UI locale (D-012). `tts` takes `lang` through `speak`/`stream_pcm` and
`_sse_stream`, and the cache key includes it. `vachana-vc-v1` (the clone) takes
an embedding and no language, so a cloned reply is Hindi by construction: a
non-Hindi reply uses the default Timbre voice, which speaks all ten languages
(`tts.effective_mode`).

## End-of-call card

`Call.end_call` sends `build_summary` — a pure function over the transcript, so
the same call always yields the same card — **before** anything else. If
`llm.available()` (and `SUMMARY_LLM` is not `0`), it then asks the chip model for
`who/agreed/next` in the **UI locale** (`end_call.lang`, the card is for the
user, not the caller), merges only non-empty fields over the extractive ones,
and sends a second `summary` with the same shape. The page already replaces the
card on a second `summary`, so nothing in the UI changes. A slow or dead model
means the first card stays, and `SUMMARY_LLM=0` is the demo's switch back to the
deterministic card.

## Phone-line simulation

`server.py --phone-line` (or `PHONE_LINE=1`) passes `telephony=True` to
`stt.MicSession`. Capture stays at 16 kHz; the socket header asks for 8 kHz; and
every captured frame goes through `harness/phone_line.py`, which bands to
300–3400 Hz, decimates to 8 kHz, adds noise at 10 dB SNR and round-trips G.711
µ-law.

The 1024-byte rule is unchanged — only what a frame *represents* changes: two
16 kHz frames (2 × 32 ms) make one 8 kHz frame (64 ms), so the class buffers and
emits one frame per two received. The mode is fixed for the life of the socket;
switching it mid-call would require a different `x-sample-rate` and thus a new
connection.

## Latency budget (measured)

| Stage | Typical |
|---|---|
| caller stops → transcript on screen | 450–600 ms (350 ms VAD silence + ~100 ms model) |
| user taps → first audio, uncached | ~760 ms |
| user taps → first audio, cached | ~0 ms |
| streaming frame cadence | 32 ms per 1024-byte frame |

These are the only numbers that belong in a demo. Anything else is an adjective.

## Failure modes and what the app does

| Failure | Behaviour |
|---|---|
| no API key | `gnani.py` exits at import with instructions |
| no microphone | `hello` carries `mic: false`, UI shows a red pill |
| TTS 500 (happens on valid input) | `gnani._request` retries 3× with backoff |
| 429 rate limit | same retry path, then surfaces an `error` message |
| credits exhausted (402) | surfaces `error`; nothing else can be done locally |
| socket drops | `web/src/ws.ts` reconnects with backoff; mic session restarts |
| talk mode, microphone refused | page shows `microphone blocked`; the server side never opened a device |
| talk mode, no HTTPS/localhost | page refuses before prompting and says the mode needs a secure context |
| talk mode, browser without AudioWorklet | page says the browser cannot capture; nothing is sent |
| chip model slow, dead or no key | no `suggest` message; the static locale chips stay on screen and the reply still works |
| card model slow, dead or no key | the extractive card is already on screen and is the one the user keeps |
| carrier bridge, no `EXOTEL_WS_TOKEN` | `/exotel/ws` answers 503; the app is exactly the demo build |
| carrier call, no page open / page has ended | 409, no Prisma session opened, no credits spent |
| carrier call while one is live | 409; one call, one page (no accounts in this build) |
| carrier hangup POST fails or is unconfigured | the media socket still closes (the session ends); the PSTN call is not guaranteed to drop — the UI never claims it did |
| cloned voice, non-Hindi reply | a `speak` with `lang: bn-IN` (say) uses the default Timbre voice, because the clone has no language parameter |
