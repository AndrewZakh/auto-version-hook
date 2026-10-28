"""Thin wrappers around the git CLI."""

from __future__ import annotations

import subprocess
from pathlib import Path
from typing import List, Optional, Sequence


class GitError(RuntimeError):
    """Raised when a git command fails."""


def _git(args: Sequence[str], cwd: Path) -> subprocess.CompletedProcess:
    try:
        return subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, text=True
        )
    except FileNotFoundError as exc:  # pragma: no cover - git is virtually always there
        raise GitError("git executable not found") from exc


def git(args: Sequence[str], cwd: Path) -> str:
    """Run git, return stdout, raise GitError with stderr on failure."""
    proc = _git(args, cwd)
    if proc.returncode != 0:
        message = (proc.stderr.strip() or proc.stdout.strip() or f"exit code {proc.returncode}")
        raise GitError(f"git {' '.join(args)}: {message}")
    return proc.stdout


def repo_root(cwd: Path) -> Path:
    return Path(git(["rev-parse", "--show-toplevel"], cwd).strip())


def current_branch(cwd: Path) -> Optional[str]:
    """The checked-out branch name, or None for a detached HEAD."""
    proc = _git(["symbolic-ref", "--quiet", "--short", "HEAD"], cwd)
    if proc.returncode != 0:
        return None
    return proc.stdout.strip() or None


def fetch(cwd: Path, remote: str, branch: str) -> None:
    """Update the remote-tracking ref of the protected branch."""
    git(["fetch", "--quiet", remote, branch], cwd)


def ls_remote_heads(cwd: Path, remote: str) -> List[str]:
    """Branch names that exist on the remote right now (one network call)."""
    out = git(["ls-remote", "--heads", remote], cwd)
    return [line.split("refs/heads/", 1)[1] for line in out.splitlines() if "refs/heads/" in line]


def remote_heads_local(cwd: Path, remote: str) -> List[str]:
    """Branch names known from the last fetch (remote-tracking refs), offline mode."""
    out = git(["for-each-ref", "--format=%(refname:short)", f"refs/remotes/{remote}/"], cwd)
    prefix = f"{remote}/"
    return [
        line[len(prefix):]
        for line in out.splitlines()
        if line.startswith(prefix) and line != f"{remote}/HEAD"
    ]


def is_merge_in_progress(cwd: Path) -> bool:
    proc = _git(["rev-parse", "-q", "--verify", "MERGE_HEAD"], cwd)
    return proc.returncode == 0


def read_file_from_ref(cwd: Path, ref: str, path: str) -> Optional[str]:
    """File content at ``ref:path``, or None if the file does not exist there."""
    proc = _git(["show", f"{ref}:{path}"], cwd)
    if proc.returncode == 0:
        return proc.stdout
    error = proc.stderr or ""
    if "does not exist" in error or "exists on disk, but not in" in error:
        return None
    raise GitError(f"git show {ref}:{path}: {error.strip()}")


def stage(cwd: Path, path: str) -> None:
    git(["add", "--", path], cwd)
