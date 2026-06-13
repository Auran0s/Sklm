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

Fabrik manages resources through a four-stage pipeline. Every command
belongs to one of these stages:

```
    COLLECTION ──→ DECLARATION ──→ ACTIVATION ──→ SYNC
   global add         add             link          agent sync
   global ls          ls              unlink        agent detect
   global rm          info
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
skills and MCPs. Resources must be in the global store before they
can be linked to a project.

```bash
fabrik global add skill ./my-skill     # Import a skill into your personal library
fabrik global add mcp ./mcp-config.yaml # Import an MCP configuration
fabrik global ls                        # Browse your entire library
fabrik global ls skills                 # Browse only skills (filter by type)
fabrik global rm skill my-skill         # Remove from your library
```

### Resource Management

Once a resource is in the global store (or a registry), declare it
for the current project with `add`. This does **not** activate the
resource yet — it simply records that this project uses it.

```bash
fabrik add skill my-skill              # Declare a resource from the global store
fabrik add mcp registry:my-mcp         # Declare a resource from a specific registry
fabrik ls                               # List all declared resources
fabrik ls skills                        # List only declared skills
fabrik ls --json                        # Machine-readable JSON output
fabrik info skill my-skill             # Show details (origin, path, link status)
fabrik rm skill my-skill               # Remove the declaration
fabrik rm skill my-skill --force       # Remove declaration and unlink in one step
```

### Linking

Linking creates a symlink that makes a declared resource accessible
in the project. After linking, the resource is automatically
synchronized to your agent's configuration (unless `--no-sync` is
passed). Unlinking removes the symlink without losing the declaration.

```bash
fabrik link skill my-skill             # Activate: symlinks the resource and syncs the agent
fabrik unlink skill my-skill           # Deactivate: removes the symlink, keeps the declaration
fabrik link skill my-skill --no-sync   # Link without updating the agent (batch multiple links)
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

The final stage: synchronize your linked resources into the agent's
configuration so the agent can actually see and use them. This runs
automatically after every `link` and `unlink`.

```bash
fabrik agent detect                   # Identify which AI agent is active in this project
fabrik agent sync                     # Apply all linked resources to the agent's config
fabrik agent sync --dry-run           # Preview what would change without applying it
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
