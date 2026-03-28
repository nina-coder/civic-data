"""Data integrity validation for Colorado Civic Data.

Run after sync and before build to catch data issues early.
Also invoked from CI.

Usage:
    python scripts/validate.py
"""

import sys
from pathlib import Path
from typing import Any

import yaml

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

REQUIRED_LEGISLATOR_FIELDS = ("id", "name", "party", "chamber", "district")

DATA_DIR = Path(__file__).parent.parent / "data"
LEGISLATORS_DIR = DATA_DIR / "legislators"
COMMITTEES_DIR = DATA_DIR / "committees"
BILLS_DIR = DATA_DIR / "bills"


# ---------------------------------------------------------------------------
# YAML helper
# ---------------------------------------------------------------------------

def load_yaml(path: Path) -> Any:
    """Load and return the contents of a YAML file."""
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


# ---------------------------------------------------------------------------
# Validators
# ---------------------------------------------------------------------------

def validate_legislators(data: list, expected_count: int) -> list[str]:
    """Validate a list of legislator records.

    Checks:
    - Correct number of legislators matches expected_count.
    - Required fields present on every record: id, name, party, chamber, district.
    - No duplicate district numbers within a chamber.

    Returns a list of error strings; empty list means valid.
    """
    errors: list[str] = []

    # Count check
    if len(data) != expected_count:
        errors.append(
            f"Expected {expected_count} legislators, found {len(data)}."
        )

    # Required fields + duplicate district tracking
    seen_districts: dict[str, set] = {}

    for i, leg in enumerate(data):
        # Use id or index for legible error messages
        label = leg.get("id") or f"record[{i}]"

        for field in REQUIRED_LEGISLATOR_FIELDS:
            if field not in leg or leg[field] is None or leg[field] == "":
                errors.append(
                    f"Legislator {label} is missing required field '{field}'."
                )

        # Duplicate district check (only within same chamber)
        chamber = leg.get("chamber")
        district = leg.get("district")
        if chamber is not None and district is not None:
            seen_districts.setdefault(chamber, set())
            if district in seen_districts[chamber]:
                errors.append(
                    f"Duplicate district {district} in chamber '{chamber}' "
                    f"(found on legislator {label})."
                )
            else:
                seen_districts[chamber].add(district)

    return errors


def validate_committees(data: list, known_legislator_ids: set) -> list[str]:
    """Validate a list of committee records.

    Checks:
    - Each committee has a name.
    - All member IDs resolve to known legislators (no orphaned refs).

    Returns a list of error strings; empty list means valid.
    """
    errors: list[str] = []

    for i, committee in enumerate(data):
        name = committee.get("name") or ""
        label = name if name else f"committee[{i}]"

        if not name:
            errors.append(f"Committee at index {i} is missing a 'name' field.")

        for member in committee.get("members", []):
            member_id = member.get("id")
            if member_id and member_id not in known_legislator_ids:
                errors.append(
                    f"Committee '{label}' references unknown legislator ID "
                    f"'{member_id}' (orphaned reference)."
                )

    return errors


def validate_bills(data: list) -> list[str]:
    """Validate a list of bill records.

    Checks:
    - Every bill has an 'id' and a 'title'.
    - For each vote, yes/no counts match the roll call entries.

    Returns a list of error strings; empty list means valid.
    """
    errors: list[str] = []

    for i, bill in enumerate(data):
        bill_id = bill.get("id")
        label = bill_id or f"bill[{i}]"

        if not bill_id:
            errors.append(f"Bill at index {i} is missing required field 'id'.")

        if not bill.get("title"):
            errors.append(f"Bill '{label}' is missing required field 'title'.")

        for j, vote in enumerate(bill.get("votes", [])):
            vote_label = f"bill '{label}' vote[{j}]"
            declared_yes = vote.get("yes", 0)
            declared_no = vote.get("no", 0)
            roll_call = vote.get("roll_call", [])

            actual_yes = sum(1 for r in roll_call if r.get("vote") == "yes")
            actual_no = sum(1 for r in roll_call if r.get("vote") == "no")

            if declared_yes != actual_yes:
                errors.append(
                    f"{vote_label}: declared yes count ({declared_yes}) does not match "
                    f"roll call yes entries ({actual_yes})."
                )
            if declared_no != actual_no:
                errors.append(
                    f"{vote_label}: declared no count ({declared_no}) does not match "
                    f"roll call no entries ({actual_no})."
                )

    return errors


# ---------------------------------------------------------------------------
# Orchestration
# ---------------------------------------------------------------------------

def validate_all() -> bool:
    """Run all validations. Prints results and returns True if all pass."""
    all_errors: list[str] = []

    # --- Legislators ---
    senate_path = LEGISLATORS_DIR / "senate.yaml"
    house_path = LEGISLATORS_DIR / "house.yaml"

    known_ids: set[str] = set()

    for path, chamber_label, expected in [
        (senate_path, "senate", 35),
        (house_path, "house", 65),
    ]:
        if not path.exists():
            all_errors.append(f"Missing legislator file: {path}")
            continue

        data = load_yaml(path) or []
        errors = validate_legislators(data, expected_count=expected)
        if errors:
            all_errors.extend(f"[legislators/{chamber_label}] {e}" for e in errors)
        else:
            print(f"  OK  legislators/{path.name} ({len(data)} records)")

        for leg in data:
            leg_id = leg.get("id")
            if leg_id:
                known_ids.add(leg_id)

    # --- Committees ---
    committee_files = sorted(COMMITTEES_DIR.glob("*.yaml")) if COMMITTEES_DIR.exists() else []

    for path in committee_files:
        data = load_yaml(path) or []
        if isinstance(data, dict):
            data = [data]
        errors = validate_committees(data, known_ids)
        if errors:
            all_errors.extend(f"[committees/{path.name}] {e}" for e in errors)
        else:
            print(f"  OK  committees/{path.name} ({len(data)} records)")

    if not committee_files:
        print("  --  No committee files found, skipping.")

    # --- Bills ---
    bill_files = sorted(BILLS_DIR.glob("*.yaml")) if BILLS_DIR.exists() else []

    for path in bill_files:
        data = load_yaml(path) or []
        if isinstance(data, dict):
            data = [data]
        errors = validate_bills(data)
        if errors:
            all_errors.extend(f"[bills/{path.name}] {e}" for e in errors)
        else:
            print(f"  OK  bills/{path.name} ({len(data)} records)")

    if not bill_files:
        print("  --  No bill files found, skipping.")

    # --- Summary ---
    if all_errors:
        print(f"\nValidation FAILED — {len(all_errors)} error(s):")
        for err in all_errors:
            print(f"  ERROR: {err}")
        return False

    print("\nValidation passed.")
    return True


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    passed = validate_all()
    sys.exit(0 if passed else 1)
