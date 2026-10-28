import pytest

from auto_version_hook.versions import VersionError, VersionSpec

DEFAULT = VersionSpec(r"^v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+)$")
MARKED = VersionSpec(r"^v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<hotfix>\d+)-(?P<mark>.+)$")


def test_group_names():
    assert DEFAULT.group_names == ["major", "minor", "patch"]
    assert MARKED.group_names == ["major", "minor", "hotfix", "mark"]


def test_bump_examples_from_spec():
    base = DEFAULT.parse("v1.2.3")
    assert str(base.bump("major")) == "v2.2.3"
    assert str(base.bump("minor")) == "v1.3.3"
    assert str(base.bump("patch")) == "v1.2.4"


def test_bump_preserves_everything_outside_the_group():
    base = MARKED.parse("v1.2.3-rc1")
    assert str(base.bump("minor")) == "v1.3.3-rc1"
    assert str(base.bump("hotfix")) == "v1.2.4-rc1"
    assert base.bump("hotfix").group("mark") == "rc1"


def test_reset_lower_zeroes_numeric_groups_to_the_right_only():
    assert str(MARKED.parse("v1.2.3-rc1").bump("major", reset_lower=True)) == "v2.0.0-rc1"
    assert str(MARKED.parse("v1.2.3-rc1").bump("minor", reset_lower=True)) == "v1.3.0-rc1"


def test_multidigit_numbers():
    assert str(DEFAULT.parse("v1.2.9").bump("patch")) == "v1.2.10"
    assert str(DEFAULT.parse("v1.9.9").bump("minor")) == "v1.10.9"


@pytest.mark.parametrize("bad", ["", "  ", "1.2.3", "v1.2", "v1.2.3.4", "V1.2.3"])
def test_parse_rejects_nonmatching(bad):
    with pytest.raises(VersionError, match="does not match"):
        DEFAULT.parse(bad)


def test_bump_unknown_group():
    with pytest.raises(VersionError, match="no group named"):
        DEFAULT.parse("v1.2.3").bump("hotfix")


def test_bump_non_numeric_group():
    spec = VersionSpec(r"^v(?P<major>\d+)\.(?P<minor>\d+)\.(?P<patch>\d+|dev)$")
    with pytest.raises(VersionError, match="not an integer"):
        spec.parse("v1.2.dev").bump("patch")


def test_invalid_parse_regex():
    with pytest.raises(VersionError, match="parse_regex"):
        VersionSpec(r"^v(?P<major>\d+")


def test_equality_and_hash():
    assert DEFAULT.parse("v1.2.3") == DEFAULT.parse("v1.2.3")
    assert DEFAULT.parse("v1.2.3") != DEFAULT.parse("v1.2.4")
    assert len({DEFAULT.parse("v1.2.3"), DEFAULT.parse("v1.2.3")}) == 1
    assert str(DEFAULT.parse(" v1.2.3 ")) == "v1.2.3"  # surrounding whitespace stripped


def test_compare_orders_by_numeric_groups():
    low = DEFAULT.parse("v1.2.3")
    high = DEFAULT.parse("v1.5.0")
    assert low.compare(high) < 0
    assert high.compare(low) > 0
    assert low.compare(DEFAULT.parse("v1.2.3")) == 0


def test_compare_ignores_non_numeric_groups():
    rc1 = MARKED.parse("v1.2.3-rc1")
    rc2 = MARKED.parse("v1.2.3-rc2")
    assert rc1.compare(rc2) == 0
    assert rc1.compare(MARKED.parse("v1.2.4-rc1")) < 0
