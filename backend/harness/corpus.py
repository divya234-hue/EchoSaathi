"""Reference clips for the WER harness.

Sentences are chosen to look like a real relay call: a name, an amount, a time,
an appointment, and a request to repeat or slow down. TTS gives ground truth
for free — the text *is* the reference, so no hand labelling.

A corpus is keyed by language. Provenance travels with it: `checked_by is None`
marks a provisional reference, and the report says the number is provisional.
Numbers are written as spoken words, never digits, because the reference has to
match what the voice actually says after `wer.normalize` folding.
"""
import hashlib
import os

CORPORA = {
    "hi-IN": {
        "texts": [
            "मेरा नाम गौतम कुमार शर्मा है।",
            "कल सुबह दस बजे अपॉइंटमेंट चाहिए।",
            "दो हज़ार पाँच सौ रुपये जमा हो गए हैं।",
            "मेरे खाते में पैसे नहीं आए हैं।",
            "कृपया थोड़ा धीरे बोलिए।",
            "डॉक्टर साहब आज नहीं आए हैं।",
            "मेरा अपॉइंटमेंट कल सुबह दस बजे है।",
            "बिल में एक हज़ार दो सौ रुपये हैं।",
            "मैं हिंदी में बात करना चाहता हूँ।",
            "कल तक पैसे भेज दीजिए।",
        ],
        "voice": "Shivani",
        "author": "assistant",
        "checked_by": None,
        "note": "Everyday Hindi relay turns. The text is the original harness "
                "corpus; no native-speaker review is recorded.",
    },
    "bn-IN": {
        "texts": [
            "আমার নাম সৌরভ চট্টোপাধ্যায়।",
            "দুই হাজার পাঁচশো টাকা জমা হয়েছে।",
            "সকাল দশটায় ফোন করবেন।",
            "আগামীকাল বিকেল চারটায় আমার ডাক্তারের অ্যাপয়েন্টমেন্ট আছে।",
            "মাফ করবেন, কথাটা আবার বলবেন?",
            "একটু আস্তে বলুন, আমি ঠিকমতো বুঝতে পারছি না।",
            "আমার অ্যাকাউন্টে এখনো টাকা ঢোকেনি।",
            "ডাক্তারবাবু আজ চেম্বারে আসেননি।",
            "আমি বাংলায় কথা বলতে চাই।",
            "কালকের মধ্যে টাকাটা পাঠিয়ে দেবেন।",
        ],
        "voice": "Shivani",
        "author": "assistant",
        "checked_by": None,
        "note": "Everyday Bengali relay turns written in Bengali rather than "
                "translated line by line from the Hindi corpus. No "
                "native-speaker check yet, so the measured number is provisional.",
    },
}

# The Hindi list was the only corpus before the registry; keep the name working.
REFERENCE_TEXTS = CORPORA["hi-IN"]["texts"]


def get(lang: str) -> dict:
    """Return the corpus entry for `lang`, or fail with the known languages."""
    try:
        return CORPORA[lang]
    except KeyError:
        known = ", ".join(sorted(CORPORA))
        raise ValueError(
            f"unknown corpus language {lang!r}; known languages: {known}"
        ) from None


def is_provisional(entry: dict) -> bool:
    """A corpus without a recorded native check produces a provisional number."""
    return entry.get("checked_by") is None


def _path(text: str, voice: str, rate: int, lang: str, out_dir: str) -> str:
    h = hashlib.sha1(f"{lang}|{text}|{voice}|{rate}".encode()).hexdigest()[:12]
    return os.path.join(out_dir, f"ref_{lang}_{h}.wav")


def ensure(texts, out_dir="cache/corpus", voice="Shivani", rate=16000,
           lang="hi-IN"):
    """Synthesise any missing reference clip. Returns [(path, text), ...].

    Cached by (language, text, voice, rate), so a second run makes no API calls
    and corpora cannot collide. `gnani` is imported here, not at module level:
    the registry and its cache paths stay importable with no API key (CI has
    none).
    """
    from gnani import tts

    os.makedirs(out_dir, exist_ok=True)
    out = []
    for text in texts:
        path = _path(text, voice, rate, lang, out_dir)
        if not os.path.exists(path):
            tts(text, voice=voice, lang=lang, out=path, rate=rate)
        out.append((path, text))
    return out
