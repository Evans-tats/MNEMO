"""Manifest tracks every file in raw/ by content hash.
Schema : make json file """

import hashlib
from pathlib import Path
from datetime import datetime,timezone
from typing import Optional,Any
from dataclasses import dataclass,asdict, field


_MANIFEST_VERSION = 1
_IGNORED_NAMES = frozenset({"_manifest.json", ".DS_Store", "Thumbs.db"})
_IGNORED_SUFFIXES = frozenset({".log", ".tmp", ".pyc"})

def _classify(path: Path):
    """Infer document type from parent directory name."""
    parent = path.parent.name
    mapping = {
        "articles": "article",
        "books": "book",
        "papers": "paper",
        "reports": "report",
        "repos" : "repo",
        "datasets" : "dataset",
        "images" : "image",
    }

    return mapping.get(parent, 'unknown')

def _sha256(path : Path, chunk: int = 1 << 20) -> str:
    h = hashlib.sha256()
    with path.open("rb") as fh:
        while data := fh.read(chunk):
            h.update(data)
    return h.hexdigest()

@dataclass
class ManifestEntry:
    hash: str
    source_url: str = ""
    ingest_ts: str = field(default_factory=lambda: datetime.now(timezone.utc)isoformat())
    type : str = ""
    size_bytes: int = 0

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str,Any]) -> "ManifestEntry":
        return cls(
            hash=d['hash'],
            source_url=d.get('source_url', ""),
            ingest_ts=d.get("ingest_ts",""),
            type=d.get("type",""),
            size_bytes=d.get("size_bytes",""),
        )
    
@dataclass
class ManifestDiff:
    new: list[Path]
    modified: list[Path]
    deleted: list[Path]

    @property
    def changed(self) -> list[Path]:
        return self.new + self.modified
    


class Manifest:
    """Read/Write the _manifest.json for a raw/ directory."""

    def __init__(self, rawd_Dir: Path) -> None:
        pass