"""Phase 1 — Synthetic dataset generator (stdlib only, no third-party deps).

Generates completely fictional FIR, CDR, transaction, vehicle and location
records with intentional cross-source overlap so later phases (NLP, entity
resolution, knowledge graph, analytics) have a meaningful demo graph.

Safety: every name, phone number, account, vehicle registration, location
and case narrative is invented. Nothing here refers to real people, real
cases, or real criminality. All outputs are marked synthetic.

Determinism: all randomness flows from random.Random(seed). Re-running with
the same seed produces byte-identical CSV files.

Usage:
    python scripts/generate_data.py [--seed 42] [--out-dir data/sample]
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import re
import sys
from datetime import datetime, timedelta, timezone

# ---------------------------------------------------------------------------
# Constants / schemas (match PROJECT_SPEC.md fields)
# ---------------------------------------------------------------------------

FIR_FIELDS = ["fir_id", "date", "police_station", "text", "source"]
CDR_FIELDS = ["cdr_id", "caller", "receiver", "timestamp", "duration"]
TXN_FIELDS = ["transaction_id", "sender_account", "receiver_account",
              "amount", "currency", "timestamp"]
VEHICLE_FIELDS = ["vehicle_id", "registration_number", "owner_name", "source"]
LOCATION_FIELDS = ["location_id", "name", "latitude", "longitude"]
ENTITY_FIELDS = ["person_id", "canonical_name", "aliases", "phone",
                 "account", "vehicle", "organization", "group",
                 "test_pattern"]

PHONE_RE = re.compile(r"^\+91\d{10}$")
VEHICLE_RE = re.compile(r"^[A-Z]{2}\d{2}[A-Z]{2}\d{4}$")
ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,64}$")

DAY_START = datetime(2026, 1, 1, tzinfo=timezone.utc)
DAY_END = datetime(2026, 8, 31, tzinfo=timezone.utc)

SYNTHETIC_TAG = "[SYNTHETIC RECORD]"

# ---------------------------------------------------------------------------
# Fictional roster (canonical persons + unique aliases)
# group: community A/B/C. test_pattern: analytics demo role (synthetic only,
# never a criminality label).
# ---------------------------------------------------------------------------

PERSONS = [
    # id, canonical name, aliases, group, test_pattern
    ("person_001", "Rahul Sharma", ["Rahul S Sharma", "R. Sharma"], "A", "central"),
    ("person_002", "Amit Kumar", ["Amit K", "A. Kumar"], "A", "community"),
    ("person_003", "Vikas Singh", ["Vikas S", "V. Singh"], "A", "comm_anomaly"),
    ("person_004", "Priya Nair", ["P. Nair"], "A", "community"),
    ("person_005", "Sanjay Gupta", ["S. Gupta"], "A", "community"),
    ("person_006", "Neha Joshi", [], "A", "standard"),
    ("person_007", "Arjun Mehta", ["A. Mehta"], "A", "bridge"),
    ("person_008", "Kavita Rao", ["K. Rao"], "B", "community"),
    ("person_009", "Manoj Tiwari", ["M. Tiwari"], "B", "fin_anomaly"),
    ("person_010", "Deepak Yadav", [], "B", "community"),
    ("person_011", "Rahul Verma", [], "B", "similar_name"),
    ("person_012", "Rohit Sharma", ["Rohit S"], "B", "loc_anomaly"),
    ("person_013", "Sunita Devi", [], "B", "standard"),
    ("person_014", "Farhan Khan", ["F. Khan"], "B", "bridge"),
    ("person_015", "Geeta Patel", ["G. Patel"], "C", "community"),
    ("person_016", "Rajesh Iyer", [], "C", "community"),
    ("person_017", "Pooja Mishra", ["P. Mishra"], "C", "community"),
    ("person_018", "Vikram Malhotra", [], "C", "standard"),
    ("person_019", "Anjali Desai", ["A. Desai"], "C", "standard"),
    ("person_020", "Karan Bedi", [], "C", "similar_name"),
]

ACCOUNT_IDS = [f"ACC{i:03d}" for i in range(1, 16)]
PERSON_ACCOUNT = {  # person_id -> list of account ids
    "person_001": ["ACC001"], "person_002": ["ACC002"],
    "person_003": ["ACC003"], "person_005": ["ACC004"],
    "person_007": ["ACC005"], "person_008": ["ACC006"],
    "person_009": ["ACC007", "ACC008"], "person_010": ["ACC009"],
    "person_012": ["ACC010"], "person_014": ["ACC011"],
    "person_015": ["ACC012"], "person_017": ["ACC013"],
    "person_018": ["ACC014"], "person_020": ["ACC015"],
}

VEHICLE_OWNERS = [  # (vehicle_id, registration, owner person_id)
    ("vehicle_001", "DL01AB1234", "person_001"),
    ("vehicle_002", "MH02CD5678", "person_002"),
    ("vehicle_003", "DL03EF9012", "person_003"),
    ("vehicle_004", "KA04GH3456", "person_005"),
    ("vehicle_005", "UP05IJ7890", "person_007"),
    ("vehicle_006", "MH06KL1234", "person_008"),
    ("vehicle_007", "DL07MN5678", "person_009"),
    ("vehicle_008", "TN08OP9012", "person_010"),
    ("vehicle_009", "DL09QR3456", "person_011"),
    ("vehicle_010", "KA10ST7890", "person_012"),
    ("vehicle_011", "UP11UV1234", "person_013"),
    ("vehicle_012", "MH12WX5678", "person_014"),
    ("vehicle_013", "DL13YZ9012", "person_015"),
    ("vehicle_014", "KA14AB3456", "person_017"),
    ("vehicle_015", "TN15CD7890", "person_018"),
    ("vehicle_016", "DL16EF1234", "person_020"),
]

# (location_id, name, lat, long) — lat/long empty string when unavailable.
LOCATIONS = [
    ("location_001", "Shanti Nagar, Delhi", "28.6139", "77.2090"),
    ("location_002", "Green Park Extension, Delhi", "28.5571", "77.2067"),
    ("location_003", "Ashok Vihar, Delhi", "", ""),
    ("location_004", "Lakeview Colony, Mumbai", "19.0760", "72.8777"),
    ("location_005", "Shivaji Park, Mumbai", "19.0282", "72.8370"),
    ("location_006", "MG Road, Bengaluru", "12.9716", "77.5946"),
    ("location_007", "Whitefield, Bengaluru", "12.9698", "77.7500"),
    ("location_008", "Anna Nagar, Chennai", "13.0827", "80.2707"),
    ("location_009", "T Nagar, Chennai", "13.0418", "80.2341"),
    ("location_010", "Aliganj, Lucknow", "26.8500", "80.9462"),
    ("location_011", "Gomti Nagar, Lucknow", "26.8467", "80.9462"),
    ("location_012", "Kothrud, Pune", "18.5074", "73.8077"),
    ("location_013", "Hadapsar, Pune", "18.5089", "73.9260"),
    ("location_014", "Salt Lake, Kolkata", "22.5726", "88.3639"),
    ("location_015", "New Town, Kolkata", "22.5793", "88.4582"),
    ("location_016", "Riverbank Colony, Patna", "", ""),
]

ORGANIZATIONS = [
    "Sunrise Trading Co", "Lotus Logistics Pvt Ltd", "Brightpath Solutions",
    "Greenfield Agro Foods", "Cityline Cabs", "NovaTech Services",
    "Harbourline Exports",
]
PERSON_ORG = {
    "person_002": "Sunrise Trading Co", "person_005": "Sunrise Trading Co",
    "person_008": "Lotus Logistics Pvt Ltd", "person_010": "Lotus Logistics Pvt Ltd",
    "person_007": "Cityline Cabs", "person_015": "NovaTech Services",
    "person_017": "NovaTech Services", "person_018": "Harbourline Exports",
}

POLICE_STATIONS = [
    "Shanti Nagar Police Station", "Lakeview Police Station",
    "MG Road Police Station", "Aliganj Police Station",
    "Kothrud Police Station", "Salt Lake Police Station",
]

FIR_TOPICS = [
    "a reported dispute over a shop payment",
    "a missing mobile phone complaint",
    "a minor roadside quarrel",
    "a suspected forged billing receipt",
    "a lost vehicle document report",
]

# Persons holding two phones (extra overlap for CDR).
SECOND_PHONE = {"person_001", "person_003"}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _ts(rng: random.Random, night: bool = False) -> str:
    span = (DAY_END - DAY_START).days
    day = DAY_START + timedelta(days=rng.randrange(span + 1))
    hour = rng.randrange(0, 5) if night else rng.randrange(5, 24)
    minute = rng.randrange(60)
    return day.replace(hour=hour, minute=minute, second=0).strftime("%Y-%m-%dT%H:%M:%SZ")


def _day(rng: random.Random) -> str:
    span = (DAY_END - DAY_START).days
    return (DAY_START + timedelta(days=rng.randrange(span + 1))).strftime("%Y-%m-%d")


# ---------------------------------------------------------------------------
# Generation
# ---------------------------------------------------------------------------

def generate(seed: int = 42) -> dict:
    """Build all tables deterministically from seed. Returns name -> rows."""
    rng = random.Random(seed)
    by_id = {p[0]: p for p in PERSONS}
    groups = {}
    for pid, _, _, grp, _ in PERSONS:
        groups.setdefault(grp, []).append(pid)

    # -- phones ------------------------------------------------------------
    numbers, seen = {}, set()
    for pid, _, _, _, _ in PERSONS:
        for _ in range(2 if pid in SECOND_PHONE else 1):
            while True:
                num = f"+91{rng.randrange(9000000000, 9999999999)}"
                if num not in seen:
                    seen.add(num)
                    numbers.setdefault(pid, []).append(num)
                    break

    # -- entities roster ----------------------------------------------------
    vehicles_by_owner = {o: (v, r) for v, r, o in VEHICLE_OWNERS}
    entities = []
    for pid, name, aliases, grp, pattern in PERSONS:
        vid, reg = vehicles_by_owner.get(pid, ("", ""))
        entities.append({
            "person_id": pid, "canonical_name": name,
            "aliases": "|".join(aliases),
            "phone": "|".join(numbers[pid]),
            "account": "|".join(PERSON_ACCOUNT.get(pid, [])),
            "vehicle": vid, "organization": PERSON_ORG.get(pid, ""),
            "group": grp, "test_pattern": pattern,
        })

    primary_phone = {pid: nums[0] for pid, nums in numbers.items()}

    # -- CDR (80) ------------------------------------------------------------
    cdr, used_pairs = [], set()

    def add_call(a: str, b: str, night: bool = False) -> None:
        if a == b:
            return
        pa = numbers[a]
        pb = numbers[b]
        caller = pa[rng.randrange(len(pa))]
        receiver = pb[rng.randrange(len(pb))]
        cdr.append({
            "cdr_id": f"CDR_{len(cdr) + 1:03d}",
            "caller": caller, "receiver": receiver,
            "timestamp": _ts(rng, night),
            "duration": str(rng.randrange(30, 901)),
        })
        used_pairs.add((a, b))

    # central entity: many connections
    central_targets = (groups["A"] + ["person_008", "person_009"]
                       + [p for p in groups["B"] if p != "person_001"])
    for i in range(18):
        add_call("person_001", central_targets[i % len(central_targets)])
    # communication anomaly: high volume + night calls + many contacts
    anomaly_contacts = [p for p in PERSONS if p[0] != "person_003"]
    for i in range(24):
        add_call("person_003", anomaly_contacts[i % len(anomaly_contacts)][0],
                 night=(i % 3 == 0))
    # bridges connect groups
    for other in ["person_002", "person_005", "person_008", "person_010"]:
        add_call("person_007", other)
        add_call(other, "person_007")
    for other in ["person_009", "person_012", "person_015", "person_017"]:
        add_call("person_014", other)
    # background intra-group traffic
    while len(cdr) < 80:
        grp = rng.choice(["A", "B", "C"])
        a, b = rng.sample(groups[grp], 2)
        add_call(a, b)

    # -- transactions (45) -----------------------------------------------------
    txns = []

    def add_txn(sender: str, receiver: str, lo: int, hi: int) -> None:
        if sender == receiver:
            return
        txns.append({
            "transaction_id": f"TXN{len(txns) + 1:03d}",
            "sender_account": sender, "receiver_account": receiver,
            "amount": str(rng.randrange(lo, hi + 1)),
            "currency": "INR", "timestamp": _ts(rng),
        })

    p9accts = PERSON_ACCOUNT["person_009"]
    others = [a for a in ACCOUNT_IDS if a not in p9accts]
    for _ in range(12):  # financial anomaly: large amounts
        if rng.random() < 0.5:
            add_txn(rng.choice(p9accts), rng.choice(others), 500000, 900000)
        else:
            add_txn(rng.choice(others), rng.choice(p9accts), 500000, 900000)
    for _ in range(6):  # central entity: moderate activity
        add_txn("ACC001", rng.choice(others), 20000, 80000)
    while len(txns) < 45:
        a, b = rng.sample(ACCOUNT_IDS, 2)
        add_txn(a, b, 5000, 60000)

    # -- FIRs (25) ---------------------------------------------------------------
    alias_of = {}
    for pid, name, aliases, _, _ in PERSONS:
        alias_of[pid] = [name] + aliases

    fir_persons = [
        ("person_001", "person_002"), ("person_003", "person_004"),
        ("person_007", "person_008"), ("person_009", "person_010"),
        ("person_001", "person_007"), ("person_012", "person_011"),
        ("person_014", "person_015"), ("person_005", "person_006"),
        ("person_008", "person_009"), ("person_015", "person_017"),
        ("person_001", "person_003"), ("person_018", "person_019"),
        ("person_007", "person_009"), ("person_002", "person_005"),
        ("person_010", "person_012"), ("person_014", "person_009"),
        ("person_016", "person_017"), ("person_001", "person_012"),
        ("person_004", "person_006"), ("person_011", "person_013"),
        ("person_003", "person_007"), ("person_009", "person_014"),
        ("person_020", "person_018"), ("person_005", "person_001"),
        ("person_012", "person_014"),
    ]
    firs = []
    for i, (pa, pb) in enumerate(fir_persons, 1):
        # use alias variants in some narratives to exercise resolution
        na = rng.choice(alias_of[pa]) if i % 3 == 0 else by_id[pa][1]
        nb = rng.choice(alias_of[pb]) if i % 4 == 0 else by_id[pb][1]
        loc = LOCATIONS[rng.randrange(len(LOCATIONS))][1]
        topic = FIR_TOPICS[rng.randrange(len(FIR_TOPICS))]
        extra = ""
        if i % 2 == 0 and pa in vehicles_by_owner:
            extra += f" A vehicle bearing registration {vehicles_by_owner[pa][1]} was noted near {loc}."
        if i % 5 == 0 and pa in primary_phone:
            extra += f" The contact number {primary_phone[pa]} was provided for follow-up."
        text = (f"{SYNTHETIC_TAG} Complainant {na} reported {topic} involving {nb} "
                f"near {loc}.{extra} The matter is recorded for investigation support only; "
                f"no finding of guilt is implied.")
        firs.append({
            "fir_id": f"FIR_{i:03d}", "date": _day(rng),
            # 2 FIRs intentionally leave the optional station blank
            "police_station": "" if i in (7, 19) else POLICE_STATIONS[rng.randrange(len(POLICE_STATIONS))],
            "text": text, "source": "SYNTHETIC",
        })

    # -- vehicles (16): some rows use alias owner names ---------------------------
    alias_owner_for = {"vehicle_003", "vehicle_007", "vehicle_012", "vehicle_014"}
    vehicles = []
    for vid, reg, owner in VEHICLE_OWNERS:
        name = by_id[owner][1]
        aliases = by_id[owner][2]
        vehicles.append({
            "vehicle_id": vid, "registration_number": reg,
            "owner_name": rng.choice(aliases) if vid in alias_owner_for and aliases else name,
            "source": "SYNTHETIC",
        })

    # -- locations (16; 2 without coordinates) ---------------------------------------
    locations = [
        {"location_id": lid, "name": nm, "latitude": la, "longitude": lo}
        for lid, nm, la, lo in LOCATIONS
    ]

    return {
        "entities": entities, "fir": firs, "cdr": cdr,
        "transactions": txns, "vehicles": vehicles, "locations": locations,
    }


# ---------------------------------------------------------------------------
# Validation (fail fast on bad data)
# ---------------------------------------------------------------------------

def _require(value: str, what: str) -> None:
    if value is None or str(value).strip() == "":
        raise ValueError(f"empty required field: {what}")


def validate(t: dict) -> None:
    phones, accounts = set(), set(ACCOUNT_IDS)
    for e in t["entities"]:
        _require(e["person_id"], "entities.person_id")
        _require(e["canonical_name"], "entities.canonical_name")
        for ph in e["phone"].split("|"):
            if not PHONE_RE.match(ph):
                raise ValueError(f"bad phone format: {ph}")
            phones.add(ph)
        for ac in e["account"].split("|"):
            if ac and ac not in accounts:
                raise ValueError(f"unknown account: {ac}")

    alias_to_person: dict[str, str] = {}
    for pid, name, aliases, _, _ in PERSONS:
        for a in [name] + aliases:
            if a in alias_to_person:
                raise ValueError(f"ambiguous alias across persons: {a}")
            alias_to_person[a] = pid

    def check_unique(rows: list, key: str, label: str) -> None:
        ids = [r[key] for r in rows]
        for rid in ids:
            _require(rid, f"{label}.{key}")
            if not ID_RE.match(rid):
                raise ValueError(f"bad id format {label}.{key}: {rid}")
        if len(set(ids)) != len(ids):
            raise ValueError(f"duplicate ids in {label}")

    check_unique(t["fir"], "fir_id", "fir")
    check_unique(t["cdr"], "cdr_id", "cdr")
    check_unique(t["transactions"], "transaction_id", "transactions")
    check_unique(t["vehicles"], "vehicle_id", "vehicles")
    check_unique(t["locations"], "location_id", "locations")

    for f in t["fir"]:
        _require(f["date"], "fir.date")
        _require(f["text"], "fir.text")
        datetime.strptime(f["date"], "%Y-%m-%d")

    for c in t["cdr"]:
        if c["caller"] not in phones or c["receiver"] not in phones:
            raise ValueError(f"CDR references unknown phone: {c['cdr_id']}")
        if c["caller"] == c["receiver"]:
            raise ValueError(f"CDR self-call: {c['cdr_id']}")
        datetime.strptime(c["timestamp"], "%Y-%m-%dT%H:%M:%SZ")
        if int(c["duration"]) <= 0:
            raise ValueError(f"bad duration: {c['cdr_id']}")

    for x in t["transactions"]:
        if x["sender_account"] not in accounts or x["receiver_account"] not in accounts:
            raise ValueError(f"txn references unknown account: {x['transaction_id']}")
        if x["sender_account"] == x["receiver_account"]:
            raise ValueError(f"txn self-transfer: {x['transaction_id']}")
        if int(x["amount"]) <= 0:
            raise ValueError(f"bad amount: {x['transaction_id']}")
        datetime.strptime(x["timestamp"], "%Y-%m-%dT%H:%M:%SZ")

    for v in t["vehicles"]:
        if not VEHICLE_RE.match(v["registration_number"]):
            raise ValueError(f"bad registration: {v['vehicle_id']}")
        if v["owner_name"] not in alias_to_person:
            raise ValueError(f"vehicle owner not traceable: {v['vehicle_id']}")

    for loc in t["locations"]:
        _require(loc["name"], "locations.name")
        for coord in (loc["latitude"], loc["longitude"]):
            if coord != "" and not (-90.0 <= float(coord) <= 180.0):
                raise ValueError(f"bad coordinate in {loc['location_id']}")


# ---------------------------------------------------------------------------
# Writing + CLI
# ---------------------------------------------------------------------------

TABLES = [
    ("entities", ENTITY_FIELDS), ("fir", FIR_FIELDS), ("cdr", CDR_FIELDS),
    ("transactions", TXN_FIELDS), ("vehicles", VEHICLE_FIELDS),
    ("locations", LOCATION_FIELDS),
]


def write_tables(t: dict, out_dir: str, seed: int) -> dict:
    import os
    os.makedirs(out_dir, exist_ok=True)
    counts = {}
    for name, fields in TABLES:
        path = os.path.join(out_dir, f"{name}.csv")
        with open(path, "w", newline="", encoding="utf-8") as fh:
            writer = csv.DictWriter(fh, fieldnames=fields)
            writer.writeheader()
            writer.writerows(t[name])
        counts[name] = len(t[name])
    manifest = {
        "synthetic": True, "seed": seed,
        "generated_at": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "counts": counts,
        "test_patterns": {
            "central": "person_001 (many connections)",
            "bridges": ["person_007 (groups A-B)", "person_014 (groups B-C)"],
            "communities": {"A": 7, "B": 7, "C": 6},
            "comm_anomaly": "person_003 (high call volume, night calls)",
            "fin_anomaly": "person_009 (large transactions)",
            "loc_anomaly": "person_012 (many location mentions)",
        },
        "disclaimer": ("Completely fictional data for analytics testing only. "
                       "No real persons, cases, or findings of criminality."),
    }
    with open(os.path.join(out_dir, "manifest.json"), "w", encoding="utf-8") as fh:
        json.dump(manifest, fh, indent=2)
    return counts


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Generate Phase 1 synthetic datasets.")
    parser.add_argument("--seed", type=int, default=42)
    parser.add_argument("--out-dir", default="data/sample")
    args = parser.parse_args(argv)

    tables = generate(seed=args.seed)
    validate(tables)
    counts = write_tables(tables, args.out_dir, args.seed)
    for name, count in counts.items():
        print(f"Wrote {count} records -> {args.out_dir}/{name}.csv")
    print(f"seed={args.seed} validation=OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
