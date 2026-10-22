#!/usr/bin/env python3
"""
Cross-dataset check: does every aws-service-eol-data entry that is billed for
Extended Support find exactly one price in data/pricing.json?

Standard library only. Loads eol.json from --eol (local path) or downloads it
from the aws-service-eol-data repository (--eol-ref, default "main").

Errors (exit 1):
  * a pricing match points at no eol entry
  * a match.versionNumbers value is not an eol versionNumber for that key
  * an eol entry with a CHARGES_APPLY behavior and an EXTENDED_SUPPORT_END
    event has no price (checked per Aurora capacity mode)
  * an eol entry matches more than one price
  * a tierStartDates entry names an unknown tier, a version not in eol, or a
    date outside [standard support end, extended support end)

Warnings (printed, exit 0):
  * an eol entry has a CHARGES_APPLY behavior but no EXTENDED_SUPPORT_END
    event. This usually means the eol support model is too broad for that
    engine (for example RDS for MariaDB, which has no Extended Support).

Usage:
  python scripts/check_eol_join.py                       # eol from GitHub main
  python scripts/check_eol_join.py --eol ../aws-service-eol-data/data/eol.json
"""

import argparse
import json
import sys
import urllib.request
from pathlib import Path

PRICING = Path("data/pricing.json")
EOL_URL = "https://raw.githubusercontent.com/awslabs/aws-service-eol-data/{ref}/data/eol.json"
AURORA_MODES = ("provisioned", "serverless-v2")


# ----------------------------- join logic (reference) -----------------------
def matches(match, entry, capacity_mode=None):
    """True if a pricing `match` block prices this eol entry.

    serviceCode and engine compare exactly (None == None is a match here,
    unlike SQL). versionNumbers and capacityMode only narrow the match when
    present on the pricing side."""
    if match["serviceCode"] != entry.get("serviceCode"):
        return False
    if match["engine"] != entry.get("engine"):
        return False
    versions = match.get("versionNumbers")
    if versions is not None and entry.get("versionNumber") not in versions:
        return False
    mode = match.get("capacityMode")
    if mode is not None and mode != capacity_mode:
        return False
    return True


def find_prices(pricing, entry, capacity_mode=None):
    """All pricing entries for one eol entry. Exactly one is expected."""
    if capacity_mode is None and entry.get("serviceCode") == "rds-aurora":
        capacity_mode = "provisioned"
    return [s for s in pricing["services"] if matches(s["match"], entry, capacity_mode)]


# --------------------------------- helpers ----------------------------------
def event_date(entry, event_type):
    for ev in entry.get("lifecycleEvents", []):
        if ev.get("lifecycleEventType") == event_type and ev.get("date"):
            return ev["date"]
    return None


def charges_apply(entry):
    for ev in entry.get("lifecycleEvents", []):
        b = ev.get("behavior")
        if not b:
            continue
        outcomes = [b.get("outcome"), b.get("default")] + list((b.get("branches") or {}).values())
        if "CHARGES_APPLY" in outcomes:
            return True
    return False


def modes_for(entry):
    return AURORA_MODES if entry.get("serviceCode") == "rds-aurora" else (None,)


def key(entry_or_match, version=None, mode=None):
    parts = [str(entry_or_match.get("serviceCode")), str(entry_or_match.get("engine"))]
    if version is not None:
        parts.append(str(version))
    if mode is not None:
        parts.append(mode)
    return "|".join(parts)


def load_eol(path, ref):
    if path:
        return json.loads(Path(path).read_text())
    url = EOL_URL.format(ref=ref)
    with urllib.request.urlopen(url, timeout=30) as resp:  # noqa: S310 - fixed https URL
        return json.loads(resp.read().decode("utf-8"))


# ---------------------------------- checks ----------------------------------
def run_checks(pricing, eol):
    entries = eol["entries"]
    services = pricing["services"]
    errors, warnings = [], []

    for s in services:
        m = s["match"]
        if not any(matches(m, e, m.get("capacityMode")) for e in entries):
            errors.append(f"match {json.dumps(m)} prices no eol entry")
        for v in m.get("versionNumbers") or []:
            if not any(e.get("serviceCode") == m["serviceCode"] and e.get("engine") == m["engine"]
                       and e.get("versionNumber") == v for e in entries):
                errors.append(f"match versionNumbers: {key(m, v)} is not in eol")

    priced = 0
    for e in entries:
        for mode in modes_for(e):
            hits = [s for s in services if matches(s["match"], e, mode)]
            if len(hits) > 1:
                errors.append(f"{key(e, e.get('versionNumber'), mode)} matches {len(hits)} prices")
            elif len(hits) == 1:
                priced += 1
            elif charges_apply(e) and event_date(e, "EXTENDED_SUPPORT_END"):
                errors.append(f"{key(e, e.get('versionNumber'), mode)} is billed (CHARGES_APPLY) but has no price")
        if charges_apply(e) and not event_date(e, "EXTENDED_SUPPORT_END"):
            warnings.append(f"{key(e, e.get('versionNumber'))} has CHARGES_APPLY but no EXTENDED_SUPPORT_END "
                            f"event (eol support model may be too broad for this engine)")

    for s in services:
        m = s["match"]
        tier_ids = {t["id"] for t in s["tiers"]}
        for v, tiers in (s.get("tierStartDates") or {}).items():
            e = next((x for x in entries if x.get("serviceCode") == m["serviceCode"]
                      and x.get("engine") == m["engine"] and x.get("versionNumber") == v), None)
            if e is None:
                errors.append(f"tierStartDates: {key(m, v)} is not in eol")
                continue
            se = event_date(e, "STANDARD_SUPPORT_END")
            ee = event_date(e, "EXTENDED_SUPPORT_END")
            for tid, d in tiers.items():
                if tid not in tier_ids:
                    errors.append(f"tierStartDates: {key(m, v)} names unknown tier '{tid}'")
                elif d is None:
                    continue
                elif se and d < se:
                    errors.append(f"tierStartDates: {key(m, v)} {tid}={d} is before standard support end {se}")
                elif ee and d >= ee:
                    errors.append(f"tierStartDates: {key(m, v)} {tid}={d} is on or after extended support end {ee}")

    return errors, warnings, priced


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[1])
    ap.add_argument("--eol", help="local path to aws-service-eol-data data/eol.json")
    ap.add_argument("--eol-ref", default="main", help="git ref to download when --eol is not given")
    args = ap.parse_args(argv)

    pricing = json.loads(PRICING.read_text())
    eol = load_eol(args.eol, args.eol_ref)
    errors, warnings, priced = run_checks(pricing, eol)

    for w in warnings:
        print("warning:", w)
    if errors:
        print(f"eol join check FAILED with {len(errors)} error(s):")
        for e in errors:
            print("  -", e)
        return 1
    print(f"eol join check PASSED: {priced} eol entry/capacity-mode pairs priced, "
          f"{len(warnings)} warning(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
