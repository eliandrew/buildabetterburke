# Customer-request hotspots near the Burke-Gilman

The [request hot spots page](../hotspots.html) summarizes **reports near existing Seattle trail segments**, grouped into the map's eight approximate areas. It defaults to public Find It, Fix It app requests created in the latest 365 days of the supplied export, **November 15, 2025–November 14, 2026**. It is a measure of reporting activity, not verified trail defects, unique incidents, safety, or maintenance responsibility.

## Source and scope

- Local export: `Customer_Service_Requests_20261114.csv`, 770,116,242 bytes; **2,553,664 rows**, created January 1, 2013–November 14, 2026.
- [City of Seattle Customer Service Requests](https://data.seattle.gov/City-Administration/Customer-Service-Requests/5ngg-rpne), dataset `5ngg-rpne`.
- [Official metadata PDF](https://data.seattle.gov/api/views/5ngg-rpne/files/1689147e-c729-473f-9159-930ee14c8918?download=true&filename=Customer_Service_Requests_metadata.pdf), updated July 15, 2025.
- **78,160 rows (3.06%)** have missing/non-numeric coordinates and cannot be spatially matched. The source has no invalid created dates or out-of-range numeric coordinates.
- Exact public app channel: `Method Received = Find It Fix It Apps`. The metadata identifies `PremierOne CSR Mobile Apps` as **City staff intake**, and `Citizen Web` / `Citizen Web Intake App` as the public web portal. “All intake channels” includes public web/phone, City staff, and other sources.
- The export has no report narrative, photo, closure date, or resolution detail. `Status` is the current snapshot status; “Closed” does not prove that an issue was fixed.

The official metadata notes that requests can be copied into new request types for departmental routing, categories and intake systems change over time, and some departments use other systems. Distinct request IDs may therefore concern the same issue. Records marked as duplicates remain part of reporting volume. An independent streaming scan found no repeated IDs in this particular export.

## Spatial method

The pipeline uses the reviewed [official trail-centerline snapshot](trail-corridor.geojson), documented in [TRAIL_GEOMETRY.md](TRAIL_GEOMETRY.md). It includes 22.370 km of existing Seattle mainline in two disconnected components. It excludes the Ballard Missing Link gap, access spurs, and non-Seattle trail. Missing coverage is not evidence of zero reports.

Each valid request coordinate is assigned once to the nearest centerline segment when its distance is within approximately **50 meters**. Distances use a local equirectangular projection centered at 47.68° N, 122.33° W with spherical Earth radius 6,371,008.8 m. This dependency-free local approximation is appropriate to an orientation map; it does not establish surveyed boundaries. Nearby roads, parks, properties, or campus reports can lie inside the corridor. Area lengths use the supplied official state-plane geometry in EPSG:2926, converted from US survey feet, without inventing length across gaps.

The eight area boundaries are approximate groupings aligned with the existing PDF map. The Ballard group contains both the western component and the initial part of the eastern component. Its representative marker summarizes that entire group. Report counts are not allocated to individual ownership sections, landowners, or maintenance agencies.

## Snapshot results

The full export contains **46,146 requests within 50 m**, across all years and intake channels. The latest 365-day period contains **5,875 public app requests** plus **1,015 requests from other intake channels**. App reporting volume by area is:

| Approximate map area | App requests | Mapped km | Requests / km |
| --- | ---: | ---: | ---: |
| Golden Gardens & Ballard | 3,086 | 4.124 | 748.4 |
| Fremont & the canal | 839 | 2.074 | 404.5 |
| Wallingford & Northlake | 470 | 1.796 | 261.7 |
| Ravenna & Bryant | 452 | 2.328 | 194.2 |
| Matthews Beach corridor | 373 | 2.314 | 161.2 |
| University of Washington | 329 | 2.845 | 115.6 |
| Sand Point corridor | 210 | 3.113 | 67.5 |
| North Seattle & map edge | 116 | 3.777 | 30.7 |

Requests per kilometer account for unequal mapped area lengths. They do not adjust for trail use, adjacent population, repeated reporters, or likelihood of reporting. Categories retain exact source names to avoid silently merging historical or different service types.

The choice of corridor matters: the same latest-period public app totals are **3,259 at 25 m**, **5,875 at 50 m**, and **8,286 at 100 m**. The 50 m view is a practical nearby-trail filter, not proof that every included request is on the trail. Sensitivity totals are retained in the generated metadata.

The current year and latest source day may be incomplete. The City describes daily refreshes through the previous day, while this particular export contains records dated November 14; the page uses the observed date range without claiming that day is final.

## Reproduce the aggregate

The builder uses Python's standard library and streams the input CSV. It holds only nearby request IDs for deduplication and anonymous daily aggregate counters in memory; it never loads or copies the full CSV into the repository. Its spatial grid filters against individual line segments and preserves disconnected trail gaps. Among valid candidate records within the 100 m sensitivity corridor, exact repeats are counted once and conflicting records sharing an ID stop the build for source review. Rows outside that corridor or with unusable dates or coordinates are not part of this duplicate check. The optional independent audit below checks IDs across the complete export.

From the repository root:

```sh
python3 scripts/build-request-hotspots.py ~/Downloads/Customer_Service_Requests_20261114.csv
python3 -m unittest discover -s scripts -p 'test_*.py' -v
```

The builder writes deterministic `request-hotspots.json` and `request-hotspots.js` (~160 KB each). The JavaScript wrapper supports the existing static HTML page, including local file access; JSON is available for downloading and independent analysis. Only category/status counts are published—no report IDs, addresses, or precise request locations. Input and geometry SHA-256 hashes are stored in the output. The supplied CSV hash is `9b7dc9133719a8d2d4b153cabb34004abbe6c553cfc3149ea71f8d835bb5da5d`.

Sparse aggregate rows use this schema:

```text
[areaId, periodId, channel, requestType, snapshotStatus, count]
```

`channel` is either `app` or `other`; these are mutually exclusive. Sum both for all intake channels. Periods overlap intentionally: select exactly one of `recent`, the latest year, the preceding year, or `all` before summing. The `recent` period is anchored to the last valid created date in the entire source, including records without usable coordinates, rather than to the system clock. Every source category and status remains available within each populated area/period/channel combination.

Tests cover 50 m inclusion/exclusion, distances beyond segment endpoints, no bridge across synthetic or actual trail gaps, nearest-area assignment, stable boundary ties, inclusive date windows, public-app versus staff channels, duplicate handling, invalid coordinates/dates, and absence of raw report fields in published output.

The same test command also checks the shipped artifacts: the browser JavaScript and downloadable JSON agree, geometry hashes and area lengths match the map, aggregate keys are unique, sensitivity totals reconcile, and the public methodology page describes the current default period and totals. These checks run without the original CSV or network access.

To verify a full rebuild without replacing the map's data:

```sh
python3 scripts/build-request-hotspots.py ~/Downloads/Customer_Service_Requests_20261114.csv --output-dir /tmp/burke-request-rebuild-validation
cmp burke-gilman/data/request-hotspots.json /tmp/burke-request-rebuild-validation/request-hotspots.json
cmp burke-gilman/data/request-hotspots.js /tmp/burke-request-rebuild-validation/request-hotspots.js
```

Both comparisons should exit successfully with no output for this source snapshot. When refreshing the source intentionally, review the changed aggregates and update the public methodology page before treating a changed output as ready to publish.

For an independent full-CSV recount, the optional checker uses Shapely/GEOS instead of the builder's spatial index. It imports no builder code, verifies every aggregate and sensitivity count, checks IDs across the whole source, and compares the documented distance approximation against an ellipsoidal metric reference. Install its dependencies in a separate environment:

```sh
python3 -m venv /tmp/burke-audit-venv
/tmp/burke-audit-venv/bin/python -m pip install -r scripts/requirements-request-audit.txt
/tmp/burke-audit-venv/bin/python scripts/verify_request_counts.py ~/Downloads/Customer_Service_Requests_20261114.csv
```

Run these commands from the repository root. The checker exits 0 when the artifacts match, 1 for discrepancies, and 2 for unusable input. It prints aggregate results; use its optional --json-output argument to save the details outside the repository. These GIS dependencies are not needed to build or view the map, or to run the regular unit tests.
