# Changelog

## 0.3.0

Reworks how skills are installed. `add` and `install` now take a **source** and
discover the skills it contains, so public GitHub repositories install without a
`git` binary. Addresses issue #42.

### Breaking changes

The `skill` resource-type token was removed from every command. Invoking the old
form now prints a migration error instead of misparsing.

| Command | Before | After |
|---|---|---|
| `add` | `sklm add skill my-skill` | `sklm add my-skill` |
| `add` from a repo | `sklm add skill my-skill --from https://github.com/user/skills` | `sklm add user/skills --skill my-skill` |
| `install` | `sklm install skill find-skills --from https://github.com/vercel-labs/skills` | `sklm install find-skills --from https://github.com/vercel-labs/skills` |
| `rm` | `sklm rm skill my-skill` | `sklm rm my-skill` |
| `uninstall` | `sklm uninstall skill my-skill` | `sklm uninstall my-skill` |
| `migrate` | `sklm migrate skill my-skill` | `sklm migrate my-skill` |

### Added

- Source grammar: GitHub shorthand (`owner/repo`), GitHub URLs, direct paths
  (`…/tree/<ref>/<path>`), inline skill filters (`owner/repo@skill`), refs
  (`owner/repo#v2@skill`), local paths, and any git URL.
- `--skill NAME` (repeatable), `--all`, `--list`, and `--ref` on `add` and
  `install`.
- Skill discovery across the repository root, `skills/`, `.agents/skills/`, and
  `<agent-dir>/skills/` for every supported agent, up to three levels deep, with
  a shallower `SKILL.md` shadowing anything nested beneath it. Frontmatter is
  optional.
- Interactive multi-select when a source contains several skills and neither
  `--skill`, `--all`, nor `--list` is given.

### Changed

- Public GitHub sources are read over HTTPS (GitHub Trees API plus
  `raw.githubusercontent.com`), so no `git` executable is required. Private
  repositories, GitLab, Azure Repos, SSH URLs, and other git remotes still use
  `git clone`.
- `GITHUB_TOKEN` / `GH_TOKEN` are honoured for the GitHub API when set.
- `rm` and `uninstall` accept more than one skill name.
- `--from URL` remains available as an alias for a source positional.

### Fixed

- Installing from a git source no longer surfaces a raw operating-system error
  when `git` is missing. The failure names `git` and points at a public GitHub
  source instead (issue #42).
- A Windows path passed to `add` is no longer misread as a `registry:name`
  reference.
- `sklm add` no longer fails on Windows without Developer Mode. When the
  operating system refuses to create a symbolic link (`WinError 1314`), the
  skill is copied into `.sklm/links/skills/` instead, so the add completes and
  syncs to the agent.
- Re-adding a skill that was recorded but never linked now repairs it instead of
  failing with an "already exists in workspace" error.
- A link whose stored skill has been deleted is reported as broken again, even
  when the workspace entry is a copy.
