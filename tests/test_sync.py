"""Tests for scripts/sync.py — Colorado Civic Data sync pipeline."""

import io
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch, call

import yaml

# Ensure scripts/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.sync import (
    attach_committees_to_legislators,
    fetch_bills,
    fetch_committees,
    fetch_legislators,
    write_yaml,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _mock_response(data: dict, status_code: int = 200) -> MagicMock:
    """Return a mock requests.Response wrapping *data*."""
    resp = MagicMock()
    resp.status_code = status_code
    resp.raise_for_status = MagicMock()
    resp.json.return_value = data
    return resp


# ---------------------------------------------------------------------------
# Sample fixtures
# ---------------------------------------------------------------------------

SAMPLE_PERSON = {
    "id": "ocd-person/aaaa-1111",
    "name": "Jane Smith",
    "given_name": "Jane",
    "family_name": "Smith",
    "biography": "A dedicated public servant.",
    "image": "https://example.com/photo.jpg",
    "links": [{"url": "https://janesmith.example.com", "note": "official"}],
    "ids": {
        "twitter": "janesmith",
        "facebook": "janesmithco",
        "instagram": "",
        "youtube": "",
    },
    "offices": [
        {
            "classification": "capitol",
            "address": "200 E Colfax Ave, Denver CO 80203",
            "voice": "303-555-0100",
        },
        {
            "classification": "district",
            "address": "123 Main St, Boulder CO 80302",
            "voice": "303-555-0200",
        },
    ],
    "current_role": {
        "party": "Democratic",
        "district": "15",
        "start_date": "2023-01-09",
        "end_date": "2027-01-09",
        "classification": "lower",
        "org_classification": "lower",
    },
    "party": [{"name": "Democratic"}],
}

SAMPLE_LEGISLATORS_PAGE_1 = {
    "results": [SAMPLE_PERSON],
    "pagination": {"total_pages": 1, "page": 1},
}

SAMPLE_COMMITTEE_LIST = {
    "results": [
        {
            "id": "ocd-organization/comm-0001",
            "name": "Judiciary",
            "classification": "committee",
            "parent": {"classification": "lower"},
        }
    ],
    "pagination": {"total_pages": 1, "page": 1},
}

SAMPLE_COMMITTEE_DETAIL = {
    "id": "ocd-organization/comm-0001",
    "name": "Judiciary",
    "classification": "committee",
    "parent": {"classification": "lower"},
    "memberships": [
        {
            "person": {"id": "ocd-person/aaaa-1111", "name": "Jane Smith"},
            "role": "chair",
        }
    ],
}

SAMPLE_BILL_PAGE_1 = {
    "results": [
        {
            "id": "HB1001",
            "identifier": "HB1001",
            "title": "Concerning School Funding",
            "subject": ["Education", "Finance"],
            "sponsorships": [
                {
                    "name": "Jane Smith",
                    "person": {"id": "ocd-person/aaaa-1111"},
                    "primary": True,
                    "classification": "primary",
                }
            ],
            "latest_action_description": "Signed by Governor",
            "versions": [{"links": [{"url": "https://leg.colorado.gov/bills/hb1001"}]}],
            "votes": [
                {
                    "start_date": "2026-02-15",
                    "organization_classification": "lower",
                    "result": "pass",
                    "counts": [
                        {"option": "yes", "value": 40},
                        {"option": "no", "value": 25},
                    ],
                    "votes": [
                        {"voter": {"id": "ocd-person/aaaa-1111"}, "option": "yes"}
                    ],
                }
            ],
        }
    ],
    "pagination": {"total_pages": 1, "page": 1},
}


# ---------------------------------------------------------------------------
# Tests: fetch_legislators
# ---------------------------------------------------------------------------

class TestFetchLegislators(unittest.TestCase):
    """Verify fetch_legislators maps OpenStates fields to our schema."""

    @patch("scripts.sync.openstates_get")
    def test_basic_field_mapping(self, mock_get):
        """fetch_legislators should map a person record to our schema."""
        mock_get.return_value = SAMPLE_LEGISLATORS_PAGE_1

        result = fetch_legislators("lower")

        self.assertEqual(len(result), 1)
        leg = result[0]

        self.assertEqual(leg["id"], "ocd-person/aaaa-1111")
        self.assertEqual(leg["name"], "Jane Smith")
        self.assertEqual(leg["given_name"], "Jane")
        self.assertEqual(leg["family_name"], "Smith")
        self.assertEqual(leg["party"], "Democratic")
        self.assertEqual(leg["chamber"], "house")       # lower → house
        self.assertEqual(leg["district"], 15)           # cast to int
        self.assertEqual(leg["term_start"], "2023-01-09")
        self.assertEqual(leg["term_end"], "2027-01-09")
        self.assertEqual(leg["bio"], "A dedicated public servant.")
        self.assertEqual(leg["photo_url"], "https://example.com/photo.jpg")
        self.assertEqual(leg["website"], "https://janesmith.example.com")

    @patch("scripts.sync.openstates_get")
    def test_contact_offices(self, mock_get):
        """Capitol and district offices should map to contact sub-dict."""
        mock_get.return_value = SAMPLE_LEGISLATORS_PAGE_1

        result = fetch_legislators("lower")
        contact = result[0]["contact"]

        self.assertEqual(contact["capitol"]["address"], "200 E Colfax Ave, Denver CO 80203")
        self.assertEqual(contact["capitol"]["phone"], "303-555-0100")
        self.assertEqual(contact["district"]["address"], "123 Main St, Boulder CO 80302")
        self.assertEqual(contact["district"]["phone"], "303-555-0200")

    @patch("scripts.sync.openstates_get")
    def test_social_handles(self, mock_get):
        """Twitter and facebook should be mapped; empty strings dropped."""
        mock_get.return_value = SAMPLE_LEGISLATORS_PAGE_1

        result = fetch_legislators("lower")
        social = result[0]["social"]

        self.assertEqual(social["twitter"], "janesmith")
        self.assertEqual(social["facebook"], "janesmithco")
        # instagram and youtube were empty strings — should be None or absent
        self.assertFalse(social.get("instagram"))
        self.assertFalse(social.get("youtube"))

    @patch("scripts.sync.openstates_get")
    def test_upper_chamber_maps_to_senate(self, mock_get):
        """'upper' classification should produce chamber='senate'."""
        person = dict(SAMPLE_PERSON)
        role = dict(person["current_role"])
        role["classification"] = "upper"
        role["org_classification"] = "upper"
        person = dict(person, current_role=role)
        mock_get.return_value = {
            "results": [person],
            "pagination": {"total_pages": 1, "page": 1},
        }

        result = fetch_legislators("upper")
        self.assertEqual(result[0]["chamber"], "senate")

    @patch("scripts.sync.openstates_get")
    def test_committees_initialized_empty(self, mock_get):
        """committees list should start empty (filled later by attach_committees)."""
        mock_get.return_value = SAMPLE_LEGISLATORS_PAGE_1

        result = fetch_legislators("lower")
        self.assertEqual(result[0]["committees"], [])

    @patch("scripts.sync.openstates_get")
    def test_sorted_by_district(self, mock_get):
        """Results should be sorted numerically by district."""
        p1 = dict(SAMPLE_PERSON, id="ocd-person/p1", name="Alice A")
        r1 = dict(SAMPLE_PERSON["current_role"], district="25")
        p1 = dict(p1, current_role=r1)

        p2 = dict(SAMPLE_PERSON, id="ocd-person/p2", name="Bob B")
        r2 = dict(SAMPLE_PERSON["current_role"], district="3")
        p2 = dict(p2, current_role=r2)

        mock_get.return_value = {
            "results": [p1, p2],
            "pagination": {"total_pages": 1, "page": 1},
        }

        result = fetch_legislators("lower")
        self.assertEqual(result[0]["district"], 3)
        self.assertEqual(result[1]["district"], 25)


# ---------------------------------------------------------------------------
# Tests: attach_committees_to_legislators
# ---------------------------------------------------------------------------

class TestAttachCommittees(unittest.TestCase):
    """Verify committee assignments are linked to legislators by ID."""

    def _make_legislators(self):
        return [
            {
                "id": "ocd-person/aaaa-1111",
                "name": "Jane Smith",
                "committees": [],
            }
        ]

    def _make_committees(self):
        return [
            {
                "name": "Judiciary",
                "chamber": "house",
                "members": [
                    {
                        "name": "Jane Smith",
                        "id": "ocd-person/aaaa-1111",
                        "role": "chair",
                    }
                ],
            }
        ]

    def test_committee_attached_by_id(self):
        legislators = self._make_legislators()
        committees = self._make_committees()

        attach_committees_to_legislators(legislators, committees)

        self.assertEqual(len(legislators[0]["committees"]), 1)
        self.assertEqual(legislators[0]["committees"][0]["name"], "Judiciary")

    def test_no_match_leaves_empty(self):
        legislators = [{"id": "ocd-person/no-match", "committees": []}]
        committees = self._make_committees()

        attach_committees_to_legislators(legislators, committees)

        self.assertEqual(legislators[0]["committees"], [])


# ---------------------------------------------------------------------------
# Tests: fetch_bills
# ---------------------------------------------------------------------------

class TestFetchBills(unittest.TestCase):
    """Verify fetch_bills maps OpenStates bill data to our schema."""

    @patch("scripts.sync.openstates_get")
    def test_basic_bill_fields(self, mock_get):
        mock_get.return_value = SAMPLE_BILL_PAGE_1

        result = fetch_bills("2026")

        self.assertEqual(len(result), 1)
        bill = result[0]

        self.assertEqual(bill["id"], "HB1001")
        self.assertEqual(bill["title"], "Concerning School Funding")
        self.assertIn("Education", bill["subjects"])
        self.assertEqual(bill["status"], "Signed by Governor")
        self.assertEqual(bill["text_url"], "https://leg.colorado.gov/bills/hb1001")

    @patch("scripts.sync.openstates_get")
    def test_sponsor_mapping(self, mock_get):
        mock_get.return_value = SAMPLE_BILL_PAGE_1

        result = fetch_bills("2026")
        sponsors = result[0]["sponsors"]

        self.assertEqual(len(sponsors), 1)
        self.assertEqual(sponsors[0]["name"], "Jane Smith")
        self.assertEqual(sponsors[0]["id"], "ocd-person/aaaa-1111")
        self.assertEqual(sponsors[0]["type"], "primary")

    @patch("scripts.sync.openstates_get")
    def test_vote_mapping(self, mock_get):
        mock_get.return_value = SAMPLE_BILL_PAGE_1

        result = fetch_bills("2026")
        votes = result[0]["votes"]

        self.assertEqual(len(votes), 1)
        v = votes[0]
        self.assertEqual(v["date"], "2026-02-15")
        self.assertEqual(v["chamber"], "house")   # lower → house
        self.assertTrue(v["passed"])
        self.assertEqual(v["yes"], 40)
        self.assertEqual(v["no"], 25)
        self.assertEqual(v["roll_call"][0]["id"], "ocd-person/aaaa-1111")
        self.assertEqual(v["roll_call"][0]["vote"], "yes")


# ---------------------------------------------------------------------------
# Tests: write_yaml
# ---------------------------------------------------------------------------

class TestWriteYaml(unittest.TestCase):
    """Verify write_yaml creates valid YAML that round-trips cleanly."""

    def test_roundtrip(self):
        data = [
            {"id": "ocd-person/test-001", "name": "Test Person", "district": 7}
        ]
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "sub" / "output.yaml"
            write_yaml(data, out_path)

            self.assertTrue(out_path.exists())
            loaded = yaml.safe_load(out_path.read_text())
            self.assertEqual(loaded, data)

    def test_creates_parent_dirs(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "a" / "b" / "c" / "data.yaml"
            write_yaml({"key": "value"}, out_path)
            self.assertTrue(out_path.exists())

    def test_empty_list(self):
        with tempfile.TemporaryDirectory() as tmpdir:
            out_path = Path(tmpdir) / "empty.yaml"
            write_yaml([], out_path)
            loaded = yaml.safe_load(out_path.read_text())
            # yaml.safe_load of an empty list written with yaml.dump returns []
            self.assertEqual(loaded, [])


# ---------------------------------------------------------------------------
# Tests: fetch_committees
# ---------------------------------------------------------------------------

class TestFetchCommittees(unittest.TestCase):
    """Verify fetch_committees returns proper schema including member list."""

    @patch("scripts.sync.openstates_get")
    def test_committee_fields(self, mock_get):
        """fetch_committees should return name, chamber, and members."""
        # First call → list; subsequent calls → detail for each committee
        mock_get.side_effect = [
            SAMPLE_COMMITTEE_LIST,
            SAMPLE_COMMITTEE_DETAIL,
        ]

        result = fetch_committees("lower")

        self.assertEqual(len(result), 1)
        comm = result[0]
        self.assertEqual(comm["name"], "Judiciary")
        self.assertEqual(comm["chamber"], "house")
        self.assertEqual(len(comm["members"]), 1)
        self.assertEqual(comm["members"][0]["id"], "ocd-person/aaaa-1111")
        self.assertEqual(comm["members"][0]["role"], "chair")


if __name__ == "__main__":
    unittest.main()
