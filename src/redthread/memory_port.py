"""Porting existing memory files into a store.

Most projects meet Redthread with memory already written somewhere else —
a harness's own memory directory (`~/.claude/projects/**/memory/`), a
`docs/decisions/` folder, a pile of hand-kept notes. Telling people to
copy those in by hand is how they stay where they are, so this module
turns a path into a list of (key, text) pairs the store can accept.

Nothing here touches a store or git; it is path walking and key
derivation only, which is the part worth testing on its own.
"""

import re
from pathlib import Path

from redthread import constants

#: Extensions worth importing. Memory entries are text; anything else in a
#: notes folder (images, `.DS_Store`, a stray `.zip`) is noise, and silently
#: importing binary as UTF-8 would fail late and confusingly.
TEXT_SUFFIXES = constants.TEXT_SUFFIXES

_UNSAFE = re.compile(r"[^A-Za-z0-9._-]+")


def discover(source: Path, recursive: bool = True) -> list[Path]:
    """Text files under `source`, sorted. A file path yields just itself.

    Hidden files and directories are skipped: a `.git` inside a notes folder
    is not memory, and importing it would be both wrong and enormous.
    """
    source = Path(source)
    if source.is_file():
        return [source]
    if not source.is_dir():
        return []
    walk = source.rglob("*") if recursive else source.glob("*")
    return sorted(
        p
        for p in walk
        if p.is_file()
        and p.suffix.lower() in TEXT_SUFFIXES
        and not any(part.startswith(".") for part in p.relative_to(source).parts)
    )


def key_for(path: Path, source_root: Path) -> str:
    """The memory key for `path`, mirroring its layout under `source_root`.

    A nested source keeps its shape (`decisions/2026-01_db.md` →
    `decisions/2026-01_db`), since that structure is usually the only
    organization the notes have. Extensions are dropped — a key is a name,
    not a filename — and each segment is reduced to characters that are safe
    in every store path.
    """
    path = Path(path)
    source_root = Path(source_root)
    rel = Path(path.name) if source_root.is_file() else path.relative_to(source_root)
    parts = [_slug(part) for part in rel.with_suffix("").parts]
    parts = [p for p in parts if p]
    if not parts:
        raise ValueError(f"cannot derive a memory key from {path}")
    return "/".join(parts)


def _slug(value: str) -> str:
    """One path segment, stripped to store-safe characters.

    Leading and trailing dots go with it, so `..` (and any other all-dot
    segment) collapses to empty rather than to a traversal — callers filter
    empties out, so a hostile path can only ever lose a segment, never
    escape the namespace.
    """
    return _UNSAFE.sub("-", value).strip("-.")
