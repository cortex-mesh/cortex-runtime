"""Memory file constants and the MemoryStore Protocol for cortex_runtime.

Defines the closed set of memory file names, typed memory categories,
write modes, and the MemoryStore structural protocol.
"""

from __future__ import annotations

import re
from enum import StrEnum
from typing import TYPE_CHECKING, Protocol, runtime_checkable

if TYPE_CHECKING:
    from pathlib import Path


# ── Memory file names ────────────────────────────────────────────────────


class MemoryFile(StrEnum):
    """Named memory files shared across the mesh."""

    CHARTER = "CHARTER"
    USER = "USER"
    SKILLS = "SKILLS"
    CONTEXT = "CONTEXT"
    PEOPLE = "PEOPLE"
    PROJECTS = "PROJECTS"
    DECISIONS = "DECISIONS"


# ── Typed memory categories (ADR-056) ────────────────────────────────────


class TypedMemoryCategory(StrEnum):
    """Categories for typed memory files."""

    PEOPLE = "people"
    PROJECTS = "projects"
    DECISIONS = "decisions"
    REFERENCE = "reference"
    FEEDBACK = "feedback"


TYPED_CATEGORIES: frozenset[str] = frozenset(c.value for c in TypedMemoryCategory)

PROPOSED_DIRNAME = "_proposed"
"""Directory name for staged (pending-approval) typed memory proposals."""


def is_safe_typed_name(name: str) -> bool:
    """Return True if *name* is safe to use as a typed memory filename.

    Accepts only lowercase letters, digits, and hyphens — no path traversal
    characters. This is enforced on the write path, not the parse path.
    """
    return bool(re.fullmatch(r"[a-z0-9][a-z0-9\-]*", name))


# ── Write modes ──────────────────────────────────────────────────────────


class MemoryWriteMode(StrEnum):
    """How to write a typed memory proposal."""

    CREATE = "create"
    UPDATE = "update"


# ── Agent-specific files ──────────────────────────────────────────────────


class AgentFile(StrEnum):
    """Named files inside an agent's memory directory."""

    MEMORY = "MEMORY"
    CHARTER = "CHARTER"


# ── MemoryStore Protocol ─────────────────────────────────────────────────


@runtime_checkable
class MemoryStore(Protocol):
    """Protocol for reading and writing mesh memory files.

    Implementations may be filesystem-backed, Redis-backed, or in-memory
    (for tests). All methods are synchronous.
    """

    def read(self, file: MemoryFile | str) -> str:
        """Read a named memory file. Returns empty string if not found."""
        ...

    def write(self, file: MemoryFile | str, content: str) -> None:
        """Write (overwrite) a named memory file."""
        ...

    def read_typed(self, category: TypedMemoryCategory | str, name: str) -> str:
        """Read a typed memory file. Returns empty string if not found."""
        ...

    def write_typed(
        self,
        category: TypedMemoryCategory | str,
        name: str,
        content: str,
        mode: MemoryWriteMode = MemoryWriteMode.CREATE,
    ) -> None:
        """Write a typed memory file."""
        ...

    def list_typed(self, category: TypedMemoryCategory | str) -> list[str]:
        """List names of typed memory files in *category*."""
        ...

    def base_path(self) -> Path:
        """Return the root path for this memory store."""
        ...
