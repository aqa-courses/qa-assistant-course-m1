"""Checks that the course fixtures agree with each other.

* tickets: known verdicts, verbatim quotes, duplicates point to earlier originals, docs exist;
* test cases: unique ids; automated cases have a test tagged @id:N, and every @id:N has a case;
* product docs: relative links resolve.

Run from the repository root: python fixtures/validate.py
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs" / "product"
VERDICTS = {"bug", "duplicate", "works_as_designed", "known_issue", "feature_request", "need_info"}
NEEDS_QUOTE = {"works_as_designed", "known_issue"}


def check_tickets(errors: list[str]) -> int:
    docs = {p.name for p in DOCS.glob("*.md")}
    tickets = [yaml.safe_load(p.read_text(encoding="utf-8")) for p in sorted((ROOT / "fixtures/tickets").glob("T-*.yaml"))]
    order = {t["id"]: i for i, t in enumerate(tickets)}
    by_id = {t["id"]: t for t in tickets}
    for t in tickets:
        tid, exp = t["id"], t["expected"]
        verdict = exp["verdict"]
        if verdict not in VERDICTS:
            errors.append(f"{tid}: unknown verdict {verdict!r}")
        for d in exp.get("docs", []):
            if d not in docs:
                errors.append(f"{tid}: docs/product/{d} does not exist")
        if verdict in NEEDS_QUOTE:
            if not exp.get("quote") or exp["quote"] not in t["body"]:
                errors.append(f"{tid}: quote must be a verbatim part of the body")
            if not exp.get("docs"):
                errors.append(f"{tid}: {verdict} needs at least one doc")
        dup = exp.get("duplicate_of")
        if verdict == "duplicate":
            if dup not in order or order[dup] >= order[tid]:
                errors.append(f"{tid}: duplicate_of must point to an earlier ticket")
            elif by_id[dup]["expected"]["verdict"] in {"duplicate", "need_info"}:
                errors.append(f"{tid}: duplicate_of must point to an original, not {dup}")
        elif dup:
            errors.append(f"{tid}: duplicate_of is set but verdict is {verdict}")
        for v in exp.get("acceptable", []):
            if v not in VERDICTS:
                errors.append(f"{tid}: unknown acceptable verdict {v!r}")
    return len(tickets)


def check_testcases(errors: list[str]) -> int:
    cases = yaml.safe_load((ROOT / "fixtures/testcases.yaml").read_text(encoding="utf-8"))
    ids = [c["id"] for c in cases]
    if len(ids) != len(set(ids)):
        errors.append("testcases: duplicate ids")
    tagged: dict[int, str] = {}
    for spec in (ROOT / "autotests/tests").glob("*.spec.ts"):
        for n in re.findall(r"@id:(\d+)", spec.read_text(encoding="utf-8")):
            if int(n) in tagged:
                errors.append(f"@id:{n} is used twice")
            tagged[int(n)] = f"autotests/tests/{spec.name}"
    for c in cases:
        if c["automated"]:
            if tagged.get(c["id"]) != c.get("test"):
                errors.append(f"case {c['id']}: expected a test tagged @id:{c['id']} in {c.get('test')}")
        elif c["id"] in tagged:
            errors.append(f"case {c['id']}: marked not automated, but {tagged[c['id']]} has @id:{c['id']}")
    for n in set(tagged) - set(ids):
        errors.append(f"@id:{n} in {tagged[n]} has no test case")
    return len(cases)


def check_doc_links(errors: list[str]) -> int:
    pages = list(DOCS.glob("*.md"))
    for page in pages:
        for target in re.findall(r"\]\(([^)#:]+\.md)\)", page.read_text(encoding="utf-8")):
            if not (DOCS / target).exists():
                errors.append(f"{page.name}: broken link {target}")
    return len(pages)


def main() -> None:
    errors: list[str] = []
    counts = (check_tickets(errors), check_testcases(errors), check_doc_links(errors))
    if errors:
        print("\n".join(errors))
        sys.exit(1)
    print("ok: {} tickets, {} test cases, {} doc pages".format(*counts))


if __name__ == "__main__":
    main()
