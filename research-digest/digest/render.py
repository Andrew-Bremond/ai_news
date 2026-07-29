"""Render the digest to markdown with commentary slots left open.

The commentary blocks are the product. Everything above them is plumbing.
They render as HTML comments so an unfilled draft is obvious but harmless.
"""
from __future__ import annotations

from datetime import date

HEADER = """---
title: "{profile_name} — {issue_date}"
date: {issue_date}
provider: {provider}
items: {count}
---

# {profile_name}
### Issue of {issue_date}

<!-- TOP-LINE: two or three sentences. What actually moved this week?
     Write this last, after you've read the items below. -->

"""

ITEM = """## {n}. {title}

**{source_name}** · [{link_label}]({url}){date_suffix}

{one_liner}

*Why it matters:* {why}

<!-- COMMENTARY {n}: your take. Delete this block if you have nothing to add —
     an empty take is worse than no take. -->

"""

FOOTER = """---

<!-- ALSO NOTED: one-line mentions that didn't earn a full slot. -->

<sub>Ranked from {total} candidates by {provider}. Scores are advisory.</sub>
"""


def render(rows, profile_name: str, provider: str, total_candidates: int,
           issue_date: str | None = None) -> str:
    issue_date = issue_date or date.today().isoformat()

    parts = [HEADER.format(
        profile_name=profile_name,
        issue_date=issue_date,
        provider=provider,
        count=len(rows),
    )]

    for n, r in enumerate(rows, 1):
        pub = (r["published"] or "")[:10]
        parts.append(ITEM.format(
            n=n,
            title=r["title"],
            source_name=r["source_name"],
            link_label="arXiv" if r["source"] == "arxiv" else "read",
            url=r["url"] or "",
            date_suffix=f" · {pub}" if pub else "",
            one_liner=r["llm_one_liner"] or _fallback(r),
            why=r["llm_why"] or "_(no LLM pass — heuristic selection)_",
        ))

    parts.append(FOOTER.format(total=total_candidates, provider=provider))
    return "".join(parts)


def _fallback(row) -> str:
    text = (row["abstract"] or "").strip()
    return (text[:220] + "…") if len(text) > 220 else (text or "_no abstract_")
