# Colorado Civic Data

Find your Colorado state legislators, see their committees, and track how they vote.

**Live site:** [nina-coder.github.io/colorado-civic-data](https://nina-coder.github.io/colorado-civic-data)

---

## What This Is

A structured, open dataset of the Colorado General Assembly — updated each session — plus a static site that lets anyone look up their legislators by address.

The data includes:

- **100 legislators** — all 65 House members and 35 Senate members, with party, district, contact info, and photo links
- **Committees** — membership rosters and chair assignments for all standing committees in both chambers
- **Bills + votes** — introduced bills with full vote records broken down by legislator
- **District boundaries** — GeoJSON files for all 100 legislative districts, sourced from Census TIGER

All data files are in YAML and GeoJSON, easy to read and import.

---

## Use the Data

Clone the repo and explore the YAML files directly:

```bash
git clone https://github.com/nina-coder/colorado-civic-data.git
cd colorado-civic-data
```

Legislators are in `data/legislators/`, one file per chamber:

```bash
ls data/legislators/
# house.yaml  senate.yaml

head -30 data/legislators/house.yaml
```

Committee rosters are in `data/committees/`, bills in `data/bills/`, and district boundaries in `data/districts/`.

---

## Run Locally

1. **Install dependencies:**
   ```bash
   python3 -m venv venv
   source venv/bin/activate
   pip install -r requirements.txt
   ```

2. **Set up API keys:**
   ```bash
   cp .env.example .env
   # Edit .env and add your OpenStates and LegiScan API keys
   ```

3. **Sync data from upstream sources:**
   ```bash
   python scripts/sync.py
   ```

4. **Build the static site:**
   ```bash
   python scripts/build.py
   ```

5. **Open the site:**
   ```bash
   open docs/index.html
   # or: python -m http.server --directory docs
   ```

---

## Data Sources

| Source | What it provides | License |
|--------|-----------------|---------|
| [OpenStates](https://openstates.org/) | Legislators, committees, bills | [CC BY 4.0](https://creativecommons.org/licenses/by/4.0/) |
| [LegiScan](https://legiscan.com/) | Vote records, bill text | Free tier, attribution required |
| [Census TIGER](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html) | District boundaries | Public domain |
| [Census Geocoder](https://geocoding.geo.census.gov/) | Address-to-district lookup | Public domain |

---

## License

Code: [MIT](LICENSE-CODE) — Copyright 2026 Nina Rivera

Data: [CC BY 4.0](LICENSE-DATA) — Copyright 2026 Nina Rivera. Underlying source data is subject to the terms of each upstream provider (see table above).

---

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for how to add states, fix data errors, or report issues.
