# AGENTS.md — Sklm

## Setup & dev commands

```bash
pip install sklm                  # install from PyPI
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
  cache/                   #   shallow-cloned git repos for install --from

./.sklm/                   # per-project workspace (gitignored)
  links/skills/            #   symlinks → ~/.sklm/store/skills/
  sklm.yaml                #   WorkspaceConfig (agents, resources, links)
```

`sklm add` pipeline: resolve → store → link → sync (copy + variant overlay) to agent config.

Note: `.sklm/` is in `.gitignore` — the per-project workspace is intentionally never committed.

## Source layout

| Path | Role |
|---|---|
| `sklm/api.py` | `Sklm` facade — wires everything |
| `sklm/cli/main.py` | Typer CLI — all commands |
| `sklm/cli/wizard.py` | Interactive prompt and state detection |
| `sklm/models/__init__.py` | Pydantic v2 models, YAML persistence |
| `sklm/store/__init__.py` | `GlobalStore` — `~/.sklm/` management |
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
- `link`/`unlink` are **internal API only** (no CLI commands). Use `add`/`rm`.
- Agent sync **copies** (not symlinks) content with variant overlay from `variants/<agent-id>/`.
- Editable install optional (`pip install -e .`) — the update mechanism runs `pip install -U sklm`.

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
