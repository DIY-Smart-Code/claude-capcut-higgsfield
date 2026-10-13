# capcut.py edit spec and CapCut troubleshooting

Reference for `scripts/capcut.py`. `make_spec.py` writes this format for you; edit it by hand for anything custom.

## Edit spec

Times in **seconds**. `at` = position on the timeline; `in` = source in-point; `dur` (or `out` = source
out-point, or `end` = timeline end). Stills default to 5 s, video/audio to the rest of the file.

```json
{
  "mode": "replace",
  "canvas": {"width": 1920, "height": 1080, "fps": 30},
  "zoom_amount": 0.06,
  "text_styles": {
    "title":   {"size": 12, "bold": true, "color": "#FFFFFF", "stroke": "#000000", "y": 0.55},
    "caption": {"size": 7, "color": "#FFFFFF", "background": "#000000", "background_alpha": 0.6,
                "y": -0.78, "max_width": 0.8}
  },
  "tracks": [
    {"type": "video", "name": "main", "clips": [
      {"file": "C:/videos/moth/media/001.png", "at": 0.0, "dur": 4.2, "zoom": "in"},
      {"file": "C:/videos/raw/take2.mov", "at": 4.2, "in": 12.5, "dur": 6.0, "volume": 1.0},
      {"file": "C:/videos/moth/media/002.png", "at": 10.2, "dur": 3.1, "zoom": {"from": 1.08, "to": 1.0}}
    ]},
    {"type": "video", "name": "overlay", "clips": [
      {"file": "C:/videos/gfx/overlay_alpha.mov", "at": 0.0}
    ]},
    {"type": "video", "name": "pip", "clips": [
      {"file": "C:/videos/raw/cam.mp4", "at": 20, "in": 20, "dur": 8, "scale": 0.3, "x": 0.65, "y": -0.6, "volume": 0}
    ]},
    {"type": "audio", "name": "voiceover", "clips": [{"file": "C:/videos/moth/media/vo.wav", "at": 0}]},
    {"type": "audio", "name": "music", "clips": [
      {"file": "C:/videos/music/bed.mp3", "at": 0, "dur": 180, "volume": 0.25, "fade_in": 1.5, "fade_out": 3}
    ]},
    {"type": "audio", "name": "sfx", "clips": [{"file": "C:/videos/sfx/whoosh.wav", "at": 10.1, "volume": 0.6}]},
    {"type": "text", "name": "titles", "clips": [
      {"text": "The First Computer Bug", "at": 0.5, "dur": 3.5, "style": "title"}
    ]},
    {"type": "text", "name": "captions", "clips": [
      {"text": "This moth is the most famous bug", "at": 0.0, "dur": 2.4, "style": "caption"}
    ]}
  ]
}
```

| Clip field | Meaning |
|---|---|
| `file` | absolute path; kind from the extension (image → still, audio ext → audio, else video) |
| `at`, `in`, `dur` / `out` / `end` | timeline position, source in-point, length (seconds) |
| `volume` | 0 mutes (use for b-roll/PiP with sound you don't want); linear gain |
| `scale`, `x`, `y`, `alpha` | placement. `x`/`y` −1…1 from the canvas centre, `y` up |
| `zoom` | `"in"`, `"out"` (± `zoom_amount`) or `{"from": a, "to": b}` — smooth scale over the clip |
| `keyframes` | any lane by hand: `{"scale": [[0, 1.0], [2.5, 1.2]], "x": [...], "alpha": [...], "volume": [...]}` (seconds from clip start) |
| `fade_in`, `fade_out` | audio fades (seconds) |
| `transition` | video: `{"name": "Left", "dur": 1.0}` — CapCut transition at the END of this clip into the next one on the same track (they must touch) |
| `anim_in`, `anim_out` | video: `{"name": "Fade In", "dur": 0.5}` — CapCut in/out animation |
| text: `text`, `style`, `size`, `color`, `bold`, `italic`, `align` (0 left, 1 centre, 2 right), `x`, `y`, `scale`, `max_width` (wrap width, share of frame), `stroke`, `stroke_width`, `shadow`, `background`, `background_alpha` | |

**Ripple cuts** (retakes, false starts): spec-level `"cuts": [[t0, t1], ...]` in pre-cut timeline seconds.
`build` removes each range from every track and closes the gap: clips split (hard cut), in-points, keyframes and
zooms re-based, a clip's transition/anim_out stay on its last piece. Text clips shrink or drop instead of
splitting, so drop the discarded words before grouping captions. Snap t0/t1 into silence (≥ 0.06 s from words)
and keep cuts ≥ 0.5 s from transitions.

Track rules: clips on one track must not overlap (put them on another track). Track `"hidden": true` / `"muted": true` set its eye / speaker switch. Video tracks stack in spec
order — later tracks draw on top. Keep the first video track gapless (CapCut's main-track magnet closes gaps
once the user edits); put gapped clips on an overlay track. One track per role (main, overlay, pip,
voiceover, music, sfx, titles, captions) keeps it readable for the user. Times snap to whole frames.

Transitions and video in/out animations need CapCut's own resource objects: the build copies them by name
from a **donor project** where the user applied them — spec-level `"effects_from": "<project>"`, or `"from"`
inside the field; without either, every project is searched (slow). Missing effect files are fetched by CapCut
by resource id when the user opens the project (verified 2026-10-11: Fade In/Out cache folders appeared after
opening a test project, transitions kept on CapCut's re-save).
Not built in: filters, effects, stickers, text animations — leave them to the user, or copy the exact object
from a project where the user applied it (`references/draft-format.md`).

## When something looks wrong in CapCut

- Project missing from the list → it was created while CapCut was open, or the registry entry is missing:
  quit CapCut, run `capcut.py list` (unregistered projects are flagged), recreate with `new`.
- Edit gone after opening → CapCut was open during the build and saved over it. Quit, rebuild.
- "Media offline" → a `file` path moved; rebuild with the right path.
- "Link media — Couldn't find some of the imported media files" on opening → the **media bin** (not the
  timeline) lists files that were moved or deleted, often left over from the user's own earlier edit. `build`
  now drops bin entries whose file is gone (printed to stderr). If the file was only moved, relink instead: replace the old
  path in `draft_meta_info.json`, `draft_agency_config.json` and `subdraft/*/draft_content.json` (compound clips).
- Anything else → `capcut.py restore <project>` and report; compare the project with a CapCut-saved one
  (`inspect --json`) before changing templates.
