# AGENTS.md — Sklm

## Setup & dev commands

```bash
pip install sklm-cli                  # install from PyPI
pip install -e .                  # editable install (development)
pip install -r requirements.txt   # pytest + pytest-cov
python3 -m pytest tests/          # run all tests (single file: tests/test_sklm.py)
python3 -m pytest tests/ -k <pattern>  # run a subset
```

No CI, no linting, no typechecking. Single test file, no `tests/__init__.py`.

## Entrypoint

- CLI: `sklm.cli.main:run` (Typer app, `no_args_is_help=True`).
- Declared in `pyproject.toml` under `[project.scripts]`.
- Version derived from `importlib.metadata.version("sklm")` in `sklm/__init__.py`.

## Architecture

Two-level store:

```
~/.sklm/                   # global store (~/.sklm/ or $SKLM_HOME)
  store/skills/            #   installed skill dirs (each has SKILL.md)
  config.yaml              #   GlobalConfig — resource catalog + telemetry
  registries.yaml          #   RegistrySource entries
  cache/                   #   shallow-cloned git repos for git-fallback sources

./.sklm/                   # per-project workspace (gitignored)
  links/skills/            #   symlinks → ~/.sklm/store/skills/
  sklm.yaml                #   WorkspaceConfig (agents, resources, links)
```

`sklm add` pipeline: parse source → discover skills → fetch → store → link → sync (copy + variant overlay) to agent config.

A source is parsed by `sklm/core/sources.py`, fetched by `sklm/core/fetch.py`
(HTTP for public GitHub, `git clone` otherwise), and searched for skills by
`sklm/core/discovery.py`. Public GitHub sources need no `git` binary; the git
fallback checks for `git` up front and raises an actionable error when missing.

Note: `.sklm/` is in `.gitignore` — the per-project workspace is intentionally never committed.

## Source layout

| Path | Role |
|---|---|
| `sklm/api.py` | `Sklm` facade — wires everything; `resolve_source`/`install_source`/`add_source` |
| `sklm/cli/main.py` | Typer CLI — all commands |
| `sklm/cli/wizard.py` | Interactive prompt and state detection |
| `sklm/models/__init__.py` | Pydantic v2 models, YAML persistence |
| `sklm/store/__init__.py` | `GlobalStore` — `~/.sklm/` management, `add_resource_from_source` |
| `sklm/core/sources.py` | `parse_source` — source grammar (`owner/repo`, URLs, tree paths, local paths) |
| `sklm/core/fetch.py` | `SourceFiles`, `HttpGithubSource`, `DiskSource`, `resolve_source`, git precondition |
| `sklm/core/discovery.py` | `discover_skills` — containers, depth, shadowing, frontmatter, selection |
| `sklm/core/workspace.py` | `Workspace` — `.sklm/` management |
| `sklm/core/registry.py` | `RegistryManager` — clone/fetch, search |
| `sklm/core/crud.py` | Resource CRUD (resolve → store → link) |
| `sklm/core/linking.py` | Symlink create/remove/repair |
| `sklm/core/update.py` | `UpdateChecker` — GitHub API version check |
| `sklm/agents/agents.yaml` | **Source of truth** — 30 agent definitions (dir_name, detect mode) |
| `sklm/agents/base.py` | Abstract `AgentAdapter` — base class for all adapters |
| `sklm/agents/_sync.py` | Shared sync logic with `variants/<agent>/` overlay |
| `sklm/agents/generic.py` | `GenericAdapter` — handles 28 auto-detect agents |
| `sklm/agents/github_copilot.py` | `GitHubCopilotAdapter` — custom (detect: explicit) |
| `sklm/agents/registry.py` | `AgentRegistry` — discovery + adapter lookup |
| `sklm/telemetry.py` | `UmamiTracker` — daemon thread, 2s timeout |

## Conventions

- **Every `.py` file** starts with `from __future__ import annotations`.
- **Resource names** must be **kebab-case** (Pydantic validator on `Resource.name`).
- **No spaces** in registry names (Pydantic validator on `RegistrySource.name`).
- Persistence: **YAML** everywhere (`yaml.safe_load` / `yaml.dump`).
- All `Path` args are `.resolve()`d eagerly.
- CLI output: **Rich** tables; `--json` flag for machine-readable output.
- Only `skill` resource kind exists — `ResourceKind` enum has a single value.
- `add`/`install` take a **source or a stored name** as their only positional. A value matching `looks_like_source()` (`owner/repo`, a URL, an SSH prefix, or a path) is a source; anything else is a resource name.
- The literal token `skill` is **reserved**: `add`, `install`, `rm`, `uninstall`, and `migrate` reject it with a migration error. The resource-type positional was removed in 0.3.0.
- `--skill` selects skills within a source (repeatable); `--all` installs every discovered skill; `--list` prints them and installs nothing. With none of them, an interactive multi-select is shown, and a non-TTY run fails with guidance.
- `--from URL` is retained as an alias for a source positional; `--subdir PATH` restricts discovery within a source.
- `link`/`unlink` are **internal API only** (no CLI commands). Use `add`/`rm`.
- Linking prefers a symlink and falls back to a **directory copy** when the platform refuses symlinks (Windows without Developer Mode, `WinError 1314`). Agent sync always reads `link.target` (the store), so a copied entry is never the source of truth. `detect_broken_links` checks the store target as well as the workspace entry.
- Agent sync **copies** (not symlinks) content with variant overlay from `variants/<agent-id>/`.
- Editable install optional (`pip install -e .`) — the update mechanism runs `pip install -U sklm-cli`.

## Agent config (agents.yaml)

30 agents defined in `sklm/agents/agents.yaml`. Each has `dir_name` (config directory). Two agents have `detect: explicit` (not auto-detected): **github-copilot** (`.github/`) and **antigravity** (`.agent/`). All others auto-detect by checking for their config directory.

## Testing quirks

- Fixtures: `temp_dir` (TemporaryDirectory + chdir), `isolated_store` (monkeypatches `SKLM_HOME`), `fake_skill_dir` (creates `my-skill/SKILL.md`).
- CLI tests use `typer.testing.CliRunner` with `monkeypatch` for isolation.
- Every CLI integration test fixture patches `sklm.store.SKLM_HOME`, `sklm.core.registry.REGISTRIES_PATH`, `sklm.core.registry.REGISTRY_CACHE`, and resets `sklm.cli.main._sklm`.
- `monkeypatch.setattr("sklm.__version__", "0.1.0")` required in update tests.
- `isolated_store` fixture patches `sklm.store.SKLM_HOME` via `monkeypatch.setattr`.

## Telemetry

- Umami Analytics. Default endpoint: `https://analytics.victorbeysseriat.fr`.
- Disable: `SKLM_TELEMETRY=0` env var (also `false`/`no`/`off`/`""`).
- Override URL/ID: `SKLM_UMAMI_URL`, `SKLM_WEBSITE_ID` env vars.
- Runs in a daemon thread with 2s join timeout — never raises, never blocks.

## Git workflow

This repo uses `opencode.jsonc` with a build prompt that repeats these rules. The authoritative version is below:

1. Check `git status` before any edit — if uncommitted changes exist, ask the user first.
2. Create a feature branch: `git checkout -b agent/<short-description>`.
3. Never edit code on `main` or `master`.
4. Run `python3 -m pytest tests/` before committing.
5. Commit with a clear message prefix: `feat:`, `fix:`, `refactor:`.
6. Push the branch when done.
