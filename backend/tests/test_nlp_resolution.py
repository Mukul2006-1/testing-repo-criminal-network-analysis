"""Phase 3 tests — NLP extraction, normalization, entity resolution,
extract/resolve API, and Phase 2 regression (stdlib unittest)."""

import json
import os
import sys
import tempfile
import unittest

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
REPO_ROOT = os.path.dirname(BACKEND_DIR)
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

from app.database.documents import DocumentStore  # noqa: E402
from app.services import entity_resolution as er  # noqa: E402
from app.services import nlp  # noqa: E402
from app.services import normalization as norm  # noqa: E402
from app.services.ingestion import IngestionService  # noqa: E402
from app.services.validation import IngestionError  # noqa: E402

try:
    from fastapi.testclient import TestClient

    from app.main import app as fastapi_app

    HAS_API = True
except Exception:
    HAS_API = False

MIXED_TEXT = ("Complainant Rahul Sharma reported a quarrel involving Amit Kumar "
              "near Shanti Nagar, Delhi on 2026-03-20. Contact +91 98765 43210. "
              "Vehicle DL 01 AB 1234 noted. Account ACC001 used. "
              "He joined Brightpath Solutions as a driver.")


def by_type(result, entity_type):
    return [e for e in result["entities"] if e["type"] == entity_type]


class NlpExtractionTests(unittest.TestCase):
    def test_contract_shape(self):
        result = nlp.extract_entities("Rahul Sharma called.", "FIR_001")
        self.assertEqual(result["document_id"], "FIR_001")
        self.assertIn("entities", result)
        self.assertEqual(result["relationships"], [])
        for entity in result["entities"]:
            for key in ("id", "type", "value", "confidence"):
                self.assertIn(key, entity)

    def test_person_extraction_strips_role_prefix(self):
        result = nlp.extract_entities(
            "Complainant Rahul Sharma reported a quarrel.", "FIR_001")
        persons = by_type(result, "PERSON")
        self.assertTrue(any(e["value"] == "Rahul Sharma" for e in persons))
        self.assertFalse(any("Complainant" in e["value"] for e in persons))

    def test_location_extraction(self):
        result = nlp.extract_entities(
            "The meeting took place near Shanti Nagar, Delhi.", "FIR_002")
        values = [e["value"] for e in by_type(result, "LOCATION")]
        self.assertIn("Delhi", values)

    def test_phone_extraction(self):
        result = nlp.extract_entities(
            "Call +91 98765 43210 immediately.", "CDR_001")
        phones = by_type(result, "PHONE")
        self.assertEqual(len(phones), 1)
        self.assertEqual(phones[0]["value"], "+919876543210")
        self.assertEqual(phones[0]["normalized_value"], "+919876543210")

    def test_vehicle_extraction(self):
        result = nlp.extract_entities(
            "Vehicle DL 01 AB 1234 was noted near the market.", "FIR_003")
        vehicles = by_type(result, "VEHICLE")
        self.assertEqual(len(vehicles), 1)
        self.assertEqual(vehicles[0]["value"], "DL01AB1234")

    def test_organization_extraction(self):
        result = nlp.extract_entities(
            "He joined Brightpath Solutions as a driver.", "FIR_004")
        orgs = by_type(result, "ORGANIZATION")
        self.assertTrue(any(e["value"] == "Brightpath Solutions"
                            for e in orgs))

    def test_date_extraction(self):
        result = nlp.extract_entities("Incident date 2026-03-20.", "FIR_005")
        dates = by_type(result, "DATE")
        self.assertTrue(any(e["value"] == "2026-03-20" for e in dates))

    def test_account_extraction(self):
        result = nlp.extract_entities(
            "Transfer from account ACC001 was flagged.", "TXN_001")
        accounts = by_type(result, "ACCOUNT")
        self.assertEqual(len(accounts), 1)
        self.assertEqual(accounts[0]["value"], "ACC001")

    def test_gazetteer_catches_alias_missed_by_ner(self):
        # "Amit Kumar" is mislabeled PRODUCT by the base model; the
        # caller-supplied gazetteer recovers it without inventing spans.
        plain = nlp.extract_entities("Amit Kumar attended.", "FIR_006")
        self.assertFalse(any(e["value"] == "Amit Kumar"
                             for e in plain["entities"]))
        gaz = nlp.extract_entities("Amit Kumar attended.", "FIR_006",
                                   known_names=["Amit Kumar"])
        found = [e for e in gaz["entities"] if e["value"] == "Amit Kumar"]
        self.assertEqual(len(found), 1)
        self.assertEqual(found[0]["method"], "gazetteer")

    def test_mixed_entity_types(self):
        result = nlp.extract_entities(MIXED_TEXT, "FIR_007",
                                      known_names=["Amit Kumar"])
        types = {e["type"] for e in result["entities"]}
        for expected in ("PERSON", "PHONE", "LOCATION", "VEHICLE",
                         "ORGANIZATION", "DATE", "ACCOUNT"):
            self.assertIn(expected, types)

    def test_empty_text(self):
        for text in ("", "   "):
            result = nlp.extract_entities(text, "FIR_008")
            self.assertEqual(result["entities"], [])
            self.assertEqual(result["relationships"], [])

    def test_malformed_input(self):
        with self.assertRaises(IngestionError):
            nlp.extract_entities(None, "FIR_009")
        with self.assertRaises(IngestionError):
            nlp.extract_entities("text", "")
        with self.assertRaises(IngestionError):
            nlp.extract_entities(12345, "FIR_009")

    def test_original_value_preserved(self):
        result = nlp.extract_entities("Call +91 98765 43210 now.", "CDR_002")
        phone = by_type(result, "PHONE")[0]
        self.assertEqual(phone["raw_text"], "+91 98765 43210")
        self.assertEqual(phone["value"], "+919876543210")


class NormalizationTests(unittest.TestCase):
    def test_names(self):
        self.assertEqual(norm.normalize_name("  Rahul   Sharma "), "Rahul Sharma")
        self.assertEqual(norm.normalized_name_key("R. Sharma"), "r. sharma")

    def test_phones(self):
        self.assertEqual(norm.normalize_phone("+91 98765 43210"), "+919876543210")
        with self.assertRaises(ValueError):
            norm.normalize_phone("123")

    def test_vehicles(self):
        self.assertEqual(norm.normalize_vehicle("DL 01 AB 1234"), "DL01AB1234")
        with self.assertRaises(ValueError):
            norm.normalize_vehicle("nope")

    def test_accounts(self):
        self.assertEqual(norm.normalize_account("acc 001"), "ACC001")
        self.assertEqual(norm.normalize_account("ACC-002"), "ACC002")
        with self.assertRaises(ValueError):
            norm.normalize_account("!!")


def fresh_store(tmpdir):
    return DocumentStore(os.path.join(tmpdir, "docs.db"))


def resolve(store, entity_type, value, normalized, document_id="FIR_001",
            confidence=0.9, method="test", doc_attrs=None, threshold=0.65):
    return er.resolve_one(store, entity_type, value, normalized, confidence,
                          method, document_id, doc_attrs, threshold)


class ResolutionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.store = fresh_store(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def test_exact_name_match(self):
        first = resolve(self.store, "PERSON", "Rahul Sharma", "rahul sharma")
        second = resolve(self.store, "PERSON", "Rahul  Sharma", "rahul sharma",
                         document_id="FIR_002")
        self.assertEqual(first["canonical_id"], second["canonical_id"])
        self.assertEqual(second["resolution_method"], ["exact_match"])
        self.assertTrue(second["canonical_id"].startswith("person_"))

    def test_phone_match(self):
        first = resolve(self.store, "PHONE", "+919876543210", "+919876543210")
        second = resolve(self.store, "PHONE", "+91 98765 43210",
                         "+919876543210", document_id="CDR_002")
        self.assertEqual(first["canonical_id"], second["canonical_id"])
        self.assertEqual(second["resolution_method"], ["phone_match"])

    def test_vehicle_match(self):
        first = resolve(self.store, "VEHICLE", "DL01AB1234", "DL01AB1234")
        second = resolve(self.store, "VEHICLE", "DL 01 AB 1234", "DL01AB1234",
                         document_id="FIR_002")
        self.assertEqual(first["canonical_id"], second["canonical_id"])
        self.assertEqual(second["resolution_method"], ["vehicle_match"])

    def test_account_match(self):
        first = resolve(self.store, "ACCOUNT", "ACC001", "ACC001")
        second = resolve(self.store, "ACCOUNT", "acc 001", "ACC001",
                         document_id="TXN_002")
        self.assertEqual(first["canonical_id"], second["canonical_id"])
        self.assertEqual(second["resolution_method"], ["account_match"])

    def test_fuzzy_name_with_shared_phone_merges(self):
        resolve(self.store, "PERSON", "Rahul Sharma", "rahul sharma",
                doc_attrs={"phones": ["+919876543210"]})
        merged = resolve(self.store, "PERSON", "R. Sharma", "r. sharma",
                         confidence=0.87, document_id="FIR_002",
                         doc_attrs={"phones": ["+919876543210"]})
        first_id = self.store.find_entities_by_normalized(
            "PERSON", "rahul sharma")[0]["id"]
        self.assertEqual(merged["canonical_id"], first_id)
        self.assertIn("name_similarity", merged["resolution_method"])
        self.assertIn("phone_match", merged["resolution_method"])
        values = [m["value"] for m in merged["matches"]]
        self.assertIn("Rahul Sharma", values)
        self.assertIn("R. Sharma", values)

    def test_similar_names_without_evidence_stay_split(self):
        for name, normed, doc in (("Rahul Sharma", "rahul sharma", "FIR_001"),
                                  ("Rahul Verma", "rahul verma", "FIR_002"),
                                  ("Rohit Sharma", "rohit sharma", "FIR_003")):
            resolve(self.store, "PERSON", name, normed, document_id=doc)
        ids = {e["id"] for e in self.store.list_entities_by_type("PERSON")}
        self.assertEqual(len(ids), 3)

    def test_alias_alone_does_not_merge(self):
        resolve(self.store, "PERSON", "Rahul Sharma", "rahul sharma")
        other = resolve(self.store, "PERSON", "R. Sharma", "r. sharma",
                        document_id="FIR_002")
        self.assertNotEqual(
            other["canonical_id"],
            self.store.find_entities_by_normalized(
                "PERSON", "rahul sharma")[0]["id"])
        self.assertEqual(other["resolution_method"], ["new_entity"])

    def test_no_match_creates_canonical(self):
        result = resolve(self.store, "LOCATION", "Shanti Nagar", "shanti nagar")
        self.assertEqual(result["resolution_method"], ["new_entity"])
        self.assertTrue(result["canonical_id"].startswith("location_"))
        self.assertIsNotNone(self.store.get_entity(result["canonical_id"]))

    def test_confidence_threshold_behavior(self):
        seed = {"doc_attrs": {"phones": ["+919876543210"]}}
        strict_store = fresh_store(tempfile.mkdtemp())
        resolve(strict_store, "PERSON", "Rahul Sharma", "rahul sharma",
                **seed)
        strict = resolve(strict_store, "PERSON", "Rahul S Sharma",
                         "rahul s sharma", document_id="FIR_002", **seed,
                         threshold=0.99)
        self.assertEqual(strict["resolution_method"], ["new_entity"])
        loose_store = fresh_store(tempfile.mkdtemp())
        resolve(loose_store, "PERSON", "Rahul Sharma", "rahul sharma",
                **seed)
        loose = resolve(loose_store, "PERSON", "Rahul S Sharma",
                        "rahul s sharma", document_id="FIR_003", **seed,
                        threshold=0.80)
        first_id = loose_store.find_entities_by_normalized(
            "PERSON", "rahul sharma")[0]["id"]
        self.assertEqual(loose["canonical_id"], first_id)

    def test_provenance_preserved(self):
        result = resolve(self.store, "PERSON", "R. Sharma", "r. sharma",
                         confidence=0.87, method="gazetteer",
                         document_id="FIR_007")
        mentions = self.store.list_mentions(result["canonical_id"])
        self.assertEqual(len(mentions), 1)
        self.assertEqual(mentions[0]["document_id"], "FIR_007")
        self.assertEqual(mentions[0]["text"], "R. Sharma")
        self.assertEqual(mentions[0]["extraction_method"], "gazetteer")

    def test_invalid_inputs_rejected(self):
        with self.assertRaises(IngestionError):
            resolve(self.store, "ALIEN", "X", "x")
        with self.assertRaises(IngestionError):
            resolve(self.store, "PERSON", "X", "x", confidence=7.0)
        with self.assertRaises(IngestionError):
            resolve(self.store, "PERSON", "", "")


class Phase2ToPhase3IntegrationTests(unittest.TestCase):
    """Phase 2 normalized output -> NLP -> resolution over real samples."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        raw = os.path.join(self.tmp.name, "raw")
        processed = os.path.join(self.tmp.name, "processed")
        self.store = fresh_store(self.tmp.name)
        self.svc = IngestionService(self.store, raw, processed)
        self.processed = processed

    def tearDown(self):
        self.tmp.cleanup()

    def _process_sample(self, filename, dtype):
        with open(os.path.join(REPO_ROOT, "data", "sample", filename),
                  "rb") as fh:
            doc = self.svc.upload(fh.read(), filename, dtype)
        result = self.svc.process(doc["id"])
        self.assertEqual(result["status"], "SUCCEEDED")
        with open(os.path.join(self.processed, doc["id"], "records.json"),
                  encoding="utf-8") as fh:
            records = json.load(fh)
        return doc["id"], records

    def test_fir_sample_end_to_end(self):
        upload_id, records = self._process_sample("fir.csv", "FIR")
        self.assertGreater(len(records), 20)
        all_entities = []
        for record in records[:5]:
            out = nlp.extract_entities(record["normalized"]["text"],
                                       record["source_id"])
            self.assertEqual(out["relationships"], [])
            all_entities.extend(out["entities"])
        types = {e["type"] for e in all_entities}
        self.assertIn("PERSON", types)
        self.assertIn("LOCATION", types)
        resolved = er.resolve_document(self.store, upload_id, all_entities)
        self.assertEqual(len(resolved["resolved"]), len(all_entities))
        canonical_ids = [r["canonical_id"] for r in resolved["resolved"]]
        self.assertTrue(all(cid for cid in canonical_ids))
        # Exact re-resolution reuses canonical IDs (no duplicates).
        again = er.resolve_document(self.store, upload_id, all_entities)
        self.assertEqual([r["canonical_id"] for r in again["resolved"]],
                         canonical_ids)

    def test_cdr_sample_structured_phones(self):
        upload_id, records = self._process_sample("cdr.csv", "CDR")
        first = records[0]
        phone = nlp.structured_entity("PHONE", first["normalized"]["caller"],
                                      source_field="caller")
        result = er.resolve_one(
            self.store, phone["type"], phone["value"],
            phone["normalized_value"], phone["confidence"], phone["method"],
            upload_id)
        self.assertTrue(result["canonical_id"].startswith("phone_"))
        self.assertEqual(result["resolution_method"], ["new_entity"])


@unittest.skipUnless(HAS_API, "fastapi/httpx not installed")
class EntitiesApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        from tests.helpers import configure_test_env, make_authed_client

        configure_test_env(self.tmp.name)
        from app.api import deps as deps_mod

        deps_mod.reset_service()
        self.client = make_authed_client(fastapi_app)

    def tearDown(self):
        from tests.helpers import clear_test_env

        clear_test_env()
        from app.api import deps as deps_mod

        deps_mod.reset_service()
        self.tmp.cleanup()

    def _upload_and_process(self, filename="fir.csv", dtype="FIR"):
        with open(os.path.join(REPO_ROOT, "data", "sample", filename),
                  "rb") as fh:
            content = fh.read()
        upload = self.client.post(
            "/api/upload", files={"file": (filename, content, "text/csv")},
            data={"dataset_type": dtype}).json()["data"]
        proc = self.client.post("/api/process",
                                json={"upload_id": upload["upload_id"]})
        self.assertEqual(proc.status_code, 200)
        return upload["upload_id"]

    def test_extract_by_upload_id(self):
        upload_id = self._upload_and_process()
        resp = self.client.post("/api/entities/extract",
                                json={"upload_id": upload_id})
        self.assertEqual(resp.status_code, 200, resp.text)
        data = resp.json()["data"]
        self.assertEqual(data["document_id"], upload_id)
        self.assertEqual(data["relationships"], [])
        self.assertGreater(len(data["entities"]), 10)
        entity = data["entities"][0]
        for key in ("id", "type", "value", "confidence"):
            self.assertIn(key, entity)

    def test_extract_by_text(self):
        resp = self.client.post(
            "/api/entities/extract",
            json={"text": "Rahul Sharma visited Delhi on 2026-01-05.",
                  "document_id": "ADHOC_1"})
        self.assertEqual(resp.status_code, 200, resp.text)
        types = {e["type"] for e in resp.json()["data"]["entities"]}
        self.assertIn("PERSON", types)
        self.assertIn("LOCATION", types)

    def test_extract_unknown_upload(self):
        resp = self.client.post("/api/entities/extract",
                                json={"upload_id": "upl_nope"})
        self.assertEqual(resp.status_code, 404)

    def test_extract_unprocessed_upload(self):
        with open(os.path.join(REPO_ROOT, "data", "sample", "fir.csv"),
                  "rb") as fh:
            upload = self.client.post(
                "/api/upload",
                files={"file": ("fir.csv", fh.read(), "text/csv")},
                data={"dataset_type": "FIR"}).json()["data"]
        resp = self.client.post("/api/entities/extract",
                                json={"upload_id": upload["upload_id"]})
        self.assertEqual(resp.status_code, 422)

    def test_resolve_merges_and_persists(self):
        first = self.client.post("/api/entities/resolve", json={
            "document_id": "FIR_001",
            "entities": [{"id": "temp_001", "type": "PERSON",
                          "value": "Rahul Sharma", "confidence": 0.9,
                          "normalized_value": "rahul sharma",
                          "method": "test"}],
            "doc_attrs": {"phones": ["+919876543210"]}}).json()["data"]
        second = self.client.post("/api/entities/resolve", json={
            "document_id": "FIR_002",
            "entities": [{"id": "temp_001", "type": "PERSON",
                          "value": "R. Sharma", "confidence": 0.87,
                          "normalized_value": "r. sharma",
                          "method": "test"}],
            "doc_attrs": {"phones": ["+919876543210"]}}).json()["data"]
        self.assertEqual(first["resolved"][0]["canonical_id"],
                         second["resolved"][0]["canonical_id"])
        self.assertIn("phone_match",
                      second["resolved"][0]["resolution_method"])

    def test_resolve_rejects_bad_body(self):
        resp = self.client.post("/api/entities/resolve", json={
            "document_id": "FIR_001",
            "entities": [{"id": "temp_001", "type": "PERSON",
                          "value": "X", "confidence": 9.0}]})
        self.assertEqual(resp.status_code, 422)


if __name__ == "__main__":
    unittest.main()
