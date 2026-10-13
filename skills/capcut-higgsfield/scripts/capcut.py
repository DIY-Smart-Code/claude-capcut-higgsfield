#!/usr/bin/env python3
"""capcut.py - read and write CapCut desktop projects (drafts) directly, without opening CapCut.

CapCut desktop (international, Windows/macOS) keeps every project as a folder of plain JSON files.
This tool builds or edits the timeline in those files from a JSON "edit spec" (see SKILL.md), using
object templates copied from real CapCut drafts (templates.json), so CapCut opens the result as a
normal, fully editable project.

Commands (run with python 3.9+, stdlib only; ffprobe on PATH for media probing):
  capcut.py doctor                          # drafts folder, CapCut running?, app version, projects
  capcut.py list                            # projects (name, modified, duration, folder)
  capcut.py inspect  <project> [--json]     # timeline summary (tracks, clips, text, keyframes)
  capcut.py build    <project> <spec.json> [--append] [--force] [--dry-run]
  capcut.py new      <name> --like <existing project> [--width 1920 --height 1080 --fps 30]
  capcut.py backup   <project>              # copy the project's JSON files to the backup folder
  capcut.py restore  <project> [<backup-dir>]   # put the newest (or given) backup back

<project> = project name as shown in CapCut, its folder name, or a path to the folder.
Times in specs are SECONDS; CapCut stores MICROSECONDS.
"""
import argparse, copy, datetime as dt, glob, json, os, re, shutil, subprocess, sys, time, uuid

HERE = os.path.dirname(os.path.abspath(__file__))
T = json.load(open(os.path.join(HERE, "templates.json"), encoding="utf-8"))
US = 1_000_000
PHOTO_DURATION = 10_800_000_000          # CapCut gives stills a 3 h source duration
IMAGE_EXT = {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif", ".heic", ".tif", ".tiff"}
AUDIO_EXT = {".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg", ".opus", ".wma", ".aiff", ".aif", ".mpeg"}
MAIN_NAMES = ("draft_content.json", "draft_info.json")    # Windows CapCut / macOS CapCut name for the timeline file


# ------------------------------------------------------------------------------------------ locations
def drafts_root():
    if os.environ.get("CAPCUT_DRAFTS"):
        return os.environ["CAPCUT_DRAFTS"]
    if sys.platform == "win32":
        return os.path.join(os.environ["LOCALAPPDATA"], "CapCut", "User Data", "Projects", "com.lveditor.draft")
    return os.path.expanduser("~/Movies/CapCut/User Data/Projects/com.lveditor.draft")


def backup_root():
    return os.environ.get("CAPCUT_BACKUPS") or os.path.join(os.path.expanduser("~"), ".capcut-timeline", "backups")


def app_dir():
    """Newest installed CapCut app folder (Windows: %LOCALAPPDATA%/CapCut/Apps/<version>)."""
    if sys.platform == "win32":
        apps = os.path.join(os.environ["LOCALAPPDATA"], "CapCut", "Apps")
        vers = [d for d in os.listdir(apps) if re.match(r"^\d+(\.\d+)+$", d)] if os.path.isdir(apps) else []
        if vers:
            return os.path.join(apps, max(vers, key=lambda v: tuple(map(int, v.split(".")))))
    return None


def installed_version():
    a = app_dir()
    return tuple(int(x) for x in os.path.basename(a).split(".")[:3]) if a else ()


def default_font():
    a = app_dir()
    for name in ("en.ttf", "CapCutSansText-Regular.otf"):
        if a and os.path.exists(os.path.join(a, "Resources", "Font", "SystemFont", name)):
            return fwd(os.path.join(a, "Resources", "Font", "SystemFont", name))
    return ""


def capcut_running():
    try:
        if sys.platform == "win32":
            out = subprocess.run(["tasklist", "/FI", "IMAGENAME eq CapCut.exe", "/NH"], capture_output=True, text=True).stdout
            return "CapCut.exe" in out
        return subprocess.run(["pgrep", "-x", "CapCut"], capture_output=True).returncode == 0
    except Exception:
        return False


def main_file(folder):
    """Timeline file name used in this project folder (draft_content.json on Windows, draft_info.json on macOS)."""
    for n in MAIN_NAMES:
        if os.path.exists(os.path.join(folder, n)):
            return n
    return MAIN_NAMES[0] if sys.platform == "win32" else MAIN_NAMES[1]


def is_project(folder):
    return any(os.path.exists(os.path.join(folder, n)) for n in MAIN_NAMES)


def fwd(p):
    return os.path.abspath(p).replace("\\", "/")


def new_id():
    """CapCut-style id: upper-case UUID with a lower-case third group (e.g. CBA9C120-9346-4cfb-96DC-...)."""
    u = str(uuid.uuid4()).upper().split("-")
    u[2] = u[2].lower()
    return "-".join(u)


def us(sec):
    return int(round(float(sec) * US))


def now_us():
    return int(time.time() * US)


def load_json(p):
    return json.load(open(p, encoding="utf-8"))


def dump_json(obj, p):
    tmp = p + ".capcut-timeline.tmp"
    with open(tmp, "w", encoding="utf-8") as f:
        json.dump(obj, f, ensure_ascii=False, separators=(",", ":"))
    os.replace(tmp, p)


# ------------------------------------------------------------------------------------------- projects
def registry():
    p = os.path.join(drafts_root(), "root_meta_info.json")
    return load_json(p) if os.path.exists(p) else {"all_draft_store": []}


def list_projects():
    out, seen = [], set()
    for e in registry().get("all_draft_store", []):
        folder = e.get("draft_fold_path", "")
        if is_project(folder):
            out.append({"name": e.get("draft_name"), "folder": fwd(folder), "modified_us": e.get("tm_draft_modified", 0),
                        "duration_us": e.get("tm_duration", 0)})
            seen.add(fwd(folder).lower())
    for f in [x for n in MAIN_NAMES for x in glob.glob(os.path.join(drafts_root(), "*", n))]:
        folder = fwd(os.path.dirname(f))
        if folder.lower() not in seen:
            out.append({"name": os.path.basename(folder), "folder": folder, "modified_us": int(os.path.getmtime(f) * US),
                        "duration_us": 0, "unregistered": True})
    return sorted(out, key=lambda x: -x["modified_us"])


def project_dir(ref):
    if is_project(ref):
        return fwd(ref)
    projs = list_projects()
    for key in ("name", "folder"):
        hits = [p for p in projs if (p[key] if key == "name" else os.path.basename(p[key])) == ref]
        if hits:
            return hits[0]["folder"]
    low = [p for p in projs if (p["name"] or "").lower() == ref.lower()]
    if low:
        return low[0]["folder"]
    sys.exit("project not found: %r (try `capcut.py list`)" % ref)


# ---------------------------------------------------------------------------------------------- media
def probe(path):
    """duration_us, width, height, has_audio, kind (video|photo|audio)."""
    ext = os.path.splitext(path)[1].lower()
    if not os.path.exists(path):
        sys.exit("media not found: %s" % path)
    info = {"duration_us": 0, "width": 0, "height": 0, "has_audio": False,
            "kind": "photo" if ext in IMAGE_EXT else ("audio" if ext in AUDIO_EXT else "video")}
    try:
        r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration:stream=codec_type,width,height,duration",
                            "-of", "json", path], capture_output=True, text=True, check=True)
        j = json.loads(r.stdout)
        st = j.get("streams", [])
        v = [s for s in st if s.get("codec_type") == "video"]
        info["has_audio"] = any(s.get("codec_type") == "audio" for s in st)
        if v:
            info["width"], info["height"] = int(v[0].get("width") or 0), int(v[0].get("height") or 0)
        d = j.get("format", {}).get("duration") or (v[0].get("duration") if v else None)
        if d and info["kind"] != "photo":
            info["duration_us"] = us(float(d))
        if info["kind"] == "video" and not v:
            info["kind"] = "audio"
    except (OSError, subprocess.CalledProcessError, ValueError):
        if info["kind"] != "photo":
            sys.exit("ffprobe failed on %s - install ffmpeg or pass dur explicitly" % path)
    if info["kind"] == "photo":
        info["duration_us"] = PHOTO_DURATION
    return info


# ---------------------------------------------------------------------------------------------- draft
class Draft:
    def __init__(self, folder):
        self.folder = fwd(folder)
        self.main = main_file(self.folder)
        self.path = os.path.join(self.folder, self.main)
        self.d = load_json(self.path)
        self._probe_cache = {}
        self.font = default_font()

    # ---- files CapCut 9.x reads/writes for the timeline
    def main_timeline_dir(self):
        pj = os.path.join(self.folder, "Timelines", "project.json")
        if os.path.exists(pj):
            tid = load_json(pj).get("main_timeline_id")
            if tid and os.path.isdir(os.path.join(self.folder, "Timelines", tid)):
                return os.path.join(self.folder, "Timelines", tid)
        return None

    def content_paths(self):
        paths = [self.path]
        if os.path.exists(os.path.join(self.folder, "template-2.tmp")):
            paths.append(os.path.join(self.folder, "template-2.tmp"))
        tl = self.main_timeline_dir()
        if tl:
            for n in (self.main, "template-2.tmp"):
                p = os.path.join(tl, n)
                if n == self.main or os.path.exists(p):
                    paths.append(p)
        return paths

    # ---- materials
    def mats(self, key):
        return self.d["materials"].setdefault(key, [])

    def index(self):
        idx = {}
        for k, v in self.d["materials"].items():
            if isinstance(v, list):
                for m in v:
                    if isinstance(m, dict) and "id" in m:
                        idx[m["id"]] = (k, m)
        return idx

    def clear(self):
        """Empty the timeline: drop all tracks and every material a segment used (media bin is untouched)."""
        used = set()
        for t in self.d["tracks"]:
            for s in t["segments"]:
                used.add(s.get("material_id"))
                used.update(s.get("extra_material_refs", []))
        for k, v in self.d["materials"].items():
            if isinstance(v, list):
                self.d["materials"][k] = [m for m in v if not (isinstance(m, dict) and m.get("id") in used)]
        self.d["tracks"] = []
        self.d["duration"] = 0

    # ---- tracks
    def track(self, ttype, name=None, new=False):
        same = [t for t in self.d["tracks"] if t["type"] == ttype]
        if name is not None and not new:
            for t in same:
                if t.get("name") == name:
                    return t
        if same and not new and name is None:
            return same[0]
        t = copy.deepcopy(T["track"])
        t.update(id=new_id(), type=ttype, name=name or "", is_default_name=not bool(name))
        t["flag"] = {"video": 0 if not same else 2, "text": 1}.get(ttype, 0)
        self.d["tracks"].append(t)
        return t

    def _layer(self, track):
        same = [t for t in self.d["tracks"] if t["type"] == track["type"]]
        n = same.index(track)
        render = {"video": n, "text": 14000 + n, "effect": 11000 + n}.get(track["type"], 0)
        return render, self.d["tracks"].index(track)

    def _extras(self, keys, fade=None):
        refs = []
        for k in keys:
            o = copy.deepcopy(T["extras"][k])
            o["id"] = new_id()
            self.mats(k).append(o)
            refs.append(o["id"])
        if fade:
            o = copy.deepcopy(T["audio_fade"])
            o.update(id=new_id(), fade_in_duration=us(fade[0]), fade_out_duration=us(fade[1]))
            self.mats("audio_fades").append(o)
            refs.insert(2, o["id"])
        return refs

    def frames(self, sec):
        """Snap seconds to the project's frame grid, in µs (CapCut's own times are frame-aligned)."""
        fps = float(self.d.get("fps") or 30.0)
        return int(round(round(float(sec) * fps) * US / fps))

    def _segment(self, kind, track, material_id, at, src_in, dur, refs):
        s = copy.deepcopy(T["kinds"][kind]["segment"])
        start, end = self.frames(at), self.frames(round(at + dur, 6))
        if end <= start:
            sys.exit("clip at %.3f s is shorter than one frame" % at)
        s.update(id=new_id(), material_id=material_id, extra_material_refs=refs,
                 target_timerange={"start": start, "duration": end - start},
                 source_timerange=None if kind == "text" else {"start": self.frames(src_in), "duration": end - start})
        s["render_index"], s["track_render_index"] = self._layer(track)
        for other in track["segments"]:
            a, b = other["target_timerange"]["start"], other["target_timerange"]["start"] + other["target_timerange"]["duration"]
            if start < b and end > a:
                sys.exit("overlap on %s track %r at %.3f s - put the clip on another track" % (track["type"], track.get("name"), at))
        track["segments"].append(s)
        track["segments"].sort(key=lambda x: x["target_timerange"]["start"])
        return s

    # ---- CapCut resources copied from a donor project (transitions, in/out animations)
    def transition(self, seg, obj, dur):
        """Transition at the END of seg (into the next clip on the same track). obj = a donor's transition material."""
        o = copy.deepcopy(obj)
        o.update(id=new_id(), duration=us(dur))
        self.mats("transitions").append(o)
        seg["extra_material_refs"].insert(min(2, len(seg["extra_material_refs"])), o["id"])

    def animate(self, seg, typ, obj, dur):
        """In/out animation on a video clip. obj = a donor's animation entry (material_animations[].animations[])."""
        ids = set(seg["extra_material_refs"])
        ma = next((m for m in self.mats("material_animations") if m.get("id") in ids), None)
        if ma is None:
            sys.exit("clip at %.3f s has no material_animations slot" % (seg["target_timerange"]["start"] / US))
        a = copy.deepcopy(obj)
        a["duration"] = us(dur)
        a["start"] = 0 if typ == "in" else seg["target_timerange"]["duration"] - a["duration"]
        ma["animations"] = [x for x in ma["animations"] if x.get("type") != typ] + [a]
        if sum(x["duration"] for x in ma["animations"]) > seg["target_timerange"]["duration"]:
            sys.exit("animations longer than the clip at %.3f s" % (seg["target_timerange"]["start"] / US))

    # ---- clips
    def add_media(self, path, at, src_in=0.0, dur=None, track=None, volume=1.0, scale=1.0, x=0.0, y=0.0,
                  alpha=1.0, fade=None, kind=None):
        """Video, still image or audio file on a track. dur defaults to the rest of the file (5 s for stills)."""
        path = fwd(path)
        info = self._probe_cache.get(path) or probe(path)
        self._probe_cache[path] = info
        kind = kind or info["kind"]
        if dur is None:
            dur = 5.0 if kind == "photo" else info["duration_us"] / US - src_in
        if kind != "photo" and us(src_in + dur) > info["duration_us"] + 2000:
            sys.exit("%s: in %.3f + dur %.3f runs past the file end (%.3f s)" % (path, src_in, dur, info["duration_us"] / US))
        if kind == "audio":
            m = copy.deepcopy(T["kinds"]["audio"]["material"])
            m.update(id=new_id(), path=path, name=os.path.basename(path), duration=info["duration_us"],
                     music_id=str(uuid.uuid4()), type="extract_music")
            self.mats("audios").append(m)
            track = track or self.track("audio")
            s = self._segment("audio", track, m["id"], at, src_in, dur, self._extras(T["kinds"]["audio"]["extras"], fade))
        else:
            m = copy.deepcopy(T["kinds"][kind]["material"])
            m.update(id=new_id(), path=path, material_name=os.path.basename(path), duration=info["duration_us"],
                     width=info["width"], height=info["height"], type=kind)
            if "has_audio" in m:
                m["has_audio"] = info["has_audio"]
            self.mats("videos").append(m)
            track = track or self.track("video")
            s = self._segment(kind, track, m["id"], at, src_in, dur, self._extras(T["kinds"][kind]["extras"]))
            s["clip"] = {"alpha": float(alpha), "flip": {"horizontal": False, "vertical": False}, "rotation": 0.0,
                         "scale": {"x": float(scale), "y": float(scale)}, "transform": {"x": float(x), "y": float(y)}}
            s["uniform_scale"] = {"on": True, "value": 1.0}
        s["volume"] = float(volume)
        s["last_nonzero_volume"] = float(volume) if volume > 0 else 1.0
        return s

    def add_text(self, text, at, dur, track=None, size=8.0, color="#FFFFFF", bold=False, italic=False,
                 align=1, x=0.0, y=-0.75, scale=1.0, max_width=0.82, stroke=None, stroke_width=0.06,
                 shadow=False, background=None, background_alpha=1.0, font=None):
        """Plain CapCut text. x/y: -1..1 from the canvas centre (y up). max_width: wrap width as a share of the frame."""
        rgb = lambda h: [round(int(h.lstrip("#")[i:i + 2], 16) / 255, 4) for i in (0, 2, 4)]
        style = {"fill": {"content": {"render_type": "solid", "solid": {"color": rgb(color)}}},
                 "font": {"path": font or self.font, "id": ""}, "size": float(size),
                 "range": [0, len(text.encode("utf-16-le")) // 2]}
        if bold:
            style["bold"] = True
        if italic:
            style["italic"] = True
        if stroke:
            style["strokes"] = [{"alpha": 1.0, "content": {"render_type": "solid", "solid": {"alpha": 1.0, "color": rgb(stroke)}},
                                 "width": float(stroke_width)}]
        if shadow:
            style["shadows"] = [{"diffuse": 0.005, "alpha": 0.35, "distance": 3.0, "angle": -45,
                                 "content": {"render_type": "solid", "solid": {"color": [0, 0, 0]}}}]
        m = copy.deepcopy(T["kinds"]["text"]["material"])
        m.update(id=new_id(), content=json.dumps({"text": text, "styles": [style]}, ensure_ascii=False),
                 font_path=font or self.font, font_size=float(size), text_color=color.upper(), alignment=int(align),
                 line_max_width=float(max_width), type="text", has_shadow=bool(shadow))
        if stroke:
            m.update(border_color=stroke, border_width=float(stroke_width))
        if background:
            m.update(background_style=1, background_color=background, background_alpha=float(background_alpha))
        # check_flag bits as CapCut writes them: 7 base, +8 stroke, +16 background, +32 shadow
        m["check_flag"] = 7 | (8 if stroke else 0) | (16 if background else 0) | (32 if shadow else 0)
        self.mats("texts").append(m)
        track = track or self.track("text")
        s = self._segment("text", track, m["id"], at, 0, dur, self._extras(T["kinds"]["text"]["extras"]))
        s["clip"] = {"alpha": 1.0, "flip": {"horizontal": False, "vertical": False}, "rotation": 0.0,
                     "scale": {"x": float(scale), "y": float(scale)}, "transform": {"x": float(x), "y": float(y)}}
        return s

    def add_effect(self, mat, seg_tpl, at, dur, track, params=None):
        """Scene effect (Vignette, Cinema, ...) over [at, at+dur] on an effect track. mat/seg_tpl come from a donor."""
        m = copy.deepcopy(mat)
        m["id"] = new_id()
        for k, v in (params or {}).items():
            if k in ("value", "intensity"):
                m["value"] = float(v)
                continue
            for ap in m.get("adjust_params") or []:
                if ap.get("name") == k or ap.get("name", "").endswith("_" + k):
                    ap["value"] = float(v)
        self.mats("video_effects").append(m)
        s = copy.deepcopy(seg_tpl)
        start, end = self.frames(at), self.frames(round(at + dur, 6))
        if end <= start:
            sys.exit("effect at %.3f s is shorter than one frame" % at)
        s.update(id=new_id(), material_id=m["id"], extra_material_refs=[], common_keyframes=[], keyframe_refs=[],
                 target_timerange={"start": start, "duration": end - start}, source_timerange=None)
        s["render_index"], s["track_render_index"] = self._layer(track)
        for other in track["segments"]:
            a, b = other["target_timerange"]["start"], other["target_timerange"]["start"] + other["target_timerange"]["duration"]
            if start < b and end > a:
                sys.exit("overlap on effect track %r at %.3f s - put the effect on another track" % (track.get("name"), at))
        track["segments"].append(s)
        track["segments"].sort(key=lambda x: x["target_timerange"]["start"])
        return s

    # ---- keyframes
    def keyframes(self, seg, prop, points):
        """points: [(seconds from the segment's start on the timeline, value), ...].
        CapCut measures time_offset in the clip's SOURCE time, so the segment's source in-point is added."""
        base = (seg.get("source_timerange") or {}).get("start", 0)
        speed = float(seg.get("speed") or 1.0)
        kl = [{"curveType": "Line", "graphID": "", "id": new_id(), "left_control": {"x": 0.0, "y": 0.0},
               "right_control": {"x": 0.0, "y": 0.0}, "string_value": "", "time_offset": base + us(t * speed),
               "values": [float(v)]} for t, v in points]
        seg["common_keyframes"] = [k for k in seg["common_keyframes"] if k["property_type"] != prop]
        seg["common_keyframes"].append({"id": new_id(), "keyframe_list": kl, "material_id": "", "property_type": prop})

    def zoom(self, seg, start, end, ease_to=None):
        """Smooth scale move over the whole clip (Ken Burns). Writes the four keyframe lanes CapCut writes itself."""
        d = seg["target_timerange"]["duration"] / US
        c = seg["clip"]
        times = [0.0, d - 1 / 30] if d > 0.1 else [0.0]
        self.keyframes(seg, "KFTypeScaleX", [(times[0], start)] + ([(times[-1], end)] if len(times) > 1 else []))
        for prop, val in (("KFTypePositionX", c["transform"]["x"]), ("KFTypePositionY", c["transform"]["y"]),
                          ("KFTypeRotation", c["rotation"])):
            self.keyframes(seg, prop, [(t, val) for t in times])
        c["scale"] = {"x": float(start), "y": float(start)}

    # ---- save
    def finish(self):
        end = 0
        for t in self.d["tracks"]:
            for s in t["segments"]:
                end = max(end, s["target_timerange"]["start"] + s["target_timerange"]["duration"])
        self.d["duration"] = end
        self.d["update_time"] = int(time.time())

    def validate(self):
        idx, problems = self.index(), []
        for t in self.d["tracks"]:
            last = -1
            for s in sorted(t["segments"], key=lambda x: x["target_timerange"]["start"]):
                if s["material_id"] not in idx:
                    problems.append("segment %s: material %s missing" % (s["id"], s["material_id"]))
                for r in s.get("extra_material_refs", []):
                    if r not in idx:
                        problems.append("segment %s: extra ref %s missing" % (s["id"], r))
                tr = s["target_timerange"]
                if tr["duration"] <= 0:
                    problems.append("segment %s: duration %d" % (s["id"], tr["duration"]))
                if tr["start"] < last - 1:
                    problems.append("%s track %r: overlap at %.3f s" % (t["type"], t.get("name"), tr["start"] / US))
                last = tr["start"] + tr["duration"]
                k, m = idx.get(s["material_id"], (None, {}))
                p = m.get("path", "") if k in ("videos", "audios") else ""
                if p and not p.startswith("##_") and not os.path.exists(p):
                    problems.append("missing media file: %s" % p)
        return problems

    def save(self, force=False, dry_run=False):
        if (capcut_running() or os.path.exists(os.path.join(self.folder, ".locked"))) and not force:
            sys.exit("CapCut is running (or this project is open: .locked). Quit CapCut first - it keeps the project "
                     "in memory and overwrites these files on close - then run again.")
        self.finish()
        problems = self.validate()
        if problems:
            sys.exit("not saved - validation failed:\n  " + "\n  ".join(problems[:20]))
        if dry_run:
            return None
        bk = backup(self.folder)
        meta_path = os.path.join(self.folder, "draft_meta_info.json")
        meta = load_json(meta_path) if os.path.exists(meta_path) else None
        if meta is not None:
            # media bin first: CapCut 9.x expects every timeline file in the bin; the bin entry id doubles as the
            # material's local_material_id (blank ids made clips "inaccessible" on some 9.x builds)
            ids = add_to_media_bin(meta, self.d)
            for key in ("videos", "audios"):
                for m in self.d["materials"].get(key, []):
                    if not m.get("local_material_id") and fwd(m.get("path", "") or "x").lower() in ids:
                        m["local_material_id"] = ids[fwd(m["path"]).lower()]
            gone = prune_missing_from_bin(meta)
            for _, p in gone:
                print("media bin: removed %s (file not found; CapCut would ask to 'Link media')" % p, file=sys.stderr)
        for p in self.content_paths():
            dump_json(self.d, p)
        added = meta.pop("_added_bin_ids", []) if meta is not None else []
        touch_meta(self.folder, self.d["duration"], meta)
        list_in_media_panel(self.folder, added)
        if meta is not None and gone:
            unlist_from_media_panel(self.folder, {i for i, _ in gone})
        return bk


# ------------------------------------------------------------------------------------- meta / backups
def touch_meta(folder, duration_us, meta=None):
    """Keep CapCut's project list in step: duration + modified time in draft_meta_info.json (meta = already-loaded
    and updated copy, or None to load it) and in the project's root_meta_info.json entry."""
    t = now_us()
    mp = os.path.join(folder, "draft_meta_info.json")
    if meta is None and os.path.exists(mp):
        meta = load_json(mp)
    if meta is not None:
        meta["tm_duration"], meta["tm_draft_modified"] = duration_us, t
        dump_json(meta, mp)
    rp = os.path.join(drafts_root(), "root_meta_info.json")
    if os.path.exists(rp):
        r = load_json(rp)
        for e in r.get("all_draft_store", []):
            if fwd(e.get("draft_fold_path", "")).lower() == fwd(folder).lower():
                e["tm_duration"], e["tm_draft_modified"] = duration_us, t
        dump_json(r, rp)


def add_to_media_bin(meta, d):
    """Add every local file the timeline uses to the media bin (draft_materials type 0) if it is not there yet.
    Returns {lower-case path: bin entry id} for all files in the bin."""
    groups = meta.setdefault("draft_materials", [])
    g = next((x for x in groups if x.get("type") == 0), None)
    if g is None:
        g = {"type": 0, "value": []}
        groups.insert(0, g)
    have = {fwd(v.get("file_Path", "")).lower(): v.get("id") for v in g["value"] if v.get("file_Path")}
    t = int(time.time())
    for key, metetype in (("videos", None), ("audios", "music")):
        for m in d["materials"].get(key, []):
            p = m.get("path", "")
            if not p or p.startswith("##_") or fwd(p).lower() in have:
                continue
            mt = metetype or ("photo" if m.get("type") == "photo" else "video")
            eid = str(uuid.uuid4())
            g["value"].append({"ai_group_type": "", "create_time": t, "duration": m.get("duration", 0), "enter_from": 0,
                               "extra_info": os.path.basename(p), "file_Path": p, "height": m.get("height", 0),
                               "id": eid, "import_time": t, "import_time_ms": now_us(), "item_source": 1,
                               "material_color_tag": "", "md5": "", "metetype": mt,
                               "roughcut_time_range": {"duration": m.get("duration", 0), "start": 0},
                               "sub_time_range": {"duration": -1, "start": -1}, "type": 0, "width": m.get("width", 0)})
            have[fwd(p).lower()] = eid
            meta.setdefault("_added_bin_ids", []).append(eid)
    return have


def prune_missing_from_bin(meta):
    """Drop media-bin entries (type 0) whose local file no longer exists. On opening, CapCut asks the user to
    "Link media" for each one, even when the timeline doesn't use it (seen 2026-10-11 on a rebuilt project whose
    bin still listed deleted/moved files). Timeline files are checked by validate(), so these are unused ones.
    The backup keeps the old entries. Returns the removed (id, path) pairs."""
    gone = []
    for g in meta.get("draft_materials", []):
        if g.get("type") != 0:
            continue
        keep = []
        for v in g.get("value", []):
            p = v.get("file_Path", "")
            if p and os.path.isabs(p) and not os.path.exists(p):
                gone.append((v.get("id"), p))
            else:
                keep.append(v)
        g["value"] = keep
    return gone


def unlist_from_media_panel(folder, ids):
    p = os.path.join(folder, "draft_virtual_store.json")
    if not ids or not os.path.exists(p):
        return
    v = load_json(p)
    for g in v.get("draft_virtual_store", []):
        if g.get("type") == 1:
            g["value"] = [x for x in g.get("value", []) if x.get("child_id") not in ids]
    dump_json(v, p)


def list_in_media_panel(folder, ids):
    """CapCut 9.x lists media-bin items in draft_virtual_store.json (type 1: child_id = bin entry id, parent_id =
    bin folder, "" = top level). Without this an imported file is on the timeline but not in the media panel."""
    if not ids:
        return
    p = os.path.join(folder, "draft_virtual_store.json")
    v = load_json(p) if os.path.exists(p) else virtual_store_skeleton()
    g = next((x for x in v.setdefault("draft_virtual_store", []) if x.get("type") == 1), None)
    if g is None:
        g = {"type": 1, "value": []}
        v["draft_virtual_store"].append(g)
    have = {x.get("child_id") for x in g["value"]}
    g["value"] += [{"child_id": i, "parent_id": ""} for i in ids if i not in have]
    dump_json(v, p)


def virtual_store_skeleton():
    return {"draft_materials": [], "draft_virtual_store": [
        {"type": 0, "value": [{"creation_time": 0, "display_name": "", "filter_type": 0, "id": "", "import_time": 0,
                               "import_time_us": 0, "material_color_tag": "", "sort_sub_type": 0, "sort_type": 0,
                               "subdraft_filter_type": 0}]},
        {"type": 1, "value": []}, {"type": 2, "value": []}]}


def backup(folder):
    name = os.path.basename(folder.rstrip("/"))
    dest = os.path.join(backup_root(), name, dt.datetime.now().strftime("%Y%m%d-%H%M%S"))
    os.makedirs(dest, exist_ok=True)
    for root, _, files in os.walk(folder):
        for f in files:
            if f.endswith((".json", ".tmp")) or f in ("draft_settings", "draft.extra"):
                src = os.path.join(root, f)
                rel = os.path.relpath(src, folder)
                os.makedirs(os.path.join(dest, os.path.dirname(rel)), exist_ok=True)
                shutil.copy2(src, os.path.join(dest, rel))
    reg = os.path.join(drafts_root(), "root_meta_info.json")
    if os.path.exists(reg):
        shutil.copy2(reg, os.path.join(dest, "_root_meta_info.json"))
    return dest


def restore(folder, src=None):
    name = os.path.basename(folder.rstrip("/"))
    if not src:
        cands = sorted(glob.glob(os.path.join(backup_root(), name, "*")))
        if not cands:
            sys.exit("no backups for %s" % name)
        src = cands[-1]
    if capcut_running():
        sys.exit("Quit CapCut first.")
    for root, _, files in os.walk(src):
        for f in files:
            if f == "_root_meta_info.json":
                continue
            rel = os.path.relpath(os.path.join(root, f), src)
            os.makedirs(os.path.join(folder, os.path.dirname(rel)), exist_ok=True)
            shutil.copy2(os.path.join(root, f), os.path.join(folder, rel))
    return src


# --------------------------------------------------------------------------------------------- build
class Donors:
    """Finds CapCut resource objects (transitions, animations) by name in a project where the user applied them,
    so a build can reuse CapCut's exact object (resource ids, category). Missing effect files are fetched by CapCut."""

    def __init__(self, default=None):
        self.default, self.cache = default, {}

    def _draft(self, folder):
        if folder not in self.cache:
            try:
                self.cache[folder] = load_json(os.path.join(folder, main_file(folder)))
            except Exception:
                self.cache[folder] = {"materials": {}}
        return self.cache[folder]

    def _folders(self, project):
        proj = project or self.default
        return proj, ([project_dir(proj)] if proj else [p["folder"] for p in list_projects()])

    def find(self, kind, name, typ=None, project=None, mtype="video"):
        """kind "transition" or "animation" (typ in/out; mtype "video" for clips, "sticker" for text)."""
        proj, folders = self._folders(project)
        for f in folders:
            m = self._draft(f).get("materials", {})
            if kind == "transition":
                for t in m.get("transitions", []):
                    if t.get("name", "").lower() == name.lower():
                        return t
            else:
                for ma in m.get("material_animations", []):
                    for a in ma.get("animations", []):
                        if (a.get("name", "").lower() == name.lower() and a.get("type") == typ
                                and a.get("material_type", "video") == mtype):
                            return a
        sys.exit("no %s %r%s in %s - apply it once in any CapCut project (see `capcut.py catalog`)"
                 % (kind, name, " (%s)" % typ if typ else "", proj or "any project"))

    def find_effect(self, name, project=None):
        """A scene effect (materials.video_effects) plus the effect-track segment that used it, as templates."""
        proj, folders = self._folders(project)
        for f in folders:
            d = self._draft(f)
            mats = {m["id"]: m for m in d.get("materials", {}).get("video_effects", []) if isinstance(m, dict)}
            for t in d.get("tracks", []):
                if t.get("type") != "effect":
                    continue
                for seg in t.get("segments", []):
                    m = mats.get(seg.get("material_id"))
                    if m and m.get("name", "").lower() == name.lower():
                        return m, seg
        sys.exit("no scene effect %r in %s - apply it once in any CapCut project (see `capcut.py catalog`)"
                 % (name, proj or "any project"))


def catalog():
    """Every transition, scene effect and in/out animation the user has applied in any project (= usable by name)."""
    seen = {}
    for p in list_projects():
        try:
            d = load_json(os.path.join(p["folder"], main_file(p["folder"])))
        except Exception:
            continue
        m = d.get("materials", {})
        effect_ids = {s.get("material_id") for t in d.get("tracks", []) if t.get("type") == "effect" for s in t["segments"]}
        for t in m.get("transitions", []):
            seen.setdefault(("transition", t.get("name")), p["name"])
        for e in m.get("video_effects", []):
            if e.get("id") in effect_ids and e.get("type") == "video_effect":
                seen.setdefault(("scene effect", e.get("name")), p["name"])
        for ma in m.get("material_animations", []):
            for a in ma.get("animations", []):
                kind = "%s anim %s" % ("text" if a.get("material_type") == "sticker" else "clip", a.get("type"))
                seen.setdefault((kind, a.get("name")), p["name"])
    return sorted((k, n, proj) for (k, n), proj in seen.items() if n)


def apply_resources(dr, s, c, donors, mtype="video"):
    """Clip fields: "transition": {"name", "dur"[, "from"]}, "anim_in" / "anim_out": {"name", "dur"[, "from"]}.
    mtype "sticker" = text clips (CapCut keeps text animations as sticker animations)."""
    for key, typ in (("anim_in", "in"), ("anim_out", "out")):
        r = c.get(key)
        if r:
            dr.animate(s, typ, donors.find("animation", r["name"], typ, r.get("from"), mtype), float(r["dur"]))
    r = c.get("transition")
    if r:
        dr.transition(s, donors.find("transition", r["name"], project=r.get("from")), float(r["dur"]))


def check_transitions(dr):
    idx = {m["id"]: m for m in dr.mats("transitions")}
    for t in dr.d["tracks"]:
        segs = t["segments"]
        for i, s in enumerate(segs):
            tr = [idx[r] for r in s.get("extra_material_refs", []) if r in idx]
            if not tr:
                continue
            a = s["target_timerange"]
            nxt = segs[i + 1]["target_timerange"] if i + 1 < len(segs) else None
            if not nxt or abs(nxt["start"] - (a["start"] + a["duration"])) > 1000:
                sys.exit("transition at %.3f s: no clip directly after it on the same track" % ((a["start"] + a["duration"]) / US))
            if tr[0]["duration"] > min(a["duration"], nxt["duration"]):
                sys.exit("transition at %.3f s is longer than a neighbouring clip" % ((a["start"] + a["duration"]) / US))


def apply_cuts(spec):
    """Ripple-delete spec["cuts"] ([[t0, t1], ...] in pre-cut timeline seconds) from every track: clips are split
    around each cut, later material moves left, keyframe lanes and zooms are re-based per piece, a clip's
    transition / anim_out / fade_out stay on its last piece and anim_in / fade_in on its first. Pieces of one clip
    meet with a hard cut. Text clips are not split: a text clip keeps its span minus the cut time (dropped if it
    lies inside a cut) - remove the discarded words before grouping captions. Returns a new spec."""
    cuts = sorted([float(a), float(b)] for a, b in spec.get("cuts", []) if float(b) > float(a))
    merged = []
    for a, b in cuts:
        if merged and a <= merged[-1][1]:
            merged[-1][1] = max(merged[-1][1], b)
        else:
            merged.append([a, b])
    if not merged:
        return spec

    def shift(t):
        """Pre-cut time -> post-cut time; a time inside a cut maps to the cut's start."""
        d = 0.0
        for a, b in merged:
            if t >= b:
                d += b - a
            elif t > a:
                return a - d
        return t - d

    def lerp(pts, t):
        pts = sorted((float(x), float(v)) for x, v in pts)
        if t <= pts[0][0]:
            return pts[0][1]
        for (x0, v0), (x1, v1) in zip(pts, pts[1:]):
            if t <= x1:
                return v0 + (v1 - v0) * (t - x0) / (x1 - x0) if x1 > x0 else v1
        return pts[-1][1]

    out = copy.deepcopy(spec)
    out.pop("cuts", None)
    probe_cache, report = {}, {"removed_s": round(sum(b - a for a, b in merged), 3), "split": 0, "dropped": 0}
    for tr in out.get("tracks", []):
        new_clips = []
        for c in tr.get("clips", []):
            at = float(c.get("at", 0))
            if tr["type"] == "text":
                dur = float(c["dur"]) if "dur" in c else float(c["end"]) - at
                a, b = shift(at), shift(at + dur)
                if b - a < 1 / 30:
                    report["dropped"] += 1
                    continue
                n = dict(c, at=round(a, 4), dur=round(b - a, 4))
                n.pop("end", None)
                new_clips.append(n)
                continue
            src_in = float(c.get("in", 0))
            if "dur" in c:
                dur = float(c["dur"])
            elif "out" in c:
                dur = float(c["out"]) - src_in
            elif "end" in c:
                dur = float(c["end"]) - at
            else:
                info = probe_cache.get(c["file"]) or probe(fwd(c["file"]))
                probe_cache[c["file"]] = info
                dur = 5.0 if info["kind"] == "photo" else info["duration_us"] / US - src_in
            end = at + dur
            pieces, p = [], at
            for a, b in merged:
                if b <= p or a >= end:
                    continue
                if a > p:
                    pieces.append((p, a))
                p = max(p, b)
            if p < end:
                pieces.append((p, end))
            pieces = [(a, b) for a, b in pieces if b - a >= 1 / 30]
            if not pieces:
                report["dropped"] += 1
                continue
            if len(pieces) == 1 and pieces[0] == (at, end):
                n = {key: v for key, v in c.items() if key not in ("out", "end")}   # "end" is pre-cut time
                n.update(at=round(shift(at), 4), dur=round(dur, 4))
                new_clips.append(n)
                continue
            report["split"] += 1
            z = c.get("zoom")
            if isinstance(z, str):
                amt, base = float(out.get("zoom_amount", 0.06)), float(c.get("scale", 1.0))
                z = {"in": {"from": base, "to": base + amt}, "out": {"from": base + amt, "to": base}}[z]
            for k, (a, b) in enumerate(pieces):
                n = {key: v for key, v in c.items() if key not in ("dur", "out", "end", "keyframes", "zoom")}
                n.update(at=round(shift(a), 4), dur=round(b - a, 4), **{"in": round(src_in + a - at, 4)})
                if k > 0:
                    for key in ("anim_in", "fade_in"):
                        n.pop(key, None)
                if k < len(pieces) - 1:
                    for key in ("anim_out", "fade_out", "transition"):
                        n.pop(key, None)
                if isinstance(z, dict):
                    f, t = float(z["from"]), float(z["to"])
                    n["zoom"] = {"from": f + (t - f) * (a - at) / dur, "to": f + (t - f) * (b - at) / dur}
                lanes = {}
                for prop, pts in (c.get("keyframes") or {}).items():
                    if not pts:
                        continue
                    r0, r1 = a - at, b - at
                    inner = [[round(float(x) - r0, 4), float(v)] for x, v in pts if r0 < float(x) < r1]
                    lanes[prop] = [[0.0, lerp(pts, r0)]] + inner + [[round(r1 - r0, 4), lerp(pts, r1)]]
                if lanes:
                    n["keyframes"] = lanes
                if "scale" in lanes:
                    n["scale"] = lanes["scale"][0][1]
                if "x" in lanes:
                    n["x"] = lanes["x"][0][1]
                if "y" in lanes:
                    n["y"] = lanes["y"][0][1]
                new_clips.append(n)
        tr["clips"] = new_clips
    print("cuts: %d ranges, %.3f s removed, %d clips split, %d dropped" % (len(merged), report["removed_s"],
          report["split"], report["dropped"]), file=sys.stderr)
    return out


def build(folder, spec, append=False, force=False, dry_run=False):
    if spec.get("cuts"):
        spec = apply_cuts(spec)
    dr = Draft(folder)
    if not append and spec.get("mode", "replace") == "replace":
        dr.clear()
    cv = spec.get("canvas")
    if cv:
        w, h = int(cv.get("width", 1920)), int(cv.get("height", 1080))
        dr.d["canvas_config"].update(width=w, height=h, ratio=cv.get("ratio", "original"))
        if cv.get("fps"):
            dr.d["fps"] = float(cv["fps"])
    styles = spec.get("text_styles", {})
    donors = Donors(spec.get("effects_from"))
    stats = {"clips": 0, "texts": 0, "effects": 0, "keyframed": 0, "transitions": 0, "animations": 0}
    for tr in spec.get("tracks", []):
        ttype = tr["type"]
        track = dr.track(ttype if ttype != "image" else "video", tr.get("name"), new=bool(tr.get("new", True)))
        if "hidden" in tr or "muted" in tr:                     # the track's eye / speaker switch in CapCut
            track["attribute"] = (1 if tr.get("muted") else 0) | (2 if tr.get("hidden") else 0)
        for c in tr.get("clips", []):
            at = float(c.get("at", 0))
            if ttype == "effect":
                mat, tpl = donors.find_effect(c["effect"], c.get("from"))
                dur = float(c["dur"]) if "dur" in c else float(c["end"]) - at
                dr.add_effect(mat, tpl, at, dur, track, c.get("params"))
                stats["effects"] += 1
                continue
            if ttype == "text":
                st = dict(styles.get(c.get("style", ""), {}))
                st.update({k: v for k, v in c.items()
                           if k not in ("text", "at", "dur", "end", "style", "keyframes", "anim_in", "anim_out")})
                dur = float(c["dur"]) if "dur" in c else float(c["end"]) - at
                s = dr.add_text(c["text"], at, dur, track=track, **st)
                apply_resources(dr, s, c, donors, mtype="sticker")
                stats["animations"] += sum(1 for k in ("anim_in", "anim_out") if c.get(k))
                stats["texts"] += 1
            else:
                src_in = float(c.get("in", 0))
                dur = float(c["dur"]) if "dur" in c else (float(c["out"]) - src_in if "out" in c else
                                                         (float(c["end"]) - at if "end" in c else None))
                fade = (float(c.get("fade_in", 0)), float(c.get("fade_out", 0))) if (c.get("fade_in") or c.get("fade_out")) else None
                s = dr.add_media(c["file"], at, src_in, dur, track=track, volume=float(c.get("volume", 1.0)),
                                 scale=float(c.get("scale", 1.0)), x=float(c.get("x", 0)), y=float(c.get("y", 0)),
                                 alpha=float(c.get("alpha", 1.0)), fade=fade)
                z = c.get("zoom")
                if z and s.get("clip"):
                    if isinstance(z, str):
                        amt = float(spec.get("zoom_amount", 0.06))
                        base = float(c.get("scale", 1.0))
                        z = {"in": (base, base + amt), "out": (base + amt, base)}[z]
                    elif isinstance(z, dict):
                        z = (float(z["from"]), float(z["to"]))
                    dr.zoom(s, z[0], z[1])
                    stats["keyframed"] += 1
                if s.get("clip"):
                    apply_resources(dr, s, c, donors)
                    stats["transitions"] += 1 if c.get("transition") else 0
                    stats["animations"] += sum(1 for k in ("anim_in", "anim_out") if c.get(k))
                stats["clips"] += 1
            for prop, pts in (c.get("keyframes") or {}).items():
                name = {"scale": "KFTypeScaleX", "x": "KFTypePositionX", "y": "KFTypePositionY", "rotation": "KFTypeRotation",
                        "alpha": "KFTypeAlpha", "volume": "KFTypeVolume"}.get(prop, prop)
                dr.keyframes(s, name, [(float(t), float(v)) for t, v in pts])
                stats["keyframed"] += 1
    check_transitions(dr)
    bk = dr.save(force=force, dry_run=dry_run)
    stats["duration_s"] = round(dr.d["duration"] / US, 3)
    stats["backup"] = bk
    return stats


# ---------------------------------------------------------------------------------------------- new
def new_project(name, like, width=None, height=None, fps=None):
    """New empty project, cloned from the JSON skeleton of an existing CapCut-made project (no media copied)."""
    src = project_dir(like)
    root = drafts_root()
    dest = os.path.join(root, name)
    if os.path.exists(dest):
        sys.exit("a project folder named %r already exists" % name)
    if capcut_running():
        sys.exit("Quit CapCut first.")
    mainf = main_file(src)
    d = load_json(os.path.join(src, mainf))
    saved_by = tuple(int(x) for x in ((d.get("last_modified_platform") or {}).get("app_version") or "0").split(".")[:3])
    inst = installed_version()
    if inst and saved_by[:2] != inst[:2]:
        print("warning: %r was last saved by CapCut %s, installed is %s. Its version markers may be stale "
              "(CapCut can refuse a draft as 'from an unusual path'). Prefer --like a project saved by the installed "
              "version - open and save any project once to refresh it." % (like, ".".join(map(str, saved_by)),
                                                                         ".".join(map(str, inst))), file=sys.stderr)
    draft_id, tl_id, proj_id = new_id(), new_id(), new_id()
    os.makedirs(dest)
    dr = Draft.__new__(Draft)
    dr.folder, dr.d, dr._probe_cache, dr.font = fwd(dest), d, {}, default_font()
    dr.clear()
    for k, v in d["materials"].items():
        if isinstance(v, list):
            d["materials"][k] = []
    d.update(id=tl_id, name="", duration=0, create_time=0, update_time=0)
    for k in ("time_marks",):
        if isinstance(d.get(k), dict):
            d[k] = None
    if width and height:
        d["canvas_config"].update(width=int(width), height=int(height), ratio="original")
    if fps:
        d["fps"] = float(fps)
    for f in (mainf, "template-2.tmp"):
        dump_json(d, os.path.join(dest, f))
    os.makedirs(os.path.join(dest, "Timelines", tl_id))
    for f in (mainf, "template-2.tmp"):
        dump_json(d, os.path.join(dest, "Timelines", tl_id, f))
    t = now_us()
    dump_json({"config": {"color_space": -1, "hdr_vivid": False, "mixed_track_mode_on": False, "render_index_track_mode_on": False,
                          "use_float_render": False}, "create_time": t, "id": proj_id, "main_timeline_id": tl_id,
               "timelines": [{"create_time": t, "id": tl_id, "is_marked_delete": False, "name": "Timeline 01", "update_time": t}],
               "update_time": t, "version": 0}, os.path.join(dest, "Timelines", "project.json"))
    m = load_json(os.path.join(src, "draft_meta_info.json"))
    for g in m.get("draft_materials", []):
        g["value"] = []
    m.update(draft_id=draft_id, draft_name=name, draft_fold_path=fwd(dest), draft_root_path=fwd(root),
             draft_cover="", tm_draft_create=t, tm_draft_modified=t, tm_duration=0, draft_timeline_materials_size=0)
    dump_json(m, os.path.join(dest, "draft_meta_info.json"))
    # fresh editor-state files - the donor's copies name the donor's timeline id and media-bin items
    dump_json({"dockItems": [{"dockIndex": 0, "ratio": 1, "timelineIds": [tl_id], "timelineNames": ["Timeline 01"]}],
               "layoutOrientation": 1}, os.path.join(dest, "timeline_layout.json"))
    dump_json({"timeline_settings": {tl_id: {"linkage_enabled": False}}, "track_settings": {}},
              os.path.join(dest, "draft_biz_config.json"))
    dump_json(virtual_store_skeleton(), os.path.join(dest, "draft_virtual_store.json"))
    with open(os.path.join(dest, "draft_settings"), "w", encoding="utf-8") as f:
        f.write("[General]\ndraft_create_time=%d\ndraft_last_edit_time=%d\nreal_edit_seconds=0\nreal_edit_keys=0\n"
                "cloud_last_modify_platform=%s\n" % (t // US, t // US, "windows" if sys.platform == "win32" else "mac"))
    rp = os.path.join(root, "root_meta_info.json")
    r = load_json(rp)
    shutil.copy2(rp, rp + ".capcut-timeline.bak")
    tmpl = next((e for e in r.get("all_draft_store", []) if fwd(e.get("draft_fold_path", "")).lower() == fwd(src).lower()), None)
    e = copy.deepcopy(tmpl) if tmpl else {}
    e.update(draft_cover="", draft_fold_path=fwd(dest), draft_id=draft_id, draft_json_file=fwd(os.path.join(dest, mainf)),
             draft_name=name, draft_root_path=fwd(root), draft_timeline_materials_size=0, tm_draft_create=t,
             tm_draft_modified=t, tm_duration=0)
    r.setdefault("all_draft_store", []).insert(0, e)
    if isinstance(r.get("draft_ids"), int):
        r["draft_ids"] += 1
    dump_json(r, rp)
    return fwd(dest)


# ------------------------------------------------------------------------------------------- inspect
def summarize(folder):
    dr = Draft(folder)
    idx = dr.index()
    out = {"folder": dr.folder, "duration_s": dr.d["duration"] / US, "fps": dr.d.get("fps"),
           "canvas": {k: dr.d["canvas_config"].get(k) for k in ("width", "height", "ratio")},
           "app_version": (dr.d.get("last_modified_platform") or {}).get("app_version"), "tracks": []}
    for t in dr.d["tracks"]:
        tr = {"type": t["type"], "name": t.get("name", ""), "clips": []}
        for s in t["segments"]:
            k, m = idx.get(s["material_id"], (None, {}))
            tt, st = s["target_timerange"], s.get("source_timerange") or {}
            c = {"at": round(tt["start"] / US, 3), "dur": round(tt["duration"] / US, 3), "kind": m.get("type")}
            if st:
                c["in"] = round(st["start"] / US, 3)
            if m.get("path"):
                c["file"] = m["path"]
            if k == "video_effects":
                c["effect"] = m.get("name")
            if k == "texts":
                try:
                    c["text"] = json.loads(m["content"])["text"]
                except Exception:
                    c["text"] = m.get("content", "")[:80]
            if s.get("clip"):
                cl = s["clip"]
                c.update(scale=round(cl["scale"]["x"], 4), x=round(cl["transform"]["x"], 4), y=round(cl["transform"]["y"], 4))
            if s.get("volume", 1.0) != 1.0:
                c["volume"] = round(s["volume"], 3)
            if s.get("speed", 1.0) != 1.0:
                c["speed"] = s["speed"]
            kfs = {k2["property_type"]: [(round(x["time_offset"] / US, 3), round(x["values"][0], 4) if x["values"] else None)
                                         for x in k2["keyframe_list"]] for k2 in s.get("common_keyframes", [])}
            if kfs:
                c["keyframes"] = kfs
            refs = [idx[r][0] for r in s.get("extra_material_refs", []) if r in idx]
            extra = [r for r in refs if r in ("transitions", "audio_fades", "effects", "video_effects", "filters", "material_animations")]
            if extra:
                c["extras"] = extra
            for r in s.get("extra_material_refs", []):
                k2, m2 = idx.get(r, (None, {}))
                if k2 == "transitions":
                    c["transition"] = {"name": m2.get("name"), "dur": round(m2.get("duration", 0) / US, 3)}
                elif k2 == "material_animations" and m2.get("animations"):
                    c["anims"] = [{"name": a.get("name"), "type": a.get("type"), "dur": round(a.get("duration", 0) / US, 3)}
                                  for a in m2["animations"]]
            tr["clips"].append(c)
        out["tracks"].append(tr)
    return out


def print_summary(s):
    print("%s\n  %.2f s  %s fps  canvas %s  saved by CapCut %s" % (s["folder"], s["duration_s"], s["fps"], s["canvas"], s["app_version"]))
    for i, t in enumerate(s["tracks"]):
        print("  [%d] %s track %s - %d clips" % (i, t["type"], repr(t["name"]) if t["name"] else "", len(t["clips"])))
        for c in t["clips"][:400]:
            what = c.get("text") or c.get("effect") or os.path.basename(c.get("file", "")) or c.get("kind")
            extra = ""
            if "in" in c and c["in"]:
                extra += " in %.3f" % c["in"]
            if c.get("keyframes"):
                extra += " kf:" + ",".join(k.replace("KFType", "") for k in c["keyframes"])
            if c.get("volume") is not None:
                extra += " vol %.2f" % c["volume"]
            for a in c.get("anims", []):
                extra += " %s:%s %.2f" % (a["type"], a["name"], a["dur"])
            if c.get("transition"):
                extra += " ->[%s %.2f]" % (c["transition"]["name"], c["transition"]["dur"])
            print("      %8.3f +%7.3f  %-44s%s" % (c["at"], c["dur"], str(what).replace("\n", " ")[:44], extra))


# ----------------------------------------------------------------------------------------------- cli
def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    sub.add_parser("list")
    sub.add_parser("catalog")
    p = sub.add_parser("inspect"); p.add_argument("project"); p.add_argument("--json", action="store_true")
    p = sub.add_parser("build"); p.add_argument("project"); p.add_argument("spec")
    p.add_argument("--append", action="store_true"); p.add_argument("--force", action="store_true"); p.add_argument("--dry-run", action="store_true")
    p = sub.add_parser("new"); p.add_argument("name"); p.add_argument("--like", required=True)
    p.add_argument("--width", type=int); p.add_argument("--height", type=int); p.add_argument("--fps", type=float)
    p = sub.add_parser("backup"); p.add_argument("project")
    p = sub.add_parser("restore"); p.add_argument("project"); p.add_argument("src", nargs="?")
    a = ap.parse_args()

    if a.cmd == "doctor":
        print("drafts folder :", drafts_root(), "(exists)" if os.path.isdir(drafts_root()) else "(MISSING)")
        print("CapCut app    :", app_dir() or "?")
        if installed_version() >= (10,):
            print("WARNING       : CapCut 10.x reportedly rejects tool-written drafts as corrupted - test on a copy first")
        print("CapCut running:", capcut_running())
        print("default font  :", default_font() or "(none found)")
        print("backups       :", backup_root())
        print("ffprobe       :", shutil.which("ffprobe") or "MISSING")
        print("projects      : %d" % len(list_projects()))
    elif a.cmd == "list":
        for p in list_projects():
            print("%s  %8.1f s  %-40s %s%s" % (dt.datetime.fromtimestamp(p["modified_us"] / US).strftime("%Y-%m-%d %H:%M"),
                                              p["duration_us"] / US, p["name"], p["folder"], "  (not in CapCut's list)" if p.get("unregistered") else ""))
    elif a.cmd == "catalog":
        for kind, name, proj in catalog():
            print("%-18s %-34s <- %s" % (kind, name, proj))
    elif a.cmd == "inspect":
        s = summarize(project_dir(a.project))
        print(json.dumps(s, indent=1, ensure_ascii=False)) if a.json else print_summary(s)
    elif a.cmd == "build":
        spec = load_json(a.spec)
        st = build(project_dir(a.project), spec, append=a.append, force=a.force, dry_run=a.dry_run)
        print(json.dumps(st, indent=1))
    elif a.cmd == "new":
        print("created", new_project(a.name, a.like, a.width, a.height, a.fps))
    elif a.cmd == "backup":
        print("backup:", backup(project_dir(a.project)))
    elif a.cmd == "restore":
        print("restored from", restore(project_dir(a.project), a.src))


if __name__ == "__main__":
    main()
