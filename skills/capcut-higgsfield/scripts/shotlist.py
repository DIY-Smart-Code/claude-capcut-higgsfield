#!/usr/bin/env python3
"""shotlist.py - time every shot from the real voice-over, not from the script.

Input: <work>/shots.json written by Claude before generating anything:
  {"title": "...", "shots": [{"id": 1, "line": "In 1947, ...", "prompt": "...", "motion": false}, ...]}
  One shot per spoken line, in order. "line" is the exact narration text of that shot.

  python shotlist.py WORK media/vo.wav [--model medium.en]

Transcribes the voice-over with faster-whisper (word timestamps, VAD), writes <work>/words.json, matches
each shot's line to the transcript and writes start / end / dur back into shots.json. Shot 1 starts at 0;
every shot ends where the next one starts, so the main track has no gaps. The last shot ends 0.6 s after
the last word.
"""
import argparse, difflib, json, os, re, sys


def norm(t):
    return re.sub(r"[^a-z0-9']+", " ", t.lower()).split()


def transcribe(audio, model_name):
    from faster_whisper import WhisperModel
    model = WhisperModel(model_name, device="auto", compute_type="auto")
    segs, _ = model.transcribe(audio, word_timestamps=True, vad_filter=True, language="en")
    return [{"word": w.word.strip(), "start": round(w.start, 3), "end": round(w.end, 3)}
            for s in segs for w in (s.words or [])]


def align(shots, words):
    script, owner = [], []
    for i, s in enumerate(shots):
        toks = norm(s["line"])
        script += toks
        owner += [i] * len(toks)
    heard = [(norm(w["word"]) or [""])[0] for w in words]
    sm = difflib.SequenceMatcher(None, script, heard, autojunk=False)
    first = {}
    for a, b, n in sm.get_matching_blocks():
        for k in range(n):
            first.setdefault(owner[a + k], b + k)
    starts = []
    for i in range(len(shots)):
        if i == 0:
            starts.append(0.0)
        elif i in first:
            starts.append(words[first[i]]["start"])
        else:
            starts.append(None)
    end_all = words[-1]["end"] + 0.6
    for i, v in enumerate(starts):         # unmatched line: interpolate between neighbours
        if v is None:
            prev = starts[i - 1]
            nxt = next((x for x in starts[i + 1:] if x is not None), end_all)
            starts[i] = round(prev + (nxt - prev) / 2, 3)
    for i, s in enumerate(shots):
        s["start"] = round(starts[i], 3)
        s["end"] = round(starts[i + 1] if i + 1 < len(shots) else end_all, 3)
        s["dur"] = round(s["end"] - s["start"], 3)
        s["matched"] = i in first or i == 0
    return shots


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("work")
    ap.add_argument("audio")
    ap.add_argument("--model", default="medium.en")
    a = ap.parse_args()
    sp = os.path.join(a.work, "shots.json")
    doc = json.load(open(sp, encoding="utf-8"))
    audio = a.audio if os.path.isabs(a.audio) else os.path.join(a.work, a.audio)
    words = transcribe(audio, a.model)
    json.dump({"words": words}, open(os.path.join(a.work, "words.json"), "w", encoding="utf-8"), indent=1)
    doc["shots"] = align(doc["shots"], words)
    doc["voiceover"] = os.path.relpath(audio, a.work).replace("\\", "/")
    json.dump(doc, open(sp, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    for s in doc["shots"]:
        flag = "" if s["matched"] else "   <- not matched, interpolated"
        print(f'{s["id"]:>3}  {s["start"]:7.2f}  {s["dur"]:5.2f}s  {s["line"][:60]}{flag}')
    short = [s["id"] for s in doc["shots"] if s["dur"] < 1.0]
    if short:
        print(f"warning: shots shorter than 1 s: {short} - merge them with a neighbour", file=sys.stderr)


if __name__ == "__main__":
    main()
