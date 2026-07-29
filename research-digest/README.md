# research-digest

A configurable pipeline that ingests papers and news, ranks them, and drafts a
weekly digest for you to write commentary on. Private by default. Runs entirely
on free tiers.

**The subject is data, not code.** `profiles/*.yaml` defines what the desk cares
about — sources, keywords, and the LLM ranking rubric. Swap the profile and the
same pipeline covers a different beat. Ships with `ai-geopolitics`.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# Pick at least one. All three are free.
export GEMINI_API_KEY=...     # aistudio.google.com/apikey
export GROQ_API_KEY=...       # console.groq.com/keys
# or run Ollama locally: ollama pull llama3.1:8b
```

## Use

```bash
python cli.py providers        # which backends are usable right now
python cli.py check-feeds      # validate the profile's RSS URLs — do this first
python cli.py run              # full pipeline
python cli.py run --no-llm     # heuristics only, zero API calls
python app.py                  # dashboard at 127.0.0.1:5000
```

Output lands in `out/YYYY-MM-DD-<profile>.md` with `<!-- COMMENTARY n -->`
blocks left open. Fill those in. That's the product.

## How it works

```
arXiv API ─┐
           ├─> SQLite (dedupe on uid) ─> heuristic prefilter ─> LLM re-rank ─> markdown draft
RSS feeds ─┘                              ~500 → 40             40 → 15        + your commentary
```

Three decisions worth knowing about:

**Two-stage ranking.** The heuristic stage is free and runs on everything; only
~40 items reach an LLM. This is what keeps the project inside a free tier
permanently rather than for a month. It's also the fallback — if every provider
is unavailable, the digest still ships on heuristic scores alone.

**Nothing publishes itself.** The pipeline writes a draft and stops. The human
gate is deliberate; everything upstream of it is commodity.

**Providers are pluggable.** `digest/llm.py` holds one interface and three
adapters, no vendor SDKs. Adding a fourth is a class plus a registry line.
Each reports `availability()` so the dashboard shows what's usable before you
submit rather than failing mid-run.

## Adding a profile

Copy `profiles/ai-geopolitics.yaml`, change `sources`, `scoring`, and `rubric`.
It appears in the CLI and the dashboard dropdown automatically.

## Not done yet

- [ ] Verify the shipped RSS URLs (`check-feeds`) — think-tank feeds move
- [ ] Tune keyword weights against 2–3 real runs before trusting the ranking
- [ ] Hold out ~20 items you've hand-labelled; measure LLM ranking against them
- [ ] GitHub Actions weekly cron opening a draft PR
- [ ] Static site + Buttondown when you go public
