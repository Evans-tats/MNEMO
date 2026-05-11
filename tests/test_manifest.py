import pytest
from pathlib import Path

from src.ingest.manifest import Manifest, ManifestEntry, _classify, _sha256


@pytest.fixture
def raw_dir(tmp_path: Path) -> Path:
    d = tmp_path / "raw"
    for sub in ("articles", "papers", "repos", "datasets", "images"):
        (d / sub).mkdir(parents=True)
    return d


def _write(path: Path, content: str = "hello") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path

def test_sha256_deterministic(tmp_path: Path):
    f = tmp_path / "a.txt"
    f.write_bytes(b"hello world")
    h1 = _sha256(f)
    h2 = _sha256(f)
    assert h1 == h2
    assert len(h1) == 64  # hex sha256

def test_sha256_different_content(tmp_path: Path):
    f1 = tmp_path / "a.txt"
    f2 = tmp_path / "b.txt"
    f1.write_bytes(b"hello world")
    f2.write_bytes(b"goodbye world")
    h1 = _sha256(f1)
    h2 = _sha256(f2)
    assert h1 != h2

def test_classify_unknown():
    assert _classify(Path("raw/misc/file.md")) == "unknown"

def test_classify_known_dirs():
    for (name, expected) in [
        ("articles", "article"),
        ("books", "book"),
        ("papers", "paper"),
        ("reports", "report"),
        ("repos", "repo"),
        ("datasets", "dataset"),
        ("images", "image"),
    ]:
        path = Path(f"raw/{name}/file.md")
        assert _classify(path=path) == expected, f"Expected {_classify(path)} to be {expected} for path {path}"


