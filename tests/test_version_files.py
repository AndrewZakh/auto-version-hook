"""version_files: mirrors of the master version (README, Configuration)."""

from __future__ import annotations

import logging

import pytest

# same dir as conftest/test_hook: pytest puts it on sys.path
from test_hook import _check, read_version, stage_change, staged_files  # noqa: I001

from auto_version_hook import AppConfig, HookError, run_hook
from auto_version_hook.config import ConfigError, VersionFileConfig, load_config

PYPROJECT_REGEX = r'^version = "(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)"$'


def cfg_with(*entries: VersionFileConfig) -> AppConfig:
    return AppConfig(version_files=list(entries))


def make_pyproject(repo, version: str = "0.1.0") -> None:
    (repo / "pyproject.toml").write_text(f'version = "{version}"\n', encoding="utf-8")


def read_pyproject(repo) -> str:
    return (repo / "pyproject.toml").read_text(encoding="utf-8")


def test_mirror_follows_the_bump(repo, git):
    make_pyproject(repo)
    git("checkout", "-b", "feature/login", cwd=repo)
    stage_change(git, repo)
    result = run_hook(
        cfg_with(VersionFileConfig(path="pyproject.toml", regex=PYPROJECT_REGEX)), repo=repo
    )
    assert result.changed is True
    assert read_version(repo) == "v1.3.3"
    assert 'version = "1.3.3"' in read_pyproject(repo)
    staged = staged_files(git, repo)
    assert "env.yml" in staged and "pyproject.toml" in staged


def test_mirror_missing_file_is_skipped(repo):
    cfg = cfg_with(VersionFileConfig(path="Cargo.toml", regex=PYPROJECT_REGEX))
    result = run_hook(cfg, repo=repo)
    assert result.changed is False  # nothing to sync: the mirror does not exist


def test_mirror_no_match_blocks_the_commit(repo, git):
    (repo / "pyproject.toml").write_text("version: 0.1.0\n", encoding="utf-8")  # wrong syntax
    git("checkout", "-b", "feature/login", cwd=repo)
    stage_change(git, repo)
    cfg = cfg_with(VersionFileConfig(path="pyproject.toml", regex=PYPROJECT_REGEX))
    with pytest.raises(HookError, match="no match"):
        run_hook(cfg, repo=repo)


def test_mirror_first_match_bumped_with_warning(repo, git, caplog):
    (repo / "double.txt").write_text(
        'version = "0.1.0"\nkeep = "x"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    git("checkout", "-b", "feature/login", cwd=repo)
    stage_change(git, repo)
    cfg = cfg_with(VersionFileConfig(path="double.txt", regex=PYPROJECT_REGEX))
    with caplog.at_level(logging.WARNING, logger="auto_version_hook"):
        result = run_hook(cfg, repo=repo)
    assert result.changed is True
    text = (repo / "double.txt").read_text(encoding="utf-8")
    assert 'version = "1.3.3"' in text
    assert text.count('version = "0.1.0"') == 1  # the second match stays
    assert any("2 matches" in record.getMessage() for record in caplog.records)


def test_mirror_replace_all_syncs_every_match(repo, git, caplog):
    (repo / "double.txt").write_text(
        'version = "0.1.0"\nkeep = "x"\nversion = "0.1.0"\n', encoding="utf-8"
    )
    git("checkout", "-b", "feature/login", cwd=repo)
    stage_change(git, repo)
    cfg = cfg_with(
        VersionFileConfig(path="double.txt", regex=PYPROJECT_REGEX, replace_all=True)
    )
    with caplog.at_level(logging.WARNING, logger="auto_version_hook"):
        result = run_hook(cfg, repo=repo)
    assert result.changed is True
    assert (repo / "double.txt").read_text(encoding="utf-8").count('version = "1.3.3"') == 2
    assert not any("matches for" in record.getMessage() for record in caplog.records)


def test_mirror_is_dragged_down_to_the_master_version(repo, git):
    make_pyproject(repo, version="9.9.9")  # somehow ahead of the flow
    git("checkout", "-b", "feature/login", cwd=repo)
    stage_change(git, repo)
    result = run_hook(
        cfg_with(VersionFileConfig(path="pyproject.toml", regex=PYPROJECT_REGEX)), repo=repo
    )
    assert result.changed is True
    assert 'version = "1.3.3"' in read_pyproject(repo)  # mirrors are absolute


def test_mirror_self_heals_on_protected_branch_without_bump(repo, git):
    make_pyproject(repo, version="0.1.0")  # stale, but env.yml stays v1.2.3 on master
    stage_change(git, repo)  # a direct commit on the protected branch: no bump
    result = run_hook(
        cfg_with(VersionFileConfig(path="pyproject.toml", regex=PYPROJECT_REGEX)), repo=repo
    )
    assert result.changed is True  # only the mirror moved
    assert read_version(repo) == "v1.2.3"
    assert 'version = "1.2.3"' in read_pyproject(repo)


def test_check_detects_stale_mirror(repo, git):
    make_pyproject(repo, version="0.1.0")
    (repo / ".version-hook.yml").write_text(
        "version:\n"
        "  file: env.yml\n"
        "  key: version\n"
        "version_files:\n"
        "  - path: pyproject.toml\n"
        f"    regex: '{PYPROJECT_REGEX}'\n",
        encoding="utf-8",
    )
    proc = _check(repo, "--branch", "master")  # env.yml is correct, the mirror is not
    assert proc.returncode == 1
    assert "version_files mirror(s) must be v1.2.3" in proc.stderr


def test_defaults_have_no_version_files(tmp_path):
    assert load_config(None, repo_root=tmp_path).version_files == []


def test_config_rejects_unknown_mirror_group(tmp_path):
    path = tmp_path / ".version-hook.yml"
    path.write_text(
        "version:\n"
        "  file: env.yml\n"
        "  key: version\n"
        "version_files:\n"
        "  - path: pyproject.toml\n"
        '    regex: \'^version = "(?P<build>\\d+)"$\'\n',
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="not named groups"):
        load_config(None, repo_root=tmp_path)


def test_config_rejects_unknown_mirror_option(tmp_path):
    path = tmp_path / ".version-hook.yml"
    path.write_text(
        "version:\n"
        "  file: env.yml\n"
        "  key: version\n"
        "version_files:\n"
        "  - path: pyproject.toml\n"
        f"    regex: '{PYPROJECT_REGEX}'\n"
        "    greedy: true\n",
        encoding="utf-8",
    )
    with pytest.raises(ConfigError, match="unknown option\\(s\\): greedy"):
        load_config(None, repo_root=tmp_path)
