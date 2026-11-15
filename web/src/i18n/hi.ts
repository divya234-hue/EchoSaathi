import type { Messages } from "./types";

export const hi: Messages = {
  status: {
    ready: "तैयार",
    listening: "सुन रहे हैं",
    thinking: "सोच रहे हैं",
    speaking: "बोल रहे हैं",
    repeat: "दोहराइए",
    noMic: "माइक नहीं",
    reconnecting: "जुड़ रहे हैं",
    error: "गड़बड़ी",
  },
  empty: {
    title: "सामने वाले की बात यहाँ पढ़िए",
    body: "जवाब देने के लिए नीचे कोई चिप दबाइए या अपने शब्द लिखिए।",
  },
  quickReplies: "जल्दी जवाब",
  chips: [
    "हाँ, बोलिए।",
    "थोड़ा धीरे बोलिए।",
    "मैं समझ गया।",
    "कृपया दोहराइए।",
    "एक मिनट रुकिए।",
  ],
  composer: {
    placeholder: "अपना जवाब लिखिए…",
    send: "बोलिए",
    aria: "अपना जवाब लिखिए",
  },
  call: { end: "कॉल खत्म करें", new: "नई कॉल" },
  summary: {
    eyebrow: "कॉल का सारांश",
    agreed: "सहमति",
    next: "आगे",
    endedLabel: "कॉल समाप्त",
    endedTitle: "कॉल खत्म हो गई",
    waiting: "सारांश आते ही यहाँ दिखेगा।",
    missing: "इस कॉल का सारांश नहीं मिला।",
    turns: (n) => `${n} बार`,
  },
  retry: {
    main: "समझ नहीं आया — दोहराइए",
    sub: "couldn't catch that",
  },
  toggles: {
    phoneLine: "फ़ोन लाइन",
    phoneLineCaption: "phone line",
    myVoice: "मेरी आवाज़",
    myVoiceCaption: "my voice",
    group: "कॉल सेटिंग",
  },
  tour: {
    skip: "छोड़ दें",
    next: "आगे",
    start: "शुरू करें",
    steps: [
      {
        title: "ये ऐप आपके लिए सुनता है",
        caption: "लाइव ट्रांसक्रिप्ट",
        body: "सामने वाले की बात सीधे स्क्रीन पर बड़े अक्षरों में आती है।",
        state: "listening",
      },
      {
        title: "और आपके लिए बोलता है",
        caption: "आवाज़ में जवाब",
        body: "आप चिप दबाइए या लिखिए — जवाब आवाज़ में सामने वाले को सुनाया जाता है।",
        state: "speaking",
      },
      {
        title: "शुरू करने के लिए तैयार",
        caption: "कॉल के लिए तैयार",
        body: "ज़ोर से बोलिए और रुकिए। जवाब देने के लिए नीचे कोई चिप दबाइए।",
        state: "idle",
      },
    ],
  },
  header: {
    help: "यह कैसे काम करता है",
    language: "भाषा",
    theme: "थीम",
  },
  mascot: {
    name: "सखी",
    idle: "शांत",
    listening: "सुन रही है",
    speaking: "बोल रही है",
    unsure: "समझ नहीं आया",
  },
  carrier: {
    live: "फ़ोन कॉल पर",
  },
  talk: {
    start: "सुनना शुरू करें",
    starting: "शुरू हो रहा है…",
    hint: "इस मोड में यही फ़ोन माइक और स्पीकर है।",
    denied: "माइक की अनुमति नहीं मिली। ब्राउज़र में अनुमति दें, फिर दोबारा कोशिश करें।",
    insecure: "यह मोड HTTPS पर चलता है। पेज को https:// से खोलिए।",
    unsupported: "यह ब्राउज़र इस मोड के लिए आवाज़ नहीं ले सकता।",
  },
};
