import pytest

from auto_version_hook.yamlfile import VersionFileError, read_key, write_key


def test_read_simple():
    assert read_key("version: v1.2.3\n", "version") == "v1.2.3"


def test_read_quoted():
    assert read_key('version: "v1.2.3"\n', "version") == "v1.2.3"


def test_read_missing_key():
    assert read_key("other: 1\n", "version") is None


def test_read_empty_document():
    assert read_key("", "version") is None


def test_read_path_on_non_mapping_document():
    # With paths, a document of any shape is fine; an inapplicable path -> None.
    assert read_key("- a\n- b\n", "version") is None
    assert read_key("- a\n- b\n", "[0]") == "a"


def test_read_invalid_yaml_raises():
    with pytest.raises(VersionFileError):
        read_key("a: [unclosed\n", "version")


def test_write_preserves_comment():
    text = "version: v1.2.3  # keep me\nname: app\n"
    out = write_key(text, "version", "v1.3.3")
    assert "version: v1.3.3  # keep me" in out
    assert "name: app" in out


def test_write_preserves_quotes():
    out = write_key('version: "v1.2.3"\n', "version", "v1.3.3")
    assert 'version: "v1.3.3"' in out


def test_write_prefers_top_level_key_over_nested():
    text = "version: v1.2.3\nmeta:\n  version: v9.9.9\n"
    out = write_key(text, "version", "v1.3.3")
    assert out.startswith("version: v1.3.3\n")
    assert "v9.9.9" in out


def test_write_appends_missing_key():
    text = "meta:\n  version: v9.9.9\n"
    out = write_key(text, "version", "v1.2.3")
    assert out.endswith("version: v1.2.3\n")
    assert read_key(out, "version") == "v1.2.3"


def test_write_into_empty_text():
    out = write_key("", "version", "v1.2.3")
    assert out == "version: v1.2.3\n"


def test_write_roundtrip_fallback_for_flow_mapping_document():
    # A flow mapping has no `key:` at the start of a line, so the line regex
    # cannot edit it; the full YAML round-trip still sets the value correctly.
    text = "{version: v1.2.3, other: 1}\n"
    out = write_key(text, "version", "v1.3.3")
    assert read_key(out, "version") == "v1.3.3"
    assert "other: 1" in out


def test_read_nested_path():
    text = "app:\n  build:\n    version: v1.2.3\n"
    assert read_key(text, "app.build.version") == "v1.2.3"
    assert read_key(text, "app.missing.version") is None


def test_read_list_path():
    text = "items:\n  - name: a\n    version: v1.0.0\n  - name: b\n    version: v1.1.0\n"
    assert read_key(text, "items[1].version") == "v1.1.0"


def test_write_nested_path_preserves_comments():
    text = (
        "# top comment\n"
        "app:\n"
        "  name: demo  # keep me\n"
        "  build:\n"
        "    version: v1.2.3  # pinned\n"
    )
    out = write_key(text, "app.build.version", "v1.3.3")
    assert "# top comment" in out
    assert "name: demo  # keep me" in out
    assert "version: v1.3.3  # pinned" in out
    assert read_key(out, "app.build.version") == "v1.3.3"


def test_write_nested_path_touches_only_its_own_key():
    text = "app:\n  version: v1.2.3\nlib:\n  version: v0.0.1\n"
    out = write_key(text, "app.version", "v1.3.3")
    assert "app:\n  version: v1.3.3" in out
    assert "lib:\n  version: v0.0.1" in out


def test_write_nested_quoted_segment():
    text = 'labels:\n  "app.version": v1.2.3\n'
    out = write_key(text, 'labels."app.version"', "v1.3.3")
    assert read_key(out, 'labels."app.version"') == "v1.3.3"
    assert '"app.version": v1.3.3' in out


def test_write_list_path_via_roundtrip_fallback():
    text = "items:\n  - name: a\n    version: v1.0.0\n"
    out = write_key(text, "items[0].version", "v2.0.0")
    assert read_key(out, "items[0].version") == "v2.0.0"


def test_write_creates_missing_nested_path():
    text = "app:\n  name: demo\n"
    out = write_key(text, "app.build.version", "v1.0.0")
    assert read_key(out, "app.build.version") == "v1.0.0"
    assert read_key(out, "app.name") == "demo"
