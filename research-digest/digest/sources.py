"""Ingestion. Two adapters, one normalized item shape.

Normalized item:
  uid, source, source_name, external_id, title, abstract,
  authors, url, published, updated, categories
"""
from __future__ import annotations

import html
import re
import time
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

import requests

ARXIV_API = "http://export.arxiv.org/api/query"
UA = {"User-Agent": "research-digest/0.1 (personal weekly digest; contact via repo)"}
NS = {"atom": "http://www.w3.org/2005/Atom"}

_ARXIV_VERSION = re.compile(r"v\d+$")
_TAGS = re.compile(r"<[^>]+>")


def _clean(text: str | None) -> str:
    if not text:
        return ""
    return " ".join(_TAGS.sub(" ", html.unescape(text)).split())


def _iso(value: str | None) -> str | None:
    """Parse the two date formats feeds actually use, give up gracefully."""
    if not value:
        return None
    value = value.strip()
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(timezone.utc).isoformat()
    except ValueError:
        pass
    try:
        return parsedate_to_datetime(value).astimezone(timezone.utc).isoformat()
    except (TypeError, ValueError):
        return None


# ---------------------------------------------------------------- arXiv ----

def fetch_arxiv(categories: list[str], lookback_days: int, max_per_category: int,
                profile: str, sleep: float = 3.0) -> list[dict]:
    """arXiv Atom API. No key. Their guidance is one request per 3s — respect it."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    out: list[dict] = []

    for i, cat in enumerate(categories):
        if i:
            time.sleep(sleep)
        params = {
            "search_query": f"cat:{cat}",
            "sortBy": "submittedDate",
            "sortOrder": "descending",
            "max_results": max_per_category,
        }
        resp = requests.get(ARXIV_API, params=params, headers=UA, timeout=45)
        resp.raise_for_status()
        root = ET.fromstring(resp.content)

        for entry in root.findall("atom:entry", NS):
            published = _iso(entry.findtext("atom:published", default="", namespaces=NS))
            if published and datetime.fromisoformat(published) < cutoff:
                continue

            raw_id = entry.findtext("atom:id", default="", namespaces=NS).rsplit("/", 1)[-1]
            base_id = _ARXIV_VERSION.sub("", raw_id)  # v2 collapses onto v1
            cats = [c.get("term") for c in entry.findall("atom:category", NS) if c.get("term")]

            out.append({
                "uid": f"arxiv:{base_id}",
                "source": "arxiv",
                "source_name": cat,
                "external_id": base_id,
                "title": _clean(entry.findtext("atom:title", default="", namespaces=NS)),
                "abstract": _clean(entry.findtext("atom:summary", default="", namespaces=NS)),
                "authors": ", ".join(
                    _clean(a.findtext("atom:name", default="", namespaces=NS))
                    for a in entry.findall("atom:author", NS)
                ),
                "url": f"https://arxiv.org/abs/{base_id}",
                "published": published,
                "updated": _iso(entry.findtext("atom:updated", default="", namespaces=NS)),
                "categories": ", ".join(cats),
                "profile": profile,
            })
    return out


# ------------------------------------------------------------------ RSS ----

def _parse_feed(xml_bytes: bytes) -> list[dict]:
    """Handle RSS 2.0 and Atom without a dependency."""
    root = ET.fromstring(xml_bytes)
    entries = []

    for item in root.iter():
        tag = item.tag.split("}")[-1]
        if tag not in ("item", "entry"):
            continue

        def find(*names):
            for n in names:
                for child in item:
                    if child.tag.split("}")[-1] == n:
                        return child
            return None

        link_el = find("link")
        link = ""
        if link_el is not None:
            link = (link_el.get("href") or link_el.text or "").strip()

        guid_el = find("guid", "id")
        title_el = find("title")
        desc_el = find("description", "summary", "content")
        date_el = find("pubDate", "published", "updated", "date")

        title = _clean(title_el.text if title_el is not None else "")
        if not title:
            continue

        entries.append({
            "external_id": (guid_el.text or link).strip() if guid_el is not None else link,
            "title": title,
            "abstract": _clean(desc_el.text if desc_el is not None else "")[:4000],
            "url": link,
            "published": _iso(date_el.text if date_el is not None else None),
        })
    return entries


def fetch_rss(feeds: list[dict], lookback_days: int, profile: str) -> tuple[list[dict], list[tuple[str, str]]]:
    """Returns (items, failures). Failures are (feed_name, reason) — never fatal."""
    cutoff = datetime.now(timezone.utc) - timedelta(days=lookback_days)
    out: list[dict] = []
    failures: list[tuple[str, str]] = []

    for feed in feeds:
        name, url = feed["name"], feed["url"]
        try:
            resp = requests.get(url, headers=UA, timeout=30)
            resp.raise_for_status()
            entries = _parse_feed(resp.content)
        except Exception as exc:  # a dead feed must not kill the run
            failures.append((name, f"{type(exc).__name__}: {exc}"))
            continue

        for e in entries:
            if e["published"] and datetime.fromisoformat(e["published"]) < cutoff:
                continue
            if not e["external_id"]:
                continue
            out.append({
                "uid": f"rss:{name}:{e['external_id']}"[:400],
                "source": "rss",
                "source_name": name,
                "external_id": e["external_id"],
                "title": e["title"],
                "abstract": e["abstract"],
                "authors": "",
                "url": e["url"],
                "published": e["published"],
                "updated": e["published"],
                "categories": "",
                "profile": profile,
            })
    return out, failures


def check_feeds(feeds: list[dict]) -> list[tuple[str, str, str]]:
    """Validate feed URLs. Returns (name, status, detail) per feed."""
    results = []
    for feed in feeds:
        name, url = feed["name"], feed["url"]
        try:
            resp = requests.get(url, headers=UA, timeout=20)
            if resp.status_code != 200:
                results.append((name, "HTTP", f"status {resp.status_code}"))
                continue
            n = len(_parse_feed(resp.content))
            results.append((name, "OK" if n else "EMPTY", f"{n} entries"))
        except Exception as exc:
            results.append((name, "FAIL", f"{type(exc).__name__}: {exc}"))
    return results
