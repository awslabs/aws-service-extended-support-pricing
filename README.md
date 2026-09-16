# AWS Service Extended Support Pricing

> **NOT AN OFFICIAL AWS API.** This is a community-maintained dataset provided on a best-effort basis. It is not an official AWS product, service, or commitment. Always verify rates against the official AWS pricing pages linked in each entry's `sourceUrl` field before making financial decisions. This data does not account for negotiated discounts, EDPs, or private pricing agreements.

A machine-readable dataset of AWS Extended Support pricing models, enabling programmatic cost calculation for resources past end of standard support.

## Why This Exists

When AWS services enter Extended Support, additional charges apply. Each service uses a different pricing model (per vCPU-hour, per cluster-hour, per normalized instance hour), with rates that vary by region and escalate over time. Customers and tooling currently have no single programmatic source for these pricing formulas, forcing manual lookups across individual service pricing pages.

This repository provides consolidated, structured pricing data that enables automated cost projection for Extended Support charges across all applicable AWS services.

## Data Format

### File Location

```
data/pricing.json
```

### Schema

```json
{
  "schemaVersion": "1.0",
  "lastUpdated": "2026-06-10",
  "services": [
    {
      "serviceCode": "eks",
      "serviceName": "Amazon EKS",
      "engine": null,
      "pricingUnit": "cluster-hour",
      "formula": "rate x clusters x hours",
      "tiers": [
        { "label": "Extended Support", "monthsFromEndOfStandardSupport": [0, 12], "rate": 0.60 }
      ],
      "sourceUrl": "https://aws.amazon.com/eks/pricing/"
    }
  ]
}
```

### Field Reference

| Field | Type | Description |
|-------|------|-------------|
| `serviceCode` | string | AWS service identifier |
| `serviceName` | string | Human-readable service name |
| `engine` | string or null | Database engine for multi-engine services |
| `pricingUnit` | string | Unit of charge (cluster-hour, vCPU-hour, node-hour, normalized-instance-hour) |
| `formula` | string | Human-readable cost calculation formula |
| `tiers` | array | Pricing tiers with time ranges and rates |
| `tiers[].label` | string | Tier name (e.g., "Year 1-2", "Year 3") |
| `tiers[].monthsFromEndOfStandardSupport` | array | [start, end] months after standard support ends |
| `tiers[].rate` | number | Fixed rate per unit (for non-regional pricing) |
| `tiers[].rateByRegion` | boolean | If true, use `regionalRates` for per-region pricing |
| `tiers[].multiplier` | number | Multiplier applied to base rate for this tier |
| `regionalRates` | object | Per-region rates (when pricing varies by region) |
| `instanceRates` | object | Per-instance rates nested as `region -> instanceKey -> {year1_2, year3}`. Used where the rate varies by instance: DocumentDB is keyed by instance family (e.g. `r5`, `t3`), ElastiCache by node type (e.g. `cache.r6g.large`). |
| `normalizationFactors` | object | Instance size to normalization factor mapping (OpenSearch) |
| `resourceInputs` | array | What inputs are needed to calculate cost for this service |
| `resourceInputs[].field` | string | The variable name used in the formula |
| `resourceInputs[].source` | string | Where to get this value (e.g., instanceClass, clusterCount) |
| `resourceInputs[].description` | string | Human-readable explanation |
| `instanceClassMapping` | object | Maps DB instance class to vCPU count (RDS/Aurora). Enables cost calculation without a separate API call. |
| `versionsRef` | string | Link to companion EOL dates repository |
| `examples` | array | Worked cost calculation examples |
| `sourceUrl` | string | Official AWS pricing page URL |

### Pricing Models by Service

| Service | Unit | Tiers | Regional |
|---------|------|-------|----------|
| Amazon EKS | cluster-hour | Single tier: $0.60 | No |
| Amazon RDS (MySQL/PostgreSQL) | vCPU-hour | Year 1-2, Year 3 (2x) | Yes |
| Amazon Aurora (MySQL/PostgreSQL) | vCPU-hour | Year 1-2, Year 3 (2x) | Yes |
| Amazon ElastiCache (Redis) | node-hour | Year 1-2, Year 3 (2x) | Yes (per node type) |
| Amazon OpenSearch Service | NIH | Single tier | Yes |
| Amazon DocumentDB | vCPU-hour | Year 1-2, Year 3 (2x) | Yes (per instance family) |
| Amazon Aurora Serverless v2 | ACU-hour | Year 1-2, Year 3 (2x) | Yes |

**Note on what each rate represents:** the EKS rate is the *total* cluster-hour cost during Extended Support (base control plane plus the Extended Support adder). Every other service lists the Extended Support *surcharge* only, applied on top of normal instance or capacity cost. RDS, Aurora, and Aurora Serverless v2 are per vCPU-hour (per ACU-hour for Serverless v2) and vary by region. DocumentDB is per vCPU-hour and varies by region and instance family (e.g. `r5` differs from `t3`) - see `instanceRates`. ElastiCache (Redis) is per node-hour and varies by region and node type - see `instanceRates`.

## Usage Examples

### Calculate monthly EKS Extended Support cost

```python
import json

with open('data/pricing.json') as f:
    data = json.load(f)

eks = next(s for s in data['services'] if s['serviceCode'] == 'eks')
clusters = 106
hours_per_month = 730
rate = eks['tiers'][0]['rate']

monthly_cost = rate * clusters * hours_per_month
print(f"EKS Extended Support: ${monthly_cost:,.2f}/month for {clusters} clusters")
# Output: EKS Extended Support: $46,428.00/month for 106 clusters
```

### Calculate RDS Extended Support cost by region

```python
rds_mysql = next(s for s in data['services'] if s['serviceCode'] == 'rds' and s['engine'] == 'mysql')
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
ec = next(s for s in data['services'] if s['serviceCode'] == 'elasticache')
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

## Update Cadence

This dataset is updated when AWS announces pricing changes for Extended Support. Pricing changes are less frequent than lifecycle date announcements. Each entry includes a `sourceUrl` pointing to the official AWS pricing page for verification.

## Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

Common contributions:
- Adding new regions when AWS launches them
- Updating rates when AWS adjusts pricing
- Adding new services as they announce Extended Support pricing
- Reporting inaccuracies via GitHub Issues

**Every contribution must include a `sourceUrl` pointing to an official AWS pricing page.**

## Disclaimer

This dataset is provided as-is for informational purposes on a best-effort basis. Pricing data is sourced from public AWS pricing pages and may change without notice. This project is community-maintained and there is no guarantee of completeness, accuracy, or timeliness of updates. Always verify critical pricing against the official AWS pricing pages linked in each entry's `sourceUrl` field before making financial decisions. This data does not account for negotiated discounts, EDPs, or private pricing agreements.

## Important: Validation for Critical Decisions

If you are using this data for automated decisions (cost projections, budget forecasting, chargeback calculations, or upgrade prioritization), you SHOULD:

1. **Validate rates against `sourceUrl`** - each entry links to the official AWS pricing page. Cross-reference before acting on the data.
2. **Account for pricing model differences** - this dataset reflects public on-demand Extended Support pricing only. It does not include EDP discounts, private pricing agreements, or credits.
3. **Pin to a tagged release** - for production integrations, pin to a specific release rather than tracking the main branch.
4. **Check `lastUpdated`** - if the dataset is more than 60 days old, re-verify rates against source URLs before acting.

## License

This project is licensed under the Apache-2.0 License. See the [LICENSE](LICENSE) file for details.

## Security

See [SECURITY.md](SECURITY.md) for our security policy and vulnerability reporting process.
