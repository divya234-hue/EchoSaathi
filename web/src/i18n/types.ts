import type { MascotState } from "../components/peacock";

/**
 * Every user-facing string in the app. One file per locale must implement this
 * shape, so adding a language is a translation file plus one line in locales.ts
 * — no component changes.
 *
 * Deliberately absent: the product name, the wordmark and the app title. Those
 * are brand, not copy, and stay in Devanagari/Latin in every locale.
 */
export type Messages = {
  status: {
    ready: string;
    listening: string;
    thinking: string;
    speaking: string;
    repeat: string;
    noMic: string;
    reconnecting: string;
    error: string;
  };
  empty: { title: string; body: string };
  chips: string[];
  quickReplies: string;
  composer: { placeholder: string; send: string; aria: string };
  call: { end: string; new: string };
  summary: {
    eyebrow: string;
    agreed: string;
    next: string;
    endedLabel: string;
    endedTitle: string;
    waiting: string;
    missing: string;
    turns: (n: number) => string;
  };
  retry: { main: string; sub: string };
  toggles: {
    phoneLine: string;
    phoneLineCaption: string;
    myVoice: string;
    myVoiceCaption: string;
    group: string;
  };
  tour: {
    skip: string;
    next: string;
    start: string;
    steps: { title: string; caption: string; body: string; state: MascotState }[];
  };
  header: {
    help: string;
    language: string;
    /** Menu label; theme names themselves are product nouns and stay Latin. */
    theme: string;
  };
  mascot: {
    name: string;
    idle: string;
    listening: string;
    speaking: string;
    unsure: string;
  };
  carrier: {
    live: string;
  };
  talk: {
    start: string;
    starting: string;
    hint: string;
    denied: string;
    insecure: string;
    unsupported: string;
  };
};
