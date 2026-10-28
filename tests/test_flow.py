from auto_version_hook.flow import (
    BranchClass,
    chain_from,
    match_class,
    mermaid_graph,
    resolve_target,
)


def flow():
    return [
        BranchClass(name="main", regex=r"^(master|main)$", protected=True, policy="keep"),
        BranchClass(name="staging", regex=r"^(dev|staging)$", protected=True, target="main", policy="keep"),
        BranchClass(name="patch", regex=r"^patch", target="main", policy="increment", bump="patch"),
        BranchClass(name="feature", regex=r"^feat(ure)?", target="staging", policy="increment", bump="minor"),
        BranchClass(name="tech", regex=r"^devops/tech.+", target="staging", policy="ignore"),
    ]


def test_match_first_wins():
    classes = flow()
    assert match_class("feature/login", classes).name == "feature"
    assert match_class("feat/quick", classes).name == "feature"
    assert match_class("patch-1", classes).name == "patch"
    assert match_class("devops/tech-cleanup", classes).name == "tech"
    assert match_class("staging", classes).name == "staging"
    assert match_class("master", classes).name == "main"


def test_match_order_is_priority():
    classes = [
        BranchClass(name="a", regex=r"^x", target="main", policy="ignore"),
        BranchClass(name="b", regex=r"^x-y", target="main", policy="increment", bump="patch"),
    ]
    assert match_class("x-y", classes).name == "a"


def test_match_no_class():
    assert match_class("weird", flow()) is None


def test_chain_from():
    classes = flow()
    assert [c.name for c in chain_from(classes[3], classes)] == ["staging", "main"]
    assert [c.name for c in chain_from(classes[2], classes)] == ["main"]
    assert chain_from(classes[0], classes) == []


def test_resolve_target_direct_and_chain_walk():
    classes = flow()
    feature = classes[3]
    # staging exists -> base is staging (exact name wins)
    tcls, branch, ambiguous = resolve_target(feature, classes, ["master", "staging"])
    assert (tcls.name, branch, ambiguous) == ("staging", "staging", [])
    # no staging -> chain walks up to main
    tcls, branch, ambiguous = resolve_target(feature, classes, ["master"])
    assert (tcls.name, branch, ambiguous) == ("main", "master", [])


def test_resolve_exact_class_name_wins_over_ambiguous_regex():
    classes = flow()
    feature = classes[3]  # staging regex ^(dev|staging)$ matches both branches
    tcls, branch, ambiguous = resolve_target(feature, classes, ["master", "dev", "staging"])
    assert (tcls.name, branch, ambiguous) == ("staging", "staging", [])


def test_resolve_target_ambiguous():
    classes = flow()
    # a class not named like any branch: regex matches several -> ambiguous
    integration = BranchClass(
        name="integration", regex=r"^(dev|staging)$", protected=True, target="main", policy="keep"
    )
    feature = BranchClass(name="feature", regex=r"^feat", target="integration", policy="increment", bump="minor")
    tcls, branch, ambiguous = resolve_target(feature, [classes[0], integration, feature], ["master", "dev", "staging"])
    assert tcls.name == "integration"
    assert branch is None
    assert sorted(ambiguous) == ["dev", "staging"]


def test_resolve_target_nothing_exists():
    classes = flow()
    tcls, branch, ambiguous = resolve_target(classes[3], classes, [])
    assert (tcls, branch, ambiguous) == (None, None, [])


def test_mermaid_graph():
    out = mermaid_graph(flow())
    assert out.startswith("flowchart TD")
    for label in ("main", "staging", "patch", "feature", "tech", "protected"):
        assert label in out
    assert 'bump minor' in out
    assert "keep · catch-up" in out
    assert 'ignore' in out
    assert "-->" in out
