# Backlog

## Open

- [ ] **pyproject version vs env.yml.** Since dogfooding (2026-10-28) the flow version
  lives in `env.yml` and is bumped by the hook itself, while `pyproject.toml` carries the
  package version seen by pip. They are synced by hand at release time for now; revisit
  (a guard test or a dynamic build version) if the drift starts to hurt.

## Done

- [x] **branch_flow: target-class ambiguity** — closed 2026-10-24 with the "resolve by
  class name" decision (no new field): the target resolves in three steps — (1) a branch
  named exactly like the class (`origin/<name>`), (2) the class regex, exactly one match,
  (3) otherwise walk up the `target` chain. The escape hatch from ambiguity is naming the
  class after the branch you need; class names that don't look like valid branch names
  produce a warning at config load. An explicit `branch: <name>` field was considered
  originally — rejected as redundant.
