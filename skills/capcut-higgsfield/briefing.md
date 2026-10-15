# Editing briefing: how this user likes their edits

Claude reads this before writing a spec and updates it after every reassessment (SKILL.md step 10):
what the user changed by hand in CapCut becomes a concrete, dated rule here. Numbers, not adjectives.

## Defaults (until the user says otherwise)

| Thing | Default | Spec field |
|---|---|---|
| Canvas | 1920×1080, 30 fps (vertical: 1080×1920) | `canvas` |
| Shots | one per spoken line, cut where the line starts in the voice-over, no gaps | `at` / `dur` |
| Zoom on stills | alternate in / out, +6 % over the clip | `zoom`, `zoom_amount: 0.06` |
| Motion clips | muted, followed by their own still if shorter than the shot | `volume: 0` |
| Music | none unless asked; if asked, `volume` 0.25 under the voice, fade in 1.5 s, out 2 s | audio clip |
| Title | on the hook, size 12, bold, white with black stroke, upper third | `text_styles.title` |
| Captions | size 7 (vertical 9), white on a 60 % black box, lower band, ≤ 42 chars (vertical 32), never across a cut | `text_styles.caption` |

## Learned from reassessments

<!-- e.g. 2026-10-20: user moved every caption up from y -0.78 to -0.70 -> new default -0.70 -->
