"""sync.py — Pull Colorado legislative data from OpenStates API v3.

Usage:
    python -m scripts.sync

Requires OPENSTATES_API_KEY in environment (or .env file at repo root).
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

import requests
import yaml
from dotenv import load_dotenv

# Load .env from repo root (two levels up from this file)
_REPO_ROOT = Path(__file__).parent.parent
load_dotenv(_REPO_ROOT / ".env")

_BASE_URL = "https://v3.openstates.org"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

_CHAMBER_MAP = {
    "upper": "senate",
    "lower": "house",
    "legislature": "joint",
}


def _chamber(raw: str) -> str:
    return _CHAMBER_MAP.get(raw, raw)


def _first_link(links: list[dict]) -> str:
    if links:
        return links[0].get("url", "")
    return ""


def _office(offices: list[dict], classification: str) -> dict:
    for o in offices or []:
        if o.get("classification") == classification:
            return o
    return {}


def _social_handle(ids: dict, key: str) -> str | None:
    val = ids.get(key, "") if ids else ""
    return val if val else None


# ---------------------------------------------------------------------------
# Core HTTP
# ---------------------------------------------------------------------------

def openstates_get(endpoint: str, params: dict | None = None) -> dict:
    """Authenticated GET to https://v3.openstates.org.

    Args:
        endpoint: Path starting with '/', e.g. '/people'.
        params:   Query parameters dict (optional).

    Returns:
        Parsed JSON response as a dict.

    Raises:
        requests.HTTPError on non-2xx responses.
        RuntimeError if OPENSTATES_API_KEY is not set.
    """
    api_key = os.environ.get("OPENSTATES_API_KEY")
    if not api_key:
        raise RuntimeError("OPENSTATES_API_KEY environment variable is not set.")

    url = _BASE_URL.rstrip("/") + "/" + endpoint.lstrip("/")
    headers = {"X-API-KEY": api_key}
    resp = requests.get(url, headers=headers, params=params or {})
    resp.raise_for_status()
    return resp.json()


# ---------------------------------------------------------------------------
# Legislators
# ---------------------------------------------------------------------------

def fetch_legislators(classification: str) -> list[dict]:
    """Fetch all legislators for *classification* ('upper' or 'lower').

    Returns a list of dicts matching the project legislator schema,
    sorted by district number.
    """
    legislators: list[dict] = []
    page = 1

    while True:
        data = openstates_get(
            "/people",
            params={
                "jurisdiction": "co",
                "org_classification": classification,
                "include": "other_identifiers,links,offices",
                "page": page,
                "per_page": 100,
            },
        )
        for person in data.get("results", []):
            legislators.append(_map_person(person, classification))

        pagination = data.get("pagination", {})
        if page >= pagination.get("total_pages", 1):
            break
        page += 1

    legislators.sort(key=lambda x: x["district"])
    return legislators


def _map_person(person: dict, classification: str) -> dict:
    """Map a raw OpenStates person record to our schema."""
    role = person.get("current_role") or {}

    # Party: prefer top-level list, fall back to current_role
    party_list = person.get("party", [])
    if party_list and isinstance(party_list, list):
        party = party_list[0].get("name", "")
    else:
        party = role.get("party", "")

    # District as int
    raw_district = role.get("district", "0")
    try:
        district = int(raw_district)
    except (ValueError, TypeError):
        district = 0

    # Chamber from role classification
    role_class = role.get("org_classification") or role.get("classification") or classification
    chamber = _chamber(role_class)

    # Offices
    offices = person.get("offices", [])
    cap = _office(offices, "capitol")
    dist = _office(offices, "district")

    # Social
    ids = person.get("ids") or {}
    social = {
        "twitter": _social_handle(ids, "twitter"),
        "facebook": _social_handle(ids, "facebook"),
        "instagram": _social_handle(ids, "instagram"),
        "youtube": _social_handle(ids, "youtube"),
    }

    return {
        "id": person.get("id", ""),
        "name": person.get("name", ""),
        "given_name": person.get("given_name", ""),
        "family_name": person.get("family_name", ""),
        "party": party,
        "chamber": chamber,
        "district": district,
        "term_start": role.get("start_date", ""),
        "term_end": role.get("end_date", ""),
        "bio": person.get("biography", ""),
        "photo_url": person.get("image", ""),
        "website": _first_link(person.get("links", [])),
        "contact": {
            "capitol": {
                "address": cap.get("address", ""),
                "phone": cap.get("voice", ""),
            },
            "district": {
                "address": dist.get("address", ""),
                "phone": dist.get("voice", ""),
            },
        },
        "social": social,
        "committees": [],
    }


# ---------------------------------------------------------------------------
# Committees
# ---------------------------------------------------------------------------

def fetch_committees(classification: str) -> list[dict]:
    """Fetch committees for *classification* ('upper', 'lower', or 'legislature').

    Fetches the committee list, then pulls individual committee details for
    member rosters.

    Returns a list of dicts with name, chamber, and members fields.
    """
    committees: list[dict] = []
    page = 1

    # For joint committees the org is "legislature"
    org_class = classification if classification == "legislature" else classification

    while True:
        data = openstates_get(
            "/committees",
            params={
                "jurisdiction": "co",
                "classification": "committee",
                "org_classification": org_class,
                "page": page,
                "per_page": 100,
            },
        )
        for raw in data.get("results", []):
            detail = openstates_get(f"/committees/{raw['id']}")
            committees.append(_map_committee(detail))

        pagination = data.get("pagination", {})
        if page >= pagination.get("total_pages", 1):
            break
        page += 1

    return committees


def _map_committee(detail: dict) -> dict:
    """Map a raw committee detail record to our schema."""
    parent = detail.get("parent") or {}
    parent_class = parent.get("classification", "")
    chamber = _chamber(parent_class) if parent_class else "joint"

    members = []
    for m in detail.get("memberships", []):
        p = m.get("person") or {}
        members.append(
            {
                "name": p.get("name", ""),
                "id": p.get("id", ""),
                "role": m.get("role", "member"),
            }
        )

    return {
        "name": detail.get("name", ""),
        "chamber": chamber,
        "members": members,
    }


# ---------------------------------------------------------------------------
# Attach committees to legislators
# ---------------------------------------------------------------------------

def attach_committees_to_legislators(
    legislators: list[dict], committees: list[dict]
) -> None:
    """Mutate legislators in place, adding committee assignments by person ID.

    Each legislator's 'committees' list will contain dicts with 'name',
    'chamber', and 'role' keys for every committee they belong to.
    """
    # Build a lookup: person_id → list of committee refs
    index: dict[str, list[dict]] = {}
    for comm in committees:
        for member in comm.get("members", []):
            pid = member.get("id", "")
            if not pid:
                continue
            if pid not in index:
                index[pid] = []
            index[pid].append(
                {
                    "name": comm["name"],
                    "chamber": comm["chamber"],
                    "role": member.get("role", "member"),
                }
            )

    for leg in legislators:
        leg["committees"] = index.get(leg["id"], [])


# ---------------------------------------------------------------------------
# Bills
# ---------------------------------------------------------------------------

def fetch_bills(session: str) -> list[dict]:
    """Fetch all bills for *session* ('2025' or '2026').

    Includes sponsorships and votes.

    Returns a list of dicts matching the project bill schema.
    """
    bills: list[dict] = []
    page = 1

    while True:
        data = openstates_get(
            "/bills",
            params={
                "jurisdiction": "co",
                "session": session,
                "include": "sponsorships,votes",
                "page": page,
                "per_page": 100,
            },
        )
        for raw in data.get("results", []):
            bills.append(_map_bill(raw))

        pagination = data.get("pagination", {})
        if page >= pagination.get("total_pages", 1):
            break
        page += 1

    return bills


def _map_bill(raw: dict) -> dict:
    """Map a raw OpenStates bill to our schema."""
    # Text URL from first version's first link
    versions = raw.get("versions", [])
    text_url = ""
    if versions:
        v_links = versions[0].get("links", [])
        if v_links:
            text_url = v_links[0].get("url", "")

    # Sponsors
    sponsors = []
    for s in raw.get("sponsorships", []):
        p = s.get("person") or {}
        sponsors.append(
            {
                "name": s.get("name", ""),
                "id": p.get("id", ""),
                "type": "primary" if s.get("primary") else "cosponsor",
            }
        )

    # Votes
    votes = []
    for v in raw.get("votes", []):
        counts = {c["option"]: c["value"] for c in v.get("counts", [])}
        chamber_raw = v.get("organization_classification", "")
        passed = v.get("result", "").lower() in ("pass", "passed")
        roll_call = [
            {
                "id": (vv.get("voter") or {}).get("id", ""),
                "vote": vv.get("option", ""),
            }
            for vv in v.get("votes", [])
        ]
        votes.append(
            {
                "date": v.get("start_date", ""),
                "chamber": _chamber(chamber_raw),
                "passed": passed,
                "yes": counts.get("yes", 0),
                "no": counts.get("no", 0),
                "roll_call": roll_call,
            }
        )

    return {
        "id": raw.get("identifier", raw.get("id", "")),
        "title": raw.get("title", ""),
        "subjects": raw.get("subject", []),
        "sponsors": sponsors,
        "status": raw.get("latest_action_description", ""),
        "text_url": text_url,
        "votes": votes,
    }


# ---------------------------------------------------------------------------
# District GeoJSON
# ---------------------------------------------------------------------------

def fetch_district_geojson() -> None:
    """Print instructions for downloading Census TIGER/Line shapefiles.

    The Census files must be downloaded manually and converted to GeoJSON
    using ogr2ogr or a similar tool.
    """
    instructions = """
District GeoJSON Instructions
==============================
Colorado district boundaries are available as Census TIGER/Line shapefiles.
Download and convert them with the following commands:

Senate districts (State Upper Legislative Districts):
  URL:  https://www2.census.gov/geo/tiger/GENZ2022/shp/cb_2022_08_sldu_500k.zip
  wget https://www2.census.gov/geo/tiger/GENZ2022/shp/cb_2022_08_sldu_500k.zip
  unzip cb_2022_08_sldu_500k.zip
  ogr2ogr -f GeoJSON data/districts/senate.geojson cb_2022_08_sldu_500k.shp

House districts (State Lower Legislative Districts):
  URL:  https://www2.census.gov/geo/tiger/GENZ2022/shp/cb_2022_08_sldl_500k.zip
  wget https://www2.census.gov/geo/tiger/GENZ2022/shp/cb_2022_08_sldl_500k.zip
  unzip cb_2022_08_sldl_500k.zip
  ogr2ogr -f GeoJSON data/districts/house.geojson cb_2022_08_sldl_500k.shp

Requires ogr2ogr (install via: sudo apt install gdal-bin  OR  brew install gdal).
Output files should be placed in data/districts/.
"""
    print(instructions)


# ---------------------------------------------------------------------------
# YAML writer
# ---------------------------------------------------------------------------

def write_yaml(data: Any, path: str | Path) -> None:
    """Write *data* to a YAML file at *path*, creating parent dirs as needed."""
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh, allow_unicode=True, default_flow_style=False, sort_keys=False)


# ---------------------------------------------------------------------------
# Main orchestration
# ---------------------------------------------------------------------------

def sync_all() -> None:
    """Fetch all data and write YAML files to data/."""
    data_dir = _REPO_ROOT / "data"

    # --- Legislators ---
    print("Fetching senate legislators…")
    senate = fetch_legislators("upper")
    print(f"  {len(senate)} senators")

    print("Fetching house legislators…")
    house = fetch_legislators("lower")
    print(f"  {len(house)} representatives")

    # --- Committees ---
    print("Fetching senate committees…")
    senate_comms = fetch_committees("upper")
    print(f"  {len(senate_comms)} senate committees")

    print("Fetching house committees…")
    house_comms = fetch_committees("lower")
    print(f"  {len(house_comms)} house committees")

    print("Fetching joint committees…")
    joint_comms = fetch_committees("legislature")
    print(f"  {len(joint_comms)} joint committees")

    all_committees = senate_comms + house_comms + joint_comms

    # --- Attach committees to legislators ---
    print("Attaching committees to legislators…")
    attach_committees_to_legislators(senate, all_committees)
    attach_committees_to_legislators(house, all_committees)

    # --- Write legislators ---
    write_yaml(senate, data_dir / "legislators" / "senate.yaml")
    write_yaml(house, data_dir / "legislators" / "house.yaml")
    print(f"Wrote data/legislators/senate.yaml and house.yaml")

    # --- Write committees ---
    write_yaml(senate_comms, data_dir / "committees" / "senate.yaml")
    write_yaml(house_comms, data_dir / "committees" / "house.yaml")
    write_yaml(joint_comms, data_dir / "committees" / "joint.yaml")
    print(f"Wrote data/committees/*.yaml")

    # --- Bills ---
    for session in ("2025", "2026"):
        print(f"Fetching bills for session {session}…")
        bills = fetch_bills(session)
        print(f"  {len(bills)} bills")
        write_yaml(bills, data_dir / "bills" / f"{session}.yaml")
        print(f"  Wrote data/bills/{session}.yaml")

    # --- Districts ---
    print()
    fetch_district_geojson()

    print("Sync complete.")


if __name__ == "__main__":
    sync_all()
