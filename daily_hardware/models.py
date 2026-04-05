"""Data models."""
from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass
class Candidate:
    """Hardware project candidate."""
    source: str
    unique_id: str
    title: str
    url: str
    extra: dict[str, Any]
