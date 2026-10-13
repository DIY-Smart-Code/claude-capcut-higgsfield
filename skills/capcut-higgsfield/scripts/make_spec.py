#!/usr/bin/env python3
"""make_spec.py - turn a timed shots.json into a capcut.py edit spec.

  python make_spec.py WORK [--vertical] [--title "The First Computer Bug"] [--no-captions]
                           [--music path.mp3 --music-volume 0.25] [--out capcut-spec.json]

Reads <work>/shots.json (after shotlist.py) and picks each shot's media by id:
  media/<id:03>.mp4 if the shot has motion and the clip exists, else media/<id:03>.png
  (a shot can reuse another shot's files with "media": "005")
  (--vertical uses media/v/<id:03>.* - generate those at 9:16).
Main track: one clip per shot, gapless, stills alternate a subtle zoom in / out. A motion clip shorter
than its shot is followed by its own still for the rest of the shot. Clip audio is muted - the voice-over
(<work>/<voiceover>) is the only sound. Captions come from <work>/words.json via captions.py.
"""
import argparse, json, os, subprocess, sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import captions  # noqa: E402


def dur_of(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of",
                          "default=nw=1:nk=1", path], capture_output=True, text=True).stdout.strip()
    return float(out or 0)


def pick(work, sid, motion, vertical):
    base = os.path.join(work, "media", "v" if vertical else "", sid if isinstance(sid, str) else f"{sid:03d}")
    mp4, png = base + ".mp4", base + ".png"
    still = png if os.path.exists(png) else None
    clip = mp4 if motion and os.path.exists(mp4) else None
    return clip, still


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("work")
    ap.add_argument("--vertical", action="store_true")
    ap.add_argument("--title", default=None)
    ap.add_argument("--no-captions", action="store_true")
    ap.add_argument("--music")
    ap.add_argument("--music-volume", type=float, default=0.25)
    ap.add_argument("--out", default="capcut-spec.json")
    a = ap.parse_args()
    work = os.path.abspath(a.work)
    doc = json.load(open(os.path.join(work, "shots.json"), encoding="utf-8"))
    w, h = (1080, 1920) if a.vertical else (1920, 1080)
    main_clips, missing, last_piece = [], [], []
    shot_fx, overlays = [], []
    for n, s in enumerate(doc["shots"]):
        clip, still = pick(work, s.get("media", s["id"]), s.get("motion"), a.vertical)
        if not (clip or still):
            missing.append(s["id"]); continue
        at, dur = s["start"], s["dur"]
        zoom = "in" if n % 2 == 0 else "out"
        first = len(main_clips)
        if clip:
            cd = min(dur_of(clip), dur)
            if 0.05 < dur - cd < 0.5 and cd > 1.5:
                cd = dur - 0.5                   # a still tail shorter than 0.5 s reads as a glitch: trim the clip
            cd = round(cd, 3)
            main_clips.append({"file": clip.replace("\\", "/"), "at": at, "dur": cd, "volume": 0})
            if dur - cd > 0.05:
                if not still:
                    missing.append(f'{s["id"]} (still for the tail)'); continue
                main_clips.append({"file": still.replace("\\", "/"), "at": round(at + cd, 3),
                                   "dur": round(s["end"] - round(at + cd, 3), 3), "zoom": zoom})
        else:
            main_clips.append({"file": still.replace("\\", "/"), "at": at, "dur": dur, "zoom": zoom})
        # CapCut look per shot: in-animation on the shot's first piece, out-animation + transition on its last
        if s.get("anim_in"):
            main_clips[first]["anim_in"] = s["anim_in"]
        if s.get("anim_out"):
            main_clips[-1]["anim_out"] = s["anim_out"]
        if s.get("transition"):
            last_piece.append((len(main_clips) - 1, s["transition"]))
        if s.get("effect"):                      # scene effect over this shot (or an offset window inside it)
            e = s["effect"]
            e_at = at + float(e.get("at", 0))
            shot_fx.append({"effect": e["name"], "at": round(e_at, 3),
                            "dur": round(min(float(e.get("dur", dur)), at + dur - e_at), 3),
                            **({"params": e["params"]} if e.get("params") else {}),
                            **({"from": e["from"]} if e.get("from") else {})})
        for o in s.get("overlays", []):          # extra on-screen text, e.g. a quote typed on
            o2 = {k: v for k, v in o.items() if k not in ("at", "dur")}
            o_at = at + float(o.get("at", 0))
            o2.update(at=round(o_at, 3), dur=round(min(float(o.get("dur", dur)), at + dur - o_at), 3))
            o2.setdefault("style", "overlay")
            overlays.append(o2)
    if missing:
        sys.exit(f"missing media for shots: {missing}")
    for i, tr in last_piece:                     # transitions need the next clip; keep them short enough
        if i + 1 < len(main_clips):
            room = 0.45 * min(main_clips[i]["dur"], main_clips[i + 1]["dur"])
            main_clips[i]["transition"] = {**tr, "dur": round(min(float(tr.get("dur", 0.8)), room), 3)}
    vo = os.path.join(work, doc["voiceover"]).replace("\\", "/")
    tracks = [{"type": "video", "name": "shots (Higgsfield)", "clips": main_clips},
              {"type": "audio", "name": "voiceover", "clips": [{"file": vo, "at": 0}]}]
    end = doc["shots"][-1]["end"]
    look = doc.get("look", {})
    for g in look.get("effects", []):            # whole-video effects (e.g. a vignette), one track each
        g_at = float(g.get("at", 0))
        tracks.append({"type": "effect", "name": "look: " + g["name"], "clips": [{
            "effect": g["name"], "at": g_at, "dur": round(float(g.get("dur", end - g_at)), 3),
            **({"params": g["params"]} if g.get("params") else {}), **({"from": g["from"]} if g.get("from") else {})}]})
    if shot_fx:
        tracks.append({"type": "effect", "name": "scene effects", "clips": shot_fx})
    if overlays:
        tracks.append({"type": "text", "name": "overlays", "clips": overlays})
    if a.music:
        tracks.append({"type": "audio", "name": "music", "clips": [{"file": os.path.abspath(a.music).replace("\\", "/"),
                       "at": 0, "dur": end, "volume": a.music_volume, "fade_in": 1.5, "fade_out": 2}]})
    if a.title:
        t = {"text": a.title, "at": 0.3, "dur": min(3.5, doc["shots"][0]["dur"]), "style": "title"}
        for k in ("anim_in", "anim_out"):           # e.g. look.title_anim_in = {"name": "Typewriter", "dur": 1.2}
            if look.get("title_" + k):
                t[k] = look["title_" + k]
        tracks.append({"type": "text", "name": "title", "clips": [t]})
    if not a.no_captions:
        words = captions.load(os.path.join(work, "words.json"))
        cuts = [sh["start"] for sh in doc["shots"][1:]]
        caps = []                            # captions never run across a cut: group each shot's words alone
        for i, t0 in enumerate([0.0] + cuts):
            t1 = cuts[i] if i < len(cuts) else 1e9
            chunk = [w for w in words if t0 - 0.05 <= (w[1] + w[2]) / 2 < t1 - 0.05]
            caps += captions.group(chunk, 32 if a.vertical else 42, 3.5, 0.6)
        merged = []                          # no one-word orphans ("computer.") after a line that runs on
        for c in caps:
            if merged and len(c) == 1 and merged[-1][-1][0][-1:] not in ".?!,":
                merged[-1] = merged[-1] + c
            else:
                merged.append(c)
        caps = merged
        clips = []
        for i, c in enumerate(caps):
            at = c[0][1]
            e = max(c[-1][2], at + 0.8)
            if i + 1 < len(caps):
                e = min(e, caps[i + 1][0][1] - 0.02)
            clips.append({"text": " ".join(x[0] for x in c), "at": round(at, 3), "dur": round(max(0.2, e - at), 3),
                          "style": "caption"})
        tracks.append({"type": "text", "name": "captions", "clips": clips})
    spec = {"mode": "replace", **({"effects_from": look["effects_from"]} if look.get("effects_from") else {}),
            "canvas": {"width": w, "height": h, "fps": 30}, "zoom_amount": 0.06,
            "text_styles": {
                "title": {"size": 12, "bold": True, "color": "#FFFFFF", "stroke": "#000000", "y": 0.55},
                "caption": {"size": 9 if a.vertical else 7, "color": "#FFFFFF", "background": "#000000",
                            "background_alpha": 0.6, "y": -0.45 if a.vertical else -0.78, "max_width": 0.8},
                "overlay": {"size": 10 if a.vertical else 9, "color": "#F4E9D2", "stroke": "#2B2118", "italic": True,
                            "y": 0.35, "max_width": 0.7}},
            "tracks": tracks}
    out = a.out if os.path.isabs(a.out) else os.path.join(work, a.out)
    json.dump(spec, open(out, "w", encoding="utf-8"), indent=1, ensure_ascii=False)
    print(f"{out}: {len(main_clips)} main clips, {end:.2f} s, canvas {w}x{h}")


if __name__ == "__main__":
    main()
