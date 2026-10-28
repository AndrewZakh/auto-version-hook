"""Version parsing and bumping driven by a user-supplied regex.

``parse_regex`` decomposes the version string into named groups; bumping a
part increments its integer in place, so everything around the bumped group
(the prefix, separators, build marks like ``-rc1`` in a ``mark`` group) is
preserved verbatim. No separate format template is needed.
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple


class VersionError(ValueError):
    """Raised when a version cannot be parsed or bumped."""


class VersionSpec:
    """A compiled parse_regex that turns version strings into RegexVersion."""

    def __init__(self, pattern: str):
        try:
            self._regex = re.compile(pattern)
        except re.error as exc:
            raise VersionError(f"invalid parse_regex {pattern!r}: {exc}") from exc
        self.pattern = pattern

    @property
    def group_names(self) -> List[str]:
        return list(self._regex.groupindex)

    def parse(self, text: str) -> "RegexVersion":
        match = self._regex.fullmatch((text or "").strip())
        if match is None:
            raise VersionError(f"version {text!r} does not match parse_regex {self.pattern!r}")
        return RegexVersion(self, match)


class RegexVersion:
    """A version string parsed against a VersionSpec."""

    def __init__(self, spec: VersionSpec, match: re.Match):
        self.spec = spec
        self.match = match
        self.text = match.group(0)

    def __str__(self) -> str:
        return self.text

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<RegexVersion {self.text!r}>"

    def __eq__(self, other: object) -> bool:
        return (
            isinstance(other, RegexVersion)
            and self.spec.pattern == other.spec.pattern
            and self.text == other.text
        )

    def __hash__(self) -> int:
        return hash((self.spec.pattern, self.text))

    def group(self, name: str) -> Optional[str]:
        return self.match.group(name)

    def numeric_groups(self) -> List[int]:
        """Values of the numeric named groups, in regex (significance) order."""
        values = []
        for name in self.spec.group_names:
            value = self.match.group(name)
            if value is not None and value.isdigit():
                values.append(int(value))
        return values

    def compare(self, other: "RegexVersion") -> int:
        """Order versions by numeric groups left-to-right; non-numeric groups
        (build marks) do not participate. Negative/zero/positive like cmp."""
        left, right = self.numeric_groups(), other.numeric_groups()
        if len(left) != len(right):  # only possible with different specs
            raise VersionError("cannot compare versions parsed by different specs")
        if left < right:
            return -1
        if left > right:
            return 1
        return 0

    def bump(self, part: str, reset_lower: bool = False) -> "RegexVersion":
        """Increment the integer in group ``part``, keeping the rest as-is.

        With reset_lower, numeric named groups located to the right of the
        bumped group are zeroed; non-numeric groups (build marks etc.) and
        groups to the left are never touched.
        """
        if part not in self.match.re.groupindex:
            raise VersionError(f"parse_regex has no group named {part!r}")
        current = self.match.group(part)
        if current is None or not current.isdigit():
            raise VersionError(f"group {part!r} value {current!r} is not an integer")
        replacements: List[Tuple[int, int, str]] = [
            (*self.match.span(part), str(int(current) + 1))
        ]
        if reset_lower:
            bumped_start = self.match.start(part)
            for name in self.match.re.groupindex:
                if name == part:
                    continue
                value = self.match.group(name)
                if value and value.isdigit() and self.match.start(name) > bumped_start:
                    replacements.append((*self.match.span(name), "0"))
        text = self.text
        for start, end, replacement in sorted(replacements, key=lambda r: r[0], reverse=True):
            text = text[:start] + replacement + text[end:]
        return self.spec.parse(text)
