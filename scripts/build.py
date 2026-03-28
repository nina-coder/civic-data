"""build.py — Generate a static site from YAML data files.

Usage:
    python -m scripts.build

Reads data/ YAML files, writes JSON files to docs/data/, renders Jinja2
templates to docs/, and copies static assets.
"""

from __future__ import annotations

import json
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import yaml
from jinja2 import Environment, FileSystemLoader, TemplateNotFound

# ---------------------------------------------------------------------------
# Repo root
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).parent.parent


# ---------------------------------------------------------------------------
# YAML helpers
# ---------------------------------------------------------------------------

def _load_yaml(path: Path) -> Any:
    with open(path, "r", encoding="utf-8") as fh:
        return yaml.safe_load(fh)


def _ensure_list(val: Any) -> list:
    """Return val if it's already a list, otherwise wrap it (handles bare dicts)."""
    if val is None:
        return []
    if isinstance(val, list):
        return val
    return [val]


# ---------------------------------------------------------------------------
# load_all_data
# ---------------------------------------------------------------------------

def load_all_data(data_dir: Path) -> dict:
    """Read all YAML data files and return a merged data dict.

    Returns:
        {
            "legislators": [...],       # senate + house merged
            "committees": [...],        # all committee files merged
            "bills": {"2025": [...], "2026": [...], ...},
        }
    """
    data_dir = Path(data_dir)

    # --- Legislators ---
    legislators: list[dict] = []
    leg_dir = data_dir / "legislators"
    for fname in ("senate.yaml", "house.yaml"):
        path = leg_dir / fname
        if path.exists():
            legislators.extend(_ensure_list(_load_yaml(path)))

    # --- Committees ---
    committees: list[dict] = []
    comm_dir = data_dir / "committees"
    if comm_dir.exists():
        for path in sorted(comm_dir.glob("*.yaml")):
            committees.extend(_ensure_list(_load_yaml(path)))

    # --- Bills keyed by session ---
    bills: dict[str, list[dict]] = {}
    bills_dir = data_dir / "bills"
    if bills_dir.exists():
        for path in sorted(bills_dir.glob("*.yaml")):
            session = path.stem          # e.g. "2025"
            bills[session] = _ensure_list(_load_yaml(path))

    return {
        "legislators": legislators,
        "committees": committees,
        "bills": bills,
    }


# ---------------------------------------------------------------------------
# generate_json
# ---------------------------------------------------------------------------

def generate_json(data: dict, output_dir: Path) -> None:
    """Write JSON files under output_dir/data/ for JS consumption.

    Files produced:
        legislators.json — flat array of all legislators
        committees.json  — flat array of all committees
        bills.json       — flat array of all bills, each with a 'session' field
    """
    output_dir = Path(output_dir)
    json_dir = output_dir / "data"
    json_dir.mkdir(parents=True, exist_ok=True)

    # legislators.json
    _write_json(json_dir / "legislators.json", data.get("legislators", []))

    # committees.json
    _write_json(json_dir / "committees.json", data.get("committees", []))

    # bills.json — flatten all sessions, adding a 'session' field to each bill
    all_bills: list[dict] = []
    for session, session_bills in data.get("bills", {}).items():
        for bill in session_bills:
            bill_copy = dict(bill, session=session)
            all_bills.append(bill_copy)
    _write_json(json_dir / "bills.json", all_bills)


def _write_json(path: Path, obj: Any) -> None:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)


# ---------------------------------------------------------------------------
# Slug helpers
# ---------------------------------------------------------------------------

def _legislator_slug(legislator: dict) -> str:
    """Return the last path component of the ocd-person ID.

    e.g. 'ocd-person/abcd-1234-efgh-5678' → 'abcd-1234-efgh-5678'
    """
    ocd_id = legislator.get("id", "")
    return ocd_id.split("/")[-1] if "/" in ocd_id else ocd_id


def _committee_slug(committee: dict) -> str:
    """Return a URL-safe slug from the committee name.

    e.g. 'Finance & Appropriations' → 'finance-and-appropriations'
    """
    name = committee.get("name", "")
    slug = name.lower()
    slug = slug.replace("&", "and")
    slug = re.sub(r"[^a-z0-9]+", "-", slug)
    slug = slug.strip("-")
    return slug


# ---------------------------------------------------------------------------
# generate_site
# ---------------------------------------------------------------------------

def generate_site(data: dict, output_dir: Path) -> None:
    """Render Jinja2 templates to static HTML and copy assets.

    Template variables provided to every template:
        legislators   — list of all legislator dicts
        committees    — list of all committee dicts
        bills         — the raw bills dict keyed by session
        leg_by_id     — dict mapping legislator ID → legislator dict
        last_updated  — ISO 8601 timestamp string
        root          — relative path prefix ('' or '../')
    Per-legislator pages also receive:
        legislator    — the individual legislator dict
        bills_by_sponsor — dict mapping leg ID → list of bills they sponsored
    Per-committee pages also receive:
        committee     — the individual committee dict
    """
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)

    # Set up Jinja2
    templates_dir = _REPO_ROOT / "templates"
    env = Environment(
        loader=FileSystemLoader(str(templates_dir)),
        autoescape=True,
    )

    # Shared context values
    last_updated = datetime.now(tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")

    legislators = data.get("legislators", [])
    committees = data.get("committees", [])
    bills_by_session = data.get("bills", {})

    leg_by_id = {leg["id"]: leg for leg in legislators}

    # bills_by_sponsor: leg_id → list of bill dicts (with session field)
    bills_by_sponsor: dict[str, list[dict]] = {}
    for session, session_bills in bills_by_session.items():
        for bill in session_bills:
            bill_with_session = dict(bill, session=session)
            for sponsor in bill.get("sponsors", []):
                sid = sponsor.get("id")
                if sid:
                    bills_by_sponsor.setdefault(sid, []).append(bill_with_session)

    base_ctx = {
        "legislators": legislators,
        "committees": committees,
        "bills": bills_by_session,
        "leg_by_id": leg_by_id,
        "last_updated": last_updated,
    }

    # --- Top-level pages ---
    for template_name, output_name in (
        ("index.html", "index.html"),
        ("browse.html", "browse.html"),
    ):
        _render_template(env, template_name, output_dir / output_name,
                         {**base_ctx, "root": ""})

    # --- Per-legislator pages ---
    leg_dir = output_dir / "legislators"
    leg_dir.mkdir(exist_ok=True)
    for leg in legislators:
        slug = _legislator_slug(leg)
        if not slug:
            continue
        _render_template(
            env,
            "legislator.html",
            leg_dir / f"{slug}.html",
            {
                **base_ctx,
                "root": "../",
                "legislator": leg,
                "bills_by_sponsor": bills_by_sponsor,
            },
        )

    # --- Per-committee pages ---
    comm_dir = output_dir / "committees"
    comm_dir.mkdir(exist_ok=True)
    for committee in committees:
        slug = _committee_slug(committee)
        if not slug:
            continue
        _render_template(
            env,
            "committee.html",
            comm_dir / f"{slug}.html",
            {
                **base_ctx,
                "root": "../",
                "committee": committee,
            },
        )

    # --- Copy static/ to docs/static/ ---
    static_src = _REPO_ROOT / "static"
    static_dst = output_dir / "static"
    if static_src.exists():
        if static_dst.exists():
            shutil.rmtree(static_dst)
        shutil.copytree(static_src, static_dst)

    # --- Copy data/districts/*.geojson to docs/data/ ---
    districts_src = _REPO_ROOT / "data" / "districts"
    data_dst = output_dir / "data"
    data_dst.mkdir(exist_ok=True)
    if districts_src.exists():
        for geojson in districts_src.glob("*.geojson"):
            shutil.copy2(geojson, data_dst / geojson.name)

    # --- Summary ---
    leg_count = len(legislators)
    comm_count = len(committees)
    bill_count = sum(len(v) for v in bills_by_session.values())
    print(f"Build complete:")
    print(f"  {leg_count} legislator pages")
    print(f"  {comm_count} committee pages")
    print(f"  {bill_count} bills in JSON")
    print(f"  Last updated: {last_updated}")


def _render_template(
    env: Environment,
    template_name: str,
    output_path: Path,
    ctx: dict,
) -> None:
    """Render *template_name* to *output_path* with *ctx*.

    Silently skips if the template doesn't exist yet (templates are added in
    Task 5).
    """
    try:
        template = env.get_template(template_name)
    except TemplateNotFound:
        return

    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as fh:
        fh.write(template.render(**ctx))


# ---------------------------------------------------------------------------
# build — top-level orchestrator
# ---------------------------------------------------------------------------

def build(
    data_dir: Path | None = None,
    output_dir: Path | None = None,
) -> None:
    """Orchestrate: load_all_data → generate_json → generate_site."""
    data_dir = Path(data_dir) if data_dir is not None else _REPO_ROOT / "data"
    output_dir = Path(output_dir) if output_dir is not None else _REPO_ROOT / "docs"

    print("Loading data…")
    data = load_all_data(data_dir)
    print(f"  {len(data['legislators'])} legislators")
    print(f"  {len(data['committees'])} committees")
    print(f"  {sum(len(v) for v in data['bills'].values())} bills across {len(data['bills'])} session(s)")

    print("Generating JSON…")
    generate_json(data, output_dir)

    print("Generating site…")
    generate_site(data, output_dir)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    build()
