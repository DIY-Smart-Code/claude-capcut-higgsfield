# claude-capcut-higgsfield

A Claude skill that makes faceless videos with the **Higgsfield MCP** and hands them over as an
**editable CapCut project**, not a flattened MP4.

Claude writes a sourced script, locks a visual style, and generates everything through Higgsfield:
the voice-over, every shot and the motion clips. It times each shot to the real voice-over and scores the
hook with Higgsfield's Virality Predictor. Then it writes a CapCut timeline (shots, zooms, voice-over,
captions, title) straight into CapCut's project files. You open CapCut and keep editing by hand.

```
script + sources ─▶ style preset ─▶ voice-over ─▶ word timestamps ─▶ shots + motion clips
      ─▶ hook score (fix + re-score) ─▶ CapCut project you can still edit ─▶ learns from your edits
```

## What you need

- **Claude Code** (or another agent that loads skills) with the **Higgsfield MCP** connected:
  `https://mcp.higgsfield.ai/mcp` (no API key; sign in on first use).
  - Claude Code: `claude mcp add --transport http higgsfield https://mcp.higgsfield.ai/mcp`
  - Claude app: Settings → Connectors → **+** → name `Higgsfield`, URL `https://mcp.higgsfield.ai/mcp` → Add
- **CapCut desktop** (tested with 9.5 on Windows). Close CapCut while the skill writes a project.
- **Python 3.10+** with `pip install faster-whisper`, and **ffmpeg / ffprobe** on PATH.
- Higgsfield credits. A 75-second video with 14 stills and 1–2 motion clips used about 35–65 credits in
  our tests (prices in `SKILL.md`).

## Install

```bash
git clone https://github.com/DIY-Smart-Code/claude-capcut-higgsfield
cp -r claude-capcut-higgsfield/skills/capcut-higgsfield ~/.claude/skills/
```

On Windows (PowerShell): `Copy-Item -Recurse claude-capcut-higgsfield\skills\capcut-higgsfield $HOME\.claude\skills\`

## Use

Ask Claude something like:

> Make a 75-second faceless video about the 1947 moth that was taped into the Harvard Mark II logbook.
> Watercolor style, male narrator, 16:9, budget 80 credits. Put it in CapCut.

Claude shows you the script and the cost before spending credits, lets you pick the style and the voice,
and tells you when the CapCut project is ready to open. When you change the edit in CapCut and ask it to
reassess, it records what you changed in `briefing.md` and applies it to the next video.

## What's inside

| File | Does |
|---|---|
| `SKILL.md` | The pipeline Claude follows, with Higgsfield MCP calls, prompt rules and measured costs |
| `scripts/capcut.py` | Writes / inspects / backs up CapCut projects from a JSON edit spec |
| `scripts/shotlist.py` | Times every shot from the real voice-over (faster-whisper word timestamps) |
| `scripts/hf_fetch.py` | Downloads Higgsfield results into the work folder and keeps a credit ledger |
| `scripts/hf_upload.py` | Uploads a local file to Higgsfield (for the Virality Predictor) |
| `scripts/hook_preview.py` | Renders a 15 s proxy of the opening to score |
| `scripts/virality_scores.py` | Reads hook / viral / overall scores from the predictor's dashboard |
| `scripts/make_spec.py` | Turns the timed shot list into a CapCut edit spec |
| `scripts/captions.py` | Word timestamps → caption clips |

## Limits

- CapCut's project format is undocumented. This works with CapCut 9.5; after a CapCut update, build a test
  project and open it before trusting it with real work (10.x reportedly rejects tool-written drafts).
- Filters, stickers and text animations are not written. Add them in CapCut.
- The Virality Predictor is a model's prediction, not a promise.

## Credits

The idea of editing CapCut by writing its project files, and the script → voice-over → timestamps →
images → CapCut recipe, come from Matt Loui's video "Claude edited my entire CapCut video" (2026-10-09).
This repo adds the Higgsfield MCP pipeline: preset style lock, Seedance motion shots, voice-over-timed
shot lists, a credit ledger and the hook-scoring loop.

Made by [DIY Smart Code](https://www.youtube.com/@diysmartcode). MIT License.
