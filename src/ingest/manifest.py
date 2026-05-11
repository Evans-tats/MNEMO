"""Manifest tracks every file in raw/ by content hash.
Schema : make json file """

import hashlib
import json
import logging
from pathlib import Path
from datetime import datetime,timezone
from typing import Optional,Any
from dataclasses import dataclass,asdict, field

logging.basicConfig(level=logging.INFO)
log = logging.getLogger(__name__)

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
    ingest_ts: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    type : str = "unknown"
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
    
    @property
    def has_changed(self) -> bool:
        return bool(self.new or self.modified or self.deleted)
    
    @property
    def summary(self) -> str:
        parts = []
        if self.new:
            parts.append(f"{len(self.new)} new")
        if self.modified:
            parts.append(f"{len(self.modified)} modified")
        if self.deleted:
            parts.append(f"{len(self.deleted)} deleted")
        return ", ".join(parts) if parts else "no changes"  

class Manifest:
    """Read/Write the _manifest.json for a raw/ directory."""

    def __init__(self, raw_Dir: Path) -> None:
        self._raw_dir = raw_Dir.resolve()
        self._path = self._raw_dir / "_manifest.json"
        self._entries: dict[str,ManifestEntry] = {}
        self._load()

    def scan(self) -> ManifestDiff:
        on_disk : dict[str,ManifestEntry] ={}
        for path in (self._raw_dir.rglob("*")):
            if not path.is_file():
                continue
            if path.name in _IGNORED_NAMES:
                continue
            if path.suffix in _IGNORED_SUFFIXES:
                continue
            rel = str(path.relative_to(self._raw_dir))
            try:
                h= _sha256(path)
            except OSError as exc:
                log.warning("cannot hash %s: %s", path, exc)
                continue
            existing = self._entries.get(rel)
            is_unchanged = existing and existing.hash == h

            on_disk[rel] = ManifestEntry(
                hash=h,
                source_url=existing.source_url if is_unchanged else "",
                ingest_ts=existing.ingest_ts if is_unchanged else datetime.now(timezone.utc).isoformat(),
                type=_classify(path),
                size_bytes=path.stat().st_size,
            )
            perv_keys = set(self.entries)
            curr_keys = set(on_disk)

            new =sorted(curr_keys - perv_keys)
            deleted = sorted(perv_keys - curr_keys)
            modified = sorted(
                k for k in (curr_keys & perv_keys)
                if on_disk[k].hash != self._entries[k].hash
            )
            self._entries = on_disk
            return ManifestDiff(
                new=[Path(p) for p in new],
                modified=[Path(p) for p in modified],
                deleted=[Path(p) for p in deleted],
            )
        
    def update_url(self, rel_path: Path | str, url:str) -> None:
        """Update the source URL for a given file."""
        key = str(rel_path)
        if key in self._entries:
            self._entries[key].source_url = url
        else:
            log.warning("Cannot update URL for %s: not found in manifest", rel_path)
    
    def get(self, rel_path: Path | str) -> Optional[ManifestEntry]:
        """Get the manifest entry for a given file."""
        return self._entries.get(str(rel_path))
    
    def all_entries(self) -> dict[str, ManifestEntry]:
        """Return all manifest entries."""
        return self._entries
    
    def save(self) -> None:
        """Write the manifest to disk."""
        payload = {
            "version": _MANIFEST_VERSION,
            "entries": {k: v.to_dict() for k, v in self._entries.items()},
        }
        tmp = self._path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, indent=2, ensure_ascii=False),encoding="utf-8")
        tmp.replace(self._path)
        log.debug("Manifest saved with %d entries", len(self._entries))

    def stats(self) -> dict[str,int]:
        counts : dict[str,int] = {}
        for entry in self._entries.values():
            counts[entry.type] = counts.get(entry.type, 0) + 1
        return counts
    
    def _load(self) -> None:
        if not self._path.is_file():
            log.info("No manifest found at %s, starting fresh.", self._path)
            return
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            if data.get("version") != _MANIFEST_VERSION:
                log.warning("Manifest version mismatch: expected %d, got %s. Ignoring existing manifest.", _MANIFEST_VERSION, data.get("version"))
                return
            entries = data.get("entries", {})
            self._entries = {k: ManifestEntry.from_dict(v) for k, v in entries.items()}
            log.info("Loaded manifest with %d entries from %s", len(self._entries), self._path)
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Failed to load manifest from %s: %s. Starting fresh.", self._path, exc)