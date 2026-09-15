# Security Policy

## Reporting a Vulnerability

If you discover a potential security issue in this project, we ask that you notify AWS Security via our [vulnerability reporting page](https://aws.amazon.com/security/vulnerability-reporting/). Please do **not** create a public GitHub issue for security vulnerabilities.

## Scope

This repository contains a static JSON dataset with no executable code. Security concerns for this project include:

- **Data integrity:** Incorrect pricing rates or tier escalation schedules that could cause consumers to produce flawed cost projections
- **Source authenticity:** Broken or manipulated `sourceUrl` references that undermine the verification model
- **Supply-chain trust:** Unauthorized modifications to the dataset that bypass the review process

## Security Controls

- All data changes require CODEOWNERS approval before merge
- CI validates JSON schema, pricing consistency, and sourceUrl patterns on every PR
- Every entry includes a `sourceUrl` pointing to an official AWS pricing page for independent verification
- The `lastUpdated` field signals dataset freshness

## Consumer Guidance

- For critical financial decisions (budget forecasting, cost projections, chargeback calculations), always verify rates against the `sourceUrl` provided in each entry
- Pin to tagged releases rather than tracking the main branch for production integrations
- This data does not account for negotiated discounts, EDPs, or private pricing agreements
