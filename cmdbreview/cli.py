"""Command line: `demo` writes the fictional Fabrikam Logistics CMDB to sample_data/ and builds the outputs; `review` runs on your own
files."""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from . import report, simulate
from .checks import review, summary
from .model import load

OUTPUTS = ("report.html", "review-pack.md", "ci-quality.csv", "unregistered.csv", "mismatches.csv", "relationships-review.csv",
           "group-scorecard.csv", "process.csv", "findings.csv", "actions.csv")


def run(data: Path, out: Path, title: str | None = None) -> dict:
    d = load(data)
    rv = review(d)
    title = title or f"{d.settings.organisation} · CMDB data quality review"
    out.mkdir(parents=True, exist_ok=True)
    (out / "report.html").write_text(report.render_html(d, rv, title), encoding="utf-8")
    (out / "review-pack.md").write_text(report.pack_md(d, rv, title), encoding="utf-8")
    report.write_csv(out / "ci-quality.csv", rv.ci_rows)
    report.write_csv(out / "unregistered.csv", rv.unregistered, ["name", "serial", "ip", "os", "kind", "sources", "last_seen"])
    report.write_csv(out / "mismatches.csv", rv.mismatches, ["ci", "name", "field", "cmdb", "discovered", "source", "seen", "group"])
    report.write_csv(out / "relationships-review.csv", rv.rel_rows, ["parent", "child", "type", "issue"])
    report.write_csv(out / "group-scorecard.csv", rv.groups, ["group", "cis", "score", "with_findings", "red"])
    report.write_csv(out / "process.csv", rv.process, ["group", "incidents", "no_ci", "no_ci_pct", "on_retired"])
    report.write_findings(rv, out / "findings.csv")
    report.write_actions(rv, out / "actions.csv")
    return summary(d, rv)


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="cmdbreview", description=__doc__)
    sub = p.add_subparsers(dest="cmd", required=True)
    dm = sub.add_parser("demo", help="write the fictional CMDB to sample_data/ and build the outputs")
    dm.add_argument("--data", type=Path, default=Path("sample_data"))
    dm.add_argument("--out", type=Path, default=Path("output"))
    rv = sub.add_parser("review", help="build the outputs from your own files")
    rv.add_argument("data", type=Path, help="folder with cis.csv and the optional exports")
    rv.add_argument("--out", type=Path, default=Path("output"))
    rv.add_argument("--title", help="title of the report and the pack")
    a = p.parse_args(argv)
    try:
        if a.cmd == "demo":
            simulate.write(a.data)
            sm = run(a.data, a.out)
        else:
            sm = run(a.data, a.out, a.title)
    except (FileNotFoundError, ValueError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2
    print(f"{sm['status']}: data quality {sm['score']} % across {sm['live']} live CIs, {sm['stale']} stale, {sm['unregistered']} unregistered "
          f"devices, {sm['mismatches']} records that disagree with discovery, {sm['red']} red and {sm['amber']} amber findings, "
          f"{sm['decisions']} decisions")
    print(f"outputs in {a.out}/: {', '.join(OUTPUTS)}")
    return 0
