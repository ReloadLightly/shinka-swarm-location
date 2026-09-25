"""Demand-header rounding, exact acceptance boundaries, and import provenance."""
from fractions import Fraction
import hashlib
import json
from pathlib import Path
import tempfile
import unittest

from scripts.prepare_search import prepare
from swarm_location.tntp_v2 import parse_documented

ROOT = Path(__file__).resolve().parents[1]
NETWORK = '<NUMBER OF NODES> 2\n<NUMBER OF LINKS> 1\n<END OF METADATA>\n1 2 1 1 1;\n'


def trips(header, rows):
    return f'<TOTAL OD FLOW> {header}\n<END OF METADATA>\nOrigin 1\n{rows}\n'


class HeaderToleranceTests(unittest.TestCase):
    def setUp(self):
        self.catalog = json.loads((ROOT / 'configs/source_catalog_search.json').read_text())
        self.tolerance = self.catalog['header_total_tolerance']

    def parse(self, header, rows='2 : 1000000;', tolerance=None):
        return parse_documented(NETWORK, trips(header, rows), 'header-fixture',
                                self.tolerance if tolerance is None else tolerance)

    def test_catalog_rounding_tolerance_and_audit(self):
        for key in ('absolute', 'relative'):
            self.assertEqual(Fraction(self.tolerance[key]), Fraction(1, 10**9))
        for header in ('1000000.00001', '999999.99999'):
            data, audit = self.parse(header)
            scale = max(Fraction(header), Fraction(1000000))
            self.assertEqual(data['od'], [[1, 2, 1000000]])
            self.assertEqual(Fraction(audit['header_discrepancy_exact']), Fraction(1, 100000))
            self.assertEqual(Fraction(audit['header_allowed_discrepancy_exact']), scale / 10**9)
            self.assertEqual(Fraction(audit['header_relative_discrepancy_exact']), Fraction(1, 100000) / scale)
            self.assertFalse(audit['source_values_modified'])

    def test_relative_boundary_is_inclusive_and_exact(self):
        _, audit = self.parse('999999.999')
        self.assertEqual(audit['header_discrepancy_exact'], '1/1000')
        self.assertEqual(audit['header_allowed_discrepancy_exact'], '1/1000')
        with self.assertRaisesRegex(ValueError, 'allowed discrepancy'):
            self.parse('999999.998999999999999999999999')

    def test_absolute_boundary_for_small_totals(self):
        data, audit = self.parse('0', '2 : 0.000000001;')
        self.assertEqual(data['od'], [[1, 2, 1e-9]])
        self.assertEqual(audit['header_allowed_discrepancy_exact'], '1/1000000000')
        with self.assertRaisesRegex(ValueError, 'OD total'):
            self.parse('0', '2 : 0.000000001000000000000000001;')

    def test_exact_accounting_includes_intrazonal_before_exclusion(self):
        data, audit = self.parse('1000000.00001', '1 : 999999.7; 2 : 0.3;')
        self.assertEqual(audit['parsed_total_demand_exact'], '1000000')
        self.assertEqual(audit['excluded_intrazonal_demand_exact'], '9999997/10')
        self.assertEqual(audit['retained_interzonal_demand_exact'], '3/10')
        self.assertEqual(data['od'], [[1, 2, 0.3]])

    def test_zero_tolerances_require_exact_header(self):
        exact = {'absolute': '0', 'relative': '0'}
        self.parse('1000000', tolerance=exact)
        with self.assertRaisesRegex(ValueError, 'OD total'):
            self.parse('1000000.00000000000000000000001', tolerance=exact)

    def test_invalid_tolerances_are_rejected_even_for_equal_totals(self):
        for component in ('absolute', 'relative'):
            for value in ('-1', 'NaN', 'Infinity', '1/0'):
                with self.subTest(component=component, value=value):
                    tolerance = dict(self.tolerance, **{component: value})
                    with self.assertRaisesRegex(ValueError, 'header tolerances'):
                        self.parse('1000000', tolerance=tolerance)

    def test_negative_header_is_not_explained_by_absolute_tolerance(self):
        with self.assertRaisesRegex(ValueError, 'declared total OD flow'):
            self.parse('-0.0000000001', '2 : 0.0000000001;')

    def test_dataset_override_is_recorded_in_prepared_provenance(self):
        # Small synthetic input: this does not open or score a held-out network.
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            raw, output = root / 'raw', root / 'prepared'
            raw.mkdir()
            files = {}
            for kind, content in [('network', NETWORK), ('trips', trips('1.25', '2 : 1;'))]:
                encoded = content.encode()
                name = kind + '.tntp'
                (raw / name).write_bytes(encoded)
                blob = hashlib.sha1(b'blob ' + str(len(encoded)).encode() + b'\0' + encoded).hexdigest()
                files[kind] = {'path': name, 'git_blob_sha1': blob}
            catalog = dict(self.catalog, datasets=[{
                'id': 'fixture', 'source_graph': 'fixture', 'split': 'development',
                'expected_nodes': 2, 'expected_edges': 1, 'budgets': [1], 'files': files,
                'header_total_tolerance': {'absolute': '0.25', 'relative': '0'}}])
            catalog_path = root / 'catalog.json'
            catalog_path.write_text(json.dumps(catalog))
            audits = prepare(catalog_path, raw, output)
            self.assertEqual(audits[0]['header_absolute_tolerance_exact'], '1/4')
            self.assertEqual(audits[0]['header_relative_tolerance_exact'], '0')
            self.assertEqual(audits[0]['header_allowed_discrepancy_exact'], '1/4')
            stored = json.loads((output / 'fixture.json').read_text())
            self.assertEqual(stored['provenance']['import_audit']['header_allowed_discrepancy_exact'], '1/4')
            self.assertEqual(stored['od'], [[1, 2, 1]])
            self.assertEqual(json.loads((output / 'import_audit.json').read_text()), audits)


if __name__ == '__main__':
    unittest.main()
