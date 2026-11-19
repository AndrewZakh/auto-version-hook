# Changelog

All notable changes are documented here. Format: Keep a Changelog; the version
scheme is the flow model — one increment per merged feature, majors by explicit
decision.

The project was first published on GitHub on 2026-11-06 (English docs, MIT license,
GitHub Actions CI, Python 3.11+); `v0.2.0` is the first tagged release on top of
that publication.

## [1.7.0] — 2026-11-19

### Added
- Bootstrap skip: while the repository has no configured origin or no branches on
  it yet, the hook skips cleanly with a clear message instead of failing the first
  local commits with a network error.

## [1.5.0] — 2026-11-19

### Added
- `--json`: the hook result as machine-readable JSON on stdout (action, branch,
  class, policy, target, versions, mirrors) — for CI gates and integrations. Pairs
  with `--check`/`--dry-run`; exit codes unchanged.

## [1.4.0] — 2026-11-19

### Added
- The development task board and sprint plan (`.jearless/`) — dogfooding the
  jearless tracker on the project's own releases.
- `docs/version-domains.md`: exploration draft for version domains and release
  manifests (deferred direction).
- README philosophy section: transparency, semver by construction, branching-model
  support, defense in depth.

## [1.3.0] — 2026-11-19

### Added
- CHANGELOG.md (this file) + GitHub Releases published automatically on every
  version tag.

## [1.2.0] — 2026-11-19

### Added
- Overversion guard: the hook warns when the version is changed by hand on a
  protected branch — a typo becomes visible instead of silently accepted.
- Release gap-guard: the release workflow refuses to tag versions that skip more
  than one increment or go backwards; intentional jumps dispatch it with `force: true`.

## [1.1.0] — 2026-11-17

### Added
- `version_files` — mirrors of the master version: the hook splices the computed
  version's named groups into additional files, so `pyproject.toml` (and Cargo/npm
  manifests, when configured) move together with the flow version.

### Fixed
- `pyproject.toml` no longer drifts: it carried `0.1.0` since day one while the flow
  version was already at `v1.1.0`.

## [1.0.0] — 2026-11-06

### Changed — BREAKING
- The default `branch_flow` is **trunk-based**: no `staging` class, `feature`
  targets `main`, and `tech` covers `devops|tech|docs` branches. GitFlow teams add
  a `staging` class — see README, "Two Git workflows out of the box".

## [0.4.0] — 2026-11-06

### Added
- Remote pre-commit usage: `.pre-commit-hooks.yaml` and the three-line
  `repo: ... rev: latest` setup (the rolling `latest` tag).

## [0.3.0] — 2026-11-06

### Added
- The release-tag workflow: every merge to main tags the `env.yml` version
  automatically — this changelog is driven by it.
- The owl logo (`assets/`).

## [0.2.0] — 2026-11-06

### Added
- `--check` validated in CI on every pull request — dogfooding the validator.
