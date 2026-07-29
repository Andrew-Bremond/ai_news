"""Orchestration: ingest -> prefilter -> LLM -> render."""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import yaml

from . import db, rank, render, sources
from .llm import ProviderError, get_provider

ROOT = Path(__file__).resolve().parent.parent


def load_config(path: str | Path = None) -> dict:
    path = Path(path) if path else ROOT / "config.yaml"
    return yaml.safe_load(path.read_text())


def load_profile(name: str) -> dict:
    return yaml.safe_load((ROOT / "profiles" / f"{name}.yaml").read_text())


def list_profiles() -> list[str]:
    return sorted(p.stem for p in (ROOT / "profiles").glob("*.yaml"))


def run(config: dict, profile_name: str = None, provider_key: str = None,
        skip_llm: bool = False, log=print) -> dict:
    profile_name = profile_name or config["active_profile"]
    provider_key = provider_key or config["llm"]["provider"]
    profile = load_profile(profile_name)
    pl = config["pipeline"]

    conn = db.connect(ROOT / config["paths"]["db"])
    report = {"profile": profile_name, "provider": provider_key, "warnings": []}

    # --- ingest -----------------------------------------------------------
    arx = profile["sources"].get("arxiv") or {}
    items = []
    if arx.get("categories"):
        log(f"arXiv: {', '.join(arx['categories'])}")
        items += sources.fetch_arxiv(
            arx["categories"], pl["lookback_days"],
            arx.get("max_per_category", 150), profile_name,
        )

    feeds = profile["sources"].get("rss") or []
    if feeds:
        log(f"RSS: {len(feeds)} feeds")
        rss_items, failures = sources.fetch_rss(feeds, pl["lookback_days"], profile_name)
        items += rss_items
        for name, reason in failures:
            report["warnings"].append(f"feed '{name}' failed — {reason}")

    new, refreshed = db.upsert_items(conn, items)
    log(f"ingested {len(items)} ({new} new, {refreshed} seen before)")
    report["ingested"], report["new"] = len(items), new

    # --- prefilter --------------------------------------------------------
    since = (datetime.now(timezone.utc) - timedelta(days=pl["lookback_days"])).isoformat()
    candidates = db.undigested(conn, profile_name, since)
    scores, top = rank.rank(candidates, profile["scoring"], pl["prefilter_keep"])
    db.set_heuristic(conn, scores)
    log(f"prefilter: {len(candidates)} -> {len(top)}")
    report["candidates"], report["prefiltered"] = len(candidates), len(top)

    if not top:
        report["warnings"].append("nothing survived the prefilter — loosen keywords")
        return report

    # --- LLM --------------------------------------------------------------
    used = "heuristic-only"
    if not skip_llm:
        from .summarize import summarize_all
        try:
            provider = get_provider(provider_key, config["llm"]["models"])
            ready, reason = provider.availability()
            if not ready:
                raise ProviderError(reason)
            log(f"LLM: {provider.label} / {provider.model}")
            results, errors = summarize_all(
                provider, profile["rubric"], top, config["llm"]["batch_size"],
                on_progress=lambda d, t: log(f"  scored {d}/{t}"),
            )
            for uid, r in results.items():
                db.set_llm(conn, uid, r["score"], r["one_liner"], r["why"])
            report["warnings"] += errors
            used = f"{provider.key}/{provider.model}"
        except ProviderError as exc:
            report["warnings"].append(f"LLM stage skipped — {exc}")
            log(f"! {exc} — falling back to heuristic ranking")

    # --- select + render --------------------------------------------------
    top_uids = [r["uid"] for r in top]
    marks = ",".join("?" for _ in top_uids)
    final = conn.execute(
        f"SELECT * FROM items WHERE uid IN ({marks}) "
        "ORDER BY COALESCE(llm_score * 10, heuristic_score) DESC LIMIT ?",
        (*top_uids, pl["digest_size"]),
    ).fetchall()

    issue = date.today().isoformat()
    markdown = render.render(final, profile["name"], used, len(candidates), issue)

    out_dir = ROOT / config["paths"]["out"]
    out_dir.mkdir(parents=True, exist_ok=True)
    out_path = out_dir / f"{issue}-{profile_name}.md"
    out_path.write_text(markdown, encoding="utf-8")

    db.mark_digested(conn, [r["uid"] for r in final], issue)
    conn.close()

    log(f"wrote {out_path}")
    report["output"] = str(out_path)
    report["selected"] = len(final)
    return report
