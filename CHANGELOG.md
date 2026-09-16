# Changelog

All notable changes to this dataset are recorded here. The format is based on
Keep a Changelog. Releases are dated; consumers should pin to a tagged release
rather than tracking `main`.

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
