# AGENTS.md — Sklm

## Setup & dev commands

```bash
pip install -e .              # editable install (required before any work)
pip install -r requirements.txt  # includes pytest + pytest-cov
python3 -m pytest tests/      # run all tests (single file: tests/test_sklm.py)
python3 -m pytest tests/ -k <pattern>  # run a subset
```

No linting or typechecking tools are configured. No CI.

## Architecture

Sklm is a Python 3.9+ CLI (Typer + Rich) that manages skills for AI agents via a two-level store:

```
~/.sklm/            # global store (user-wide library)
  store/skills/     #   skill directories (each contains a SKILL.md)

./.sklm/            # per-project workspace (gitignored)
  links/skills/     #   symlinks → global store
  sklm.yaml         #   WorkspaceConfig per project
```

- `_type_dir(kind)` in `GlobalStore` always returns `skills_dir` — the `kind` parameter is ignored (only `skill` exists).
- `sklm add` pipeline: resolve → store → link → sync to agent config.
- Agent sync **copies** (not symlinks) skill content into the agent's config dir (e.g. `.opencode/skills/`).
- Entrypoint: `sklm.cli.main:run` (Typer app, `no_args_is_help=True`).

### Source layout

| Path | Role |
|---|---|
| `sklm/api.py` | `Sklm` facade — wires everything together |
| `sklm/cli/main.py` | Typer CLI app — all commands |
| `sklm/models/` | Pydantic v2 models (YAML persistence) |
| `sklm/store/` | `GlobalStore` — `~/.sklm/` management |
| `sklm/core/workspace.py` | `Workspace` — `.sklm/` management |
| `sklm/core/registry.py` | `RegistryManager` — registry discovery |
| `sklm/core/crud.py` | CRUD operations |
| `sklm/core/linking.py` | Symlink create/remove/repair |
| `sklm/core/update.py` | `UpdateChecker` — version check and self-update |
| `sklm/agents/` | 8 agents in `agents.yaml`; `GenericAdapter` handles 7, `GitHubCopilotAdapter` is custom |
| `sklm/telemetry.py` | `UmamiTracker` — telemetry |

## Conventions

- **Every `.py` file** starts with `from __future__ import annotations`.
- **Resource names** must be **kebab-case** (enforced by Pydantic validator).
- **No spaces** in registry names.
- Persistence is **YAML** everywhere (`yaml.safe_load` / `yaml.dump`).
- All `Path` arguments are `.resolve()`d eagerly.
- CLI output uses **Rich** (tables, `print_json`, `Console`); use `--json` for machine-readable output.
- Only `skill` resource kind exists — the `ResourceKind` enum has a single value.
- `link`/`unlink` are **internal API only** (not CLI commands). Use `add`/`rm`.
- `install --from` resolves skill dirs in this order: `skills/<name>` → repo root (if `SKILL.md` present) → `<name>` subdir → recursive walk of `skills/` for `<name>/SKILL.md`.
- `SKLM_HOME` overrides the global store root (`~/.sklm/` by default); tests patch `sklm.store.SKLM_HOME`.

## Testing

- Single test file: `tests/test_sklm.py` (no `__init__.py`).
- Uses `pytest` fixtures (`temp_dir`, `isolated_store`, `fake_skill_dir`).
- CLI integration tests use `typer.testing.CliRunner`.
- Global store tests patch `SKLM_HOME` via `monkeypatch`.

## Telemetry

- Umami Analytics; disable with `SKLM_TELEMETRY=0` (or `false`/`no`/`off`/`""`).
- Also overridable via `SKLM_UMAMI_URL`, `SKLM_WEBSITE_ID`.
- Tracker runs in a daemon thread with 2s timeout — never raises, never blocks.
