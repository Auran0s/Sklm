<div align="center">

# Sklm

*Skills manager for AI agents*

![Python version](https://img.shields.io/badge/Python->=3.9-3776AB?style=flat-square&logo=python&logoColor=fff)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)

[Quickstart](#quickstart) • [Usage](#usage) • [Supported Agents](#supported-agents) • [Architecture](#architecture) • [Development](#development)

</div>

Sklm is a CLI tool that centralizes management of **skills** (SKILL.md files) for your AI agents. It solves the tension between wanting skills globally available vs. per-project scoped, without polluting your agent's configuration.

> [!TIP]
> New to Sklm? Start with [`sklm init`](#quickstart) — it auto-detects your AI agent and sets up everything in seconds.

## Features

- **Multi-agent support** — recognizes 8 AI agents (OpenCode, Claude Code, Cursor, Windsurf, Gemini CLI, Cline, Amazon Q, GitHub Copilot) and syncs skills to the right place.
- **Global store** — install skills once in `~/.sklm/`, reuse across projects.
- **Per-project scoping** — activate only the skills each project needs via symlinks; your agent only sees what you explicitly add.
- **Registry discovery** — index local directories or git repos as resource catalogs, searchable by keyword.
- **Auto-sync** — `sklm add` and `sklm rm` automatically sync your agent's configuration directory — no manual copying.
- **Telemetry (opt-out)** — anonymous usage tracking via Umami. Disable with `SKLM_TELEMETRY=0`.

## Installation

```bash
git clone https://github.com/Auran0s/sklm.git
cd sklm
pip install -e .
```

## Quickstart

```bash
sklm init                          # Creates .sklm/ and detects your agent
sklm install skill my-skill \
  --from https://github.com/user/skills   # Install into global store
sklm add skill my-skill            # Activate in the current project
```

That's it — your AI agent can now use the skill.

> [!TIP]
> If you already have skills in `~/.agents/skills/`, import them with `sklm migrate`.

## Usage

### Workspace setup

```bash
sklm init                          # Auto-detect agent and create .sklm/
sklm init --agent opencode         # Force a specific agent
sklm status                        # Show workspace health
sklm status --repair               # Fix broken symlinks
```

### Global store (install once)

```bash
sklm install skill find-skills \
  --from https://github.com/vercel-labs/skills
sklm uninstall skill find-skills   # Remove from global store
sklm uninstall skill find-skills --force   # Skip confirmation
sklm migrate                       # Import from ~/.agents/skills/
sklm migrate skill find-skills     # Import a single skill
```

### Resource management (activate per project)

```bash
sklm add skill my-skill            # Full pipeline: resolve → store → link → sync
sklm add skill my-skill \
  --from https://github.com/user/skills   # Install from git and activate
sklm ls                             # List active resources
sklm ls --json                      # Machine-readable output
sklm info skill my-skill           # Show origin, path, status
sklm rm skill my-skill             # Remove, unlink, and clean agent
```

### Registry discovery

```bash
sklm registry add ~/my-skills                  # Local folder as registry
sklm registry add https://github.com/org/skills.git   # Git repo as registry
sklm registry ls                                # List registries
sklm registry search scraper                    # Search across all registries
sklm registry search scraper --registry my-skills   # Within a specific registry
```

### Agent management

```bash
sklm agent detect                   # Identify the active AI agent
sklm agent list                     # List all known agents
sklm agent sync                     # Force re-sync all linked skills
sklm agent sync --dry-run           # Preview changes without applying
```

### Telemetry

```bash
sklm telemetry status              # Check if telemetry is enabled
sklm telemetry off                  # Disable anonymous usage data
sklm telemetry on                   # Re-enable
```

## Supported Agents

Sklm detects the active agent by checking which config directories exist in your project:

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

GitHub Copilot requires `sklm init --agent github-copilot` because `.github/` is too common to auto-detect.

## Architecture

Sklm uses a two-level store model:

```
~/.sklm/                 # Global store (user-wide)
  config.yaml            # Resource catalog
  registries.yaml        # Registry sources
  cache/                 # Cloned git repos (for install --from)
  store/skills/          # Installed skill directories

./.sklm/                 # Per-project workspace (gitignored)
  sklm.yaml              # Project config (agent, links, resources)
  links/skills/          # Symlinks → ~/.sklm/store/skills/

<agent-dir>/skills/      # Agent-visible copies (auto-synced)
                         # e.g., .opencode/skills/ for OpenCode
```

The `sklm add` command runs four steps in sequence:

1. **Resolve** — find the resource (global store → registries → local path)
2. **Store** — copy it into `~/.sklm/store/` if not already there
3. **Link** — create a symlink in `./.sklm/links/`
4. **Sync** — copy linked skills to the agent's config directory

Removal (`sklm rm`) reverses steps 3 and 4. The global store is untouched — skills remain available for other projects.

## Development

```bash
pip install -e .                    # Editable install
pip install -r requirements.txt     # Dev dependencies (pytest, pytest-cov)
python3 -m pytest tests/            # Run the test suite
python3 -m pytest tests/ -k <pattern>   # Run a subset of tests
```
