"""Unit tests for probe_eks in scripts/check_pricing_freshness.py.

Run from the repository root:

    python -m unittest discover -s tests

No AWS access is needed: a fake Price List client serves products shaped like
GetProducts output, and boto3 is stubbed because probe_eks never calls it.
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


def sku(region, operation, usd, usagetype="AmazonEKS-Hours:perCluster", currency="USD"):
    """One AmazonEKS product, as GetProducts returns it (a JSON string)."""
    return {
        "operation": operation,
        "json": json.dumps({
            "product": {"attributes": {"regionCode": region, "operation": operation,
                                       "usagetype": usagetype}},
            "terms": {"OnDemand": {"T": {"priceDimensions": {
                "D": {"unit": "Hours", "pricePerUnit": {currency: str(usd)}}}}}},
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


def dataset(rate=0.6):
    return {"services": [{"match": {"serviceCode": "eks", "engine": None},
                          "tiers": [{"id": "extended", "rate": rate}]}]}


def region_skus(region, base=0.1, adder=0.5):
    return [sku(region, "CreateOperation", base),
            sku(region, "ExtendedSupport", adder, usagetype="AmazonEKS-Hours:extendedSupport")]


def run(skus, data):
    cpf.CHECKED.clear()
    cpf.MISSING_ENTRIES.clear()
    return cpf.probe_eks(FakePricing(skus), data)


class ProbeEks(unittest.TestCase):

    def test_every_region_matching_the_global_rate_is_quiet(self):
        skus = region_skus("us-east-1") + region_skus("eu-west-1") + region_skus("ap-southeast-2")
        self.assertEqual(run(skus, dataset()), [])
        self.assertEqual(cpf.CHECKED, [("eks:extended", 3, True)])

    def test_us_east_1_change_updates_the_global_rate(self):
        skus = region_skus("us-east-1", adder=0.6) + region_skus("eu-west-1", adder=0.6)
        comps = run(skus, dataset())
        us = [c for c in comps if c["confident"]]
        self.assertEqual(len(us), 1)
        self.assertEqual((us[0]["path"], us[0]["dataset_value"], us[0]["api_value"]),
                         (["tiers", 0, "rate"], 0.6, 0.7))

    def test_other_region_that_differs_is_reported_not_written(self):
        skus = region_skus("us-east-1") + region_skus("sa-east-1", adder=0.55)
        data = dataset()
        [c] = run(skus, data)
        self.assertFalse(c["confident"])
        self.assertIsNone(c["path"])
        self.assertTrue(c["label"].startswith("sa-east-1"))
        self.assertEqual(c["api_value"], 0.65)
        self.assertEqual(data["services"][0]["tiers"][0]["rate"], 0.6)

    def test_outposts_local_and_non_usd_rows_are_ignored(self):
        skus = region_skus("us-east-1") + [
            sku("us-east-1", "ExtendedSupport", 9.9, usagetype="Outposts-EKS-Hours:extendedSupport"),
            sku("us-east-1", "CreateOperation", 9.9, usagetype="Local-EKS-Hours:perCluster"),
        ] + region_skus("cn-north-1", base=0.64, adder=3.2)
        for s in skus[-2:]:
            s["json"] = s["json"].replace('"USD"', '"CNY"')
        self.assertEqual(run(skus, dataset()), [])
        self.assertEqual(cpf.CHECKED, [("eks:extended", 1, True)])

    def test_region_with_conflicting_rates_is_reported(self):
        skus = region_skus("us-east-1") + [sku("us-east-1", "CreateOperation", 0.2)]
        [c] = run(skus, dataset())
        self.assertFalse(c["confident"])
        self.assertIn("conflicting", c["label"])

    def test_region_missing_base_or_adder_is_not_counted(self):
        skus = region_skus("us-east-1") + [sku("eu-west-1", "ExtendedSupport", 0.5)]
        self.assertEqual(run(skus, dataset()), [])
        self.assertEqual(cpf.CHECKED, [("eks:extended", 1, True)])


if __name__ == "__main__":
    unittest.main()
