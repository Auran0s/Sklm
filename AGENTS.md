# AGENTS.md — Fabrik

## Setup & dev commands

```bash
pip install -e .              # editable install (required before any work)
pip install -r requirements.txt  # includes pytest + pytest-cov
python3 -m pytest tests/      # run all tests (single file: tests/test_fabrik.py)
python3 -m pytest tests/ -k <pattern>  # run a subset
```

No linting or typechecking tools are configured yet.

## Architecture

Fabrik is a Python CLI (Typer + Rich) that manages skills and MCPs for AI agents via a two-level store:

```
~/.fabrik/          # global store (user-wide library)
  store/skills/     #   skill directories (each contains a SKILL.md)
  store/mcps/       #   MCP dirs (each contains a config.yaml or config.json)

./.fabrik/          # per-project workspace
  links/skills/     #   symlinks → global store
  links/mcps/       #   symlinks → global store
```

- `fabrik add` does everything: resolve → store → link → sync to agent config.
- Agent sync copies (not symlinks) skill/MCP content into the agent's config dir (e.g. `.opencode/skills/`, `.opencode/mcps/`).
- `.fabrik/` and `.opencode/` are **gitignored** — they are generated/derived, never committed.

### Source layout

| Path | Role |
|---|---|
| `fabrik/api.py` | `Fabrik` facade — wires everything together |
| `fabrik/cli/main.py` | Typer CLI app — all commands |
| `fabrik/models/` | Pydantic v2 models (YAML persistence) |
| `fabrik/store/` | `GlobalStore` — `~/.fabrik/` management |
| `fabrik/core/workspace.py` | `Workspace` — `.fabrik/` management |
| `fabrik/core/registry.py` | `RegistryManager` — registry discovery |
| `fabrik/core/crud.py` | CRUD operations |
| `fabrik/core/linking.py` | Symlink create/remove/repair |
| `fabrik/agents/` | Agent adapters (only `OpencodeAdapter` so far) |
| `fabrik/telemetry.py` | `UmamiTracker` — telemetry |

## Conventions

- **Every `.py` file** starts with `from __future__ import annotations`.
- **Resource names** must be **kebab-case** (enforced by Pydantic validator).
- **No spaces** in registry names.
- Persistence format is **YAML** everywhere (`yaml.safe_load` / `yaml.dump`).
- All `Path` arguments are `.resolve()`d eagerly.
- CLI output uses **Rich** (tables, `print_json`, `Console`); use `--json` for machine-readable output.

## OpenSpec workflow

The project uses **OpenSpec** for spec-driven development:
- Specs live in `openspec/specs/` (7 capabilities).
- Active changes in `openspec/changes/`.
- Slash commands available via `.opencode/commands/`: `/opsx-propose`, `/opsx-explore`, `/opsx-apply`, `/opsx-sync`, `/opsx-archive`.

## Testing

- Single test file: `tests/test_fabrik.py`
- Uses `pytest` fixtures (`temp_dir`, `isolated_store`, `fake_skill_dir`, `fake_mcp_dir`).
- CLI integration tests use `typer.testing.CliRunner`.
- Global store tests patch `FABRIK_HOME` via `monkeypatch`.

## Telemetry

- Powered by Umami Analytics.
- Disable with `FABRIK_TELEMETRY=0` (or `false`/`no`/`off`).
- Tracker runs in a daemon thread with 2s timeout — never raises, never blocks.
