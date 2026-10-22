# Migrating from v1 to v2

v2.0 restructures each pricing entry around a `match` block, so every rate card says
exactly which [aws-service-eol-data](https://github.com/awslabs/aws-service-eol-data)
entries it prices. Rates are unchanged.

**You are not forced to migrate immediately.** Releases are tagged, so a v1.x pin is
unaffected. v2 is the recommended path forward.

## What changed

| v1 | v2 |
|----|----|
| top-level `serviceCode`, `engine` | `match.serviceCode`, `match.engine` |
| `serviceCode: "aurora"` | `match.serviceCode: "rds-aurora"`, `match.capacityMode: "provisioned"` |
| `serviceCode: "aurora-serverless-v2"` (one entry, `engine: null`) | `match.serviceCode: "rds-aurora"`, `match.capacityMode: "serverless-v2"`, one entry per engine (`mysql`, `postgresql`) with the same rates |
| DocumentDB `engine: "docdb"` | `match.engine: null` (matches the lifecycle dataset) |
| one OpenSearch entry per engine | two entries per engine, selected by `match.versionNumbers`: current versions (per-NIH rate) and legacy versions (per-NIH rate, then a surcharge equal to the on-demand instance price from Nov 7, 2026) |
| tiers identified by `label` | tiers also carry a stable `id` (`year1_2`, `year3`, `extended`, `extended_instance`) |
| tier timing only as `monthsFromEndOfStandardSupport` | `tierStartDates[versionNumber][tierId]` gives exact dates where AWS publishes them; months remain the fallback |
| `schemaVersion: "1.0"` | `schemaVersion: "2.0"` |

## Action

1. Read the join key from `match`:

   ```python
   # v1
   rds_mysql = next(s for s in data["services"]
                    if s["serviceCode"] == "rds" and s["engine"] == "mysql")
   # v2
   rds_mysql = next(s for s in data["services"]
                    if s["match"]["serviceCode"] == "rds" and s["match"]["engine"] == "mysql")
   ```

2. When joining to the lifecycle dataset, also respect `versionNumbers` and, for Aurora,
   `capacityMode`. The README's `find_price()` function shows the full rule.
3. Replace `aurora` with `rds-aurora`, and `aurora-serverless-v2` with
   `rds-aurora` + `capacityMode: "serverless-v2"`.
4. For DocumentDB, match `engine` as `null`. In SQL, compare engines with
   `COALESCE(engine, '')` or `IS NOT DISTINCT FROM`, because `NULL = NULL` is not true.
5. For tier timing, prefer `tierStartDates` over `monthsFromEndOfStandardSupport`.
   Example: Aurora MySQL 8.0 has `"year3": null` (no Year 3 tier), and Aurora MySQL 5.7
   Year 3 starts Dec 1, 2026, 25 months after its end of standard support.

## Note on Valkey and Memcached

ElastiCache Extended Support applies to **Redis OSS** versions only. No Valkey or
Memcached Extended Support rates are published (as of 2026-10-20). Valkey is the
engine that deprecated Redis caches are upgraded to, so it carries no Extended Support
pricing and no `valkey` entry is added. A `valkey` lifecycle version finding no price
here is the correct result: those versions are current, not in Extended Support.
