"""Outputs: report.html (score and tiles, decisions, support groups, classes, every finding by area, devices nobody registered and
records that disagree with discovery), review-pack.md (the page for the monthly configuration management review) and the CSVs:
ci-quality, unregistered, mismatches, relationships-review, group-scorecard, process, findings and actions."""
from __future__ import annotations

import csv
import html
from pathlib import Path

from .checks import AREAS, Review, summary
from .model import FILES, Data

e = html.escape


def write_csv(path: Path, rows: list[dict], header: list[str] | None = None) -> None:
    header = header or (list(rows[0].keys()) if rows else ["ci"])
    with open(path, "w", newline="", encoding="utf-8") as fh:
        w = csv.DictWriter(fh, fieldnames=header, lineterminator="\n", extrasaction="ignore")
        w.writeheader()
        w.writerows([{k: ("" if r.get(k) is None else r.get(k)) for k in header} for r in rows])


def write_findings(rv: Review, path: Path) -> None:
    write_csv(path, [{"severity": f.severity, "area": AREAS[f.area], "code": f.code, "subject": f.subject, "finding": f.text,
                      "items": " ".join(f.items), "owner": f.owner, "due": f.due.isoformat() if f.due else "", "action": f.action}
                     for f in rv.findings], ["severity", "area", "code", "subject", "finding", "items", "owner", "due", "action"])


def write_actions(rv: Review, path: Path) -> None:
    rows = [{"ref": f"A{n:03d}", "severity": f.severity, "action": f.action, "subject": f.subject, "owner": f.owner,
             "due": f.due.isoformat() if f.due else "", "done": ""} for n, f in enumerate(rv.findings, 1)]
    write_csv(path, rows, ["ref", "severity", "action", "subject", "owner", "due", "done"])


def _day(x) -> str:
    return "" if not x else f"{x:%d %b %Y}"


def _trend(d: Data, rv: Review) -> str:
    p = d.settings.previous_score
    if p is None:
        return ""
    diff = round(rv.score - p, 1)
    return f"{'+' if diff >= 0 else ''}{diff} points on last month ({p} %)"


def pack_md(d: Data, rv: Review, title: str) -> str:
    s, sm = d.settings, summary(d, rv)
    out = [f"# {title}", "", f"Review of {_day(s.review_date)} · {sm['live']} live CIs ({sm['cis']} records)", "",
           f"**Result: {rv.status}** · data quality **{rv.score} %**" + (f" · {_trend(d, rv)}" if _trend(d, rv) else ""), "",
           "## Headlines", "",
           f"- {sm['stale']} live CIs no discovery source has seen lately; {sm['unregistered']} devices on the network with no CI.",
           f"- {sm['mismatches']} records disagree with discovery (address, operating system or location).",
           f"- {sm['red']} red and {sm['amber']} amber findings, {sm['decisions']} decisions.", "", "## Decisions", ""]
    out += [f"{n}. **{x['decision']}** — {x['detail']} · {x['owner']} · by {_day(x['due'])}" for n, x in enumerate(rv.decisions, 1)] or ["None this month."]
    out += ["", "## Support groups (lowest score first)", "", "| Group | CIs | Score | With findings |", "|---|---:|---:|---:|"]
    out += [f"| {g['group']} | {g['cis']} | {g['score']} % | {g['with_findings']} |" for g in rv.groups]
    out += ["", "## Red findings", ""]
    out += [f"- **{f.code}** {f.text} → {f.action} ({f.owner}, {_day(f.due)})" for f in rv.findings if f.severity == "RED"] or ["None."]
    out += ["", "## Process", "", "| Group | Incidents | No CI | % | On retired CIs |", "|---|---:|---:|---:|---:|"]
    out += [f"| {p['group']} | {p['incidents']} | {p['no_ci']} | {p['no_ci_pct']} | {p['on_retired']} |" for p in rv.process]
    out += ["", "## Sources", ""] + [f"- {FILES[k]} ({k}): {v} rows" for k, v in d.sources.items()]
    out += ["", "## Notes", "", "- Amber findings and actions: findings.csv and actions.csv.", ""]
    return "\n".join(out)


CSS = """
:root{--bg:#f2eee6;--card:#fbf8f3;--ink:#0e1a24;--muted:#5d6670;--line:#e2dccf;--ok:#1e7a4c;--warn:#a46200;--bad:#b42318;--track:#e8e2d6}
@media (prefers-color-scheme:dark){:root{--bg:#0e1a24;--card:#142331;--ink:#f2eee6;--muted:#a9b3bb;--line:#24364a;--ok:#4cc38a;
--warn:#f0a83a;--bad:#f2685c;--track:#2b333b}}
*{box-sizing:border-box}body{border-top:4px solid #c4672b}h1{font-weight:800;letter-spacing:-.025em;text-transform:uppercase;line-height:1.05}h1::before{content:"IGG · IT Ops toolkit";display:block;font:600 11px/1.4 ui-monospace,SFMono-Regular,Menlo,monospace;letter-spacing:.14em;text-transform:uppercase;color:#c4672b;margin-bottom:10px}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.5 system-ui,-apple-system,Segoe UI,sans-serif}
main{max-width:1100px;margin:0 auto;padding:28px 18px 60px}h1{font-size:26px;margin:0 0 4px}h2{font-size:18px;margin:34px 0 12px}
.muted{color:var(--muted)}.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin-top:20px}
.tile{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:14px 16px}.tile b{display:block;font-size:24px}
.overall{display:inline-block;margin-top:14px;padding:6px 14px;border-radius:99px;font-weight:700;border:2px solid currentColor}
table{width:100%;border-collapse:collapse;background:var(--card);border:1px solid var(--line);border-radius:10px;overflow:hidden}
th,td{text-align:left;padding:8px 10px;border-bottom:1px solid var(--line);vertical-align:top}
th{font-size:12px;text-transform:uppercase;letter-spacing:.04em;color:var(--muted)}tr:last-child td{border-bottom:0}.wrap{overflow-x:auto}
.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}
.pill{display:inline-block;white-space:nowrap;padding:1px 8px;border-radius:99px;font-size:12px;font-weight:600;border:1px solid currentColor}
.red{color:var(--bad)}.amber{color:var(--warn)}.green{color:var(--ok)}td.fix{font-size:13px;color:var(--muted);min-width:200px;max-width:340px}
.bar{display:inline-block;width:90px;height:8px;border-radius:4px;background:var(--track);vertical-align:middle;margin-right:8px;overflow:hidden}
.bar i{display:block;height:100%}.brk{overflow-wrap:anywhere;word-break:break-word}footer{margin-top:40px;font-size:13px}
"""


def _pill(x: str) -> str:
    return f"<span class='pill {x.lower()}'>{e(x)}</span>"


def _table(head: list[str], rows: list[str], empty: str = "Nothing to show.") -> str:
    if not rows:
        rows = [f"<tr><td colspan='{len(head)}'>{e(empty)}</td></tr>"]
    return "<div class='wrap'><table><tr>" + "".join(f"<th>{e(h)}</th>" for h in head) + "</tr>" + "".join(rows) + "</table></div>"


def _bar(score: float, s) -> str:
    cls = "ok" if score >= s.score_amber else "warn" if score >= s.score_red else "bad"
    return f"<span class='bar'><i style='width:{max(0, min(100, score)):.0f}%;background:var(--{cls})'></i></span>{score} %"


def render_html(d: Data, rv: Review, title: str) -> str:
    s, sm = d.settings, summary(d, rv)
    h = ["<!doctype html><html lang='en'><head><meta charset='utf-8'><meta name='viewport' content='width=device-width,initial-scale=1'>",
         f"<title>{e(title)}</title><style>{CSS}</style></head><body><main>",
         f"<h1>{e(title)}</h1><p class='muted'>Review of {_day(s.review_date)} · {sm['live']} live CIs out of {sm['cis']} records · "
         + ", ".join(f"{FILES[k]} ({v})" for k, v in d.sources.items()) + "</p>",
         f"<span class='overall {rv.status.lower()}'>{rv.status} · data quality {rv.score} %</span>"
         + (f" <span class='muted'>{e(_trend(d, rv))}</span>" if _trend(d, rv) else ""),
         "<div class='tiles'>"]
    tiles = [("Data quality", f"{rv.score} %"), ("Live CIs", sm["live"]), ("Not seen lately", sm["stale"]), ("Not in the CMDB", sm["unregistered"]),
             ("Disagree with discovery", sm["mismatches"]), ("Red findings", sm["red"]), ("Amber findings", sm["amber"]), ("Decisions", sm["decisions"])]
    h += [f"<div class='tile'><span class='muted'>{e(k)}</span><b>{e(str(v))}</b></div>" for k, v in tiles] + ["</div>"]
    h.append("<h2>Decisions</h2>")
    h.append(_table(["Decision", "Detail", "Owner", "Due"], [f"<tr><td><b>{e(x['decision'])}</b></td><td class='brk'>{e(x['detail'])}</td>"
                    f"<td>{e(x['owner'])}</td><td class='num'>{_day(x['due'])}</td></tr>" for x in rv.decisions], "No decisions this month."))
    h.append("<h2>Support groups</h2>")
    h.append(_table(["Group", "CIs", "Score", "With findings", "In a red finding"], [f"<tr><td>{e(g['group'])}</td><td class='num'>{g['cis']}</td>"
                    f"<td>{_bar(g['score'], s)}</td><td class='num'>{g['with_findings']}</td><td class='num'>{g['red']}</td></tr>" for g in rv.groups]))
    h.append("<h2>Classes</h2>")
    h.append(_table(["Class", "CIs", "Score", "With findings"], [f"<tr><td>{e(c['class'])}</td><td class='num'>{c['cis']}</td>"
                    f"<td>{_bar(c['score'], s)}</td><td class='num'>{c['with_findings']}</td></tr>" for c in rv.classes]))
    for area, label in AREAS.items():
        fs = [f for f in rv.findings if f.area == area]
        h.append(f"<h2>{e(label)} <span class='muted'>({len(fs)})</span></h2>")
        h.append(_table(["", "Code", "Finding", "Action", "Owner", "Due"], [f"<tr><td>{_pill(f.severity)}</td><td class='num'>{e(f.code)}</td>"
                        f"<td class='brk'>{e(f.text)}</td><td class='fix'>{e(f.action)}</td><td>{e(f.owner)}</td><td class='num'>{_day(f.due)}</td></tr>"
                        for f in fs], "Nothing to report."))
    h.append("<h2>On the network, not in the CMDB</h2>")
    h.append(_table(["Name", "Kind", "Serial", "IP", "OS", "Seen by", "Last seen"], [f"<tr><td>{e(u['name'])}</td><td>{e(u['kind'])}</td>"
                    f"<td>{e(u['serial'])}</td><td>{e(u['ip'])}</td><td>{e(u['os'])}</td><td>{e(u['sources'])}</td><td class='num'>{e(u['last_seen'])}</td></tr>"
                    for u in rv.unregistered], "Every device discovery sees is in the CMDB."))
    h.append("<h2>The CMDB and discovery disagree</h2>")
    h.append(_table(["CI", "Field", "CMDB", "Discovered", "Source"], [f"<tr><td>{e(m['name'])}</td><td>{e(m['field'])}</td><td>{e(m['cmdb'])}</td>"
                    f"<td>{e(m['discovered'])}</td><td>{e(m['source'])} · {e(m['seen'])}</td></tr>" for m in rv.mismatches], "No differences."))
    h.append("<h2>Incidents and their CI</h2>")
    h.append(_table(["Group", "Incidents", "No CI", "%", "On retired CIs"], [f"<tr><td>{e(p['group'])}</td><td class='num'>{p['incidents']}</td>"
                    f"<td class='num'>{p['no_ci']}</td><td class='num'>{p['no_ci_pct']}</td><td class='num'>{p['on_retired']}</td></tr>" for p in rv.process],
                    "No incidents loaded."))
    h.append("<footer class='muted'>Score per CI: the share of the fields its class needs, whether discovery sees it lately and agrees with it, "
             "and whether an application or database has what it runs on. ci-quality.csv has every CI.</footer></main></body></html>")
    return "\n".join(h)
