"""Idempotent demo seeding: ingest sample data, build graph, run analytics.

Safe to re-run: identical files hit DUPLICATE_UPLOAD and are reused via the
returned upload_id; graph writes are idempotent MERGEs; analytics runs are
history-preserved. Never deletes anything.

Usage (password via env only, never CLI args):
    ADMIN_EMAIL=admin@example.local ADMIN_PASSWORD=... python scripts/seed_demo.py
"""

from __future__ import annotations

import os
import sys
import time

import requests

BASE = os.environ.get("DEMO_BASE_URL", "http://127.0.0.1:8000")
REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FILES = [
    ("data/sample/fir.csv", "FIR"),
    ("data/sample/cdr.csv", "CDR"),
    ("data/sample/transactions.csv", "TRANSACTION"),
    ("data/sample/vehicles.csv", "VEHICLE"),
    ("data/sample/locations.csv", "LOCATION"),
]
TERMINAL = {"SUCCEEDED", "PARTIAL", "FAILED"}


def main() -> int:
    email = os.environ.get("ADMIN_EMAIL", "admin@example.local")
    password = os.environ.get("ADMIN_PASSWORD", "")
    if not password:
        print("Set ADMIN_PASSWORD in your shell first (never commit it).")
        return 2
    session = requests.Session()
    login = session.post(f"{BASE}/api/auth/login",
                         json={"username": email, "password": password},
                         timeout=30)
    if not login.ok:
        print(f"Login failed ({login.status_code}): {login.text[:200]}")
        return 1
    session.headers["Authorization"] = (
        f"Bearer {login.json()['data']['access_token']}")

    upload_ids = []
    for relpath, dtype in FILES:
        path = os.path.join(REPO, *relpath.split("/"))
        with open(path, "rb") as fh:
            resp = session.post(
                f"{BASE}/api/upload",
                files={"file": (os.path.basename(path), fh, "text/csv")},
                data={"dataset_type": dtype}, timeout=120)
        body = resp.json()
        if resp.status_code == 201:
            upload_id = body["data"]["upload_id"]
            print(f"uploaded {relpath} -> {upload_id}")
        elif (body.get("error") or {}).get("code") == "DUPLICATE_UPLOAD":
            upload_id = body["error"]["details"][0]["upload_id"]
            print(f"reusing {relpath} -> {upload_id}")
        else:
            print(f"FAILED upload {relpath}: {resp.status_code} {resp.text[:200]}")
            return 1
        upload_ids.append(upload_id)

        proc = session.post(f"{BASE}/api/process", json={"upload_id": upload_id},
                            timeout=300).json()["data"]
        job_id = proc["job_id"]
        for _ in range(120):
            job = session.get(f"{BASE}/api/process/{job_id}",
                              timeout=30).json()["data"]
            status = job.get("status") or (job.get("result") or {}).get("status")
            if status in TERMINAL:
                break
            time.sleep(2)
        print(f"processed {upload_id} -> {status}")
        if status not in ("SUCCEEDED", "PARTIAL"):
            return 1

        build = session.post(f"{BASE}/api/graph/build",
                             json={"upload_id": upload_id}, timeout=600)
        bstatus = (build.json().get("data") or {}).get("status")
        print(f"graph {upload_id} -> {build.status_code} {bstatus}")
        if not build.ok or bstatus != "SUCCEEDED":
            print(build.text[:300])
            return 1

    run = session.post(f"{BASE}/api/analytics/run", json={}, timeout=600)
    print(f"analytics -> {run.status_code}")
    if not run.ok:
        print(run.text[:300])
        return 1

    verify = session.get(f"{BASE}/api/audit/verify", timeout=30).json()["data"]
    print(f"audit chain: verified={verify['verified']} "
          f"count={verify['count']}")
    print("Demo seed complete.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
