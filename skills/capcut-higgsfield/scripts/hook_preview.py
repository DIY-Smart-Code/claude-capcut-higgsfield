#!/usr/bin/env python3
"""hook_preview.py - render the first seconds of the edit as an MP4 for the Higgsfield Virality Predictor.

  python hook_preview.py WORK [--seconds 15] [--vertical] [--out hook-preview.mp4]

Stitches the shots that fall inside the first --seconds (stills with the same subtle zoom, motion clips
as-is) under the voice-over, 720p, H.264 + AAC. If <work>/capcut-spec.json exists (run make_spec.py
first), its title and captions are burned in too, so the predictor sees what a viewer sees.
Upload it with the MCP's media_upload (scripts/hf_upload.py), then run virality_predictor on the media_id.
This is a quick proxy of the CapCut edit, not the final export.
"""
import argparse, json, os, subprocess, sys

ASS_NAME = "hook-preview.ass"


def ts(t):
    h, r = divmod(max(0.0, t), 3600)
    m, sec = divmod(r, 60)
    return f"{int(h)}:{int(m):02d}:{sec:05.2f}"


def write_ass(work, W, H, limit):
    """Title + captions from capcut-spec.json as an .ass file (white on a dark box, lower band)."""
    sp = os.path.join(work, "capcut-spec.json")
    if not os.path.exists(sp):
        return False
    spec = json.load(open(sp, encoding="utf-8"))
    events = []
    for tr in spec["tracks"]:
        if tr.get("type") != "text":
            continue
        style = "Title" if tr.get("name") == "title" else "Cap"
        for c in tr["clips"]:
            if c["at"] < limit:
                end = min(limit, c["at"] + c["dur"])
                text = " ".join(c["text"].split())
                events.append(f"Dialogue: 0,{ts(c['at'])},{ts(end)},{style},,0,0,0,,{text}")
    lines = [
        "[Script Info]", "ScriptType: v4.00+", f"PlayResX: {W}", f"PlayResY: {H}", "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, OutlineColour, BackColour, Bold, BorderStyle, "
        "Outline, Shadow, Alignment, MarginL, MarginR, MarginV",
        f"Style: Cap,Arial,{round(H * 0.045)},&H00FFFFFF,&H66000000,&H66000000,0,3,6,0,2,40,40,{round(H * 0.08)}",
        f"Style: Title,Arial,{round(H * 0.085)},&H00FFFFFF,&H00000000,&H00000000,1,1,4,0,8,40,40,{round(H * 0.2)}",
        "", "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text",
        *events,
    ]
    with open(os.path.join(work, ASS_NAME), "w", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return True


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("work")
    ap.add_argument("--seconds", type=float, default=15.0)
    ap.add_argument("--vertical", action="store_true")
    ap.add_argument("--out", default="hook-preview.mp4")
    a = ap.parse_args()
    work = os.path.abspath(a.work)
    doc = json.load(open(os.path.join(work, "shots.json"), encoding="utf-8"))
    W, H = (720, 1280) if a.vertical else (1280, 720)
    sub = "v" if a.vertical else ""
    inputs, chains, labels = [], [], []
    for n, s in enumerate(doc["shots"]):
        if s["start"] >= a.seconds:
            break
        d = min(s["dur"], a.seconds - s["start"])
        m = s.get("media", s["id"])
        base = os.path.join(work, "media", sub, m if isinstance(m, str) else f"{m:03d}")
        clip = base + ".mp4" if s.get("motion") and os.path.exists(base + ".mp4") else None
        k = sum(1 for x in inputs if x == "-i")
        if clip:
            inputs += ["-t", f"{d:.3f}", "-i", clip]
            chains.append(f"[{k}:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
                          f"fps=30,tpad=stop_mode=clone:stop_duration={d:.3f},trim=duration={d:.3f},setsar=1[s{n}]")
        else:
            frames = max(1, round(d * 30))
            z0, z1 = (1.0, 1.06) if n % 2 == 0 else (1.06, 1.0)
            zexpr = f"{z0}+({z1}-{z0})*on/{frames}"
            inputs += ["-i", base + ".png"]
            chains.append(f"[{k}:v]scale={W*2}:{H*2}:force_original_aspect_ratio=increase,crop={W*2}:{H*2},"
                          f"zoompan=z='{zexpr}':d={frames}:s={W}x{H}:fps=30:x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)',"
                          f"trim=duration={d:.3f},setsar=1[s{n}]")
        labels.append(f"[s{n}]")
    inputs += ["-i", os.path.join(work, doc["voiceover"])]
    vo_idx = sum(1 for x in inputs if x == "-i") - 1
    fc = ";".join(chains) + f";{''.join(labels)}concat=n={len(labels)}:v=1:a=0"
    if write_ass(work, W, H, a.seconds):
        fc += f"[vc];[vc]subtitles={ASS_NAME}[v]"     # relative name: ffmpeg runs in WORK, no path escaping
    else:
        fc += "[v]"
    out = a.out if os.path.isabs(a.out) else os.path.join(work, a.out)
    cmd = ["ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex", fc, "-map", "[v]", "-map", f"{vo_idx}:a",
           "-t", f"{a.seconds:.3f}", "-c:v", "libx264", "-preset", "veryfast", "-crf", "20", "-pix_fmt", "yuv420p",
           "-c:a", "aac", "-b:a", "160k", "-movflags", "+faststart", out]
    r = subprocess.run(cmd, cwd=work)
    if r.returncode:
        sys.exit(r.returncode)
    print(out)


if __name__ == "__main__":
    main()
