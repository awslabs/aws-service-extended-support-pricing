# Changelog

All notable changes to this dataset are recorded here. The format is based on
Keep a Changelog. Releases are dated; consumers should pin to a tagged release
rather than tracking `main`.

## [2.0.1] - 2026-10-21

### Changed
- Documentation only, no data or schema change. README, CONTRIBUTING and ROADMAP
  now say the maintainers run the monthly Price List freshness check by hand,
  because the scheduled `pricing-freshness.yml` workflow is disabled for now.
  ROADMAP lists re-enabling it. SECURITY now points consumers to the Price List API
  as the reference for verifying rates, matching CONTRIBUTING.

## [2.0.0] - 2026-10-21

### Changed
- **BREAKING: every entry now has a `match` block** that names exactly which
  aws-service-eol-data entries it prices: `serviceCode` and `engine` (copied
  exactly from the lifecycle dataset), plus optional `versionNumbers` and, for
  Aurora, `capacityMode`. The top-level `serviceCode` and `engine` fields are
  removed. Read `s["match"]["serviceCode"]` instead of `s["serviceCode"]`.
- **BREAKING:** Aurora `serviceCode` renamed from `aurora` to `rds-aurora`, to
  match the aws-service-eol-data v2.0 RDS/Aurora split.
- **BREAKING:** DocumentDB `engine` changed from `"docdb"` to `null`, to match
  the lifecycle dataset (which has no DocumentDB engine). In v1 the two datasets
  never joined for DocumentDB.
- **BREAKING:** Aurora Serverless v2 moved from its own `aurora-serverless-v2`
  serviceCode to `rds-aurora` with `capacityMode: "serverless-v2"`, one entry per
  engine. No lifecycle entry carried `aurora-serverless-v2`, so these rates could
  never be found by a join.
- **BREAKING:** OpenSearch split into rate groups by `versionNumbers`. Legacy
  versions (Elasticsearch 1.5 to 7.8 except 5.6, OpenSearch 1.0 to 1.2 and 2.3
  to 2.9) gain an `extended_instance` tier: from Nov 7, 2026 the surcharge equals
  the on-demand instance price (`instancePriceMultiplier: 1.0`). Current versions
  (Elasticsearch 5.6, 6.8, 7.9, 7.10, OpenSearch 1.3 and 2.11 to 2.19) stay at
  the per-NIH rate. Source: the AWS Big Data Blog post on extended version
  lifecycle timelines (Aug 2026).
- Every tier has a stable `id` (`year1_2`, `year3`, `extended`,
  `extended_instance`) matching the keys in `regionalRates` / `instanceRates`.
- `schemaVersion` is now `2.0`.

### Added
- `tierStartDates`: exact per-version tier start dates from the AWS release
  calendars (RDS MySQL, RDS PostgreSQL, Aurora MySQL, Aurora PostgreSQL,
  DocumentDB, ElastiCache, OpenSearch legacy). `null` means the tier does not
  apply: Aurora MySQL 8.0 has no Year 3 tier. Versions not listed fall back to
  `monthsFromEndOfStandardSupport`, which is approximate (Aurora MySQL 5.7 Year
  3 starts 25 months after end of standard support, not 24). Includes Aurora
  PostgreSQL 18 (Year 1-2 from 2031-03-01, Year 3 from 2033-03-01), which the
  lifecycle dataset carries from the Aurora release calendar because the AWS Health
  Version Catalog does not return it yet.
- `scripts/check_eol_join.py` and a CI step (on change and monthly) that fails if
  a `match` prices nothing, a billed lifecycle entry has no price, an entry
  matches more than one price, or a tier date falls outside the version's
  Extended Support window.
- `joinKey`: plain-language description of the join rule.

### Fixed
- The pricing freshness check silently skipped Aurora after the
  `aurora` -> `rds-aurora` rename. A probe that cannot find its entry is now
  reported as an error, which opens a review Issue.
- The freshness check could report "0 drift" when a query returned nothing
  (for example after AWS renames a Price List attribute or value). Each probe
  now records how many Price List rates it found per entry and tier, the report
  lists the counts, and zero found where the dataset has rates is an error.
- The freshness check only compared rates the Price List API returns, so a
  dataset rate with no API counterpart passed silently. Those rates are now
  listed by region for manual review (never removed automatically). The first
  run found 28 Aurora MySQL Year 3 regions and 2 OpenSearch regions in this
  state.
- Removed 28 Aurora MySQL (provisioned) Year 3 rates that were calculated by
  hand as 2x Year 1-2 rather than taken from the AWS Price List: the API
  publishes Aurora MySQL Year 3 only for mx-central-1 so far, and AWS's own
  rounding differs from 2x in 6 regions (for example eu-west-2 0.235, not
  0.236). The entry's `notes` explain how to estimate Year 3 meanwhile; the
  freshness check adds each region's rate when AWS publishes it.
- Removed OpenSearch rates for `ca-west-2` and `me-west-1` from all four
  OpenSearch entries. These are not AWS Region codes (present since 1.0.0).

### Notes
- Rates are unchanged from 1.0.0 (verified field by field during the
  restructure). The OpenSearch legacy instance-price tier is new data, not a
  rate change to existing tiers.
- ElastiCache Extended Support remains **Redis OSS only**: no Valkey or Memcached
  Extended Support rates are published (as of 2026-10-20). Valkey is the engine
  that deprecated Redis caches are upgraded *to*, and no Valkey version has an
  announced end of standard support; no `valkey` engine entry is added. A
  `valkey` lifecycle version is current (not in Extended Support), so finding no
  price for it is the correct result, not a gap. The ElastiCache entry's `notes`
  now state this scope (GitHub issue #6).
- The freshness check now queries ElastiCache Extended Support prices without a
  `cacheEngine` filter and flags any non-Redis engine for manual review (opens an
  Issue), so a first Valkey or Memcached rate cannot be missed.
- RDS Extended Support is available for MySQL and PostgreSQL only, so there is
  no MariaDB entry.

## [1.0.0] - 2026-09-16

### Added
- Initial public release of the AWS Extended Support pricing dataset.
- Pricing models for Amazon EKS, RDS (MySQL, PostgreSQL), Aurora (MySQL,
  PostgreSQL), Aurora Serverless v2, ElastiCache (Redis), OpenSearch Service
  (OpenSearch and Elasticsearch), and DocumentDB.
- Per-instance `instanceRates` model (`region -> instanceKey -> {year1_2,
  year3}`) for services whose Extended Support rate varies by instance:
  DocumentDB by instance family and ElastiCache by node type.
- JSON schema (`data/schema.json`), worked examples in the README, and an
  official `sourceUrl` on every entry.
