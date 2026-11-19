"""Command-line interface.

Exit codes: 0 - ok (version written or already correct, or a tolerated warn),
1 - hook error that blocks the commit (hooks.on_error=fail), 2 - usage/config
errors (bad arguments, not a git repository, broken config).
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path
from typing import Optional, Sequence

from . import gittools
from .config import AppConfig, ConfigError, load_config
from .flow import mermaid_graph
from .gittools import GitError
from .hook import HookError, run_hook
from .versions import VersionError
from .yamlfile import VersionFileError

log = logging.getLogger("auto_version_hook")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="auto-version-hook",
        description="Pre-commit hook: bump a YAML version based on the branch class.",
    )
    parser.add_argument("--config", help="path to the YAML config (default: searched in the repo root)")
    parser.add_argument("--repo", default=".", help="path inside the target git repository (default: cwd)")
    parser.add_argument("--branch", help="branch name override (default: the current branch)")
    parser.add_argument("--graph", action="store_true", help="validate the config and print the branch_flow graph as Mermaid")
    parser.add_argument("--version-file", help="override version.file")
    parser.add_argument("--version-key", help="override version.key (yq-style path, e.g. app.build.version)")
    parser.add_argument("--parse-regex", help="override version.parse_regex (named groups, e.g. major/minor/patch)")
    parser.add_argument("--remote", help="override git.remote")
    parser.add_argument("--no-fetch", action="store_true", help="work offline: no ls-remote/fetch, use remote-tracking refs")
    parser.add_argument("--no-stage", action="store_true", help="do not `git add` the version file after changing it")
    parser.add_argument("--on-error", choices=["fail", "warn"], help="override hooks.on_error")
    parser.add_argument("--dry-run", action="store_true", help="only print what would happen")
    parser.add_argument(
        "--check",
        action="store_true",
        help="validator mode for CI: verify the version without changing anything; "
        "exit 1 if the hook would update the file or the branch is unknown "
        "(hooks.on_error=warn is ignored)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="print the result as JSON to stdout (human logs stay on stderr); "
        "pairs with --check/--dry-run, exit codes unchanged",
    )
    parser.add_argument("-v", "--verbose", action="count", default=0, help="debug output")
    parser.add_argument("-q", "--quiet", action="store_true", help="suppress informational output")
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    level = logging.WARNING if args.quiet else (logging.DEBUG if args.verbose else logging.INFO)
    logging.basicConfig(level=level, format="%(message)s")

    if args.graph:
        try:
            cfg = load_config(args.config, repo_root=Path(args.repo).resolve())
        except ConfigError as exc:
            print(f"auto-version-hook: {exc}", file=sys.stderr)
            return 2
        print(mermaid_graph(cfg.branch_flow))
        return 0

    try:
        root = gittools.repo_root(Path(args.repo))
        cfg = load_config(args.config, repo_root=root)
    except (ConfigError, GitError) as exc:
        if args.json:
            print(json.dumps({"action": "error", "message": str(exc)}, ensure_ascii=False))
            return 2
        print(f"auto-version-hook: {exc}", file=sys.stderr)
        return 2
    _apply_overrides(cfg, args)

    try:
        result = run_hook(cfg, repo=root, branch=args.branch, dry_run=args.dry_run or args.check)
    except (HookError, GitError, VersionError, VersionFileError) as exc:
        if args.json:
            print(json.dumps({"action": "error", "message": str(exc)}, ensure_ascii=False))
            return 1
        if cfg.hooks.on_error == "warn" and not args.check:
            log.warning("auto-version-hook: %s (on_error=warn, continuing)", exc)
            return 0
        print(f"auto-version-hook: {exc}", file=sys.stderr)
        return 1

    if args.json:
        print(json.dumps(_json_payload(result), ensure_ascii=False, indent=2))
        if args.check:
            return 1 if (result.skipped or result.would_change) else 0
        return 0

    if args.check:
        return _check_result(result, cfg)
    return 0


def _json_payload(result) -> dict:
    """The stable machine-readable contract for --json (see README)."""
    if result.skipped:
        action = "skipped"
    elif result.changed:
        action = "update"
    elif result.would_change:
        action = "would-update"
    else:
        action = "none"
    return {
        "action": action,
        "branch": result.branch,
        "branch_class": result.branch_class,
        "policy": result.policy,
        "target_branch": result.target_branch,
        "base_version": str(result.base) if result.base is not None else None,
        "version": str(result.version) if result.version is not None else None,
        "mirrors": list(result.mirrors),
        "changed": bool(result.changed),
        "would_change": bool(result.would_change),
        "dry_run": bool(result.dry_run),
    }


def _check_result(result, cfg: AppConfig) -> int:
    if result.skipped:
        print(
            "auto-version-hook: version check failed: branch could not be determined "
            "(detached HEAD or merge in progress); pass --branch",
            file=sys.stderr,
        )
        return 1
    if result.would_change:
        if result.version is not None:
            print(
                f"auto-version-hook: version check failed: {cfg.version.file} must be "
                f"{result.version} (run the pre-commit hook and commit again)",
                file=sys.stderr,
            )
        else:
            print(
                f"auto-version-hook: version check failed: version_files mirror(s) must be "
                f"{result.reference} (run the pre-commit hook and commit again)",
                file=sys.stderr,
            )
        return 1
    log.info("auto-version-hook: version check passed")
    return 0


def _apply_overrides(cfg: AppConfig, args: argparse.Namespace) -> None:
    if args.version_file:
        cfg.version.file = args.version_file
    if args.version_key:
        cfg.version.key = args.version_key
    if args.parse_regex:
        cfg.version.parse_regex = args.parse_regex
    if args.remote:
        cfg.git.remote = args.remote
    if args.no_fetch:
        cfg.git.fetch = False
    if args.no_stage:
        cfg.hooks.auto_stage = False
    if args.on_error:
        cfg.hooks.on_error = args.on_error


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
