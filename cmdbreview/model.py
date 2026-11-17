"""Loading: the CMDB export (cis.csv), its relationships (relationships.csv), what the discovery sources see (discovery.csv: Active
Directory, Intune, vCenter, a network scan…), the people directory (people.csv), the support groups (groups.csv), the business
services (services.csv), the incidents and changes of the period (incidents.csv, changes.csv) and the settings (settings.json).
Forgiving column names, into plain dataclasses. cis.csv is required; every other file adds its checks when it is there."""
from __future__ import annotations

import csv
import json
import re
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

CI_ALIASES = {
    "id": ["CI", "Id", "CI id", "Sys id", "sys_id", "Asset", "Asset tag", "ConfigurationItem"],
    "name": ["Name", "CI name", "Hostname", "Display name"],
    "cls": ["Class", "CI class", "Type", "Category", "sys_class_name"],
    "status": ["Status", "Operational status", "Install status", "Lifecycle", "State"],
    "environment": ["Environment", "Env", "Used for"],
    "owner": ["Owner", "Owned by", "Managed by", "Assigned to", "User"],
    "group": ["SupportGroup", "Support group", "Assignment group", "Resolver group", "Group"],
    "location": ["Location", "Site", "Office", "Room"],
    "serial": ["Serial", "SerialNumber", "Serial number", "S/N"],
    "ip": ["IP", "IPAddress", "IP address", "Address"],
    "os": ["OS", "OperatingSystem", "Operating system", "OS version"],
    "service": ["BusinessService", "Business service", "Service"],
    "criticality": ["Criticality", "Business criticality", "Tier", "Priority"],
    "updated": ["Updated", "Last updated", "sys_updated_on", "Modified"],
    "retired": ["Retired", "Retired on", "Disposed", "Decommissioned"],
}
REL_ALIASES = {
    "parent": ["Parent", "From", "Source", "Upstream"],
    "child": ["Child", "To", "Target", "Downstream"],
    "kind": ["Type", "Relationship", "Kind"],
}
DISC_ALIASES = {
    "source": ["Source", "Discovery source", "Tool"],
    "name": ["Name", "Hostname", "DNSHostName", "Device name", "ComputerName"],
    "serial": ["Serial", "SerialNumber", "Serial number"],
    "ip": ["IP", "IPv4Address", "IP address", "Address"],
    "os": ["OS", "OperatingSystem", "Operating system"],
    "location": ["Location", "Site"],
    "last_seen": ["LastSeen", "Last seen", "LastLogonDate", "Last contact", "Last check-in", "LastSyncDateTime"],
}
PEOPLE_ALIASES = {
    "id": ["User", "SamAccountName", "Username", "Id", "UserPrincipalName"],
    "name": ["Name", "DisplayName", "Display name"],
    "enabled": ["Enabled", "Active", "AccountEnabled", "Status"],
    "department": ["Department", "Team"],
}
GROUP_ALIASES = {
    "id": ["Group", "SupportGroup", "Support group", "Name"],
    "manager": ["Manager", "Lead", "Owner"],
    "active": ["Active", "Enabled", "Status"],
}
SERVICE_ALIASES = {
    "id": ["Service", "Business service", "Name"],
    "criticality": ["Criticality", "Tier", "Business criticality"],
    "owner": ["Owner", "Service owner"],
}
INC_ALIASES = {
    "id": ["Incident", "Number", "Ticket", "Id"],
    "opened": ["Opened", "Created", "Opened at"],
    "ci": ["CI", "Configuration item", "cmdb_ci", "Asset"],
    "group": ["Group", "Assignment group", "SupportGroup", "Support group"],
    "service": ["Service", "Business service"],
}
CHG_ALIASES = {
    "id": ["Change", "Number", "Id"],
    "ci": ["CI", "Configuration item", "cmdb_ci"],
    "implemented": ["Implemented", "Closed", "End", "Implemented on", "Completed"],
    "state": ["State", "Status", "Outcome"],
    "summary": ["Summary", "Short description", "Title", "Description"],
}
YES = {"yes", "y", "true", "1", "x", "si", "enabled", "active", "on"}
FILES = {"cis.csv": "CMDB export", "relationships.csv": "Relationships", "discovery.csv": "Discovery sources", "people.csv": "People directory",
         "groups.csv": "Support groups", "services.csv": "Business services", "incidents.csv": "Incidents", "changes.csv": "Changes"}
CLASSES = {"server": "Physical server", "vm": "Virtual machine", "workstation": "Desktop", "laptop": "Laptop", "network": "Network device",
           "application": "Application", "database": "Database", "storage": "Storage"}
DISCOVERABLE = {"server", "vm", "workstation", "laptop", "network", "storage"}     # a discovery source should see them
HOSTED = {"application", "database"}                                                # they run on something
HOST_REL = ("runs on", "hosted on", "installed on")


def _norm(s) -> str:
    s = unicodedata.normalize("NFKD", str(s or "")).encode("ascii", "ignore").decode().lower()
    return re.sub(r"\s+", " ", s).strip()


def key(s) -> str:
    """A name to match on: lower case, no domain suffix, no spaces."""
    return re.sub(r"[\s_]+", "", _norm(s).split(".")[0])


def yes(v) -> bool:
    return _norm(v) in YES


def parse_dt(v) -> datetime | None:
    s = str(v or "").strip()
    if not s:
        return None
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M", "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M",
                "%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y %I:%M:%S %p"):
        try:
            return datetime.strptime(s[:22].strip(), fmt)
        except ValueError:
            pass
    return None


def parse_d(v) -> date | None:
    x = parse_dt(v)
    return x.date() if x else None


def ip(v) -> str:
    m = re.search(r"\d{1,3}(?:\.\d{1,3}){3}", str(v or ""))
    return m.group(0) if m else ""


def cls(v) -> str:
    n = _norm(str(v or "").replace("_", " "))
    for k, words in (("vm", ("virtual", "vm", "guest")), ("laptop", ("laptop", "notebook", "portable")),
                     ("workstation", ("workstation", "desktop", "pc")), ("database", ("database", "db instance", "sql instance")),
                     ("application", ("application", "app", "software")), ("storage", ("storage", "san", "nas")),
                     ("network", ("network", "switch", "router", "firewall", "access point", "wlc")), ("server", ("server", "host"))):
        if any(w == n or re.search(r"\b" + re.escape(w) + r"\b", n) for w in words):
            return k
    return "server" if not n else n


def status(v) -> str:
    n = _norm(v)
    if any(w in n for w in ("retired", "disposed", "decommission", "absent")):
        return "retired"
    if any(w in n for w in ("stock", "store", "spare")):
        return "stock"
    if any(w in n for w in ("maint", "repair")):
        return "maintenance"
    return "operational"


def criticality(v) -> str:
    n = _norm(v)
    if n in ("1", "tier 1", "critical", "high", "1 - critical", "1 - high") or n.startswith("crit") or n.startswith("high"):
        return "high"
    if n in ("2", "tier 2", "medium", "2 - medium") or n.startswith("med"):
        return "medium"
    return "low" if n else ""


def os_family(v) -> str:
    """'Windows Server 2019 Standard' -> 'windows server 2019'; enough to tell an upgrade from a different wording."""
    n = _norm(v)
    m = re.search(r"(windows server \d{4}|windows \d+|red hat enterprise linux \d+|rhel \d+|ubuntu \d+\.\d+|debian \d+|rocky linux \d+|"
                  r"ios xe|fortios|esxi \d+|macos \d+)", n)
    if not m:
        return n
    out = m.group(1)
    return out.replace("red hat enterprise linux", "rhel")


@dataclass
class CI:
    id: str
    name: str
    cls: str
    status: str = "operational"
    environment: str = ""
    owner: str = ""
    group: str = ""
    location: str = ""
    serial: str = ""
    ip: str = ""
    os: str = ""
    service: str = ""
    criticality: str = ""
    updated: date | None = None
    retired: date | None = None


@dataclass
class Rel:
    parent: str
    child: str
    kind: str


@dataclass
class Seen:
    source: str
    name: str
    serial: str = ""
    ip: str = ""
    os: str = ""
    location: str = ""
    last_seen: date | None = None


@dataclass
class Person:
    id: str
    name: str
    enabled: bool = True
    department: str = ""


@dataclass
class Group:
    id: str
    manager: str = ""
    active: bool = True


@dataclass
class Service:
    id: str
    criticality: str = ""
    owner: str = ""


@dataclass
class Incident:
    id: str
    opened: date | None
    ci: str = ""
    group: str = ""
    service: str = ""


@dataclass
class Change:
    id: str
    ci: str
    implemented: date | None
    state: str = ""
    summary: str = ""


@dataclass
class Settings:
    organisation: str = "Your organisation"
    review_date: date = field(default_factory=date.today)
    required: dict = field(default_factory=lambda: {
        "server": ["owner", "group", "location", "serial", "ip", "os", "criticality"],
        "vm": ["owner", "group", "ip", "os", "criticality"],
        "workstation": ["owner", "group", "location", "serial", "os"],
        "laptop": ["owner", "group", "serial", "os"],
        "network": ["owner", "group", "location", "serial", "ip"],
        "storage": ["owner", "group", "location", "serial"],
        "application": ["owner", "group", "service", "criticality"],
        "database": ["owner", "group", "service", "criticality"]})
    stale_days: dict = field(default_factory=lambda: {"server": 14, "vm": 14, "network": 14, "storage": 14, "workstation": 45, "laptop": 45})
    no_ci_threshold: float = 15.0        # % of a group's incidents with no CI before it is a finding
    score_amber: float = 90.0
    score_red: float = 80.0
    previous_score: float | None = None
    owners: dict = field(default_factory=lambda: {"cmdb": "Configuration manager", "process": "Service management"})


@dataclass
class Data:
    cis: list[CI]
    rels: list[Rel] = field(default_factory=list)
    seen: list[Seen] = field(default_factory=list)
    people: list[Person] = field(default_factory=list)
    groups: list[Group] = field(default_factory=list)
    services: list[Service] = field(default_factory=list)
    incidents: list[Incident] = field(default_factory=list)
    changes: list[Change] = field(default_factory=list)
    settings: Settings = field(default_factory=Settings)
    sources: dict = field(default_factory=dict)       # file -> rows read


def _read(path: Path) -> tuple[list[str], list[dict]]:
    raw = path.read_bytes()
    text = raw.decode("utf-16") if raw.startswith((b"\xff\xfe", b"\xfe\xff")) else raw.decode("utf-8-sig")
    sample = text[:2000]
    delim = ";" if sample.count(";") > sample.count(",") else ","
    rows = list(csv.DictReader(text.splitlines(), delimiter=delim))
    return (list(rows[0].keys()) if rows else []), rows


def _rows(path: Path, aliases: dict) -> list[dict]:
    fields, rows = _read(path)
    lower = {_norm(f): f for f in fields}
    pick = {}
    for k, names in aliases.items():
        for n in names:
            if _norm(n) in lower:
                pick[k] = lower[_norm(n)]
                break
    return [{k: str(r.get(col) or "").strip() for k, col in pick.items()} for r in rows]


def _settings(path: Path) -> Settings:
    s = Settings()
    if not path.exists():
        return s
    raw = json.loads(path.read_text(encoding="utf-8"))
    for k, v in raw.items():
        if k == "review_date":
            s.review_date = parse_d(v) or s.review_date
        elif k in ("required", "stale_days", "owners") and isinstance(v, dict):
            getattr(s, k).update(v)
        elif hasattr(s, k):
            setattr(s, k, v)
    return s


def load(folder: Path) -> Data:
    folder = Path(folder)
    p = folder / "cis.csv"
    if not p.exists():
        raise FileNotFoundError(f"{p} not found: export the CMDB to cis.csv (docs/data-format.md)")
    d = Data(cis=[], settings=_settings(folder / "settings.json"))
    for r in _rows(p, CI_ALIASES):
        if not r.get("id") and not r.get("name"):
            continue
        d.cis.append(CI(id=r.get("id") or r.get("name"), name=r.get("name") or r.get("id"), cls=cls(r.get("cls")), status=status(r.get("status")),
                        environment=r.get("environment", ""), owner=r.get("owner", ""), group=r.get("group", ""), location=r.get("location", ""),
                        serial=r.get("serial", "").upper(), ip=ip(r.get("ip")), os=r.get("os", ""), service=r.get("service", ""),
                        criticality=criticality(r.get("criticality")), updated=parse_d(r.get("updated")), retired=parse_d(r.get("retired"))))
    d.sources["cis.csv"] = len(d.cis)
    readers = (("relationships.csv", REL_ALIASES, lambda r: Rel(r.get("parent", ""), r.get("child", ""), _norm(r.get("kind")))),
               ("discovery.csv", DISC_ALIASES, lambda r: Seen(r.get("source", ""), r.get("name", ""), r.get("serial", "").upper(), ip(r.get("ip")),
                                                              r.get("os", ""), r.get("location", ""), parse_d(r.get("last_seen")))),
               ("people.csv", PEOPLE_ALIASES, lambda r: Person(r.get("id", ""), r.get("name", ""), yes(r.get("enabled", "yes")), r.get("department", ""))),
               ("groups.csv", GROUP_ALIASES, lambda r: Group(r.get("id", ""), r.get("manager", ""), yes(r.get("active", "yes")))),
               ("services.csv", SERVICE_ALIASES, lambda r: Service(r.get("id", ""), criticality(r.get("criticality")), r.get("owner", ""))),
               ("incidents.csv", INC_ALIASES, lambda r: Incident(r.get("id", ""), parse_d(r.get("opened")), r.get("ci", ""), r.get("group", ""), r.get("service", ""))),
               ("changes.csv", CHG_ALIASES, lambda r: Change(r.get("id", ""), r.get("ci", ""), parse_d(r.get("implemented")), _norm(r.get("state")), r.get("summary", ""))))
    target = {"relationships.csv": d.rels, "discovery.csv": d.seen, "people.csv": d.people, "groups.csv": d.groups, "services.csv": d.services,
              "incidents.csv": d.incidents, "changes.csv": d.changes}
    for name, aliases, make in readers:
        f = folder / name
        if f.exists():
            rows = [make(r) for r in _rows(f, aliases)]
            target[name].extend(x for x in rows if any(str(v) for v in vars(x).values()))
            d.sources[name] = len(target[name])
    return d
