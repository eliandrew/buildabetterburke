"""Spatial and counting regression tests; no network or downloaded CSV required."""

import csv
import importlib.util
import json
import math
import tempfile
import unittest
from pathlib import Path

SPEC = importlib.util.spec_from_file_location('hotspots', Path(__file__).with_name('build-request-hotspots.py'))
hotspots = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(hotspots)


def coordinates(x, y):
    return [hotspots.ORIGIN_LON + math.degrees(x / (hotspots.EARTH_RADIUS * math.cos(math.radians(hotspots.ORIGIN_LAT)))),
            hotspots.ORIGIN_LAT + math.degrees(y / hotspots.EARTH_RADIUS)]


def feature(area, lines):
    return {'type': 'Feature', 'properties': {'areaId': area},
            'geometry': {'type': 'MultiLineString', 'coordinates': [[coordinates(*point) for point in line] for line in lines]}}


def geometry(*features):
    return {'type': 'FeatureCollection', 'features': list(features)}


def request(identifier, day, x=50, y=20, method=hotspots.PUBLIC_APP, status='Closed'):
    lon, lat = coordinates(x, y)
    return {'Service Request Number': identifier, 'Service Request Type': 'Graffiti',
            'Created Date': day, 'Method Received': method, 'Status': status,
            'Latitude': str(lat), 'Longitude': str(lon)}


class CorridorTests(unittest.TestCase):
    def test_threshold_and_endpoint_distance(self):
        corridor = hotspots.Corridor(geometry(feature('west', [[(0, 0), (100, 0)]])), radius=50)
        self.assertAlmostEqual(corridor.nearest(*coordinates(50, 50))[1], 50, places=5)
        self.assertIsNone(corridor.nearest(*coordinates(50, 50.01)))
        # Distance past an endpoint must use that endpoint, not an infinite line.
        self.assertIsNone(corridor.nearest(*coordinates(151, 0)))

    def test_disconnected_lines_do_not_bridge_missing_link(self):
        corridor = hotspots.Corridor(geometry(feature('west', [[(0, 0), (100, 0)], [(300, 0), (400, 0)]])), radius=50)
        self.assertIsNone(corridor.nearest(*coordinates(200, 0)))
        self.assertAlmostEqual(corridor.lengths['west'], 200, places=5)

    def test_nearest_area_is_single_and_boundary_tie_is_stable(self):
        parts = [feature('west', [[(0, 0), (100, 0)]]), feature('east', [[(100, 0), (200, 0)]])]
        corridor = hotspots.Corridor(geometry(*parts))
        self.assertEqual(corridor.nearest(*coordinates(95, 20))[0], 'west')
        expected = corridor.nearest(*coordinates(100, 20))[0]
        reverse = hotspots.Corridor(geometry(*reversed(parts)))
        self.assertEqual(reverse.nearest(*coordinates(100, 20))[0], expected)


class AggregationTests(unittest.TestCase):
    def aggregate(self, rows):
        with tempfile.TemporaryDirectory() as directory:
            csv_path = Path(directory) / 'requests.csv'
            with csv_path.open('w', newline='') as output:
                writer = csv.DictWriter(output, fieldnames=sorted(hotspots.REQUIRED_COLUMNS))
                writer.writeheader()
                writer.writerows(rows)
            return hotspots.aggregate_csv(csv_path, geometry(feature('west', [[(0, 0), (100, 0)]])),
                                          [{'id': 'west', 'name': 'West'}])

    def test_snapshot_windows_channels_duplicates_and_unmapped_rows(self):
        first = request('a', '11/15/2025 12:00:00 PM')
        staff = request('b', '11/13/2026 12:00:00 PM', method='PremierOne CSR Mobile Apps', status='Reported')
        older = request('c', '11/14/2025 12:00:00 PM', status='Closed as Duplicate')
        newest = request('d', '11/14/2026 12:00:00 PM')
        newest['Latitude'] = ''
        far = request('e', '11/14/2026 12:00:00 PM', y=75)
        result = self.aggregate([first, staff, older, newest, far, dict(first)])
        self.assertEqual(result['source']['totalRows'], 6)
        self.assertEqual(result['source']['missingCoordinates'], 1)
        self.assertEqual(result['source']['duplicateCandidateRows'], 1)
        self.assertEqual(result['source']['matchedRequests'], 3)
        self.assertEqual(result['source']['lastDate'], '2026-11-14')
        recent = [row for row in result['rows'] if row[1] == 'recent']
        self.assertEqual(sum(row[-1] for row in recent), 2)
        self.assertEqual({row[2] for row in recent}, {'app', 'other'})
        self.assertEqual(next(p for p in result['periods'] if p['id'] == 'recent')['start'], '2025-11-15')
        self.assertIn(['west', 'all', 'app', 'Graffiti', 'Closed as Duplicate', 1], result['rows'])
        sensitivity = result['methodology']['sensitivityRows']
        self.assertEqual(sum(row[-1] for row in sensitivity if row[0] == 'all' and row[1] == 100), 4)
        # The published shape contains aggregates, never identities or point locations.
        encoded = json.dumps(result)
        self.assertNotIn('Service Request Number', encoded)
        self.assertNotIn('Latitude', encoded)
        self.assertEqual(result['rowFields'], ['areaId', 'periodId', 'channel', 'type', 'status', 'count'])

    def test_conflicting_duplicate_ids_fail_instead_of_choosing_a_status(self):
        first = request('same', '2026-11-14')
        changed = dict(first, Status='Reported')
        with self.assertRaisesRegex(ValueError, 'Conflicting records'):
            self.aggregate([first, changed])

    def test_invalid_dates_and_coordinates_are_excluded(self):
        valid = request('a', '2026-11-14')
        bad_date = request('b', '02/30/2026 12:00:00 PM')
        bad_coordinate = dict(request('c', '2026-11-14'), Latitude='inf')
        out_of_range = dict(request('d', '2026-11-14'), Longitude='181')
        result = self.aggregate([valid, bad_date, bad_coordinate, out_of_range])
        self.assertEqual(result['source']['matchedRequests'], 1)
        self.assertEqual(result['source']['invalidDates'], 1)
        self.assertEqual(result['source']['missingCoordinates'], 1)
        self.assertEqual(result['source']['invalidCoordinates'], 1)

    def test_real_geometry_gap_lengths_and_area_coverage(self):
        path = hotspots.DATA_DIR / 'trail-corridor.geojson'
        if not path.exists():
            self.skipTest('Committed geometry not present')
        data = json.loads(path.read_text())
        corridor = hotspots.Corridor(data, radius=50)
        self.assertEqual(set(corridor.lengths), {'ballard', 'fremont', 'wallingford', 'uw', 'ravenna', 'sand-point', 'matthews', 'north'})
        self.assertIsNone(corridor.nearest(-122.384, 47.6645))
        self.assertGreater(sum(corridor.lengths.values()), 22000)
        self.assertLess(sum(corridor.lengths.values()), 23000)


if __name__ == '__main__':
    unittest.main()
