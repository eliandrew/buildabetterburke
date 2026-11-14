#!/usr/bin/env python3
"""Independently audit hotspot aggregates with Shapely/GEOS and pyproj.

This optional checker imports no builder code. Install its separate dependencies
from requirements-request-audit.txt. The builder and unit tests remain stdlib-only.
Only aggregate statistics are printed or written; source IDs stay in memory.
"""

import argparse
from collections import Counter
import csv
from datetime import date, datetime, timedelta
import hashlib
import json
import math
from pathlib import Path
import sys

try:
    import numpy as np
    import pyproj
    import shapely
    from shapely import STRtree
except ImportError as error:
    raise SystemExit(
        'Install audit dependencies with: python -m pip install -r '
        'scripts/requirements-request-audit.txt'
    ) from error

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[1] / 'burke-gilman' / 'data'
APP_CHANNEL = 'Find It Fix It Apps'
METRIC_CRS = '+proj=aeqd +lat_0=47.68 +lon_0=-122.33 +datum=WGS84 +units=m +no_defs'


def local_projection(longitudes, latitudes):
    """The projection documented in REQUEST_HOTSPOTS.md, implemented separately."""
    radius = 6371008.8
    x = np.deg2rad(np.asarray(longitudes) + 122.33) * radius * math.cos(math.radians(47.68))
    y = np.deg2rad(np.asarray(latitudes) - 47.68) * radius
    return x, y


def segment_tree(geometry, projection):
    """Keep disconnected paths separate; let GEOS calculate segment distances."""
    segments, areas = [], []
    for feature in geometry['features']:
        geo = feature['geometry']
        if geo['type'] not in ('LineString', 'MultiLineString'):
            raise ValueError('The corridor must contain only line geometries.')
        lines = [geo['coordinates']] if geo['type'] == 'LineString' else geo['coordinates']
        for line in lines:
            vertices = np.asarray(line, dtype=float)
            x, y = projection(vertices[:, 0], vertices[:, 1])
            points = np.column_stack((x, y))
            for start, end in zip(points[:-1], points[1:]):
                if not np.array_equal(start, end):
                    segments.append([start, end])
                    areas.append(feature['properties']['areaId'])
    if not segments:
        raise ValueError('The corridor has no non-degenerate segments.')
    return STRtree(shapely.linestrings(np.asarray(segments))), areas


def nearest_segments(tree, coordinates, max_distance):
    indices, distances = tree.query_nearest(
        shapely.points(coordinates), max_distance=max_distance,
        all_matches=True, return_distance=True)
    nearest = {}
    for point_index, segment_index, distance in zip(indices[0], indices[1], distances):
        point_index = int(point_index)
        candidate = (float(distance), int(segment_index))
        # Exact ties follow geometry order, independently of STRtree traversal.
        if point_index not in nearest or candidate < nearest[point_index]:
            nearest[point_index] = candidate
    return nearest


def mismatches(expected, observed):
    return [
        {'key': list(key) if isinstance(key, tuple) else key,
         'published': expected.get(key, 0), 'recount': observed.get(key, 0)}
        for key in sorted(set(expected) | set(observed))
        if key not in expected or key not in observed or expected[key] != observed[key]
    ]


def distribution(values):
    if not values:
        return {'n': 0}
    return {
        'n': len(values),
        **dict(zip(('minimum', 'median', 'p95', 'maximum'),
                   map(float, np.quantile(values, [0, .5, .95, 1])))),
    }


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as stream:
        for chunk in iter(lambda: stream.read(8 * 1024 * 1024), b''):
            digest.update(chunk)
    return digest.hexdigest()


def verify(csv_path, data_dir):
    published = json.loads((data_dir / 'request-hotspots.json').read_text())
    geometry_path = data_dir / 'trail-corridor.geojson'
    geometry = json.loads(geometry_path.read_text())
    local_tree, areas = segment_tree(geometry, local_projection)
    # An ellipsoidal reference in meters, centered on Seattle, with no datum shift.
    metric_projection = pyproj.Transformer.from_crs(4326, METRIC_CRS, always_xy=True)
    metric_tree, metric_areas = segment_tree(geometry, metric_projection.transform)
    stats, methods, ids, date_cache = Counter(), Counter(), set(), {}
    first_day = last_day = None
    nearby, batch = [], []

    def process_batch():
        if not batch:
            return
        coordinates = np.asarray([(row[1], row[2]) for row in batch])
        x, y = local_projection(coordinates[:, 0], coordinates[:, 1])
        local = nearest_segments(local_tree, np.column_stack((x, y)), 105)
        indices = sorted(local)
        if indices:
            subset = coordinates[indices]
            x, y = metric_projection.transform(subset[:, 0], subset[:, 1])
            metric = nearest_segments(metric_tree, np.column_stack((x, y)), 106)
            if len(metric) != len(indices):
                raise ValueError('Metric candidate search was unexpectedly incomplete.')
            for index, batch_index in enumerate(indices):
                day, _, _, channel, category, status = batch[batch_index]
                distance, segment = local[batch_index]
                metric_distance, metric_segment = metric[index]
                nearby.append((day, areas[segment], channel, category, status,
                               distance, metric_distance, metric_areas[metric_segment]))
        batch.clear()

    with csv_path.open(encoding='utf-8-sig', newline='') as stream:
        reader = csv.DictReader(stream)
        required = {'Service Request Number', 'Created Date', 'Latitude', 'Longitude',
                    'Method Received', 'Service Request Type', 'Status'}
        if not required <= set(reader.fieldnames or []):
            raise ValueError('The CSV is missing required service-request columns.')
        for row in reader:
            stats['totalRows'] += 1
            request_id = row['Service Request Number'].strip()
            if not request_id:
                stats['missingIds'] += 1
            elif request_id in ids:
                stats['repeatedIds'] += 1
            else:
                ids.add(request_id)
            method = row['Method Received']
            methods[method] += 1
            raw_day = row['Created Date'].split(' ', 1)[0]
            try:
                if raw_day not in date_cache:
                    date_cache[raw_day] = datetime.strptime(raw_day, '%m/%d/%Y').date()
                day = date_cache[raw_day]
                first_day = day if first_day is None else min(first_day, day)
                last_day = day if last_day is None else max(last_day, day)
            except ValueError:
                stats['invalidDates'] += 1
                day = None
            try:
                latitude, longitude = float(row['Latitude']), float(row['Longitude'])
            except ValueError:
                stats['missingCoordinates'] += 1
                continue
            if not (math.isfinite(longitude) and math.isfinite(latitude)
                    and -180 <= longitude <= 180 and -90 <= latitude <= 90):
                stats['invalidCoordinates'] += 1
                continue
            stats['validCoordinates'] += 1
            if day is not None:
                batch.append((day, longitude, latitude,
                              'app' if method == APP_CHANNEL else 'other',
                              row['Service Request Type'], row['Status']))
            if len(batch) >= 10000:
                process_batch()
        process_batch()
    if first_day is None:
        raise ValueError('The CSV has no valid created calendar dates.')

    windows = {
        'recent': (last_day - timedelta(days=364), last_day),
        str(last_day.year): (date(last_day.year, 1, 1), last_day),
        str(last_day.year - 1): (date(last_day.year - 1, 1, 1), date(last_day.year - 1, 12, 31)),
        'all': (first_day, last_day),
    }
    counts, sensitivity, metric_sensitivity = Counter(), Counter(), Counter()
    recent_areas, metric_recent_areas = Counter(), Counter()
    errors, boundary_errors = [], []
    changes, area_changes = Counter(), Counter()
    for day, area, channel, category, status, distance, metric_distance, metric_area in nearby:
        errors.append(abs(metric_distance - distance))
        if 49 <= distance <= 51:
            boundary_errors.append(abs(metric_distance - distance))
        if (distance <= 50) != (metric_distance <= 50):
            changes['localIncludedMetricExcluded' if distance <= 50 else
                    'localExcludedMetricIncluded'] += 1
            if windows['recent'][0] <= day <= last_day:
                changes['recent_' + channel] += 1
        if distance <= 50 and metric_distance <= 50 and area != metric_area:
            area_changes[(area, metric_area)] += 1
        for period, (start, end) in windows.items():
            if start <= day <= end:
                for threshold in (25, 50, 100):
                    if distance <= threshold:
                        sensitivity[(period, threshold, channel)] += 1
                    if metric_distance <= threshold:
                        metric_sensitivity[(period, threshold, channel)] += 1
                if distance <= 50:
                    counts[(area, period, channel, category, status)] += 1
        if windows['recent'][0] <= day <= last_day:
            if distance <= 50:
                recent_areas[(area, channel)] += 1
            if metric_distance <= 50:
                metric_recent_areas[(metric_area, channel)] += 1

    expected_counts = {tuple(row[:-1]): row[-1] for row in published['rows']}
    expected_sensitivity = {tuple(row[:-1]): row[-1]
                            for row in published['methodology']['sensitivityRows']}
    source = {key: stats[key] for key in ('totalRows', 'missingCoordinates',
              'invalidCoordinates', 'validCoordinates', 'invalidDates')}
    source.update(firstDate=first_day.isoformat(), lastDate=last_day.isoformat(),
                  matchedRequests=sum(sensitivity[('all', 50, c)] for c in ('app', 'other')))
    failures = {
        'source': mismatches({key: published['source'][key] for key in source}, source),
        'intakeMethods': mismatches(published['source']['methodCounts'], methods),
        'aggregates': mismatches(expected_counts, counts),
        'sensitivity': mismatches(expected_sensitivity, sensitivity),
        'periods': mismatches(
            {p['id']: (p['start'], p['end']) for p in published['periods']},
            {key: tuple(day.isoformat() for day in days) for key, days in windows.items()}),
        'duplicateAggregateKeys': len(published['rows']) - len(expected_counts),
        'duplicateSensitivityKeys': len(published['methodology']['sensitivityRows']) - len(expected_sensitivity),
        # Repeated/missing source IDs need separate review, not silent assumptions
        # about whether those records describe the same request. This checker
        # intentionally fails when source-wide identity cannot be established.
        'repeatedSourceIds': stats['repeatedIds'],
        'missingSourceIds': stats['missingIds'],
        'sourceHash': sha256(csv_path) != published['source']['sha256'],
        'geometryHash': sha256(geometry_path) != published['methodology']['geometrySha256'],
    }
    return {
        'passed': not any(failures.values()),
        'versions': {'shapely': shapely.__version__, 'pyproj': pyproj.__version__, 'numpy': np.__version__},
        'source': {**source, 'uniqueIds': len(ids), 'missingIds': stats['missingIds'],
                   'repeatedIds': stats['repeatedIds']},
        'segmentCount': len(areas), 'candidateRowsWithin105m': len(nearby),
        'aggregateKeyCount': len(counts), 'sensitivityKeyCount': len(sensitivity),
        'recentWindow': [d.isoformat() for d in windows['recent']],
        'recentApp': sensitivity[('recent', 50, 'app')],
        'recentOther': sensitivity[('recent', 50, 'other')],
        'recentAreaCounts': [[*key, n] for key, n in sorted(recent_areas.items())],
        'sensitivityRows': [[*key, n] for key, n in sorted(sensitivity.items())],
        'metricComparison': {
            'projection': METRIC_CRS, 'absoluteDifferenceMeters': distribution(errors),
            'absoluteDifferenceMetersWithin49To51m': distribution(boundary_errors),
            'threshold50mChanges': dict(changes),
            'nearestAreaChangesWithinBoth50m': [[*key, n] for key, n in sorted(area_changes.items())],
            'recentAreaCounts': [[*key, n] for key, n in sorted(metric_recent_areas.items())],
            'sensitivityRows': [[*key, n] for key, n in sorted(metric_sensitivity.items())],
        },
        'failures': failures,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('csv', type=Path, help='Source Customer Service Requests CSV')
    parser.add_argument('--data-dir', type=Path, default=DEFAULT_DATA_DIR,
                        help='Directory containing request-hotspots.json and trail-corridor.geojson')
    parser.add_argument('--json-output', type=Path, help='Optional detailed aggregate-only audit report')
    args = parser.parse_args()
    try:
        result = verify(args.csv, args.data_dir)
    except (OSError, ValueError, KeyError, TypeError, csv.Error) as error:
        # Source row contents can appear in parsing exceptions. Keep those private.
        print(f'Audit could not complete ({type(error).__name__}); check input schema and files.', file=sys.stderr)
        return 2
    if args.json_output:
        args.json_output.write_text(json.dumps(result, indent=2) + '\n')
    label = 'PASS' if result['passed'] else 'FAIL'
    source = result['source']
    print(f"{label}: {result['aggregateKeyCount']:,} aggregate keys; "
          f"{result['sensitivityKeyCount']} sensitivity rows. "
          f"Source: {source['totalRows']:,} rows, {source['uniqueIds']:,} unique IDs, "
          f"{source['missingCoordinates']:,} missing coordinates.")
    print(f"Within 50 m: all years {source['matchedRequests']:,}; "
          f"latest 365 days {result['recentApp']:,} app + {result['recentOther']:,} other "
          f"({result['recentWindow'][0]} to {result['recentWindow'][1]}).")
    metric = result['metricComparison']
    changes = metric['threshold50mChanges']
    maximum = metric['absoluteDifferenceMetersWithin49To51m'].get('maximum', 0)
    print(f"Ellipsoidal reference: max difference near 50 m {maximum:.4f} m; "
          f"{changes.get('localIncludedMetricExcluded', 0)} out / "
          f"{changes.get('localExcludedMetricIncluded', 0)} in; latest app changes "
          f"{changes.get('recent_app', 0)}.")
    if not result['passed']:
        print('Failed checks: ' + ', '.join(key for key, value in result['failures'].items() if value))
    return 0 if result['passed'] else 1


if __name__ == '__main__':
    sys.exit(main())
