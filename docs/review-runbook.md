# Monthly CMDB data quality review

## The cycle

| When | What | Who |
|---|---|---|
| First working day | Export the CMDB (CIs and relationships), the discovery sources (`Export-DiscoveryAD.ps1`, Intune, vCenter, the network scan), the directory, the support groups, the business services and last month's incidents and changes | Configuration manager |
| Same day | `python -m cmdbreview review data/`; send report.html to the support group leads | Configuration manager |
| Within two days | Reds: critical CIs nobody sees, servers or network devices with no CI, retired devices still on the network, critical CIs owned by people who left, links to retired CIs, changes on retired CIs | Support group leads |
| Within a week | The review meeting with review-pack.md: decisions, the group scorecard, the process figures | Service management lead, group leads |
| After | Actions in the ITSM tool with owner and date; this month's score kept as `previous_score` for next month | Owners |

## Reading the result

1. **Can you trust what it says is there?** Stale CIs, devices on the network with no CI, retired devices still checking in, duplicates. A device nobody registered is also a security question: find out what it is before you register it.
2. **Does it say the right things about them?** Records that disagree with discovery and changes that did not update the record. When the change process is followed but the record is still old, the gap is in how changes are closed, not in the people.
3. **Does someone answer for them?** Owners who left and support groups that no longer exist: these are the records nobody fixes.
4. **Can an outage be traced?** Applications with nothing to run on, services with no CI, links to retired CIs: impact analysis and major incidents depend on them.
5. **Does the process feed it?** Incidents with no CI per group and incidents logged against retired CIs.

## Fixing without surprises

- **Retiring a CI:** confirm with its support group, keep the record with status retired (never delete it: the history of incidents and changes stays with it).
- **Registering a device:** find out who put it there and what it does; register it with owner, group and service, or remove it from the network.
- **Merging duplicates:** keep the record with more history, move the relationships and the open tickets to it, retire the other.
- **New owners:** the support group lead names them; a critical CI never stays without an owner over a weekend.
- **CI mandatory on incidents:** turn it on for the groups above the limit first, with a short note to the team, and look at the figure again next month.

## Evidence

findings.csv and actions.csv with their dates, the decisions in review-pack.md, group-scorecard.csv and ci-quality.csv are the record of the month; keep them with the review minutes for the audit.
