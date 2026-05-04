MNEMO

# knowledge-base

An LLM-powered personal knowledge base. Raw source documents (articles, papers,
repos, datasets, images) are ingested into `raw/`, then an LLM incrementally
compiles them into a structured Markdown wiki in `wiki/`. The wiki is operated
on by a Q&A agent, a hybrid search CLI, and a linter — all viewable in Obsidian.

---

## Quick start

```bash
# 1. Clone and set up
git clone <repo>
cd knowledge-base
python -m venv .venv && source .venv/bin/activate
make dev-install

# 2. Configure
cp .env.example .env
# Edit .env — set ANTHROPIC_API_KEY at minimum

# 3. Check ingest status
make status

# 4. Clip a web article
make fetch URL=https://example.com/interesting-article

# 5. Watch for changes and auto-compile
make watch

# 6. Run tests
make test
```

---

## Project structure

```
knowledge-base/
├── raw/                  Source of truth — never edited by hand
│   ├── _manifest.json    Content-hash registry (auto-maintained)
│   ├── articles/         Web-clipped .md files
│   ├── papers/           Academic papers — .md + figures/
│   ├── repos/            Repo summaries + key source files
│   ├── datasets/         Schema summaries + sample data
│   └── images/           All downloaded images
│
├── wiki/                 LLM-owned — do not edit manually
│   ├── _index.md         Master TOC with 1-line summaries
│   ├── _graph.json       Concept relationship graph
│   ├── _health_report.md Linter output
│   ├── concepts/         One .md per concept — synthesised articles
│   ├── sources/          One .md per raw/ file — summary + metadata
│   ├── derived/          Q&A answers and reports filed back in
│   └── visualizations/   Marp slides + matplotlib charts
│
├── src/
│   ├── config.py         Central settings (Pydantic, .env)
│   ├── ingest/
│   │   ├── manifest.py   Content-hash manifest with diff logic
│   │   ├── normalizer.py Converts all source types → Markdown
│   │   └── watcher.py    FS watcher with debounce + CLI
│   ├── compiler/
│   │   ├── compiler.py   Incremental LLM compile loop  [Phase 2]
│   │   ├── prompts.py    Prompt templates               [Phase 2]
│   │   └── wiki_writer.py Upsert articles/backlinks     [Phase 2]
│   └── agent/
│       ├── qa_agent.py   Q&A agent                      [Phase 3]
│       └── linter.py     Wiki health checks             [Phase 3]
│
└── tools/
    ├── web_fetch.py      Web clipper + image downloader
    ├── search.py         BM25 + embedding hybrid search  [Phase 3]
    ├── render.py         Marp / matplotlib renderer      [Phase 3]
    └── finetune_prep.py  QA pair → JSONL export          [Phase 4]
```

---

## Phases

| Phase | Weeks | What ships |
|-------|-------|-----------|
| **1 — Foundation** | 1–2 | Manifest, normaliser, watcher, web clipper, full test suite |
| **2 — Compiler + Wiki** | 3–5 | LLM compiler, prompt templates, wiki writer, concept graph |
| **3 — Agent + Tools** | 6–8 | Q&A agent, hybrid search, linter, Marp/matplotlib renderer |
| **4 — Product + Tune** | 9–12 | Fine-tune prep, web UI, MCP server, confidence scores |

---

## Daily workflow

```bash
# Add an article
make fetch URL=https://...

# Add with images downloaded locally
make fetch-images URL=https://...

# Batch-clip a list of URLs
kb-fetch batch urls.txt --images

# Check what's in raw/
make status

# Manually trigger compile (usually automatic via watch)
make compile

# Ask a question
make qa Q="What are the key differences between RLHF and DPO?"

# Search
make search Q="attention mechanism transformers"

# Health check the wiki
make lint
```

---

## Configuration

All settings are environment variables (or `.env`):

| Variable | Default | Description |
|----------|---------|-------------|
| `ANTHROPIC_API_KEY` | — | **Required** |
| `ANTHROPIC_MODEL` | `claude-opus-4-5-20251101` | Model for compilation + Q&A |
| `KB_RAW_DIR` | `./raw` | Raw source directory |
| `KB_WIKI_DIR` | `./wiki` | Compiled wiki directory |
| `KB_CHUNK_SIZE` | `6000` | Max tokens per normaliser chunk |
| `KB_MERGE_BATCH` | `5` | Concept articles merged per LLM call |
| `KB_STUB_MIN_WORDS` | `200` | Min words for a non-stub concept article |
| `KB_DEBOUNCE_SECONDS` | `3.0` | FS watch quiet period before compile |
| `KB_EMBED_MODEL` | `all-MiniLM-L6-v2` | Sentence-transformers model for search |
| `KB_SEARCH_BLEND` | `0.5` | BM25 vs embedding blend (0=BM25, 1=embed) |
| `KB_SEARCH_TOP_K` | `10` | Number of search results |

---

## Obsidian setup

1. Open the `knowledge-base/` folder as an Obsidian vault.
2. The `wiki/` folder is your compiled knowledge — Obsidian's graph view shows the concept relationships from `_graph.json`.
3. Install **Marp for Obsidian** to render `wiki/visualizations/slides-*.md` as slideshows.
4. The `raw/` folder is also accessible — click through from any `wiki/sources/` file to the original.

Recommended Obsidian plugins:
- **Dataview** — query concept articles by frontmatter fields
- **Marp** — render slide outputs
- **Kanban** — track `_stub-candidates.md` as a task board

---

## Development

```bash
make fmt      # ruff format + lint fix
make check    # mypy type-check
make test     # pytest with coverage
```

Coverage targets: `src/ingest/` ≥ 90%, `tools/web_fetch.py` ≥ 80%.

