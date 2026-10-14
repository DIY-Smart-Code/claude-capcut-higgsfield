---
name: capcut-higgsfield
description: "Make a faceless video with the Higgsfield MCP and hand it over as an editable CapCut project. Claude writes a sourced script, picks a Higgsfield explainer style, generates the voice-over, every shot (GPT Image) and key motion clips (Seedance) through the Higgsfield MCP, times each shot to the real voice-over, scores the hook with the Higgsfield Virality Predictor, then writes a real CapCut timeline (shots, zooms, voice-over, captions, title) the user can keep editing by hand. Use when the user wants a faceless / explainer / storytelling video, a video for a faceless channel, Higgsfield images or clips assembled in CapCut, or 'make a video in CapCut with Higgsfield'. Also edits existing CapCut projects from files (cuts, overlays, captions, music)."
---

# CapCut + Higgsfield: faceless videos you can still edit

Higgsfield MCP does the generating (voice, shots, motion, hook score). `scripts/capcut.py` writes the result
into CapCut's own project files, so the user opens a normal CapCut project, not a flattened MP4, and can move
any cut, swap any shot or restyle any caption by hand.

**Needs:** the Higgsfield MCP connected (`https://mcp.higgsfield.ai/mcp`, no API key), CapCut desktop
(tested with 9.5 on Windows), Python 3.10+ with `faster-whisper` (`pip install faster-whisper`), ffmpeg/ffprobe
on PATH. Run the scripts with `python` (not `py`, whose shebang lookup may pick another interpreter).

**Hard rules**
- **CapCut must be closed** while you write a project. It keeps the open project in memory and overwrites
  the files when it closes. `capcut.py` refuses to save while `CapCut.exe` runs. Ask the user to quit it;
  never kill it yourself. Never drive the CapCut UI. Files only.
- **No invented facts.** Every sentence of the script traces to a source you read in this session; list the
  sources in `shots.json`. If you can't source it, cut it or say it as an opinion.
- **Show the cost before spending.** Preflight with `get_cost: true` and tell the user the total (shots ×
  image cost + clips × video cost + voice). Ask before anything over their stated budget.
- **A timeout is not a failure.** If a `generate_*` call times out or returns a gateway error, check
  `show_generations` for the job before resubmitting; the job may exist and be charged already.
- **Keep every take.** `hf_fetch.py` moves a replaced file into `media/rejected/` and logs it, so the ledger
  shows real retries and the real credit total.

## Pipeline

Work folder: one folder per video, e.g. `~/Videos/<slug>/`. Everything below writes into it.

### 1. Brief and sources
Topic, target length (≈150 spoken words per minute), format (16:9, 9:16 or both), voice gender/tone, budget.
Research the topic and keep the source URLs. Prefer primary sources (archives, official docs, papers).

### 2. Script and shot list → `shots.json`
One shot per spoken line, one visual idea per shot, 3–8 s each.
```json
{"title": "The First Computer Bug", "sources": ["https://..."],
 "shots": [{"id": 1, "line": "This moth is the most famous bug in computer history.",
            "prompt": "Extreme close-up of a small grey moth caught between two brass relay contacts", "motion": true},
           {"id": 2, "line": "...", "prompt": "...", "motion": false}]}
```
- **Write for TTS:** numbers and years as words ("nineteen forty-seven"), no symbols, no em dashes, model
  names spelled the way they are said ("Mark Two").
- **Hook first:** line 1 is the most surprising true thing in the story, shown on the strongest image. Not a
  date, not "In this video". Line 2 opens a question the rest answers.
- `prompt` describes the picture only: subject, framing, light. No style words (step 3 adds them) and no
  readable text (image models misspell; use "illegible handwriting" when paper must show writing).
- Mark 1–4 shots `"motion": true`: the hook shot and the story's turning points. Motion costs ~50× a still.
- A shot can reuse another shot's files: `"media": "005"`.
Show the script to the user and get a yes before spending credits.

### 3. Style lock
1. `get_explainer_presets` → show 3–4 fitting presets (name + preview) and recommend one.
2. `resolve_explainer_preset(preset_id)` → `media_id` (the preset's style image).
3. Generate **one style frame** (a representative shot) with that `media_id` as `image_references`, and
   **name the style in the prompt**. The preset image alone is often only a poster frame and the model drifts
   to photoreal; the words carry the style. Prefix every shot prompt with the same sentence, e.g.
   `Match the art style of the reference images exactly: loose watercolor illustration, visible paper
   texture, soft ink outlines, muted sepia and grey washes. No text, no letters, no logos. Scene: ...`
4. User approves the frame → its **job_id** becomes the second style reference for every shot
   (`medias: [{preset media_id}, {style frame job_id}]`, role `image_references`).

### 4. Voice-over (Higgsfield)
`list_voices` → offer 3 voices with `preview_url`, user picks. Then one call for the whole script:
`generate_audio` with `model: seed_audio`, `voice_type: preset`, `voice_id`, `format: wav`,
`sample_rate: 44100`, prompt = all `line`s joined with spaces. Fetch it as `vo` (step 6 command).

### 5. Time the shots from the real audio
`python scripts/shotlist.py WORK media/vo.wav` → `words.json` + `start`/`end`/`dur` on every shot.
Every line should say matched; fix the script/VO mismatch if not. Merge shots shorter than ~1 s.
Seedance clips are 4–30 s at 7 credits/s (720p, no audio), so size each motion clip to its shot (`dur`).

### 6. Generate the shots
- `generate_image_batch`, model `gpt_image_2_5`, `aspect_ratio: "16:9"` (or `"9:16"`), `quality: "medium"`.
  **At most 6 per batch**: bigger batches hit `429 rate_limit_reached`; resubmit only the failed indices.
- `jobs_wait` (≤ 12 ids, 15 s) until done, then fetch each result into the work folder:
  ```
  python scripts/hf_fetch.py WORK 003 <result_url> --kind image --job <job_id> --model gpt_image_2_5 --credits 0.5 --prompt "<prompt>"
  ```
- Make a contact sheet and look at it. Regenerate any shot that breaks the style, shows garbled text or
  contradicts the line; fetch the new take under the same name (the old one moves to `media/rejected/`).
- **Motion shots:** `generate_video`, model `seedance_2_5`, `mode: omni_reference`,
  `medias: [{value: <the shot's image job_id>, role: start_image}]`, `duration` ≥ the shot (min 4),
  `resolution: 720p`, `generate_audio: false` (cheaper; the voice-over is the only sound), prompt =
  "Keep the illustration style and composition of the start image. <one small motion>, slow camera push."
  Fetch as `<id>.mp4` with `--kind video`. A clip shorter than its shot is followed by its own still.
- `python scripts/hf_fetch.py WORK --summary` → files, throwaways, credits per model.

### 7. Score the hook (Virality Predictor)
```
python scripts/hook_preview.py WORK --seconds 15      # quick 720p proxy of the first 15 s with voice
```
Run `make_spec.py` first (step 9) so the preview carries the title and captions. Then:
`media_upload` (filename `hook-preview.mp4`) → `python scripts/hf_upload.py WORK/hook-preview.mp4 "<upload_url>"`
(prints 200) → `media_confirm` → `virality_predictor` `create` with the media_id → `jobs_wait` (1–3 min) →
`python scripts/virality_scores.py WORK <result_url> --label "hook v1"`. That prints `hook_score`,
`viral_potential`, `overall_score` (0–100) and `sustain_score` (0–1) and keeps every run in `virality.json`.
If the hook scores low, rewrite lines 1–2 (stronger image, open question), re-voice, re-time and score
again. Report every score honestly, including the ones that did not improve. It is a model's prediction,
not a guarantee.

### 8. The CapCut look (transitions, effects, animations, text overlays)
CapCut's transitions, scene effects and animations are CapCut resources, not files. The engine copies the
exact object from any project where the user applied that item once, so first see what is available:
```
python scripts/capcut.py catalog      # transition / scene effect / clip anim in|out / text anim in|out + source project
```
Pick from that list (nothing else will build) and write the look into `shots.json` (comments are for
reading here only, not part of the file):
```jsonc
{"look": {"effects": [{"name": "Vignette"}],                         // whole video, own track
          "title_anim_in": {"name": "Typewriter", "dur": 1.2}, "title_anim_out": {"name": "Fade Out", "dur": 0.5}},
 "shots": [{"id": 1, "anim_in": {"name": "Retro Fade-in", "dur": 0.8},  // clip animation on the shot
            "transition": {"name": "Page Turning", "dur": 0.9},         // into the next shot
            "effect": {"name": "Horizontal Reel"},                      // scene effect over this shot
            "overlays": [{"text": "First actual case of bug being found.", "at": 2.4,
                          "anim_in": {"name": "Typewriter", "dur": 1.6}}]}]}
```
Match the look to the story: one consistent base (a vignette or grain over everything), transitions at
scene changes rather than on every cut, effects only where the narration earns them (a film-reel effect for a
flashback, light when "the lights come back on"). Avoid flashing/strobe effects. If the user wants an item
that is not in the catalog, ask them to apply it once in any CapCut project, quit CapCut, and rerun `catalog`.
Transition length is capped at 45 % of the shorter neighbouring clip.

### 9. Build the CapCut project
1. Project: the user creates an empty project in CapCut, names it and quits CapCut, **or**
   `python scripts/capcut.py new "<name>" --like "<any existing project>"` (`--width 1080 --height 1920`
   for vertical).
2. `python scripts/make_spec.py WORK --title "<title>"` (`--vertical` reads `media/v/`; `--music file.mp3`
   adds a bed at 0.25 with fades; `--no-captions`).
3. `python scripts/capcut.py build "<name>" WORK/capcut-spec.json --dry-run`, then without `--dry-run`.
4. `python scripts/capcut.py inspect "<name>"`: the end time must match the voice-over.
5. Tell the user to open the project in CapCut. Shots alternate a +6 % zoom in/out, clip audio is muted,
   captions sit in the lower band and never cross a cut, the title is on the hook, the look from step 8 is on
   its own tracks (effects, overlays) so every piece stays individually editable.

### 10. Learn from the user's edits
After the user changes the edit in CapCut and quits it: `capcut.py inspect "<name>" --json`, compare with
`capcut-spec.json` (moved or trimmed clips, caption size/position, volumes, deleted shots) and write each
change as a dated, concrete rule into the user's briefing. Read it before every new spec.

**Where the briefing lives:** `~/.claude/capcut-higgsfield/briefing.md` (Windows:
`%USERPROFILE%\.claude\capcut-higgsfieldriefing.md`). If it does not exist yet, copy this skill's
`briefing.md` there first. Never write learned rules into the skill's own `briefing.md`: a plugin update
replaces the skill folder and the rules would be lost. Only if the home folder is not writable (e.g. a
sandboxed app), fall back to the skill's copy and tell the user.

## Costs (measured 2026-10-13, Higgsfield Plus)
| Item | Credits |
|---|---|
| GPT Image 2.5 still, 16:9, quality low / medium | 0.25 / 0.5 |
| Seedance 2.5, 720p, no audio (with audio) | 7 (8.75) per second, 4 s minimum |
| Seed Audio voice-over (whole 75 s script) | 0.4 |
| Virality Predictor | 0 (at the time of writing) |
| Video reframe, 60 s, 1080p | 549 — rebuild a 9:16 cut in CapCut from 9:16 stills instead |

A 75 s video with 14 stills and 1–2 motion clips: ~35–65 credits; with 8 motion clips (the demo build): ~265.

## Editing CapCut projects (general)
`capcut.py` is a general CapCut-from-files tool. The spec format, clip fields (zoom, keyframes, transitions,
fades, PiP, text styles, ripple cuts), the `--append` mode for adding layers to an existing edit, backups
(`capcut.py restore`) and troubleshooting are in `references/capcut-spec.md` and `references/draft-format.md`.

## Credits
The CapCut-by-files idea and the script → voice-over → timestamps → images → CapCut recipe follow Matt
Loui's "Claude edited my entire CapCut video" (2026-10-09). This skill adds the Higgsfield MCP pipeline:
style lock from explainer presets, Seedance motion shots, VO-timed shot lists, a credit ledger and the
Virality Predictor hook loop.
