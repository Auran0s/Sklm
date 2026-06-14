# Fabrik

**Skills manager for AI agents.**

Fabrik is a Python CLI that centralizes management of **skills** (SKILL.md files)
for your AI agents.

## Problem

Agent resources are either **global** (available everywhere but pollute
every project) or **local** (project-specific but must be reinstalled
each time). Fabrik resolves this tension with a **per-project scoping**
model: install skills globally in a hidden store, then activate only
what you need in each project.

## Installation

```bash
git clone https://github.com/Auran0s/fabrik.git
cd fabrik
pip install -e .
```

## Usage

Fabrik provides a simple lifecycle for skills:

```
    INSTALL ──→ ACTIVATE ──→ DEACTIVATE ──→ UNINSTALL
   install        add            rm           uninstall
   migrate        ls            (keep in       (remove
       (import)       info          store)        from store)
```

Use the sections below to find the right command for your current stage.

### Workspace

Before using any Fabrik commands, initialize a workspace in your
project directory. This creates the `.fabrik/` structure and detects
your AI agent. Use `status` to inspect what's configured and check
for broken links.

```bash
cd my-project
fabrik init                          # First command: creates .fabrik/ and detects the agent
fabrik init --agent opencode         # Force a specific agent (skip auto-detection)
fabrik status                        # Show workspace health (resources, links, broken symlinks)
fabrik status --repair               # Auto-fix any broken symlinks
```

### Install (Store without Activating)

Install a skill from a GitHub repository into the global store without
activating it in the current project. This lets you pre-install skills
and activate them later per project.

```bash
fabrik install skill find-skills --from https://github.com/vercel-labs/skills
fabrik install skill flask-api --from https://github.com/aj-geddes/useful-ai-prompts \
  --subdir skills/flask-api-development
fabrik uninstall skill find-skills                # Remove from store permanently
fabrik uninstall skill find-skills --force        # Skip confirmation
```

### Migrating from existing tools

If you're coming from another tool — for example, skills installed via `npx skills`
in `~/.agents/skills/` — import them into Fabrik's store:

```bash
fabrik migrate                         # Import all externally managed skills
fabrik migrate skill find-skills       # Import a specific skill
```

### Resource Management

`fabrik add` is the single command to install and activate a resource in
your project. It resolves the resource, copies it to the global store
if needed, links it into the workspace, and syncs with your AI agent
— all in one step.

```bash
fabrik add skill my-skill              # Add and activate (from store, registry, or local path)
fabrik add skill find-skills --from https://github.com/vercel-labs/skills  # Install from GitHub + activate
fabrik ls                               # List all active resources
fabrik ls skills                        # List only active skills
fabrik ls --json                        # Machine-readable JSON output
fabrik info skill my-skill             # Show details (origin, path, status)
fabrik rm skill my-skill               # Remove from project, unlink, and clean agent
```

### Registry

Registries are discovery sources — local directories or git repos
where you can find and import skills. Think of them as
package indexes for agent resources.

```bash
fabrik registry add ~/my-skills                 # Add a local folder as a registry source
fabrik registry add https://github.com/org/skills.git  # Add a git repository as a registry source
fabrik registry ls                               # List all configured registries
fabrik registry search scraper                   # Search for resources across all registries
fabrik registry search scraper --registry my-skills # Search within a specific registry
fabrik registry search scraper --type skill       # Filter search results by resource type
```

### Per-Project Scoping

Skills installed globally (e.g., via `npx skills` in `~/.agents/skills/`) may be
visible to your AI agent in **every** project. Fabrik changes this by scoping
skills per-project: your agent only sees skills that Fabrik explicitly syncs
into its configuration directory (e.g., `.opencode/skills/` for OpenCode).

Use `fabrik status` to check for unmanaged skills that may bypass scoping.

```bash
fabrik status
# ⚠ 5 skills found outside Fabrik's store
#    These may be globally visible to your AI agent in every project.
#    Use fabrik migrate to import them into the Fabrik store.
```

### Agent

Agent synchronization runs automatically during `add` and `rm`. You
only need the agent commands for setup and diagnostics.

```bash
fabrik agent detect                   # Identify which AI agent is active in this project
```

## Supported Agents

Fabrik recognizes and can sync skills with the following AI agents:

| Agent | ID | Skills | Commands | Auto-detect |
|---|---|---|---|---|
| OpenCode | `opencode` | `.opencode/skills/` | `init`, `add`, `rm`, `agent sync` | ✅ |
| Claude Code | `claude` | `.claude/skills/` | `init`, `add`, `rm`, `agent sync` | ✅ |
| Cursor | `cursor` | `.cursor/skills/` | `init`, `add`, `rm`, `agent sync` | ✅ |
| Windsurf | `windsurf` | `.windsurf/skills/` | `init`, `add`, `rm`, `agent sync` | ✅ |
| Gemini CLI | `gemini` | `.gemini/skills/` | `init`, `add`, `rm`, `agent sync` | ✅ |
| Cline | `cline` | `.cline/skills/` | `init`, `add`, `rm`, `agent sync` | ✅ |
| Amazon Q | `amazon-q` | `.amazonq/skills/` | `init`, `add`, `rm`, `agent sync` | ✅ |
| GitHub Copilot | `github-copilot` | `.github/skills/` | `init --agent github-copilot` | 🔲 (explicit only) |

### Other agents

The following agents are recognized but not yet supported. Pull requests welcome!

| Agent | Status |
|---|---|
| Agent (`~/.agent/`) | 🔲 |
| Augment (`~/.augment/`) | 🔲 |
| Codex (`~/.codex/`) | 🔲 |
| Forge (`~/.forge/`) | 🔲 |
| Cospec (`~/.cospec/`) | 🔲 |
| Roo (`~/.roo/`) | 🔲 |

## Architecture

```
~/.fabrik/               # Global store (user-wide, hidden from agents)
  config.yaml            # Global resource catalog
  registries.yaml        # Registry sources
  cache/                 # Cloned git repositories (for install --from)
  store/skills/          # Global skills (each may have .fabrik-source.yaml)

./.fabrik/               # Project workspace (not committed)
  fabrik.yaml            # Project configuration
  links/skills/          # Linked skill symlinks → ~/.fabrik/store/skills/

<agent-dir>/skills/      # Agent sees only these (per-project scoping)
                         # e.g., .opencode/skills/ for OpenCode
```

## Development

```bash
pip install -e .
pip install pytest
python3 -m pytest tests/
```

## License

MIT
