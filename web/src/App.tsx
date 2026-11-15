/**
 * Pashyanti — one screen: the caller's words, the user's replies, and Sakhi.
 *
 * The call ends on an artefact, not a chat bubble: `end_call` asks the backend
 * for `summary` (#4), and the card replaces the transcript. `new_call` clears
 * everything and hands the screen back to the empty state.
 *
 * All chrome comes from the active locale (i18n/); the caller's own words are
 * rendered in the language the recogniser reported for that line.
 */
import { useCallback, useEffect, useRef, useState } from "react";
import { DemoToggles } from "./components/DemoToggles";
import { LanguageMenu } from "./components/LanguageMenu";
import { Mascot, type MascotState } from "./components/Mascot";
import { Onboarding } from "./components/Onboarding";
import { PeacockField } from "./components/PeacockField";
import { RetryNotice } from "./components/RetryNotice";
import { SummaryCard } from "./components/SummaryCard";
import { ThemeMenu } from "./components/ThemeMenu";
import { useI18n } from "./i18n";
import { Talk, TalkError } from "./talk";
import type { CallMode, Line, ServerMsg, Summary } from "./types";
import { useSocket } from "./ws";

/** Server state → mascot face. The mascot is the state indicator, not decoration. */
function face(state: string): MascotState {
  if (state.startsWith("error")) return "unsure";
  if (state === "speaking") return "speaking";
  if (state === "listening") return "listening";
  return "idle";
}

/** How long to wait for #4's summary before saying it did not arrive. */
const SUMMARY_WAIT_MS = 3000;

/** `?mode=talk`: the phone is the microphone and the speaker (D-004). */
const TALK_REQUESTED =
  new URLSearchParams(location.search).get("mode") === "talk";

type CaptureState =
  | "idle"
  | "starting"
  | "ready"
  | "denied"
  | "insecure"
  | "unsupported"
  | "error";

export default function App() {
  const { locale, m } = useI18n();
  const [lines, setLines] = useState<Line[]>([]);
  const [state, setState] = useState<string>("idle");
  const [mic, setMic] = useState<boolean | null>(null);
  const [draft, setDraft] = useState("");
  const [summary, setSummary] = useState<Summary | null>(null);
  const [ended, setEnded] = useState(false);
  const [summaryMissing, setSummaryMissing] = useState(false);
  const [retry, setRetry] = useState(false);
  const [phoneLine, setPhoneLine] = useState(false);
  const [clonedVoice, setClonedVoice] = useState(false);
  const [mode, setMode] = useState<CallMode>(TALK_REQUESTED ? "talk" : "server");
  const [capture, setCapture] = useState<CaptureState>("idle");
  const [carrier, setCarrier] = useState<{ from?: string } | null>(null);
  const [suggestions, setSuggestions] = useState<string[]>([]);
  const talk = useRef<Talk | null>(null);
  const callerLang = useRef<string | null>(null);
  const [tour, setTour] = useState(
    () => new URLSearchParams(location.search).has("tour"),
  );
  const summaryTimer = useRef<number | null>(null);
  const pendingEcho = useRef<string | null>(null);

  const clearSummaryTimer = useCallback(() => {
    if (summaryTimer.current !== null) {
      window.clearTimeout(summaryTimer.current);
      summaryTimer.current = null;
    }
  }, []);

  useEffect(() => clearSummaryTimer, [clearSummaryTimer]);

  // Leaving the page must release the microphone, not just the socket.
  useEffect(() => () => talk.current?.stop(), []);

  const onMsg = useCallback(
    (msg: ServerMsg) => {
      switch (msg.type) {
        case "hello":
          setMic(msg.mic);
          if (msg.mode) setMode(msg.mode);
          if (typeof msg.phone_line === "boolean") setPhoneLine(msg.phone_line);
          if (typeof msg.cloned_voice === "boolean")
            setClonedVoice(msg.cloned_voice);
          break;
        case "phone_line":
          setPhoneLine(msg.enabled);
          break;
        case "cloned_voice":
          setClonedVoice(msg.enabled);
          break;
        case "status":
          setState(msg.state);
          // Half-duplex, page side: our own reply must not be captured. The
          // player's drain re-opens the microphone when the audio has played.
          if (msg.state === "speaking") talk.current?.setMuted(true);
          if (msg.state === "listening" && !talk.current?.playing)
            talk.current?.setMuted(false);
          break;
        case "audio":
          if (!msg.final) talk.current?.play(msg.data, msg.rate);
          break;
        case "carrier":
          // A real inbound call is the audio source; the local mic is idle.
          setCarrier(msg.state === "live" ? { from: msg.from } : null);
          break;
        case "capture":
          // `stopped` is the server closing the call: release the phone's
          // microphone, not just the socket.
          if (msg.state === "stopped") {
            talk.current?.stop();
            talk.current = null;
            setCapture("idle");
          } else {
            setCapture(msg.state);
          }
          break;
        case "transcript":
          setRetry(false);
          // A new caller language makes the previous chips the wrong script.
          if (msg.lang !== callerLang.current) setSuggestions([]);
          callerLang.current = msg.lang;
          setLines((prev) => [
            ...prev,
            {
              id: prev.length + 1,
              who: "caller",
              text: msg.text,
              lang: msg.lang,
              latency_ms: msg.latency_ms,
            },
          ]);
          break;
        case "suggest":
          // Caller-language chips: the model's answer plus "please repeat" and
          // "a little slower". The static locale row is the fallback until
          // these arrive; a failed call leaves it in place.
          setSuggestions(msg.chips);
          break;
        case "speak": {
          // The tap already put this line on screen (`reply` below); `speak`
          // arrives after the audio has been synthesised and played out, which
          // can be seconds. Only append when the server speaks something the
          // page did not echo — a chip reply, or a stale one.
          const echo = pendingEcho.current;
          pendingEcho.current = null;
          setLines((prev) => {
            const last = prev[prev.length - 1];
            if (echo !== null && last?.who === "me" && last.text === msg.text) {
              return prev;
            }
            return [...prev, { id: prev.length + 1, who: "me", text: msg.text }];
          });
          break;
        }
        case "retry":
          setRetry(true);
          break;
        case "summary":
          clearSummaryTimer();
          setSummary({
            who: msg.who,
            agreed: msg.agreed,
            next: msg.next,
            turns: msg.turns,
            duration_s: msg.duration_s,
          });
          setSummaryMissing(false);
          setRetry(false);
          setEnded(true);
          setState("idle");
          break;
        case "error":
          setState(`error: ${msg.message}`);
          break;
      }
    },
    [clearSummaryTimer],
  );

  const { connected, send, sendBytes } = useSocket(onMsg, TALK_REQUESTED ? "?mode=talk" : "");

  const togglePhoneLine = () => {
    const enabled = !phoneLine;
    setPhoneLine(enabled);
    send({ type: "set_phone_line", enabled });
  };

  const toggleVoice = () => {
    const enabled = !clonedVoice;
    setClonedVoice(enabled);
    send({ type: "set_cloned_voice", enabled });
  };

  const startListening = async () => {
    if (capture === "starting" || capture === "ready") return;
    if (!window.isSecureContext) {
      setCapture("insecure");
      return;
    }
    setCapture("starting");
    try {
      const engine = await Talk.start({
        onFrame: (frame) => sendBytes(frame),
        onPlaybackDrained: () => talk.current?.setMuted(false),
      });
      talk.current = engine;
      send({ type: "start_capture" });
    } catch (err) {
      if (err instanceof TalkError) {
        setCapture(err.kind);
      } else {
        setState(`error: ${err instanceof Error ? err.message : String(err)}`);
        setCapture("idle");
      }
    }
  };

  const reply = (text: string) => {
    const t = text.trim();
    if (!t) return;
    send({ type: "reply", text: t });
    setDraft("");
    // Show it now. `speak` comes back only after Timbre has synthesised and the
    // reply has played, so waiting for it makes the composer look like it ate
    // the message.
    pendingEcho.current = t;
    setLines((prev) => [...prev, { id: prev.length + 1, who: "me", text: t }]);
  };

  const endCall = () => {
    if (ended) return;
    // End it here too: the phone's microphone goes off on the tap, not after a
    // round trip. The server stops its own session on `end_call`.
    talk.current?.stop();
    talk.current = null;
    setCapture("idle");
    send({ type: "end_call", lang: locale });
    setEnded(true);
    setRetry(false);
    setState("idle");
    setSummaryMissing(false);
    clearSummaryTimer();
    summaryTimer.current = window.setTimeout(
      () => setSummaryMissing(true),
      SUMMARY_WAIT_MS,
    );
  };

  const newCall = () => {
    clearSummaryTimer();
    send({ type: "new_call" });
    setLines([]);
    setSuggestions([]);
    callerLang.current = null;
    setCapture("idle");
    setSummary(null);
    setEnded(false);
    setSummaryMissing(false);
    setRetry(false);
    setDraft("");
    setState("idle");
  };

  const empty = lines.length === 0 && !ended;
  const errored = state.startsWith("error");
  const isTalk = mode === "talk";
  const isCarrier = carrier !== null;
  const noMic = !isTalk && !isCarrier && mic === false;
  const missed = retry && !ended;
  const dotState = !connected || noMic || errored
    ? "error"
    : missed
      ? "missed"
      : state;
  // Only a failure needs a sentence next to the button; the hint lives in the
  // empty state, once.
  // The caller's language replaces the UI locale's chips once the model
  // answers; until then (or if it fails) the static row is exactly what it was.
  const chipsToShow = suggestions.length > 0 ? suggestions : m.chips;
  const captureNote =
    capture === "denied"
      ? m.talk.denied
      : capture === "insecure"
        ? m.talk.insecure
        : capture === "unsupported"
          ? m.talk.unsupported
          : "";
  const statusKey = state as "listening" | "thinking" | "speaking";
  const statusLabel = !connected
    ? m.status.reconnecting
    : isCarrier
      ? m.carrier.live
      : noMic
      ? m.status.noMic
      : errored
        ? m.status.error
        : missed
          ? m.status.repeat
          : (m.status[statusKey] ?? m.status.ready);

  return (
    <div
      className="screen mx-auto flex h-dvh w-full max-w-[430px] flex-col"
      data-empty={empty ? "true" : "false"}
    >
      <PeacockField className="peacock-field" />

      <header className="app-top">
        <span className="mascot-tile">
          <Mascot state={missed ? "unsure" : face(state)} size={40} />
        </span>
        <div className="brand">
          <h1 className="wordmark" lang="hi">
            पश्यन्ती
          </h1>
          <p className="wordmark-latin">Pashyanti</p>
        </div>

        <div className="top-tools">
          <span
            className="status-pill"
            role="status"
            aria-live="polite"
            data-state={dotState}
          >
            <span className="status-dots" aria-hidden="true">
              <i />
              <i />
              <i />
            </span>
            <span className="status-label">{statusLabel}</span>
            {carrier?.from ? (
              <span className="status-caller">{carrier.from}</span>
            ) : null}
          </span>
          <LanguageMenu />
          <ThemeMenu />
          <button
            type="button"
            onClick={() => setTour(true)}
            aria-label={m.header.help}
            className="icon-btn"
          >
            <span aria-hidden="true" className="text-[17px]">
              ?
            </span>
          </button>
        </div>
      </header>

      {!ended && (
        <DemoToggles
          phoneLine={phoneLine}
          clonedVoice={clonedVoice}
          onPhoneLine={togglePhoneLine}
          onVoice={toggleVoice}
        />
      )}

      <main className="app-thread">
        {summary ? (
          <SummaryCard summary={summary} />
        ) : ended ? (
          <div className="summary-card" aria-live="polite">
            <p className="summary-eyebrow">{m.summary.endedLabel}</p>
            <p className="summary-title">{m.summary.endedTitle}</p>
            <p className="summary-note">
              {summaryMissing ? m.summary.missing : m.summary.waiting}
            </p>
          </div>
        ) : empty ? (
          <div className="empty">
            <Mascot state={missed ? "unsure" : face(state)} size={116} />
            {missed ? (
              <div className="mt-6 w-full">
                <RetryNotice />
              </div>
            ) : (
              <>
                <h2 className="empty-title">{m.empty.title}</h2>
                <p className="empty-body">{m.empty.body}</p>
                {isTalk && <p className="empty-body">{m.talk.hint}</p>}
              </>
            )}
          </div>
        ) : (
          <ul className="turns" aria-live="polite">
            {lines.map((line) => (
              <li
                key={line.id}
                className={`bubble ${line.who === "me" ? "bubble-me" : "bubble-caller"}`}
              >
                <p
                  className="bubble-text"
                  lang={line.lang ?? undefined}
                >
                  {line.text}
                </p>
                {line.who === "caller" && line.latency_ms !== undefined && (
                  <small className="bubble-meta">
                    {line.lang} · {line.latency_ms} ms
                  </small>
                )}
              </li>
            ))}
            {missed && (
              <li>
                <RetryNotice />
              </li>
            )}
          </ul>
        )}
      </main>

      <footer className="app-foot">
        {ended ? (
          <button type="button" className="btn-primary w-full" onClick={newCall}>
            {m.call.new}
          </button>
        ) : isTalk && capture !== "ready" ? (
          <div>
            {captureNote && <p className="talk-note">{captureNote}</p>}
            <button
              type="button"
              className="btn-primary w-full"
              onClick={startListening}
              disabled={capture === "starting"}
            >
              {capture === "starting" ? m.talk.starting : m.talk.start}
            </button>
          </div>
        ) : (
          <>
            {(lines.length > 0 || isCarrier) && (
              <div className="foot-end">
                <button type="button" className="footer-end" onClick={endCall}>
                  <svg
                    width="13"
                    height="13"
                    viewBox="0 0 16 16"
                    aria-hidden="true"
                  >
                    <rect
                      x="2.5"
                      y="2.5"
                      width="11"
                      height="11"
                      rx="2.5"
                      fill="currentColor"
                    />
                  </svg>
                  {m.call.end}
                </button>
              </div>
            )}

            <div className="chips" aria-label={m.quickReplies}>
              {chipsToShow.map((chip) => (
                <button
                  key={chip}
                  type="button"
                  onClick={() => reply(chip)}
                  className="chip"
                >
                  {chip}
                </button>
              ))}
            </div>

            <form
              className="composer"
              onSubmit={(e) => {
                e.preventDefault();
                reply(draft);
              }}
            >
              <input
                value={draft}
                onChange={(e) => setDraft(e.target.value)}
                placeholder={m.composer.placeholder}
                aria-label={m.composer.aria}
                className="composer-input"
                enterKeyHint="send"
              />
              <button type="submit" className="btn-primary">
                {m.composer.send}
              </button>
            </form>
          </>
        )}
      </footer>

      <Onboarding open={tour} onClose={() => setTour(false)} />
    </div>
  );
}
