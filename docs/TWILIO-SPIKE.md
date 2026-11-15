# Twilio Media Streams — spike

**Status:** closed, no-go for the 60-second video; go-later only with a US number.
**Timebox:** one session. **Account created:** none. **Calls placed:** none.

This is a spike, not a feature: the output is this document and the recommendation
at the end. It is the only file on this branch. No Twilio credentials, account
SIDs, phone numbers or production code are in it.

---

## The question

Gnani's API cannot receive a call — there is no PSTN, no number, no SIP
(`API-NOTES.md` §Not available). Twilio can receive one and forward the audio to
our websocket as 8 kHz µ-law. Our stack already speaks 8 kHz µ-law at both ends,
so the whole loop might fit without resampling. Nobody had checked.

Four questions, from #7:

1. Can we get a number at all, before the deadline?
2. What exactly arrives on the socket?
3. Does the round trip work — caller audio → Prisma → transcript, and reply text
   → Timbre → caller?
4. What is the real latency?

---

## Verdict, up front

| Recommendation | **No-go for tomorrow's video. Go only with a US number, as a post-submission pilot.** |
|---|---|
| Blocking reason | An Indian (+91) number cannot be provisioned before 15 Nov 18:00: Twilio's Regulatory Bundle review is quoted as "generally takes up to three business days, but in some regions it might take several weeks". A US number needs no bundle, but a +1 number in an Indian clinic demo is a visible tell. |
| Second reason | On a Trial account **only verified numbers can call in**. The demo's claim is "someone can call you"; on a trial that someone has to be a number you verified in the console first. That is fine for a rehearsal, not for a judge. |
| What is *not* blocking | The audio path itself. Both halves already speak 8 kHz µ-law, and the only new code is a re-framer plus a websocket handler. The bridge is a day of work, not a research problem. |

---

## What I tried, in order, and what happened

This machine has no Twilio account, no phone and no payment method, so the spike
could not place a call. Everything below is either a repository check (verifiable
here) or a primary-source check of Twilio's documentation (cited at the end).
Nothing here was measured on a live call, and the document says so at every
point where that matters.

### 1. Does Gnani already offer PSTN/SIP? — No

`API-NOTES.md` §Not available lists what the API does not have: PSTN/SIP/number
provisioning, WhatsApp, an agent-builder API. Re-checked against the repo, not
re-queried against the live API (no key on this machine).

**Consequence:** the number has to come from a carrier like Twilio.

### 2. Can our audio path accept 8 kHz µ-law without resampling? — Yes

| Need | Already in the repo |
|---|---|
| µ-law → PCM16 | `audio.ulaw_to_pcm16` (`backend/audio.py`) |
| PCM16 → µ-law | `audio.pcm16_to_ulaw` (`backend/audio.py`) |
| 8 kHz streaming mode, 64 ms frames | `MicSession(telephony=True)` sets `send_rate = 8000` and the telephony VAD preset (`backend/stt.py`) |
| µ-law TTS at 8 kHz | `gnani.tts(..., container="mulaw", rate=8000)` (`backend/gnani.py`, docstring: "Use container='mulaw', rate=8000 only for telephony") |
| G.711 round trip already exercised | `tests/test_audio.py`, `tests/test_degrade.py` |

**Consequence:** no resampling and no new dependency. The work is framing,
transport and the TwiML webhook.

### 3. Can we get a number? — US in minutes, India not by tomorrow

- Twilio numbers in regulated countries require a **Regulatory Bundle**: identity
  documents plus an address that satisfies the local requirement. Twilio's own
  getting-started page says the review "generally takes up to three business
  days, but in some regions it might take several weeks".
- India is one of those regulated countries, so a +91 number is behind that
  review. The submission is 15 Nov 18:00; there is no path to an approved Indian
  number in that window.
- A **US local number** has no such review. That is the only number obtainable
  today.

**Consequence:** the only call possible before the deadline is on a +1 number,
which is exactly the tell the demo cannot afford.

### 4. Can a stranger call a Trial number? — No

Twilio's trial documentation is explicit: trial projects can use only the
project's own Twilio number or a verified caller-ID as the `From` number, and
trial calls are capped at 10 minutes. Inbound calls to trial numbers must also
come from a **verified** number (errors 21264 and 32100 are the two faces of
this).

**Consequence:** a judge cannot dial the demo number. The demo would have to say
"call this number, but first verify your number in my Twilio console", which is
not a demo.

### 5. What arrives on the socket? — documented, not observed

Twilio's WebSocket-message reference defines the `media` message in both
directions: the audio is `audio/x-mulaw` at 8 kHz, base64-encoded, with no file
header bytes. The stream is opened by TwiML: `<Start><Stream>` is unidirectional
(fork for listening), `<Connect><Stream>` is bidirectional (what a relay needs —
it can play our reply back to the caller). Every message we send back must carry
the `streamSid` from the `start` event.

**Not observed:** no call was placed, so there is no captured frame to quote. In
particular, the widely repeated "160 bytes / 20 ms" figure is a convention, not a
contract — Twilio's docs say the audio in a media message may be any size. A
bridge must therefore **buffer and re-frame**, not assume a chunk size.

### 6. The frame arithmetic — the part that is checkable here

This is the only quantitative work the spike could complete, and it is exact:

| Quantity | Value | Where it comes from |
|---|---|---|
| Twilio inbound | 8 kHz **µ-law**, 1 byte per sample | Twilio docs (above) |
| Prisma streaming frame | **1024 bytes** of s16le mono = **512 samples** = **64 ms** at 8 kHz | `AGENTS.md` hard constraint 2; `audio.frames` |
| One 20 ms µ-law chunk (if that is what arrives) | 160 samples = 160 bytes | convention only |
| Added delay from re-framing | **0–64 ms**, average ~32 ms | buffering 512 samples before a send — arithmetic, not measurement |
| Sends per second | 15.625 | 1000 / 64 ms |

A 1024-byte frame is 3.2 conventional 20 ms chunks, so the sender must carry a
remainder across messages:

```
decode 160 B µ-law → 320 B PCM (160 samples)
acc  += 320 B
while len(acc) >= 1024: emit acc[:1024]; acc = acc[1024:]
```

The alternative — forwarding each 320-byte chunk as it arrives — violates the
1024-byte rule and, worse, sends 320-byte frames to a VAD that wants a steady
64 ms cadence (`AGENTS.md` constraint 2: never burst). Re-framing is mandatory.

---

## Does the round trip work?

**Not verified.** The shape is complete and every hop has a proven component, but
no call was placed, so the honest answer to question 3 is "unproven, and here is
why it should work":

```
caller ──PSTN──► Twilio number
                   │  <Connect><Stream url="wss://our-host/twilio">
                   ▼
        our aiohttp app  ── base64 → µ-law → PCM16 → 1024-byte frames ──► Prisma v3.0 (8 kHz, telephony VAD)
                   │                                                        │
                   │◄────────── reply text ─────────────────────────────────┘
                   ▼
        Timbre v3.0 (container=mulaw, 8000 Hz) → 160-byte chunks → base64 + streamSid → caller hears it
```

The pieces that do not exist yet, roughly:

1. A `POST /twilio/voice` route returning TwiML `<Connect><Stream …>`, and a
   `GET /twilio/ws` websocket handler next to the existing `/ws` — the same
   process, the same port (`DECISIONS.md` D-003).
2. A small `TwilioAudio` class, in the shape of `audio.frames`: decode, buffer,
   emit 1024-byte frames; and the reverse, cut µ-law into 160-byte chunks at a
   20 ms cadence with `streamSid` on each.
3. A `mark` after the last chunk of a reply (so "finished speaking" means
   "playback finished", not "bytes left the server"), and `clear` if the caller
   barges in — which half-duplex muting currently forbids anyway (`D-005`).
4. The webhook has to be reachable from the internet: an HTTPS tunnel whose URL
   goes into the number's voice configuration. That is a new deployment
   dependency this repo does not have today ("one process, one port", no tunnel).

---

## Latency

**Not measured.** No call was placed, so this section is a budget, not a result.
Saying it is measured would be the one thing the issue explicitly forbids.

| Stage | Clean path (measured today) | On a Twilio call |
|---|---|---|
| caller stops → VAD closes | 350 ms (`stt.headers`, laptop preset) | **450 ms** — the telephony preset raises `x-min-silence-ms` |
| model → transcript | 57–211 ms (D-004) | same model, same socket |
| caller → Twilio → our server | ~0 (mic is local) | **unmeasured**; one WAN leg each way, plus base64 decode |
| our server → caller | speaker, local | **unmeasured**; one WAN leg, plus carrier buffering |
| reply tap → first audio | 764 ms uncached, ~0 cached (`API-NOTES.md`) | worse by the WAN leg plus carrier jitter buffer; unmeasured |
| re-framing | — | 0–64 ms (arithmetic, above) |

The two `unmeasured` rows are the ones that decide the number, and they depend on
where the server sits relative to Twilio's edge. A number quoted now would be
invented, so there isn't one. If the spike resumes, measure these first: they are
the only unknowns left.

One thing the doc can say without measuring: a phone call does not remove the
350/450 ms VAD silence, so the floor is already ~450 ms + model latency before
any network is involved.

---

## Recommendation

**No-go for the 15 Nov video. Go, with a US number only, for a post-submission
pilot.**

Why the video is a no-go:

- A +91 number needs a bundle review measured in days to weeks; the deadline is
  tomorrow.
- A +1 number is obtainable, but "a US number rings in an Indian clinic" is a
  visible tell in exactly the frame the video is selling.
- Trial inbound is limited to verified caller numbers, so the "anyone can call
  this" demonstration is impossible without upgrading the account.

Why the pilot is a go:

- Nothing in the audio path needs research: both ends are 8 kHz µ-law, the
  codec and VAD modes already exist, and the only new code is a re-framer and a
  websocket handler — roughly a day, including the tunnel.
- A US number proves the loop end to end and produces the two missing latency
  numbers, which is what a follow-up issue should be written from.
- The Indian number is a paperwork problem, not an engineering one. Start the
  bundle on day one of any real pilot.

What would make this a **go for a demo** (not today): an approved Indian number,
or an upgraded account so an unverified phone can dial in.

---

## What this spike could not do, plainly

- Create a Twilio account, buy a number, or place a call: no account, no phone,
  no payment method on this machine.
- Capture 20 seconds of real call audio, and therefore quote a log line with
  frame sizes and a `track` value.
- Measure caller-stops-to-text or tap-to-first-audio over PSTN.
- Exercise KYC: no address documents were submitted, so the India timing above
  is Twilio's published review window, not this project's experience.

Those four gaps are the whole of what remains between this document and a
one-page result.

---

## Sources

Twilio, checked 14 Nov 2026:

- Media Streams, WebSocket messages — payload encoding, base64, no header bytes,
  `streamSid`, any-size messages:
  <https://www.twilio.com/docs/voice/media-streams/websocket-messages>
- Media Streams overview: <https://www.twilio.com/docs/voice/media-streams>
- TwiML `<Stream>` — `<Start>` unidirectional vs `<Connect>` bidirectional:
  <https://www.twilio.com/docs/voice/twiml/stream>
- Regulatory bundle review window:
  <https://www.twilio.com/docs/phone-numbers/regulatory/getting-started/console-create-new-bundle>
- Address requirements for number types:
  <https://help.twilio.com/articles/223182868>
- Trial restrictions (own number or verified caller-ID only, 10-minute cap):
  <https://help.twilio.com/articles/360036052753>
- Trial accounts can only call verified caller IDs (error 32100):
  <https://www.twilio.com/docs/api/errors/32100>
- Inbound calls to trial numbers must come from verified numbers (error 21264):
  <https://www.twilio.com/docs/api/errors/21264>
