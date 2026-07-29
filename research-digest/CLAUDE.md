# CLAUDE.md

Context for Claude Code sessions on this repo.

## What this is

A configurable research digest pipeline. It ingests papers and news, ranks them
in two stages, and writes a markdown draft with commentary slots for a human to
fill. Private, single-user, runs on free tiers only.

Owner: Andrew. Built partly as a portfolio artifact for data-engineering roles,
so **code clarity and defensible design decisions matter as much as working
output**. Prefer explicit and readable over clever.

## Architecture

```
arXiv API ─┐
           ├─> SQLite ─> heuristic prefilter ─> LLM re-rank ─> markdown draft
RSS feeds ─┘   (dedupe)   ~500 → 40             40 → 15        + human commentary
```

| File | Role |
|---|---|
| `config.yaml` | Provider choice, models, pipeline sizes |
| `profiles/*.yaml` | **The subject matter.** Sources, keyword weights, LLM rubric |
| `digest/sources.py` | arXiv Atom API + generic RSS/Atom, stdlib XML |
| `digest/db.py` | SQLite schema, upsert, dedupe on `uid` |
| `digest/rank.py` | Stage 1 heuristic scoring (free, runs on everything) |
| `digest/llm.py` | Provider interface + Gemini/Groq/Ollama adapters |
| `digest/summarize.py` | Stage 2 LLM re-rank, batched |
| `digest/render.py` | Markdown output with `<!-- COMMENTARY n -->` slots |
| `digest/pipeline.py` | Orchestration + config loading |
| `cli.py` | `run`, `check-feeds`, `providers`, `profiles` |
| `app.py` | Local Flask dashboard, binds 127.0.0.1 only |

## Invariants — do not break these without discussion

1. **Two-stage ranking.** The heuristic stage must run on everything and be free.
   Only the prefiltered set reaches an LLM. This is what keeps the project inside
   free tiers permanently. Never send all candidates to an LLM.

2. **Heuristic-only must always work.** `--no-llm` and provider failure both fall
   back to heuristic ranking and still produce a digest. Any new stage must
   degrade, not crash.

3. **Nothing auto-publishes.** The pipeline writes a draft and stops. The human
   commentary gate is the product.

4. **Subject matter lives in YAML, never in Python.** No keywords, feed URLs, or
   topic assumptions hardcoded in `digest/`. Adding a beat = adding a profile file.

5. **No vendor SDKs.** Providers use `requests` against REST endpoints. Deps stay
   at requests + PyYAML + Flask.

6. **A dead feed is never fatal.** `fetch_rss` collects failures and continues.

7. **Free tier only.** No paid services, no managed databases, no hosting bills.

## Conventions

- Python 3.12, `from __future__ import annotations`, type hints on public functions
- SQLite rows are `sqlite3.Row` — index by column name, not position
- Dates stored as ISO8601 UTC strings
- `uid` format: `arxiv:{base_id}` (version stripped) or `rss:{feed_name}:{guid}`
- Secrets from env vars only. Never commit a key, never add one to `config.yaml`

## State

Working and offline-tested: config/profile loading, RSS 2.0 + Atom parsing,
SQLite dedupe, heuristic ranking, markdown rendering, provider registry, dashboard.

Untested against the live internet: `fetch_arxiv`, `fetch_rss`, all three LLM
adapters. Assume these have bugs until proven otherwise.

## Next tasks, in order

1. Run `python cli.py check-feeds` and fix/remove broken RSS URLs in the profile
2. Run `--no-llm` a few times; tune `scoring.keywords` weights until the top 15 is readable
3. First live LLM run; verify each adapter's JSON parsing against real responses
4. **Eval harness**: hand-label ~20 items good/bad, measure LLM re-rank vs heuristic
   baseline on that holdout. Highest-value item in this list — it's the difference
   between "I built a pipeline" and "I measured my pipeline"
5. GitHub Actions weekly cron that opens a draft PR
6. Static site + email, only when going public

## Testing

No test suite yet — worth adding. `rank.py`, `db.py`, `render.py`, and
`sources._parse_feed` are all pure enough to test without network. Mock the
provider `complete()` method to test `summarize.py`. Start there.
