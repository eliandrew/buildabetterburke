"""Cross-file checks for the static data actually shipped to the map.

These require no CSV, network, GIS package, or browser. They catch stale exports,
double-counted aggregate keys, changed area denominators, and stale public notes.
"""

from collections import Counter
from datetime import date
import hashlib
import json
from pathlib import Path
import re
import unittest

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / 'burke-gilman' / 'data'


class PublishedArtifactTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.data = json.loads((DATA / 'request-hotspots.json').read_text())
        cls.geometry = json.loads((DATA / 'trail-corridor.geojson').read_text())

    def test_browser_and_download_payloads_are_identical(self):
        wrapper = (DATA / 'request-hotspots.js').read_text()
        assignment = wrapper.split('window.BURKE_REQUEST_HOTSPOTS = ', 1)[1]
        self.assertEqual(json.loads(assignment.strip().removesuffix(';')), self.data)
        self.assertEqual(self.data['rowFields'],
                         ['areaId', 'periodId', 'channel', 'type', 'status', 'count'])

    def test_geometry_provenance_and_area_lengths_match_the_map(self):
        digest = hashlib.sha256((DATA / 'trail-corridor.geojson').read_bytes()).hexdigest()
        self.assertEqual(digest, self.data['methodology']['geometrySha256'])
        page = (ROOT / 'burke-gilman' / 'hotspots.html').read_text()
        embedded = re.search(r'<script id="map-data"[^>]*>(.*?)</script>', page, re.S)
        map_data = json.loads(embedded.group(1))
        ownership_page = (ROOT / 'burke-gilman' / 'index.html').read_text()
        ownership_data = re.search(r'<script id="map-data"[^>]*>(.*?)</script>',
                                   ownership_page, re.S)
        self.assertEqual(map_data, json.loads(ownership_data.group(1)))
        areas = {area['id']: area for area in self.data['areas']}
        self.assertEqual(set(areas), {area['id'] for area in map_data['areas']})
        lengths = Counter()
        for feature in self.geometry['features']:
            lengths[feature['properties']['areaId']] += feature['properties']['lengthM']
        self.assertEqual(set(areas), set(lengths))
        for identifier, area in areas.items():
            with self.subTest(area=identifier):
                self.assertGreater(area['lengthKm'], 0)
                self.assertAlmostEqual(area['lengthKm'], lengths[identifier] / 1000, places=4)
        self.assertAlmostEqual(sum(lengths.values()),
                               self.geometry['metadata']['totalLengthM'], places=2)

    def test_unique_aggregate_keys_and_independent_sensitivity_totals_reconcile(self):
        periods = {period['id'] for period in self.data['periods']}
        areas = {area['id'] for area in self.data['areas']}
        keys, totals = set(), Counter()
        for row in self.data['rows']:
            self.assertEqual(len(row), 6)
            area, period, channel, request_type, status, count = row
            self.assertIn(area, areas)
            self.assertIn(period, periods)
            self.assertIn(channel, ('app', 'other'))
            self.assertIsInstance(count, int)
            self.assertGreater(count, 0)
            self.assertIsInstance(request_type, str)
            self.assertIsInstance(status, str)
            key = tuple(row[:5])
            self.assertNotIn(key, keys)
            keys.add(key)
            totals[period, channel] += count
        source = self.data['source']
        self.assertEqual(totals['all', 'app'] + totals['all', 'other'], source['matchedRequests'])
        self.assertEqual(source['totalRows'], source['validCoordinates'] +
                         source['missingCoordinates'] + source['invalidCoordinates'])
        self.assertEqual(sum(source['methodCounts'].values()), source['totalRows'])
        sensitivity = {(p, radius, channel): n for p, radius, channel, n
                       in self.data['methodology']['sensitivityRows']}
        for period in periods:
            for channel in ('app', 'other'):
                with self.subTest(period=period, channel=channel):
                    self.assertEqual(sensitivity.get((period, 50, channel), 0), totals[period, channel])
                    self.assertLessEqual(sensitivity.get((period, 25, channel), 0), totals[period, channel])
                    self.assertGreaterEqual(sensitivity.get((period, 100, channel), 0), totals[period, channel])
                    self.assertLessEqual(totals[period, channel], totals['all', channel])

    def test_default_window_and_public_snapshot_notes_stay_current(self):
        periods = {period['id']: period for period in self.data['periods']}
        recent, all_years = periods['recent'], periods['all']
        self.assertEqual((date.fromisoformat(recent['end']) -
                          date.fromisoformat(recent['start'])).days + 1, 365)
        self.assertEqual(recent['end'], self.data['source']['lastDate'])
        self.assertEqual(all_years['start'], self.data['source']['firstDate'])
        self.assertEqual(all_years['end'], self.data['source']['lastDate'])
        page = (ROOT / 'burke-gilman' / 'request-hotspots-methodology.html').read_text()
        public_count = re.search(r'<strong>([0-9,]+) public app requests</strong>', page)
        all_count = re.search(r'raises that number to <strong>([0-9,]+)</strong>', page)
        expected_public = sum(row[5] for row in self.data['rows']
                              if row[1] == 'recent' and row[2] == 'app')
        expected_all = sum(row[5] for row in self.data['rows'] if row[1] == 'recent')
        self.assertEqual(int(public_count.group(1).replace(',', '')), expected_public)
        self.assertEqual(int(all_count.group(1).replace(',', '')), expected_all)
        for value in (recent['start'], recent['end']):
            day = date.fromisoformat(value)
            self.assertIn(f'{day.strftime("%B")} {day.day}, {day.year}', page)


if __name__ == '__main__':
    unittest.main()
