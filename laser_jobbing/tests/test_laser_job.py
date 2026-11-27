# -*- coding: utf-8 -*-
import io

from PIL import Image

from odoo.exceptions import AccessError, UserError, ValidationError
from odoo.tests import tagged

from ..models.laser_template import binary_bytes
from ..tools import raster_tools
from .common import SVG_BASE, LaserCase, b64, picture


@tagged('post_install', '-at_install')
class TestLaserJob(LaserCase):

    def test_values_follow_template(self):
        job = self.make_job(self.engrave_template)
        self.assertEqual(job.value_ids.element_id, self.engrave_template.element_ids)
        self.assertEqual(self.value(job, 'Name').text_value, 'Your Name')
        self.assertTrue(job.name.startswith('LJ/'))

    def test_engraving_keeps_uploaded_format(self):
        for ext in ('png', 'jpg', 'jpeg', 'bmp', 'webp', 'tif', 'tiff', 'gif'):
            with self.subTest(ext=ext):
                job = self.make_job(self.engrave_template)
                self.value(job, 'Photo').write({'image': b64(picture(ext)), 'image_filename': 'me.%s' % ext})
                self.assertFalse(job.output_error)
                self.assertEqual(job.output_format, ext)
                self.assertTrue(job.output_filename.endswith('.' + ext))
                image = Image.open(io.BytesIO(binary_bytes(job, 'output_file')))
                self.assertEqual(image.size, (236, 157))  # 60 x 40 mm at 100 dpi

    def test_engraving_without_upload_uses_base_format(self):
        job = self.make_job(self.engrave_template)
        self.assertEqual(job.output_format, 'png')

    def test_heic(self):
        template = self.engrave_template.copy({'base_file': False, 'base_filename': False})
        template.element_ids.filtered(lambda e: e.element_type == 'text').unlink()
        job = self.make_job(template)
        heic = b'\x00\x00\x00\x18ftypheic' + b'\x00' * 64
        self.value(job, 'Photo').write({'image': b64(heic), 'image_filename': 'phone.heic'})
        if raster_tools.HEIF_SUPPORTED:
            self.skipTest('pillow-heif installed: real HEIC files are read')
        # Without pillow-heif a lone HEIC picture is passed through unchanged...
        self.assertEqual(job.output_format, 'heic')
        self.assertEqual(binary_bytes(job, 'output_file'), heic)
        # ...but it can't be combined with text.
        job2 = self.make_job(self.engrave_template)
        self.value(job2, 'Photo').write({'image': b64(heic), 'image_filename': 'phone.heic'})
        self.assertFalse(job2.output_file)
        self.assertIn('pillow-heif', job2.output_error)

    def test_cutting_makes_sanitised_svg(self):
        job = self.make_job(self.cut_template)
        self.value(job, 'Initials').text_value = 'XYZ'
        self.value(job, 'Logo').write({'image': b64(SVG_BASE), 'image_filename': 'logo.svg'})
        self.assertEqual(job.output_format, 'svg')
        data = binary_bytes(job, 'output_file')
        self.assertTrue(data.startswith(b'<?xml'))
        self.assertIn(b'width="80mm"', data)
        self.assertNotIn(b'<script', data)
        self.assertNotIn(b'example.com', data)

    def test_cutting_rejects_pictures(self):
        job = self.make_job(self.cut_template)
        with self.assertRaises(ValidationError):
            self.value(job, 'Logo').write({'image': b64(picture('png')), 'image_filename': 'logo.png'})

    def test_engraving_rejects_other_files(self):
        job = self.make_job(self.engrave_template)
        with self.assertRaises(ValidationError):
            self.value(job, 'Photo').write({'image': b64(b'%PDF-1.4'), 'image_filename': 'photo.pdf'})
        with self.assertRaises(ValidationError):
            self.value(job, 'Photo').write({'image': b64(b'not a picture'), 'image_filename': 'photo.png'})

    def test_base_file_must_match_operation(self):
        with self.assertRaises(ValidationError):
            self.env['laser.template'].create({
                'name': 'Wrong', 'operation': 'cut', 'base_file': b64(picture('png')), 'base_filename': 'x.png',
            })
        with self.assertRaises(ValidationError):
            self.env['laser.template'].create({
                'name': 'Wrong', 'operation': 'engrave', 'base_file': b64(SVG_BASE), 'base_filename': 'x.svg',
            })

    def test_text_limit(self):
        job = self.make_job(self.engrave_template)
        with self.assertRaises(ValidationError):
            self.value(job, 'Name').text_value = 'x' * 21

    def test_workflow(self):
        job = self.make_job(self.engrave_template)
        self.value(job, 'Name').text_value = False
        with self.assertRaises(UserError):
            job.action_confirm()
        self.value(job, 'Name').text_value = 'Alex'
        job.action_confirm()
        self.assertEqual(job.state, 'confirmed')
        job.action_start()
        self.assertEqual(job.state, 'in_progress')
        job.action_done()
        self.assertEqual(job.state, 'done')
        self.assertTrue(job.date_done)
        self.assertEqual(job.personalisation_summary, 'Name: Alex')

    def test_editing_remakes_the_file(self):
        job = self.make_job(self.engrave_template)
        before = binary_bytes(job, 'output_file')
        job.write({'value_ids': [(1, self.value(job, 'Name').id, {'text_value': 'Someone else'})]})
        self.assertNotEqual(binary_bytes(job, 'output_file'), before)

    def test_open_jobs_follow_template(self):
        job = self.make_job(self.engrave_template)
        done = self.make_job(self.engrave_template)
        done.action_done()
        before = binary_bytes(job, 'output_file')
        self.engrave_template.write({'element_ids': [(0, 0, {
            'name': 'Date', 'element_type': 'text', 'default_text': '07/11/2026',
            'x_mm': 5, 'y_mm': 30, 'width_mm': 30, 'height_mm': 8,
        })]})
        self.assertIn('Date', job.value_ids.element_id.mapped('name'))
        self.assertNotEqual(binary_bytes(job, 'output_file'), before)
        self.assertNotIn('Date', done.value_ids.element_id.mapped('name'))
        self.engrave_template.element_ids.filtered(lambda e: e.name == 'Name').x_mm = 1
        self.assertEqual(len(job.value_ids), 3)

    def test_editor_data(self):
        data = self.engrave_template.laser_editor_data(customer_only=True)
        self.assertEqual(data['width'], 60)
        self.assertEqual([e['name'] for e in data['elements']], ['Name', 'Photo'])
        self.assertIn('/laser_jobbing/template/', data['base_url'])

    def test_settings(self):
        settings = self.env['res.config.settings'].create({
            'laser_visual_editor_internal': True,
            'laser_visual_editor_portal': True,
        })
        settings.execute()
        params = self.env['ir.config_parameter'].sudo()
        self.assertEqual(params.get_param('laser_jobbing.visual_editor_internal'), 'True')
        self.assertEqual(params.get_param('laser_jobbing.visual_editor_portal'), 'True')
        self.assertTrue(self.engrave_template.laser_visual_editor)


@tagged('post_install', '-at_install')
class TestLaserAccess(LaserCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        Users = cls.env['res.users'].with_context(no_reset_password=True)
        cls.owner = Users.create({
            'name': 'Owner', 'login': 'laser_owner',
            'group_ids': [(6, 0, [cls.env.ref('laser_jobbing.group_laser_job_edit_own').id])],
        })
        cls.other = Users.create({
            'name': 'Other', 'login': 'laser_other',
            'group_ids': [(6, 0, [cls.env.ref('laser_jobbing.group_laser_job_edit_own').id])],
        })
        cls.nobody = Users.create({
            'name': 'Nobody', 'login': 'laser_nobody',
            'group_ids': [(6, 0, [cls.env.ref('laser_jobbing.group_laser_user').id])],
        })

    def test_own_jobs_only(self):
        job = self.env['laser.job'].with_user(self.owner).create({'template_id': self.engrave_template.id})
        job.with_user(self.owner).read(['name'])
        job.with_user(self.owner).value_ids.read(['text_value'])
        with self.assertRaises(AccessError):
            job.with_user(self.other).read(['name'])
        with self.assertRaises(AccessError):
            job.with_user(self.owner).unlink()

    def test_no_permission_no_access(self):
        job = self.make_job(self.engrave_template)
        with self.assertRaises(AccessError):
            job.with_user(self.nobody).read(['name'])
        with self.assertRaises(AccessError):
            self.env['laser.job'].with_user(self.nobody).create({'template_id': self.engrave_template.id})

    def test_templates_read_only_for_users(self):
        self.engrave_template.with_user(self.owner).read(['name'])
        with self.assertRaises(AccessError):
            self.engrave_template.with_user(self.owner).write({'name': 'Changed'})
