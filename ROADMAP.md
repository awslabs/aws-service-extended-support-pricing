# Roadmap

Planned and under-consideration work. This is directional, not a commitment to dates
or scope. Feedback and requests are welcome via GitHub Issues and Discussions.

The dataset is updated monthly on a best-effort basis, sometimes more often. The AWS
Price List API is the authoritative source for every rate.

## Planned

- **OpenSearch legacy-version rate from the Price List API** - the surcharge that
  starts Nov 7, 2026 for legacy Elasticsearch and OpenSearch versions currently comes
  from the AWS announcement. Once the Price List API publishes it, the dataset
  switches to those values and the monthly freshness check covers it.
- **Cost estimate with your pricing** - a script that reads your inventory (service,
  engine, version, region, and quantity in each entry's rate unit) and both
  datasets, and outputs the monthly Extended Support cost per resource and pricing
  tier, with the date each tier starts. It shows list and net cost side by side:
  - **AWS Enterprise Discount Program (EDP) and private pricing** - apply your own
    negotiated discount, per service, to the public list rates. Whether a given
    agreement discounts Extended Support charges depends on that agreement, so you
    set it per service; the tool never assumes.
  - **Rates from your Cost and Usage Report (CUR)** - a ready-made Amazon Athena
    query (for CUR 2.0 and legacy CUR) that returns your effective Extended Support
    rate and discount per service, engine, and region, and feeds them into the
    estimate. It runs in your account and the results stay with you.
  Negotiated rates and billing data are customer-specific and are never shipped in
  the dataset.

## Ongoing

- **New regions and instance or node types** - the monthly freshness check compares
  the dataset with the Price List API and opens a pull request when a published rate
  is missing.
- **New services** - when the lifecycle dataset adds a version that is billed in
  Extended Support and this dataset has no rate for it, the join check fails, and the
  rate is added from the Price List API.

## Under consideration

- A `valkey` or `memcached` entry if and when AWS publishes an ElastiCache Extended
  Support rate for that engine (none exists today; Valkey is currently the upgrade
  target away from Extended Support, not subject to it). The monthly freshness check
  flags the first such rate in the AWS Price List API.

## Companion dataset

- Lifecycle dates are provided by
  [aws-service-eol-data](https://github.com/awslabs/aws-service-eol-data). Each pricing
  entry's `match` block names the lifecycle entries it prices (`serviceCode`, `engine`,
  and optionally `versionNumbers` and `capacityMode`).
