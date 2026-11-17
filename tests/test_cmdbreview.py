import csv
import json
from datetime import date
from pathlib import Path

from cmdbreview import simulate
from cmdbreview.checks import review, summary
from cmdbreview.cli import OUTPUTS, run
from cmdbreview.model import cls, criticality, key, load, os_family, status

RD = "2026-11-17"


def write(folder: Path, files: dict, settings: dict | None = None) -> Path:
    folder.mkdir(parents=True, exist_ok=True)
    for name, rows in files.items():
        with (folder / name).open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
            w.writeheader()
            w.writerows(rows)
    (folder / "settings.json").write_text(json.dumps({"organisation": "Test", "review_date": RD, **(settings or {})}))
    return folder


def server(i="CI1", name="SRV-01", **kw):
    row = {"CI": i, "Name": name, "Class": "Server", "Status": "Operational", "Owner": "ana", "SupportGroup": "Servers", "Location": "DC",
           "Serial": "S1", "IP": "10.0.0.1", "OS": "Windows Server 2022 Standard", "BusinessService": "", "Criticality": "Medium",
           "Updated": "2026-11-01", "Retired": ""}
    row.update(kw)
    return row


def seen(name="srv-01", **kw):
    row = {"Source": "Active Directory", "Name": name, "Serial": "", "IP": "10.0.0.1", "OS": "Windows Server 2022 Standard", "Location": "",
           "LastSeen": "2026-11-16"}
    row.update(kw)
    return row


def codes(folder):
    d = load(folder)
    return d, review(d), [f.code for f in review(d).findings]


def test_parsers():
    assert cls("cmdb_ci_win_server") == "server" and cls("Virtual Machine Instance") == "vm" and cls("Notebook") == "laptop"
    assert cls("Network switch") == "network" and cls("Database instance") == "database" and cls("Business application") == "application"
    assert status("Retired") == "retired" and status("In stock") == "stock" and status("Installed") == "operational"
    assert criticality("1 - Critical") == "high" and criticality("Tier 2") == "medium" and criticality("") == ""
    assert os_family("Windows Server 2019 Datacenter") == os_family("Microsoft Windows Server 2019 Standard")
    assert os_family("Windows 10 Enterprise 22H2") != os_family("Windows 11 Enterprise 24H2")
    assert os_family("Red Hat Enterprise Linux 9.4") == os_family("RHEL 9")
    assert key("SRV-01.contoso.local") == key("srv-01")


def test_clean_cmdb_has_no_findings(tmp_path):
    f = write(tmp_path, {"cis.csv": [server()], "discovery.csv": [seen()]})
    d, rv, c = codes(f)
    assert c == [] and rv.status == "GREEN" and rv.score == 100.0


def test_missing_fields_by_class_and_criticality(tmp_path):
    f = write(tmp_path, {"cis.csv": [server(Serial="", Location=""), server("CI2", "SRV-02", Owner="", Criticality="High", Serial="S2")]})
    d, rv, c = codes(f)
    m = [x for x in rv.findings if x.code == "CI-MISSING"]
    assert {x.subject for x in m} == {"CI1", "CI2"}
    assert next(x for x in m if x.subject == "CI2").severity == "RED"      # a critical CI with a gap is red
    assert "location, serial" in next(x for x in m if x.subject == "CI1").text


def test_stale_and_retire_candidate(tmp_path):
    f = write(tmp_path, {"cis.csv": [server(), server("CI2", "SRV-02", Serial="S2")],
                         "discovery.csv": [seen(), seen("srv-02", LastSeen="2026-08-01")]})
    d, rv, c = codes(f)
    st = [x for x in rv.findings if x.code == "CI-STALE"]
    assert [x.subject for x in st] == ["CI2"] and "candidate to retire" in st[0].text
    assert rv.decisions and rv.decisions[0]["detail"] == "SRV-02"


def test_stale_but_needed_is_not_a_retire_candidate(tmp_path):
    app = server("APP", "Billing", Class="Application", Serial="", IP="", OS="", Location="", BusinessService="Billing")
    f = write(tmp_path, {"cis.csv": [server(), app], "discovery.csv": [seen(LastSeen="2026-07-01")],
                         "relationships.csv": [{"Parent": "APP", "Child": "CI1", "Type": "Runs on"}]})
    d, rv, c = codes(f)
    st = next(x for x in rv.findings if x.code == "CI-STALE")
    assert "candidate to retire" not in st.text and not any("Retire" in x["decision"] for x in rv.decisions)


def test_unregistered_and_retired_seen(tmp_path):
    f = write(tmp_path, {"cis.csv": [server(), server("CI9", "SRV-OLD", Serial="S9", Status="Retired", Retired="2026-09-01")],
                         "discovery.csv": [seen(), seen("SRV-NEW", IP="10.0.0.7"), seen("laptop-77", OS="Windows 11 Enterprise", Source="Intune"),
                                           seen("srv-old", LastSeen="2026-11-10")]})
    d, rv, c = codes(f)
    assert {u["name"] for u in rv.unregistered} == {"SRV-NEW", "laptop-77"}
    un = next(x for x in rv.findings if x.code == "CI-UNREGISTERED")
    assert un.severity == "RED"                                             # one of them is a server
    assert "CI-RETIRED-SEEN" in c


def test_mismatch_ip_os_location(tmp_path):
    f = write(tmp_path, {"cis.csv": [server(OS="Windows Server 2019 Standard")],
                         "discovery.csv": [seen(IP="10.0.0.9", OS="Windows Server 2022 Standard", Location="Branch")]})
    d, rv, c = codes(f)
    assert {m["field"] for m in rv.mismatches} == {"IP address", "operating system", "location"}
    assert next(x for x in rv.findings if x.code == "CI-MISMATCH").severity == "AMBER"
    f2 = write(tmp_path / "b", {"cis.csv": [server(OS="Windows Server 2022 Datacenter")], "discovery.csv": [seen()]})
    assert review(load(f2)).mismatches == []                                    # the same version in other words is not a difference


def test_duplicates_by_serial(tmp_path):
    f = write(tmp_path, {"cis.csv": [server(), server("CI2", "SRV-02-NEW")]})
    d, rv, c = codes(f)
    dup = next(x for x in rv.findings if x.code == "CI-DUPLICATE")
    assert set(dup.items) == {"CI1", "CI2"}


def test_owner_left_and_inactive_group(tmp_path):
    f = write(tmp_path, {"cis.csv": [server(Owner="bob", Criticality="High"), server("CI2", "SRV-02", Serial="S2", SupportGroup="Old team")],
                         "people.csv": [{"User": "ana", "Name": "Ana", "Enabled": "True"}, {"User": "bob", "Name": "Bob", "Enabled": "False"}],
                         "groups.csv": [{"Group": "Servers", "Manager": "ana", "Active": "True"}, {"Group": "Old team", "Manager": "", "Active": "False"}]})
    d, rv, c = codes(f)
    left = next(x for x in rv.findings if x.code == "OWN-LEFT")
    assert left.severity == "RED" and left.items == ["CI1"]
    assert next(x for x in rv.findings if x.code == "OWN-GROUP").items == ["CI2"]


def test_relationships(tmp_path):
    app = dict(server("APP", "Billing", Class="Application", Serial="", IP="", OS="", Location="", BusinessService="Billing"))
    orphan = dict(app, CI="APP2", Name="Reports")
    f = write(tmp_path, {"cis.csv": [server(), server("CI9", "SRV-OLD", Serial="S9", Status="Retired", Retired="2026-06-01"), app, orphan],
                         "relationships.csv": [{"Parent": "APP", "Child": "CI9", "Type": "Runs on"}, {"Parent": "APP", "Child": "GONE", "Type": "Depends on"}],
                         "services.csv": [{"Service": "Billing", "Criticality": "High", "Owner": "ana"}, {"Service": "Returns", "Criticality": "High", "Owner": "ana"}]})
    d, rv, c = codes(f)
    assert "REL-RETIRED" in c and "REL-DANGLING" in c
    assert [x.subject for x in rv.findings if x.code == "REL-ORPHAN"] == ["APP2"]       # APP runs on a retired CI: REL-RETIRED, not orphan
    empty = next(x for x in rv.findings if x.code == "REL-SERVICE-EMPTY")
    assert empty.subject == "Returns" and empty.severity == "RED"


def test_process_incidents_and_changes(tmp_path):
    cis = [server(Updated="2026-09-01"), server("CI9", "SRV-OLD", Serial="S9", Status="Retired", Retired="2026-06-01")]
    incs = [{"Incident": f"I{n}", "Opened": "2026-11-10", "CI": "" if n < 4 else "CI1", "Group": "Desk"} for n in range(12)]
    incs.append({"Incident": "I99", "Opened": "2026-11-11", "CI": "CI9", "Group": "Desk"})
    chgs = [{"Change": "C1", "CI": "CI1", "Implemented": "2026-11-05", "State": "Successful", "Summary": "OS upgrade"},
            {"Change": "C2", "CI": "CI9", "Implemented": "2026-11-06", "State": "Successful", "Summary": "Patch"},
            {"Change": "C3", "CI": "CI1", "Implemented": "2026-11-07", "State": "Cancelled", "Summary": "x"}]
    f = write(tmp_path, {"cis.csv": cis, "incidents.csv": incs, "changes.csv": chgs})
    d, rv, c = codes(f)
    assert "PROC-INC-NO-CI" in c and "PROC-INC-RETIRED" in c
    assert [x.subject for x in rv.findings if x.code == "PROC-CHG-NOT-UPDATED"] == ["C1"]
    assert next(x for x in rv.findings if x.code == "PROC-CHG-RETIRED").severity == "RED"


def test_other_column_names_and_semicolons(tmp_path):
    (tmp_path / "cis.csv").write_text("sys_id;Hostname;sys_class_name;Install status;Managed by;Assignment group;Site;Serial number;"
                                      "IP address;Operating system;Business criticality\n"
                                      "a1;SRV-01;cmdb_ci_win_server;Installed;ana;Servers;DC;S1;10.0.0.1;Windows Server 2022;2 - Medium\n",
                                      encoding="utf-8")
    d = load(tmp_path)
    c = d.cis[0]
    assert (c.id, c.name, c.cls, c.status, c.owner, c.criticality) == ("a1", "SRV-01", "server", "operational", "ana", "medium")


def test_missing_cmdb_export(tmp_path):
    try:
        load(tmp_path)
    except FileNotFoundError as exc:
        assert "cis.csv" in str(exc)
    else:
        raise AssertionError("expected FileNotFoundError")


def test_demo_end_to_end(tmp_path):
    simulate.write(tmp_path / "data")
    sm = run(tmp_path / "data", tmp_path / "out")
    for name in OUTPUTS:
        assert (tmp_path / "out" / name).exists(), name
    assert sm["status"] == "RED" and sm["unregistered"] == 6 and sm["mismatches"] == 7 and sm["stale"] == 9 and sm["decisions"] == 5
    d = load(tmp_path / "data")
    rv = review(d)
    assert d.settings.review_date == date(2026, 11, 17)
    assert {f.code for f in rv.findings if f.severity == "RED"} == {"CI-RETIRED-SEEN", "CI-STALE", "CI-UNREGISTERED", "OWN-LEFT", "REL-RETIRED",
                                                                     "REL-SERVICE-EMPTY", "PROC-CHG-RETIRED"}
    pack = (tmp_path / "out" / "review-pack.md").read_text(encoding="utf-8")
    assert "Customer returns portal" in pack and "Result: RED" in pack


def test_demo_is_deterministic(tmp_path):
    simulate.write(tmp_path / "a")
    simulate.write(tmp_path / "b")
    for f in (tmp_path / "a").iterdir():
        assert f.read_bytes() == (tmp_path / "b" / f.name).read_bytes(), f.name
    assert summary(load(tmp_path / "a"), review(load(tmp_path / "a")))["score"] == summary(load(tmp_path / "b"), review(load(tmp_path / "b")))["score"]
