import type { Messages } from "./types";

export const en: Messages = {
  status: {
    ready: "Ready",
    listening: "Listening",
    thinking: "Thinking",
    speaking: "Speaking",
    repeat: "Repeat",
    noMic: "No mic",
    reconnecting: "Reconnecting",
    error: "Error",
  },
  empty: {
    title: "The other person’s words, right here",
    body: "Tap a chip below, or type your reply and it is spoken down the line.",
  },
  quickReplies: "Quick replies",
  chips: [
    "Yes, go ahead.",
    "A little slower, please.",
    "I understood.",
    "Please repeat that.",
    "One moment.",
  ],
  composer: {
    placeholder: "Type your reply…",
    send: "Speak",
    aria: "Type your reply",
  },
  call: { end: "End call", new: "New call" },
  summary: {
    eyebrow: "Call summary",
    agreed: "Agreed",
    next: "Next",
    endedLabel: "Call ended",
    endedTitle: "The call has ended",
    waiting: "The summary will appear here.",
    missing: "No summary arrived for this call.",
    turns: (n) => `${n} ${n === 1 ? "turn" : "turns"}`,
  },
  retry: {
    main: "Couldn’t catch that — please repeat",
    sub: "the audio was unclear",
  },
  toggles: {
    phoneLine: "Phone line",
    phoneLineCaption: "bad line",
    myVoice: "My voice",
    myVoiceCaption: "cloned voice",
    group: "Call settings",
  },
  tour: {
    skip: "Skip",
    next: "Next",
    start: "Start",
    steps: [
      {
        title: "This app listens for you",
        caption: "Live transcript",
        body: "The other person’s speech appears here as large text.",
        state: "listening",
      },
      {
        title: "And speaks for you",
        caption: "Spoken reply",
        body: "Tap a chip or type — your reply is spoken down the line in a natural voice.",
        state: "speaking",
      },
      {
        title: "Ready when you are",
        caption: "Ready to call",
        body: "Speak clearly and pause. Tap a chip below to reply.",
        state: "idle",
      },
    ],
  },
  header: {
    help: "How this works",
    language: "Language",
    theme: "Theme",
  },
  mascot: {
    name: "Sakhi",
    idle: "idle",
    listening: "listening",
    speaking: "speaking",
    unsure: "didn’t catch that",
  },
  carrier: {
    live: "On a phone call",
  },
  talk: {
    start: "Start listening",
    starting: "Starting…",
    hint: "In talk mode this phone is the microphone and the speaker.",
    denied: "Microphone blocked. Allow it in the browser, then try again.",
    insecure: "Talk mode needs HTTPS. Open this page over https://.",
    unsupported: "This browser cannot capture audio for talk mode.",
  },
};
