"""The demo: Fabrikam Logistics, a made-up logistics company with a head office in Madrid, a warehouse in Zaragoza and a sales office
in Valencia, reviewed on Tuesday 17 November 2026. Everything is fictional. The problems are placed on purpose among records that are
fine; the generator is deterministic, so the committed sample_data/ is always what it writes."""
from __future__ import annotations

import csv
import json
import random
from datetime import date, timedelta
from pathlib import Path

RD = date(2026, 11, 17)
ORG = "Fabrikam Logistics"


def _d(days: int) -> str:
    return (RD - timedelta(days=days)).isoformat()


PEOPLE = [("lruiz", "Lucía Ruiz", "IT"), ("dprieto", "Daniel Prieto", "IT"), ("mserrano", "Marta Serrano", "IT"), ("pvidal", "Pablo Vidal", "IT"),
          ("cnieto", "Carmen Nieto", "IT"), ("jortega", "Javier Ortega", "IT"), ("agil", "Ana Gil", "Operations"), ("rmarin", "Raúl Marín", "Operations"),
          ("sleon", "Sara León", "Finance"), ("ecano", "Elena Cano", "Finance"), ("vrubio", "Víctor Rubio", "Sales"), ("nsoto", "Nuria Soto", "Sales"),
          ("iblanco", "Irene Blanco", "HR"), ("tmoya", "Tomás Moya", "Warehouse"), ("bpena", "Beatriz Peña", "Warehouse"), ("hcampos", "Hugo Campos", "Legal"),
          ("jmorales", "Jorge Morales", "IT")]
DISABLED = {"jmorales"}            # left in October; acastro left earlier and is no longer in the directory
GROUPS = [("Service Desk", "lruiz", True), ("Field Services", "dprieto", True), ("Windows Servers", "mserrano", True), ("Linux Servers", "pvidal", True),
          ("Network", "cnieto", True), ("Database", "jortega", True), ("Applications", "jortega", True), ("Infrastructure Operations", "mserrano", False)]
SERVICES = [("Order management", "high", "agil"), ("Warehouse management", "high", "tmoya"), ("Customer returns portal", "high", "vrubio"),
            ("Payroll", "high", "iblanco"), ("Finance reporting", "medium", "sleon"), ("Email and collaboration", "medium", "lruiz"),
            ("File shares", "medium", "mserrano"), ("Fleet tracking", "medium", "rmarin"), ("Printing", "low", "dprieto"), ("Intranet", "low", "iblanco")]

CI_FIELDS = ["CI", "Name", "Class", "Status", "Environment", "Owner", "SupportGroup", "Location", "Serial", "IP", "OS", "BusinessService",
             "Criticality", "Updated", "Retired"]


def build() -> dict:
    rnd = random.Random(56)
    cis, seen, rels, incs, chgs = [], [], [], [], []

    def ci(i, name, cls, owner, group, loc, serial, ip_, os_, service="", crit="", status="Operational", env="Production", updated=40, retired=""):
        cis.append({"CI": i, "Name": name, "Class": cls, "Status": status, "Environment": env, "Owner": owner, "SupportGroup": group,
                    "Location": loc, "Serial": serial, "IP": ip_, "OS": os_, "BusinessService": service, "Criticality": crit,
                    "Updated": _d(updated) if isinstance(updated, int) else updated, "Retired": retired})

    def see(source, name, serial, ip_, os_, days, loc=""):
        seen.append({"Source": source, "Name": name, "Serial": serial, "IP": ip_, "OS": os_, "Location": loc, "LastSeen": _d(days)})

    hq, zar, vlc, dc = "Madrid HQ", "Zaragoza warehouse", "Valencia office", "Madrid HQ data room"
    # --- physical servers and storage (data room)
    for n in range(1, 5):
        ci(f"CI{1000+n}", f"ESX-0{n}", "Server", "mserrano", "Windows Servers", dc, f"FBK4{n}X7Q", f"10.10.1.{10+n}", "VMware ESXi 8.0 U3",
           crit="high")
        see("vCenter", f"esx-0{n}.fabrikam.local", f"FBK4{n}X7Q", f"10.10.1.{10+n}", "VMware ESXi 8.0.3", 0)
    ci("CI1005", "BKP-01", "Server", "mserrano", "Windows Servers", dc, "FBK7B2P1", "10.10.1.20", "Windows Server 2022 Standard", crit="high")
    see("Active Directory", "BKP-01", "", "10.10.1.20", "Windows Server 2022 Standard", 1)
    ci("CI1006", "SQL-01", "Server", "jortega", "Database", dc, "FBK7S9Q4", "10.10.1.30", "Windows Server 2019 Standard", crit="high")
    see("Active Directory", "SQL-01", "", "10.10.1.30", "Windows Server 2019 Standard", 1)
    ci("CI1007", "SQL-2014-LEG", "Server", "jortega", "Database", dc, "FBK2L0D8", "10.10.1.31", "Windows Server 2012 R2 Standard", crit="high")
    see("Active Directory", "SQL-2014-LEG", "", "10.10.1.31", "Windows Server 2012 R2 Standard", 74)         # stale, critical
    ci("CI1008", "NAS-01", "Storage", "mserrano", "Windows Servers", dc, "NS83K2M1", "10.10.1.40", "")
    see("Network scan", "nas-01", "NS83K2M1", "10.10.1.40", "", 0)
    ci("CI1009", "SAN-01", "Storage", "mserrano", "Windows Servers", dc, "", "10.10.1.41", "")                    # no serial
    see("Network scan", "san-01", "", "10.10.1.41", "", 0)
    ci("CI1010", "BKP-OLD-02", "Server", "acastro", "Infrastructure Operations", dc, "FBK1C4V3", "10.10.1.21", "Windows Server 2016 Standard",
       crit="medium", updated=400)                                                                                # stale, idle, owner gone

    # --- virtual machines
    vms = [("DC-01", "Windows Server 2022 Standard", "Email and collaboration", "high", "Windows Servers"),
           ("DC-02", "Windows Server 2022 Standard", "Email and collaboration", "high", "Windows Servers"),
           ("FS-01", "Windows Server 2022 Standard", "File shares", "medium", "Windows Servers"),
           ("PRN-01", "Windows Server 2022 Standard", "Printing", "low", "Windows Servers"),
           ("INTRA-01", "Windows Server 2019 Standard", "Intranet", "low", "Windows Servers"),
           ("ORD-APP-01", "Red Hat Enterprise Linux 9.4", "Order management", "high", "Linux Servers"),
           ("ORD-APP-02", "Red Hat Enterprise Linux 9.4", "Order management", "high", "Linux Servers"),
           ("ORD-DB-01", "Red Hat Enterprise Linux 9.4", "Order management", "high", "Database"),
           ("WMS-APP-01", "Windows Server 2019 Standard", "Warehouse management", "high", "Applications"),
           ("WMS-DB-01", "Windows Server 2019 Standard", "Warehouse management", "high", "Database"),
           ("PAY-APP-01", "Red Hat Enterprise Linux 8.10", "Payroll", "high", "Linux Servers"),
           ("RPT-02", "Windows Server 2022 Standard", "Finance reporting", "medium", "Windows Servers"),
           ("FLT-APP-01", "Ubuntu 22.04 LTS", "Fleet tracking", "medium", "Linux Servers"),
           ("MON-01", "Ubuntu 24.04 LTS", "", "medium", "Linux Servers"),
           ("WSUS-01", "Windows Server 2022 Standard", "", "low", "Windows Servers"),
           ("JUMP-01", "Windows Server 2022 Standard", "", "medium", "Windows Servers"),
           ("OLD-RPT-02", "Windows Server 2016 Standard", "Finance reporting", "low", "Windows Servers"),      # stale, idle
           ("TEST-WEB-03", "Ubuntu 20.04 LTS", "", "low", "Linux Servers")]                                       # stale, idle
    for n, (name, os_, svc, crit, grp) in enumerate(vms):
        ip_ = f"10.10.2.{20+n}"
        owner = "mserrano" if grp == "Windows Servers" else "pvidal" if grp == "Linux Servers" else "jortega"
        if name in ("WMS-APP-01",):
            owner = "jmorales"
        ci(f"CI2{n:03d}", name, "Virtual machine", owner, grp, dc, "", ip_, os_, svc, crit if name != "MON-01" else "",
           env="Test" if name.startswith("TEST") else "Production")
        if name in ("OLD-RPT-02", "TEST-WEB-03"):
            see("vCenter", name.lower(), "", ip_, os_, 96 if name == "OLD-RPT-02" else 131)
            continue
        disc_ip = {"FS-01": "10.10.2.80", "PRN-01": "10.10.2.81", "MON-01": "10.10.2.82"}.get(name, ip_)     # re-addressed, CMDB not updated
        see("vCenter", name.lower(), "", disc_ip, os_, 0)
        if os_.startswith("Windows"):
            see("Active Directory", name, "", disc_ip, os_, 1)

    # --- network
    net = [("FW-MAD-01", "FortiOS 7.4.4", hq, "10.10.0.1"), ("SW-MAD-CORE", "Cisco IOS XE 17.9", dc, "10.10.0.2"),
           ("SW-MAD-F1", "Cisco IOS XE 17.9", hq, "10.10.0.11"), ("SW-MAD-F2", "Cisco IOS XE 17.9", hq, "10.10.0.12"),
           ("SW-MAD-F3", "Cisco IOS XE 17.9", hq, "10.10.0.13"), ("SW-ZAR-01", "Cisco IOS XE 17.9", zar, "10.20.0.2"),
           ("RTR-VLC-01", "Cisco IOS XE 17.9", vlc, "10.30.0.1"), ("WLC-MAD-01", "Cisco IOS XE 17.12", dc, "10.10.0.20")]
    for n, (name, os_, loc, ip_) in enumerate(net):
        serial = f"FOC27{n}1N{n}" if name != "WLC-MAD-01" else ""
        ci(f"CI3{n:03d}", name, "Network device", "cnieto", "Network", loc, serial, ip_, os_, crit="high" if "CORE" in name or "FW" in name else "medium")
        see("Network scan", name.lower(), serial, ip_, os_, 0)

    # --- desktops and laptops
    users = ["agil", "rmarin", "sleon", "ecano", "vrubio", "nsoto", "iblanco", "tmoya", "bpena", "hcampos", "lruiz", "dprieto", "mserrano",
             "pvidal", "cnieto", "jortega"]
    for n in range(1, 25):
        name = f"PC-MAD-{n:03d}"
        owner = users[n % len(users)]
        os_ = "Windows 11 Enterprise 24H2" if n > 6 else "Windows 10 Enterprise 22H2"
        serial = f"MXL{4000+n}"
        loc = zar if n in (20, 21, 22, 23, 24) else hq
        ci(f"CI4{n:03d}", name, "Desktop", owner, "Field Services", loc, serial, "", os_, updated=60)
        days = rnd.randint(0, 6)
        if n in (4, 5, 6):                                           # upgraded to Windows 11 by CHG-71xx, record still says Windows 10
            see("Active Directory", name, "", f"10.10.40.{n}", "Windows 11 Enterprise 24H2", days)
            continue
        if n in (17, 18):                                            # not seen for months
            see("Active Directory", name, "", "", os_, 88 + n)
            continue
        see("Active Directory", name, "", f"10.10.40.{n}", os_, days)
    for n in range(1, 41):
        name = f"LT-{n:03d}"
        owner = users[(n * 3) % len(users)] if n not in (8, 9) else ""       # two laptops with no owner
        if n == 22:
            owner = "jmorales"
        serial = f"5CG{3100+n}"
        if n == 33:
            serial = f"5CG{3100+31}"                                           # re-imaged LT-031 registered again as LT-033
        loc = vlc if n in (36, 37, 38) else hq
        status, retired = "Operational", ""
        if n == 12:
            status, retired = "Retired", "2026-09-15"
        ci(f"CI5{n:03d}", name, "Laptop", owner, "Field Services", loc, serial, "", "Windows 11 Enterprise 24H2", status=status, retired=retired,
           updated=70)
        if n == 12:
            see("Intune", name, serial, "", "Windows 11 Enterprise 24H2", 7)   # retired, still checking in
            continue
        if n in (25, 26, 27):
            see("Intune", name, serial, "", "Windows 11 Enterprise 24H2", 60 + n)
            continue
        if n == 33:
            continue                                                           # the duplicate: Intune knows the device once
        see("Intune", name, serial, "", "Windows 11 Enterprise 24H2", rnd.randint(0, 9), "Zaragoza warehouse" if n == 38 else "")
    # devices nobody registered
    see("vCenter", "vm-temp-migr", "", "10.10.2.95", "Windows Server 2022 Standard", 0)
    see("Active Directory", "SRV-TEST-NEW", "", "10.10.2.96", "Windows Server 2022 Standard", 2)
    see("Network scan", "sw-zar-02", "FOC2799X1Z", "10.20.0.3", "Cisco IOS XE 17.9", 0)
    for n in (90, 91, 92):
        see("Intune", f"LT-{n:03d}", f"5CG{3100+n}", "", "Windows 11 Enterprise 24H2", rnd.randint(0, 5))

    # --- applications and databases
    apps = [("APP-ORD-API", "Order management API", "application", "Order management", "high", "jmorales", "Applications", "ORD-APP-01"),
            ("APP-ORD-WEB", "Order management web", "application", "Order management", "high", "agil", "Applications", "ORD-APP-02"),
            ("APP-WMS", "Contoso WMS", "application", "Warehouse management", "high", "tmoya", "Applications", "WMS-APP-01"),
            ("APP-PAY", "Payroll", "application", "Payroll", "high", "iblanco", "Applications", "PAY-APP-01"),
            ("APP-RPT", "Finance reports", "application", "Finance reporting", "medium", "sleon", "Applications", "RPT-01-OLD"),
            ("APP-FLT", "Fleet tracking", "application", "Fleet tracking", "medium", "rmarin", "Applications", "FLT-APP-01"),
            ("APP-INTRA", "Intranet", "application", "Intranet", "low", "iblanco", "Applications", "INTRA-01"),
            ("APP-PRINT", "Print management", "application", "Printing", "low", "dprieto", "Applications", ""),
            ("APP-MAIL", "Email", "application", "Email and collaboration", "medium", "lruiz", "Applications", ""),
            ("DB-ORD", "Orders database", "database", "Order management", "high", "jortega", "Database", "ORD-DB-01"),
            ("DB-WMS", "WMS database", "database", "Warehouse management", "high", "jortega", "Database", "WMS-DB-01"),
            ("DB-PAY", "Payroll database", "database", "Payroll", "high", "jortega", "Database", "SQL-01"),
            ("DB-RPT", "Reporting warehouse", "database", "Finance reporting", "medium", "jmorales", "Database", "SQL-2014-LEG"),
            ("DB-FLT", "Fleet database", "database", "Fleet tracking", "medium", "jortega", "Database", "FLT-APP-01")]
    names = {c["Name"]: c["CI"] for c in cis}
    ci("CI1099", "RPT-01-OLD", "Virtual machine", "mserrano", "Windows Servers", dc, "", "10.10.2.15", "Windows Server 2012 R2 Standard",
       "Finance reporting", "medium", status="Retired", retired="2026-06-30", updated="2026-06-30")
    names["RPT-01-OLD"] = "CI1099"
    for i, (cid, name, cls_, svc, crit, owner, grp, host) in enumerate(apps):
        ci(cid, name, cls_.title(), owner, grp, "", "", "", "", svc, crit, updated=30)
        if host:
            rels.append({"Parent": cid, "Child": names[host], "Type": "Runs on"})
    rels.append({"Parent": "APP-ORD-API", "Child": "DB-ORD", "Type": "Depends on"})
    rels.append({"Parent": "APP-ORD-WEB", "Child": "APP-ORD-API", "Type": "Depends on"})
    rels.append({"Parent": "APP-WMS", "Child": "DB-WMS", "Type": "Depends on"})
    rels.append({"Parent": "APP-PAY", "Child": "DB-PAY", "Type": "Depends on"})
    rels.append({"Parent": "APP-RPT", "Child": "DB-RPT", "Type": "Depends on"})
    rels.append({"Parent": "APP-FLT", "Child": "DB-FLT", "Type": "Depends on"})
    rels.append({"Parent": "APP-INTRA", "Child": "VM-OLD-17", "Type": "Depends on"})        # a CI deleted without its relationships
    rels.append({"Parent": "MON-01", "Child": "VM-OLD-18", "Type": "Depends on"})
    for n in range(1, 5):
        for vm in [c for c in cis if c["Class"] == "Virtual machine" and c["Status"] == "Operational"][n - 1::4]:
            rels.append({"Parent": vm["CI"], "Child": f"CI{1000+n}", "Type": "Hosted on"})
    # a group that no longer exists
    for c in cis:
        if c["Name"] in ("WSUS-01",):
            c["SupportGroup"] = "Infrastructure Operations"
        if c["Name"] == "JUMP-01":
            c["SupportGroup"] = ""

    # --- incidents of the last 30 days
    live = [c for c in cis if c["Status"] == "Operational"]
    mix = [("Service Desk", 120, 7), ("Field Services", 45, 14), ("Network", 25, 1), ("Windows Servers", 30, 2), ("Applications", 18, 1)]
    n = 0
    for grp, total, none in mix:
        pool = [c for c in live if c["SupportGroup"] == grp] or live
        for k in range(total):
            n += 1
            opened = RD - timedelta(days=rnd.randint(1, 30), hours=rnd.randint(0, 9))
            cid = "" if k < none else rnd.choice(pool)["CI"]
            incs.append({"Incident": f"INC{40100+n}", "Opened": opened.isoformat(), "CI": cid, "Group": grp, "Service": ""})
    incs[3]["CI"] = "CI5012"          # the retired laptop
    incs[9]["CI"] = "CI5012"
    incs[150]["CI"] = "CI1099"        # the retired reporting server
    for i in incs:
        c = next((x for x in cis if x["CI"] == i["CI"]), None)
        i["Service"] = c["BusinessService"] if c else ""
    # make sure the stale, idle records have no tickets
    idle = {names[x] for x in ("OLD-RPT-02", "TEST-WEB-03", "BKP-OLD-02")} | {"CI4017", "CI4018"}
    for i in incs:
        if i["CI"] in idle:
            i["CI"] = "CI2000"

    # --- changes of the last 30 days
    chg = [("CHG7101", "CI4004", 13, "Successful", "Windows 11 upgrade"), ("CHG7102", "CI4005", 12, "Successful", "Windows 11 upgrade"),
           ("CHG7103", "CI4006", 11, "Successful", "Windows 11 upgrade"), ("CHG7110", "CI1099", 9, "Successful", "Reporting service restart and patching"),
           ("CHG7111", "CI2007", 20, "Successful", "Database patching"), ("CHG7112", "CI3001", 18, "Successful", "Core switch firmware"),
           ("CHG7113", "CI2008", 6, "Cancelled", "WMS upgrade"), ("CHG7114", "CI1005", 25, "Successful", "Backup agent update")]
    for cid, ci_, days, state, summary in chg:
        chgs.append({"Change": cid, "CI": ci_, "Implemented": _d(days), "State": state, "Summary": summary})
    for c in cis:                         # records touched by the other changes were updated afterwards
        if c["CI"] in ("CI2007", "CI3001", "CI1005", "CI2008"):
            c["Updated"] = _d(2)
    return {"cis": cis, "seen": seen, "rels": rels, "incs": incs, "chgs": chgs}


def write(folder: Path) -> None:
    folder = Path(folder)
    folder.mkdir(parents=True, exist_ok=True)
    b = build()

    def out(name, fields, rows):
        with (folder / name).open("w", newline="", encoding="utf-8") as fh:
            w = csv.DictWriter(fh, fieldnames=fields, lineterminator="\n")
            w.writeheader()
            w.writerows(rows)

    out("cis.csv", CI_FIELDS, b["cis"])
    out("discovery.csv", ["Source", "Name", "Serial", "IP", "OS", "Location", "LastSeen"], b["seen"])
    out("relationships.csv", ["Parent", "Child", "Type"], b["rels"])
    out("people.csv", ["User", "Name", "Enabled", "Department"],
        [{"User": u, "Name": n, "Enabled": "False" if u in DISABLED else "True", "Department": dep} for u, n, dep in PEOPLE])
    out("groups.csv", ["Group", "Manager", "Active"], [{"Group": g, "Manager": m, "Active": "True" if a else "False"} for g, m, a in GROUPS])
    out("services.csv", ["Service", "Criticality", "Owner"], [{"Service": s, "Criticality": c, "Owner": o} for s, c, o in SERVICES])
    out("incidents.csv", ["Incident", "Opened", "CI", "Group", "Service"], b["incs"])
    out("changes.csv", ["Change", "CI", "Implemented", "State", "Summary"], b["chgs"])
    settings = {"organisation": ORG, "review_date": RD.isoformat(), "previous_score": 96.2, "no_ci_threshold": 15,
                "owners": {"cmdb": "Configuration manager (Lucía Ruiz)", "process": "Service management lead (Marta Serrano)"}}
    (folder / "settings.json").write_text(json.dumps(settings, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
