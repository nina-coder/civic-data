"""Tests for scripts/validate.py — Colorado Civic Data validation."""

import sys
import unittest
from pathlib import Path

# Ensure scripts/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.validate import (
    validate_legislators,
    validate_committees,
    validate_bills,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_legislator(id_="ocd-person/test-001", name="Test Person",
                     party="Democratic", chamber="house", district=1):
    return {
        "id": id_,
        "name": name,
        "party": party,
        "chamber": chamber,
        "district": district,
    }


def _make_35_senators():
    return [
        _make_legislator(
            id_=f"ocd-person/sen-{i:03d}",
            name=f"Senator {i}",
            chamber="senate",
            district=i,
        )
        for i in range(1, 36)
    ]


def _make_65_reps():
    return [
        _make_legislator(
            id_=f"ocd-person/rep-{i:03d}",
            name=f"Rep {i}",
            chamber="house",
            district=i,
        )
        for i in range(1, 66)
    ]


# ---------------------------------------------------------------------------
# Tests: validate_legislators
# ---------------------------------------------------------------------------

class TestValidateLegislators(unittest.TestCase):

    def test_valid_data_returns_no_errors(self):
        """35 senators with all required fields should produce no errors."""
        data = _make_35_senators()
        errors = validate_legislators(data, expected_count=35)
        self.assertEqual(errors, [], msg=f"Expected no errors, got: {errors}")

    def test_valid_65_house_returns_no_errors(self):
        """65 reps with all required fields should produce no errors."""
        data = _make_65_reps()
        errors = validate_legislators(data, expected_count=65)
        self.assertEqual(errors, [], msg=f"Expected no errors, got: {errors}")

    def test_wrong_count_raises_error(self):
        """Fewer legislators than expected_count must produce an error."""
        data = _make_35_senators()[:30]  # only 30 of 35
        errors = validate_legislators(data, expected_count=35)
        self.assertTrue(
            any("35" in e for e in errors),
            msg=f"Expected count error mentioning 35, got: {errors}",
        )

    def test_missing_required_field_id(self):
        """Legislator missing 'id' field must produce an error."""
        data = _make_35_senators()
        del data[0]["id"]
        errors = validate_legislators(data, expected_count=35)
        self.assertTrue(
            any("id" in e.lower() for e in errors),
            msg=f"Expected 'id' field error, got: {errors}",
        )

    def test_missing_required_field_name(self):
        """Legislator missing 'name' field must produce an error."""
        data = _make_35_senators()
        del data[0]["name"]
        errors = validate_legislators(data, expected_count=35)
        self.assertTrue(
            any("name" in e.lower() for e in errors),
            msg=f"Expected 'name' field error, got: {errors}",
        )

    def test_missing_required_field_party(self):
        """Legislator missing 'party' field must produce an error."""
        data = _make_35_senators()
        del data[0]["party"]
        errors = validate_legislators(data, expected_count=35)
        self.assertTrue(
            any("party" in e.lower() for e in errors),
            msg=f"Expected 'party' field error, got: {errors}",
        )

    def test_missing_required_field_chamber(self):
        """Legislator missing 'chamber' field must produce an error."""
        data = _make_35_senators()
        del data[0]["chamber"]
        errors = validate_legislators(data, expected_count=35)
        self.assertTrue(
            any("chamber" in e.lower() for e in errors),
            msg=f"Expected 'chamber' field error, got: {errors}",
        )

    def test_missing_required_field_district(self):
        """Legislator missing 'district' field must produce an error."""
        data = _make_35_senators()
        del data[0]["district"]
        errors = validate_legislators(data, expected_count=35)
        self.assertTrue(
            any("district" in e.lower() for e in errors),
            msg=f"Expected 'district' field error, got: {errors}",
        )

    def test_duplicate_districts_within_chamber(self):
        """Two legislators sharing a district in the same chamber must produce an error."""
        data = _make_35_senators()
        data[1]["district"] = data[0]["district"]  # force duplicate
        errors = validate_legislators(data, expected_count=35)
        self.assertTrue(
            any("duplicate" in e.lower() or "district" in e.lower() for e in errors),
            msg=f"Expected duplicate district error, got: {errors}",
        )

    def test_duplicate_districts_across_chambers_ok(self):
        """District numbers can repeat across chambers — senate 1 and house 1 is fine."""
        senate = [_make_legislator(
            id_=f"ocd-person/sen-{i:03d}", chamber="senate", district=i
        ) for i in range(1, 36)]
        house = [_make_legislator(
            id_=f"ocd-person/rep-{i:03d}", chamber="house", district=i
        ) for i in range(1, 36)]
        # Check senate only — districts 1-35 are all unique within senate
        errors = validate_legislators(senate, expected_count=35)
        self.assertEqual(errors, [], msg=f"Cross-chamber duplicates incorrectly flagged: {errors}")


# ---------------------------------------------------------------------------
# Tests: validate_committees
# ---------------------------------------------------------------------------

class TestValidateCommittees(unittest.TestCase):

    def _make_committee(self, name="Judiciary", member_ids=None):
        member_ids = member_ids or ["ocd-person/test-001"]
        return {
            "name": name,
            "members": [{"id": mid, "name": f"Person {mid}", "role": "member"}
                        for mid in member_ids],
        }

    def test_valid_committee_returns_no_errors(self):
        known_ids = {"ocd-person/test-001", "ocd-person/test-002"}
        committees = [self._make_committee(member_ids=list(known_ids))]
        errors = validate_committees(committees, known_ids)
        self.assertEqual(errors, [], msg=f"Expected no errors, got: {errors}")

    def test_committee_missing_name(self):
        known_ids = {"ocd-person/test-001"}
        committees = [{"members": [{"id": "ocd-person/test-001", "role": "member"}]}]
        errors = validate_committees(committees, known_ids)
        self.assertTrue(
            any("name" in e.lower() for e in errors),
            msg=f"Expected name error, got: {errors}",
        )

    def test_orphaned_member_reference(self):
        """Member ID not in known_legislator_ids must produce an error."""
        known_ids = {"ocd-person/test-001"}
        committees = [self._make_committee(member_ids=["ocd-person/GHOST-999"])]
        errors = validate_committees(committees, known_ids)
        self.assertTrue(
            any("ocd-person/GHOST-999" in e or "unknown" in e.lower() or "orphan" in e.lower()
                for e in errors),
            msg=f"Expected orphaned member error, got: {errors}",
        )

    def test_multiple_committees_one_bad_member(self):
        """Only the committee with the bad member should produce an error."""
        known_ids = {"ocd-person/test-001"}
        good = self._make_committee(name="Good Committee", member_ids=["ocd-person/test-001"])
        bad = self._make_committee(name="Bad Committee", member_ids=["ocd-person/GHOST-999"])
        errors = validate_committees([good, bad], known_ids)
        self.assertTrue(len(errors) >= 1)
        # Good committee should not appear in errors
        self.assertFalse(any("Good Committee" in e for e in errors))


# ---------------------------------------------------------------------------
# Tests: validate_bills
# ---------------------------------------------------------------------------

class TestValidateBills(unittest.TestCase):

    def _make_bill(self, id_="HB1001", title="Test Bill", votes=None):
        if votes is None:
            votes = []
        return {"id": id_, "title": title, "votes": votes}

    def _make_vote(self, yes=2, no=1, roll_call=None):
        if roll_call is None:
            roll_call = [
                {"id": "ocd-person/test-001", "vote": "yes"},
                {"id": "ocd-person/test-002", "vote": "yes"},
                {"id": "ocd-person/test-003", "vote": "no"},
            ]
        return {
            "yes": yes,
            "no": no,
            "roll_call": roll_call,
        }

    def test_valid_bill_returns_no_errors(self):
        bills = [self._make_bill(votes=[self._make_vote()])]
        errors = validate_bills(bills)
        self.assertEqual(errors, [], msg=f"Expected no errors, got: {errors}")

    def test_bill_missing_id(self):
        bills = [{"title": "No ID Bill", "votes": []}]
        errors = validate_bills(bills)
        self.assertTrue(
            any("id" in e.lower() for e in errors),
            msg=f"Expected 'id' error, got: {errors}",
        )

    def test_bill_missing_title(self):
        bills = [{"id": "HB9999", "votes": []}]
        errors = validate_bills(bills)
        self.assertTrue(
            any("title" in e.lower() for e in errors),
            msg=f"Expected 'title' error, got: {errors}",
        )

    def test_vote_counts_match_roll_call(self):
        """Yes/no counts that match roll call entries should produce no errors."""
        roll_call = [
            {"id": "ocd-person/a", "vote": "yes"},
            {"id": "ocd-person/b", "vote": "yes"},
            {"id": "ocd-person/c", "vote": "no"},
        ]
        vote = {"yes": 2, "no": 1, "roll_call": roll_call}
        bills = [self._make_bill(votes=[vote])]
        errors = validate_bills(bills)
        self.assertEqual(errors, [], msg=f"Expected no errors, got: {errors}")

    def test_vote_yes_count_mismatch(self):
        """Declared yes count > actual yes votes in roll call must produce an error."""
        roll_call = [
            {"id": "ocd-person/a", "vote": "yes"},
            {"id": "ocd-person/b", "vote": "no"},
        ]
        vote = {"yes": 5, "no": 1, "roll_call": roll_call}  # says 5 yes, roll call has 1
        bills = [self._make_bill(votes=[vote])]
        errors = validate_bills(bills)
        self.assertTrue(
            any("yes" in e.lower() or "mismatch" in e.lower() or "count" in e.lower()
                for e in errors),
            msg=f"Expected vote count mismatch error, got: {errors}",
        )

    def test_vote_no_count_mismatch(self):
        """Declared no count > actual no votes in roll call must produce an error."""
        roll_call = [
            {"id": "ocd-person/a", "vote": "yes"},
            {"id": "ocd-person/b", "vote": "no"},
        ]
        vote = {"yes": 1, "no": 10, "roll_call": roll_call}  # says 10 no, roll call has 1
        bills = [self._make_bill(votes=[vote])]
        errors = validate_bills(bills)
        self.assertTrue(
            any("no" in e.lower() or "mismatch" in e.lower() or "count" in e.lower()
                for e in errors),
            msg=f"Expected vote count mismatch error, got: {errors}",
        )


if __name__ == "__main__":
    unittest.main()
