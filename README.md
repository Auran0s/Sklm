<div align="center">

# Fabrik

*Skills manager for AI agents*

![Python version](https://img.shields.io/badge/Python->=3.9-3776AB?style=flat-square&logo=python&logoColor=fff)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)

[Quickstart](#quickstart) • [Usage](#usage) • [Supported Agents](#supported-agents) • [Architecture](#architecture) • [Development](#development)

</div>

Fabrik is a CLI tool that centralizes management of **skills** (SKILL.md files) for your AI agents. It solves the tension between wanting skills globally available vs. per-project scoped, without polluting your agent's configuration.

> [!TIP]
> New to Fabrik? Start with [`fabrik init`](#quickstart) — it auto-detects your AI agent and sets up everything in seconds.

## Features

- **Multi-agent support** — recognizes 8 AI agents (OpenCode, Claude Code, Cursor, Windsurf, Gemini CLI, Cline, Amazon Q, GitHub Copilot) and syncs skills to the right place.
- **Global store** — install skills once in `~/.fabrik/`, reuse across projects.
- **Per-project scoping** — activate only the skills each project needs via symlinks; your agent only sees what you explicitly add.
- **Registry discovery** — index local directories or git repos as resource catalogs, searchable by keyword.
- **Auto-sync** — `fabrik add` and `fabrik rm` automatically sync your agent's configuration directory — no manual copying.
- **Telemetry (opt-out)** — anonymous usage tracking via Umami. Disable with `FABRIK_TELEMETRY=0`.

## Installation

```bash
git clone https://github.com/Auran0s/fabrik.git
cd fabrik
pip install -e .
```

## Quickstart

```bash
fabrik init                          # Creates .fabrik/ and detects your agent
fabrik install skill my-skill \
  --from https://github.com/user/skills   # Install into global store
fabrik add skill my-skill            # Activate in the current project
```

That's it — your AI agent can now use the skill.

> [!TIP]
> If you already have skills in `~/.agents/skills/`, import them with `fabrik migrate`.

## Usage

### Workspace setup

```bash
fabrik init                          # Auto-detect agent and create .fabrik/
fabrik init --agent opencode         # Force a specific agent
fabrik status                        # Show workspace health
fabrik status --repair               # Fix broken symlinks
```

### Global store (install once)

```bash
fabrik install skill find-skills \
  --from https://github.com/vercel-labs/skills
fabrik uninstall skill find-skills   # Remove from global store
fabrik uninstall skill find-skills --force   # Skip confirmation
fabrik migrate                       # Import from ~/.agents/skills/
fabrik migrate skill find-skills     # Import a single skill
```

### Resource management (activate per project)

```bash
fabrik add skill my-skill            # Full pipeline: resolve → store → link → sync
fabrik add skill my-skill \
  --from https://github.com/user/skills   # Install from git and activate
fabrik ls                             # List active resources
fabrik ls --json                      # Machine-readable output
fabrik info skill my-skill           # Show origin, path, status
fabrik rm skill my-skill             # Remove, unlink, and clean agent
```

### Registry discovery

```bash
fabrik registry add ~/my-skills                  # Local folder as registry
fabrik registry add https://github.com/org/skills.git   # Git repo as registry
fabrik registry ls                                # List registries
fabrik registry search scraper                    # Search across all registries
fabrik registry search scraper --registry my-skills   # Within a specific registry
```

### Agent management

```bash
fabrik agent detect                   # Identify the active AI agent
fabrik agent list                     # List all known agents
fabrik agent sync                     # Force re-sync all linked skills
fabrik agent sync --dry-run           # Preview changes without applying
```

### Telemetry

```bash
fabrik telemetry status              # Check if telemetry is enabled
fabrik telemetry off                  # Disable anonymous usage data
fabrik telemetry on                   # Re-enable
```

## Supported Agents

Fabrik detects the active agent by checking which config directories exist in your project:

| Agent | Config directory | Skills path | Auto-detect |
|---|---|---|---|
| OpenCode | `.opencode/` | `.opencode/skills/` | ✅ |
| Claude Code | `.claude/` | `.claude/skills/` | ✅ |
| Cursor | `.cursor/` | `.cursor/skills/` | ✅ |
| Windsurf | `.windsurf/` | `.windsurf/skills/` | ✅ |
| Gemini CLI | `.gemini/` | `.gemini/skills/` | ✅ |
| Cline | `.cline/` | `.cline/skills/` | ✅ |
| Amazon Q | `.amazonq/` | `.amazonq/skills/` | ✅ |
| GitHub Copilot | `.github/` | `.github/skills/` | 🔲 (explicit only) |

GitHub Copilot requires `fabrik init --agent github-copilot` because `.github/` is too common to auto-detect.

## Architecture

Fabrik uses a two-level store model:

```
~/.fabrik/               # Global store (user-wide)
  config.yaml            # Resource catalog
  registries.yaml        # Registry sources
  cache/                 # Cloned git repos (for install --from)
  store/skills/          # Installed skill directories

./.fabrik/               # Per-project workspace (gitignored)
  fabrik.yaml            # Project config (agent, links, resources)
  links/skills/          # Symlinks → ~/.fabrik/store/skills/

<agent-dir>/skills/      # Agent-visible copies (auto-synced)
                         # e.g., .opencode/skills/ for OpenCode
```

The `fabrik add` command runs four steps in sequence:

1. **Resolve** — find the resource (global store → registries → local path)
2. **Store** — copy it into `~/.fabrik/store/` if not already there
3. **Link** — create a symlink in `./.fabrik/links/`
4. **Sync** — copy linked skills to the agent's config directory

Removal (`fabrik rm`) reverses steps 3 and 4. The global store is untouched — skills remain available for other projects.

## Development

```bash
pip install -e .                    # Editable install
pip install -r requirements.txt     # Dev dependencies (pytest, pytest-cov)
python3 -m pytest tests/            # Run the test suite
python3 -m pytest tests/ -k <pattern>   # Run a subset of tests
```
