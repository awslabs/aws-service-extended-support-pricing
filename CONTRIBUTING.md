# Contributing to AWS Service Extended Support Pricing

Thank you for your interest in contributing! This project relies on community contributions to keep pricing data accurate and up-to-date.

## Where rates come from

The **AWS Price List API** is the authoritative source for every rate in this dataset. A
monthly CI job (`scripts/check_pricing_freshness.py`) compares `data/pricing.json` with
the Price List in both directions: rates that changed, and dataset rates the Price List
does not return. It opens a PR for changes it is sure of and an Issue for anything that
needs a person.

Each entry's `sourceUrl` points to the matching AWS pricing page. Use it as the
human-readable reference, but note that **the pricing page can lag the Price List**,
especially for newly launched regions. If the two disagree, the Price List wins.

To check one rate yourself (any AWS account can call the Price List API; it is served
from `us-east-1`):

```bash
aws pricing get-products --region us-east-1 --service-code AmazonRDS \
  --filters '[{"Type":"TERM_MATCH","Field":"databaseEngine","Value":"Any"},
              {"Type":"TERM_MATCH","Field":"extendedSupportPricingYear","Value":"Year 1, Year 2"},
              {"Type":"TERM_MATCH","Field":"regionCode","Value":"ap-east-2"}]'
```

This example looks up Aurora Serverless v2 (Year 1-2) in ap-east-2. The exact service
code and filters for every entry are in the probe functions of
`scripts/check_pricing_freshness.py`.

## How to Contribute

### Reporting Inaccuracies

If you find a rate that looks wrong:

1. Open a GitHub Issue with:
   - The service, region, and tier affected
   - The dataset value and the value you found
   - Where you found it: the Price List API (preferred: include the filters you used) or
     the AWS pricing page (include the link)

A difference between the dataset and the pricing page alone is still worth reporting,
but we will not remove a rate the Price List API confirms. A rate that neither the Price
List nor the pricing page shows is a real problem, so please report it.

### Adding or Updating Data

1. Fork the repository
2. Make your changes to `data/pricing.json`
3. Ensure your changes follow the schema (see README.md)
4. Submit a Pull Request

### Contribution Requirements

Every data entry **must** include:

- `sourceUrl`: A link to an official AWS pricing page for the service's Extended Support rates. The URL must point to the **specific service pricing page section** relevant to Extended Support (not just a service landing page). For example, use `https://aws.amazon.com/rds/mysql/pricing/` rather than `https://aws.amazon.com/rds/`.
- Correct `pricingUnit` matching the service's billing model
- Regional rates verified against the AWS Price List API, or against the pricing page when the Price List does not publish that rate. Say which one you used in the PR.

### What We Accept

- New regional rates when AWS launches new regions
- Rate corrections when AWS adjusts Extended Support pricing
- New services as they announce Extended Support pricing models
- New pricing tiers when services introduce tier changes

### What We Do Not Accept

- Speculative pricing without official AWS documentation
- Negotiated, EDP, or private pricing rates
- Customer-specific cost calculations or resource counts
- Lifecycle dates (those belong in aws-service-eol-data)

## Validation

Before submitting, verify that:

1. Your JSON is valid (`python -m json.tool data/pricing.json`)
2. All `sourceUrl` fields point to live, official AWS pricing pages
3. Regional rates match the AWS Price List API (or the pricing page, where the Price List does not publish the rate)
4. Examples calculate correctly using the stated formula

## Code of Conduct

This project has adopted the [Amazon Open Source Code of Conduct](https://aws.github.io/code-of-conduct). For more information, see the [Code of Conduct FAQ](https://aws.github.io/code-of-conduct-faq) or contact opensource-codeofconduct@amazon.com with any additional questions or comments.

## Security

If you discover a potential security issue in this project, please notify AWS Security via our [vulnerability reporting page](http://aws.amazon.com/security/vulnerability-reporting/). Please do **not** create a public GitHub issue.

## Licensing

See the [LICENSE](LICENSE) file for this project's licensing. When you submit a pull request, your contributions are understood to be under the same Apache-2.0 License that covers the project.
