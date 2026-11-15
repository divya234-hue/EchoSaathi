# Decisions

Short records of choices that shape the code. Each one is reversible, but not
casually — read the consequence before reopening it mid-build.

---

## D-001 — Python backend, not Rust or Node

**Context.** Rust is a stronger language for real-time audio, and this desktop
already runs a Rust voice agent. TypeScript would collapse the repo to one
language.

**Decision.** Python for everything server-side.

**Why.** The latency budget is dominated by the remote models, not the runtime:
~760 ms to first audio, ~100 ms of tokenisation overhead would not move it. The
streaming protocol, voice clone and SSE path were already proven in Python
before the frontend existed. A rewrite would have cost 4–8 hours of a 26-hour
window and re-opened solved problems.

**Consequence.** Keep the hot path boring: no per-frame allocations beyond what
`stt.py` already does, and `asyncio.to_thread` around blocking calls so the event
loop never stalls during synthesis.

---

## D-002 — Web app with a PWA manifest, not a native app

**Context.** The product is for a phone. "App" was the original framing.

**Decision.** A browser app, installable via `manifest.webmanifest`.

**Why.** A native app buys no telephony access: Android reserves in-call audio
capture (`CAPTURE_AUDIO_OUTPUT`) for system apps, and iOS exposes nothing.
Flutter or React Native would cost days, throw away the React work, and still
need this Python backend. A PWA installs fullscreen with an icon, and a link is
clickable in a post where an APK is not.

**Consequence.** If a store presence is ever needed, wrap the same bundle with
Capacitor. Do not rewrite the UI.

---

## D-003 — One process, aiohttp, one port

**Context.** Options were stdlib `http.server` + a separate `websockets` server,
FastAPI/uvicorn, or aiohttp.

**Decision.** One aiohttp app serving `/ws` and the built frontend.

**Why.** Two servers means two lifecycles, CORS, and a class of "works in dev,
not in prod" bugs. FastAPI adds routing sugar we do not need for two routes.
aiohttp gives static files and websockets in one asyncio process.

**Consequence.** `web/` is built separately and served from `dist/`. In dev, Vite
proxies `/ws` to 8080 (see `vite.config.ts`); in production there is no proxy and
no CORS.

---

## D-004 — The microphone lives on the server

**Context.** The browser could capture audio with an AudioWorklet.

**Decision.** Capture on the server with `sounddevice`; the phone only renders.

**Why.** Browser capture requires HTTPS or localhost (`getUserMedia`), which
forces a tunnel for the phone demo. Server-side capture already worked at
57–211 ms. The phone then needs no permissions at all.

**Consequence.** The phone must be able to reach the server over the LAN. For a
true remote product, swap in the AudioWorklet and a tunnel — the WebSocket
protocol does not change.

**Amended 2026-11-14 (`feat/talk-mode`).** The owner's requirement is an
**in-person conversation**: the laptop will not be there, the user holds the
phone, another person speaks to them in the same room, and the reply is spoken
out of the phone. Server-side capture cannot do that, so `?mode=talk` reverses
this decision for that mode: the page captures with `getUserMedia` + an
AudioWorklet (16 kHz mono s16le, whole 1024-byte frames over the websocket), the
server's `BrowserMic` forwards them to Prisma at real-time cadence with the
normal laptop VAD preset, and Timbre's PCM is streamed back as `audio` messages
for Web Audio to play. No `sounddevice` device is opened in that mode.

The cost recorded above is now real: talk mode needs a **secure context**
(`getUserMedia`), so the phone is opened over the ngrok tunnel (or `--tls` with a
trusted certificate), the origin — and therefore the microphone permission —
changes when the tunnel URL changes, and iOS needs the `AudioContext` resumed
inside the "Start listening" tap. Half-duplex becomes two-sided (`D-005`): the
server sends silence while it streams, and the page stops sending frames until
its player drains. The demo path is unchanged and still server-side; the video
does not use talk mode ([`TALK-MODE.md`](TALK-MODE.md)).

---

## D-005 — Half-duplex, not echo cancellation

**Context.** The microphone hears the speaker, so the app transcribes its own
reply.

**Decision.** Mute the microphone for the duration of playback.

**Why.** AEC is a research problem; muting is eight lines and is correct for a
relay where turns alternate.

**Consequence.** No barge-in. If that becomes a requirement, the fix is AEC or
headphones, not a UI change.

---

## D-006 — `verbatim` output for measurement, `transcribe` for the app

**Context.** With `format=transcribe`, "दो हज़ार पाँच सौ" comes back as "2,500",
so a perfect transcript scored 44% WER.

**Decision.** The harness asks for `verbatim`; the app asks for `transcribe`.

**Why.** The harness measures listening, so it must compare like with like. The
app serves a human reading an amount, so digits are better on screen.

**Consequence.** Never compare harness numbers with app output. The split is
deliberate and documented in `harness/cli.py`.

---

## D-007 — Fold orthography out of WER

**Context.** `हजार`/`हज़ार`, `पाँच`/`पांच`, `यूपीआई`/`यू पी आई` are the same sounds.

**Decision.** `wer.normalize` strips nukta, unifies candrabindu to anusvara,
maps Devanagari digits, and drops punctuation.

**Why.** Counting spelling variants as recognition errors measures the writer,
not the recogniser. Clean WER moved from 17.5% to 0.0% purely from this and
D-006.

**Consequence.** The number is now comparable across formats, but it is not the
same metric a strict ASR paper reports. Say "after folding orthography" when
quoting it.

---

## D-008 — uv and bun

**Context.** pip/venv and npm both work.

**Decision.** `uv` for Python, `bun` for the web.

**Why.** Both are single-binary, fast, and lock deterministically. Python 3.14 is
managed by uv without touching the system interpreter, which matters on Fedora.

**Consequence.** Commit `uv.lock` and `bun.lock`. Never hand-edit lock files; use
`uv add` / `bun add`.

---

## D-009 — Tailwind for layout, CSS variables for theme

**Context.** The original rule was hand-written CSS in one file, no framework.
Adding a theme toggle, a mascot and an onboarding sheet meant duplicating every
colour for light and dark by hand, and every layout tweak was a full edit-build-
look cycle at a 430 px viewport.

**Decision.** Adopt Tailwind 4 (`@tailwindcss/vite`), but keep the *theme* in CSS
variables under `:root` / `.dark`, mapped in with `@theme inline`. Utilities are
for layout, spacing and responsive work; any shape repeated three or more times
gets a semantic class.

**Why.** The slow part of styling this app was never selectors — it was layout at
one fixed viewport and a second colour palette for dark mode. Tailwind fixes both
without importing a component library. This **reverses the "hand-written CSS"
clause** recorded in AGENTS.md; leaving that entry in place would have been the
silent drift D-007-style amendments exist to prevent.

**Consequence.** `web/src/styles.css` is gone; `web/src/index.css` holds the
tokens. Class-soup is the real risk, so the rule is explicit: three repetitions
→ a class. A component library (shadcn, MUI, Radix) is still banned.

---

## D-010 — Paper & Ink, light by default

**Context.** The first build was a dark dashboard with a mint accent — the
default look of every hackathon entry. The actual reader is often older, reads
Devanagari at 23–28 px, and is filmed vertically in daylight on a phone.

**Decision.** Light "Paper & Ink" theme as the default: warm off-white paper,
near-black ink, one deep-teal accent, no gradients. Dark mode exists behind a
toggle in the header.

**Why.** Contrast holds in daylight and on video compression, where dark themes
bloom and lose definition. It also looks like a document rather than a toy,
which matters for a product whose audience is not buying software.

**Consequence.** One theme appears on camera — the video never shows the toggle.
Accessibility floor is now a constraint, not a preference: body ≥ 18 px,
contrast ≥ 7:1, tap targets ≥ 44 px, visible focus, `prefers-reduced-motion`
respected. If a later screen fails those, the screen is wrong, not the rule.

**Amended 2026-11-14 (`feat/web-identity`).** The palette and mascot below were
replaced by D-011 after owner review; the light-default and accessibility rules
stand unchanged. The original decision is kept as the record of why light was
chosen.

**Amended 2026-11-14 (`feat/pixel-matrix-ui`).** The light-default rule is
superseded by D-016: three grounds ship and the default is Peacock (dark). The
daylight reasoning below still holds, so the daylight ground survives as Lime
Wash — one tap away instead of the only option. The accessibility floor is
unchanged.

---

## D-011 — Myna identity: a bird mark, one accent, state as geometry

**Context.** The identity from D-010 (warm paper, teal, a line-drawn blob
mascot) was reviewed by the owner and rejected as not looking professional. The
blob also failed the 30 px header: its eye and inner ear collapsed into noise.
The product's audience is Deaf and hard-of-hearing users and their families,
not early adopters who forgive a toy aesthetic.

**Decision.** Replace the identity with **Myna**: porcelain paper `#F4F6F9`,
midnight ink `#0E1B2C`, one marigold signal `#E39A2B`; IBM Plex Sans with IBM
Plex Sans Devanagari; a solid myna-head mark (round skull, long beak, amber
cheek) shared by `public/icon.svg` and the mascot via `components/myna.ts`.
State is geometry, not expression: a pulsing amber ring (listening), an open
beak (speaking), a `?` badge (missed), stillness (idle). No body, no decorative
bobbing. The mascot stays 30 px in the header and 96–112 px in the empty state
and tour. The logo is the same head in an ink tile; the header lockup is the
mascot plus the Devanagari wordmark.

**Why.** A myna imitates human speech, which is the product's job in one
animal, and its silhouette survives 30 px where a line drawing does not. A
solid mark and a single warm accent read as an instrument rather than a toy;
reserving the accent for audio moving (ring, beak, active state) makes colour
carry meaning instead of decoration. Devanagari in the wordmark is the Indian
cue; no mandala, lotus or rangoli ornament.

**Consequence.** `public/icon.svg` and `components/myna.ts` must change
together. Every colour still lives in `web/src/index.css`, so the palette moves
by editing one block. Reintroducing a cartoon character re-opens the 30 px
legibility problem, and the accent must stay scarce or the state signal dies.

**Amended 2026-11-14 (`feat/peacock-identity`).** The owner supplied a peacock
reference and asked for the mascot to be exact. D-013 replaces the myna and the
navy/marigold tokens with a traced peacock and cream/pine/clay. The state
principle — geometry, no decorative motion — still stands.

---

## D-012 — UI locales are client-side; English is the default

**Context.** The interface copy was hard-coded Hindi, including the chips, tour,
summary labels and error states. The owner asked for English as the preferred
language, plus other languages. Recognition was never the gap: `stt.py` asks
Prisma v3.0 for `indic-auto` (nine Indic languages + English) and records the
detected language per line, so the caller's language already varies
independently of the UI.

**Decision.** Keep every user-facing string in typed dictionaries under
`web/src/i18n/` (`en`, `hi`, `bn`, `mr`), expose them through a small React
context, and put a 44 px globe picker in the header. English is the default;
`?lang=` overrides the saved choice; the choice persists in `localStorage`.
No dependency, no routing, no SSR. The type is the font-curator's verified
four-family pairing: Fraunces for display, Karla for Latin UI, Mukta for
Devanagari and Noto Sans Bengali. Karla and Mukta x-heights are within 2%, so
an English and a Hindi line at the same px sit level.

**Why.** A Deaf or speech-impaired reader should see the controls in the
language they think in, but the product must still be usable on first open
without a settings detour — hence English default plus a persistent picker.
Four locales cover a large share of the audience and two scripts; Tamil,
Telugu, Kannada, Malayalam, Gujarati, Punjabi, Odia and Urdu are one dictionary
file, one registry line, and a font entry if the script is new — not a refactor.

**Consequence.** Every new string must be added to all four dictionaries; a
missing key is a type error. The font stack includes Noto Sans Bengali for the
new script; another script adds its Noto face. The UI language is **not** the
call language: it never changes recognition, and it does not yet change the
voice — TTS remains Hindi; a per-call voice language is a backend follow-up,
not something #5/#6 provide.

**Amended 2026-11-14 (`feat/suggest-chips`).** The reply now follows the
**caller's** language, which is the point of the product: `tts.speak` and
`tts.stream_pcm` take a `lang`, `Call.reply_lang` passes the last
`detected_language_code`, and the cache key includes it. The UI locale still
changes nothing about recognition or the voice. The reply chips follow the same
rule: `Call.offer_suggestions` asks a model for one short direct answer in the
caller's language and `chips.py` adds "please repeat" and "a little slower"
from a reviewed table, replacing the static UI-locale chips only when they
arrive. The static row remains the fallback, so a slow or dead model changes
nothing.

Two limits are deliberate. The **cloned voice cannot change language**:
`vachana-vc-v1` takes an embedding, not a language, so a cloned reply is Hindi
by construction and a non-Hindi reply uses the default Timbre voice (which
speaks all ten). And the chips are only as right as `msg.lang` — the same
Bengali clip was detected `bn-IN` once and `mr-IN` once, and the chips followed
the reported language both times. `LLM-NOTES.md` records the model's own
limitations (gender, bluntness, three lines of context).

---

## D-013 — Peacock identity: trace the reference, cream/pine, serif display

**Context.** The owner rejected the myna as not close enough and supplied a
reference icon: a cream tile with a pine-green peacock head, five-feather crest,
ringed eye, small beak and three sound arcs, soft-embossed. They asked for the
mascot to be "more similar or exact", a similar theme, and better fonts. The
supplied Gemini key authenticates but **image generation is quota-blocked**:
every image model returns HTTP 429 with a per-model free-tier limit of 0, so no
generated PNG exists or is used.

**Decision.** Trace the reference's green silhouette into vector paths — head,
neck, shoulder, crest, pupil, nostril, beak and three arcs — with a 4-unit
margin that survives 30 px. The beak is separate; speaking cuts a transparent
gape through it. The unsure state replaces the arcs with a green ? disc. The
palette is cream `#F2EADB`, pine `#255035`, clay `#7A2F16` for warnings, sage
`#8FC7A3` in dark. Type is Fraunces (display), Karla (Latin UI), Mukta
(Devanagari), Noto Sans Bengali — the font-curator's four-family recommendation,
with Karla/Mukta x-heights within 2%.

**Why.** A trace is the only way to be exact; a generated raster cannot be a
30 px state indicator and cannot be recoloured by tokens. The flat trace loses
the tile's emboss but keeps every contour; the uneasy edge cases (open beak, ?
disc) are designed because the reference has no states. Fraunces gives the
English brand an editorial note; Karla/Mukta keep a Hindi and an English line at
the same optical size; Mukta supplies full conjuncts at 18 px. The cream/pine
palette matches the reference and keeps the measured contrast floor.

**Consequence.** `components/peacock.ts` holds the traced paths and is the source
of truth; `public/icon.svg` is the same mark on a cream tile. The arcs are part
of the mark at rest; their pulse is the listening state, so do not animate them
decoratively. The ? disc is green (state), while the retry notice and the
"missed" status dot use clay (warning). Re-tracing is required if the owner
changes the reference; the brand sheet records the current reference next to the
vector.

---

## D-014 — No real phone call in the demo; the Twilio bridge waits for a number

**Context.** The largest gap between this build and a product is that no
telephone call can reach it: the Gnani API has no PSTN, no number and no SIP
(`API-NOTES.md`). Twilio Media Streams can receive a call and hand us 8 kHz
µ-law, and both halves of our audio path already speak that, so the bridge
looked like a day of work. Whether it could exist *this week* was untested.

**Decision.** The 60-second video does not show a ringing phone, and the
bridge is not built. The spike (#7) closed as **no-go for this deadline; go
only with a US number as a post-submission pilot**, recorded in
[`TWILIO-SPIKE.md`](TWILIO-SPIKE.md).

**Why.** An Indian (+91) number sits behind a Regulatory Bundle; Twilio's own
page puts the review at "up to three business days", "several weeks" in some
regions, and the deadline is 15 Nov 18:00. A US number is obtainable today, but
a +1 number in an Indian clinic demo is a tell. A Trial account also accepts
inbound calls only from verified numbers, so "anyone can call this" is
impossible without upgrading: the demo would be showing a phone that only our
own verified handsets can ring.

**Consequence.** The README says *simulated* phone line and the UI never claims
a real call; `AGENTS.md` lists the bridge as not built. If it is picked up
later, start the Indian bundle on day one and measure the two WAN legs before
quoting any latency. They are the only unknowns the spike left, and the 450 ms
telephony VAD floor is part of the budget either way.

**Amended 2026-11-14 (`docs/exotel-call`).** A trial Indian number over Exotel
AgentStream was tested end to end: a real mobile call reached a throwaway bridge,
Prisma v3.0 transcribed two Hindi/code-mixed turns, and Timbre v3.0's reply was
heard on the handset. The video still uses the simulated line: the trial number
is not judge-dialable (limited inbound, possibly a PIN, 7-day expiry), the page
is not wired to the bridge, and the run's timing includes a 2.2 s Prisma
handshake and a 400 ms jitter buffer. See [`EXOTEL-SPIKE.md`](EXOTEL-SPIKE.md).
The Twilio decision above stands.

**Amended 2026-11-15 (`feat/exotel-bridge`).** The owner asked to ship the
carrier leg rather than keep it in `.scratch/`, so the spike's protocol is now
product code: `backend/exotel.py` plus `/exotel/ws`, **opt-in behind
`EXOTEL_WS_TOKEN`** (503 without it), bound to the most recently opened page,
one call at a time, with the caller's last four digits as the only number that
crosses the wire. `Call.end_call` now hangs up the carrier first, best-effort.

What this does **not** change: Gnani's API still has no PSTN, no SIP and no
number provisioning; the trial line is still not judge-dialable; the 60-second
video still shows the simulated line and must not claim a real number. The
hangup route was probed against the live API on 15 Nov: `POST .../Calls/{sid}`
answers `403 Method not allowed` and only `.../Calls/{sid}/Hangup` answers
`200`, so `end_call` posts that with the call SID from the stream's `start`
event. A live call on 15 Nov answered `200` and the handset dropped, and the
reply was heard on the handset without the gaps the earlier per-chunk padding
caused. The
"go only with a US number" Twilio decision stands; this pilot uses an Indian
trial number under the same limits as the 14 Nov trial call.

---

## D-015 — Bengali is reported unfolded until a speaker checks it

**Context.** #34 added a `bn-IN` corpus and published a first Bengali number
(3.7% clean, 8.7% at 10 dB). D-007 folds orthography out of WER so the metric
measures the recogniser, not the writer — but `wer.normalize` folds Devanagari
only (`\u093c` nukta, `\u0901` candrabindu, Devanagari digits). Bengali has its
own nukta (`\u09bc`) and candrabindu (`\u0981`), and neither is folded, so the
Bengali number is not comparable with the Hindi one.

**Decision.** Keep `wer.normalize` as it is for Bengali, report the number as
measured, and pin that with `tests/test_wer.py::BengaliMetricTest`. The folding
decision waits for the native-speaker check in #12. The Bengali number does not
go into `README.md` until then.

**Why.** The two clean Bengali misses are `পাঁচশো/পাঁচশ` and `এখনো/এখনও` — final
vowel-sign variants, not the nukta/candrabindu class D-007 folds. A generic
Bengali fold would change neither, so it would add an unvalidated normaliser
and move no number; writing rules aimed at those two strings is exactly tuning
to the result, which D-007 exists to avoid. Without a speaker, there is no way
to tell a spelling variant from a different word.

**Consequence.** The Bengali clean figure is not comparable to the Hindi clean
figure and must never be presented side by side without saying so. When a
speaker confirms the variants, add the Bengali fold, update D-015 and the pinned
tests in the same PR, and re-run the sweep — transcripts and audio are cached by
hash, so unchanged clips cost nothing.

---

## D-016 — Halftone dot screen, three grounds, dot-matrix Sakhi

**Context.** The chat surface had one light palette (D-013) and a light/dark
toggle. Owner review asked for a "pixel matrix" style: character in the
background, better bubbles, the peacock drawn in the same style, colour options,
and an HTML prototype to choose from. The prototype set (`opendesign/mockups/
pashyanti-pixel-matrix/`) recorded three directions, six palettes, ten bubble
treatments and six backgrounds; the owner picked the dot-screen direction with
the dot-peacock field, dissolving cards, and three grounds named Peacock, Lime
Wash and Slate.

**Decision.** The chat surface is a halftone dot screen.
- A 6 px lattice is the ground; panels are flat holes in it. Surfaces are only
  1.06–1.11:1 against the field, so the lattice — not fill contrast — is what
  defines a panel.
- Bubble edges dissolve into ground-coloured dots instead of ending in a border;
  the end-of-call card is chamfered, not rounded.
- Three grounds ship, user-selectable from a header menu, persisted, with
  `?theme=` overriding: Peacock `#0B110A` / ink `#F2F5E4` / signal `#C9F05C`;
  Lime Wash `#F1EDDD` / `#17231A` / `#B7DB4B`; Slate `#08201E` / `#E7F3EE` /
  `#E7A93F`. Default Peacock.
- Sakhi is rasterised from the traced paths in `peacock.ts` at a finer screen
  (~1.8 px dots) than the field, and the same geometry is ghosted into the lower
  field on the field's own lattice, static, and hidden behind the empty state.

**Why.** Measured, not eyeballed: body text on its ground 13.86–17.25:1,
secondary text 7.89–11.72:1, reply text on the signal block 8.95–14.35:1 — all
above the 7:1 floor in every ground. The lattice is deliberately 1.60–1.67:1:
enough to read as a printed screen, not enough to compete with a word. A dot
halftone is also the one treatment that survives both the demo's acid look and a
daylight phone without inventing a second design. The mascot keeps the state
language it already had (arcs pulse = listening, beak opens = speaking, `?` disc
= missed, still = idle); the field is static for exactly that reason, and it is
hidden on the empty screen where the real mascot owns the space.

**Consequence.** Every colour lives in `[data-theme]` blocks in
`web/src/index.css`; a fourth ground is one block plus one row in `theme.tsx`.
The pixel face (Silkscreen) may only carry Latin-only strings — it has no
Devanagari, so status labels, buttons, summary labels and notices use the Indic
UI font, and the pixel face is reserved for latency/language metadata and the
wordmark's Latin line. `dotPeacock.ts` is a renderer over `peacock.ts`, never a
second drawing; `public/icon.svg` still comes from the same trace. The arc pulse
stops under `prefers-reduced-motion`; nothing else moves. Animating the field
would re-open the rule that the mascot is the only state indicator.
