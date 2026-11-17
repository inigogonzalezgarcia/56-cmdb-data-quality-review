"""The review: every configuration item against the discovery sources, the directory and the tickets. Completeness (the fields its
class needs), accuracy (what discovery sees: address, operating system, location), freshness (seen lately), ownership (owner still
here, support group that exists), relationships (what an application runs on, services with nothing mapped, links to retired CIs)
and process (incidents with no CI, changes that left the record behind). Each finding has a severity, an owner and a due date; a
data quality score per CI, class and support group; and the choices become decisions."""
from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
from datetime import date, timedelta

from .model import CLASSES, DISCOVERABLE, HOST_REL, HOSTED, CI, Data, Seen, _norm, key, os_family

AREAS = {"complete": "Completeness", "accurate": "Accuracy", "owner": "Ownership", "rel": "Relationships", "process": "Process"}


@dataclass
class Finding:
    code: str
    severity: str              # RED or AMBER
    area: str
    subject: str
    text: str
    items: list[str] = field(default_factory=list)
    owner: str = ""
    due: date | None = None
    action: str = ""


@dataclass
class Review:
    findings: list[Finding] = field(default_factory=list)
    ci_rows: list[dict] = field(default_factory=list)
    unregistered: list[dict] = field(default_factory=list)
    mismatches: list[dict] = field(default_factory=list)
    rel_rows: list[dict] = field(default_factory=list)
    groups: list[dict] = field(default_factory=list)
    classes: list[dict] = field(default_factory=list)
    process: list[dict] = field(default_factory=list)
    decisions: list[dict] = field(default_factory=list)
    score: float = 0.0
    status: str = "GREEN"


def _sev(ci: CI | None, base: str = "AMBER") -> str:
    return "RED" if ci is not None and ci.criticality == "high" else base


def _due(rd: date, sev: str) -> date:
    return rd + timedelta(days=2 if sev == "RED" else 14)


def match(d: Data) -> dict[str, list[Seen]]:
    """Discovery rows for each CI: by serial first, then by name. A row is used by one CI only."""
    by_serial, by_name = defaultdict(list), defaultdict(list)
    for s in d.seen:
        if s.serial:
            by_serial[s.serial].append(s)
        if s.name:
            by_name[key(s.name)].append(s)
    out: dict[str, list[Seen]] = {}
    for c in d.cis:
        rows = list(by_serial.get(c.serial, [])) if c.serial else []
        for s in by_name.get(key(c.name), []):
            if s not in rows and (not s.serial or not c.serial or s.serial == c.serial):
                rows.append(s)
        out[c.id] = rows
    return out


def _latest(rows: list[Seen], attr: str = "") -> Seen | None:
    rows = [r for r in rows if r.last_seen and (not attr or getattr(r, attr))]
    return max(rows, key=lambda r: r.last_seen) if rows else None


def review(d: Data) -> Review:
    s = d.settings
    rd = s.review_date
    rv = Review()
    live = [c for c in d.cis if c.status != "retired"]
    by_id = {c.id: c for c in d.cis}
    seen = match(d)
    window = max(s.stale_days.values()) if s.stale_days else 45
    touched = Counter(i.ci for i in d.incidents) + Counter(c.ci for c in d.changes)
    # something live still depends on it or runs on it: not a candidate to retire even if nobody logged a ticket
    needed = {r.child for r in d.rels if r.parent in by_id and by_id[r.parent].status != "retired"}
    per_ci: dict[str, list[str]] = defaultdict(list)

    def add(code, sev, area, subject, text, items=(), owner="", action=""):
        f = Finding(code, sev, area, subject, text, list(items), owner or s.owners.get("cmdb", ""), _due(rd, sev), action)
        rv.findings.append(f)
        for i in f.items:
            per_ci[i].append(code)
        return f

    # --- completeness
    missing: dict[str, list[str]] = {}
    for c in live:
        need = s.required.get(c.cls, [])
        gaps = [f for f in need if not str(getattr(c, f, "") or "").strip()]
        if gaps:
            missing[c.id] = gaps
            add("CI-MISSING", _sev(c), "complete", c.id, f"{c.name} ({CLASSES.get(c.cls, c.cls)}) has no {', '.join(gaps)}", [c.id],
                c.group, "Fill in the missing fields from discovery or the owner")

    # --- accuracy and freshness against discovery
    fresh: dict[str, bool] = {}
    accurate: dict[str, float] = {}
    if d.seen:
        for c in live:
            if c.cls not in DISCOVERABLE:
                continue
            rows = seen[c.id]
            last = _latest(rows)
            limit = rd - timedelta(days=s.stale_days.get(c.cls, window))
            fresh[c.id] = bool(last and last.last_seen >= limit)
            if not fresh[c.id] and c.status == "operational":
                idle = touched[c.id] == 0 and c.id not in needed
                when = f"since {last.last_seen.isoformat()}" if last else "at all"
                f = add("CI-STALE", _sev(c), "accurate", c.id, f"{c.name} is operational in the CMDB but no discovery source has seen it {when}"
                        + (", and no ticket or change names it: a candidate to retire" if idle else ""), [c.id], c.group,
                        "Confirm it still exists; retire the record or fix its discovery")
                f.idle = idle
            diffs = []
            for attr, label in (("ip", "IP address"), ("os", "operating system"), ("location", "location")):
                r = _latest(rows, attr)
                mine = getattr(c, attr)
                if not r or not mine:
                    continue
                theirs = getattr(r, attr)
                same = os_family(mine) == os_family(theirs) if attr == "os" else _norm(mine) == _norm(theirs)
                if not same:
                    diffs.append(label)
                    rv.mismatches.append({"ci": c.id, "name": c.name, "field": label, "cmdb": mine, "discovered": theirs, "source": r.source,
                                          "seen": r.last_seen.isoformat(), "group": c.group})
            if diffs:
                add("CI-MISMATCH", "AMBER", "accurate", c.id, f"{c.name}: the CMDB and {_latest(rows).source} disagree on the {', '.join(diffs)}",
                    [c.id], c.group, "Update the record from discovery (or fix the source if the CMDB is right)")
            accurate[c.id] = 0.0 if not rows else (0.5 if diffs else 1.0)

        # discovered, not in the CMDB (or only as retired)
        claimed = {id(r) for rows in seen.values() for r in rows}
        groups_seen: dict[str, list[Seen]] = defaultdict(list)
        for r in d.seen:
            if id(r) not in claimed and r.last_seen and r.last_seen >= rd - timedelta(days=window):
                groups_seen[r.serial or key(r.name)].append(r)
        for ident, rows in sorted(groups_seen.items()):
            last = max(rows, key=lambda r: r.last_seen)
            name = next((r.name for r in rows if r.name), ident)
            kind = "server" if any(_norm(r.os).startswith("windows server") or "esxi" in _norm(r.os) or r.source.lower().startswith("vcenter")
                                   for r in rows) else "network" if any("ios" in _norm(r.os) or "fortios" in _norm(r.os) for r in rows) else "endpoint"
            rv.unregistered.append({"name": name, "serial": last.serial, "ip": last.ip, "os": last.os, "kind": kind,
                                    "sources": ", ".join(sorted({r.source for r in rows})), "last_seen": last.last_seen.isoformat()})
        if rv.unregistered:
            red = [u for u in rv.unregistered if u["kind"] in ("server", "network")]
            add("CI-UNREGISTERED", "RED" if red else "AMBER", "accurate", f"{len(rv.unregistered)} devices",
                f"{len(rv.unregistered)} devices seen on the network in the last {window} days have no CI"
                + (f", {len(red)} of them servers or network devices" if red else ""), [u["name"] for u in rv.unregistered], "",
                "Register them or find out why they are there")

        # retired, still seen
        for c in d.cis:
            if c.status != "retired":
                continue
            last = _latest(seen[c.id])
            since = c.retired or c.updated
            if last and since and last.last_seen > since:
                add("CI-RETIRED-SEEN", "RED", "accurate", c.id, f"{c.name} was retired on {since.isoformat()} but {last.source} saw it on "
                    f"{last.last_seen.isoformat()}", [c.id], c.group, "Find the device: wipe and dispose of it, or bring the record back")

    # duplicates
    seen_key: dict[tuple, list[CI]] = defaultdict(list)
    for c in live:
        if c.serial:
            seen_key[("serial", c.serial)].append(c)
        seen_key[("name", key(c.name), c.cls)].append(c)
    done = set()
    for k, cs in seen_key.items():
        ids = tuple(sorted(x.id for x in cs))
        if len(cs) > 1 and ids not in done:
            done.add(ids)
            what = f"serial {k[1]}" if k[0] == "serial" else f"name {cs[0].name}"
            add("CI-DUPLICATE", "AMBER", "accurate", ", ".join(ids), f"{len(cs)} live records share the {what}: {', '.join(ids)}", ids,
                cs[0].group, "Merge them into one record and keep its history")

    # --- ownership
    if d.people:
        people = {}
        for p in d.people:
            people[_norm(p.id)] = p
            if p.name:
                people[_norm(p.name)] = p
        left = defaultdict(list)
        for c in live:
            if not c.owner:
                continue
            p = people.get(_norm(c.owner))
            if p is None or not p.enabled:
                left[c.owner].append(c)
        for owner, cs in sorted(left.items()):
            sev = "RED" if any(c.criticality == "high" for c in cs) else "AMBER"
            add("OWN-LEFT", sev, "owner", owner, f"{len(cs)} CI{'s' if len(cs) > 1 else ''} owned by {owner}, who is no longer in the directory "
                "or is disabled: " + ", ".join(c.name for c in cs), [c.id for c in cs], cs[0].group, "Name a new owner with the support group lead")
    if d.groups:
        active = {_norm(g.id) for g in d.groups if g.active}
        bad = defaultdict(list)
        for c in live:
            if c.group and _norm(c.group) not in active:
                bad[c.group].append(c)
        for g, cs in sorted(bad.items()):
            add("OWN-GROUP", "AMBER", "owner", g, f"{len(cs)} CI{'s' if len(cs) > 1 else ''} assigned to {g}, which is not an active support group: "
                + ", ".join(c.name for c in cs), [c.id for c in cs],
                "", "Move them to the group that supports them now")

    # --- relationships
    has_host = set()
    for r in d.rels:
        pa, ch = by_id.get(r.parent), by_id.get(r.child)
        row = {"parent": r.parent, "child": r.child, "type": r.kind, "issue": ""}
        if pa is None or ch is None:
            row["issue"] = "unknown CI"
        elif ch.status == "retired" and pa.status != "retired":
            row["issue"] = "depends on a retired CI"
        if r.kind in HOST_REL and ch is not None:
            has_host.add(r.parent)          # a host that was retired is REL-RETIRED, not an orphan
        rv.rel_rows.append(row)
    dangling = [x for x in rv.rel_rows if x["issue"] == "unknown CI"]
    if dangling:
        add("REL-DANGLING", "AMBER", "rel", f"{len(dangling)} relationships", f"{len(dangling)} relationships point to a CI that is not in the "
            "CMDB: " + "; ".join(f"{x['parent']} → {x['child']}" for x in dangling), [x["parent"] for x in dangling if x["parent"] in by_id],
            "", "Remove them or restore the missing CI")
    for x in rv.rel_rows:
        if x["issue"] == "depends on a retired CI":
            pa = by_id[x["parent"]]
            add("REL-RETIRED", "RED", "rel", pa.id, f"{pa.name} {x['type']} {by_id[x['child']].name}, which was retired", [pa.id], pa.group,
                "Find what it really runs on now and fix the relationship")
    for c in live:
        if c.cls in HOSTED and c.id not in has_host:
            add("REL-ORPHAN", _sev(c), "rel", c.id, f"{c.name} ({CLASSES[c.cls].lower()}) has no relationship to what it runs on", [c.id],
                c.group, "Add the runs-on relationship to its server or VM")
    if d.services:
        mapped = Counter(c.service for c in live if c.service)
        for sv in d.services:
            if not mapped.get(sv.id):
                sev = "RED" if sv.criticality == "high" else "AMBER"
                add("REL-SERVICE-EMPTY", sev, "rel", sv.id, f"The business service {sv.id} has no CI mapped to it, so an outage cannot be "
                    "traced to it", [], sv.owner, "Map its applications, databases and servers")

    # --- process
    if d.incidents:
        by_group = defaultdict(lambda: [0, 0, 0])
        for i in d.incidents:
            g = by_group[i.group or "(no group)"]
            g[0] += 1
            c = by_id.get(i.ci)
            if not i.ci or c is None:
                g[1] += 1
            elif c.status == "retired":
                g[2] += 1
        for g, (n, none, retired) in sorted(by_group.items()):
            pct = round(100 * none / n, 1) if n else 0.0
            rv.process.append({"group": g, "incidents": n, "no_ci": none, "no_ci_pct": pct, "on_retired": retired})
            if n >= 10 and pct > s.no_ci_threshold:
                add("PROC-INC-NO-CI", "AMBER", "process", g, f"{none} of {n} incidents of {g} ({pct} %) have no CI, above the {s.no_ci_threshold:g} % "
                    "limit", [], s.owners.get("process", ""), "Make the CI mandatory when the group resolves an incident")
        on_ret = [i for i in d.incidents if i.ci in by_id and by_id[i.ci].status == "retired"]
        if on_ret:
            add("PROC-INC-RETIRED", "AMBER", "process", f"{len(on_ret)} incidents", f"{len(on_ret)} incidents are logged against retired CIs: "
                + ", ".join(f"{i.id} ({by_id[i.ci].name})" for i in on_ret), [i.ci for i in on_ret], s.owners.get("process", ""),
                "Re-point them to the live CI; hide retired CIs from the incident form")
    for ch in d.changes:
        c = by_id.get(ch.ci)
        if c is None or not ch.implemented or any(w in ch.state for w in ("cancel", "fail", "reject")):
            continue
        since = c.retired or c.updated
        if c.status == "retired" and since and ch.implemented > since:
            add("PROC-CHG-RETIRED", "RED", "process", ch.id, f"{ch.id} was implemented on {c.name} on {ch.implemented.isoformat()}, after the CI was "
                f"retired on {since.isoformat()}", [c.id], s.owners.get("process", ""), "Check what the change really touched and fix the record")
        elif c.status != "retired" and c.updated and c.updated < ch.implemented:
            add("PROC-CHG-NOT-UPDATED", "AMBER", "process", ch.id, f"{ch.id} ({ch.summary or 'change'}) was implemented on {c.name} on "
                f"{ch.implemented.isoformat()}, but the record was last updated on {c.updated.isoformat()}", [c.id], c.group,
                "Update the CI as part of closing the change")

    # --- scores
    for c in d.cis:
        parts = []
        need = s.required.get(c.cls, [])
        if c.status != "retired":
            if need:
                parts.append(1 - len(missing.get(c.id, [])) / len(need))
            if c.id in accurate:
                parts.append(accurate[c.id])
            if c.id in fresh:
                parts.append(1.0 if fresh[c.id] else 0.0)
            if c.cls in HOSTED:
                parts.append(1.0 if c.id in has_host else 0.0)
        score = round(100 * sum(parts) / len(parts), 1) if parts else None
        last = _latest(seen.get(c.id, []))
        rv.ci_rows.append({"ci": c.id, "name": c.name, "class": CLASSES.get(c.cls, c.cls), "status": c.status, "criticality": c.criticality,
                           "group": c.group, "owner": c.owner, "service": c.service, "last_seen": last.last_seen.isoformat() if last else "",
                           "source": last.source if last else "", "score": score, "findings": " ".join(sorted(set(per_ci.get(c.id, []))))})
    scored = [r for r in rv.ci_rows if r["score"] is not None]
    rv.score = round(sum(r["score"] for r in scored) / len(scored), 1) if scored else 0.0
    for keyname, out in (("group", rv.groups), ("class", rv.classes)):
        agg = defaultdict(list)
        for r in scored:
            agg[r[keyname] or "(none)"].append(r)
        for k, rows in sorted(agg.items(), key=lambda kv: sum(r["score"] for r in kv[1]) / len(kv[1])):
            out.append({keyname: k, "cis": len(rows), "score": round(sum(r["score"] for r in rows) / len(rows), 1),
                        "with_findings": sum(1 for r in rows if r["findings"]), "red": sum(1 for r in rows if any(
                            f.severity == "RED" and r["ci"] in f.items for f in rv.findings))})

    # --- decisions
    idle = [f.items[0] for f in rv.findings if f.code == "CI-STALE" and getattr(f, "idle", False)]
    if idle:
        rv.decisions.append({"decision": f"Retire {len(idle)} CIs nobody has seen or touched", "detail": ", ".join(by_id[i].name for i in idle),
                             "owner": s.owners.get("cmdb", ""), "due": _due(rd, "AMBER")})
    if rv.unregistered:
        rv.decisions.append({"decision": f"Register or remove {len(rv.unregistered)} unknown devices", "detail": ", ".join(u["name"] for u in rv.unregistered),
                             "owner": s.owners.get("cmdb", ""), "due": _due(rd, "RED")})
    left = [f for f in rv.findings if f.code == "OWN-LEFT"]
    if left:
        rv.decisions.append({"decision": f"New owners for {sum(len(f.items) for f in left)} CIs of people who left",
                             "detail": "; ".join(f"{f.subject}: {', '.join(by_id[i].name for i in f.items)}" for f in left), "owner": s.owners.get("cmdb", ""),
                             "due": _due(rd, "RED" if any(f.severity == "RED" for f in left) else "AMBER")})
    empty = [f for f in rv.findings if f.code == "REL-SERVICE-EMPTY"]
    if empty:
        rv.decisions.append({"decision": f"Map {len(empty)} business services with no CI" if len(empty) > 1 else "Map the business service with no CI",
                             "detail": ", ".join(f.subject for f in empty),
                             "owner": empty[0].owner or s.owners.get("cmdb", ""), "due": _due(rd, empty[0].severity)})
    noci = [f for f in rv.findings if f.code == "PROC-INC-NO-CI"]
    if noci:
        rv.decisions.append({"decision": "Make the CI mandatory to resolve an incident in " + ", ".join(f.subject for f in noci),
                             "detail": "; ".join(f.text for f in noci), "owner": s.owners.get("process", ""), "due": _due(rd, "AMBER")})

    red = any(f.severity == "RED" for f in rv.findings)
    amber = any(f.severity == "AMBER" for f in rv.findings)
    rv.status = "RED" if red or rv.score < s.score_red else "AMBER" if amber or rv.score < s.score_amber else "GREEN"
    order = {"RED": 0, "AMBER": 1}
    rv.findings.sort(key=lambda f: (order[f.severity], list(AREAS).index(f.area), f.code, f.subject))
    return rv


def summary(d: Data, rv: Review) -> dict:
    count = Counter(f.code for f in rv.findings)
    return {"status": rv.status, "score": rv.score, "previous": d.settings.previous_score, "cis": len(d.cis),
            "live": sum(1 for c in d.cis if c.status != "retired"), "stale": count["CI-STALE"], "unregistered": len(rv.unregistered),
            "mismatches": count["CI-MISMATCH"], "red": sum(1 for f in rv.findings if f.severity == "RED"),
            "amber": sum(1 for f in rv.findings if f.severity == "AMBER"), "decisions": len(rv.decisions)}
