# claude-capcut-higgsfield

> ▶ **Watch it in action:** [Claude + Higgsfield MCP make a faceless video as an editable CapCut project](https://youtu.be/5x5oYTYn4e8)

> [!WARNING]
> **Early test version. Use at your own risk.** This is a first test of the skill. It does not cover
> everything CapCut can do, and parts of it may not work on your setup. The skill writes straight into
> CapCut's project files, so **back up your CapCut projects before you use it**: copy the whole drafts
> folder, `%LOCALAPPDATA%\CapCut\User Data\Projects\com.lveditor.draft` on Windows or `~/Movies/CapCut/User Data/Projects/com.lveditor.draft` on macOS.
> The skill keeps its own backup of each project it changes (`capcut.py backup` / `restore`), but that
> is no replacement for yours.

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

Find your assistant below. The marketplace is **`diy-smart-code`**, the plugin is **`capcut-higgsfield`**.
Every assistant needs the Higgsfield MCP connected (see above); the plugin doesn't add it, because most
people already have it as a connector and a second copy would duplicate every tool.

### Claude Code

```
/plugin marketplace add DIY-Smart-Code/claude-capcut-higgsfield
/plugin install capcut-higgsfield@diy-smart-code
```

On Claude Code 2.1.275 or later, one line does both:
`/plugin install capcut-higgsfield --marketplace DIY-Smart-Code/claude-capcut-higgsfield`.
Update later with `/plugin marketplace update diy-smart-code`.

### Claude app (claude.ai / desktop)

Zip the `skills/capcut-higgsfield` folder and upload it under **Settings → Capabilities → Skills**.

### GitHub Copilot CLI

```bash
copilot plugin marketplace add DIY-Smart-Code/claude-capcut-higgsfield
copilot plugin install capcut-higgsfield@diy-smart-code
```

Copilot reads the same `.claude-plugin/marketplace.json`.

### Codex CLI

```bash
codex plugin marketplace add https://github.com/DIY-Smart-Code/claude-capcut-higgsfield
codex plugin add capcut-higgsfield@diy-smart-code
```

Note `plugin add`, not `plugin install`. Confirm with `codex plugin list`.

### Gemini CLI

```bash
gemini extensions install https://github.com/DIY-Smart-Code/claude-capcut-higgsfield
```

Run it outside Gemini's interactive mode; it takes effect on the next session. Update with
`gemini extensions update capcut-higgsfield`.

### Cursor

Clone the repo and link it into Cursor's local plugin folder, then run **Developer: Reload Window**:

```bash
git clone https://github.com/DIY-Smart-Code/claude-capcut-higgsfield
mkdir -p ~/.cursor/plugins/local
ln -s "$PWD/claude-capcut-higgsfield" ~/.cursor/plugins/local/capcut-higgsfield
```

On Windows (PowerShell, as admin or with Developer Mode on):
`New-Item -ItemType SymbolicLink -Path $HOME\.cursor\plugins\local\capcut-higgsfield -Target $PWD\claude-capcut-higgsfield`

### Manual (any agent that loads skills)

```bash
git clone https://github.com/DIY-Smart-Code/claude-capcut-higgsfield
cp -r claude-capcut-higgsfield/skills/capcut-higgsfield ~/.claude/skills/
```

What the skill learns from your CapCut edits is kept in `~/.claude/capcut-higgsfield/briefing.md`, outside
the plugin folder, so updates never wipe it.

## Use

Ask Claude something like:

> Make a 75-second faceless video about the 1947 moth that was taped into the Harvard Mark II logbook.
> Watercolor style, male narrator, 16:9, budget 80 credits. Put it in CapCut.

Claude shows you the script and the cost before spending credits, lets you pick the style and the voice,
and tells you when the CapCut project is ready to open. When you change the edit in CapCut and ask it to
reassess, it records what you changed in your briefing (`~/.claude/capcut-higgsfield/briefing.md`) and applies it to the next video.

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
| `.claude-plugin/`, `.codex-plugin/`, `.cursor-plugin/`, `.agents/plugins/`, `gemini-extension.json` | Plugin and marketplace manifests for each assistant (all point at `skills/`) |

## Limits

- This is an early test version, not a finished tool. Expect gaps and rough edges, and please report
  what breaks in the issues.
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
