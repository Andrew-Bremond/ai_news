"""Stage 2: LLM scoring + one-line summaries, on the prefiltered set only."""
from __future__ import annotations

import json

from .llm import LLMProvider, ProviderError

SYSTEM = """{rubric}

Return ONLY a JSON object of this exact shape, no prose, no markdown:
{{"items": [{{"ref": <int>, "score": <0-10>, "one_liner": "<max 25 words>",
              "why": "<max 40 words, why this matters strategically>"}}]}}
Include exactly one object per input item, keyed by its ref number."""


def _payload(batch) -> str:
    lines = []
    for i, it in enumerate(batch):
        abstract = (it["abstract"] or "")[:1200]
        lines.append(
            f"[ref {i}]\nSOURCE: {it['source_name']}\nTITLE: {it['title']}\n"
            f"TEXT: {abstract}\n"
        )
    return "\n".join(lines)


def summarize_batch(provider: LLMProvider, rubric: str, batch) -> dict[str, dict]:
    data = provider.complete_json(SYSTEM.format(rubric=rubric), _payload(batch))
    rows = data.get("items", data) if isinstance(data, dict) else data
    results: dict[str, dict] = {}
    for row in rows:
        try:
            item = batch[int(row["ref"])]
        except (KeyError, ValueError, IndexError, TypeError):
            continue
        results[item["uid"]] = {
            "score": float(row.get("score", 0)),
            "one_liner": str(row.get("one_liner", "")).strip(),
            "why": str(row.get("why", "")).strip(),
        }
    return results


def summarize_all(provider: LLMProvider, rubric: str, items, batch_size: int,
                  on_progress=None) -> tuple[dict[str, dict], list[str]]:
    """Returns (results, errors). A failed batch is skipped, not fatal —
    those items fall back to their heuristic score."""
    results: dict[str, dict] = {}
    errors: list[str] = []

    for start in range(0, len(items), batch_size):
        batch = items[start:start + batch_size]
        try:
            results.update(summarize_batch(provider, rubric, batch))
        except (ProviderError, json.JSONDecodeError, KeyError) as exc:
            errors.append(f"batch {start // batch_size}: {exc}")
        if on_progress:
            on_progress(min(start + batch_size, len(items)), len(items))

    return results, errors
