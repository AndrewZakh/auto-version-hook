# Contributing

Thanks for looking at auto-version-hook! This document covers the development loop
and the house rules.

## Development setup

```sh
python3 -m venv .venv && . .venv/bin/activate
pip install -e ".[dev]"
pytest            # integration-first: disposable git repositories, no mocks
ruff check src tests scripts
```

The test suite creates throwaway git repositories and drives the hook end to end —
same as production, minus the network.

## How this repository runs

- The pre-commit hook bumps the flow version in `env.yml` on every commit (one
  minor per merged feature; majors are an explicit hand decision on a protected
  branch).
- `pyproject.toml` mirrors the flow version via `version_files` — never bump it by
  hand.
- Merges to `main` are PR merges; the release-tag workflow tags the version, rolls
  the `latest` tag, and publishes a GitHub Release with notes.
- CHANGELOG.md follows [Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and
  is updated in the release PR.
- Docs-only changes go through `docs/...` branches (the `tech` class keeps the
  version untouched).
- The task board lives in `.jearless/tasks.yml` (jearless kanban); the sprint plan
  is `.jearless/plans/sprint_1.yml`. The charts refresh on merge via the
  sprint-artifacts workflow.

## Pull requests

- One task per branch; branch first (`feature/...` for code, `docs/...` for docs),
  CI green before review (ruff + the pytest matrix + `--check` on the PR).
- Keep PRs focused: one task, its tests, its docs.
- The changelog section for the release is part of the release PR.

## Where the version lives (topology)

- `env.yml` — the master version file, bumped by the hook on feature commits.
- `pyproject.toml` — a mirror (`version_files`), synced by the same hook run.
- git tag + GitHub Release — published by the release workflow from the merged
  `env.yml` version. The release badge reads the master file directly.
