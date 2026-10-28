"""Configuration: dataclasses, YAML loading, validation (v2, branch_flow).

The config file is optional: defaults implement the conventions from
docs/branch-flow-design.md — v1.2.3 versions, and the branch_flow with
main/staging/patch/feature/tech classes.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field, fields
from pathlib import Path
from typing import List, Optional

import yaml

from .flow import (
    IGNORE,
    INCREMENT,
    KEEP,
    POLICIES,
    BranchClass,
    find_class,
)
from .versions import VersionError, VersionSpec
from .yamlpath import PathError, parse_path

log = logging.getLogger("auto_version_hook")

CONFIG_ENV_VAR = "AUTO_VERSION_HOOK_CONFIG"
CONFIG_CANDIDATES = ("version-hook.yml", "version-hook.yaml", ".version-hook.yml", ".version-hook.yaml")
DESIGN_DOC = "docs/branch-flow-design.md"
_VALID_ON_ERROR = {"fail", "warn"}
_LEGACY_TOP_LEVEL = ("bump",)
_LEGACY_MESSAGE = (
    "v1 options are no longer supported ({options}); the config is v2 now: "
    "branch_flow replaces protected_branch/bump.rules/ignore_branches_regex, "
    f"see {DESIGN_DOC}"
)


class ConfigError(ValueError):
    """Raised on an invalid or missing configuration file."""


DEFAULT_PARSE_REGEX = r"^v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$"


def _default_flow() -> List[BranchClass]:
    return [
        BranchClass(name="main", regex=r"^(master|main)$", protected=True, policy=KEEP),
        BranchClass(
            name="staging",
            regex=r"^(dev(elop(ment)?)?|stag(ing)?)$",
            protected=True,
            target="main",
            policy=KEEP,
        ),
        BranchClass(name="patch", regex=r"^patch", target="main", policy=INCREMENT, bump="patch"),
        BranchClass(
            name="feature", regex=r"^feat(ure)?", target="staging", policy=INCREMENT, bump="minor"
        ),
        BranchClass(name="tech", regex=r"^devops/tech.+", target="staging", policy=IGNORE),
    ]


@dataclass
class VersionConfig:
    file: str = "env.yml"
    # yq-style path: app.build.version, items[0].version, labels."app.version"
    key: str = "version"
    # Decomposes the version string into named groups (whole string must
    # match). Bumpable parts are the groups named in branch_flow bump fields.
    parse_regex: str = DEFAULT_PARSE_REGEX


@dataclass
class GitConfig:
    remote: str = "origin"
    fetch: bool = True


@dataclass
class HookSettings:
    auto_stage: bool = True
    on_error: str = "fail"
    skip_merges: bool = True  # do not act on merge commits (MERGE_HEAD present)


@dataclass
class AppConfig:
    version: VersionConfig = field(default_factory=VersionConfig)
    git: GitConfig = field(default_factory=GitConfig)
    branch_flow: List[BranchClass] = field(default_factory=_default_flow)
    hooks: HookSettings = field(default_factory=HookSettings)
    source: Optional[Path] = None


def find_config(explicit: Optional[str], repo_root: Path) -> Optional[Path]:
    """Locate the config file: --config flag, then $AUTO_VERSION_HOOK_CONFIG,
    then the well-known names in the repository root. None means "defaults"."""
    explicit_or_env = explicit or os.environ.get(CONFIG_ENV_VAR)
    if explicit_or_env:
        path = Path(explicit_or_env)
        if not path.is_file():
            raise ConfigError(f"config file not found: {path}")
        return path
    for name in CONFIG_CANDIDATES:
        path = repo_root / name
        if path.is_file():
            return path
    return None


def load_config(explicit: Optional[str], repo_root: Path) -> AppConfig:
    path = find_config(explicit, repo_root)
    cfg = AppConfig()
    if path is None:
        _validate(cfg, None)
        return cfg

    try:
        raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"invalid YAML in {path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise ConfigError(f"config root must be a mapping: {path}")

    legacy = [option for option in _LEGACY_TOP_LEVEL if option in raw]
    if isinstance(raw.get("git"), dict) and "protected_branch" in raw["git"]:
        legacy.append("git.protected_branch")
    if legacy:
        raise ConfigError(f"{path}: " + _LEGACY_MESSAGE.format(options=", ".join(legacy)))

    _load_section(cfg.version, "version", raw, path)
    _load_section(cfg.git, "git", raw, path)
    _load_section(cfg.hooks, "hooks", raw, path)
    _load_flow(cfg, raw, path)

    unknown = set(raw) - {"version", "git", "branch_flow", "hooks"}
    if unknown:
        raise ConfigError(f"{path}: unknown section(s): {', '.join(sorted(unknown))}")

    _validate(cfg, path)
    cfg.source = path
    return cfg


def _load_section(target: object, name: str, raw: dict, path: Path) -> None:
    section = raw.get(name)
    if section is None:
        return
    if not isinstance(section, dict):
        raise ConfigError(f"{path}: section '{name}' must be a mapping")
    known = {f.name for f in fields(target)}  # type: ignore[arg-type]
    for key, value in section.items():
        if key not in known:
            raise ConfigError(f"{path}: unknown option '{name}.{key}'")
        setattr(target, key, value)


def _load_flow(cfg: AppConfig, raw: dict, path: Path) -> None:
    flow_raw = raw.get("branch_flow")
    if flow_raw is None:
        return
    if not isinstance(flow_raw, list) or not flow_raw:
        raise ConfigError(f"{path}: branch_flow must be a non-empty list")
    classes: List[BranchClass] = []
    known = {f.name for f in fields(BranchClass)}
    for index, item in enumerate(flow_raw):
        if not isinstance(item, dict):
            raise ConfigError(f"{path}: branch_flow[{index}] must be a mapping")
        unknown = set(item) - known
        if unknown:
            raise ConfigError(
                f"{path}: branch_flow[{index}]: unknown option(s): {', '.join(sorted(unknown))}"
            )
        classes.append(BranchClass(**item))
    cfg.branch_flow = classes


def _validate(cfg: AppConfig, path: Optional[Path]) -> None:
    where = str(path) if path else "defaults"

    _require_non_empty_str(cfg.version.file, "version.file", where)
    try:
        spec = VersionSpec(cfg.version.parse_regex)
    except VersionError as exc:
        raise ConfigError(f"{where}: version.parse_regex: {exc}") from exc
    try:
        parse_path(cfg.version.key)
    except PathError as exc:
        raise ConfigError(f"{where}: version.key: {exc}") from exc

    _require_non_empty_str(cfg.git.remote, "git.remote", where)
    _require_bool(cfg.git.fetch, "git.fetch", where)

    _require_bool(cfg.hooks.auto_stage, "hooks.auto_stage", where)
    if cfg.hooks.on_error not in _VALID_ON_ERROR:
        raise ConfigError(f"{where}: hooks.on_error must be one of {sorted(_VALID_ON_ERROR)}")
    _require_bool(cfg.hooks.skip_merges, "hooks.skip_merges", where)

    _validate_flow(cfg.branch_flow, spec, where)


def _validate_flow(flow: List[BranchClass], spec: VersionSpec, where: str) -> None:
    if not flow:
        raise ConfigError(f"{where}: branch_flow must not be empty")

    names = [cls.name for cls in flow]
    for name in names:
        if not isinstance(name, str) or not name:
            raise ConfigError(f"{where}: branch_flow class names must be non-empty strings")
    duplicates = sorted({name for name in names if names.count(name) > 1})
    if duplicates:
        raise ConfigError(f"{where}: duplicate branch_flow class names: {', '.join(duplicates)}")

    group_names = set(spec.group_names)
    for cls in flow:
        _require_regex(cls.regex, f"branch_flow[{cls.name}].regex", where)
        if cls.policy not in POLICIES:
            raise ConfigError(
                f"{where}: branch_flow[{cls.name}].policy must be one of {list(POLICIES)}, got {cls.policy!r}"
            )
        _require_bool(cls.protected, f"branch_flow[{cls.name}].protected", where)
        _require_bool(cls.reset_lower_parts, f"branch_flow[{cls.name}].reset_lower_parts", where)
        if cls.target is not None and cls.target not in names:
            raise ConfigError(
                f"{where}: branch_flow[{cls.name}].target {cls.target!r} is not a class name"
            )
        if cls.protected:
            if cls.policy != KEEP:
                raise ConfigError(
                    f"{where}: branch_flow[{cls.name}]: protected classes must use policy 'keep'"
                )
            if cls.bump is not None:
                raise ConfigError(
                    f"{where}: branch_flow[{cls.name}]: protected classes must not have bump"
                )
        else:
            if cls.target is None:
                raise ConfigError(
                    f"{where}: branch_flow[{cls.name}]: non-protected classes need a target"
                )
            if cls.policy not in (INCREMENT, IGNORE):
                raise ConfigError(
                    f"{where}: branch_flow[{cls.name}]: non-protected classes must use "
                    f"'increment' or 'ignore'"
                )
        if cls.policy == INCREMENT:
            if not isinstance(cls.bump, str) or not cls.bump:
                raise ConfigError(
                    f"{where}: branch_flow[{cls.name}]: policy 'increment' needs a bump group"
                )
            if cls.bump not in group_names:
                raise ConfigError(
                    f"{where}: branch_flow[{cls.name}].bump {cls.bump!r}: "
                    f"version.parse_regex has no group named {cls.bump!r}"
                )

    for cls in flow:
        walked = [cls.name]
        current = cls
        while current.target:
            nxt = find_class(current.target, flow)
            if nxt is None:
                break  # already reported above
            if nxt.name in walked:
                raise ConfigError(
                    f"{where}: branch_flow has a cycle: {' -> '.join(walked + [nxt.name])}"
                )
            walked.append(nxt.name)
            current = nxt

    for i, earlier in enumerate(flow):
        for later in flow[i + 1:]:
            if earlier.matches(later.name):
                log.warning(
                    "config: class %r regex may capture branches meant for later class %r "
                    "(matching is order-dependent)",
                    earlier.name,
                    later.name,
                )

    for cls in flow:
        if not _is_branchlike(cls.name):
            log.warning(
                "config: class name %r does not look like a valid git branch name; "
                "exact remote-branch resolution (origin/%s) will never match it",
                cls.name,
                cls.name,
            )


_BRANCH_NAME_GUARD = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._/-]*$")


def _is_branchlike(name: str) -> bool:
    """Close enough to git branch-name rules for the exact-resolution hint."""
    return bool(
        _BRANCH_NAME_GUARD.match(name)
        and ".." not in name
        and not name.endswith(("/", ".", ".lock"))
    )


def _require_non_empty_str(value: object, option: str, where: str) -> None:
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{where}: {option} must be a non-empty string")


def _require_bool(value: object, option: str, where: str) -> None:
    if not isinstance(value, bool):
        raise ConfigError(f"{where}: {option} must be a boolean")


def _require_regex(value: object, option: str, where: str) -> None:
    if not isinstance(value, str) or not value:
        raise ConfigError(f"{where}: {option} must be a non-empty regex string")
    try:
        re.compile(value)
    except re.error as exc:
        raise ConfigError(f"{where}: {option}: {exc}") from exc
