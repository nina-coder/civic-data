# Contributing to Colorado Civic Data

Thanks for your interest in contributing. Here's how to help.

## Adding Support for Other States

This repo is structured so that adding a new state is straightforward.

1. **Fork and clone** the repo.
2. **Get API keys.** You'll need an [OpenStates API key](https://openstates.org/accounts/signup/) and optionally a [LegiScan API key](https://legiscan.com/legiscan). Add them to your `.env` (copy `.env.example` to start).
3. **Run the sync script** for your state:
   ```bash
   python scripts/sync.py --state XX
   ```
   Replace `XX` with the two-letter state abbreviation (e.g., `WY`, `MT`, `AZ`).
4. **Validate the output.** Run the validation script to catch missing fields, broken district references, or schema mismatches:
   ```bash
   python scripts/validate.py --state XX
   ```
5. **Open a pull request.** Include the new data files and any template or script changes needed to support the state.

If you're adding a state that uses a non-standard chamber structure (unicameral, territories, etc.), open an issue first to discuss the approach.

---

## Fixing Data Errors

Before filing a data fix, check the upstream source:

- **Legislator info** (name, party, district) — check [OpenStates](https://openstates.org/) and your state's official legislature website. If OpenStates is wrong, consider filing a correction there too.
- **Bill text and vote records** — check [LegiScan](https://legiscan.com/) or your state legislature's official bill tracker.
- **District boundaries** — sourced from [Census TIGER](https://www.census.gov/geographies/mapping-files/time-series/geo/tiger-line-file.html). Boundary errors should be reported to the Census Bureau.

If the error is in how this repo processed or transformed the data, open a PR with the fix and a clear explanation of what was wrong.

---

## Reporting Issues

Use [GitHub Issues](https://github.com/nina-coder/civic-data/issues) to report:

- **Data errors** — wrong legislator info, missing votes, stale committee assignments
- **Site bugs** — broken address lookup, display errors, mobile layout issues
- **Script errors** — sync failures, validation false positives/negatives

Please include:
- What you expected to see
- What you actually saw
- Steps to reproduce (for bugs) or a source link (for data errors)

---

## Code Style

- Python: standard library preferred, PEP 8 formatting
- No new dependencies without discussion in an issue first
- Tests live in `tests/` — run with `pytest` before submitting a PR
