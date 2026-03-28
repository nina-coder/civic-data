"""Tests for scripts/build.py — Colorado Civic Data static site builder."""

import json
import sys
import unittest
from pathlib import Path

import yaml

# Ensure scripts/ is importable
sys.path.insert(0, str(Path(__file__).parent.parent))

from scripts.build import load_all_data, generate_json


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_legislator(id_="ocd-person/aaaa-0001", name="Test Person",
                     party="Democratic", chamber="senate", district=1):
    return {
        "id": id_,
        "name": name,
        "given_name": "Test",
        "family_name": "Person",
        "party": party,
        "chamber": chamber,
        "district": district,
        "committees": [],
        "social": {},
    }


def _make_committee(name="Judiciary", chamber="senate"):
    return {
        "name": name,
        "chamber": chamber,
        "members": [{"id": "ocd-person/aaaa-0001", "name": "Test Person", "role": "member"}],
    }


def _make_bill(id_="HB1001", title="Test Bill"):
    return {
        "id": id_,
        "title": title,
        "subjects": ["Education"],
        "sponsors": [{"name": "Test Person", "id": "ocd-person/aaaa-0001", "type": "primary"}],
        "status": "Introduced",
        "text_url": "",
        "votes": [],
    }


def _write_yaml(path: Path, data) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        yaml.dump(data, fh, allow_unicode=True, default_flow_style=False, sort_keys=False)


# ---------------------------------------------------------------------------
# Tests: load_all_data
# ---------------------------------------------------------------------------

class TestLoadAllData(unittest.TestCase):
    """Verify load_all_data merges YAML from multiple files correctly."""

    def setUp(self):
        """Build a minimal data directory tree in a temp location."""
        import tempfile
        self._tmpdir = tempfile.TemporaryDirectory()
        self.data_dir = Path(self._tmpdir.name)

        # legislators/senate.yaml — 2 senators
        self.senators = [
            _make_legislator(id_="ocd-person/sen-001", chamber="senate", district=1),
            _make_legislator(id_="ocd-person/sen-002", chamber="senate", district=2),
        ]
        _write_yaml(self.data_dir / "legislators" / "senate.yaml", self.senators)

        # legislators/house.yaml — 1 rep
        self.reps = [
            _make_legislator(id_="ocd-person/rep-001", chamber="house", district=1),
        ]
        _write_yaml(self.data_dir / "legislators" / "house.yaml", self.reps)

        # committees/senate.yaml
        self.senate_comms = [_make_committee("Finance", "senate")]
        _write_yaml(self.data_dir / "committees" / "senate.yaml", self.senate_comms)

        # committees/house.yaml
        self.house_comms = [_make_committee("Judiciary", "house")]
        _write_yaml(self.data_dir / "committees" / "house.yaml", self.house_comms)

        # bills/2025.yaml
        self.bills_2025 = [_make_bill("HB1001", "School Funding")]
        _write_yaml(self.data_dir / "bills" / "2025.yaml", self.bills_2025)

        # bills/2026.yaml
        self.bills_2026 = [_make_bill("HB2001", "Climate Bill")]
        _write_yaml(self.data_dir / "bills" / "2026.yaml", self.bills_2026)

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_returns_dict_with_expected_keys(self):
        data = load_all_data(self.data_dir)
        self.assertIn("legislators", data)
        self.assertIn("committees", data)
        self.assertIn("bills", data)

    def test_legislators_merged_from_senate_and_house(self):
        """Senate + house files should be combined into one flat list."""
        data = load_all_data(self.data_dir)
        self.assertEqual(len(data["legislators"]), 3)

    def test_legislators_contains_both_chambers(self):
        data = load_all_data(self.data_dir)
        chambers = {leg["chamber"] for leg in data["legislators"]}
        self.assertIn("senate", chambers)
        self.assertIn("house", chambers)

    def test_senator_ids_present(self):
        data = load_all_data(self.data_dir)
        ids = {leg["id"] for leg in data["legislators"]}
        self.assertIn("ocd-person/sen-001", ids)
        self.assertIn("ocd-person/sen-002", ids)
        self.assertIn("ocd-person/rep-001", ids)

    def test_committees_merged_from_all_files(self):
        """All committee YAML files should be merged into one flat list."""
        data = load_all_data(self.data_dir)
        self.assertEqual(len(data["committees"]), 2)

    def test_committee_names_present(self):
        data = load_all_data(self.data_dir)
        names = {c["name"] for c in data["committees"]}
        self.assertIn("Finance", names)
        self.assertIn("Judiciary", names)

    def test_bills_keyed_by_session(self):
        """Bills should be a dict keyed by session string."""
        data = load_all_data(self.data_dir)
        self.assertIsInstance(data["bills"], dict)
        self.assertIn("2025", data["bills"])
        self.assertIn("2026", data["bills"])

    def test_bills_2025_content(self):
        data = load_all_data(self.data_dir)
        self.assertEqual(len(data["bills"]["2025"]), 1)
        self.assertEqual(data["bills"]["2025"][0]["id"], "HB1001")

    def test_bills_2026_content(self):
        data = load_all_data(self.data_dir)
        self.assertEqual(len(data["bills"]["2026"]), 1)
        self.assertEqual(data["bills"]["2026"][0]["id"], "HB2001")

    def test_empty_legislators_dir_returns_empty_list(self):
        """If senate.yaml and house.yaml are absent, legislators should be []."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            # Only create an empty legislators dir (no files)
            (tmp_dir / "legislators").mkdir(parents=True)
            (tmp_dir / "committees").mkdir(parents=True)
            (tmp_dir / "bills").mkdir(parents=True)
            data = load_all_data(tmp_dir)
            self.assertEqual(data["legislators"], [])

    def test_missing_bills_dir_returns_empty_dict(self):
        """If bills/ doesn't exist, bills should be {}."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            tmp_dir = Path(tmp)
            (tmp_dir / "legislators").mkdir(parents=True)
            (tmp_dir / "committees").mkdir(parents=True)
            # Don't create bills/
            data = load_all_data(tmp_dir)
            self.assertEqual(data["bills"], {})

    def test_joint_committee_file_is_also_merged(self):
        """A third committee file (joint.yaml) should also appear in the list."""
        joint_comms = [_make_committee("Economic & Business Development", "joint")]
        _write_yaml(self.data_dir / "committees" / "joint.yaml", joint_comms)
        data = load_all_data(self.data_dir)
        self.assertEqual(len(data["committees"]), 3)
        names = {c["name"] for c in data["committees"]}
        self.assertIn("Economic & Business Development", names)


# ---------------------------------------------------------------------------
# Tests: generate_json
# ---------------------------------------------------------------------------

class TestGenerateJson(unittest.TestCase):
    """Verify generate_json writes valid, complete JSON files."""

    def setUp(self):
        import tempfile
        self._tmpdir = tempfile.TemporaryDirectory()
        self.output_dir = Path(self._tmpdir.name)

        self.data = {
            "legislators": [
                _make_legislator("ocd-person/sen-001", "Alice Adams", chamber="senate", district=1),
                _make_legislator("ocd-person/rep-001", "Bob Brown", chamber="house", district=5),
            ],
            "committees": [
                _make_committee("Finance", "senate"),
                _make_committee("Judiciary", "house"),
            ],
            "bills": {
                "2025": [_make_bill("HB1001", "Education Act")],
                "2026": [_make_bill("SB2001", "Water Rights")],
            },
        }

    def tearDown(self):
        self._tmpdir.cleanup()

    def test_legislators_json_created(self):
        generate_json(self.data, self.output_dir)
        self.assertTrue((self.output_dir / "data" / "legislators.json").exists())

    def test_committees_json_created(self):
        generate_json(self.data, self.output_dir)
        self.assertTrue((self.output_dir / "data" / "committees.json").exists())

    def test_bills_json_created(self):
        generate_json(self.data, self.output_dir)
        self.assertTrue((self.output_dir / "data" / "bills.json").exists())

    def test_legislators_json_is_valid(self):
        generate_json(self.data, self.output_dir)
        path = self.output_dir / "data" / "legislators.json"
        with open(path, encoding="utf-8") as fh:
            loaded = json.load(fh)
        self.assertIsInstance(loaded, list)

    def test_legislators_json_count(self):
        generate_json(self.data, self.output_dir)
        path = self.output_dir / "data" / "legislators.json"
        loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(loaded), 2)

    def test_committees_json_count(self):
        generate_json(self.data, self.output_dir)
        path = self.output_dir / "data" / "committees.json"
        loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertEqual(len(loaded), 2)

    def test_bills_json_is_flat_array(self):
        """All bills from all sessions should be flattened into one array."""
        generate_json(self.data, self.output_dir)
        path = self.output_dir / "data" / "bills.json"
        loaded = json.loads(path.read_text(encoding="utf-8"))
        self.assertIsInstance(loaded, list)
        self.assertEqual(len(loaded), 2)

    def test_bills_json_has_session_field(self):
        """Each bill in bills.json must carry a 'session' field."""
        generate_json(self.data, self.output_dir)
        path = self.output_dir / "data" / "bills.json"
        loaded = json.loads(path.read_text(encoding="utf-8"))
        for bill in loaded:
            self.assertIn("session", bill, msg=f"Bill missing 'session': {bill}")

    def test_bills_session_values_correct(self):
        """The session field should match the key the bill came from."""
        generate_json(self.data, self.output_dir)
        path = self.output_dir / "data" / "bills.json"
        loaded = json.loads(path.read_text(encoding="utf-8"))
        sessions = {b["session"] for b in loaded}
        self.assertIn("2025", sessions)
        self.assertIn("2026", sessions)

    def test_legislators_json_preserves_fields(self):
        """Legislators JSON should preserve id, name, chamber, district."""
        generate_json(self.data, self.output_dir)
        path = self.output_dir / "data" / "legislators.json"
        loaded = json.loads(path.read_text(encoding="utf-8"))
        alice = next(l for l in loaded if l["id"] == "ocd-person/sen-001")
        self.assertEqual(alice["name"], "Alice Adams")
        self.assertEqual(alice["chamber"], "senate")
        self.assertEqual(alice["district"], 1)

    def test_output_dir_created_if_missing(self):
        """generate_json should create docs/data/ even if output_dir doesn't exist."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            new_out = Path(tmp) / "new_output"
            generate_json(self.data, new_out)
            self.assertTrue((new_out / "data" / "legislators.json").exists())

    def test_empty_data_writes_empty_arrays(self):
        """An empty data dict should produce empty JSON arrays."""
        empty = {"legislators": [], "committees": [], "bills": {}}
        generate_json(empty, self.output_dir)
        for filename in ("legislators.json", "committees.json", "bills.json"):
            path = self.output_dir / "data" / filename
            loaded = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(loaded, [])


if __name__ == "__main__":
    unittest.main()
