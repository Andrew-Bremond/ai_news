#!/usr/bin/env python3
"""research-digest CLI.

  python cli.py run                      # full pipeline, provider from config
  python cli.py run --provider ollama    # override for one run
  python cli.py run --no-llm             # heuristics only, zero API calls
  python cli.py check-feeds              # validate the profile's RSS URLs
  python cli.py providers                # which LLM backends are usable now
  python cli.py profiles                 # list interest profiles
"""
from __future__ import annotations

import argparse
import sys

from digest import pipeline, sources
from digest.llm import provider_status


def cmd_run(args):
    cfg = pipeline.load_config()
    report = pipeline.run(
        cfg, profile_name=args.profile, provider_key=args.provider, skip_llm=args.no_llm
    )
    print()
    for w in report["warnings"]:
        print(f"  warning: {w}", file=sys.stderr)
    if report.get("output"):
        print(f"Draft ready: {report['output']}")
        print("Fill in the COMMENTARY blocks, then publish.")
    return 0


def cmd_check_feeds(args):
    cfg = pipeline.load_config()
    profile = pipeline.load_profile(args.profile or cfg["active_profile"])
    feeds = profile["sources"].get("rss") or []
    print(f"Checking {len(feeds)} feeds...\n")
    bad = 0
    for name, status, detail in sources.check_feeds(feeds):
        print(f"  {status:<6} {name:<22} {detail}")
        bad += status != "OK"
    print(f"\n{len(feeds) - bad}/{len(feeds)} healthy.")
    if bad:
        print("Remove or replace the failures in the profile's sources.rss list.")
    return 0


def cmd_providers(args):
    cfg = pipeline.load_config()
    for p in provider_status(cfg["llm"]["models"]):
        mark = "ready" if p["ready"] else "----"
        print(f"  [{mark}] {p['label']:<28} {p['model']}")
        if not p["ready"]:
            print(f"          {p['reason']}")
    return 0


def cmd_profiles(args):
    cfg = pipeline.load_config()
    for name in pipeline.list_profiles():
        active = " (active)" if name == cfg["active_profile"] else ""
        print(f"  {name}{active}")
        print(f"      {pipeline.load_profile(name)['name']}")
    return 0


def main():
    ap = argparse.ArgumentParser(prog="research-digest")
    sub = ap.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("run", help="run the full pipeline")
    r.add_argument("--profile")
    r.add_argument("--provider", choices=["gemini", "groq", "ollama"])
    r.add_argument("--no-llm", action="store_true")
    r.set_defaults(fn=cmd_run)

    c = sub.add_parser("check-feeds", help="validate RSS URLs in a profile")
    c.add_argument("--profile")
    c.set_defaults(fn=cmd_check_feeds)

    sub.add_parser("providers", help="LLM backend availability").set_defaults(fn=cmd_providers)
    sub.add_parser("profiles", help="list interest profiles").set_defaults(fn=cmd_profiles)

    args = ap.parse_args()
    sys.exit(args.fn(args))


if __name__ == "__main__":
    main()
