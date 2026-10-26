#!/usr/bin/env python3
"""
Check data/pricing.json Extended Support rates against the live AWS Price List
Query API and report drift.

SAFE MODEL:
  * Each probe is fn(client, data) -> list of comparisons. A comparison is only
    emitted when the API value differs from the dataset.
  * comparison.confident == True  -> data/pricing.json is updated in place and
    the workflow opens a PR for review.
  * comparison.confident == False -> reported only; the workflow opens an Issue.
  * Nothing is ever merged automatically.
  * Each probe also records how many Price List rates it found per entry and
    tier. Zero found where the dataset has rates is an error (opens an Issue),
    so a stale filter cannot pass as "0 drift".
  * The reverse direction is checked too: a dataset rate the Price List API
    did not return (not yet published, withdrawn, or derived by hand) is
    listed for manual review. It is never deleted automatically.

Filters below were validated against the live API (see repo notes). Wrong
filters produce false drift, not silent corruption, and confident writes still
go through a human-reviewed PR.

Outputs (for the workflow):
  * freshness-report.md  (PR/Issue body)
  * has_changes / needs_review via $GITHUB_OUTPUT
"""

import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

import boto3
from jsonschema import validate, ValidationError

PRICING_REGION = "us-east-1"
DATA = Path("data/pricing.json")
SCHEMA = Path("data/schema.json")
REPORT = Path("freshness-report.md")
TOL = 1e-9

NOT_YET_AUTOMATED = "none (all covered services automated)"


# --------------------------------------------------------------------------- #
# helpers
# --------------------------------------------------------------------------- #
def _usd_ondemand(product):
    """Return (usd_float, unit_str) for the single on-demand price dimension."""
    try:
        terms = product["terms"]["OnDemand"]
        dim = next(iter(next(iter(terms.values()))["priceDimensions"].values()))
        return float(dim["pricePerUnit"]["USD"]), dim.get("unit", "")
    except (KeyError, StopIteration, ValueError, TypeError):
        return None, None


def paginate_products(client, service_code, filters):
    token = None
    while True:
        kw = dict(ServiceCode=service_code, Filters=filters,
                  FormatVersion="aws_v1", MaxResults=100)
        if token:
            kw["NextToken"] = token
        resp = client.get_products(**kw)
        for p in resp.get("PriceList", []):
            yield json.loads(p)
        token = resp.get("NextToken")
        if not token:
            break


MISSING_ENTRIES = []  # match keys a probe expected but data lacked
CHECKED = []          # (label, rates found in the Price List API, dataset expects rates)


def record_checked(label, found, expected=True):
    """Record how many Price List rates a probe found for one entry and tier.

    "0 drift" alone cannot tell "every rate matched" from "the query returned
    nothing" (for example after AWS renames a Price List attribute or value).
    main() reports found == 0 as an error when the dataset has rates for that
    entry and tier, and prints every count in the report."""
    CHECKED.append((label, found, expected))


def record_instance_rates(label, api, dataset_rates, tier_keys):
    """record_checked() for the nested instanceRates shape
    (region -> instanceKey -> {tier: rate}), once per tier."""
    for tk in tier_keys:
        found = sum(1 for inst in api.values() for tiers in inst.values() if tk in tiers)
        expected = any(tk in tiers for inst in dataset_rates.values()
                       if isinstance(inst, dict) for tiers in inst.values() if isinstance(tiers, dict))
        record_checked(f"{label}:{tk}", found, expected)


def dataset_only(service, entry, where, value):
    """A rate the dataset has but the Price List API did not return.

    Reverse direction of the drift check: drift compares what the API returns
    against the dataset, so a dataset rate with no API counterpart (not yet
    published, withdrawn, or derived by hand) would otherwise pass silently.
    Reported for manual review only. Never deleted or changed automatically."""
    return {"service": service, "label": where, "dataset_value": value,
            "api_value": "not returned", "entry": entry, "path": None,
            "confident": False, "kind": "dataset_only"}


def dataset_only_instance(service, entry, api, dataset_rates, tier_keys):
    """dataset_only() items for the nested instanceRates shape. Skips a tier
    the API returned nothing for: record_checked() already reports that as an
    error, and listing every rate again would only add noise."""
    out = []
    for tk in tier_keys:
        if not any(tk in tiers for inst in api.values() for tiers in inst.values()):
            continue
        for region, insts in sorted(dataset_rates.items()):
            if not isinstance(insts, dict):
                continue
            for inst, tiers in sorted(insts.items()):
                if isinstance(tiers, dict) and tk in tiers \
                        and api.get(region, {}).get(inst, {}).get(tk) is None:
                    out.append(dataset_only(service, entry, f"{region} {inst} {tk}", tiers[tk]))
    return out


def find_entries(data, service_code, engine=None, capacity_mode=None):
    """All pricing entries whose match block has this (serviceCode, engine)
    and, when given, this capacityMode. v2 can hold several entries per key
    (OpenSearch rate groups by versionNumbers; Aurora provisioned vs
    serverless-v2)."""
    hits = [s for s in data["services"]
            if s["match"]["serviceCode"] == service_code
            and s["match"].get("engine") == engine
            and (capacity_mode is None or s["match"].get("capacityMode") == capacity_mode)]
    if not hits:
        # A probe expected this entry. Record it so main() reports it as an
        # error (opens a review Issue) instead of the probe skipping silently.
        # This is what hid the Aurora probe after the aurora -> rds-aurora rename.
        MISSING_ENTRIES.append((service_code, engine, capacity_mode))
    return hits


def find_entry(data, service_code, engine=None, capacity_mode=None):
    hits = find_entries(data, service_code, engine, capacity_mode)
    return hits[0] if hits else None


def set_by_path(entry, path, value):
    cur = entry
    for k in path[:-1]:
        if isinstance(cur, dict):
            cur = cur.setdefault(k, {})
        else:  # list index
            cur = cur[k]
    cur[path[-1]] = value


# --------------------------------------------------------------------------- #
# probes
# --------------------------------------------------------------------------- #
def probe_eks(client, data):
    """EKS ES total cluster-hour = base control-plane rate + ES adder.
    Price List 'ExtendedSupport' SKU is the adder only (~0.50); dataset stores
    the TOTAL (~0.60) per the pricing page = base (~0.10) + adder.

    The dataset has one global rate, so every region is checked against it.
    A us-east-1 change is a confident update of that rate. Any other region
    whose total differs is reported for review: the Price List price is
    correct, but the entry has no per-region field to hold it, so the entry
    needs to move to regionalRates."""
    entry = find_entry(data, "eks")
    if not entry:
        return []

    def by_region(operation, exclude):
        out = {}  # regionCode -> set of rates
        for p in paginate_products(client, "AmazonEKS", [
            {"Type": "TERM_MATCH", "Field": "operation", "Value": operation},
        ]):
            attrs = p.get("product", {}).get("attributes", {})
            ut = attrs.get("usagetype", "")
            region = attrs.get("regionCode")
            if not region or any(x in ut for x in exclude):
                continue
            r, _ = _usd_ondemand(p)
            if r is not None:
                out.setdefault(region, set()).add(r)
        return out

    adders = by_region("ExtendedSupport", ("Outposts", "Local"))
    bases = by_region("CreateOperation", ("Outposts", "Local"))
    regions = sorted(set(adders) & set(bases))
    record_checked("eks:extended", len(regions))
    cur = entry["tiers"][0].get("rate")
    comps = []
    for region in regions:
        if len(adders[region]) > 1 or len(bases[region]) > 1:
            comps.append({"service": "eks", "label": f"{region} (conflicting Price List rates)",
                          "dataset_value": cur,
                          "api_value": {"adder": sorted(adders[region]), "base": sorted(bases[region])},
                          "entry": entry, "path": None, "confident": False})
            continue
        total = round(next(iter(bases[region])) + next(iter(adders[region])), 10)
        if cur is not None and abs(cur - total) <= TOL:
            continue
        if region == "us-east-1":
            comps.append({"service": "eks", "label": "ES cluster-hour total (base+adder, us-east-1)",
                          "dataset_value": cur, "api_value": total,
                          "entry": entry, "path": ["tiers", 0, "rate"], "confident": True})
        else:
            comps.append({"service": "eks",
                          "label": f"{region} ES cluster-hour total differs from the global rate "
                                   f"(switch the entry to regionalRates)",
                          "dataset_value": cur, "api_value": total,
                          "entry": entry, "path": None, "confident": False})
    return comps


# dataset match key -> which Price List rows price it.
# dbs: databaseEngine values to query. Provisioned rows are priced per vCPU and
#      filed under the engine's own databaseEngine.
# asv2: Serverless v2 (ACU) rows only, routed by the engine token in the
#      usagetype (e.g. "ExtendedSupport:Yr1-Yr2:ASv2:AuroraMySQL3" or
#      "ASv2-ExtendedSupport:Yr3:AuroraPostgreSQL13"). Serverless v2 rates are
#      engine-specific: the Price List files some under databaseEngine "Any"
#      and others under the engine's own value, so both are queried, and one
#      engine's rate must never be written into the other engine's entry.
RDS_MAP = [
    {"sc": "rds", "engine": "mysql", "mode": None, "dbs": ("MySQL",), "asv2": None},
    {"sc": "rds", "engine": "postgresql", "mode": None, "dbs": ("PostgreSQL",), "asv2": None},
    {"sc": "rds-aurora", "engine": "mysql", "mode": "provisioned",
     "dbs": ("Aurora MySQL",), "asv2": None},
    {"sc": "rds-aurora", "engine": "postgresql", "mode": "provisioned",
     "dbs": ("Aurora PostgreSQL",), "asv2": None},
    {"sc": "rds-aurora", "engine": "mysql", "mode": "serverless-v2",
     "dbs": ("Any", "Aurora MySQL"), "asv2": "AuroraMySQL"},
    {"sc": "rds-aurora", "engine": "postgresql", "mode": "serverless-v2",
     "dbs": ("Any", "Aurora PostgreSQL"), "asv2": "AuroraPostgreSQL"},
]
RDS_TIERS = {"year1_2": "Year 1, Year 2", "year3": "Year 3"}  # non-PP schedule


def _rds_row_matches(m, usagetype, unit):
    """Does one Price List row belong to the RDS_MAP entry m?

    Serverless v2 rows are identified by "ASv2" in the usagetype, not by the
    unit: at least one region (ap-southeast-7) labels an ASv2 SKU "vCPU-hour".
    Provisioned rows are vCPU-hour rows that are not ASv2."""
    is_asv2 = "ASv2" in usagetype
    if m["asv2"]:
        return is_asv2 and m["asv2"] in usagetype
    return not is_asv2 and "vcpu" in (unit or "").lower()


def probe_rds(client, data):
    """RDS/Aurora ES per-vCPU surcharge (+ Aurora Serverless v2 per-ACU).
    Filter by databaseEngine + extendedSupportPricingYear; region comes from
    regionCode in the response, so no region-name map is needed. Rows are
    assigned to entries by _rds_row_matches()."""
    comps = []
    rows = {}  # (databaseEngine, tier_key) -> [(region, rate, unit, usagetype)]

    def fetch(db, tier_key):
        if (db, tier_key) not in rows:
            out = []
            for p in paginate_products(client, "AmazonRDS", [
                {"Type": "TERM_MATCH", "Field": "databaseEngine", "Value": db},
                {"Type": "TERM_MATCH", "Field": "extendedSupportPricingYear",
                 "Value": RDS_TIERS[tier_key]},
            ]):
                attrs = p.get("product", {}).get("attributes", {})
                region = attrs.get("regionCode")
                rate, unit = _usd_ondemand(p)
                if region and rate is not None:
                    out.append((region, rate, unit, attrs.get("usagetype", "")))
            rows[(db, tier_key)] = out
        return rows[(db, tier_key)]

    for m in RDS_MAP:
        entry = find_entry(data, m["sc"], m["engine"], m["mode"])
        if not entry:
            continue
        label_svc = f"{m['sc']}/{m['engine']}" + (f"/{m['mode']}" if m["mode"] else "")
        api = {}  # region -> tier_key -> set of rates
        for tier_key in RDS_TIERS:
            for db in m["dbs"]:
                for region, rate, unit, usagetype in fetch(db, tier_key):
                    if _rds_row_matches(m, usagetype, unit):
                        api.setdefault(region, {}).setdefault(tier_key, set()).add(rate)
        rr = entry.setdefault("regionalRates", {})
        for tier_key in RDS_TIERS:
            found = sum(1 for tiers in api.values() if tier_key in tiers)
            expected = any(isinstance(v, dict) and tier_key in v for v in rr.values())
            record_checked(f"{label_svc}:{tier_key}", found, expected)
            if found:
                for region, v in sorted(rr.items()):
                    if isinstance(v, dict) and tier_key in v and tier_key not in api.get(region, {}):
                        comps.append(dataset_only(label_svc, entry, f"{region} {tier_key}", v[tier_key]))
        for region, tiers in sorted(api.items()):
            for tier_key, rates in sorted(tiers.items()):
                cur = rr.get(region, {}).get(tier_key)
                if len(rates) > 1:
                    # Several SKUs (engine versions) for one region and tier
                    # disagree. Never pick one silently.
                    comps.append({"service": label_svc,
                                  "label": f"{region} {tier_key} (conflicting Price List rates)",
                                  "dataset_value": cur, "api_value": sorted(rates),
                                  "entry": entry, "path": None, "confident": False})
                    continue
                rate = next(iter(rates))
                if cur is None or abs(cur - rate) > TOL:
                    comps.append({"service": label_svc,
                                  "label": f"{region} {tier_key}",
                                  "dataset_value": cur, "api_value": rate,
                                  "entry": entry,
                                  "path": ["regionalRates", region, tier_key],
                                  "confident": True})
    return comps


def _es_extended_usagetypes(client):
    """All AmazonES usagetype values for OpenSearch Extended Support
    (region-coded plus the bare us-east-1 form)."""
    vals, token = [], None
    while True:
        kw = dict(ServiceCode="AmazonES", AttributeName="usagetype", MaxResults=100)
        if token:
            kw["NextToken"] = token
        resp = client.get_attribute_values(**kw)
        for av in resp.get("AttributeValues", []):
            v = av.get("Value", "")
            if v.endswith("OpenSearchExtendedSupport"):
                vals.append(v)
        token = resp.get("NextToken")
        if not token:
            break
    return vals


def probe_opensearch(client, data):
    """OpenSearch/Elasticsearch ES: single flat per-NIH rate per region,
    engine-agnostic. usagetype is <REGION>-OpenSearchExtendedSupport (bare in
    us-east-1); no operation/productFamily isolates it, so enumerate the
    usagetypes and read regionCode from each response. The same per-NIH rate
    applies to every opensearch and elasticsearch entry (v2 splits each engine
    into rate groups by versionNumbers; legacy groups also carry an
    instance-price tier from Nov 7, 2026 that this probe does not touch)."""
    entries = (find_entries(data, "opensearch", "opensearch")
               + find_entries(data, "opensearch", "elasticsearch"))
    if not entries:
        return []
    api = {}  # regionCode -> rate
    for ut in _es_extended_usagetypes(client):
        for p in paginate_products(client, "AmazonES",
                                   [{"Type": "TERM_MATCH", "Field": "usagetype", "Value": ut}]):
            region = p.get("product", {}).get("attributes", {}).get("regionCode")
            if not region:
                continue
            rate, _ = _usd_ondemand(p)
            if rate is not None:
                api[region] = rate
    record_checked("opensearch:extended", len(api),
                   any(e.get("regionalRates") for e in entries))
    comps = []
    for entry in entries:
        rr = entry.setdefault("regionalRates", {})
        svc = (f"opensearch/{entry['match'].get('engine')}"
               f"/{(entry['match'].get('versionNumbers') or ['all'])[0]}+")
        if api:
            for region, cur in sorted(rr.items()):
                if isinstance(cur, (int, float)) and region not in api:
                    comps.append(dataset_only(svc, entry, region, cur))
        for region, rate in sorted(api.items()):
            cur = rr.get(region)
            if not isinstance(cur, (int, float)) or abs(cur - rate) > TOL:
                comps.append({"service": f"opensearch/{entry['match'].get('engine')}"
                                         f"/{(entry['match'].get('versionNumbers') or ['all'])[0]}+",
                              "label": region, "dataset_value": cur, "api_value": rate,
                              "entry": entry, "path": ["regionalRates", region],
                              "confident": True})
    return comps


def probe_docdb(client, data):
    """DocumentDB ES per-vCPU surcharge that VARIES BY INSTANCE FAMILY
    (r5 != t3). Filter databaseEngine + year_number (Y1 -> year1_2, Y3 ->
    year3); the family is the usagetype tail; regionCode from the response.
    Writes per-family into instanceRates[region][family][tier]."""
    entry = find_entry(data, "docdb", None)
    if not entry:
        return []
    yearmap = {"Y1": "year1_2", "Y3": "year3"}
    api = {}  # region -> family -> {tier: rate}
    for yr, tier_key in yearmap.items():
        for p in paginate_products(client, "AmazonDocDB", [
            {"Type": "TERM_MATCH", "Field": "year_number", "Value": yr},
        ]):
            attrs = p.get("product", {}).get("attributes", {})
            region = attrs.get("regionCode")
            ut = attrs.get("usagetype", "")
            fam = ut.split(":")[-1] if ":" in ut else None
            if not region or not fam:
                continue
            rate, _ = _usd_ondemand(p)
            if rate is not None:
                api.setdefault(region, {}).setdefault(fam, {})[tier_key] = rate
    ir = entry.setdefault("instanceRates", {})
    record_instance_rates("docdb", api, ir, yearmap.values())
    comps = dataset_only_instance("docdb", entry, api, ir, yearmap.values())
    for region, fams in sorted(api.items()):
        for fam, tiers in sorted(fams.items()):
            for tier_key, rate in tiers.items():
                cur = ir.get(region, {}).get(fam, {}).get(tier_key)
                if cur is None or abs(cur - rate) > TOL:
                    comps.append({"service": "docdb", "label": f"{region} {fam} {tier_key}",
                                  "dataset_value": cur, "api_value": rate, "entry": entry,
                                  "path": ["instanceRates", region, fam, tier_key],
                                  "confident": True})
    return comps


def probe_elasticache(client, data):
    """ElastiCache ES per-node-hour surcharge (Redis OSS), varies by node type.
    Filter year_number (Yr1_Yr2 -> year1_2, Yr3 -> year3); node type from
    instanceType; regionCode from response. Writes
    instanceRates[region][nodeType][tier].

    The query deliberately has NO cacheEngine filter, and the engine is split
    here instead. Redis rows are compared exactly as before. A row for any
    other engine (Valkey, Memcached, ...) is a newly published Extended Support
    rate the dataset does not model, so it is reported for manual review,
    which opens an Issue. This replaces keeping GitHub issue #6 open by hand.
    Filtering client-side also avoids guessing how the Price List API spells
    engines that have no Extended Support SKUs yet."""
    entry = find_entry(data, "elasticache", "redis")
    if not entry:
        return []
    yearmap = {"Yr1_Yr2": "year1_2", "Yr3": "year3"}
    api = {}    # region -> nodeType -> {tier: rate}
    other = {}  # non-Redis cacheEngine -> number of Extended Support SKUs seen
    for yr, tier_key in yearmap.items():
        for p in paginate_products(client, "AmazonElastiCache", [
            {"Type": "TERM_MATCH", "Field": "year_number", "Value": yr},
        ]):
            attrs = p.get("product", {}).get("attributes", {})
            engine = attrs.get("cacheEngine")
            if engine and engine != "Redis":
                other[engine] = other.get(engine, 0) + 1
                continue
            if engine != "Redis":
                continue  # no engine attribute: the old cacheEngine=Redis filter excluded these too
            region = attrs.get("regionCode")
            node = attrs.get("instanceType")
            if not region or not node:
                continue
            rate, _ = _usd_ondemand(p)
            if rate is not None:
                api.setdefault(region, {}).setdefault(node, {})[tier_key] = rate
    ir = entry.setdefault("instanceRates", {})
    record_instance_rates("elasticache/redis", api, ir, yearmap.values())
    comps = dataset_only_instance("elasticache/redis", entry, api, ir, yearmap.values())
    for region, nodes in sorted(api.items()):
        for node, tiers in sorted(nodes.items()):
            for tier_key, rate in tiers.items():
                cur = ir.get(region, {}).get(node, {}).get(tier_key)
                if cur is None or abs(cur - rate) > TOL:
                    comps.append({"service": "elasticache", "label": f"{region} {node} {tier_key}",
                                  "dataset_value": cur, "api_value": rate, "entry": entry,
                                  "path": ["instanceRates", region, node, tier_key],
                                  "confident": True})
    for engine, n in sorted(other.items()):
        comps.append({"service": "elasticache",
                      "label": f"new Extended Support engine '{engine}' (not modeled; add an entry)",
                      "dataset_value": "Redis OSS only",
                      "api_value": f"{n} Extended Support SKU(s)",
                      "entry": entry, "path": None, "confident": False})
    return comps


PROBES = [probe_eks, probe_rds, probe_opensearch, probe_docdb, probe_elasticache]


# --------------------------------------------------------------------------- #
def main():
    data = json.loads(DATA.read_text())
    client = boto3.client("pricing", region_name=PRICING_REGION)

    drifts, errors = [], []
    for probe in PROBES:
        try:
            drifts.extend(probe(client, data))
        except Exception as e:  # noqa: BLE001 - report, never crash the run
            errors.append(f"{probe.__name__}: {e}")
    for sc, eng, mode in MISSING_ENTRIES:
        errors.append(f"dataset has no entry for serviceCode={sc!r} engine={eng!r} capacityMode={mode!r}; "
                      f"probe skipped (renamed or removed entry?)")
    for label, found, expected in CHECKED:
        if expected and found == 0:
            errors.append(f"{label}: the Price List API returned 0 rates but the dataset has rates; "
                          f"the probe's filters may be stale (renamed attribute or value?)")

    changed = False
    for c in drifts:
        if c["confident"]:
            set_by_path(c["entry"], c["path"], c["api_value"])
            changed = True

    if changed:
        data["lastUpdated"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        try:
            validate(instance=data, schema=json.loads(SCHEMA.read_text()))
        except ValidationError as e:
            print(f"Schema validation FAILED after update: {e.message}", file=sys.stderr)
            sys.exit(2)
        DATA.write_text(json.dumps(data, indent=2) + "\n")

    auto = [c for c in drifts if c["confident"]]
    manual = [c for c in drifts if not c["confident"] and c.get("kind") != "dataset_only"]
    ds_only = [c for c in drifts if c.get("kind") == "dataset_only"]
    lines = ["# Pricing freshness check", ""]
    lines.append(f"- Confident drift (auto-written to a PR): {len(auto)}")
    lines.append(f"- Drift needing manual review: {len(manual)}")
    lines.append(f"- Dataset rates not returned by the Price List API (manual review): {len(ds_only)}")
    lines.append(f"- Probe errors: {len(errors)}")
    lines.append(f"- Not yet automated: {NOT_YET_AUTOMATED}")
    lines.append(f"- Rates checked: {sum(f for _, f, _ in CHECKED)} across {len(CHECKED)} entry/tier checks")
    lines.append("")
    if CHECKED:
        lines.append("## Rates checked per probe")
        for label, found, expected in CHECKED:
            flag = "" if found or not expected else "  <- 0 found, expected rates"
            lines.append(f"- {label}: {found}{flag}")
        lines.append("")
    for title, items in (("Auto-updated (in PR)", auto), ("Manual review", manual),
                         ("Dataset rates not returned by the Price List API", ds_only)):
        if items:
            lines.append(f"## {title}")
            for c in items[:200]:
                lines.append(f"- **{c['service']} {c['label']}**: dataset={c['dataset_value']} api={c['api_value']}")
            lines.append("")
    if errors:
        lines.append("## Probe errors")
        lines += [f"- {e}" for e in errors]
    REPORT.write_text("\n".join(lines))
    print("\n".join(lines))

    needs_review = bool(manual or ds_only or errors)
    gho = os.environ.get("GITHUB_OUTPUT")
    if gho:
        with open(gho, "a") as fh:
            fh.write(f"has_changes={'true' if changed else 'false'}\n")
            fh.write(f"needs_review={'true' if needs_review else 'false'}\n")


if __name__ == "__main__":
    main()
