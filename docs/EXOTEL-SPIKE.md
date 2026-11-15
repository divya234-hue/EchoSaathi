# Exotel AgentStream — real-call spike

**Status:** one real call placed and answered, 14 Nov 2026 ~20:42 IST. The
throwaway bridge is not merged and is not in the 60-second video. (The protocol
was later ported into the product as an opt-in pilot — `EXOTEL-BRIDGE.md`,
2026-11-15 — but this document stays the record of the first real call.) This document
is the output; the recommendation is at the end.

It exists because the Twilio spike ([`TWILIO-SPIKE.md`](TWILIO-SPIKE.md)) closed
with "no call was placed". Exotel gives an Indian trial number without
production KYC and a bidirectional WebSocket, so the audio path could be tested
for real before the deadline. It was.

---

## What was tested

A real Indian mobile call to an Exotel free-trial ExoPhone, routed by a
**Voicebot applet** over a static `wss://` URL to a throwaway bridge, then:

```
caller ──PSTN──► Exotel number ──Voicebot applet──► wss://<tunnel>/exotel/ws
  ── base64 PCM 16-bit 8 kHz ──► 400 ms buffer ──► 1024-byte frames / 64 ms
  ──► Prisma v3.0 (telephony VAD) ──► transcript
  ──► Timbre v3.0 (8 kHz PCM) ──► 3200-byte chunks / 200 ms ──► Exotel
  ──► caller hears the reply
```

No resampling on either side: both ends are 8 kHz PCM.

## The call, from the bridge log

Numbers and stream SID are redacted here; the local log has the full values.

```
[start] sid=… from=+91… to=+91… media_format={'encoding': 'base64',
        'sample_rate': '8000', 'bit_rate': '128kbps'}
[first media chunk] 320 bytes (chunk=1 ts=20)
[transcript] lang=hi-IN latency=110ms audio=3188ms
             text='Hello, मेरा नाम गौतम कुमार शर्मा है।'
[reply sent] 2.40s in 12 chunks
[transcript] lang=hi-IN latency=83ms audio=2464ms
             text='और आज हमारा appointment है।'
[reply sent] 2.40s in 12 chunks
[stop] … [closed] received=292800B sent_to_prisma=261120B session=21.0s
```

- 21.0 s call; 292,800 B = **18.3 s** of caller audio received (8 kHz, 16-bit).
- Two turns, code-mixed (`Hello` + Hindi, `appointment` + Hindi); Prisma
  reported `hi-IN` for both.
- The reply was 2.40 s of Timbre audio, sent as 12 × 3,200-byte chunks (200 ms
  each). **The caller reported hearing both replies on the handset.**
- The second transcript was produced *while* the first reply was playing — the
  throwaway bridge has no half-duplex. That is a real finding, not a surprise:
  the app's mute guard lives in `Call.on_reply`, which this bridge does not use.

## What actually arrived on the socket

| Property | Observed | Exotel docs |
|---|---|---|
| Audio | base64 **raw PCM, 16-bit signed LE, mono** | raw/slin, base64 |
| Sample rate | 8,000 Hz; `bit_rate` 128 kbps | 8 kHz default, 16/24 kHz optional |
| Inbound chunk | **320 bytes (20 ms)**, `chunk=1`, `ts=20` | 3.2 kB–100 kB, multiple of 320 (that floor is for media **sent to** Exotel) |
| `start` | `stream_sid`, `from`, `to`, `media_format` | same |
| Events seen | `connected`, `start`, `media`, `stop` | also `mark`, `dtmf` (not exercised) |
| Media we send | `{"event":"media","stream_sid":…,"media":{"payload":…}}` | same |

Two details a bridge has to get right:

1. `media_format.encoding` said **`base64`**, not the `audio/x-raw` in Exotel's
   sample. The payload is base64 PCM either way; do not branch on the field.
2. Inbound chunks are **20 ms**, so the 1024-byte Prisma frame (64 ms = 3.2
   chunks) needs buffering. The bridge buffered 400 ms and emitted one frame
   every 64 ms. Forwarding each 320-byte chunk as it arrived would violate the
   1024-byte rule and burst the VAD.

## Latency — do not quote this as the product's

| Observed | Time |
|---|---|
| WebSocket accept → `start` | 0.62 s |
| `start` → Prisma socket open | **2.2 s** |
| First media chunk | 320 B at 2.85 s |
| First transcript | 8.56 s |
| Timbre reply | 2.40 s of audio in 12 chunks |

The 2.2 s Prisma handshake plus the 400 ms buffer dominate this run, and the
caller had already been speaking during the handshake. **The app's 450–600 ms
caller-stops-to-text is not what this test measured**, and the two WAN legs are
still unmeasured — the call proves they work, not how fast. A production bridge
would pre-connect Prisma and buffer less.

## Setup that was used

1. Free trial at <https://my.exotel.com/auth/register>: 7 days, free credits,
   **1 trial ExoPhone assigned automatically**, inbound calls supported,
   outbound only to whitelisted numbers (max 10), no production KYC. The
   caller's mobile was whitelisted; it was not asked for a PIN.
2. App Bazaar flow with the **Voicebot applet**, static URL
   `wss://<tunnel-host>/exotel/ws?sample-rate=8000`, attached to the trial
   number's incoming calls. The applet also accepts an https URL that returns
   `{"url": "wss://…"}`; the static form was enough.
3. `ngrok http 8090`, then a throwaway aiohttp bridge: echo mode first (caller
   heard their own voice), then Prisma + Timbre mode.
4. Call from the whitelisted mobile.

Trial limits (docs checked 14 Nov 2026): 7 days, 1 trial number, no production
numbers, no KYC needed for the trial (KYC unlocks production), inbound limited,
outbound only to whitelisted numbers. Unregistered callers may be asked for a
PIN; the registered caller was not.

## What this proves, and what it does not

**Proves:** a real Indian mobile call reached our server through Exotel; the
8 kHz PCM path, the 20 ms framing, the 1024-byte Prisma re-framing and the 8 kHz
Timbre reply all work together; Prisma transcribes Hindi and code-mixed speech
on a real line; the caller hears the reply.

**Does not prove:** the app page, the summary card, retry or the demo toggles
(the bridge prints transcripts and speaks one fixed reply); half-duplex (the
second transcript arrived during the first reply); the 450–600 ms / 764 ms
numbers; a judge-dialable number; production KYC; the two WAN latency legs.

## Recommendation

**No-go for the 15 Nov video. Go, post-deadline, as a pilot.**

Why not the video:

- The page is not wired to the bridge; a video of the app would still be the
  simulated mic line.
- The trial number is not judge-dialable in any meaningful sense: inbound is
  limited, unknown callers may need a PIN, and the number expires after 7 days.
- Putting a real call on camera would change the script, the casting and the
  post's "caller in the room" line, one day before the deadline.
- The demo's measured claim (3.6% WER on the simulated line) is already scripted
  and auditable; the real call adds credibility to the *post*, not to the video.

Why the pilot is a go:

1. Wire the bridge into the normal call state so the page shows the transcript,
   the status pill and the summary card (the bridge and `/ws` share one `Call`).
2. Add half-duplex or use Exotel's `clear` so the caller's audio does not keep
   transcribing under the reply.
3. Pre-connect Prisma and shrink the 400 ms buffer; then measure
   caller-stops-to-text and tap-to-first-audio with a stopwatch and the log.
4. Get a production Indian number: Exotel KYC, or the same trial line upgraded.
5. Then decide whether the real call replaces the simulated one in the product
   demo.

## The honest post line

The submission post can say, without touching the video:

> We also tested the relay on a real Indian phone call: the caller's Hindi
> arrived as text and the reply was heard on the handset. The demo video uses a
> simulated line because a trial number only accepts registered callers.

That is true for the audio path; the app page and summary were not part of this
call. The sentence says "relay", not "app", for that reason.

## Sources

- AgentStream overview: <https://developer.exotel.com/docs/agentstream/overview>
- WebSocket protocol (events, audio, chunks):
  <https://developer.exotel.com/docs/agentstream/websocket-protocol>
- Voicebot applet (static WSS URL, bidirectional audio):
  <https://docs.exotel.com/exotel-agentstream/voicebot-applet>
- Trial account:
  <https://developer.exotel.com/docs/getting-started/trial-account>
- Sample bridge: <https://github.com/exotel/Agent-Stream>

No credentials, phone numbers or account SIDs are in this document or in the
repository. The throwaway bridge was not committed; it is a spike, not product
code.
