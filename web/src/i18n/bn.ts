import type { Messages } from "./types";

export const bn: Messages = {
  status: {
    ready: "প্রস্তুত",
    listening: "শুনছি",
    thinking: "ভাবছি",
    speaking: "বলছি",
    repeat: "আবার বলুন",
    noMic: "মাইক নেই",
    reconnecting: "যুক্ত হচ্ছে",
    error: "সমস্যা",
  },
  empty: {
    title: "সামনের মানুষের কথা এখানে পড়ুন",
    body: "উত্তর দিতে নিচের চিপ চাপুন বা নিজের কথা লিখুন।",
  },
  quickReplies: "দ্রুত উত্তর",
  chips: [
    "হ্যাঁ, বলুন।",
    "একটু ধীরে বলুন।",
    "আমি বুঝেছি।",
    "দয়া করে আবার বলুন।",
    "এক মিনিট অপেক্ষা করুন।",
  ],
  composer: {
    placeholder: "আপনার উত্তর লিখুন…",
    send: "বলুন",
    aria: "আপনার উত্তর লিখুন",
  },
  call: { end: "কল শেষ করুন", new: "নতুন কল" },
  summary: {
    eyebrow: "কলের সারসংক্ষেপ",
    agreed: "সম্মতি",
    next: "পরবর্তী",
    endedLabel: "কল শেষ",
    endedTitle: "কল শেষ হয়েছে",
    waiting: "সারসংক্ষেপ এলে এখানে দেখাবে।",
    missing: "এই কলের সারসংক্ষেপ পাওয়া যায়নি।",
    turns: (n) => `${n} বার`,
  },
  retry: {
    main: "বুঝতে পারিনি — আবার বলুন",
    sub: "শুনতে পাইনি",
  },
  toggles: {
    phoneLine: "ফোন লাইন",
    phoneLineCaption: "phone line",
    myVoice: "আমার কণ্ঠ",
    myVoiceCaption: "my voice",
    group: "কল সেটিংস",
  },
  tour: {
    skip: "বাদ দিন",
    next: "এগিয়ে যান",
    start: "শুরু করুন",
    steps: [
      {
        title: "এই অ্যাপ আপনার জন্য শোনে",
        caption: "লাইভ ট্রান্সক্রিপ্ট",
        body: "সামনের মানুষের কথা বড় অক্ষরে এখানে আসে।",
        state: "listening",
      },
      {
        title: "এবং আপনার জন্য বলে",
        caption: "কণ্ঠে উত্তর",
        body: "চিপ চাপুন বা লিখুন — আপনার উত্তর আওয়াজে সামনের মানুষকে শোনানো হয়।",
        state: "speaking",
      },
      {
        title: "শুরু করার জন্য প্রস্তুত",
        caption: "কলে প্রস্তুত",
        body: "স্পষ্ট করে বলুন এবং থামুন। উত্তর দিতে নিচের চিপ চাপুন।",
        state: "idle",
      },
    ],
  },
  header: {
    help: "এটি কীভাবে কাজ করে",
    language: "ভাষা",
    theme: "থিম",
  },
  mascot: {
    name: "সখী",
    idle: "শান্ত",
    listening: "শুনছে",
    speaking: "বলছে",
    unsure: "বুঝতে পারিনি",
  },
  carrier: {
    live: "ফোন কলে",
  },
  talk: {
    start: "শোনা শুরু করুন",
    starting: "শুরু হচ্ছে…",
    hint: "এই মোডে এই ফোনটিই মাইক আর স্পিকার।",
    denied: "মাইকের অনুমতি পাওয়া যায়নি। ব্রাউজারে অনুমতি দিন, তারপর আবার চেষ্টা করুন।",
    insecure: "এই মোডের জন্য HTTPS দরকার। পেজটি https:// দিয়ে খুলুন।",
    unsupported: "এই ব্রাউজার এই মোডের জন্য শব্দ নিতে পারে না।",
  },
};
