#!/usr/bin/env python3
"""captions.py - turn word timestamps into caption clips for a capcut.py spec (a "text" track).

Input: a JSON word list in any of these shapes
  {"words": [[word, start, end], ...]}                    (whisper-style lists)
  {"words": [{"word": w, "start": s, "end": e}, ...]}     (faster-whisper / dicts)
  [[word, start, end], ...]
Times in seconds on the TIMELINE (if your words are in source time, offset them first with --shift).

  python captions.py words.json --max-chars 42 --max-dur 3.5 --gap 0.6 --style caption > captions_track.json

Output: {"type": "text", "name": "captions", "clips": [{"text", "at", "dur", "style"}, ...]} - paste it into
the spec's "tracks" list. A caption breaks at sentence ends, pauses longer than --gap, --max-chars or --max-dur.
"""
import argparse, json, sys


def load(path, cuts=None):
    """cuts: [[t0, t1], ...] ripple cuts of the spec - words said inside them are dropped (the build removes that
    audio), so no caption carries discarded words. Times stay pre-cut; the build shifts the captions."""
    d = json.load(open(path, encoding="utf-8"))
    w = d.get("words", d) if isinstance(d, dict) else d
    out = []
    for x in w:
        if isinstance(x, dict):
            out.append((str(x.get("word", x.get("text", ""))).strip(), float(x["start"]), float(x["end"])))
        else:
            out.append((str(x[0]).strip(), float(x[1]), float(x[2])))
    cuts = cuts or []
    return [x for x in out if x[0] and not any(a <= (x[1] + x[2]) / 2 < b for a, b in cuts)]


def load_cuts(path):
    """Approved ripple cuts from a cuts file {"cuts": [{"t0", "t1", ...}, ...]} (or [[t0, t1], ...]); [] if absent."""
    import os
    if not os.path.exists(path):
        return []
    d = json.load(open(path, encoding="utf-8"))
    d = d.get("cuts", d) if isinstance(d, dict) else d
    return [[float(c["t0"]), float(c["t1"])] if isinstance(c, dict) else [float(c[0]), float(c[1])] for c in d]


def group(words, max_chars, max_dur, gap):
    caps, cur = [], []
    for w in words:
        if cur:
            text = " ".join(x[0] for x in cur + [w])
            if (w[1] - cur[-1][2] > gap or len(text) > max_chars or w[2] - cur[0][1] > max_dur
                    or cur[-1][0][-1:] in ".?!"):
                caps.append(cur); cur = []
        cur.append(w)
    if cur:
        caps.append(cur)
    return caps


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("words")
    ap.add_argument("--max-chars", type=int, default=42)
    ap.add_argument("--max-dur", type=float, default=3.5)
    ap.add_argument("--gap", type=float, default=0.6, help="pause (s) that always starts a new caption")
    ap.add_argument("--shift", type=float, default=0.0, help="seconds added to every word time")
    ap.add_argument("--min-dur", type=float, default=0.8)
    ap.add_argument("--style", default="caption")
    ap.add_argument("--name", default="captions")
    a = ap.parse_args()
    words = [(w, s + a.shift, e + a.shift) for w, s, e in load(a.words)]
    clips = []
    caps = group(words, a.max_chars, a.max_dur, a.gap)
    for i, c in enumerate(caps):
        at = c[0][1]
        end = max(c[-1][2], at + a.min_dur)
        if i + 1 < len(caps):
            end = min(end, caps[i + 1][0][1] - 0.02)     # never overlap the next caption
        clips.append({"text": " ".join(x[0] for x in c), "at": round(at, 3), "dur": round(max(0.2, end - at), 3), "style": a.style})
    json.dump({"type": "text", "name": a.name, "clips": clips}, sys.stdout, indent=1, ensure_ascii=False)


if __name__ == "__main__":
    main()
