#!/usr/bin/env python3
"""Stream Seattle's request export into anonymous Burke-Gilman area aggregates.

Only the Python standard library is required. The source CSV stays outside the
repository. Run with --help for paths; use unittest discovery for pipeline tests.
"""

import argparse
import csv
import hashlib
import json
import math
from collections import Counter, defaultdict
from datetime import date, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / 'burke-gilman' / 'data'
PUBLIC_APP = 'Find It Fix It Apps'
RADII = (25, 50, 100)
EARTH_RADIUS = 6371008.8
ORIGIN_LAT = 47.68
ORIGIN_LON = -122.33
DATASET_URL = 'https://data.seattle.gov/City-Administration/Customer-Service-Requests/5ngg-rpne'
METADATA_URL = 'https://data.seattle.gov/api/views/5ngg-rpne/files/1689147e-c729-473f-9159-930ee14c8918?download=true&filename=Customer_Service_Requests_metadata.pdf'
REQUIRED_COLUMNS = {
    'Service Request Number', 'Service Request Type', 'Created Date',
    'Method Received', 'Status', 'Latitude', 'Longitude',
}


def project(lon, lat):
    """Local metric approximation; never project the ownership PDF's pixels."""
    return (EARTH_RADIUS * math.radians(lon - ORIGIN_LON) * math.cos(math.radians(ORIGIN_LAT)),
            EARTH_RADIUS * math.radians(lat - ORIGIN_LAT))


def point_segment_distance_squared(point, start, end):
    dx, dy = end[0] - start[0], end[1] - start[1]
    length_squared = dx * dx + dy * dy
    if not length_squared:
        return (point[0] - start[0]) ** 2 + (point[1] - start[1]) ** 2
    fraction = max(0, min(1, ((point[0] - start[0]) * dx + (point[1] - start[1]) * dy) / length_squared))
    return (point[0] - start[0] - fraction * dx) ** 2 + (point[1] - start[1] - fraction * dy) ** 2


class Corridor:
    """Index individual mainline edges without bridging disconnected features."""

    def __init__(self, geometry, radius=100, cell_size=250):
        self.radius = radius
        self.cell_size = cell_size
        self.edges = []
        self.cells = defaultdict(list)
        self.lengths = Counter()
        for feature in geometry['features']:
            kind = feature['geometry']['type']
            if kind not in ('LineString', 'MultiLineString'):
                raise ValueError('Corridor features must be LineString or MultiLineString')
            area = feature['properties']['areaId']
            coordinates = feature['geometry']['coordinates']
            lines = [coordinates] if kind == 'LineString' else coordinates
            pairs = ((first, second) for line in lines for first, second in zip(line, line[1:]))
            for first, second in pairs:
                start, end = project(*first[:2]), project(*second[:2])
                length = math.dist(start, end)
                if not length:
                    continue
                self.lengths[area] += length
                index = len(self.edges)
                self.edges.append((area, start, end))
                west = math.floor((min(start[0], end[0]) - radius) / cell_size)
                east = math.floor((max(start[0], end[0]) + radius) / cell_size)
                south = math.floor((min(start[1], end[1]) - radius) / cell_size)
                north = math.floor((max(start[1], end[1]) + radius) / cell_size)
                for x in range(west, east + 1):
                    for y in range(south, north + 1):
                        self.cells[x, y].append(index)
        if not self.edges:
            raise ValueError('No trail centerline edges supplied')

    def nearest(self, lon, lat):
        point = project(lon, lat)
        cell = tuple(math.floor(value / self.cell_size) for value in point)
        nearest = None
        for index in self.cells.get(cell, ()):
            area, start, end = self.edges[index]
            distance_squared = point_segment_distance_squared(point, start, end)
            # Area IDs resolve exact boundary ties deterministically.
            candidate = (distance_squared, area)
            if nearest is None or candidate < nearest:
                nearest = candidate
        if nearest is None or nearest[0] > self.radius ** 2 + 1e-6:
            return None
        return nearest[1], math.sqrt(nearest[0])


def parse_date(value):
    """Read both Seattle's local CSV dates and ISO exports, preserving local day."""
    if len(value) >= 10 and value[2:3] == '/' and value[5:6] == '/':
        return date(int(value[6:10]), int(value[:2]), int(value[3:5]))
    return date.fromisoformat(value[:10])


def make_periods(first, last):
    previous_year = last.year - 1
    return [
        {'id': 'recent', 'label': 'Latest 12 months', 'start': (last - timedelta(days=364)).isoformat(), 'end': last.isoformat()},
        {'id': str(last.year), 'label': f'{last.year} to {last.strftime("%b")} {last.day}', 'start': date(last.year, 1, 1).isoformat(), 'end': last.isoformat()},
        {'id': str(previous_year), 'label': str(previous_year), 'start': date(previous_year, 1, 1).isoformat(), 'end': date(previous_year, 12, 31).isoformat()},
        {'id': 'all', 'label': 'All years', 'start': first.isoformat(), 'end': last.isoformat()},
    ]


def aggregate_csv(csv_path, geometry, area_definitions, buffer_meters=50):
    corridor = Corridor(geometry, radius=max(RADII))
    areas = [dict(area) for area in area_definitions]
    known_areas = {area['id'] for area in areas}
    if set(corridor.lengths) - known_areas:
        raise ValueError('Centerline contains an unrecognized map area')
    official_lengths = Counter()
    for feature in geometry['features']:
        if 'lengthM' in feature['properties']:
            official_lengths[feature['properties']['areaId']] += feature['properties']['lengthM']
    for area in areas:
        # Use official state-plane lengths when supplied; gaps are never counted.
        length = official_lengths.get(area['id'], corridor.lengths[area['id']])
        area['lengthKm'] = round(length / 1000, 4)

    audit = Counter()
    methods = Counter()
    daily = Counter()
    sensitivity_daily = Counter()
    candidate_ids = {}
    first_date = last_date = None
    with Path(csv_path).open(newline='', encoding='utf-8-sig') as source:
        reader = csv.DictReader(source)
        missing_columns = REQUIRED_COLUMNS - set(reader.fieldnames or ())
        if missing_columns:
            raise ValueError('CSV is missing columns: ' + ', '.join(sorted(missing_columns)))
        for row in reader:
            audit['totalRows'] += 1
            methods[row['Method Received']] += 1
            try:
                created = parse_date(row['Created Date'])
                first_date = min(first_date or created, created)
                last_date = max(last_date or created, created)
            except (ValueError, TypeError):
                audit['invalidDates'] += 1
                created = None
            try:
                latitude, longitude = float(row['Latitude']), float(row['Longitude'])
                if not (math.isfinite(latitude) and math.isfinite(longitude)):
                    raise ValueError('Non-finite coordinates')
            except (ValueError, TypeError):
                audit['missingCoordinates'] += 1
                continue
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                audit['invalidCoordinates'] += 1
                continue
            audit['validCoordinates'] += 1
            if created is None:
                continue
            match = corridor.nearest(longitude, latitude)
            if match is None:
                continue
            request_id = row['Service Request Number'].strip()
            if not request_id:
                audit['missingCandidateIds'] += 1
                continue
            fingerprint = (created, latitude, longitude, row['Method Received'], row['Service Request Type'], row['Status'])
            if request_id in candidate_ids:
                if fingerprint != candidate_ids[request_id]:
                    raise ValueError(f'Conflicting records share request ID {request_id}; resolve the source before publishing')
                audit['duplicateCandidateRows'] += 1
                continue
            candidate_ids[request_id] = fingerprint
            area, distance = match
            day = created.isoformat()
            channel = 'app' if row['Method Received'] == PUBLIC_APP else 'other'
            for radius in RADII:
                if distance <= radius + 1e-6:
                    sensitivity_daily[day, radius, channel] += 1
            if distance <= buffer_meters + 1e-6:
                audit['matchedRequests'] += 1
                daily[area, day, channel, row['Service Request Type'] or '(Unspecified)', row['Status'] or '(Unspecified)'] += 1
    if first_date is None or last_date is None:
        raise ValueError('Source contains no valid created dates')
    periods = make_periods(first_date, last_date)
    counts = Counter()
    sensitivity = Counter()
    for (area, day, channel, request_type, status), count in daily.items():
        for period in periods:
            if period['start'] <= day <= period['end']:
                counts[area, period['id'], channel, request_type, status] += count
    for (day, radius, channel), count in sensitivity_daily.items():
        for period in periods:
            if period['start'] <= day <= period['end']:
                sensitivity[period['id'], radius, channel] += count
    return {
        'schemaVersion': 1,
        'source': {
            'filename': Path(csv_path).name, 'url': DATASET_URL, 'metadataUrl': METADATA_URL,
            'snapshotDate': last_date.isoformat(), 'firstDate': first_date.isoformat(),
            'lastDate': last_date.isoformat(),
            **{key: audit[key] for key in ('totalRows', 'missingCoordinates', 'invalidCoordinates', 'validCoordinates', 'invalidDates', 'missingCandidateIds', 'duplicateCandidateRows', 'matchedRequests')},
            'methodCounts': dict(sorted(methods.items())),
        },
        'methodology': {
            'bufferMeters': buffer_meters,
            'description': f'Requests located within approximately {buffer_meters} m of the mapped trail centerline, assigned once to the nearest of eight approximate map areas.',
            'geometrySource': geometry.get('source', {}).get('name', 'Seattle SDOT Multi-use Trails (Seattle Only)'),
            'geometryUrl': geometry.get('metadata', {}).get('source', 'https://services.arcgis.com/ZOyb2t4B0UYuYNYH/arcgis/rest/services/SDOT_Bike_Facilities/FeatureServer/1'),
            'distanceMethod': 'Local equirectangular projection centered at 47.68 N, 122.33 W; spherical Earth radius 6,371,008.8 m. Buffer measurements are approximate.',
            'lengthMethod': 'Official centerline lengths in EPSG:2926 Washington North state-plane coordinates, converted from US survey feet to meters.',
            'appChannel': PUBLIC_APP,
            'otherChannels': 'All other intake methods, including public web/phone and City staff intake. PremierOne CSR Mobile Apps is City staff intake.',
            'countUnit': 'Unique service-request IDs near the mapped centerline; multiple requests may concern the same underlying issue.',
            'dateWindow': 'Created date in the source local calendar; latest 12 months means the latest 365 calendar days including the last observed day.',
            'ranking': 'Requests per mapped kilometer within each area, without dividing by an inferred missing-link length.',
            'limitations': [
                'These are reports near the trail, including nearby streets, parks and properties; they are not verified trail incidents or a measure of danger.',
                'Reporting volume depends on app use, public reporting and departmental practices, rather than only on physical conditions.',
                'Current status is the export snapshot status. Closed does not establish that an issue was fixed; no resolution details or closure dates are supplied.',
                'Unique request IDs can still describe one issue, including departmental copies and records marked as duplicates. Those requests remain counted.',
                'Requests with missing or invalid coordinates or dates cannot be mapped. The last source day and current year may be incomplete.',
                'Only the official Seattle trail mainline is covered. The Ballard Missing Link, access spurs and trail beyond the supplied northern geometry are excluded.',
                'Area boundaries approximate the existing ownership-map orientation labels; reports are not assigned to ownership sections or maintenance responsibility.',
                'Categories and intake systems changed over the historical period, so all-year totals are unsuitable as a current-condition score.',
            ],
            'sensitivityRowFields': ['periodId', 'bufferMeters', 'channel', 'count'],
            'sensitivityRows': [[*key, value] for key, value in sorted(sensitivity.items())],
        },
        'periods': periods,
        'areas': areas,
        'rowFields': ['areaId', 'periodId', 'channel', 'type', 'status', 'count'],
        'rows': [[*key, value] for key, value in sorted(counts.items())],
    }


def sha256_file(path):
    digest = hashlib.sha256()
    with Path(path).open('rb') as source:
        for block in iter(lambda: source.read(1024 * 1024), b''):
            digest.update(block)
    return digest.hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', type=Path, help='Path to the local Seattle CSV export (never copied into the repository)')
    parser.add_argument('--geometry', type=Path, default=DATA_DIR / 'trail-corridor.geojson')
    parser.add_argument('--areas', type=Path, default=DATA_DIR / 'trail-areas.json')
    parser.add_argument('--output-dir', type=Path, default=DATA_DIR)
    args = parser.parse_args()
    geometry = json.loads(args.geometry.read_text())
    area_definitions = json.loads(args.areas.read_text())
    if isinstance(area_definitions, dict):
        area_definitions = area_definitions['areas']
    result = aggregate_csv(args.csv, geometry, area_definitions)
    result['source']['sha256'] = sha256_file(args.csv)
    result['methodology']['geometrySha256'] = sha256_file(args.geometry)
    compact = json.dumps(result, ensure_ascii=False, separators=(',', ':'), allow_nan=False)
    args.output_dir.mkdir(parents=True, exist_ok=True)
    (args.output_dir / 'request-hotspots.json').write_text(compact + '\n')
    (args.output_dir / 'request-hotspots.js').write_text('// Generated by scripts/build-request-hotspots.py; contains aggregate counts only.\nwindow.BURKE_REQUEST_HOTSPOTS = ' + compact + ';\n')
    print(json.dumps({'sourceRows': result['source']['totalRows'], 'matchedRequests': result['source']['matchedRequests'], 'aggregateRows': len(result['rows']), 'dataBytes': len(compact.encode()), 'dateRange': [result['source']['firstDate'], result['source']['lastDate']]}, indent=2))


if __name__ == '__main__':
    main()
