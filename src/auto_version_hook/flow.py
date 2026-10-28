"""branch_flow: named branch classes forming the promotion graph.

A class describes one kind of branch: how its name is recognized (regex),
where it is promoted to (target, a class name) and what happens to the
version (policy). Targets form a DAG rooted at protected classes; see
docs/branch-flow-design.md.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import List, Optional, Sequence, Tuple

INCREMENT = "increment"
KEEP = "keep"
IGNORE = "ignore"
POLICIES = (INCREMENT, KEEP, IGNORE)


@dataclass
class BranchClass:
    name: str
    regex: str
    protected: bool = False
    target: Optional[str] = None
    policy: str = KEEP
    bump: Optional[str] = None
    reset_lower_parts: bool = False

    def matches(self, branch: str) -> bool:
        return re.search(self.regex, branch) is not None


def match_class(branch: str, classes: Sequence[BranchClass]) -> Optional[BranchClass]:
    """First class whose regex matches the branch (list order = priority)."""
    for cls in classes:
        if cls.matches(branch):
            return cls
    return None


def find_class(name: str, classes: Sequence[BranchClass]) -> Optional[BranchClass]:
    for cls in classes:
        if cls.name == name:
            return cls
    return None


def chain_from(cls: BranchClass, classes: Sequence[BranchClass]) -> List[BranchClass]:
    """Classes upwards from cls.target, in walk order (closest target first)."""
    chain: List[BranchClass] = []
    seen = {cls.name}
    current = cls
    while current.target:
        nxt = find_class(current.target, classes)
        if nxt is None or nxt.name in seen:
            break  # config validation rejects both cases
        seen.add(nxt.name)
        chain.append(nxt)
        current = nxt
    return chain


def resolve_target(
    cls: BranchClass, classes: Sequence[BranchClass], remote_branches: Sequence[str]
) -> Tuple[Optional[BranchClass], Optional[str], List[str]]:
    """Resolve the concrete base branch for a class.

    Each class of the target chain, closest first, is resolved as:
      1. a remote branch named exactly like the class -> use it;
      2. else regex matches: exactly one -> use it; several -> ambiguous
         (an error for the caller);
      3. none -> continue up the chain.

    Returns (target_class, branch, candidates):
      * branch set, candidates empty          -> resolved
      * candidates non-empty                  -> ambiguous (an error for the caller)
      * both empty                            -> nothing in the chain exists remotely
    """
    for candidate in chain_from(cls, classes):
        if candidate.name in remote_branches:
            return candidate, candidate.name, []
        matches = [b for b in remote_branches if candidate.matches(b)]
        if len(matches) == 1:
            return candidate, matches[0], []
        if len(matches) > 1:
            return candidate, None, matches
    return None, None, []


def mermaid_graph(classes: Sequence[BranchClass]) -> str:
    """The branch lifecycle graph as a Mermaid flowchart."""
    lines = ["flowchart TD"]
    for cls in classes:
        label = f"{cls.name} · {cls.regex}" + (" · protected" if cls.protected else "")
        lines.append(f'    {_node_id(cls.name)}["{label}"]')
    for cls in classes:
        if not cls.target:
            continue
        target = find_class(cls.target, classes)
        if target is None:
            continue
        if cls.policy == INCREMENT:
            edge = f"bump {cls.bump}"
        elif cls.policy == KEEP:
            edge = "keep · catch-up"
        else:
            edge = "ignore"
        lines.append(f'    {_node_id(cls.name)} -->|"{edge}"| {_node_id(target.name)}')
    return "\n".join(lines)


def _node_id(name: str) -> str:
    return "c_" + re.sub(r"[^A-Za-z0-9_]", "_", name)
