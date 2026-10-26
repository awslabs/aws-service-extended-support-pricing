# AWS Service Extended Support Pricing

![License](https://img.shields.io/github/license/awslabs/aws-service-extended-support-pricing)
![Last commit](https://img.shields.io/github/last-commit/awslabs/aws-service-extended-support-pricing)
![Latest release](https://img.shields.io/github/v/release/awslabs/aws-service-extended-support-pricing?sort=semver)
[![Validate](https://github.com/awslabs/aws-service-extended-support-pricing/actions/workflows/validate.yml/badge.svg)](https://github.com/awslabs/aws-service-extended-support-pricing/actions/workflows/validate.yml)
[![Discussions](https://img.shields.io/github/discussions/awslabs/aws-service-extended-support-pricing)](https://github.com/awslabs/aws-service-extended-support-pricing/discussions)

> **NOT AN OFFICIAL AWS API.** This is a community republication of AWS pricing data, not an official AWS product, service, or commitment. The rates are drawn from the first-party AWS Price List and the official AWS pricing pages, and each entry links its source in `sourceUrl` so you can confirm any rate before you act on it. These are public list prices and do not account for negotiated discounts, EDPs, or private pricing agreements.

A machine-readable dataset of AWS Extended Support pricing models, enabling programmatic cost calculation for resources past end of standard support.

## Why This Exists

When AWS services enter Extended Support, additional charges apply. Each service uses a different pricing model (per vCPU-hour, per cluster-hour, per normalized instance hour), with rates that vary by region and escalate over time. Customers and tooling currently have no single programmatic source for these pricing formulas, forcing manual lookups across individual service pricing pages.

This repository provides consolidated, structured pricing data that enables automated cost projection for Extended Support charges across all applicable AWS services.

## Examples of use cases

- **Forecast Extended Support exposure** before the charges land - project the monthly or annual surcharge for resources heading past end of standard support, per account or per team.
- **Build the upgrade business case** - quantify the cost of not upgrading (the Extended Support surcharge) against the effort to upgrade, and prioritize the fleet by dollar impact.
- **Budgeting, chargeback, and showback** - attribute projected Extended Support cost to owners using the per-vCPU, per-node, or per-ACU model.
- **Dashboards and FinOps tooling** - feed the pricing model into any dashboard or FinOps tool (such as QuickSight, Grafana, Tableau, or your own internal tooling) so every consumer shares one figured-out calculation instead of re-deriving it.
- **Agents and chatbots** - give an LLM or agent a structured source to answer "what will Extended Support cost for X?" with a `sourceUrl` to cite.
- **Enrich CI/CD, change management, and ITSM workflows with cost** - when an end-of-support-driven pipeline gate, change record, or ServiceNow/Jira ticket fires (often off the companion lifecycle dataset), attach the projected Extended Support surcharge so the decision carries a dollar figure, not just a date.
- **Pair with [aws-service-eol-data](https://github.com/awslabs/aws-service-eol-data)** to answer "when does my version lose support, and what will it cost if I don't upgrade?" in one join.

## Data Format

### File Location

```
data/pricing.json
```

### Schema

```json
{
  "schemaVersion": "2.0",
  "lastUpdated": "2026-10-19",
  "services": [
    {
      "match": { "serviceCode": "eks", "engine": null },
      "serviceName": "Amazon EKS",
      "pricingUnit": "cluster-hour",
      "formula": "rate x clusters x hours",
      "tiers": [
        { "id": "extended", "label": "Extended Support", "monthsFromEndOfStandardSupport": [0, 12], "rate": 0.60 }
      ],
      "sourceUrl": "https://aws.amazon.com/eks/pricing/"
    }
  ]
}
```

### Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `match` | object | Join key into aws-service-eol-data. An entry prices the eol entries it matches. |
| `match.serviceCode` | string | Copied exactly from aws-service-eol-data (`eks`, `rds`, `rds-aurora`, `elasticache`, `opensearch`, `docdb`) |
| `match.engine` | string or null | Copied exactly from aws-service-eol-data. `null` means the service has no engine (EKS, DocumentDB) and matches eol's `null` |
| `match.versionNumbers` | array (optional) | When present, the entry prices only these eol `versionNumber` values. Used where the rate depends on the version (OpenSearch) |
| `match.capacityMode` | string (optional) | Aurora only: `provisioned` or `serverless-v2`. Not in the eol dataset; you supply it from your resource |
| `serviceName` | string | Human-readable service name |
| `pricingUnit` | string | Unit of charge (cluster-hour, vCPU-hour, ACU-hour, node-hour, normalized-instance-hour) |
| `formula` | string | Human-readable cost calculation formula |
| `tiers` | array | Pricing tiers with time ranges and rates |
| `tiers[].id` | string | Stable tier key (`year1_2`, `year3`, `extended`, `extended_instance`); matches the keys in `regionalRates` / `instanceRates` |
| `tiers[].label` | string | Tier name (e.g., "Year 1-2", "Year 3") |
| `tiers[].monthsFromEndOfStandardSupport` | array | [start, end] months after standard support ends. Approximate; prefer `tierStartDates` when present |
| `tiers[].rate` | number | Fixed rate per unit (for non-regional pricing) |
| `tiers[].rateByRegion` | boolean | If true, use `regionalRates` or `instanceRates` for per-region pricing |
| `tiers[].multiplier` | number | Multiplier applied to base rate for this tier |
| `tiers[].instancePriceMultiplier` | number | Surcharge as a multiple of the on-demand instance price (1.0 = equal to the instance price) |
| `tierStartDates` | object (optional) | Exact tier start dates from the AWS release calendars: `versionNumber -> tier id -> date`. `null` means that tier does not apply to the version (Aurora MySQL 8.0 has no Year 3). Versions not listed fall back to `monthsFromEndOfStandardSupport` |
| `regionalRates` | object | Per-region rates (when pricing varies by region) |
| `instanceRates` | object | Per-instance rates nested as `region -> instanceKey -> {year1_2, year3}`. Used where the rate varies by instance: DocumentDB is keyed by instance family (e.g. `r5`, `t3`), ElastiCache by node type (e.g. `cache.r6g.large`). |
| `normalizationFactors` | object | Instance size to normalization factor mapping (OpenSearch) |
| `resourceInputs` | array | What inputs are needed to calculate cost for this service |
| `resourceInputs[].field` | string | The variable name used in the formula |
| `resourceInputs[].source` | string | Where to get this value (e.g., instanceClass, clusterCount) |
| `resourceInputs[].description` | string | Human-readable explanation |
| `instanceClassMapping` | object | Maps DB instance class to vCPU count (RDS/Aurora). Enables cost calculation without a separate API call. |
| `versionsRef` | string | Link to companion EOL dates repository |
| `joinKey` | string | Plain-language description of the join rule |
| `examples` | array | Worked cost calculation examples |
| `sourceUrl` | string | Official AWS pricing page URL |

### Pricing Models by Service

| Service | Unit | Tiers | Regional |
|---------|------|-------|----------|
| Amazon EKS | cluster-hour | Single tier: $0.60 | No |
| Amazon RDS (MySQL/PostgreSQL) | vCPU-hour | Year 1-2, Year 3 (2x) | Yes |
| Amazon Aurora (MySQL/PostgreSQL), provisioned | vCPU-hour | Year 1-2, Year 3 (2x); Aurora MySQL 8.0 has no Year 3. Aurora MySQL Year 3 rates are published only for mx-central-1 so far (see the entry's `notes`) | Yes |
| Amazon Aurora Serverless v2 (`capacityMode: serverless-v2`) | ACU-hour | Year 1-2, Year 3 (2x). Rates are per engine. Aurora MySQL Serverless v2 Year 3 is published only for mx-central-1 so far (see the entry's `notes`) | Yes |
| Amazon ElastiCache (Redis OSS only) | node-hour | Year 1-2, Year 3 (2x) | Yes (per node type) |
| Amazon OpenSearch Service, current versions | NIH | Single tier | Yes |
| Amazon OpenSearch Service, legacy versions | NIH, then instance price | NIH rate until Nov 7, 2026; surcharge equal to the on-demand instance price from Nov 7, 2026 | Yes |
| Amazon DocumentDB | vCPU-hour | Year 1-2, Year 3 (2x) | Yes (per instance family) |

**Note on what each rate represents:** the EKS rate is the *total* cluster-hour cost during Extended Support (base control plane plus the Extended Support adder). Every other service lists the Extended Support *surcharge* only, applied on top of normal instance or capacity cost. RDS, Aurora, and Aurora Serverless v2 are per vCPU-hour (per ACU-hour for Serverless v2) and vary by region. DocumentDB is per vCPU-hour and varies by region and instance family (e.g. `r5` differs from `t3`) - see `instanceRates`. ElastiCache (Redis) is per node-hour and varies by region and node type - see `instanceRates`.

## Usage Examples

### Calculate monthly EKS Extended Support cost

```python
import json

with open('data/pricing.json') as f:
    data = json.load(f)

eks = next(s for s in data['services'] if s['match']['serviceCode'] == 'eks')
clusters = 106
hours_per_month = 730
rate = eks['tiers'][0]['rate']

monthly_cost = rate * clusters * hours_per_month
print(f"EKS Extended Support: ${monthly_cost:,.2f}/month for {clusters} clusters")
# Output: EKS Extended Support: $46,428.00/month for 106 clusters
```

### Calculate RDS Extended Support cost by region

```python
rds_mysql = next(s for s in data['services'] if s['match'] == {'serviceCode': 'rds', 'engine': 'mysql'})
region = 'us-east-1'
vcpus = 8  # db.r5.2xlarge
instances = 50
hours_per_month = 730

rate = rds_mysql['regionalRates'][region]['year1_2']
monthly_cost = rate * vcpus * instances * hours_per_month
print(f"RDS MySQL ES (Year 1-2, {region}): ${monthly_cost:,.2f}/month")
# Output: RDS MySQL ES (Year 1-2, us-east-1): $29,200.00/month
```

### Project annual cost with tier escalation

```python
# Year 1-2 vs Year 3 comparison
rate_y12 = rds_mysql['regionalRates']['us-east-1']['year1_2']
rate_y3 = rds_mysql['regionalRates']['us-east-1']['year3']

annual_y12 = rate_y12 * vcpus * instances * 8760
annual_y3 = rate_y3 * vcpus * instances * 8760
print(f"Year 1-2: ${annual_y12:,.2f}/year")
print(f"Year 3:   ${annual_y3:,.2f}/year (doubles)")
```

### Calculate ElastiCache Extended Support cost by node type

```python
ec = next(s for s in data['services'] if s['match']['serviceCode'] == 'elasticache')
region = 'us-east-1'
node_type = 'cache.r6g.2xlarge'
nodes = 6
hours_per_month = 730

rate = ec['instanceRates'][region][node_type]['year1_2']
monthly_cost = rate * nodes * hours_per_month
print(f"ElastiCache ES (Year 1-2, {region}, {node_type}): ${monthly_cost:,.2f}/month")
```

DocumentDB uses the same `instanceRates` shape, keyed by instance family instead of node type - for example `data[...]['instanceRates']['us-east-1']['r5']['year1_2']`, multiplied by vCPUs and instances.

## Relationship to aws-service-eol-data

This repository is a companion to [aws-service-eol-data](https://github.com/awslabs/aws-service-eol-data), which provides lifecycle dates. Together they enable end-to-end automation:

1. **aws-service-eol-data**: "When does my version lose support?"
2. **aws-service-extended-support-pricing** (this repo): "What will it cost if I don't upgrade?"

Each pricing entry's `match` block names the lifecycle entries it prices:

```python
def find_price(pricing, eol_entry, capacity_mode="provisioned"):
    """Return the one pricing entry for an aws-service-eol-data entry, or None.
    capacity_mode only matters for Aurora ("provisioned" or "serverless-v2")."""
    for s in pricing["services"]:
        m = s["match"]
        if m["serviceCode"] != eol_entry["serviceCode"] or m["engine"] != eol_entry.get("engine"):
            continue
        if m.get("versionNumbers") and eol_entry["versionNumber"] not in m["versionNumbers"]:
            continue
        if m.get("capacityMode") and m["capacityMode"] != capacity_mode:
            continue
        return s
    return None
```

- `serviceCode` and `engine` are copied exactly from the lifecycle dataset, so `null` matches `null` (EKS and DocumentDB have no engine). **In SQL, `NULL = NULL` is not true**: join with `COALESCE(engine, '')` on both sides, or `IS NOT DISTINCT FROM`.
- Aurora uses `serviceCode: "rds-aurora"`, matching the lifecycle dataset's RDS/Aurora split. Aurora Serverless v2 rates are under `rds-aurora` with `capacityMode: "serverless-v2"`; take the capacity mode from your cluster.
- For tier dates, use `tierStartDates[versionNumber]` when present; otherwise count `monthsFromEndOfStandardSupport` from the lifecycle dataset's `STANDARD_SUPPORT_END` date.
- ElastiCache Extended Support applies to **Redis OSS** versions only (v4, v5, and v6 in the [ElastiCache docs](https://docs.aws.amazon.com/AmazonElastiCache/latest/dg/extended-support-versions.html); the Health Version Catalog also lists Redis OSS 7). **No Valkey or Memcached Extended Support rates are published** as of 2026-10-20. Valkey is the engine that deprecated Redis caches are upgraded *to*, and no Valkey version has an announced end of standard support. A `valkey` lifecycle entry therefore has no price here, which is correct: those versions are current, not in Extended Support. The monthly freshness check flags any non-Redis ElastiCache Extended Support rate that appears in the AWS Price List API.

CI runs `scripts/check_eol_join.py` against the current lifecycle dataset on every change and monthly. It fails if a `match` points at nothing, if a billed lifecycle entry has no price, if an entry matches more than one price, or if a tier start date falls outside the version's Extended Support window.

## Update Cadence

The dataset is updated monthly on a best-effort basis, sometimes more often (for example when AWS announces an Extended Support pricing change). Each month the maintainers run a check that compares every rate with the AWS Price List API, in both directions, and open a PR or an Issue for anything that changed. The scheduled workflow for this check is disabled for now, so it runs by hand. The top-level `lastUpdated` tells you when a rate last changed; the monthly check re-confirms every rate even when nothing changes, so an older `lastUpdated` means the rates are stable, not stale. Each entry also includes a `sourceUrl` pointing to the official AWS pricing page as a human-readable reference; if it and the Price List disagree, the Price List is authoritative (see [CONTRIBUTING.md](CONTRIBUTING.md)).

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

Common contributions:
- Adding new regions when AWS launches them
- Updating rates when AWS adjusts pricing
- Adding new services as they announce Extended Support pricing
- Reporting inaccuracies via GitHub Issues

**Every contribution must include a `sourceUrl` pointing to an official AWS pricing page.**

## Disclaimer

This dataset is provided as-is for informational purposes. Rates are sourced from the first-party AWS Price List and public AWS pricing pages, and may change as AWS updates them. This is a community-maintained republication rather than an official AWS product; each entry links its `sourceUrl` so you can confirm critical rates against the official AWS pricing pages before making financial decisions. These are public list prices and do not account for negotiated discounts, EDPs, or private pricing agreements.

## Using this data in automated workflows

If you integrate this data into cost projections, budget forecasting, chargeback, or upgrade prioritization, a few practices keep the numbers reliable:

- **Cross-reference `sourceUrl`** - each entry links to the official AWS pricing page it was taken from.
- **Account for your own pricing** - these are public on-demand Extended Support list prices; they do not include EDP discounts, private pricing agreements, or credits.
- **Pin to a tagged release** for production integrations, rather than tracking the main branch.
- **Check `lastUpdated`** and re-confirm against source URLs if the dataset has aged.

## License

This project is licensed under the Apache-2.0 License. See the [LICENSE](LICENSE) file for details.

## Security

See [SECURITY.md](SECURITY.md) for our security policy and vulnerability reporting process.
