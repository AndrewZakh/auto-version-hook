import pytest

from auto_version_hook.config import ConfigError, load_config


def test_defaults_match_the_design(tmp_path):
    cfg = load_config(None, repo_root=tmp_path)
    assert cfg.version.parse_regex == r"^v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$"
    assert cfg.git.remote == "origin"
    assert cfg.git.fetch is True
    assert cfg.hooks.skip_merges is True
    assert cfg.hooks.on_error == "fail"

    names = [c.name for c in cfg.branch_flow]
    assert names == ["main", "staging", "patch", "feature", "tech"]
    by_name = {c.name: c for c in cfg.branch_flow}
    assert by_name["main"].protected is True and by_name["main"].target is None
    assert by_name["staging"].protected is True and by_name["staging"].target == "main"
    assert by_name["patch"].policy == "increment" and by_name["patch"].bump == "patch"
    assert by_name["feature"].target == "staging" and by_name["feature"].bump == "minor"
    assert by_name["tech"].policy == "ignore"


def test_load_full_config(tmp_path):
    path = tmp_path / "version-hook.yml"
    path.write_text(
        "version:\n"
        "  file: ver.yaml\n"
        "  key: app.build.version\n"
        "  parse_regex: '^v(?P<major>\\d+)\\.(?P<minor>\\d+)\\.(?P<hotfix>\\d+)$'\n"
        "git:\n"
        "  remote: upstream\n"
        "branch_flow:\n"
        "  - name: main\n"
        "    regex: '^(master|main)$'\n"
        "    protected: true\n"
        "    policy: keep\n"
        "  - name: feature\n"
        "    regex: '^feat(ure)?'\n"
        "    target: main\n"
        "    policy: increment\n"
        "    bump: minor\n"
        "    reset_lower_parts: true\n"
        "  - name: tech\n"
        "    regex: '^chore'\n"
        "    target: main\n"
        "    policy: ignore\n"
        "hooks:\n"
        "  on_error: warn\n"
        "  skip_merges: false\n",
        encoding="utf-8",
    )
    cfg = load_config(str(path), repo_root=tmp_path)
    assert cfg.version.file == "ver.yaml"
    assert cfg.git.remote == "upstream"
    assert cfg.hooks.on_error == "warn"
    assert cfg.hooks.skip_merges is False
    feature = [c for c in cfg.branch_flow if c.name == "feature"][0]
    assert feature.target == "main"
    assert feature.bump == "minor"
    assert feature.reset_lower_parts is True
    assert cfg.source == path


def test_v1_config_rejected_with_migration_hint(tmp_path):
    path = tmp_path / "version-hook.yml"
    path.write_text("bump:\n  rules:\n    major: x\n")
    with pytest.raises(ConfigError, match="v1 options are no longer supported"):
        load_config(str(path), repo_root=tmp_path)

    path.write_text("git:\n  protected_branch: master\n")
    with pytest.raises(ConfigError, match="v1 options"):
        load_config(str(path), repo_root=tmp_path)


def _flow_config(tmp_path, flow_yaml):
    path = tmp_path / "version-hook.yml"
    path.write_text(f"branch_flow:\n{flow_yaml}")
    return path


def test_unknown_target_rejected(tmp_path):
    path = _flow_config(tmp_path, "  - name: feature\n    regex: '^f'\n    target: nowhere\n    policy: ignore\n")
    with pytest.raises(ConfigError, match="target 'nowhere' is not a class name"):
        load_config(str(path), repo_root=tmp_path)


def test_cycle_rejected(tmp_path):
    flow = (
        "  - name: a\n    regex: '^a'\n    target: b\n    policy: ignore\n"
        "  - name: b\n    regex: '^b'\n    target: a\n    policy: ignore\n"
    )
    path = _flow_config(tmp_path, flow)
    with pytest.raises(ConfigError, match="cycle"):
        load_config(str(path), repo_root=tmp_path)


def test_protected_must_keep_and_not_bump(tmp_path):
    flow = (
        "  - name: main\n    regex: '^main$'\n    protected: true\n    policy: keep\n"
        "  - name: wrong\n    regex: '^w'\n    protected: true\n    target: main\n    policy: increment\n    bump: minor\n"
    )
    path = _flow_config(tmp_path, flow)
    with pytest.raises(ConfigError, match="protected classes must use policy 'keep'"):
        load_config(str(path), repo_root=tmp_path)

    flow = flow.replace("policy: increment\n    bump: minor", "policy: keep\n    bump: minor")
    path = _flow_config(tmp_path, flow)
    with pytest.raises(ConfigError, match="protected classes must not have bump"):
        load_config(str(path), repo_root=tmp_path)


def test_increment_needs_bump_group_from_parse_regex(tmp_path):
    path = _flow_config(
        tmp_path,
        "  - name: main\n    regex: '^main$'\n    protected: true\n    policy: keep\n"
        "  - name: feature\n    regex: '^f'\n    target: main\n    policy: increment\n",
    )
    with pytest.raises(ConfigError, match="needs a bump group"):
        load_config(str(path), repo_root=tmp_path)

    path = _flow_config(
        tmp_path,
        "  - name: main\n    regex: '^main$'\n    protected: true\n    policy: keep\n"
        "  - name: feature\n    regex: '^f'\n    target: main\n    policy: increment\n    bump: mega\n",
    )
    with pytest.raises(ConfigError, match="no group named 'mega'"):
        load_config(str(path), repo_root=tmp_path)


def test_non_protected_needs_target_and_increment_or_ignore(tmp_path):
    path = _flow_config(
        tmp_path,
        "  - name: main\n    regex: '^main$'\n    protected: true\n    policy: keep\n"
        "  - name: orphan\n    regex: '^o'\n    policy: ignore\n",
    )
    with pytest.raises(ConfigError, match="need a target"):
        load_config(str(path), repo_root=tmp_path)

    path = _flow_config(
        tmp_path,
        "  - name: main\n    regex: '^main$'\n    protected: true\n    policy: keep\n"
        "  - name: docs\n    regex: '^d'\n    target: main\n    policy: keep\n",
    )
    with pytest.raises(ConfigError, match="'increment' or 'ignore'"):
        load_config(str(path), repo_root=tmp_path)


def test_bad_policy_and_regex_rejected(tmp_path):
    path = _flow_config(
        tmp_path,
        "  - name: main\n    regex: '^main$'\n    protected: true\n    policy: keep\n"
        "  - name: x\n    regex: '^x'\n    target: main\n    policy: mega\n",
    )
    with pytest.raises(ConfigError, match="policy must be one of"):
        load_config(str(path), repo_root=tmp_path)

    path = _flow_config(
        tmp_path,
        "  - name: x\n    regex: '[unclosed'\n    target: main\n    policy: ignore\n",
    )
    with pytest.raises(ConfigError, match="regex"):
        load_config(str(path), repo_root=tmp_path)


def test_duplicate_names_and_empty_flow_rejected(tmp_path):
    path = _flow_config(
        tmp_path,
        "  - name: x\n    regex: '^x'\n    target: main\n    policy: ignore\n"
        "  - name: x\n    regex: '^y'\n    target: main\n    policy: ignore\n",
    )
    with pytest.raises(ConfigError, match="duplicate"):
        load_config(str(path), repo_root=tmp_path)

    path = tmp_path / "version-hook.yml"
    path.write_text("branch_flow: []\n")
    with pytest.raises(ConfigError, match="non-empty list"):
        load_config(str(path), repo_root=tmp_path)


def test_unknown_class_option_rejected(tmp_path):
    path = _flow_config(
        tmp_path,
        "  - name: main\n    regex: '^main$'\n    protected: true\n    policy: keep\n    bump_policy: mega\n",
    )
    with pytest.raises(ConfigError, match="unknown option"):
        load_config(str(path), repo_root=tmp_path)


def test_overlapping_regexes_warn(tmp_path, caplog):
    flow = (
        "  - name: main\n    regex: '^main$'\n    protected: true\n    policy: keep\n"
        "  - name: release\n    regex: '^release'\n    target: main\n    policy: increment\n    bump: minor\n"
        "  - name: release-candidate\n    regex: '^release-candidate'\n    target: main\n    policy: ignore\n"
    )
    path = _flow_config(tmp_path, flow)
    with caplog.at_level("WARNING", logger="auto_version_hook"):
        load_config(str(path), repo_root=tmp_path)
    assert any("release" in record.message and "release-candidate" in record.message for record in caplog.records)


def test_non_branchlike_class_name_warns(tmp_path, caplog):
    flow = (
        "  - name: main branch\n    regex: '^(master|main)$'\n    protected: true\n    policy: keep\n"
        "  - name: feature\n    regex: '^feat'\n    target: main branch\n    policy: increment\n    bump: minor\n"
    )
    path = _flow_config(tmp_path, flow)
    with caplog.at_level("WARNING", logger="auto_version_hook"):
        load_config(str(path), repo_root=tmp_path)  # loads fine, only warns
    assert any("main branch" in record.message for record in caplog.records)


def test_branchlike_class_name_does_not_warn(tmp_path, caplog):
    flow = (
        "  - name: main\n    regex: '^(master|main)$'\n    protected: true\n    policy: keep\n"
        "  - name: feature\n    regex: '^feat'\n    target: main\n    policy: increment\n    bump: minor\n"
    )
    path = _flow_config(tmp_path, flow)
    with caplog.at_level("WARNING", logger="auto_version_hook"):
        load_config(str(path), repo_root=tmp_path)
    assert not any("does not look like a valid git branch" in record.message for record in caplog.records)


def test_unknown_option_rejected(tmp_path):
    path = tmp_path / "version-hook.yml"
    path.write_text("version:\n  prefix: v\n")
    with pytest.raises(ConfigError, match="version.prefix"):
        load_config(str(path), repo_root=tmp_path)


def test_unknown_section_rejected(tmp_path):
    path = tmp_path / "version-hook.yml"
    path.write_text("versioning:\n  file: env.yml\n")
    with pytest.raises(ConfigError, match="unknown section"):
        load_config(str(path), repo_root=tmp_path)


def test_explicit_missing_config_rejected(tmp_path):
    with pytest.raises(ConfigError, match="not found"):
        load_config(str(tmp_path / "nope.yml"), repo_root=tmp_path)


def test_config_discovered_in_repo_root(tmp_path):
    path = tmp_path / ".version-hook.yml"
    path.write_text("version:\n  file: custom.yml\n")
    cfg = load_config(None, repo_root=tmp_path)
    assert cfg.version.file == "custom.yml"
