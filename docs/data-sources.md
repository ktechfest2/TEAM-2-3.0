# Data sources

VoteTrace does not ship any INEC data. By default (`DIRECTORY_SOURCE=database`) the directory starts empty and is filled by administrators: they import the polling-unit register from the official file, configure the elections they observe, and publish updates. A clearly labelled demonstration dataset remains available for tests and walkthroughs.

## The demonstration dataset

`backend/app/directory/demo_data.py` is served only when `DIRECTORY_SOURCE=demo`. Production refuses to start with it.

| What | Real or fictional |
| --- | --- |
| State names (FCT, Lagos, Kano) | Real names only. Codes are placeholders. |
| LGA names (two per state) | Real names only. Codes are placeholders. |
| Wards | Fictional: "Ward A" and "Ward B". |
| Polling units | Fictional: codes start with `DEMO-` and names end with "(fictional)". |
| Addresses | Fictional placeholder text, or missing. |
| Coordinates | Fictional offsets from an approximate LGA centre, marked `precision: "demo_approximate"`. A third of the units have none. |
| Relocation and closure notices | Fictional. Each source reads "Demonstration notice (not an INEC announcement)". |
| Election updates | Fictional, with `is_demo: true`. |

Every API response carries `data_source` (`kind: "demo"` and a description) and `generated_at`. The interface shows a one-line "Sample directory, not sourced from INEC." note wherever `kind` is `demo`, and a note on the map that positions are approximate.

The dataset covers each status at least once, so the interface can be tested: active, relocation reported (three crowd reports, no notice), officially relocated (confirmed notice with reference and effective date), temporarily unavailable (notice with no source, so "Official confirmation unavailable."), and information pending verification (no source).

## The imported register

`DIRECTORY_SOURCE=database` serves `DatabaseDirectoryRepository` (`app/directory/database.py`) from the same database as evidence (Postgres, or the SQLite development file). Responses carry `data_source.label: "Imported register"`, and each unit names the source it was imported from. Imported coordinates are marked `precision: "source_reported"`, never `surveyed`.

Load the register in the admin console (**Elections and register**, then **Import from CSV**) or from the command line:

```bash
cd backend && .venv/bin/python -m app.directory.import_csv polling-units.csv \
  --source "INEC polling units, <publication>" --reference "<URL or document reference>"
```

Columns (header names are case-insensitive): `state`, `lga`, `ward`, `polling_unit_code`, `polling_unit_name`, and optionally `state_code`, `lga_code`, `ward_code`, `address`, `latitude`, `longitude` and `registered_voters`. Codes are derived from INEC-style unit codes (`SS-LL-WW-PPP`) when the code columns are missing. The whole file is validated first and one bad row rejects it, so the directory never holds half a register. **Check file** (or `--dry-run`) validates without writing. Units are matched by code and updated in place, so evidence linked to them stays valid across corrected re-imports. Every import is recorded in the audit log with the file's SHA-256.

Elections are created under **Elections** in the same page: name, the election label printed on the result sheet, date, result-sheet template and the parties on the ballot in ballot order. Once evidence exists for an election, its label, template and parties are locked.

### Required fields from an authoritative register

For each polling unit:

- the full delimitation code (state, LGA, registration area and unit), with names for each level;
- the official polling-unit name;
- the address or location description, as published;
- coordinates, if published, with their precision or survey method. VoteTrace must not geocode addresses and present the result as official;
- the publisher, the dataset version or publication reference, and its publication date (`source_name`, `source_reference`, `source_updated_at`);
- the licence or terms that permit redistribution.

For each relocation or closure notice:

- the issuing authority (`source_name`) and a document reference or URL;
- the new location, if any;
- the effective date, and the date VoteTrace received the notice;
- the verification status assigned by an election administrator.

### Where it would be stored

`polling_units` (with `status`, `address_description`, `source_name`, `source_reference`, `source_updated_at`), `polling_unit_notices`, `relocation_reports` and `election_updates`. These are all created by revision `0001_initial`. A unit may be marked `officially_relocated` only when it has an `officially_confirmed` relocation notice that names a source. The API schema enforces this.

## Crowd reports versus official notices

`relocation_reports` holds reports from the public. They are counted and shown as "Relocation reported" with "Official confirmation unavailable." They are never copied into `polling_unit_notices`, and they never change a unit to `officially_relocated`. Only an election administrator recording an authoritative source can do that, and that write path is not built yet (notices can be inserted directly in the database by an administrator).

## Election updates

Publishing is `POST /api/v1/admin/updates`, restricted to `election_admin` and `system_admin`. An `officially_confirmed` update must cite a reference or an HTTPS source URL. With the database directory the update is stored, appears on the public Updates page and in USSD and SMS, and is written to the audit log. The admin console has a form for it (**Elections and register**, then **Updates**). Under the demo directory the endpoint validates and authorizes the request, then returns `503 persistence_unavailable`.

## Demonstration results

`python -m app.analytics.demo_seed` creates fictional submissions for the "Presidential Election 2027 (sample)" through the real evidence pipeline. Figures are generated and labelled "Sample data. Not an official election result." in every API response. Nothing in the API or UI hardcodes result totals. See [results-aggregation.md](results-aggregation.md#demonstration-dataset).

The demo directory now has uneven polling-unit counts per ward (44 units in 15 wards) and real ISO 3166-2 state codes. Every third unit in a ward (10 of 44) deliberately has no coordinates or address, to exercise the "incomplete location record" alert. No coordinates or addresses were invented for them.

## State boundaries

The results map uses **geoBoundaries gbOpen NGA ADM1** (source: GRID3), CC BY 4.0, simplified with `scripts/simplify_boundaries.py` and stored at `frontend/public/geo/nigeria-states.geojson`. These are real administrative boundaries, simplified for display only. LGA and ward boundaries are not included, and none were invented.

## Map tiles

The map uses OpenStreetMap's public tile server (`tile.openstreetmap.org`) with attribution, and loads only when the user selects "Show map". The OSM [tile usage policy](https://operations.osmfoundation.org/policies/tiles/) does not allow heavy production traffic. Before launch, switch to a commercial tile provider or a self-hosted tile server, and update `TILE_URL` in `frontend/src/features/polling-units/polling-unit-map.tsx`. Tiles are not cached offline. When offline, the interface lists units instead of showing a map.
