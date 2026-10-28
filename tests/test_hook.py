"""End-to-end tests against real disposable git repositories (v2 branch_flow)."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

from auto_version_hook import AppConfig, HookError, run_hook
from auto_version_hook.flow import BranchClass

SRC = Path(__file__).resolve().parents[1] / "src"


def read_version(repo: Path) -> str:
    return yaml.safe_load((repo / "env.yml").read_text())["version"]


def stage_change(git, repo: Path) -> None:
    (repo / "src.txt").write_text("change\n", encoding="utf-8")
    git("add", "src.txt", cwd=repo)


def staged_files(git, repo: Path):
    return git("diff", "--cached", "--name-only", cwd=repo).stdout.split()


def set_version(git, repo: Path, version: str) -> None:
    """Commit a new version on the current branch and push it."""
    (repo / "env.yml").write_text(f"version: {version}\n", encoding="utf-8")
    git("add", "env.yml", cwd=repo)
    git("commit", "-m", f"version {version}", cwd=repo)
    git("push", "-q", "origin", "HEAD", cwd=repo)


# --- default flow, trunk-based repo (only master exists) ---


@pytest.mark.parametrize(
    "branch, branch_class, expected",
    [
        ("feature/login", "feature", "v1.3.3"),
        ("feat/quick", "feature", "v1.3.3"),
        ("patch-DEMO-1", "patch", "v1.2.4"),
    ],
)
def test_bump_by_branch(repo, git, branch, branch_class, expected):
    git("checkout", "-b", branch, cwd=repo)
    stage_change(git, repo)
    result = run_hook(AppConfig(), repo=repo)
    assert result.changed is True
    assert result.branch_class == branch_class
    # no staging exists: the feature chain walks up to main
    assert result.target_branch == "master"
    assert read_version(repo) == expected
    assert "env.yml" in staged_files(git, repo)


def test_main_is_untouched(repo, git):
    (repo / "env.yml").write_text("version: v3.0.0\n", encoding="utf-8")
    stage_change(git, repo)
    result = run_hook(AppConfig(), repo=repo)
    assert result.changed is False
    assert result.branch_class == "main"
    assert read_version(repo) == "v3.0.0"
    assert "env.yml" not in staged_files(git, repo)


# --- GitFlow ---


def test_feature_bases_on_staging_not_master(gitflow_repo, git):
    git("checkout", "staging", cwd=gitflow_repo)
    set_version(git, gitflow_repo, "v1.2.9")
    git("checkout", "-b", "feature/login", cwd=gitflow_repo)
    stage_change(git, gitflow_repo)
    result = run_hook(AppConfig(), repo=gitflow_repo)
    assert result.target_branch == "staging"
    # minor bump keeps the patch part: v1.2.9 -> v1.3.9 (not v1.3.3 from master)
    assert read_version(gitflow_repo) == "v1.3.9"


def test_second_feature_rebases_on_live_staging(gitflow_repo, git):
    repo = gitflow_repo
    git("checkout", "staging", cwd=repo)
    git("checkout", "-b", "feat-1", cwd=repo)
    (repo / "a.txt").write_text("1\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    run_hook(AppConfig(), repo=repo)
    git("add", "-A", cwd=repo)
    git("commit", "-m", "feat-1", cwd=repo)

    git("checkout", "staging", cwd=repo)
    git("merge", "--no-ff", "-m", "merge feat-1", "feat-1", cwd=repo)
    git("push", "-q", "origin", "staging", cwd=repo)

    git("checkout", "-b", "feat-2", cwd=repo)
    (repo / "b.txt").write_text("2\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    result = run_hook(AppConfig(), repo=repo)
    assert result.changed is True
    # staging advanced to v1.3.3 (feat-1), so feat-2 claims the next minor
    assert read_version(repo) == "v1.4.3"


def test_tech_ignore_syncs_to_staging(gitflow_repo, git):
    git("checkout", "staging", cwd=gitflow_repo)
    set_version(git, gitflow_repo, "v1.2.9")
    git("checkout", "-b", "devops/tech-cleanup", cwd=gitflow_repo)
    (gitflow_repo / "env.yml").write_text("version: v9.9.9\n", encoding="utf-8")
    stage_change(git, gitflow_repo)
    result = run_hook(AppConfig(), repo=gitflow_repo)
    assert result.changed is True
    assert result.branch_class == "tech"
    assert read_version(gitflow_repo) == "v1.2.9"


def test_staging_catchup_after_hotfix(gitflow_repo, git):
    git("checkout", "master", cwd=gitflow_repo)
    set_version(git, gitflow_repo, "v1.2.4")  # a hotfix reached main
    git("checkout", "staging", cwd=gitflow_repo)  # staging still at v1.2.3
    stage_change(git, gitflow_repo)
    result = run_hook(AppConfig(), repo=gitflow_repo)
    assert result.changed is True
    assert result.branch_class == "staging"
    assert result.target_branch == "master"
    assert read_version(gitflow_repo) == "v1.2.4"
    assert "env.yml" in staged_files(git, gitflow_repo)


def test_staging_ahead_of_main_is_untouched(gitflow_repo, git):
    git("checkout", "staging", cwd=gitflow_repo)
    set_version(git, gitflow_repo, "v1.5.0")
    stage_change(git, gitflow_repo)
    result = run_hook(AppConfig(), repo=gitflow_repo)
    assert result.changed is False
    assert read_version(gitflow_repo) == "v1.5.0"


def test_exact_class_name_resolves_ambiguous_target(gitflow_repo, git):
    # both dev and staging match the staging class regex on origin;
    # the class is named staging -> exact branch wins, no ambiguity
    git("checkout", "-b", "dev", cwd=gitflow_repo)
    git("push", "-q", "origin", "dev", cwd=gitflow_repo)
    git("checkout", "-b", "feature/x", cwd=gitflow_repo)
    stage_change(git, gitflow_repo)
    result = run_hook(AppConfig(), repo=gitflow_repo)
    assert result.target_branch == "staging"


def test_ambiguous_target_branches(gitflow_repo, git):
    git("checkout", "-b", "dev", cwd=gitflow_repo)
    git("push", "-q", "origin", "dev", cwd=gitflow_repo)
    git("checkout", "-b", "feature/x", cwd=gitflow_repo)
    stage_change(git, gitflow_repo)
    cfg = AppConfig()
    # rename the staging class so no branch is named exactly like it
    cfg.branch_flow = [
        BranchClass(name="main", regex=r"^(master|main)$", protected=True, policy="keep"),
        BranchClass(
            name="integration",
            regex=r"^(dev(elop(ment)?)?|stag(ing)?)$",
            protected=True,
            target="main",
            policy="keep",
        ),
        BranchClass(
            name="feature", regex=r"^feat(ure)?", target="integration",
            policy="increment", bump="minor",
        ),
    ]
    with pytest.raises(HookError, match="several remote branches"):
        run_hook(cfg, repo=gitflow_repo)


# --- guards and edge cases ---


def test_unknown_branch_name_blocks_commit(repo, git):
    git("checkout", "-b", "weird_branch", cwd=repo)
    with pytest.raises(HookError, match="invalid"):
        run_hook(AppConfig(), repo=repo)


def test_no_downgrade_to_lower_computed_version(repo, git):
    git("checkout", "-b", "feature/high", cwd=repo)
    (repo / "env.yml").write_text("version: v9.9.9\n", encoding="utf-8")
    stage_change(git, repo)
    result = run_hook(AppConfig(), repo=repo)
    assert result.changed is False
    assert read_version(repo) == "v9.9.9"


def test_idempotent_second_run(repo, git):
    git("checkout", "-b", "feature/twice", cwd=repo)
    stage_change(git, repo)
    first = run_hook(AppConfig(), repo=repo)
    second = run_hook(AppConfig(), repo=repo)
    assert first.changed is True
    assert second.changed is False
    assert read_version(repo) == "v1.3.3"


def test_dry_run_does_not_touch_worktree(repo, git):
    git("checkout", "-b", "feature/dry", cwd=repo)
    stage_change(git, repo)
    result = run_hook(AppConfig(), repo=repo, dry_run=True)
    assert result.dry_run is True
    assert read_version(repo) == "v1.2.3"
    assert "env.yml" not in staged_files(git, repo)


def test_detached_head_is_skipped(repo, git):
    git("checkout", "--detach", cwd=repo)
    stage_change(git, repo)
    result = run_hook(AppConfig(), repo=repo)
    assert result.skipped is True
    assert result.changed is False
    assert read_version(repo) == "v1.2.3"


def test_merge_commit_is_skipped(repo, git):
    git("checkout", "-b", "feature/merge-skip", cwd=repo)
    stage_change(git, repo)
    run_hook(AppConfig(), repo=repo)
    git("add", "-A", cwd=repo)
    git("commit", "-m", "work", cwd=repo)

    git("checkout", "-b", "side", "master", cwd=repo)
    (repo / "side.txt").write_text("side\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-m", "side", cwd=repo)

    git("checkout", "feature/merge-skip", cwd=repo)
    git("merge", "--no-ff", "--no-commit", "side", cwd=repo)  # MERGE_HEAD appears
    try:
        result = run_hook(AppConfig(), repo=repo)
        assert result.skipped is True
        assert read_version(repo) == "v1.3.3"  # not bumped during the merge
    finally:
        git("merge", "--abort", cwd=repo)


def test_merge_commit_runs_when_skip_disabled(repo, git):
    git("checkout", "-b", "feature/merge-run", cwd=repo)
    stage_change(git, repo)
    git("add", "-A", cwd=repo)
    git("commit", "-m", "work", cwd=repo)  # env.yml still v1.2.3

    git("checkout", "-b", "side", "master", cwd=repo)
    (repo / "side.txt").write_text("side\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-m", "side", cwd=repo)

    git("checkout", "feature/merge-run", cwd=repo)
    git("merge", "--no-ff", "--no-commit", "side", cwd=repo)
    try:
        cfg = AppConfig()
        cfg.hooks.skip_merges = False
        result = run_hook(cfg, repo=repo)
        assert result.skipped is False
        assert result.changed is True
        assert read_version(repo) == "v1.3.3"
    finally:
        git("merge", "--abort", cwd=repo)


def test_missing_version_file_on_target(repo, git):
    git("rm", "-q", "env.yml", cwd=repo)
    git("commit", "-m", "drop version file", cwd=repo)
    git("push", "-q", "origin", "master", cwd=repo)
    git("checkout", "-b", "feature/no-version", cwd=repo)
    with pytest.raises(HookError, match="not found in origin/master"):
        run_hook(AppConfig(), repo=repo)


def test_no_fetch_uses_remote_tracking_refs(repo, git):
    git("checkout", "-b", "feature/offline", cwd=repo)
    cfg = AppConfig()
    cfg.git.fetch = False
    result = run_hook(cfg, repo=repo)
    assert result.changed is True
    assert read_version(repo) == "v1.3.3"


# --- CLI ---


def _module_env() -> dict:
    pythonpath = os.pathsep.join(
        part for part in (str(SRC), os.environ.get("PYTHONPATH", "")) if part
    )
    return {**os.environ, "PYTHONPATH": pythonpath}


def test_cli_dry_run(repo, git):
    git("checkout", "-b", "feature/cli", cwd=repo)
    stage_change(git, repo)
    proc = subprocess.run(
        [sys.executable, "-m", "auto_version_hook", "--dry-run"],
        cwd=str(repo), capture_output=True, text=True, env=_module_env(),
    )
    assert proc.returncode == 0, proc.stderr
    assert "v1.3.3" in proc.stdout + proc.stderr
    assert read_version(repo) == "v1.2.3"


def test_cli_updates_and_stages(repo, git):
    git("checkout", "-b", "feature/cli-real", cwd=repo)
    stage_change(git, repo)
    proc = subprocess.run(
        [sys.executable, "-m", "auto_version_hook"],
        cwd=str(repo), capture_output=True, text=True, env=_module_env(),
    )
    assert proc.returncode == 0, proc.stderr
    assert read_version(repo) == "v1.3.3"
    assert "env.yml" in staged_files(git, repo)


def test_cli_graph(repo, git):
    proc = subprocess.run(
        [sys.executable, "-m", "auto_version_hook", "--graph"],
        cwd=str(repo), capture_output=True, text=True, env=_module_env(),
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert out.startswith("flowchart TD")
    assert "feature" in out and "staging" in out and "bump minor" in out


# --- --check (CI validator mode) ---


def _check(repo: Path, *extra_args: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        [sys.executable, "-m", "auto_version_hook", "--check", *extra_args],
        cwd=str(repo), capture_output=True, text=True, env=_module_env(),
    )


def test_check_passes_when_version_is_correct(repo, git):
    git("checkout", "-b", "feature/ok", cwd=repo)
    stage_change(git, repo)
    run_hook(AppConfig(), repo=repo)  # the pre-commit hook bumps to v1.3.3
    git("add", "-A", cwd=repo)
    git("commit", "-m", "work", cwd=repo)
    proc = _check(repo, "--branch", "feature/ok")
    assert proc.returncode == 0, proc.stderr
    assert "passed" in proc.stdout + proc.stderr
    assert read_version(repo) == "v1.3.3"
    assert "env.yml" not in staged_files(git, repo)  # nothing extra staged


def test_check_fails_when_version_is_stale(repo, git):
    git("checkout", "-b", "feature/stale", cwd=repo)
    # simulate a commit made before the version file was refreshed
    (repo / "env.yml").write_text("version: v0.0.1\n", encoding="utf-8")
    git("add", "-A", cwd=repo)
    git("commit", "-m", "work", cwd=repo)
    proc = _check(repo, "--branch", "feature/stale")
    assert proc.returncode == 1
    assert "must be v1.3.3" in proc.stderr
    assert read_version(repo) == "v0.0.1"  # nothing written
    assert "env.yml" not in staged_files(git, repo)


def test_check_fails_on_unknown_branch(repo, git):
    proc = _check(repo, "--branch", "weird_branch")
    assert proc.returncode == 1
    assert "invalid" in proc.stderr


def test_check_ignores_on_error_warn(repo, git):
    # without --check, on_error=warn would let an invalid branch through (exit 0);
    # the CI validator must stay strict
    proc = _check(repo, "--branch", "weird_branch", "--on-error", "warn")
    assert proc.returncode == 1
    assert "invalid" in proc.stderr


def test_check_without_branch_in_detached_head_fails(repo, git):
    git("checkout", "--detach", cwd=repo)
    stage_change(git, repo)
    proc = _check(repo)  # CI runners check out detached HEAD and must pass --branch
    assert proc.returncode == 1
    assert "branch could not be determined" in proc.stderr


def test_check_passes_on_merge_commit_with_skip_merges(gitflow_repo, git):
    git("checkout", "-b", "feature/mrg", cwd=gitflow_repo)
    stage_change(git, gitflow_repo)
    run_hook(AppConfig(), repo=gitflow_repo)
    git("add", "-A", cwd=gitflow_repo)
    git("commit", "-m", "work", cwd=gitflow_repo)
    git("checkout", "-b", "side", "master", cwd=gitflow_repo)
    (gitflow_repo / "side.txt").write_text("side\n", encoding="utf-8")
    git("add", "-A", cwd=gitflow_repo)
    git("commit", "-m", "side", cwd=gitflow_repo)
    git("checkout", "feature/mrg", cwd=gitflow_repo)
    git("merge", "--no-ff", "--no-commit", "side", cwd=gitflow_repo)
    try:
        proc = _check(gitflow_repo, "--branch", "feature/mrg")
        # skipped because of skip_merges -> treated as "cannot determine", strict
        assert proc.returncode == 1
        assert "branch could not be determined" in proc.stderr
    finally:
        git("merge", "--abort", cwd=gitflow_repo)
