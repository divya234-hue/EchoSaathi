# Demo — 60 seconds

The submission is a video and a post, judged on engagement and on whether the
claims survive a look at the repository. This file is the shoot script: someone
who has never seen Pashyanti should be able to record the video from it without
asking a question.

Two rules decide every choice below.

1. **Nothing in the video that this repository cannot reproduce.** If a number is
   on screen, its source is in [Numbers](#the-numbers-and-where-they-came-from).
2. **The first three seconds name a person and a failure, not the product.**
   The hook is burned in as text at frame 1 — LinkedIn autoplays muted — and the
   product appears at 0:05.

Related: [`ARCHITECTURE.md`](ARCHITECTURE.md) (the latency budget),
[`API-NOTES.md`](API-NOTES.md) (what the models actually do),
[`DECISIONS.md`](DECISIONS.md) (why the build looks like this).

---

## The claims the video has to carry

| # | Claim | Evidence |
|---|---|---|
| 1 | The caller's speech becomes large live text on the user's screen | `web/src/App.tsx` — `transcript` → caller bubble |
| 2 | A tap becomes speech down the line, optionally in the user's cloned voice | `server.Call.on_reply` → `tts.speak(mode="cloned")` |
| 3 | On a simulated phone line the text still lands | 3.6% WER at 10 dB SNR, `pashyanti/backend/harness_report.json` |
| 4 | When the audio is unusable it asks for a repeat instead of guessing | `stt.looks_unusable` → `{"type":"retry"}` |
| 5 | The call ends as a record, not a chat | `server.build_summary` → `SummaryCard` |

Claim 4 is the differentiator. Most transcription demos show a good sentence;
this one shows what happens when the model is not sure, because showing a guess
to a Deaf user is worse than asking.

---

## Cast and consent

- **The user** — the person we follow, holding the phone. If the story is
  someone's real story, they are on camera and have agreed to it; if it is a
  composite, the video caption says **"a re-enactment"** *and* the post says so
  after its first line. Do not invent a biography a judge can disprove. The
  cloned-voice reference must be the on-camera person's own recording; for a
  composite, it must be the performer's — never a third voice.
- **The caller** — a Hindi speaker in the same room, reading the lines in
  [The call script](#the-call-script). This is a live performance, **not** a
  recording of a real call; no real call audio is used (`AGENTS.md`).
- All names in this document (Meera, Dr. Mehra) are fictional placeholders.
  Keep them fictional or replace them with the real person's, never half-way.
- No Aadhaar number, PAN, account number, real phone number or API key is ever
  visible. Not in a frame, not in a terminal, not in a reflection.

---

## Pre-flight (T−20 minutes)

Run all of this before the camera is on. Every item has a failure mode that is
expensive to discover mid-take.

### 1. Serve the built app, not the dev server

```fish
cd pashyanti/web && ../../scripts/with-cache.sh bun run build   # must end clean
cd ../backend && ../../scripts/with-cache.sh uv run python server.py
```

The `with-cache.sh` wrapper keeps bun/uv caches out of `/tmp`, which is a 3.6 GB
tmpfs on the demo machine; filling it breaks every shell command. The server
serves `web/dist` at `http://0.0.0.0:8080` on the LAN. If the page says
"Frontend not built yet", the build did not run — stop and fix it rather than
shooting the dev server (#14 lists this as a blocker).

### 2. Build the cloned voice and restart the server

```fish
cd pashyanti/backend
uv run python clone_voice.py build ref.wav   # 5–30 s, one speaker, clean
```

`ref.wav` must be the **user's own voice**, recorded before the shoot, one
speaker, no music. A cloned voice that is not the person on camera is the one
thing a judge will spot, and it makes beat 7 a lie.

This writes `pashyanti/backend/embedding.json`. `tts.EMBEDDING` is loaded **at
import**, so restart the server afterwards. Check without printing the
embedding:

```fish
uv run python -c "import tts; print('clone:', tts.has_clone())"
```

If it prints `False`, the `मेरी आवाज़ / my voice` switch answers with the error
pill `no cloned voice on this server` instead of speaking. That is a re-shoot,
not a take.

### 3. Leave the two live replies uncached for the first take

`tts.py` caches by text hash, so a reply spoken once replays from disk in ~0 ms
(`ARCHITECTURE.md` §Latency budget). The video quotes **764 ms to first audio**;
that figure describes an uncached reply, so do not warm the two replies you
record before the first good take. After a take you are happy with, warm them
and the retakes are instant.

### 4. Phone

- Same LAN as the server; open
  `http://<lan-ip>:8080/?lang=hi&theme=light` — the query overrides a saved
  locale, so every take starts in the same state.
- **Add to Home Screen** and open from the icon: fullscreen, no browser chrome,
  no address bar in frame.
- Do Not Disturb on, notifications off, auto-lock off, brightness maximum,
  auto-brightness off. A banner or a dim screen ruins the take.
- Delete other tabs and other home-screen pages from the shot.

### 5. Locale and theme

- Language: **हिंदी**, forced with `?lang=hi` before recording; do not open the
  globe picker on camera. The caller speaks Hindi and the chips are then Hindi
  sentences, so the spoken reply is Hindi text spoken by a Hindi voice. English
  lives in the edit, as burned-in subtitles — not in the UI, and never as a
  second take.
- Theme: **Peacock, light**. The toggle is never shown (`DECISIONS.md` D-010).
- This is a read-aloud product for a Hindi-speaking user; do not mix locales
  between beats. The UI language does not change recognition (`D-012`).

### 6. Room

- One person on camera, one caller just off-camera, one person behind the
  camera counting beats.
- Phone on a stand at chest height, vertical, 9:16.
- The caller hears the reply from the same speaker the camera hears: there is no
  earpiece and no second line. That is why `Call.on_reply` mutes the microphone
  while the reply plays (`DECISIONS.md` D-005) — without it the app transcribes
  its own voice.
- Record the room, not two separate takes. The caller's voice and the app's
  reply must be in the same acoustic space or the cut sounds staged.

### 7. Checks, once, with the camera off

- [ ] Page loads from `http://<lan-ip>:8080/?lang=hi&theme=light` on the phone,
      fullscreen.
- [ ] Header pill reads `तैयार`, mascot idle, no red pill.
- [ ] `फ़ोन लाइन` off at the start of the take.
- [ ] `मेरी आवाज़` off at the start of the take.
- [ ] `embedding.json` exists and `tts.has_clone()` is `True`.
- [ ] One throwaway sentence transcribes and one throwaway reply speaks.
- [ ] Decide the card: **the extractive card is instant and always appears; a
      model-written rewrite of `who/agreed/next` follows ~2–3 s later** in the UI
      language. Both are true to the transcript. If the take needs the exact
      deterministic wording in the beat sheet, start the server with
      `SUMMARY_LLM=0` (same shape as `PHONE_LINE=1`) and only the first card
      appears.
- [ ] After that sentence, the chip row may replace itself with **caller-language
      chips** (one direct answer, then "please repeat" and "a little slower")
      about 2.5 s later. For a Hindi caller the row always contains
      **थोड़ा धीरे बोलिए।**, so beat 4's tap exists either way. If the chip model
      is slow or offline, the static हिंदी row stays and the take is still valid —
      this is an enhancement, not a beat, and nothing on screen depends on it.

---

## The call script

Say exactly these lines. The summary card is computed from the transcript
(`server.build_summary`), so the sentences below are also the card's copy:
`who` is the **first** caller line, `agreed` the **last** caller line, `next`
the **last** reply the user spoke.

| Line | Who | Hindi | English gloss | Feeds |
|---|---|---|---|---|
| A1 | caller | नमस्ते, मैं डॉ. मेहरा की क्लिनिक से बोल रही हूँ। | Hello, I'm calling from Dr. Mehra's clinic. | `who` |
| U1 | user (chip **थोड़ा धीरे बोलिए।**) | थोड़ा धीरे बोलिए। | A little slower, please. | — (motivates A2) |
| A2 | caller | *repeat A1 word-for-word, a little slower* | — | the phone-line A/B |
| A3 | caller | कल सुबह दस बजे का अपॉइंटमेंट खाली है। | Tomorrow at 10 a.m. is free. | — |
| U2 | user (typed, cloned voice) | हाँ, कल सुबह दस बजे आ जाऊँगी। | Yes, I'll come tomorrow at 10. | `next` |
| A4 | caller | ठीक है, दस बजे मिलते हैं। | Okay, see you at 10. | `agreed` |

A1 is under the 60-character cap `_shorten` applies, so the card's title is the
whole sentence. A2 must be word-for-word identical to A1 or the comparison in
beat 5 is not a comparison — rehearse it with the caller until it is. U2's verb
agrees with the person on camera: `आ जाऊँगी` (female) or `आ जाऊँगा` (male).
Keep the persona, the chip and the cloned reference consistent; a female
persona with a male verb is the kind of detail a Hindi-speaking judge hears.

### Opening line — write it ten times, shoot three

The opening names a person and a failure. It never names Pashyanti. Candidates,
in the order worth trying:

1. **"The clinic called at 9:04. Meera watched the phone ring, and could not
   answer it."** — concrete time, concrete failure, no product. Recommended.
2. "Meera cannot hear. So when the clinic calls, her brother answers."
3. "Every call Meera receives is a call someone else has to make for her."
4. "Meera lost her hearing at 34. The phone became a locked door."
5. "This is what a phone call looks like when you cannot hear it." — weakest:
   it promises the product, not the person.
6. "My uncle lost his voice to cancer. His phone has been silent since."
7. "My neighbour is Deaf. Every call she makes goes through someone else's
   mouth."
8. "My father can't hear on the phone. My mother translates, every time."
9. "My student is Deaf. She doesn't need an interpreter for a call — she needs
   the words."
10. "My friend has cerebral palsy. People hang up before she finishes typing."

Use only a line that is literally true about someone you know, with permission
to name and film them. If none is true, use the composite persona and label the
post a re-enactment — do not present a fictional person as a real one.

Pick in the edit, with the sound on. The best line read once beats the perfect
line read five times.

---

## Beat sheet

Sixty seconds, no slack. Each beat is one idea; if a beat runs long, cut a word
from the voiceover, never a frame from the transcript.

| # | In–out | On screen | On the soundtrack | Line (voiceover / burned-in subtitle) |
|---|---|---|---|---|
| 1 | 0:00–0:05 | Camera: a phone face-down in two hands. **Hook burned in at frame 1.** | Room tone only | Burned-in + voiceover: "The clinic called at 9:04. Meera watched the phone ring, and could not answer it." |
| 2 | 0:05–0:11 | The phone turns over onto the empty state: Sakhi idle, "सामने वाले की बात यहाँ पढ़िए". | UI, quiet | "This morning, she answered it herself." |
| 3 | 0:11–0:19 | The caller's bubble grows in the transcript, `hi-IN · <latency> ms` under it. The mascot is **still** and the pill reads `तैयार` on this first turn — the arcs only start after the first reply; the bubble is the cue. | Caller speaking, live | "Their voice becomes text — in about half a second." |
| 4 | 0:19–0:25 | She taps **थोड़ा धीरे बोलिए।** — the static chip, or the same option in the caller-language row if the chips have replaced themselves; the reply bubble appears after the audio; the beak opens while it speaks. | Her voice through the speaker | "Her tap becomes a voice." |
| 5 | 0:25–0:34 | Thumb flips **फ़ोन लाइन**; the caller repeats A1, a little slower; a second, near-identical bubble lands. Lower third: `8 clips · 3.6% WER · 10 dB · 8 kHz µ-law`. | Caller, live; the degradation is server-side and is **not** audible in the room | "Same sentence, on a bad line. Eight clips: 3.6% word error at 10 dB." |
| 6 | 0:34–0:39 | A short noise burst at the mic. The `?` disc, then "समझ नहीं आया — दोहराइए". Hold ≥ 2 s. | Room | "When it isn't sure, it asks — it does not guess." |
| 7 | 0:39–0:47 | Caller: **"कल सुबह दस बजे का अपॉइंटमेंट खाली है।"** — the bubble clears the retry card. She flips **मेरी आवाज़**, taps **बोलिए** on the pre-filled U2; the reply is spoken in her cloned voice. | Caller, then her cloned voice | "The appointment is free. She says yes — in her own voice." |
| 8 | 0:47–0:55 | Caller says A4; text lands; she taps **कॉल खत्म करें**; the summary card slides in — `who` (A1), `agreed` (A4), `next` (U2), then `<turns> बार · <duration>`. Hold the card: about two seconds in, the model may replace those three lines with its own wording of the same facts (or not, if `SUMMARY_LLM=0`). Either card is honest; do not cut between them. | Caller, then UI | "And the call ends as a record, not a chat." |
| 9 | 0:55–1:00 | End card: **Pashyanti · Prisma v3.0 + Timbre v3.0**, then `3.6% WER · 764 ms`, the limitation line, the repo URL. | One music sting | "Overlapping speech still breaks it. You can't interrupt the reply." |

**Total: 5 + 6 + 8 + 6 + 9 + 5 + 8 + 8 + 5 = 60 s.**

Beat 5 says the WER out loud; beat 9 puts both numbers on the end card and
repeats the limitation. Nothing else in the video is a measurement, and nothing
in the video is a measurement without a row in
[the numbers table](#the-numbers-and-where-they-came-from).

### Timing inside the beats

- **0:11** starts on the caller's first syllable, not before it. Trim the breath.
- **0:25** flip the toggle after U1 has finished cleanly and before the caller
  starts A2; the server rebuilds the upstream Prisma socket and loses about one
  VAD segment (`Call.set_phone_line`), so cut the dead air in the edit but do
  not fake the transcript: A2 lands on its own.
- **0:34** the retry card is a heuristic; hold it ≥ 2 s, and it clears on the
  next transcript — A3 at 0:39.
- **0:39** A3 lands and clears the retry card; then the clone toggle. U2 is
  typed **before the recording starts**, so the keyboard never appears on
  camera; only the filled composer and the tap are in frame. The composer keeps
  its draft through the phone-line rebuild and the retry notice.
- **0:47** end the call only after A4 has landed, or `agreed` will be A3.

---

## Shot list

Two kinds of footage, cut together. Keep them visually distinct so the audience
knows which is the screen and which is the room.

| Shot | Source | Phone in hand? | Why |
|---|---|---|---|
| S1 hands, phone face-down + hook | camera, close, 60 fps | **yes** | opens on a person, not a product; the hook is burned in at frame 1 |
| S2 the empty state | phone screen recording | no | the frame a judge sees before any words |
| S3 caller speaking + bubble | phone screen recording | no | the transcript must be legible at 1080×1920 |
| S4 tap the chip + reply | phone screen recording, plus a cutaway of the thumb | thumb cutaway **yes** | the tap is the interaction; show the finger once |
| S5 phone-line toggle + repeat | over the shoulder, screen and thumb in frame | **yes** | the switch is a physical act, not a setting |
| S6 retry notice | phone screen recording | no | hold ≥ 2 s, no cursor over the card |
| S7 A3 + cloned-voice toggle + pre-typed reply | over the shoulder | **yes** | A3 lands and clears the retry card; the composer was filled before the take, so only the tap is filmed |
| S8 end call → summary card | phone screen recording | **yes** for the tap, **no** for the card | the card is the payoff; give it the full 4:5 frame |
| S9 end card | edit only | no | name, models, number, limitation |

**Capture the screen on the phone itself.** The built-in recorder gives the real
device, the real fullscreen PWA and no browser chrome. The app is capped at
430 px (`App.tsx`: `max-w-[430px]`), so a desktop browser at 430 px wide renders
the same layout — but the height changes the composition, so check the 4:5 card
crop before trusting a fallback; do not mix the fallback into a shot that also
shows the physical phone.

**Framing.** The summary card is composed for 4:5 —
[`screenshots/peacock-summary-4x5.png`](screenshots/peacock-summary-4x5.png) is
the reference. On a 9:16 canvas keep the card fully inside the middle band; do
not let the bottom button or the safe-area collapse crop it.

**What is never in frame:** the terminal with the API key, `.env`, the Gnani
dashboard or its balance, browser devtools, the theme toggle, the language
picker mid-change, another app's notification.

---

## The numbers, and where they came from

Every figure below is copied from a file in this repository. If a number is not
in this table, it is not in the video.

| Claim | Value | Source | Reproduce |
|---|---|---|---|
| Word error rate, phone line | **3.6%** (3.57% in the JSON) | `pashyanti/backend/harness_report.json` → `summary[1].wer` = `0.0357`; table in `harness_report.md` | `cd pashyanti/backend && uv run python -m harness.cli` |
| Character error rate, phone line | **2.9%** | same file → `summary[1].cer` = `0.0295` | same |
| Conditions | 8 clips, `hi-IN`, 300–3400 Hz band-limit, 8 kHz resample, G.711 µ-law, noise added at **10 dB SNR**; the reference clips are synthesised from known text, so the reference is exact and the audio is not a human recording | `harness_report.md` header; `harness/degrade.py`; `harness/corpus.py` | same |
| Worse conditions | 27.8% at 5 dB, **93.5% at 0 dB** (and the model writes plausible text from noise) | `summary[2]`, `summary[3]`; `API-NOTES.md` §Measured results | same |
| Caller stops → text on screen | **450–600 ms** = 350 ms VAD silence (450 ms on the phone-line preset) + ~100 ms model | `ARCHITECTURE.md` §Latency budget; both VAD presets in `stt.headers` (`API-NOTES.md` §Streaming socket) | watch the app: the ms under each bubble is the model's part; the silence is `x-min-silence-ms` |
| The small print under a bubble | the API's own `latency` field, measured **57–211 ms** | `DECISIONS.md` D-004; `stt.py` reads `d["latency"]` | every transcript message carries it |
| Tap → first audio, uncached | **764 ms** streaming; ~2.5 s for the same sentence over REST | `API-NOTES.md` §Text-to-speech ("SSE is worth it") | one uncached reply with the app on screen |
| Tap → first audio, cached | **~0 ms** | `ARCHITECTURE.md` §Latency budget | repeat the same chip twice |
| Default reply voice | `Shivani`, Timbre v3.0; cloned replies use `vachana-vc-v1` | `pashyanti/backend/tts.py` (`VOICE`, `MODEL`, `MODEL_CLONE`) | `tts.speak(..., mode="cloned")` |

Issue #13 wrote these as "~550 ms" and "~760 ms". Those are roundings of
450–600 ms and 764 ms; the video uses the measured values from the table, and
the voiceover says "about half a second" rather than inventing a decimal. The
"~550" is the phone-line case: `stt.headers` raises `x-min-silence-ms` from 350
to 450 ms in telephony mode, so the wait grows by the same 100 ms.

Two things to say out loud when the numbers are spoken:

- **"after folding orthography"** — `हजार`/`हज़ार` and `पाँच`/`पांच` are counted as
  the same word (`DECISIONS.md` D-007). Without that caveat the number is not
  the metric it claims to be.
- **"simulated"** — the phone line is band-limiting, µ-law quantisation and
  added noise in `harness/degrade.py`, not a real call. There is no PSTN in this
  build; see the post copy.

The beat uses **3.6%** and **764 ms** and nothing else. Do not round 764 to
"under a second" or 3.6 to "about 4%" on screen; the ragged precision is the
evidence.

---

## The honest limitation

One sentence, used verbatim on the end card and in the post:

> **It still breaks on overlapping speech, and the reply cannot be interrupted
> because the microphone is muted while it speaks.**

Why it is true, so the answer is ready if asked:

- Half-duplex muting is deliberate (`DECISIONS.md` D-005); barge-in needs echo
  cancellation, which is out of scope for this build.
- Two people talking at once closes the VAD segment with mixed audio; the
  transcript is one of them, not both. `looks_unusable` catches the worst cases
  and asks for a repeat.
- There is no live diarization and no translation. Neither is claimed anywhere
  in the UI or the video.

---

## Post copy

Paste-ready. First line is the hook; last line is the question. Use it only
with a real person whose cloned reference is their own; if the video is a
composite, add `(A re-enactment with a composite persona.)` after the first line
and keep every "her" true to the performer.

```text
The clinic called at 9:04. Meera watched the phone ring, and could not answer it.

This is her side of the next call. The caller's Hindi arrives as large text on
her screen. She taps a reply, and it is spoken down the line — in a natural
Indian voice, or in her own cloned voice from a short reference recording
(5–30 seconds). The call ends with a card: who called, what was agreed, what
happens next.

Built on Gnani Prisma v3.0 (speech → text) and Timbre v3.0 (text → speech), plus
the voice-clone endpoint.

On a simulated phone line — 8 kHz, µ-law, 10 dB SNR — word error rate was 3.6%
across 8 clips, after folding orthography. At 0 dB it collapses to 93.5%, so
when the audio is unusable the app asks for a repeat instead of showing a guess.

What is not solved: overlapping speech breaks it, and the reply cannot be
interrupted because the microphone is muted while it speaks. There is no
production phone number yet — the caller in this video is in the room and the
line is simulated. We did test the relay on a real Indian trial call (the
caller's Hindi came back as text and the reply was heard), but a trial line is not
judge-dialable (unknown callers may hit a PIN), so it is not the demo.

What would you want your own voice to say on a call you can't take?

#GnaniAI #GreatIndianAIInternshipChallenge
```

Rules for whoever posts it: the two hashtags are spelled exactly like that, no
extra tags, no quote-tweet thread that repeats the video, and no claim that is
not in the script above.

---

## Do not say

- **"real-time translation"**, "translation", "translates" — nothing is
  translated. Speech is recognised in the language it is spoken; the reply is
  spoken from the text the user wrote.
- **"diarization"**, "speaker identification", "who said what" — diarization
  exists only in Gnani's Batch API and is not in this app.
- **"call recording"** — nothing records a call. `cache/summary.json` is a text
  artefact; the TTS cache holds synthesised audio, not the caller.
- **"works on any phone call"**, "real phone number", "PSTN", "SIP" — there is
  no number provisioning. The caller is in the room; the line is simulated.
- **"nine languages"** as a tested claim — recognition accepts `indic-auto`, but
  the demo demonstrates Hindi. One tested language, honestly labelled, beats
  nine asserted ones (see #12).
- **"on-device"**, "offline", "private by default" — the audio goes to Gnani's
  API from the server.
- **"instant"**, "zero latency", "perfect" — 764 ms and 3.6% are the numbers.
- **"the AI understands your call"** — the card is a pure function over the
  transcript lines (`build_summary`); a model may *rephrase* three fields of it
  from those same lines, with no audio and no facts of its own. Do not claim it
  listened to the call or understood more than the text.
- **"the chips translate"** — they are written **in** the caller's language, not
  translated from the user's; nothing in this app translates. A chip is a
  suggestion, not a transcript of what the user said.

---

## If it goes wrong

| Symptom | Cause | Fix on the spot |
|---|---|---|
| `no cloned voice on this server` | `embedding.json` missing or server not restarted after building it | rebuild, restart, re-take beat 7 |
| Red pill, `माइक नहीं` | no microphone on the server host | check `sounddevice` sees an input; restart |
| Toggle flips, no new transcript | the Prisma socket is reconnecting after `set_phone_line`; one segment is lost by design | wait one sentence, repeat A2 |
| Reply silent | speaker muted or wrong output device | check the host's output; the UI still shows the reply bubble |
| `error` pill with a message | TTS 500 / 429 / 402 | 500 and 429 retry themselves; 402 means credits are gone and the take is over |
| Retry card refuses to appear | `looks_unusable` needs empty text, punctuation only, or ≥4 words in <400 ms of audio (`stt.py`) | cover or rustle the mic for ~300 ms and try again; do not stage it from a screenshot |

The retry beat is the one that fails most often. Rehearse it five times before
the real take; if it will not fire, shoot the beat again rather than cutting in
a still — a frozen `?` card is exactly the kind of fake a judge notices.

---

## Questions a judge may ask

| Question | Answer |
|---|---|
| Is that a real phone call? | No — this video's call is simulated. A real trial call was tested over Exotel AgentStream on 14 Nov (mobile → Indian trial number → Prisma/Timbre → the reply was heard), and that protocol is now merged as an opt-in pilot (`/exotel/ws`, off without a token, one page, one call, End call best-effort hangs up the carrier). It is not in the video because a trial line is not judge-dialable: limited inbound, unknown callers may hit a PIN. Gnani's API still has no PSTN/SIP; see `EXOTEL-SPIKE.md` and `EXOTEL-BRIDGE.md`. |
| Does it translate? | No. Prisma recognises Indic speech (and English) in the language spoken; the reply is spoken from the text the user typed. |
| Who makes the summary? | Two cards, in order. `server.build_summary` is a pure function over the transcript — first caller line, last caller line, last reply, turn count, duration — and it is sent **instantly**. A second `summary` may follow ~2 s later with only `who/agreed/next` rewritten by `deepseek-v4.1-flash` (the UI language, facts only, empty fields keep the extractive value); if it fails or is slow, the first card is what you keep. `SUMMARY_LLM=0` disables the rewrite entirely. |
| How accurate is it? | 3.6% WER at 10 dB SNR on 8 clips, `hi-IN`, 8 kHz µ-law, after folding orthography. At 0 dB it is 93.5%, so the app asks for a repeat when the audio is unusable. |
| What still breaks? | Overlapping speech; no barge-in while the mic is muted; the cloned voice needs a 5–30 s reference and is **Hindi-only**, so a non-Hindi reply uses the default Timbre voice; the reply chips can be blunt or use the wrong grammatical gender, and they follow the *detected* language, which is occasionally wrong (`D-012` amendment, `LLM-NOTES.md`). |
| Why is the phone only a screen? | In this video it is: capture is server-side (`D-004`), so the phone needs no microphone permission and no HTTPS tunnel. That is also why the caller is in the room — the laptop microphone is the input. A browser *can* feed Prisma's 1024-byte PCM socket: `?mode=talk` does exactly that with an AudioWorklet, and the phone becomes microphone and speaker (`D-004` amendment, [`TALK-MODE.md`](TALK-MODE.md)). It is not in this video and changes nothing on screen. |

---

## Edit checklist

- [ ] Total length 58–60 s; no beat over its budget.
- [ ] English subtitles burned in; Hindi on screen is not subtitled word-for-word,
      only the voiceover is.
- [ ] The two hashtags spelled exactly `#GnaniAI` and
      `#GreatIndianAIInternshipChallenge`.
- [ ] Numbers on screen long enough to read (≥ 2 s), and spelled as in the
      numbers table.
- [ ] The limitation sentence appears on the end card, unsoftened.
- [ ] No API key, `.env`, balance screen, real number or real call audio in any
      frame.
- [ ] Watch it once with the sound off: the hook is burned in and the story
      still reads.
- [ ] If the persona is composite, the post says "a re-enactment" after the
      first line, and the cloned voice is the performer's.
