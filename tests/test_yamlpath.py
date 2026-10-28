import pytest

from auto_version_hook.yamlpath import (
    INDEX,
    KEY,
    MISSING,
    PathError,
    Segment,
    get_by_path,
    parse_path,
    set_by_path,
)


def segs(*items):
    return [Segment(kind, value) for kind, value in items]


def test_parse_dotted_path():
    assert parse_path("app.build.version") == segs((KEY, "app"), (KEY, "build"), (KEY, "version"))


def test_parse_leading_dot_tolerated():
    assert parse_path(".app.version") == segs((KEY, "app"), (KEY, "version"))


def test_parse_list_index():
    assert parse_path("items[0].version") == segs(
        (KEY, "items"), (INDEX, 0), (KEY, "version")
    )
    assert parse_path("items[-1]")[-1] == Segment(INDEX, -1)


def test_parse_quoted_segment_with_dot():
    assert parse_path('labels."app.version"') == segs((KEY, "labels"), (KEY, "app.version"))


def test_parse_quoted_segment_in_brackets():
    assert parse_path("a['x y']") == segs((KEY, "a"), (KEY, "x y"))


@pytest.mark.parametrize("bad", ["", "   ", ".", "a[", "a[x]", "a[-]", 'a."b', "a[]"])
def test_parse_rejects_garbage(bad):
    with pytest.raises(PathError):
        parse_path(bad)


def test_get_nested():
    data = {"app": {"build": {"version": "v1"}}}
    assert get_by_path(data, parse_path("app.build.version")) == "v1"


def test_get_list_index():
    data = {"items": [{"version": "v1"}, {"version": "v2"}]}
    assert get_by_path(data, parse_path("items[1].version")) == "v2"


def test_get_missing_returns_sentinel():
    data = {"app": {"name": "x"}}
    assert get_by_path(data, parse_path("app.version")) is MISSING
    assert get_by_path(data, parse_path("app.name.version")) is MISSING
    assert get_by_path(data, parse_path("items[9].version")) is MISSING
    assert get_by_path(data, parse_path("app[0]")) is MISSING


def test_set_existing_nested():
    data = {"app": {"build": {"version": "v1"}}}
    set_by_path(data, parse_path("app.build.version"), "v2")
    assert data["app"]["build"]["version"] == "v2"


def test_set_creates_missing_mappings():
    data = {}
    set_by_path(data, parse_path("app.build.version"), "v1")
    assert data == {"app": {"build": {"version": "v1"}}}


def test_set_list_index():
    data = {"items": [{"version": "v1"}]}
    set_by_path(data, parse_path("items[0].version"), "v2")
    assert data["items"][0]["version"] == "v2"


def test_set_rejects_out_of_range_index():
    data = {"items": [{"version": "v1"}]}
    with pytest.raises(PathError, match="out of range"):
        set_by_path(data, parse_path("items[3].version"), "v")


def test_set_rejects_index_into_missing_mapping():
    with pytest.raises(PathError, match="not a list"):
        set_by_path({}, parse_path("items[3].version"), "v")


def test_set_rejects_scalar_mid_path():
    with pytest.raises(PathError, match="not a mapping"):
        set_by_path({"app": "scalar"}, parse_path("app.build.version"), "v")
