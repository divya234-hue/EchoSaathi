# The chip model — OpenCode Go, not Gnani

Prisma gives us the caller's language and Timbre speaks the reply, but neither
can write a *contextual* reply chip in that language. One short chat completion
does, and this file records what was verified about that endpoint so nobody has
to rediscover it. Nothing here is Gnani's API; `API-NOTES.md` is Gnani.

The key is `LLM_API_KEY` in `pashyanti/backend/.env` (gitignored), read by
`backend/llm.py`. It never leaves the server: not into the page, not into a log
line, not into a message.

## Endpoint

| | |
|---|---|
| Base | `https://opencode.ai/inference/go/openai/v1` |
| Model | `deepseek-v4.1-flash` |
| Required header | `x-opencode-session: <stable string>` — without it: `400 MissingSessionID` |
| Auth | `Authorization: Bearer <LLM_API_KEY>` |

- `https://opencode.ai/zen/v1` (pay-as-you-go) answers **402** with this key; the
  `deepseek-v4.1-flash-free` model answers **429** (free-tier limit). The Go
  endpoint answers **200**, and the response's `billing_source` says `go`.
- The session header is generated once per server process
  (`pashyanti-<8 hex>`), so a conversation keeps one session and a restart gets
  a fresh one. A header is not a secret; it is a routing/session hint.
- The model is a **reasoning** model. With its default thinking on, a one-line
  answer spends 300–400 reasoning tokens and takes **4–7 s**; with
  `"thinking": {"type": "disabled"}` the same answer takes **2.1–3.2 s** (five
  lines, 14 Nov). A chip that arrives after the conversation has moved on is
  worth nothing, so `llm.py` disables thinking and caps `max_tokens` at 200.
  (Another consequence: `max_tokens: 80` returns `finish_reason: "length"` with
  an empty `content` — the reasoning budget ate the answer. Do not shrink it.)

## What the prompt is allowed to do

The system prompt asks for **one** string in a JSON array: a short reply (≤ 40
characters) the user could say next, in the caller's language and script, using
only facts in the caller's line. It explicitly forbids inventing names, numbers,
times, prices or promises, and allows `[]` when nothing safe fits.

`chips.py` turns that into the row on screen:

```
[ direct answer from the model, "please repeat", "a little slower" ]
```

The last two are **not** model output. They come from a reviewed table in
`chips.py` for English, Hindi, Bengali, Marathi, Gujarati, Punjabi, Odia, Tamil,
Telugu, Kannada and Malayalam (an unknown language falls back to English). That
is deliberate: "please repeat" and "a little slower" must exist on every
transcript, in the caller's language, even when the model is slow, down, or
returns something creative. The model contributes the one chip that needs
judgement.

`Call.offer_suggestions` runs the call off the message path, cancels an older
in-flight request when a newer line arrives, and waits at most
`SUGGEST_TIMEOUT = 6 s`. If nothing usable comes back, **no `suggest` message is
sent** and the page keeps the static locale chips it already has.

## The end-of-call card

`llm.summary(lines, lang)` asks for one JSON object — `who` (≤ 60 chars),
`agreed` (≤ 90), `next` (≤ 90) — from the transcript, in the **UI language**
(the card is for the user). `Call.end_call` sends the extractive card first and
only then asks, merges non-empty fields, and sends a second `summary`; a slow or
failed call leaves the first card. Tests cover the merge and the fallback with
no key.

Measured on the demo transcript (`नमस्ते, मैं डॉ. मेहरा की क्लिनिक से बोल रही हूँ।`
… `ठीक है, दस बजे मिलते हैं।`):

| UI language | Latency | Card |
|---|---|---|
| `en` | 2153 ms | `who: Clinic receptionist` · `agreed: Appointment tomorrow at 10 am` · `next: User will come to the clinic tomorrow at 10 am` |
| `hi` | 3050 ms | `who: डॉ. मेहरा की क्लिनिक से कॉलर` · `agreed: कल सुबह दस बजे का अपॉइंटमेंट` · `next: कल सुबह दस बजे मिलना` |

End to end in the app (one wav through the loopback, chip tap, end call): the
extractive card arrived first (`who` = the first caller line), then the rewrite
replaced `who` with `पश्यन्ती` and kept `agreed`/`next`; `turns` and `duration_s`
were identical in both, because those are not the model's to change.

## Measured, 14 November 2026

| Caller line | Detected | Latency | Chips |
|---|---|---|---|
| `कल सुबह दस बजे का अपॉइंटमेंट खाली है।` | `hi-IN` | 2762 ms | `कल दस बजे मैं आ जाऊँगा।` · `कृपया दोहराइए।` · `थोड़ा धीरे बोलिए।` |
| `আপনি কত টাকা জমা দিয়েছেন?` | `bn-IN` | 2556 ms | `আমি এখনো টাকা জমা দিইনি।` · `অনুগ্রহ করে আবার বলুন।` · `একটু ধীরে বলুন।` |
| `Tomorrow at 10 a.m. is free.` | `en-IN` | 2681 ms | `I'll be there at 10 a.m.` · `Please repeat that.` · `A little slower, please.` |

End to end in the app (server microphone, this machine's output monitor as the
input, one Hindi utterance): transcript `नमस्ते, मैं पश्यन्ती हूँ।` `hi-IN` 103 ms;
chips `नमस्ते, मैं बधिर हूँ।` · `कृपया दोहराइए।` · `थोड़ा धीरे बोलिए।`; tapping the
first chip spoke it with `lang: hi-IN` (`ttfa_ms 2809`, uncached).

Same end to end for a Bengali caller through talk mode in Chrome: transcript
`সকাল দশটায় ফোন করবেন।` `bn-IN`, chips `ঠিক আছে, দশটায় ফোন করব।` ·
`অনুগ্রহ করে আবার বলুন।` · `একটু ধীরে বলুন।`, and the reply came back as **32 audio
chunks / 69,120 bytes = 2.16 s of Bengali PCM** (`lang: bn-IN`).

## Limitations, honestly

- **The chips are only as right as `msg.lang`.** The same synthetic Bengali
  sentence was detected `bn-IN` in one run and `mr-IN` in another (Bengali and
  Marathi are both Indic scripts the model can confuse on a TTS voice). The app
  then offered Marathi chips, because the caller's *detected* language is what
  it follows. That is correct behaviour and a recogniser limitation.
- **Gender.** Hindi, Marathi and Gujarati mark the speaker's gender in
  first-person verbs. The app has no persona profile, so a chip can use the
  wrong one (`आ जाऊँगा` vs `आ जाऊँगी`). The composer is there to edit it.
- **Register.** The model can be blunt (`नमस्ते, मैं बधिर हूँ।` for "hello, I am
  Pashyanti"). It is a suggestion, not a script.
- **No memory of who the user is.** Three lines of context, nothing else.
- The model is a third party: a line of the conversation leaves the machine.
  The two safety chips do not depend on it, and `LLM_API_KEY` can simply be
  absent — then the feature is off and the static chips are used.

## Reproduce

```fish
cd pashyanti/backend
uv run python -c "import llm; print(llm.available())"   # True/False, never the key
uv run python -m unittest tests.test_llm tests.test_chips
```

The end-to-end runs used a scratch Puppeteer harness (a real server, one wav
through this machine's output monitor, headless Chrome) and
[`../backend/talk_replay.py`](../backend/talk_replay.py) for the talk-mode audio
path. The chip and card calls themselves are exercised by
`tests.test_llm` without the network; the browser harness is not committed,
because Puppeteer is not a project dependency.
