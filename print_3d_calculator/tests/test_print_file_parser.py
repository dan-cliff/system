from odoo.tests import BaseCase, tagged

from ..tools import print_file_parser as parser
from . import samples


@tagged('post_install', '-at_install')
class TestPrintFileParser(BaseCase):

    def assertWeights(self, result, expected):
        self.assertEqual([round(f.weight_g, 2) for f in result.filaments], expected)

    def test_durations(self):
        self.assertEqual(parser.parse_duration('1h 2m 3s'), 3723)
        self.assertEqual(parser.parse_duration('1d 2h'), 93600)
        self.assertEqual(parser.parse_duration('10m27s'), 627)
        self.assertEqual(parser.parse_duration('1 hours 2 minutes'), 3720)
        self.assertEqual(parser.parse_duration('6666'), 6666)
        self.assertEqual(parser.parse_duration('01:02:03'), 3723)

    def test_prusaslicer(self):
        result = parser.analyse(samples.PRUSA_GCODE, 'part.gcode')
        self.assertTrue(result.sliced)
        self.assertEqual(result.slicer, 'PrusaSlicer 2.7.1')
        self.assertEqual(result.print_time_s, 3723)
        # The unused middle extruder is dropped.
        self.assertEqual([f.slot for f in result.filaments], [1, 3])
        self.assertWeights(result, [3.68, 1.4])
        self.assertEqual([f.material for f in result.filaments], ['PLA', 'PETG'])
        self.assertEqual(result.filaments[1].colour, '#0000FF')
        self.assertAlmostEqual(result.total_weight_g, 5.08)
        self.assertTrue(all(f.weight_reported for f in result.filaments))

    def test_bambu_gcode(self):
        result = parser.analyse(samples.BAMBU_GCODE, 'plate_1.gcode')
        self.assertEqual(result.slicer, 'Bambu Studio 01.09.00.70')
        self.assertEqual(result.print_time_s, 1010)
        self.assertWeights(result, [3.0, 0.6])
        self.assertEqual([f.colour for f in result.filaments], ['#000000', '#FFFFFF'])
        self.assertAlmostEqual(result.filaments[0].length_mm, 1000.0)

    def test_cura(self):
        result = parser.analyse(samples.CURA_GCODE, 'part.gcode')
        self.assertEqual(result.slicer, 'Cura 5.4.0')
        self.assertEqual(result.print_time_s, 6666)
        self.assertEqual([round(f.length_mm) for f in result.filaments], [1500, 250])
        # Cura reports length only: the weight is worked out (and flagged as such).
        self.assertFalse(result.filaments[0].weight_reported)
        self.assertAlmostEqual(result.filaments[0].weight_g, 4.47, places=2)

    def test_simplify3d(self):
        result = parser.analyse(samples.SIMPLIFY3D_GCODE, 'part.gcode')
        self.assertEqual(result.slicer, 'Simplify3D 4.1.2')
        self.assertEqual(result.print_time_s, 3720)
        self.assertWeights(result, [3.68])

    def test_ideamaker(self):
        result = parser.analyse(samples.IDEAMAKER_GCODE, 'part.gcode')
        self.assertEqual(result.slicer, 'ideaMaker 4.4.0')
        self.assertEqual(result.print_time_s, 3600)
        self.assertEqual([round(f.length_mm) for f in result.filaments], [1000, 500])

    def test_kisslicer(self):
        result = parser.analyse(samples.KISSLICER_GCODE, 'part.gcode')
        self.assertEqual(result.slicer, 'KISSlicer')
        self.assertEqual(result.print_time_s, 2070)
        self.assertEqual([round(f.length_mm, 2) for f in result.filaments], [1234.56])

    def test_unknown_gcode_is_measured(self):
        result = parser.analyse(samples.UNKNOWN_GCODE, 'part.gcode')
        self.assertEqual([round(f.length_mm, 2) for f in result.filaments], [12.0, 3.0])
        self.assertEqual(result.print_time_s, 2)
        self.assertEqual(len(result.warnings), 2)

    def test_bgcode(self):
        result = parser.analyse(samples.bgcode(), 'part.bgcode')
        self.assertEqual(result.file_format, 'bgcode')
        self.assertEqual(result.slicer, 'PrusaSlicer 2.7.1')
        self.assertEqual(result.print_time_s, 9000)
        self.assertWeights(result, [3.0, 1.6])
        self.assertEqual([f.material for f in result.filaments], ['PLA', 'PETG'])

    def test_ufp(self):
        result = parser.analyse(samples.ufp(), 'part.ufp')
        self.assertEqual(result.file_format, 'ufp')
        self.assertEqual(result.print_time_s, 6666)
        self.assertEqual(len(result.filaments), 2)

    def test_bambu_3mf_sliced(self):
        result = parser.analyse(samples.bambu_3mf_sliced(), 'part.gcode.3mf')
        self.assertTrue(result.sliced)
        self.assertEqual(result.slicer, 'Bambu Studio 01.09.07.52')
        self.assertEqual(result.plate_count, 2)
        self.assertEqual(result.print_time_s, 5400)
        self.assertEqual([f.slot for f in result.filaments], [1, 3])
        self.assertWeights(result, [15.0, 2.5])
        self.assertEqual([f.material for f in result.filaments], ['PLA', 'PETG'])
        self.assertEqual(result.filaments[0].density, 1.24)
        self.assertAlmostEqual(result.volume_cm3, 8.0)

    def test_3mf_unsliced(self):
        result = parser.analyse(samples.prusa_3mf_unsliced(), 'part.3mf')
        self.assertFalse(result.sliced)
        self.assertEqual(result.slicer, 'PrusaSlicer 2.7.1')
        self.assertAlmostEqual(result.volume_cm3, 8.0)
        self.assertAlmostEqual(result.surface_area_cm2, 24.0)
        self.assertEqual(result.size_mm, (20.0, 20.0, 20.0))
        self.assertEqual(result.settings['infill_percent'], 20.0)
        self.assertEqual(result.filaments[0].material, 'PETG')

    def test_stl(self):
        for data in (samples.stl_binary(), samples.stl_ascii()):
            result = parser.analyse(data, 'cube.stl')
            self.assertFalse(result.sliced)
            self.assertAlmostEqual(result.volume_cm3, 1.0, places=4)
            self.assertAlmostEqual(result.surface_area_cm2, 6.0, places=4)
            self.assertEqual(result.triangle_count, 12)

    def test_obj_materials(self):
        result = parser.analyse(samples.obj_two_materials(), 'cubes.obj')
        self.assertEqual(len(result.filaments), 2)
        self.assertEqual([f.name for f in result.filaments], ['Red', 'Blue'])
        self.assertAlmostEqual(result.volume_cm3, 2.0, places=4)

    def test_amf(self):
        result = parser.analyse(samples.amf_cube(), 'cube.amf')
        self.assertAlmostEqual(result.volume_cm3, 1.0, places=4)

    def test_sniff_without_extension(self):
        self.assertEqual(parser.detect_format(samples.stl_binary(), 'upload'), 'stl')
        self.assertEqual(parser.detect_format(samples.bgcode(), 'upload'), 'bgcode')
        self.assertEqual(parser.detect_format(samples.prusa_3mf_unsliced(), 'upload'), '3mf')
        self.assertEqual(parser.detect_format(samples.PRUSA_GCODE, 'upload'), 'gcode')

    def test_bad_files(self):
        with self.assertRaises(parser.PrintFileError):
            parser.analyse(b'', 'empty.stl')
        with self.assertRaises(parser.PrintFileError):
            parser.analyse(b'not a model', 'readme.txt')
        with self.assertRaises(parser.PrintFileError):
            parser.analyse(b'PK not a zip', 'broken.3mf')
