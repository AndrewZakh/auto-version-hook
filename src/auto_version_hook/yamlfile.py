"""Reading and editing a value at a yq-style path in a YAML file.

Editing is done line-oriented (descending through nested block mappings by
indentation) so that comments, quoting style and the surrounding layout of
the file are preserved. A full YAML round-trip is only used as a fallback,
for paths the line editor cannot handle (list indices, flow collections,
missing nested keys).
"""

from __future__ import annotations

import re
from typing import List, Optional, Tuple

import yaml

from .yamlpath import (
    KEY,
    Segment,
    get_by_path,
    parse_path,
    set_by_path,
)
from .yamlpath import (
    MISSING as _MISSING,
)
from .yamlpath import (
    PathError as _PathError,
)


class VersionFileError(ValueError):
    """Raised when the version file cannot be parsed or updated."""


def read_key(text: str, path: str) -> Optional[str]:
    """Return the raw string value at ``path``, or None if it is absent."""
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise VersionFileError(f"invalid YAML: {exc}") from exc
    value = get_by_path(data, parse_path(path))
    if value is _MISSING or value is None:
        return None
    if not isinstance(value, str):
        value = str(value)
    return value.strip()


def write_key(text: str, path: str, value: str) -> str:
    """Set the value at ``path`` and return the new file text."""
    segments = parse_path(path)

    new_text = _write_block_mapping_text(text, segments, value)
    if new_text is not None and _current_value(new_text, path) == value:
        return new_text

    # A missing top-level key is appended at the end of the file, which
    # preserves comments everywhere else.
    if new_text is None and len(segments) == 1 and segments[0].type == KEY:
        if not text.strip():
            candidate = f"{segments[0].value}: {value}\n"
        else:
            candidate = text.rstrip("\n") + f"\n{segments[0].value}: {value}\n"
        if _current_value(candidate, path) == value:
            return candidate

    # Fallback: full YAML round-trip (loses comments, but handles list
    # indices, flow collections and missing nested paths).
    try:
        data = yaml.safe_load(text)
    except yaml.YAMLError as exc:
        raise VersionFileError(f"invalid YAML: {exc}") from exc
    if data is None:
        data = {}
    try:
        set_by_path(data, segments, value, create=True)
    except _PathError as exc:
        raise VersionFileError(f"cannot set {path!r}: {exc}") from exc
    fallback = yaml.safe_dump(data, sort_keys=False, default_flow_style=False, allow_unicode=True)
    if _current_value(fallback, path) != value:
        raise VersionFileError(f"failed to set {path!r} in the YAML document")
    return fallback


_KEY_LINE_TEMPLATE = r"""^(?P<indent>[ \t]*)(?P<open>["']?)(?P<key>%s)(?P=open)[ \t]*:(?P<rest>.*)$"""


def _write_block_mapping_text(text: str, segments: List[Segment], value: str) -> Optional[str]:
    """Line-oriented edit of an all-mapping path; None when not applicable."""
    if any(seg.type != KEY for seg in segments):
        return None
    lines = text.splitlines(keepends=True)
    search_from = 0
    parent_indent: Optional[int] = None  # None = top level (indent must be 0)
    final: Optional[Tuple[int, re.Match]] = None
    for position, seg in enumerate(segments):
        regex = re.compile(_KEY_LINE_TEMPLATE % re.escape(seg.value))
        found: Optional[Tuple[int, re.Match]] = None
        j = search_from
        while j < len(lines):
            body, _terminator = _split_line(lines[j])
            stripped = body.strip()
            if not stripped or stripped.startswith("#"):
                j += 1
                continue
            indent = len(body) - len(body.lstrip(" \t"))
            if parent_indent is not None and indent <= parent_indent:
                return None  # the parent's block ended without this key
            match = regex.match(body)
            if match and (position > 0 or match.group("indent") == ""):
                found = (j, match)
                break
            j += 1
        if found is None:
            return None
        line_index, match = found
        search_from = line_index + 1
        parent_indent = len(match.group("indent"))
        final = found

    line_index, match = final  # type: ignore[union-attr]
    body, terminator = _split_line(lines[line_index])
    rest = re.match(r"^(?P<sep>\s*)(?P<value>.*?)(?P<trailing>\s*(?:#.*)?)$", match.group("rest"))
    old = rest.group("value").strip()
    quote = ""
    if len(old) >= 2 and old[0] in ("\"", "'") and old[-1] == old[0]:
        quote = old[0]
    replacement = f"{rest.group('sep')}{quote}{value}{quote}{rest.group('trailing')}"
    new_body = body[: match.start("rest")] + replacement + body[match.end("rest"):]
    lines[line_index] = new_body + terminator
    return "".join(lines)


def _split_line(line: str) -> Tuple[str, str]:
    """Split a line into (body, line terminator)."""
    body = line[:-1] if line.endswith("\n") else line
    if body.endswith("\r"):
        return body[:-1], "\r\n"
    return body, "\n" if line.endswith("\n") else ""


def _current_value(text: str, path: str) -> Optional[str]:
    try:
        return read_key(text, path)
    except VersionFileError:
        return None
