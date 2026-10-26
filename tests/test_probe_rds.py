"""Unit tests for probe_rds in scripts/check_pricing_freshness.py.

Run from the repository root:

    python -m unittest discover -s tests

No AWS access is needed: a fake Price List client serves products shaped like
GetProducts output, and boto3 is stubbed because probe_rds never calls it.
"""

import importlib.util
import json
import sys
import types
import unittest
from pathlib import Path

sys.modules.setdefault("boto3", types.ModuleType("boto3"))

_SCRIPT = Path(__file__).resolve().parent.parent / "scripts" / "check_pricing_freshness.py"
_spec = importlib.util.spec_from_file_location("check_pricing_freshness", _SCRIPT)
cpf = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cpf)


def sku(region, engine, year, usagetype, unit, usd):
    """One Price List product, as GetProducts returns it (a JSON string)."""
    return {
        "databaseEngine": engine,
        "extendedSupportPricingYear": year,
        "json": json.dumps({
            "product": {"attributes": {
                "regionCode": region, "usagetype": usagetype,
                "databaseEngine": engine, "extendedSupportPricingYear": year}},
            "terms": {"OnDemand": {"T": {"priceDimensions": {
                "D": {"unit": unit, "pricePerUnit": {"USD": str(usd)}}}}}},
        }),
    }


class FakePricing:
    """Answers get_products with the SKUs whose TERM_MATCH filters all match."""

    def __init__(self, skus):
        self.skus = skus

    def get_products(self, ServiceCode, Filters, **_):
        want = {f["Field"]: f["Value"] for f in Filters}
        return {"PriceList": [s["json"] for s in self.skus
                              if all(s.get(k) == v for k, v in want.items())]}


def dataset(**rates):
    """pricing.json with the six RDS/Aurora entries probe_rds expects.
    Keyword names: rds_mysql, rds_postgresql, aurora_mysql, aurora_postgresql,
    sv2_mysql, sv2_postgresql. Each value is a regionalRates dict."""
    keys = {
        "rds_mysql": ("rds", "mysql", None),
        "rds_postgresql": ("rds", "postgresql", None),
        "aurora_mysql": ("rds-aurora", "mysql", "provisioned"),
        "aurora_postgresql": ("rds-aurora", "postgresql", "provisioned"),
        "sv2_mysql": ("rds-aurora", "mysql", "serverless-v2"),
        "sv2_postgresql": ("rds-aurora", "postgresql", "serverless-v2"),
    }
    services = []
    for name, (sc, engine, mode) in keys.items():
        match = {"serviceCode": sc, "engine": engine}
        if mode:
            match["capacityMode"] = mode
        services.append({"match": match, "regionalRates": json.loads(json.dumps(rates.get(name, {})))})
    return {"services": services}


def run(skus, data):
    cpf.CHECKED.clear()
    cpf.MISSING_ENTRIES.clear()
    return cpf.probe_rds(FakePricing(skus), data)


def by(comps, service, label):
    return [c for c in comps if c["service"] == service and c["label"] == label]


SV2_MYSQL = "rds-aurora/mysql/serverless-v2"
SV2_PG = "rds-aurora/postgresql/serverless-v2"
Y12, Y3 = "Year 1, Year 2", "Year 3"


class ProbeRdsServerlessV2(unittest.TestCase):

    def test_rates_are_routed_by_engine_in_usagetype(self):
        # MySQL is filed under "Any", PostgreSQL under its own databaseEngine
        # with unit "ACU-Hr" (as in ap-southeast-6). Each entry must get its
        # own engine's rate, not the other's.
        skus = [
            sku("ap-southeast-6", "Any", Y12, "APS8-ExtendedSupport:Yr1-Yr2:ASv2:AuroraMySQL3", "ACU-hour", 0.107),
            sku("ap-southeast-6", "Aurora PostgreSQL", Y12,
                "APS8-ASv2-ExtendedSupport:Yr1-Yr2:AuroraPostgreSQL13", "ACU-Hr", 0.102),
        ]
        data = dataset(sv2_mysql={"ap-southeast-6": {"year1_2": 0.107}},
                       sv2_postgresql={"ap-southeast-6": {"year1_2": 0.107}})
        comps = run(skus, data)
        self.assertEqual(by(comps, SV2_MYSQL, "ap-southeast-6 year1_2"), [])
        [pg] = by(comps, SV2_PG, "ap-southeast-6 year1_2")
        self.assertTrue(pg["confident"])
        self.assertEqual((pg["dataset_value"], pg["api_value"]), (0.107, 0.102))

    def test_mysql_does_not_inherit_postgresql_year3(self):
        # The only "Any" Year 3 ACU SKU in us-east-1 is PostgreSQL's. The MySQL
        # entry must not count it as a MySQL Year 3 rate.
        skus = [
            sku("us-east-1", "Any", Y12, "ExtendedSupport:Yr1-Yr2:ASv2:AuroraMySQL3", "ACU-hour", 0.085),
            sku("us-east-1", "Any", Y12, "ExtendedSupport:Yr1-Yr2:ASv2:AuroraPostgreSQL13", "ACU-hour", 0.085),
            sku("us-east-1", "Any", Y3, "ExtendedSupport:Yr3:ASv2:AuroraPostgreSQL13", "ACU-hour", 0.17),
        ]
        data = dataset(sv2_mysql={"us-east-1": {"year1_2": 0.085, "year3": 0.17}},
                       sv2_postgresql={"us-east-1": {"year1_2": 0.085, "year3": 0.17}})
        comps = run(skus, data)
        self.assertEqual(comps, [])
        checked = {label: (found, expected) for label, found, expected in cpf.CHECKED}
        # 0 MySQL Year 3 rates found while the dataset has some: main() reports
        # this as an error, so the rate goes to human review.
        self.assertEqual(checked[f"{SV2_MYSQL}:year3"], (0, True))
        self.assertEqual(checked[f"{SV2_PG}:year3"], (1, True))

    def test_mysql_year3_without_a_price_list_rate_is_listed_for_review(self):
        # When MySQL Year 3 exists in some region (mx-central-1 today), each
        # dataset MySQL Year 3 rate without a Price List counterpart is listed.
        skus = [
            sku("mx-central-1", "Any", Y3, "MXC1-ExtendedSupport:Yr3:ASv2:AuroraMySQL3", "ACU-hour", 0.179),
            sku("us-east-1", "Any", Y3, "ExtendedSupport:Yr3:ASv2:AuroraPostgreSQL13", "ACU-hour", 0.17),
        ]
        data = dataset(sv2_mysql={"mx-central-1": {"year3": 0.179}, "us-east-1": {"year3": 0.17}},
                       sv2_postgresql={"us-east-1": {"year3": 0.17}})
        comps = run(skus, data)
        [mysql_y3] = by(comps, SV2_MYSQL, "us-east-1 year3")
        self.assertEqual(mysql_y3.get("kind"), "dataset_only")
        self.assertFalse(mysql_y3["confident"])
        self.assertEqual(len(comps), 1)

    def test_asv2_sku_with_vcpu_unit_is_serverless(self):
        # ap-southeast-7 labels its MySQL Serverless v2 SKU "vCPU-hour". It is
        # still a Serverless v2 rate and must not land in the provisioned entry.
        skus = [
            sku("ap-southeast-7", "Any", Y12, "APS9-ExtendedSupport:Yr1-Yr2:ASv2:AuroraMySQL3", "vCPU-hour", 0.092),
            sku("ap-southeast-7", "Aurora MySQL", Y12, "APS9-ExtendedSupport:Yr1-Yr2:AuroraMySQL3", "vCPU-hour", 0.108),
        ]
        data = dataset(aurora_mysql={"ap-southeast-7": {"year1_2": 0.108}})
        comps = run(skus, data)
        [new] = by(comps, SV2_MYSQL, "ap-southeast-7 year1_2")
        self.assertTrue(new["confident"])
        self.assertEqual((new["dataset_value"], new["api_value"]), (None, 0.092))
        self.assertEqual(by(comps, "rds-aurora/mysql/provisioned", "ap-southeast-7 year1_2"), [])

    def test_provisioned_ignores_serverless_rows_under_its_engine(self):
        # "Aurora PostgreSQL" also returns ASv2 rows (unit "ACU-Hr"). The
        # provisioned entry keeps only its per-vCPU rate.
        skus = [
            sku("us-east-1", "Aurora PostgreSQL", Y12, "ExtendedSupport:Yr1-Yr2:AuroraPostgreSQL13", "vCPU-hour", 0.1),
            sku("us-east-1", "Aurora PostgreSQL", Y12, "ASv2-ExtendedSupport:Yr1-Yr2:AuroraPostgreSQL13", "ACU-Hr", 0.085),
        ]
        data = dataset(aurora_postgresql={"us-east-1": {"year1_2": 0.1}},
                       sv2_postgresql={"us-east-1": {"year1_2": 0.085}})
        self.assertEqual(run(skus, data), [])

    def test_conflicting_rates_are_reported_not_written(self):
        skus = [
            sku("eu-west-1", "Any", Y12, "EU-ExtendedSupport:Yr1-Yr2:ASv2:AuroraPostgreSQL13", "ACU-hour", 0.095),
            sku("eu-west-1", "Any", Y12, "EU-ExtendedSupport:Yr1-Yr2:ASv2:AuroraPostgreSQL14", "ACU-hour", 0.099),
        ]
        data = dataset(sv2_postgresql={"eu-west-1": {"year1_2": 0.095}})
        [c] = run(skus, data)
        self.assertFalse(c["confident"])
        self.assertIsNone(c["path"])
        self.assertEqual(c["api_value"], [0.095, 0.099])
        self.assertEqual(data["services"][5]["regionalRates"]["eu-west-1"]["year1_2"], 0.095)


if __name__ == "__main__":
    unittest.main()
