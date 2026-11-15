"""Measure what a phone line costs in accuracy.

    uv run python -m harness.cli                 # 8 Hindi clips, 10/5/0 dB sweep
    uv run python -m harness.cli -n 10
    uv run python -m harness.cli --lang bn-IN --levels 10
    uv run python -m harness.cli --rebuild       # ignore caches

`--lang` selects the reference corpus. Hindi keeps `harness_report.json` and
`harness_report.md`; every other language writes `harness_report_<lang>.*`, so
the two measurements never overwrite each other.

For each clip: transcribe clean 16 kHz, then degrade to 8 kHz µ-law at each
noise level and transcribe again. Everything is compared to the known reference
text, so no hand labelling is needed.

Transcripts are cached by audio hash — a re-run of the same levels costs zero.
"""
import argparse
import hashlib
import json
import os
import wave

from gnani import stt_file

from . import corpus, degrade, wer

CACHE = "cache"
STT_CACHE = os.path.join(CACHE, "stt")
NOISY_DIR = os.path.join(CACHE, "noisy")
DEFAULT_LEVELS = (10.0, 5.0, 0.0)      # dB SNR; clean is always measured too


# --- io -------------------------------------------------------------------

def _hash(data: bytes, lang: str, fmt: str) -> str:
    return hashlib.sha1(data + lang.encode() + fmt.encode()).hexdigest()[:16]


def read_wav(path: str):
    with wave.open(path) as w:
        return w.readframes(w.getnframes()), w.getframerate()


def write_wav(path: str, pcm: bytes, rate: int):
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)


def transcribe(path: str, lang: str, fmt: str = "verbatim",
               rebuild: bool = False) -> dict:
    """Cached transcription, keyed on the audio bytes and output format."""
    with open(path, "rb") as f:
        key = _hash(f.read(), lang, fmt)
    cached = os.path.join(STT_CACHE, f"{key}.json")
    if os.path.exists(cached) and not rebuild:
        with open(cached) as f:
            return json.load(f)
    os.makedirs(STT_CACHE, exist_ok=True)
    # No keyterm boosting: the measurement must not be flattered.
    out = stt_file(path, lang=lang, fmt=fmt)
    with open(cached, "w") as f:
        json.dump(out, f)
    return out


def phone_line(clean_path: str, snr: float | None, seed: int):
    """Degrade a clean clip to a phone line at `snr` dB. Returns the wav path."""
    pcm, rate = read_wav(clean_path)
    noisy, noisy_rate = degrade.telephony(pcm, rate, snr_db=snr, seed=seed)
    label = "clean" if snr is None else f"snr{int(snr)}"
    path = os.path.join(NOISY_DIR, f"{os.path.basename(clean_path)[:-4]}_{label}.wav")
    write_wav(path, noisy, noisy_rate)
    return path


# --- measurement ----------------------------------------------------------

def run(n: int, levels=DEFAULT_LEVELS, lang: str = "hi-IN",
        rebuild: bool = False) -> dict:
    entry = corpus.get(lang)
    pairs = corpus.ensure(entry["texts"][:n], voice=entry["voice"], lang=lang)
    rows = []
    for i, (clean_path, text) in enumerate(pairs, 1):
        row = {"i": i, "text": text, "levels": {}}
        for snr in (None, *levels):
            path = clean_path if snr is None else phone_line(clean_path, snr, seed=i)
            hyp = transcribe(path, lang, rebuild=rebuild).get("transcript", "") or ""
            row["levels"][label(snr)] = {
                "text": hyp,
                "wer": round(wer.wer(text, hyp), 4),
                "cer": round(wer.cer(text, hyp), 4),
            }
        rows.append(row)
        worst = row["levels"][label(levels[-1])]
        print(f"  {i:2d}/{len(pairs)}  clean {row['levels']['clean']['wer']:.0%} "
              f"-> {label(levels[-1])} {worst['wer']:.0%}")

    summary = []
    for snr in (None, *levels):
        key = label(snr)
        wers = [r["levels"][key]["wer"] for r in rows]
        cers = [r["levels"][key]["cer"] for r in rows]
        summary.append({
            "level": key,
            "snr_db": snr,
            "wer": round(sum(wers) / len(wers), 4),
            "cer": round(sum(cers) / len(cers), 4),
        })
    return {"lang": lang, "clips": len(rows), "summary": summary, "rows": rows}


def label(snr: float | None) -> str:
    return "clean" if snr is None else f"{snr:g}dB"


def report_paths(lang: str) -> tuple[str, str]:
    """(json, markdown) report paths. Hindi keeps the original names."""
    suffix = "" if lang == "hi-IN" else f"_{lang}"
    return f"harness_report{suffix}.json", f"harness_report{suffix}.md"


def report(result: dict, path: str = "harness_report.md",
           entry: dict | None = None) -> str:
    head = [
        "# Phone-line accuracy — Prisma v3.0",
        "",
        f"{result['clips']} clips · language `{result['lang']}` · "
        "clean studio audio degraded to 8 kHz G.711 µ-law + noise",
        "",
    ]
    if entry is not None and corpus.is_provisional(entry):
        head += [
            "The reference sentences are assistant-authored and await a "
            "native-speaker check, so this number is provisional.",
            "",
        ]
    head += [
        "| audio | WER | CER |",
        "|---|---|---|",
    ]
    for s in result["summary"]:
        name = "clean 16 kHz" if s["level"] == "clean" else f"phone line, {s['level']} SNR"
        bold = "**" if s["level"] == "clean" else ""
        head.append(f"| {name} | {bold}{s['wer']:.1%}{bold} | {s['cer']:.1%} |")

    worst = result["summary"][-1]["level"]
    head += ["", f"## Per clip at {worst}", "",
             "| # | reference | hypothesis | WER |", "|---|---|---|---|"]
    for r in result["rows"]:
        c = r["levels"][worst]
        head.append(f"| {r['i']} | {r['text']} | {c['text']} | {c['wer']:.0%} |")
    text = "\n".join(head) + "\n"
    with open(path, "w") as f:
        f.write(text)
    return text


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("-n", type=int, default=8, help="number of clips (max 10)")
    ap.add_argument("--levels", default=",".join(str(x) for x in DEFAULT_LEVELS),
                    help="comma separated dB SNR levels")
    ap.add_argument("--lang", default="hi-IN")
    ap.add_argument("--rebuild", action="store_true", help="ignore transcript cache")
    args = ap.parse_args()

    levels = tuple(float(x) for x in args.levels.split(","))
    try:
        entry = corpus.get(args.lang)
    except ValueError as exc:
        ap.error(str(exc))
    n = min(args.n, len(entry["texts"]))
    print(f"harness: {n} clips, levels {levels} dB SNR, lang={args.lang}")

    result = run(n, levels, args.lang, args.rebuild)
    for s in result["summary"]:
        print(f"  {s['level']:>7s}  WER {s['wer']:6.1%}   CER {s['cer']:6.1%}")

    json_path, md_path = report_paths(args.lang)
    with open(json_path, "w") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    report(result, md_path, entry)
    print(f"wrote {md_path} and {json_path}")


if __name__ == "__main__":
    main()
