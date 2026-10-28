"""Shared fixtures: a `git` runner and disposable repos with a bare origin."""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest


@pytest.fixture()
def git():
    def _git(*args, cwd, check=True):
        return subprocess.run(
            ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=check
        )

    return _git


@pytest.fixture()
def repo(tmp_path: Path, git):
    """Trunk-based repo: master only (env.yml at v1.2.3), pushed to a bare origin."""
    bare = tmp_path / "origin.git"
    git("init", "--bare", str(bare), cwd=tmp_path)
    git("symbolic-ref", "HEAD", "refs/heads/master", cwd=bare)

    work = tmp_path / "work"
    work.mkdir()
    git("init", str(work), cwd=tmp_path)
    git("symbolic-ref", "HEAD", "refs/heads/master", cwd=work)
    git("config", "user.email", "test@example.com", cwd=work)
    git("config", "user.name", "Test User", cwd=work)
    (work / "env.yml").write_text("version: v1.2.3\n", encoding="utf-8")
    git("add", "-A", cwd=work)
    git("commit", "-m", "initial", cwd=work)
    git("remote", "add", "origin", str(bare), cwd=work)
    git("push", "-qu", "origin", "master", cwd=work)
    return work


@pytest.fixture()
def gitflow_repo(repo: Path, git):
    """GitFlow repo: master + staging (both at v1.2.3), left checked out on master."""
    git("checkout", "-b", "staging", cwd=repo)
    git("push", "-qu", "origin", "staging", cwd=repo)
    git("checkout", "master", cwd=repo)
    return repo
