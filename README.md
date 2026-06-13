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

### Workspace

```bash
cd my-project
fabrik init                    # Creates .fabrik/ in the project
fabrik init --agent opencode   # Or specify the agent explicitly
fabrik status                  # View workspace status
fabrik status --repair         # Repair broken links
```

### Global Store

```bash
fabrik global add skill ./my-skill     # Add a skill to the global store
fabrik global add mcp ./mcp-config.yaml # Add an MCP
fabrik global ls                        # List the global store
fabrik global ls skills                 # List only skills
fabrik global rm skill my-skill         # Remove from global store
```

### Resource Management

```bash
fabrik add skill my-skill              # Add a reference to the project
fabrik add mcp registry:my-mcp         # Add from a registry
fabrik ls                               # List resources
fabrik ls skills                        # List only skills
fabrik ls --json                        # JSON output
fabrik info skill my-skill             # View details
fabrik rm skill my-skill               # Remove from project
fabrik rm skill my-skill --force       # Remove + unlink
```

### Linking

```bash
fabrik link skill my-skill             # Link global → project
fabrik unlink skill my-skill           # Unlink
fabrik link skill my-skill --no-sync   # Link without syncing agent
```

### Registry

```bash
fabrik registry add ~/my-skills       # Add a local registry
fabrik registry add https://github.com/org/skills.git  # Git registry
fabrik registry ls                     # List registries
fabrik registry search scraper         # Search across all registries
fabrik registry search scraper --registry my-skills  # Filter by registry
fabrik registry search scraper --type skill           # Filter by type
```

### Agent

```bash
fabrik agent detect                   # Detect the active agent
fabrik agent sync                     # Synchronize agent config
fabrik agent sync --dry-run           # Preview changes
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
  local/skills/          # Project-specific skills
  local/mcps/            # Project-specific MCPs
```

## Development

```bash
pip install -e .
pip install pytest
python3 -m pytest tests/
```

## License

MIT
