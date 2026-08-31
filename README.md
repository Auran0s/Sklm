<div align="center">

# SKIM - SKlm IMproved

*Skills manager for AI agents*
</div>

## Why use SKIM?

I think copy&pasting markdown files from one special folder to another isn't the best way to manage specialised LLM context. At the same time, I wanted

- to have a toolbox of curated skillfiles
- to be able to cherrypick from the toolbox easily
- to make the skill adding/removal process easy and... more robust than trying to remember what convention my agent uses for skill storage?

I've forked [SKLM](https://github.com/Auran0s/Sklm) because I've ran into bugs in the installer and didn't see any activity in the original repo. I've also found that SKLM includes telemetry and it is opt out... nope, not on my watch. Shoutout to the original creator for creating and publishing SKLM, I only added minor improvements.  


## Features

- **Works with 30 AI agents** — from OpenCode and Claude Code to Codex CLI, GitHub Copilot, and beyond.
- **Install once, scope per project** — a global store at `~/.skim/` holds your skills; per-project symlinks activate only what you need.
- **Auto-sync** — `skim add` and `skim rm` automatically update the agent's skills directory. No manual copying.
- **Registry discovery** — index local folders or git repos as searchable skill catalogs.
- **Git repo installation** — `skim add --from` clones a repo and figures out where the skill lives.
- **Per-agent skill variants** — a single skill can ship agent-specific file overrides in a `variants/` subdirectory. Each agent receives the version tuned for it.

## Installation

```bash
uv tool install skim
```

## Quickstart

```bash
skim                               # interactive wizard opens — detects your setup
```

That's it. The CLI's interactive wizard detects your AI agents, initializes the workspace, and guides you through adding your first skill — no flags needed.

> [!TIP]
> Run `skim init --agent opencode` to skip the wizard and set a specific agent. Pass `--agent` multiple times for multiple agents.

## Usage

### Workspace setup

```bash
skim init                          # auto-detect or prompt for agent(s)
skim init --agent opencode         # force a specific agent
skim init --agent claude --agent cursor   # multiple agents at once
skim status                        # show workspace health
skim status --repair               # fix broken symlinks
```

If no agent directory is detected, skim shows an interactive prompt. Select one or more agents (e.g. `1,3,5`) or press `c` to skip.

### Global store (install once, activate anywhere)

```bash
skim install skill find-skills \
  --from https://github.com/vercel-labs/skills
skim uninstall skill find-skills               # remove from global store
skim uninstall skill find-skills --force       # skip confirmation

skim migrate                                   # import all from ~/.agents/skills/
skim migrate skill find-skills                 # import a single skill
skim migrate --from-registry my-reg            # import from a local registry
skim migrate --force-cleanup                   # delete sources after import
```


### Project resources (activate per project)

```bash
skim add skill my-skill                        # resolve → store → link → sync
skim add skill my-skill \
  --from https://github.com/user/skills        # install from git + activate
skim ls                                        # list active resources
skim ls --json                                 # machine-readable output
skim info skill my-skill                       # origin, path, link status
skim rm skill my-skill                         # unlink + clean agent config
```


### Skill variants (authoring)

A skill can ship agent-specific overrides using a `variants/` subdirectory inside the skill. When synced, the base skill is copied first, then any files from `variants/<agent-id>/` are merged on top.

```
my-skill/
  SKILL.md                 # fallback for any agent
  references/
    tools.md
  variants/
    opencode/
      SKILL.md             # overrides root SKILL.md for OpenCode
    claude/
      SKILL.md             # overrides it for Claude Code
      references/
        claude-only.md     # additional file, only for Claude
```

- Files in the variant override same-named files from the base.
- Files only in the variant are added.
- Files only in the base pass through untouched.
- `variants/` itself is never copied to the agent's config directory.
- If no variant exists for an agent, the base skill is used as-is.

Variant directory names match agent IDs (`opencode`, `claude`, `cursor`, `windsurf`, `gemini`, `cline`, `amazon-q`, `codex`, `github-copilot`, and all others listed in [Supported Agents](#supported-agents)).

`skim info skill <name>` lists available variants when present.

### Registry discovery

```bash
skim registry add ~/my-skills                           # local folder
skim registry add https://github.com/org/skills.git     # git repo
skim registry ls                                        # list registries
skim registry search scraper                            # search all registries
skim registry search scraper --registry my-skills       # within one registry
```

You can also reference skills by registry when adding:

```bash
skim add skill my-registry:my-skill
```

### Agent management

```bash
skim agent detect                    # identify the active agent
skim agent list                      # list all known agents
skim agent add opencode              # add an agent post-init (syncs skills)
skim agent remove claude             # remove an agent (cleans skills)
skim agent sync                      # force re-sync all linked skills
skim agent sync --dry-run            # preview without applying
```


### Updating

skim checks for new versions automatically after every command (once per day).
When a new release is available, a notice is shown with upgrade instructions.

```bash
skim update                         # upgrade to latest version via pip
skim update --check                 # check only, no upgrade
skim update --force                 # bypass 24h cache
```

Disable the automatic check by setting:

```bash
export SKIM_NO_UPDATE_CHECK=1
```

Updates are installed via `pip install -U skim`. The version check uses the [GitHub Releases](https://github.com/gojoGS/skim/releases) API.

### Supported Agents

| Agent | Config dir | Skills path | Auto-detected |
|---|---|---|---|
| OpenCode | `.opencode/` | `.opencode/skills/` | ✅ |
| Claude Code | `.claude/` | `.claude/skills/` | ✅ |
| Cursor | `.cursor/` | `.cursor/skills/` | ✅ |
| Windsurf | `.windsurf/` | `.windsurf/skills/` | ✅ |
| Gemini CLI | `.gemini/` | `.gemini/skills/` | ✅ |
| Cline | `.cline/` | `.cline/skills/` | ✅ |
| Amazon Q | `.amazonq/` | `.amazonq/skills/` | ✅ |
| Bob Shell | `.bob/` | `.bob/skills/` | ✅ |
| CodeBuddy | `.codebuddy/` | `.codebuddy/skills/` | ✅ |
| Codex CLI | `.codex/` | `.codex/skills/` | ✅ |
| Continue | `.continue/` | `.continue/skills/` | ✅ |
| Crush | `.crush/` | `.crush/skills/` | ✅ |
| Factory Droid | `.factory/` | `.factory/skills/` | ✅ |
| iFlow | `.iflow/` | `.iflow/skills/` | ✅ |
| Junie | `.junie/` | `.junie/skills/` | ✅ |
| Kilo Code | `.kilocode/` | `.kilocode/skills/` | ✅ |
| Kimi CLI | `.kimi/` | `.kimi/skills/` | ✅ |
| Kiro | `.kiro/` | `.kiro/skills/` | ✅ |
| Lingma | `.lingma/` | `.lingma/skills/` | ✅ |
| Pi | `.pi/` | `.pi/skills/` | ✅ |
| Qoder | `.qoder/` | `.qoder/skills/` | ✅ |
| Qwen Code | `.qwen/` | `.qwen/skills/` | ✅ |
| Trae | `.trae/` | `.trae/skills/` | ✅ |
| Mistral Vibe | `.vibe/` | `.vibe/skills/` | ✅ |
| Auggie | `.augment/` | `.augment/skills/` | ✅ |
| CoStrict | `.cospec/` | `.cospec/skills/` | ✅ |
| ForgeCode | `.forge/` | `.forge/skills/` | ✅ |
| RooCode | `.roo/` | `.roo/skills/` | ✅ |
| Antigravity | `.agent/` | `.agent/skills/` | — (explicit only) |
| GitHub Copilot | `.github/` | `.github/skills/` | — (explicit only) |

Antigravity and GitHub Copilot require `skim init --agent <name>` because `.agent/` and `.github/` exist in many projects unrelated to those tools.

> [!TIP]
> `skim init` without `--agent` shows an interactive prompt if no agent directory is found. Use `--agent` for non-interactive setups.

### How it Works

skim manages three locations to keep skills organized:

```
~/.skim/                 # global store (user-wide)
  store/skills/          #   installed skill directories
  config.yaml            #   resource catalog
  registries.yaml        #   registry sources
  cache/                 #   cloned git repos

./.skim/                 # per-project workspace (gitignored)
  skim.yaml              #   project config (agents, links, resources)
  links/skills/          #   symlinks → ~/.skim/store/skills/

<agent-dir>/skills/      # agent-visible copies (auto-synced)
                         # e.g., .opencode/skills/
```

Running `skim add skill my-skill` does four things in sequence:

1. **Resolve** — finds the skill in the global store, a registry, or a local path
2. **Store** — copies it into `~/.skim/store/skills/` if it wasn't there already
3. **Link** — creates a symlink in `./.skim/links/skills/`
4. **Sync** — copies the linked skill into the agent's config directory, applying any `variants/<agent>/` overlay automatically

Removal (`skim rm`) reverses steps 3 and 4. The global store is untouched, so skills stay available for other projects.

### Development

```bash
uv sync                             # create venv + install project + dev deps
uv run python -m pytest tests/      # run the test suite
uv run python -m pytest tests/ -k <pattern>   # run a subset
skim --version                      # check installed version
```

### Troubleshooting

**"No skim workspace found"**
Run `skim init` first. It creates the `.skim/` directory and configures your agent.

**"No agent configured — not synced"**
The skill is installed and linked, but no agent is set up to receive it. Run `skim init --agent <name>`.

**"Broken symlinks"**
Run `skim status --repair` to re-create links that point to missing targets.

**"Skill not found in git repo"**
Some repos use non-standard layouts. Use `--subdir` to point to the exact directory:
```bash
skim add skill my-skill --from https://github.com/user/repo --subdir custom/path
```

**"GitHub Copilot isn't detected"**
That's expected. Copilot requires explicit setup: `skim init --agent github-copilot`.

**"`skim registry add` fails"**
For git registries, make sure `git` is installed and the URL is accessible. For local paths, use an absolute or `~`-expanded path.
