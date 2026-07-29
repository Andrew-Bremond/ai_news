"""Stage 1: heuristic scoring. Runs on everything, costs nothing.

The whole point is that this cuts ~500 items to ~40 so the LLM stage stays
inside a free tier forever. It is also the fallback: if every provider is
down, the digest still ships on these scores alone.
"""
from __future__ import annotations

TITLE_MULTIPLIER = 2.0
RECENCY_BONUS = 1.5  # applied to the newest third of the batch


def score_item(item, scoring: dict) -> float:
    title = (item["title"] or "").lower()
    body = (item["abstract"] or "").lower()
    haystack = f"{title} {body}"

    for bad in scoring.get("exclude", []) or []:
        if bad.lower() in haystack:
            return -1.0

    total = 0.0

    for kw, weight in (scoring.get("keywords") or {}).items():
        k = kw.lower()
        if k in title:
            total += weight * TITLE_MULTIPLIER
        elif k in body:
            total += weight

    authors_and_source = f"{item['authors'] or ''} {item['source_name'] or ''}".lower()
    for org, weight in (scoring.get("orgs") or {}).items():
        if org.lower() in authors_and_source:
            total += weight

    cats = (item["categories"] or "").split(", ")
    for cat, weight in (scoring.get("category_weights") or {}).items():
        if cat in cats:
            total += weight

    # Editorial sources are curated by humans already; give them a floor so a
    # good Lawfare piece with none of our keywords still competes.
    if item["source"] == "rss":
        total += 2.0

    return total


def rank(items, scoring: dict, keep: int) -> tuple[dict[str, float], list]:
    """Returns (all_scores, top_n_rows)."""
    scores = {it["uid"]: score_item(it, scoring) for it in items}

    # Recency bonus applies only to items that survived the exclude rules —
    # a hard drop must stay dropped no matter how fresh it is.
    live = [it for it in items if scores[it["uid"]] >= 0]
    live.sort(key=lambda r: r["published"] or "", reverse=True)
    for it in live[:max(1, len(live) // 3)]:
        scores[it["uid"]] += RECENCY_BONUS

    ranked = sorted(items, key=lambda r: scores[r["uid"]], reverse=True)
    top = [r for r in ranked if scores[r["uid"]] > 0][:keep]
    return scores, top
