<div align="center">

<img src="https://raw.githubusercontent.com/Auran0s/sklm/develop/docs/sklm-logo.png" alt="Sklm logo" width="120" />

# Sklm

*Skills manager for AI agents*

![Python version](https://img.shields.io/badge/Python->=3.9-3776AB?style=flat-square&logo=python&logoColor=fff)
[![License](https://img.shields.io/badge/License-MIT-yellow?style=flat-square)](LICENSE)

[![Product Hunt](https://api.producthunt.com/widgets/embed-image/v1/featured.svg?post_id=1172208&theme=light)](https://www.producthunt.com/products/sklm?utm_source=badge-featured&utm_medium=badge&utm_campaign=badge-sklm)

[Why Sklm?](#why-sklm) • [Quickstart](#quickstart) • [Usage](#usage) • [Updating](#updating) • [Supported Agents](#supported-agents) • [How it Works](#how-it-works) • [Development](#development)

</div>

## Why Sklm?

Sklm lets you install AI agent skills once and activate them per project. No more copy-pasting `SKILL.md` files between directories.

- **Install a skill globally** and every project sees it, even when it's irrelevant.
- **Drop it in one project** and it's invisible to others.

Sklm keeps a global library in `~/.sklm/`, then lets you pick which skills each project sees.

> [!NOTE]
> Sklm only supports `skill` resources for now. More resource types may come later.

## Features

- **Works with 30 AI agents** — from OpenCode and Claude Code to Codex CLI, GitHub Copilot, and beyond.
- **Install once, scope per project** — a global store at `~/.sklm/` holds your skills; per-project symlinks activate only what you need.
- **Auto-sync** — `sklm add` and `sklm rm` automatically update the agent's skills directory. No manual copying.
- **Registry discovery** — index local folders or git repos as searchable skill catalogs.
- **Git repo installation** — `sklm add --from` clones a repo and figures out where the skill lives.
- **Per-agent skill variants** — a single skill can ship agent-specific file overrides in a `variants/` subdirectory. Each agent receives the version tuned for it.

## Installation

```bash
pip install sklm-cli
```

> [!TIP]
> For development, clone the repo and use `pip install -e .` for an editable install.

## Quickstart

```bash
pip install sklm-cli                   # install globally
sklm                               # interactive wizard opens — detects your setup
```

That's it. The CLI's interactive wizard detects your AI agents, initializes the workspace, and guides you through adding your first skill — no flags needed.

> [!TIP]
> Run `sklm init --agent opencode` to skip the wizard and set a specific agent. Pass `--agent` multiple times for multiple agents.

## Usage

### Workspace setup

```bash
sklm init                          # auto-detect or prompt for agent(s)
sklm init --agent opencode         # force a specific agent
sklm init --agent claude --agent cursor   # multiple agents at once
sklm status                        # show workspace health
sklm status --repair               # fix broken symlinks
```

If no agent directory is detected, Sklm shows an interactive prompt. Select one or more agents (e.g. `1,3,5`) or press `c` to skip.

### Global store (install once, activate anywhere)

```bash
sklm install skill find-skills \
  --from https://github.com/vercel-labs/skills
sklm uninstall skill find-skills               # remove from global store
sklm uninstall skill find-skills --force       # skip confirmation

sklm migrate                                   # import all from ~/.agents/skills/
sklm migrate skill find-skills                 # import a single skill
sklm migrate --from-registry my-reg            # import from a local registry
sklm migrate --force-cleanup                   # delete sources after import
```


### Project resources (activate per project)

```bash
sklm add skill my-skill                        # resolve → store → link → sync
sklm add skill my-skill \
  --from https://github.com/user/skills        # install from git + activate
sklm ls                                        # list active resources
sklm ls --json                                 # machine-readable output
sklm info skill my-skill                       # origin, path, link status
sklm rm skill my-skill                         # unlink + clean agent config
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

`sklm info skill <name>` lists available variants when present.

### Registry discovery

```bash
sklm registry add ~/my-skills                           # local folder
sklm registry add https://github.com/org/skills.git     # git repo
sklm registry ls                                        # list registries
sklm registry search scraper                            # search all registries
sklm registry search scraper --registry my-skills       # within one registry
```

You can also reference skills by registry when adding:

```bash
sklm add skill my-registry:my-skill
```

### Agent management

```bash
sklm agent detect                    # identify the active agent
sklm agent list                      # list all known agents
sklm agent add opencode              # add an agent post-init (syncs skills)
sklm agent remove claude             # remove an agent (cleans skills)
sklm agent sync                      # force re-sync all linked skills
sklm agent sync --dry-run            # preview without applying
```

### Telemetry

Anonymous usage data via Umami. Opt out anytime.

```bash
sklm telemetry status               # check if enabled
sklm telemetry off                   # disable
sklm telemetry on                    # re-enable
```

Telemetry is also disabled by setting `SKLM_TELEMETRY=0` in your environment.


### Updating

sklm checks for new versions automatically after every command (once per day).
When a new release is available, a notice is shown with upgrade instructions.

```bash
sklm update                         # upgrade to latest version via pip
sklm update --check                 # check only, no upgrade
sklm update --force                 # bypass 24h cache
```

Disable the automatic check by setting:

```bash
export SKLM_NO_UPDATE_CHECK=1
```

Updates are installed via `pip install -U sklm-cli`. The version check uses the [GitHub Releases](https://github.com/Auran0s/Sklm/releases) API.

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

Antigravity and GitHub Copilot require `sklm init --agent <name>` because `.agent/` and `.github/` exist in many projects unrelated to those tools.

> [!TIP]
> `sklm init` without `--agent` shows an interactive prompt if no agent directory is found. Use `--agent` for non-interactive setups.

### How it Works

Sklm manages three locations to keep skills organized:

```
~/.sklm/                 # global store (user-wide)
  store/skills/          #   installed skill directories
  config.yaml            #   resource catalog
  registries.yaml        #   registry sources
  cache/                 #   cloned git repos

./.sklm/                 # per-project workspace (gitignored)
  sklm.yaml              #   project config (agents, links, resources)
  links/skills/          #   symlinks → ~/.sklm/store/skills/

<agent-dir>/skills/      # agent-visible copies (auto-synced)
                         # e.g., .opencode/skills/
```

Running `sklm add skill my-skill` does four things in sequence:

1. **Resolve** — finds the skill in the global store, a registry, or a local path
2. **Store** — copies it into `~/.sklm/store/skills/` if it wasn't there already
3. **Link** — creates a symlink in `./.sklm/links/skills/`
4. **Sync** — copies the linked skill into the agent's config directory, applying any `variants/<agent>/` overlay automatically

Removal (`sklm rm`) reverses steps 3 and 4. The global store is untouched, so skills stay available for other projects.

### Development

```bash
pip install -e .                    # editable install
pip install -r requirements.txt     # dev dependencies (pytest, pytest-cov)
python3 -m pytest tests/            # run the test suite
python3 -m pytest tests/ -k <pattern>   # run a subset
sklm --version                      # check installed version
```

### Troubleshooting

**"No Sklm workspace found"**
Run `sklm init` first. It creates the `.sklm/` directory and configures your agent.

**"No agent configured — not synced"**
The skill is installed and linked, but no agent is set up to receive it. Run `sklm init --agent <name>`.

**"Broken symlinks"**
Run `sklm status --repair` to re-create links that point to missing targets.

**"Skill not found in git repo"**
Some repos use non-standard layouts. Use `--subdir` to point to the exact directory:
```bash
sklm add skill my-skill --from https://github.com/user/repo --subdir custom/path
```

**"GitHub Copilot isn't detected"**
That's expected. Copilot requires explicit setup: `sklm init --agent github-copilot`.

**"`sklm registry add` fails"**
For git registries, make sure `git` is installed and the URL is accessible. For local paths, use an absolute or `~`-expanded path.
