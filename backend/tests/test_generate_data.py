"""Phase 1 tests — synthetic data generator (stdlib unittest only).

Covers: files/columns exist, unique IDs, valid cross-source references,
deterministic output for a fixed seed, non-empty required fields, and
synthetic markings. No third-party deps.
"""

import csv
import importlib.util
import json
import os
import tempfile
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(
    os.path.abspath(__file__))))
GENERATOR_PATH = os.path.join(REPO_ROOT, "scripts", "generate_data.py")
SAMPLE_DIR = os.path.join(REPO_ROOT, "data", "sample")

EXPECTED_COLUMNS = {
    "entities": ["person_id", "canonical_name", "aliases", "phone",
                 "account", "vehicle", "organization", "group",
                 "test_pattern"],
    "fir": ["fir_id", "date", "police_station", "text", "source"],
    "cdr": ["cdr_id", "caller", "receiver", "timestamp", "duration"],
    "transactions": ["transaction_id", "sender_account", "receiver_account",
                     "amount", "currency", "timestamp"],
    "vehicles": ["vehicle_id", "registration_number", "owner_name", "source"],
    "locations": ["location_id", "name", "latitude", "longitude"],
}

# Required non-empty in every row (optional fields like police_station /
# coordinates are excluded on purpose).
REQUIRED = {
    "entities": ["person_id", "canonical_name", "phone", "group"],
    "fir": ["fir_id", "date", "text", "source"],
    "cdr": ["cdr_id", "caller", "receiver", "timestamp", "duration"],
    "transactions": ["transaction_id", "sender_account", "receiver_account",
                     "amount", "currency", "timestamp"],
    "vehicles": ["vehicle_id", "registration_number", "owner_name",
                 "source"],
    "locations": ["location_id", "name"],
}


def load_generator():
    spec = importlib.util.spec_from_file_location("generate_data",
                                                  GENERATOR_PATH)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def read_csv(path):
    with open(path, newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


class TestSyntheticData(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.gen = load_generator()
        cls.tables = {}
        for name in EXPECTED_COLUMNS:
            cls.tables[name] = read_csv(os.path.join(SAMPLE_DIR, f"{name}.csv"))

    def test_expected_files_exist(self):
        for name in EXPECTED_COLUMNS:
            self.assertTrue(
                os.path.isfile(os.path.join(SAMPLE_DIR, f"{name}.csv")),
                f"missing {name}.csv")
        self.assertTrue(os.path.isfile(os.path.join(SAMPLE_DIR,
                                                    "manifest.json")))

    def test_expected_columns_exist(self):
        for name, columns in EXPECTED_COLUMNS.items():
            with open(os.path.join(SAMPLE_DIR, f"{name}.csv"),
                      newline="", encoding="utf-8") as fh:
                self.assertEqual(csv.DictReader(fh).fieldnames, columns,
                                 f"column mismatch in {name}.csv")

    def test_ids_unique(self):
        id_col = {"entities": "person_id", "fir": "fir_id", "cdr": "cdr_id",
                  "transactions": "transaction_id", "vehicles": "vehicle_id",
                  "locations": "location_id"}
        for name, col in id_col.items():
            ids = [r[col] for r in self.tables[name]]
            self.assertEqual(len(set(ids)), len(ids),
                             f"duplicate ids in {name}")

    def test_no_empty_required_fields(self):
        for name, cols in REQUIRED.items():
            for row in self.tables[name]:
                for col in cols:
                    self.assertTrue(row[col] and row[col].strip(),
                                    f"empty {name}.{col} in {row}")

    def test_cross_source_references_valid(self):
        phones, accounts, names = set(), set(), set()
        for e in self.tables["entities"]:
            phones.update(e["phone"].split("|"))
            names.add(e["canonical_name"])
            names.update(a for a in e["aliases"].split("|") if a)
            accounts.update(a for a in e["account"].split("|") if a)
        for c in self.tables["cdr"]:
            self.assertIn(c["caller"], phones)
            self.assertIn(c["receiver"], phones)
            self.assertNotEqual(c["caller"], c["receiver"])
        for x in self.tables["transactions"]:
            self.assertIn(x["sender_account"], accounts)
            self.assertIn(x["receiver_account"], accounts)
            self.assertNotEqual(x["sender_account"], x["receiver_account"])
            self.assertGreater(int(x["amount"]), 0)
        for v in self.tables["vehicles"]:
            self.assertIn(v["owner_name"], names)

    def test_deterministic_with_same_seed(self):
        with tempfile.TemporaryDirectory() as d1, \
                tempfile.TemporaryDirectory() as d2:
            for d in (d1, d2):
                tables = self.gen.generate(seed=42)
                self.gen.validate(tables)
                self.gen.write_tables(tables, d, seed=42)
            for name in EXPECTED_COLUMNS:
                with open(os.path.join(d1, f"{name}.csv"), "rb") as f1, \
                        open(os.path.join(d2, f"{name}.csv"), "rb") as f2:
                    self.assertEqual(f1.read(), f2.read(),
                                     f"non-deterministic {name}.csv")

    def test_synthetic_markings(self):
        with open(os.path.join(SAMPLE_DIR, "manifest.json"),
                  encoding="utf-8") as fh:
            manifest = json.load(fh)
        self.assertTrue(manifest["synthetic"])
        for row in self.tables["fir"]:
            self.assertIn("[SYNTHETIC RECORD]", row["text"])
        for row in self.tables["vehicles"]:
            self.assertEqual(row["source"], "SYNTHETIC")

    def test_graph_patterns_present(self):
        # central entity has the most FIR-adjacent presence; anomaly entity
        # has strictly more calls than a median entity.
        phones_of = {e["person_id"]: e["phone"].split("|")
                     for e in self.tables["entities"]}
        call_count: dict[str, int] = {pid: 0 for pid in phones_of}
        for c in self.tables["cdr"]:
            for pid, nums in phones_of.items():
                if c["caller"] in nums or c["receiver"] in nums:
                    call_count[pid] += 1
        self.assertGreater(call_count["person_001"], 10)
        self.assertGreater(call_count["person_003"],
                           sorted(call_count.values())[len(call_count) // 2])
        big = [x for x in self.tables["transactions"]
               if int(x["amount"]) >= 500000]
        self.assertGreaterEqual(len(big), 5)

    def test_alias_variation_exists(self):
        with_alias = [e for e in self.tables["entities"] if e["aliases"]]
        self.assertGreaterEqual(len(with_alias), 5)
        owners = {v["owner_name"] for v in self.tables["vehicles"]}
        canonical = {e["canonical_name"] for e in self.tables["entities"]}
        self.assertTrue(owners - canonical,
                        "expected some alias owner names in vehicles.csv")


if __name__ == "__main__":
    unittest.main()
