# Version domains & release manifest — design exploration

Status: **draft / exploration**. Nothing here is implemented or scheduled; this file
exists to think through a possible direction before any code is written.

## Motivation

Real precedent: in the Macromer setup the `dcp` deploy layer pins a concrete milkcow
image version (`milkcow_image_version`), and every milkcow release needs a matching
manual bump on the deploy side. That is exactly the coordination pain this exploration
targets: several components, each versioned on its own, that must periodically agree
on one consistent release state.

(From an external review of the project: "AVH could manage the version consistency of
a software product as a whole, independently of how the source code is organized.")

## Concepts

- **Version domain** — an independent version scope inside (or across) a repository:
  its own master file, its own parse rules, its own promotion graph. The shipped
  single-domain model would generalize to N domains.
- **Release manifest** — a frozen document naming the exact set of component versions
  that constitute one release (`frontend: 2.4.0 + backend: 3.7.1 + ...`). It answers:
  what ships, who created it, when it becomes immutable, which repositories bind to it.
- **Version propagation** — dependency rules: a change to component A raises the
  version of components that depend on it. Explicitly the most dangerous concept:
  one step away from a dependency management system.
- **Multirepo** — components living in different repositories, bound by the manifest.

## Relationship to what ships today

`version_files` is **not** a domain mechanism: it mirrors ONE master version into many
surfaces. Domains require N masters, each with its own file/key/parse_regex and its
own promotion rules — a generalization of the `version:` section, not of the mirrors.

## Deliberate caution

The hook's value is its narrowness. The manifest layer should not grow inside the
hook core: it is a separate concern (release coordination/reporting) and a separate
design effort. The first deliverable of any real work here is a written manifest
contract: what it describes, who creates it, when it becomes immutable, how
repositories bind to it.

## Open questions

- Manifest contract: format, ownership, immutability point, repo binding mechanics.
- Domains: how do branch classes map to domains? One promotion graph per domain?
- Propagation: declarative `depends_on` + bump rules, or purely informative?
- Where does it live: inside AVH core, a companion tool, or a jear integration?
- Is there a second real consumer besides the milkcow/dcp pinning case?

## Decision

Deferred. Do not start without a concrete two-component product that hurts.
