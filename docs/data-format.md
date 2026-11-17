# Data format

Every file is CSV (comma or semicolon, UTF-8 or UTF-16), column names are matched without case, spaces or accents, and the usual
names from ITSM tools work (Assignment group, Managed by, sys_class_name, Install status…). Only `cis.csv` is required; each other
file turns on its checks.

## cis.csv (required): the CMDB export

| Column | Also read as | Notes |
|---|---|---|
| CI | Id, Sys id, Asset tag | Unique id; the name is used when empty |
| Name | Hostname, Display name | |
| Class | Type, Category, sys_class_name | server, virtual machine, desktop, laptop, network, storage, application, database |
| Status | Install status, Lifecycle | Retired, disposed or decommissioned = retired; in stock; in maintenance; anything else is operational |
| Environment | Used for | |
| Owner | Owned by, Managed by | User id or name, checked against people.csv |
| SupportGroup | Assignment group | Checked against groups.csv |
| Location, Serial, IP, OS | Site, Serial number, IP address, Operating system | Compared with discovery |
| BusinessService | Business service | Checked against services.csv |
| Criticality | Business criticality, Tier | 1 / critical / high → high: its gaps are red |
| Updated | Last updated, sys_updated_on | Compared with the changes implemented on it |
| Retired | Retired on, Decommissioned | Date it was retired |

## relationships.csv

`Parent, Child, Type`: the parent depends on, runs on or is hosted on the child. `Runs on`, `Hosted on` and `Installed on` count as what
an application or database runs on.

## discovery.csv

`Source, Name, Serial, IP, OS, Location, LastSeen`: one row per device per source. `scripts/Export-DiscoveryAD.ps1` writes the Active
Directory rows; Intune (managed devices), vCenter (VMs and hosts), the network scan or your discovery tool export the same columns. A
CI is matched by serial first, then by name (without the domain).

## people.csv, groups.csv, services.csv

- people: `User, Name, Enabled, Department` (an export of the directory).
- groups: `Group, Manager, Active`.
- services: `Service, Criticality, Owner`.

## incidents.csv, changes.csv

- incidents of the period: `Incident, Opened, CI, Group, Service`.
- changes of the period: `Change, CI, Implemented, State, Summary`. Cancelled, failed or rejected changes are ignored.

## settings.json

| Setting | Default | |
|---|---|---|
| organisation | Your organisation | Title of the report |
| review_date | today | Date of the review |
| required | per class | Fields each class must have |
| stale_days | 14 for servers, VMs, network and storage; 45 for desktops and laptops | Days without discovery before a live CI is stale |
| no_ci_threshold | 15 | % of a group's incidents without CI before it is a finding (groups with 10 incidents or more) |
| score_amber, score_red | 90, 80 | Score bands |
| previous_score | none | Last month's score, for the trend |
| owners | cmdb, process | Owners of the CMDB-wide and process findings |

## Checks

| Area | Code | Finding | Severity |
|---|---|---|---|
| Completeness | CI-MISSING | A field its class needs is empty | AMBER (RED if critical) |
| Accuracy | CI-STALE | Live CI not seen by any source within stale_days; a candidate to retire when no ticket, change or live CI needs it | AMBER (RED if critical) |
| Accuracy | CI-UNREGISTERED | Seen lately, no CI | AMBER (RED if a server or network device) |
| Accuracy | CI-MISMATCH | IP address, operating system (same family and version) or location differ | AMBER |
| Accuracy | CI-DUPLICATE | Two live records with the same serial, or the same name and class | AMBER |
| Accuracy | CI-RETIRED-SEEN | Retired CI seen after its retirement | RED |
| Ownership | OWN-LEFT | Owner disabled or not in the directory | AMBER (RED if any is critical) |
| Ownership | OWN-GROUP | Support group not active | AMBER |
| Relationships | REL-DANGLING | Relationship to a CI that does not exist | AMBER |
| Relationships | REL-RETIRED | Live CI depends on a retired CI | RED |
| Relationships | REL-ORPHAN | Application or database with nothing it runs on | AMBER (RED if critical) |
| Relationships | REL-SERVICE-EMPTY | Business service with no live CI | AMBER (RED if critical) |
| Process | PROC-INC-NO-CI | Share of a group's incidents with no CI above the limit | AMBER |
| Process | PROC-INC-RETIRED | Incidents logged against retired CIs | AMBER |
| Process | PROC-CHG-RETIRED | Change implemented on a CI after it was retired | RED |
| Process | PROC-CHG-NOT-UPDATED | Change implemented after the record's last update | AMBER |

**Score per CI:** the average of the parts that apply to it: the share of required fields filled in; whether discovery sees it (1),
sees it with differences (0.5) or not at all (0); whether it was seen within stale_days; and, for applications and databases, whether
they have what they run on. The overall, class and group scores are averages of the CI scores.
