"""Paths into YAML documents, yq-style.

Supported syntax:
    a.b.c            nested mapping keys
    a.b[0].c         list items by index (negative indices allowed)
    a."b.c".d        quoted segment: a key containing dots or spaces
    a['b c']         quoted segment in brackets

A path parses into a list of Segments; get_by_path/set_by_path navigate
plain Python data (dicts/lists) produced by yaml.safe_load.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, List, Tuple, Union

KEY = "key"
INDEX = "index"


class PathError(ValueError):
    """Raised for malformed paths or paths that cannot be applied to the data."""


@dataclass(frozen=True)
class Segment:
    type: str  # KEY or INDEX
    value: Union[str, int]


class _Missing:
    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return "<missing>"


MISSING = _Missing()


def parse_path(path: str) -> List[Segment]:
    path = (path or "").strip()
    if not path:
        raise PathError("empty path")
    segments: List[Segment] = []
    i, n = 0, len(path)
    while i < n:
        ch = path[i]
        if ch == ".":
            i += 1  # separator; also tolerates a leading or doubled dot
            continue
        if ch == "[":
            i += 1
            if i < n and path[i] in "\"'":
                key, i = _read_quoted(path, i)
                if i >= n or path[i] != "]":
                    raise PathError(f"expected ']' after a quoted key: {path!r}")
                i += 1
                segments.append(Segment(KEY, key))
            else:
                end = path.find("]", i)
                if end == -1:
                    raise PathError(f"unterminated '[': {path!r}")
                token = path[i:end].strip()
                if not (token.lstrip("-").isdigit() and token not in ("", "-")):
                    raise PathError(f"invalid list index {token!r}: {path!r}")
                segments.append(Segment(INDEX, int(token)))
                i = end + 1
            continue
        if ch in "\"'":
            key, i = _read_quoted(path, i)
            segments.append(Segment(KEY, key))
            continue
        j = i
        while j < n and path[j] not in ".[":
            j += 1
        token = path[i:j].strip()
        if not token:
            raise PathError(f"empty path segment: {path!r}")
        segments.append(Segment(KEY, token))
        i = j
    if not segments:
        raise PathError(f"path has no segments: {path!r}")
    return segments


def get_by_path(data: Any, segments: List[Segment]) -> Any:
    """Walk the data; returns MISSING when any segment cannot be applied."""
    node = data
    for seg in segments:
        if seg.type == KEY:
            if not isinstance(node, dict) or seg.value not in node:
                return MISSING
            node = node[seg.value]
        else:
            if not isinstance(node, list):
                return MISSING
            try:
                node = node[seg.value]
            except IndexError:
                return MISSING
    return node


def set_by_path(data: Any, segments: List[Segment], value: Any, create: bool = True) -> Any:
    """Set ``value`` at ``segments``; creates missing intermediate mappings.

    List indices are never created: the index must already exist.
    """
    if not segments:
        raise PathError("cannot set an empty path")
    if data is None:
        if not create:
            raise PathError("document is empty")
        data = {}
    seg = segments[0]
    if seg.type == KEY:
        if not isinstance(data, dict):
            raise PathError(f"segment {seg.value!r}: parent is not a mapping")
        if len(segments) == 1:
            data[seg.value] = value
            return data
        child = data.get(seg.value)
        if child is None and create:
            child = {}
            data[seg.value] = child
        set_by_path(child, segments[1:], value, create=create)
        return data
    if not isinstance(data, list):
        raise PathError(f"segment [{seg.value}]: parent is not a list")
    try:
        child = data[seg.value]
    except IndexError as exc:
        raise PathError(f"list index {seg.value} is out of range") from exc
    if len(segments) == 1:
        data[seg.value] = value
        return data
    set_by_path(child, segments[1:], value, create=create)
    return data


def _read_quoted(path: str, i: int) -> Tuple[str, int]:
    quote = path[i]
    i += 1
    out: List[str] = []
    while i < len(path):
        ch = path[i]
        if ch == "\\" and i + 1 < len(path):
            out.append(path[i + 1])
            i += 2
            continue
        if ch == quote:
            return "".join(out), i + 1
        out.append(ch)
        i += 1
    raise PathError(f"unterminated quoted segment: {path!r}")
