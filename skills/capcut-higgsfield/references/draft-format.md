# CapCut desktop draft format — what the tool relies on

Verified on CapCut **9.5.0** (Windows, 2026-10-10) against 136 local projects saved by CapCut 5.4 – 9.5.
All of them are **plain JSON** (`"version": 360000`, `"new_version"` 128.0.0 – 187.0.0). (JianYing — the
Chinese edition — encrypts drafts from 6.x on; CapCut international did not as of 9.5. If a future CapCut
starts encrypting, `json.load` fails on `draft_content.json` — stop and tell the user.)

## Where projects live

| OS | Drafts folder |
|---|---|
| Windows | `%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft\` |
| macOS | `~/Movies/CapCut/User Data/Projects/com.lveditor.draft/` |

Override with `CAPCUT_DRAFTS`. App versions: Windows `%LOCALAPPDATA%\CapCut\Apps\<version>\` (several kept).

```
com.lveditor.draft/
  root_meta_info.json            ← CapCut's project list (all_draft_store[]: name, folder, json path, times)
  <Project>/
    draft_content.json           ← THE timeline (tracks, segments, materials, keyframes)
    template-2.tmp               ← byte-identical copy written on every save
    Timelines/project.json       ← {"main_timeline_id": <id>, "timelines": [...]}  (multi-timeline, CapCut 9.x)
    Timelines/<main_timeline_id>/draft_content.json (+ template-2.tmp)   ← byte-identical copy too
    draft_meta_info.json         ← project card: name, id, times, tm_duration, media bin (draft_materials)
    draft_cover.jpg, draft_settings, draft_virtual_store.json, key_value.json, crypto_key_store.dat, …
    subdraft/<id>/draft_content.json   ← compound clips
    Resources/, matting/, smart_crop/, … ← caches CapCut computes
```

`matting/<hash>/2/mask/<time_us>` holds the Remove-background result as raw 8-bit low-res masks (114688
bytes = 448×256 per frame) plus `maskinfo/`, `mocf` (JSON frame list) and `matting_result.json`; the video
material's `matting` object (`flag`, `path`, `strokes` = the outline stroke, e.g. "Luminescence") points at
it. Whether CapCut recomputes a missing cache for a generated draft is unverified — render cut-outs offline
instead (`workflows.md` §4).

**Alpha media is read as premultiplied.** CapCut 9.5 composites ProRes 4444 alpha as `rgb + bg·(1−a)`. A
straight-alpha file (full colour under low alpha, e.g. a soft glow) shows as a solid bright halo. Encode alpha
media premultiplied (`-vf format=gbrap,premultiply=inplace=1`). To swap files in an existing project, replace the
path and basename in every timeline copy, `draft_meta_info.json`, `draft_agency_info.json` and the
`Timelines/*/attachment/patch/mini_draft.json`. The proxy/converter (`draft_agency_config.json`
`use_converter`) keeps the alpha as it is (qtrle argb), so it neither causes nor fixes this.

**Write all four timeline copies identically** (root `draft_content.json`, root `template-2.tmp`,
`Timelines/<main>/draft_content.json` and its `template-2.tmp`). CapCut 9.5 keeps them byte-identical (md5
checked on 4 projects). Which one wins has changed between versions: 8.7 Windows ignored a root-only edit
because `template-2.tmp` won; 9.2.8 macOS reads only `Timelines/<main_timeline_id>/` (capcut-cli issues
#35, #50). Writing all four covers every case.

Three different ids: `draft_meta_info.draft_id` (= the `root_meta_info` entry's `draft_id`), the project id
in `Timelines/project.json`, and the **timeline id** = `draft_content.json["id"]` = the `Timelines/`
subfolder name = `main_timeline_id` (also named in `timeline_layout.json` and `draft_biz_config.json`).

macOS CapCut (and JianYing) call the timeline file **`draft_info.json`**; `capcut.py` uses whichever exists.

`.locked` exists in a project folder while CapCut has it open - never write then.

`draft_meta_info.json` `tm_duration` / `tm_draft_modified` (µs) and the matching `root_meta_info.json` entry
drive the project card (length, sort order). `draft_fold_path` inside `draft_meta_info.json` may be stale
(CapCut tolerates it — a renamed folder keeps its old value).

**Media bin.** Every local file on the timeline should have an entry in
`draft_meta_info.json → draft_materials[type 0]` (`file_Path`, `metetype` video|photo|music, `duration`,
`width`, `height`, lower-case uuid `id`) **and** be listed in `draft_virtual_store.json →
draft_virtual_store[type 1]` as `{"child_id": <bin id>, "parent_id": ""}` (that list is what the media
panel shows; `parent_id` = a bin folder). Set the timeline material's `local_material_id` to the bin entry
id — CapCut 9.1+ builds showed clips as inaccessible / asked to relink without it (capcut-cli, pyCapCut #13).
`capcut.py` does all three on every save.

**Version markers.** Keep `version`, `new_version`, `platform`, `last_modified_platform`, `color_space` and
the render-mode flags exactly as the installed CapCut wrote them. Stale markers (e.g. from an old template)
make CapCut 8.4+/9.3 refuse the draft ("Current project is from an unusual path") or show 00:00 in the list.
That is why `capcut.py new` clones a project the user's CapCut saved, and warns if it was saved by another
major.minor version.

**New project registration.** Adding an entry to `root_meta_info.json → all_draft_store` (copied from an
existing entry, new `draft_id` / `draft_name` / `draft_fold_path` / `draft_json_file` / times) makes it show in
the project list; some tools instead rely on CapCut rescanning the folder on the home screen. Only edit the
registry with CapCut closed.

## Units and ids

- Time: **microseconds** (int). 30 fps frame = 33 333.33 µs; CapCut rounds per segment (durations like
  `366667`).
- Ids: UUIDs, CapCut style upper-case with a lower-case third group (`CBA9C120-9346-4cfb-96DC-6C50B09F8501`).
  Media-bin item ids and `music_id` are lower-case UUIDs.
- Paths: absolute with forward slashes. CapCut-internal files use `##_draftpath_placeholder_<uuid>_##/…`.

## Timeline objects

```
tracks[]          {id, type: video|audio|text|effect|sticker, flag, attribute, name, is_default_name, segments[]}
  segments[]      {id, material_id, extra_material_refs[], source_timerange{start,duration} | null (text),
                   target_timerange{start,duration}, clip{scale{x,y}, transform{x,y}, rotation, alpha, flip} | null (audio),
                   uniform_scale, volume, speed, common_keyframes[], render_index, track_render_index, visible, …}
materials{}       videos[] (video + photo), audios[], texts[], plus per-segment helpers:
                  speeds, placeholder_infos, canvases (canvas_color), material_animations (sticker_animation),
                  sound_channel_mappings, material_colors, vocal_separations, beats (audio), audio_fades (audio)
```

- Each segment has **its own material** (CapCut creates one `videos` entry per segment even for the same
  file) and its own helper materials, linked through `extra_material_refs`. The tool copies the exact helper
  set CapCut writes for each kind (`templates.json`).
- `source_timerange` = slice of the file; `target_timerange` = position on the timeline. Equal durations at
  speed 1.
- Stills: material `type: "photo"`, `duration: 10800000000` (3 h), source starts at 0.
- Local audio files: material `type: "extract_music"` (CapCut-library music is `music`, SFX `sound`,
  detached video audio `video_original_sound`).
- Video tracks: first `flag 0`, overlay tracks `flag 2`; later tracks draw on top. Text tracks `flag 1`.
  `render_index`: main video 0, overlays 1, 2, …; text 14000+; effects 11000+. `track_render_index`: layer
  order.
- Canvas: `canvas_config {width, height, ratio}`; `fps` top level. `duration` = end of the last segment.
- `clip.transform` x/y are in **half-canvas units** from the centre (−1…1 = edge to edge), **y positive =
  up** (app-made subtitles sit at y ≈ −0.73; a PiP at scale 0.4229 and x 0.5773 touches the right edge
  exactly). `clip.scale` 1 = the media fitted to the canvas. `rotation` in degrees clockwise, `alpha` 0–1.
- Track `attribute` bits: 1 = muted, 2 = hidden (eye off; hidden text is not rendered) (verified on the user's projects 2026-10-11). `config.maintrack_adsorb: true` (main-track magnet) can close gaps on
  track 0 once the user edits — keep the main track gapless, put gapped clips on overlay tracks.
- All times are frame-aligned in CapCut's own drafts (`round(frame * 1e6 / fps)`); `capcut.py` snaps every
  start and end to the frame grid so no sub-frame gaps appear between clips.

## Keyframes

```json
{"id": "...", "property_type": "KFTypeScaleX", "material_id": "",
 "keyframe_list": [{"id": "...", "time_offset": 23100000, "values": [1.0], "curveType": "Line",
                    "graphID": "", "left_control": {"x": 0, "y": 0}, "right_control": {"x": 0, "y": 0},
                    "string_value": ""}]}
```

- On the segment in `common_keyframes[]`.
- **`time_offset` is in the clip's SOURCE time** (µs): a segment cut from 127.4 s of its file has keyframes
  starting at 127 400 000 even if it sits at 365 s on the timeline. For stills (source starts at 0) it is
  simply the offset from the clip start. Verified on 803 keyframe lanes in 136 real projects (CapCut 5.7 –
  9.5, incl. 9.5) where the two readings differ: 803 source-time, 0 segment-relative. **pyJianYingDraft and
  most generators document "offset from the segment start"** — that is only equal when the clip starts at 0
  in its file; for trimmed footage it puts keyframes in the wrong place. `capcut.py keyframes()` adds the
  source in-point for you.
- Easing set in the UI writes `curveType: "FreeCurveInOut"` with control handles; `Line` is linear.
- Keyframes override the static `clip` values. `KFTypeAlpha` reportedly shows in preview but not in the
  export on some builds (capcut-cli) — prefer fades/animations for visibility changes.
- With uniform scale on, CapCut stores scale as `KFTypeScaleX` only. When you add a keyframe in the UI it
  writes ScaleX + PositionX + PositionY + Rotation together; the tool does the same for zooms.
- Other lanes seen in real drafts: `KFTypeAlpha`, `KFTypeVolume`, `KFTypeScaleY` (non-uniform),
  colour lanes (`KFTypeBrightness`, `KFTypeSaturation`, …), mask lanes (`KFTypeCommonMask*`).

## Text

`materials.texts[]` entry; the visible text and its styling are a JSON **string** in `content`:

```json
{"text": "The Great Emu War",
 "styles": [{"fill": {"content": {"render_type": "solid", "solid": {"color": [1, 1, 1]}}},
             "font": {"path": "<CapCut app>/Resources/Font/SystemFont/en.ttf", "id": ""},
             "size": 12, "bold": true,
             "strokes": [{"alpha": 1, "content": {"render_type": "solid", "solid": {"alpha": 1, "color": [0, 0, 0]}}, "width": 0.06}],
             "shadows": [{"alpha": 0.35, "angle": -45, "distance": 3, "diffuse": 0.005, "content": {"render_type": "solid", "solid": {"color": [0, 0, 0]}}}],
             "range": [0, 17]}]}
```

- `range` counts UTF-16 code units (measured by capcut-cli on 211 app-written texts; Python `len()` is wrong
  for emoji). Several styles with different ranges = mixed styling in one text.
- Material `check_flag`: 7, +8 with a stroke, +16 with a background box, +32 with a shadow.
- Mirror the main values on the material: `font_path`, `font_size`, `text_color`, `alignment` (0 left,
  1 centre, 2 right), `line_max_width` (wrap width as a share of the canvas — keeps text inside the frame),
  `border_color`/`border_width` for a stroke, `has_shadow`, and for a box behind the text
  `background_style 1`, `background_color`, `background_alpha`.
- Font paths point into the installed app version folder; the tool uses the newest installed version's
  `en.ttf`. Text templates / effect styles from CapCut's online library reference cache files — not used.

## Not supported by the tool (yet)

Transitions (`materials.transitions`, linked from the **earlier** segment), filters (`materials.effects`,
`type: "filter"`) and scene effects (`materials.video_effects`) need CapCut-international `effect_id` /
`resource_id` values (JianYing ids do nothing) and CapCut downloads the resources when the project opens.
To add one, copy the exact object from a project where the user applied it in CapCut, with fresh ids.

## Version notes

- CapCut international desktop: plain JSON from 6.x to 9.5 (all 136 local drafts). JianYing: AES-encrypted
  since 6.0.
- **CapCut 10.x reportedly rejects tool-written drafts as corrupted** (capcut-cli refuses to write to 10.x
  without `--force-write`). `capcut.py doctor` warns. After a CapCut update, rebuild the test project and open
  it before trusting the tool again.
- Materials key for masks: `common_mask` (CapCut) vs `masks` (JianYing).

## Gotchas

- **CapCut open = edits lost.** It holds the project in memory and saves over the files on close. Quit it
  before writing; the tool refuses while `CapCut.exe` runs.
- Older-version objects are accepted: CapCut upgrades a draft saved by 5.x/8.x when it opens it. The
  templates mix 9.5 (video) and 8.x (photo, audio, text) objects plus the two fields 9.5 added to every
  segment (`hdr_vivid_settings`, `segment_color_tag`).
- Same file several times: one material per segment is normal; don't share material ids between segments.
- Media is referenced, not copied. Moving a file later shows "media offline" in CapCut.
- Overlapping segments on one track are invalid — use another track.
- `draft_content.json.bak` is CapCut's own backup; the tool keeps separate backups (`~/.capcut-timeline/backups`).
- Copying a donor project: its `timeline_layout.json`, `draft_biz_config.json` and `draft_virtual_store.json`
  name the donor's timeline and media ids — `capcut.py new` writes fresh ones; never copy them verbatim.

## Sources

- Local evidence: the user's CapCut 9.5 install and 136 drafts (read-only survey, 2026-10-10).
- pyJianYingDraft — github.com/GuanYixuan/pyJianYingDraft (segment, keyframe, text, local materials, templates)
- pyCapCut — github.com/GuanYixuan/pyCapCut (issue #13: draft_materials)
- VectCutAPI (formerly CapCutAPI) — github.com/sun-guannan/VectCutAPI (draft profiles, root_meta_info entry)
- capcut-cli — github.com/renezander030/capcut-cli (docs/version-support.md, draft-schema/*, issues #35 #50 #67 #85 #111)
- capcut-mcp — github.com/JmsLdrn/capcut-mcp (running/.locked guard, validator)
- capcut-shell-inject — github.com/zxypro1/capcut-shell-inject (empty-shell injection verified on 9.3)
- Matt Loui, "Claude Edited My Entire CapCut Video" — youtube.com/watch?v=5N1moUCsVhI (workflow, prompts)
