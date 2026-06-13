# Fabrik

**MCP/Skills manager for AI agents.**

Fabrik is a Python CLI that centralizes management of **skills** (SKILL.md files)
and **MCPs** (Model Context Protocol configurations) for your AI agents —
OpenCode, Claude Code, Cursor, etc.

## Problem

Agent resources are either **global** (available everywhere but pollute
every project) or **local** (project-specific but must be reinstalled
each time). Fabrik resolves this tension.

## Installation

```bash
git clone https://github.com/Auran0s/fabrik.git
cd fabrik
pip install -e .
```

## Usage

Fabrik manages resources through a simple three-step flow. `add` does
everything — resolve, store, link, and sync — in a single command.

```
    COLLECTION ──→ ACTIVATE
   global ls          add
   global rm          ls
                      info
                      rm
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

### Global Store

The global store (`~/.fabrik/`) is your personal curated library of
skills and MCPs. Resources are automatically copied here when you
run `fabrik add` from a registry or local path.

```bash
fabrik global ls                        # Browse your entire library
fabrik global ls skills                 # Browse only skills (filter by type)
fabrik global rm skill my-skill         # Remove from your library
```

### Resource Management

`fabrik add` is the single command to add and activate a resource in
your project. It resolves the resource, copies it to the global store
if needed, links it into the workspace, and syncs with your AI agent
— all in one step.

```bash
fabrik add skill my-skill              # Add and activate a skill (from global store or registry)
fabrik add skill ./my-skill/           # Add and activate a skill from a local path
fabrik add mcp registry:my-mcp         # Add and activate an MCP from a specific registry
fabrik ls                               # List all active resources
fabrik ls skills                        # List only active skills
fabrik ls --json                        # Machine-readable JSON output
fabrik info skill my-skill             # Show details (origin, path, status)
fabrik rm skill my-skill               # Remove, unlink, and clean up from agent in one step
```

### Registry

Registries are discovery sources — local directories or git repos
where you can find and import skills and MCPs. Think of them as
package indexes for agent resources.

```bash
fabrik registry add ~/my-skills                 # Add a local folder as a registry source
fabrik registry add https://github.com/org/skills.git  # Add a git repository as a registry source
fabrik registry ls                               # List all configured registries
fabrik registry search scraper                   # Search for resources across all registries
fabrik registry search scraper --registry my-skills # Search within a specific registry
fabrik registry search scraper --type skill       # Filter search results by resource type
```

### Agent

Agent synchronization runs automatically during `add` and `rm`. You
only need the agent commands for setup and diagnostics.

```bash
fabrik agent detect                   # Identify which AI agent is active in this project
```

## Architecture

```
~/.fabrik/               # Global store (user-wide)
  config.yaml            # Global resource catalog
  registries.yaml        # Registry sources
  store/skills/          # Global skills
  store/mcps/            # Global MCPs

./.fabrik/               # Project workspace
  fabrik.yaml            # Project configuration
  links/skills/          # Linked skill symlinks
  links/mcps/            # Linked MCP symlinks
```

## Development

```bash
pip install -e .
pip install pytest
python3 -m pytest tests/
```

## License

MIT
