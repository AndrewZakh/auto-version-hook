"""The hook itself: resolve the branch class, take the base version from the
target branch, apply the class policy, write and stage the version.

Semantics (docs/branch-flow-design.md):
  * merge commits are skipped (hooks.skip_merges);
  * detached HEAD: nothing to do;
  * keep (protected): never bump; if the local version is below the target's,
    catch it up (this is how a hotfix propagated to main reaches staging);
  * increment: bump the class group on top of the target's version; written
    only when higher than the local one (idempotent, no downgrades);
  * ignore: force the target's version.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional, Tuple

from . import gittools
from .config import AppConfig
from .flow import INCREMENT, KEEP, BranchClass, chain_from, match_class, resolve_target
from .versions import RegexVersion, VersionError, VersionSpec
from .yamlfile import VersionFileError, read_key, write_key

log = logging.getLogger("auto_version_hook")


class HookError(RuntimeError):
    """Fatal hook problem: the version cannot be computed or written."""


@dataclass
class HookResult:
    branch: Optional[str] = None
    branch_class: Optional[str] = None
    target_branch: Optional[str] = None
    base: Optional[RegexVersion] = None
    version: Optional[RegexVersion] = None
    changed: bool = False
    dry_run: bool = False
    skipped: bool = False
    would_change: bool = False  # in dry-run/check mode: the file would be rewritten


def run_hook(
    cfg: AppConfig,
    repo: Path,
    branch: Optional[str] = None,
    dry_run: bool = False,
) -> HookResult:
    root = gittools.repo_root(repo)

    if cfg.hooks.skip_merges and gittools.is_merge_in_progress(root):
        log.debug("merge in progress and hooks.skip_merges=true: doing nothing")
        return HookResult(dry_run=dry_run, skipped=True)

    if branch is None:
        branch = gittools.current_branch(root)
    if branch is None:
        log.info("auto-version-hook: detached HEAD, nothing to do")
        return HookResult(dry_run=dry_run, skipped=True)

    try:
        spec = VersionSpec(cfg.version.parse_regex)
    except VersionError as exc:
        raise HookError(str(exc)) from exc

    cls = match_class(branch, cfg.branch_flow)
    if cls is None:
        names = ", ".join(c.name for c in cfg.branch_flow)
        raise HookError(f"branch name {branch!r} is invalid: it matches no branch_flow class ({names})")
    log.debug("branch %r -> class %r (policy %s)", branch, cls.name, cls.policy)

    target_branch: Optional[str] = None
    base: Optional[RegexVersion] = None
    if cls.target:
        target_branch, base = _resolve_base(root, cfg, spec, cls)

    vfile = root / cfg.version.file
    local_version: Optional[RegexVersion] = None
    if vfile.exists():
        try:
            local_version = _version_from_text(vfile.read_text(encoding="utf-8"), spec, cfg)
        except (VersionError, VersionFileError):
            local_version = None  # broken local value: policies overwrite it below

    new_version = _apply_policy(cls, branch, base, local_version)
    if new_version is None:
        return HookResult(branch, cls.name, target_branch, base, local_version, changed=False, dry_run=dry_run)

    old_label = str(local_version) if local_version is not None else "<none>"
    where = f"[{cls.name} -> {cfg.git.remote}/{target_branch}]" if target_branch else f"[{cls.name}]"
    log.info(
        "%sauto-version-hook: %s %s: %s -> %s in %s",
        "[dry-run] " if dry_run else "",
        branch,
        where,
        old_label,
        new_version,
        cfg.version.file,
    )
    if dry_run:
        return HookResult(branch, cls.name, target_branch, base, new_version, changed=False, dry_run=True, would_change=True)

    text = vfile.read_text(encoding="utf-8") if vfile.exists() else ""
    try:
        new_text = write_key(text, cfg.version.key, str(new_version))
    except VersionFileError as exc:
        raise HookError(f"cannot update {cfg.version.key!r} in {cfg.version.file}: {exc}") from exc
    vfile.parent.mkdir(parents=True, exist_ok=True)
    vfile.write_text(new_text, encoding="utf-8")
    if cfg.hooks.auto_stage:
        gittools.stage(root, cfg.version.file)
        log.debug("staged %s", cfg.version.file)
    return HookResult(branch, cls.name, target_branch, base, new_version, changed=True)


def _resolve_base(
    root: Path, cfg: AppConfig, spec: VersionSpec, cls: BranchClass
) -> Tuple[str, RegexVersion]:
    if cfg.git.fetch:
        heads = gittools.ls_remote_heads(root, cfg.git.remote)
    else:
        heads = gittools.remote_heads_local(root, cfg.git.remote)

    target_class, target_branch, ambiguous = resolve_target(cls, cfg.branch_flow, heads)
    if ambiguous:
        raise HookError(
            f"class {target_class.name!r} matches several remote branches: "
            f"{', '.join(ambiguous)}; resolution prefers a branch named exactly "
            f"like the class (origin/<name>) — rename the class or tighten the regex"
        )
    if target_branch is None:
        chain = " -> ".join(c.name for c in chain_from(cls, cfg.branch_flow))
        raise HookError(f"no remote branch matches {chain}: cannot determine the base for class {cls.name!r}")

    if cfg.git.fetch:
        gittools.fetch(root, cfg.git.remote, target_branch)
    ref = f"{cfg.git.remote}/{target_branch}"
    text = gittools.read_file_from_ref(root, ref, cfg.version.file)
    if text is None:
        raise HookError(f"{cfg.version.file} not found in {ref}: cannot determine the base version")
    try:
        base = _version_from_text(text, spec, cfg)
    except (VersionError, VersionFileError) as exc:
        raise HookError(f"cannot read {cfg.version.key!r} from {cfg.version.file} in {ref}: {exc}") from exc
    if base is None:
        raise HookError(f"path {cfg.version.key!r} not found in {cfg.version.file} in {ref}")
    return target_branch, base


def _apply_policy(
    cls: BranchClass, branch: str, base: Optional[RegexVersion], local: Optional[RegexVersion]
) -> Optional[RegexVersion]:
    """The version to write, or None when nothing should change."""
    if cls.policy == KEEP:
        if base is not None and (local is None or local.compare(base) < 0):
            return base  # quiet catch-up, e.g. a hotfix that reached main
        label = str(local) if local is not None else "no local version"
        log.info("auto-version-hook: %s: protected %s keeps %s", branch, cls.name, label)
        return None
    if cls.policy == INCREMENT:
        assert base is not None  # non-protected classes always have a target
        try:
            new_version = base.bump(cls.bump or "", reset_lower=cls.reset_lower_parts)
        except VersionError as exc:
            raise HookError(f"cannot bump {cls.bump!r} of class {cls.name!r} in {base}: {exc}") from exc
        if local is not None and new_version.compare(local) <= 0:
            log.info(
                "auto-version-hook: %s: version %s already >= computed %s, nothing to do",
                branch,
                local,
                new_version,
            )
            return None
        return new_version
    # IGNORE: force the target's version
    assert base is not None
    if local == base:
        return None
    return base


def _version_from_text(text: str, spec: VersionSpec, cfg: AppConfig) -> Optional[RegexVersion]:
    value = read_key(text, cfg.version.key)
    if value is None:
        return None
    return spec.parse(value)
