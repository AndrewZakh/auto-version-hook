# Backlog

## Done

- [x] **pyproject version vs env.yml** — closed 2026-11-07 with the `version_files`
  section (v1.1.0): optional mirrors of the master version, each `{path, regex,
  replace_all}`. The hook splices the computed version's named groups into the first
  match (a warning is logged for more; `replace_all: true` syncs all), missing files are
  skipped, a no-match in an existing file fails the run, mirrors are absolute and covered
  by `--check`/`auto_stage`. Renaming `version:` into a list was considered and rejected
  as breaking; the name `greedy` lost to `replace_all`. This repo mirrors `pyproject.toml`
  via `.version-hook.yml`.

- [x] **branch_flow: target-class ambiguity** — closed 2026-10-24 with the "resolve by
  class name" decision (no new field): the target resolves in three steps — (1) a branch
  named exactly like the class (`origin/<name>`), (2) the class regex, exactly one match,
  (3) otherwise walk up the `target` chain. The escape hatch from ambiguity is naming the
  class after the branch you need; class names that don't look like valid branch names
  produce a warning at config load. An explicit `branch: <name>` field was considered
  originally — rejected as redundant.
