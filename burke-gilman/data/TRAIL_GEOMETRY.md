# Trail geometry and approximate map areas

The request corridor uses the City of Seattle's **SDOT Bike Facilities → Multi-use Trails (Seattle Only)** GIS layer, downloaded on November 14, 2026. The query selects exactly ORD_STNAME_CONCAT = 'BURKE GILMAN TRL' AND CITYCODE = 1. It returns 64 connected street-network features forming two existing trail components, totaling **22.370 km / 13.900 miles**. The small trail-corridor.geojson snapshot contains all centerline vertices grouped into the page's eight areas, with WGS84 [longitude, latitude] coordinates.

- [Official GIS item and attribution](https://www.arcgis.com/home/item.html?id=bf36bd11b499489d8cc1d491b72eb712)
- [Queryable official layer](https://services.arcgis.com/ZOyb2t4B0UYuYNYH/arcgis/rest/services/SDOT_Bike_Facilities/FeatureServer/1)
- [Seattle Parks trail information](https://www.seattle.gov/parks/parks/burke-gilman-trail)
- [SDOT trail map](https://www.seattle.gov/transportation/projects-and-programs/programs/bike-program/ballard-multimodal-corridor/burke-gilman-trail-map)
- [SDOT Missing Link project](https://www.seattle.gov/transportation/projects-and-programs/programs/bike-program/bgtmissinglink)

## Coverage and interpretation

The western component runs from Golden Gardens to the existing trail endpoint in Ballard. The eastern component starts at 11th Avenue NW and continues through Fremont, UW, and northeast Seattle to the last city-coded trail endpoint near NE 145th Street. These are the two components present in the official inventory; no connecting segment is invented across the **Ballard Missing Link**. Requests beside that gap are outside this analysis, except where they fall within the selected distance of an existing trail endpoint. Absence of a hotspot in the gap means **not analyzed**, not zero reports.

Named access branches (BURKE GILMAN ACCESS TRL, BURKE GILMAN SAND PT TRL) and non-Seattle trail segments are excluded. A request's distance is measured against this real geographic centerline, not against the ownership map drawing. A 50 m corridor can include nearby streets, buildings, and parks; matching reports must be described as **near the trail**, not as confirmed trail defects. Report locations and reporting behavior limit any interpretation of counts as need or safety.

## How the eight areas were aligned

The existing ownership map supplies PDF drawing coordinates and approximate area groups, not a formal geographic projection or official neighborhood boundaries. We aligned its trail paths to the city centerline in Washington North State Plane feet (EPSG:2926), initialized by the three matching endpoints at Golden Gardens, the western Ballard trail end, and the north Seattle trail end. Thirty iterations of least-squares nearest-centerline affine fitting refined the alignment.

The final fit has a **1.43 m median** distance from a PDF vertex to the official centerline, **5.11 m at the 95th percentile**, and **12.36 m maximum**. These describe fit residuals, not survey accuracy or request-location accuracy. Each existing area boundary was transformed and snapped to the nearest position along the ordered official eastern mainline. All seven boundary offsets are under 3 m. The fixed transformation, original endpoint controls, and PDF area-boundary coordinates are retained in scripts/trail-corridor-config.json; each final geographic split is also recorded in the GeoJSON metadata.

| Area | Existing map sections | Approximate trail length |
| --- | --- | ---: |
| Golden Gardens & Ballard | 01–02 | 4.124 km |
| Fremont & the canal | 03–14 | 2.074 km |
| Wallingford & Northlake | 15–18 | 1.796 km |
| University of Washington | 19–27 | 2.845 km |
| Ravenna & Bryant | 28–37 | 2.328 km |
| Sand Point corridor | 38–45 | 3.113 km |
| Matthews Beach corridor | 46–53 | 2.314 km |
| North Seattle & map edge | 54–62 | 3.777 km |

These intentionally preserve the page's approximate group names and boundaries. For example, the Ballard group includes the western component and the beginning of the eastern component. Its map marker is a representative point on the western component, not the location of all reports assigned to it. Area markers must summarize the whole group; they must not be presented as exact report clusters. Aggregation by nearest mainline segment gives each report one area even near a group boundary.

## Refreshing

Run python3 scripts/prepare_trail_corridor.py from any directory. The script uses only Python's standard library, fetches the current official centerline in EPSG:2926 and WGS84, applies the reviewed area configuration, verifies topology and complete source coverage, and writes burke-gilman/data/trail-corridor.geojson. Changed source feature counts or disconnected topology stop the script for review. Re-run the request aggregation after refreshing the geometry. The stored snapshot is sufficient to reproduce request filtering without another GIS download.

The pdfAnchor properties give representative coordinates on the existing page drawing. They are suitable for labeled area summaries. They should not be used to imply precise reported-incident locations or parcel ownership.

## Reporting and data links

- [Customer Service Requests dataset](https://data.seattle.gov/City-Administration/Customer-Service-Requests/5ngg-rpne)
- [Find It, Fix It app and reporting guidance](https://www.seattle.gov/customer-service-bureau/find-it-fix-it-mobile-app)

All links above returned HTTP 200 on November 14, 2026. The older Seattle Parks /parks/allparks/burke-gilman-trail URL redirects to the /parks/parks/ URL used here.
