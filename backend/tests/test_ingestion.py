"""Phase 2 tests — ingestion & preprocessing (stdlib unittest).

Service tests import only stdlib code. API tests use FastAPI TestClient and
are skipped when web dependencies are unavailable. Every test uses isolated
temporary directories: repo data/ is never touched.
"""

import csv
import io
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
from app.services import ingestion as ing_mod  # noqa: E402
from app.services import normalization as norm  # noqa: E402
from app.services import validation as val  # noqa: E402
from app.services.ingestion import IngestionService  # noqa: E402
from app.services.parser import parse  # noqa: E402
from app.services.validation import IngestionError  # noqa: E402

try:
    from fastapi.testclient import TestClient

    from app.main import app as fastapi_app

    HAS_API = True
except Exception:  # fastapi/httpx absent -> API tests skip, services still run
    HAS_API = False

CDR_CSV = ("cdr_id,caller,receiver,timestamp,duration\n"
           "CDR_001,+919876543210,+919876543211,2026-08-12T10:32:00Z,420\n"
           "CDR_002,+919876543211,+919876543212,2026-08-12,60\n")
FIR_JSON = json.dumps([{"fir_id": "FIR_001", "date": "2026-03-20",
                        "police_station": "Shanti Nagar Police Station",
                        "text": "Synthetic narrative.", "source": "SYNTHETIC"}])
FIR_TXT = "First synthetic line.\n\nSecond synthetic line.\n"


def make_service(tmpdir):
    raw = os.path.join(tmpdir, "raw")
    processed = os.path.join(tmpdir, "processed")
    store = DocumentStore(os.path.join(tmpdir, "docs.db"))
    return IngestionService(store, raw, processed), raw, processed, store


def read_json(path):
    with open(path, encoding="utf-8") as fh:
        return json.load(fh)


class ServiceIngestionTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.svc, self.raw, self.processed, self.store = make_service(
            self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def upload_bytes(self, content: bytes, name="cdr.csv", dtype="CDR"):
        return self.svc.upload(content, name, dtype)

    # -- valid inputs ----------------------------------------------------
    def test_valid_csv_ingestion(self):
        doc = self.upload_bytes(CDR_CSV.encode())
        result = self.svc.process(doc["id"])
        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertEqual(result["valid_count"], 2)
        self.assertEqual(self.store.get_document(doc["id"])["status"],
                         "PROCESSED")

    def test_valid_json_ingestion(self):
        doc = self.upload_bytes(FIR_JSON.encode(), "fir.json", "FIR")
        result = self.svc.process(doc["id"])
        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertEqual(result["valid_count"], 1)

    def test_valid_txt_ingestion(self):
        doc = self.upload_bytes(FIR_TXT.encode(), "note.txt", "FIR")
        result = self.svc.process(doc["id"])
        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertEqual(result["valid_count"], 2)
        out = read_json(os.path.join(self.processed, doc["id"], "records.json"))
        self.assertTrue(out[0]["source_id"].endswith("#L1"))

    # -- malformed inputs --------------------------------------------------
    def test_malformed_json(self):
        doc = self.upload_bytes(b'{"records": [', "bad.json", "FIR")
        result = self.svc.process(doc["id"])
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["errors"][0]["code"], "INVALID_JSON")
        self.assertEqual(self.store.get_document(doc["id"])["status"], "FAILED")

    def test_malformed_csv(self):
        doc = self.upload_bytes(b"no-header-no-newline", "bad.csv", "CDR")
        result = self.svc.process(doc["id"])
        self.assertEqual(result["status"], "FAILED")
        self.assertIn(result["errors"][0]["code"],
                      ("INVALID_CSV", "INVALID_RECORD_STRUCTURE"))

    def test_unsupported_file_type(self):
        with self.assertRaises(IngestionError) as ctx:
            self.upload_bytes(b"data", "evil.exe", "CDR")
        self.assertEqual(ctx.exception.code, "UNSUPPORTED_FILE_TYPE")
        self.assertEqual(ctx.exception.http_status, 422)

    def test_oversized_file(self):
        old = val.MAX_FILE_SIZE_BYTES
        val.MAX_FILE_SIZE_BYTES = 10
        try:
            with self.assertRaises(IngestionError) as ctx:
                self.upload_bytes(b"0" * 11, "big.csv", "CDR")
            self.assertEqual(ctx.exception.code, "FILE_TOO_LARGE")
            self.assertEqual(ctx.exception.http_status, 413)
        finally:
            val.MAX_FILE_SIZE_BYTES = old

    def test_missing_required_fields(self):
        bad = b"cdr_id,caller,receiver,timestamp,duration\nCDR_001,,,,,\n"
        doc = self.upload_bytes(bad, "missing.csv", "CDR")
        result = self.svc.process(doc["id"])
        self.assertEqual(result["status"], "FAILED")
        codes = {e.get("code") for e in result["errors"]}
        self.assertIn("MISSING_REQUIRED_FIELD", codes)

    def test_invalid_timestamps(self):
        bad = (b"cdr_id,caller,receiver,timestamp,duration\n"
               b"CDR_001,+919876543210,+919876543211,not-a-date,60\n")
        doc = self.upload_bytes(bad, "ts.csv", "CDR")
        result = self.svc.process(doc["id"])
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["errors"][0]["code"], "INVALID_TIMESTAMP")

    def test_invalid_numeric_values(self):
        bad = (b"transaction_id,sender_account,receiver_account,amount,"
               b"currency,timestamp\n"
               b"TXN001,ACC001,ACC002,-500,INR,2026-08-12T10:00:00Z\n")
        doc = self.upload_bytes(bad, "txn.csv", "TRANSACTION")
        result = self.svc.process(doc["id"])
        self.assertEqual(result["status"], "FAILED")
        self.assertEqual(result["errors"][0]["code"], "INVALID_NUMERIC_VALUE")

    def test_partial_success_reports_invalid_records(self):
        mixed = (b"cdr_id,caller,receiver,timestamp,duration\n"
                 b"CDR_001,+919876543210,+919876543211,2026-08-12T10:00:00Z,60\n"
                 b"CDR_002,bad-phone,+919876543211,2026-08-12T10:00:00Z,60\n")
        doc = self.upload_bytes(mixed, "mixed.csv", "CDR")
        result = self.svc.process(doc["id"])
        self.assertEqual(result["status"], "PARTIAL")
        self.assertEqual(result["valid_count"], 1)
        self.assertEqual(result["invalid_count"], 1)
        self.assertEqual(len(result["errors"]), 1)

    def test_duplicate_ingestion_rejected(self):
        doc = self.upload_bytes(CDR_CSV.encode(), "a.csv", "CDR")
        with self.assertRaises(IngestionError) as ctx:
            self.upload_bytes(CDR_CSV.encode(), "b.csv", "CDR")
        self.assertEqual(ctx.exception.code, "DUPLICATE_UPLOAD")
        self.assertEqual(ctx.exception.http_status, 409)
        self.assertEqual(ctx.exception.details[0]["upload_id"], doc["id"])

    def test_process_unknown_upload(self):
        with self.assertRaises(IngestionError) as ctx:
            self.svc.process("upl_missing")
        self.assertEqual(ctx.exception.code, "UPLOAD_NOT_FOUND")
        self.assertEqual(ctx.exception.http_status, 404)

    # -- normalization ------------------------------------------------------
    def test_phone_normalization(self):
        for raw, expected in [
                ("+91 98765 43210", "+919876543210"),
                ("+91-98765-43210", "+919876543210"),
                ("919876543210", "+919876543210"),
                ("9876543210", "+919876543210")]:
            self.assertEqual(norm.normalize_phone(raw), expected)
        with self.assertRaises(ValueError):
            norm.normalize_phone("12345")

    def test_name_normalization(self):
        self.assertEqual(norm.normalize_name("  Rahul   Sharma "), "Rahul Sharma")
        self.assertEqual(norm.normalized_name_key(" Rahul Sharma "), "rahul sharma")

    def test_vehicle_normalization(self):
        self.assertEqual(norm.normalize_vehicle("DL 01 AB 1234"), "DL01AB1234")
        self.assertEqual(norm.normalize_vehicle("dl-01-ab-1234"), "DL01AB1234")
        with self.assertRaises(ValueError):
            norm.normalize_vehicle("NOT A PLATE")

    def test_timestamp_normalization(self):
        self.assertEqual(norm.normalize_timestamp("2026-08-12"),
                         "2026-08-12T00:00:00Z")
        self.assertEqual(norm.normalize_timestamp("2026-08-12 10:32:00"),
                         "2026-08-12T10:32:00Z")
        self.assertEqual(norm.normalize_timestamp("2026-08-12T10:32:00+05:30"),
                         "2026-08-12T05:02:00Z")
        with self.assertRaises(ValueError):
            norm.normalize_timestamp("yesterday-ish")

    # -- provenance & storage -------------------------------------------------
    def test_provenance_preservation(self):
        doc = self.upload_bytes(CDR_CSV.encode(), "cdr_batch.csv", "CDR")
        self.svc.process(doc["id"])
        out = read_json(os.path.join(self.processed, doc["id"], "records.json"))
        rec = out[0]
        self.assertEqual(rec["source_id"], "CDR_001")
        self.assertEqual(rec["source_type"], "CDR")
        self.assertEqual(rec["upload_id"], doc["id"])
        self.assertEqual(rec["original"]["caller"], "+919876543210")
        self.assertEqual(rec["provenance"]["source_file"], "cdr_batch.csv")
        self.assertEqual(rec["provenance"]["dataset_type"], "CDR")
        self.assertIn("ingested_at", rec["provenance"])

    def test_raw_file_preserved(self):
        content = CDR_CSV.encode()
        doc = self.upload_bytes(content, "orig.csv", "CDR")
        self.svc.process(doc["id"])
        stored = doc["metadata"]["storage"]
        with open(os.path.join(self.raw, "CDR", stored), "rb") as fh:
            self.assertEqual(fh.read(), content)

    def test_processed_output_separate_from_raw(self):
        doc = self.upload_bytes(CDR_CSV.encode(), "x.csv", "CDR")
        self.svc.process(doc["id"])
        processed_file = os.path.join(self.processed, doc["id"], "records.json")
        self.assertTrue(os.path.isfile(processed_file))
        raw_files = [os.path.join(r, f) for r, _, fs in os.walk(self.raw)
                     for f in fs]
        self.assertEqual(len(raw_files), 1)
        self.assertNotIn(os.path.realpath(processed_file),
                         [os.path.realpath(p) for p in raw_files])

    # -- security -------------------------------------------------------------
    def test_path_traversal_filename_rejected(self):
        for evil in ["../../etc/passwd", "..\\..\\win.ini", "/abs/path.csv",
                     "a/b.csv"]:
            with self.assertRaises(IngestionError) as ctx:
                self.upload_bytes(b"x", evil, "CDR")
            self.assertEqual(ctx.exception.code, "INVALID_FILE_NAME", evil)

    def test_storage_name_not_derived_from_filename(self):
        doc = self.upload_bytes(CDR_CSV.encode(), "my_private_laptop.csv", "CDR")
        stored = doc["metadata"]["storage"]
        self.assertNotIn("my_private_laptop", stored)
        self.assertNotIn("laptop", stored)

    def test_unexpected_dataset_type(self):
        with self.assertRaises(IngestionError) as ctx:
            self.upload_bytes(b"x", "f.csv", "CRIMINAL_SCORE")
        self.assertEqual(ctx.exception.http_status, 422)

    def test_non_utf8_encoding_rejected(self):
        with self.assertRaises(IngestionError) as ctx:
            parse(b"\xff\xfe\x00bad", ".csv")
        self.assertEqual(ctx.exception.code, "INVALID_ENCODING")


@unittest.skipUnless(HAS_API, "fastapi/httpx not installed")
class UploadProcessApiTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        from tests.helpers import configure_test_env, make_authed_client

        configure_test_env(self.tmp.name)
        from app.api import deps as deps_mod

        deps_mod.reset_service()
        self.client = make_authed_client(fastapi_app)
        self.dirs = (os.environ["RAW_DATA_DIR"],
                     os.environ["PROCESSED_DATA_DIR"])

    def tearDown(self):
        from tests.helpers import clear_test_env

        clear_test_env()
        from app.api import deps as deps_mod

        deps_mod.reset_service()
        self.tmp.cleanup()

    def assert_no_paths(self, body: bytes):
        text = body.decode()
        for secret in self.dirs + (os.environ.get("DOCUMENT_DB_PATH", ""),):
            self.assertNotIn(secret, text)
        self.assertNotIn(".db", text)

    def test_upload_endpoint(self):
        resp = self.client.post(
            "/api/upload", files={"file": ("cdr.csv", CDR_CSV, "text/csv")},
            data={"dataset_type": "CDR", "source_name": "test"})
        self.assertEqual(resp.status_code, 201, resp.text)
        data = resp.json()["data"]
        self.assertEqual(data["dataset_type"], "CDR")
        self.assertEqual(data["status"], "UPLOADED")
        self.assertEqual(data["record_count"], 2)
        self.assert_no_paths(resp.content)

    def test_upload_missing_file(self):
        resp = self.client.post("/api/upload", data={"dataset_type": "CDR"})
        self.assertEqual(resp.status_code, 400)
        self.assertEqual(resp.json()["error"]["code"], "MISSING_FILE")

    def test_upload_unsupported_extension(self):
        resp = self.client.post(
            "/api/upload", files={"file": ("run.exe", b"MZ", "application/x-msdownload")},
            data={"dataset_type": "CDR"})
        self.assertEqual(resp.status_code, 422)
        self.assertEqual(resp.json()["error"]["code"], "UNSUPPORTED_FILE_TYPE")

    def test_upload_duplicate(self):
        kwargs = {"files": {"file": ("a.csv", CDR_CSV, "text/csv")},
                  "data": {"dataset_type": "CDR"}}
        first = self.client.post("/api/upload", **kwargs)
        self.assertEqual(first.status_code, 201)
        second = self.client.post("/api/upload", **kwargs)
        self.assertEqual(second.status_code, 409)
        self.assertEqual(second.json()["error"]["code"], "DUPLICATE_UPLOAD")

    def test_process_endpoint(self):
        upload = self.client.post(
            "/api/upload", files={"file": ("cdr.csv", CDR_CSV, "text/csv")},
            data={"dataset_type": "CDR"}).json()["data"]
        resp = self.client.post("/api/process",
                                json={"upload_id": upload["upload_id"]})
        self.assertEqual(resp.status_code, 200, resp.text)
        body = resp.json()["data"]
        self.assertEqual(body["status"], "SUCCEEDED")
        self.assertEqual(body["valid_count"], 2)
        self.assertEqual(body["stages"], ["VALIDATION", "PARSING", "NORMALIZATION"])
        self.assert_no_paths(resp.content)
        poll = self.client.get(f"/api/process/{body['job_id']}")
        self.assertEqual(poll.status_code, 200)
        self.assertEqual(poll.json()["data"]["status"], "SUCCEEDED")

    def test_process_unknown_upload(self):
        resp = self.client.post("/api/process", json={"upload_id": "upl_nope"})
        self.assertEqual(resp.status_code, 404)
        self.assertEqual(resp.json()["error"]["code"], "UPLOAD_NOT_FOUND")

    def test_process_failure_honest(self):
        upload = self.client.post(
            "/api/upload", files={"file": ("bad.json", b"{oops", "application/json")},
            data={"dataset_type": "FIR"}).json()["data"]
        resp = self.client.post("/api/process",
                                json={"upload_id": upload["upload_id"]})
        body = resp.json()["data"]
        self.assertEqual(body["status"], "FAILED")
        self.assertEqual(body["errors"][0]["code"], "INVALID_JSON")

    def test_process_rejects_bad_upload_id_shape(self):
        resp = self.client.post("/api/process", json={"upload_id": "../x"})
        self.assertEqual(resp.status_code, 422)


class Phase1SampleTests(unittest.TestCase):
    """Phase 1 compatibility: real generator output must ingest cleanly."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.svc, _, _, _ = make_service(self.tmp.name)

    def tearDown(self):
        self.tmp.cleanup()

    def ingest_sample(self, filename, dtype):
        path = os.path.join(REPO_ROOT, "data", "sample", filename)
        with open(path, "rb") as fh:
            content = fh.read()
        doc = self.svc.upload(content, filename, dtype)
        return self.svc.process(doc["id"])

    def test_sample_cdr(self):
        result = self.ingest_sample("cdr.csv", "CDR")
        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertGreater(result["valid_count"], 50)

    def test_sample_fir(self):
        result = self.ingest_sample("fir.csv", "FIR")
        self.assertEqual(result["status"], "SUCCEEDED")
        self.assertGreater(result["valid_count"], 20)

    def test_sample_transactions(self):
        result = self.ingest_sample("transactions.csv", "TRANSACTION")
        self.assertEqual(result["status"], "SUCCEEDED")

    def test_sample_vehicles_locations(self):
        for name, dtype in (("vehicles.csv", "VEHICLE"),
                            ("locations.csv", "LOCATION")):
            result = self.ingest_sample(name, dtype)
            self.assertEqual(result["status"], "SUCCEEDED", name)


if __name__ == "__main__":
    unittest.main()
