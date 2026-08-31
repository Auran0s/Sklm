# AGENTS.md — Skim

## Setup & dev commands

```bash
uv tool install skim              # install from PyPI
uv sync                           # create venv + install project + dev deps
uv run python -m pytest tests/    # run all tests (single file: tests/test_skim.py)
uv run python -m pytest tests/ -k <pattern>  # run a subset
```

No CI, no linting, no typechecking. Single test file, no `tests/__init__.py`.

## Entrypoint

- CLI: `skim.cli.main:run` (Typer app, `no_args_is_help=True`).
- Declared in `pyproject.toml` under `[project.scripts]`.
- Version derived from `importlib.metadata.version("skim")` in `skim/__init__.py`.

## Architecture

Two-level store:

```
~/.skim/                   # global store (~/.skim/ or $SKIM_HOME)
  store/skills/            #   installed skill dirs (each has SKILL.md)
  config.yaml              #   GlobalConfig — resource catalog
  registries.yaml          #   RegistrySource entries
  cache/                   #   shallow-cloned git repos for install --from

./.skim/                   # per-project workspace (gitignored)
  links/skills/            #   symlinks → ~/.skim/store/skills/
  skim.yaml                #   WorkspaceConfig (agents, resources, links)
```

`skim add` pipeline: resolve → store → link → sync (copy + variant overlay) to agent config.

Note: `.skim/` is in `.gitignore` — the per-project workspace is intentionally never committed.

## Source layout

| Path | Role |
|---|---|
| `skim/api.py` | `Skim` facade — wires everything |
| `skim/cli/main.py` | Typer CLI — all commands |
| `skim/cli/wizard.py` | Interactive prompt and state detection |
| `skim/models/__init__.py` | Pydantic v2 models, YAML persistence |
| `skim/store/__init__.py` | `GlobalStore` — `~/.skim/` management |
| `skim/core/workspace.py` | `Workspace` — `.skim/` management |
| `skim/core/registry.py` | `RegistryManager` — clone/fetch, search |
| `skim/core/crud.py` | Resource CRUD (resolve → store → link) |
| `skim/core/linking.py` | Symlink create/remove/repair |
| `skim/core/update.py` | `UpdateChecker` — GitHub API version check |
| `skim/agents/agents.yaml` | **Source of truth** — 30 agent definitions (dir_name, detect mode) |
| `skim/agents/base.py` | Abstract `AgentAdapter` — base class for all adapters |
| `skim/agents/_sync.py` | Shared sync logic with `variants/<agent>/` overlay |
| `skim/agents/generic.py` | `GenericAdapter` — handles 28 auto-detect agents |
| `skim/agents/github_copilot.py` | `GitHubCopilotAdapter` — custom (detect: explicit) |
| `skim/agents/registry.py` | `AgentRegistry` — discovery + adapter lookup |

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
- Editable install optional (`uv sync`) — the update mechanism runs `pip install -U skim`.

## Agent config (agents.yaml)

30 agents defined in `skim/agents/agents.yaml`. Each has `dir_name` (config directory). Two agents have `detect: explicit` (not auto-detected): **github-copilot** (`.github/`) and **antigravity** (`.agent/`). All others auto-detect by checking for their config directory.

## Testing quirks

- Fixtures: `temp_dir` (TemporaryDirectory + chdir), `isolated_store` (monkeypatches `SKIM_HOME`), `fake_skill_dir` (creates `my-skill/SKILL.md`).
- CLI tests use `typer.testing.CliRunner` with `monkeypatch` for isolation.
- Every CLI integration test fixture patches `skim.store.SKIM_HOME`, `skim.core.registry.REGISTRIES_PATH`, `skim.core.registry.REGISTRY_CACHE`, and resets `skim.cli.main._skim`.
- `monkeypatch.setattr("skim.__version__", "0.1.0")` required in update tests.
- `isolated_store` fixture patches `skim.store.SKIM_HOME` via `monkeypatch.setattr`.

## Telemetry

Removed in this fork.

## Git workflow

This repo uses `opencode.jsonc` with a build prompt that repeats these rules. The authoritative version is below:

1. Check `git status` before any edit — if uncommitted changes exist, ask the user first.
2. Create a feature branch: `git checkout -b agent/<short-description>`.
3. Never edit code on `main` or `master`.
4. Run `uv run python -m pytest tests/` before committing.
5. Commit with a clear message prefix: `feat:`, `fix:`, `refactor:`.
6. Push the branch when done.
