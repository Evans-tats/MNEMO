"""
Normalizer — converts raw source files into clean Markdown.

Each normalise_*(path) function returns a NormalizedDoc containing:
  - content: the markdown text
  - title: best-guess document title
  - images: list of (src_path, suggested_slug) for any embedded images

The router `normalise(path)` dispatches by extension and parent directory.
"""

import logging
import re

from pathlib import Path
from dataclasses import dataclass,field
from typing import List, Tuple

log = logging.getLogger(__name__)

_BINARY_SUFFIXES = frozenset({".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg",
                               ".pdf", ".xlsx", ".docx", ".pptx", ".zip"})


@dataclass
class NormalizedDoc:
    content: str
    title: str 
    source_path: Path
    images: List[Tuple[Path, str]] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

def normalise(path: Path) -> NormalizedDoc | None:
    ext=path.suffix.lower()
    if  ext in _BINARY_SUFFIXES or path.parent.name == 'images':
        return None
    if ext == ".md":
        return _normalise_markdown(path)
    if ext in {".html", ".htm"}:
        return _normalise_html(path)
    if ext in {".csv", ".tsv", ".json", ".jsonl"}:
        return _normalise_data(path)
    if ext == ".pdf":
        return _normalise_pdf(path)
    if ext == "txt":
        return _normalise_text(path)
    
    log.debug("No normaliser for file %s with extension %s. Treating it as plain text", path.name, ext)
    return _normalise_text(path)

def _normalise_markdown(path: Path) -> NormalizedDoc:
    text = path.read_text(encoding="utf-8")
    
    body, metadata = _strip_frontmatter(text)
    title = metadata.get("title") or _heading_title(body) or path.stem.replace("_", " ").replace("-", " ").title()
    
    images = _collect_md_images(body, path.parent)
    return NormalizedDoc(
        content=body.strip(), 
        title=title, 
        source_path=path,
        images=images,
        metadata=metadata)

def _normalise_html(path: Path) -> NormalizedDoc:
    """HTML → Markdown via markdownify + BeautifulSoup cleanup."""
    try:
        from bs4 import BeautifulSoup
        import markdownify
    except ImportError as exc:
        log.error("HTML normalisation requires bs4+markdownify: %s", exc)
        return _normalise_text(path)

    html = path.read_text(encoding="utf-8", errors="replace")
    soup = BeautifulSoup(html, "lxml")

    # Extract title before converting
    title_tag = soup.find("title")
    h1_tag = soup.find("h1")
    title = (
        (title_tag.get_text(strip=True) if title_tag else None)
        or (h1_tag.get_text(strip=True) if h1_tag else None)
        or path.stem
    )

    # Remove boilerplate tags
    for tag in soup(["script", "style", "nav", "footer", "aside", "iframe"]):
        tag.decompose()

    # Prefer <article> or <main> if present
    body_el = soup.find("article") or soup.find("main") or soup.find("body") or soup

    md = markdownify.markdownify(
        str(body_el),
        heading_style="ATX",
        bullets="-",
        strip=["a"],          # keep text, drop href noise
    )
    md = _clean_whitespace(md)

    return NormalizedDoc(content=md, title=title, source_path=path)

def _normalise_pdf(path: Path) -> NormalizedDoc:
    """PDF → Markdown via pypdf text extraction (best-effort)."""
    try:
        from pypdf import PdfReader
    except ImportError:
        log.error("PDF normalisation requires pypdf")
        return NormalizedDoc(
            content=f"# {path.stem}\n\n*(PDF — pypdf not installed)*",
            title=path.stem,
            source_path=path,
        )

    reader = PdfReader(str(path))
    pages: list[str] = []
    for i, page in enumerate(reader.pages, 1):
        text = page.extract_text() or ""
        if text.strip():
            pages.append(f"<!-- page {i} -->\n{text}")

    content = "\n\n".join(pages)
    content = _clean_whitespace(content)

    # Attempt to get title from PDF metadata
    meta = reader.metadata or {}
    title = (
        str(meta.get("/Title", "")).strip()
        or _heading_title(content)
        or path.stem
    )

    return NormalizedDoc(content=content, title=title, source_path=path)

def _normalise_text(path: Path) -> NormalizedDoc:
    """Plain text — wrap in a markdown code block if it looks like code, else inline."""
    text = path.read_text(encoding="utf-8", errors="replace")
    code_suffixes = {".py", ".js", ".ts", ".rs", ".go", ".java", ".cpp", ".c", ".sh"}
    _lang_map = {".py": "python", ".js": "javascript", ".ts": "typescript",
                 ".sh": "bash", ".cpp": "cpp", ".c": "c"}

    if path.suffix.lower() in code_suffixes:
        lang = _lang_map.get(path.suffix.lower(), path.suffix.lstrip("."))
        content = f"```{lang}\n{text}\n```"
    else:
        content = text

    return NormalizedDoc(
        content=content.strip(),
        title=path.stem.replace("_", " ").replace("-", " ").title(),
        source_path=path,
    )
def _normalise_data(path: Path) -> NormalizedDoc:
    """
    Data files (CSV/JSON/JSONL) → markdown summary with schema + sample rows.
    The full data is NOT embedded — just a representative sample.
    """
    suffix = path.suffix.lower()
    max_rows = 20

    if suffix in {".csv", ".tsv"}:
        content = _summarise_csv(path, max_rows)
    elif suffix == ".json":
        content = _summarise_json(path)
    elif suffix == ".jsonl":
        content = _summarise_jsonl(path, max_rows)
    else:
        content = _normalise_text(path).content

    return NormalizedDoc(
        content=content,
        title=path.stem.replace("_", " ").title() + " (dataset)",
        source_path=path,
    )



def _strip_frontmatter(text: str) -> tuple[str, dict[str, str]]:
    """
    Extracts YAML frontmatter and returns the body and a dictionary of metadata.
    Supports standard '---' delimiters.
    """
    # Regex looks for '---' at the start, captures everything until the next '---'
    # on its own line, then captures the remaining text as the body.
    pattern = r'^---\s*\n(.*?)\n---\s*\n'
    match = re.match(pattern, text, re.DOTALL)
    
    fm: dict[str, str] = {}
    
    if not match:
        return text, fm

    fm_block = match.group(1)
    body = text[match.end():]

    for line in fm_block.splitlines():
        if ":" in line:
            # Partition on the first colon only
            key, _, value = line.partition(":")
            # Clean up keys and values (removing quotes and extra spaces)
            fm[key.strip()] = value.strip().strip('"').strip("'")

    return body, fm

def _heading_title(md: str) -> str:
    """Extract first ATX heading as title."""
    for line in md.splitlines():
        line = line.strip()
        if line.startswith("# "):
            return line[2:].strip()
    return ""

    
def _collect_md_images(md: str, base_dir: Path) -> list[tuple[Path, str]]:
    """Return list of (resolved_path, slug) for local images referenced in markdown."""
    results: list[tuple[Path, str]] = []
    # ![alt](path) and [[path.png]]
    patterns = [
        r"!\[.*?\]\(([^)]+)\)",
        r"\[\[([^\]]+\.(?:png|jpg|jpeg|gif|webp|svg))\]\]",
    ]
    for pat in patterns:
        for match in re.finditer(pat, md, re.IGNORECASE):
            src = match.group(1).strip()
            if src.startswith(("http://", "https://")):
                continue
            resolved = (base_dir / src).resolve()
            if resolved.exists():
                slug = resolved.stem
                results.append((resolved, slug))
    return results

def _clean_whitespace(text: str) -> str:
    """Collapse 3+ blank lines → 2, strip trailing whitespace per line."""
    lines = [l.rstrip() for l in text.splitlines()]
    out: list[str] = []
    blanks = 0
    for line in lines:
        if line == "":
            blanks += 1
            if blanks < 3:
                out.append("")
        else:
            blanks = 0
            out.append(line)
    return "\n".join(out).strip()

def _summarise_csv(path: Path, max_rows: int) -> str:
    import csv
    lines: list[str] = []
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            reader = csv.reader(fh)
            rows = list(reader)
        if not rows:
            return f"# {path.stem}\n\n*(empty CSV)*"
        headers = rows[0]
        sample = rows[1 : max_rows + 1]
        total = len(rows) - 1

        lines.append(f"# {path.stem}\n")
        lines.append(f"**Rows:** {total}  **Columns:** {len(headers)}\n")
        lines.append("## Schema\n")
        lines.append("| Column | Sample values |")
        lines.append("|--------|--------------|")
        for i, h in enumerate(headers):
            vals = ", ".join(str(r[i]) for r in sample[:5] if i < len(r))
            lines.append(f"| {h} | {vals} |")
        lines.append(f"\n## Sample ({min(max_rows, total)} of {total} rows)\n")
        lines.append("| " + " | ".join(headers) + " |")
        lines.append("|" + "|".join(["---"] * len(headers)) + "|")
        for row in sample:
            lines.append("| " + " | ".join(str(v) for v in row) + " |")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"*(Could not parse CSV: {exc})*")
    return "\n".join(lines)


def _summarise_json(path: Path) -> str:
    import json as _json
    try:
        data = _json.loads(path.read_text(encoding="utf-8", errors="replace"))
        preview = _json.dumps(data, indent=2, ensure_ascii=False)[:3000]
        return f"# {path.stem}\n\n```json\n{preview}\n```"
    except Exception as exc:  # noqa: BLE001
        return f"# {path.stem}\n\n*(Invalid JSON: {exc})*"


def _summarise_jsonl(path: Path, max_rows: int) -> str:
    import json as _json
    lines: list[str] = [f"# {path.stem}\n"]
    try:
        with path.open(encoding="utf-8", errors="replace") as fh:
            for i, line in enumerate(fh):
                if i >= max_rows:
                    break
                obj = _json.loads(line)
                lines.append(f"**Row {i+1}:** `{_json.dumps(obj, ensure_ascii=False)[:300]}`\n")
    except Exception as exc:  # noqa: BLE001
        lines.append(f"*(Parse error: {exc})*")
    return "\n".join(lines)
