"""Headed Windows GUI smoke tests catch Tk geometry-manager regressions."""
import sys
import unittest
from unittest import mock


@unittest.skipUnless(sys.platform == 'win32', 'Requires a Windows GUI session')
class LayoutTests(unittest.TestCase):
    def setUp(self):
        from modern_ui import App
        with mock.patch('preview_cache.clear_legacy_cache'), mock.patch('preview_cache.trim_cache'):
            self.app = App()
        self.app.withdraw()

    def tearDown(self):
        self.app.destroy()

    def test_welcome_screen_shows_primary_action(self):
        self.assertTrue(self.app.empty.winfo_manager())
        self.assertFalse(self.app.preview._parent_frame.winfo_manager())
        self.assertEqual(self.app.go.cget('state'), 'disabled')

    def test_discovery_renders_library_without_tcl_pack_error(self):
        self.app.usb_items = [
            {'path': 'DCIM/100APPLE/IMG_0001.HEIC',
             'name': 'IMG_0001.HEIC', 'suffix': '.heic'},
            {'path': 'DCIM/100APPLE/VIDEO_0001.MOV',
             'name': 'VIDEO_0001.MOV', 'suffix': '.mov'}
        ]
        self.app.scanned = True
        self.app.selected = {'DCIM/100APPLE/IMG_0001.HEIC'}
        self.app.draw_tiles()
        self.app.update_idletasks()
        self.assertTrue(self.app.preview._parent_frame.winfo_manager())
        self.assertTrue(self.app.pager.winfo_manager())
        self.assertFalse(self.app.empty.winfo_manager())
        self.assertEqual(self.app.go.cget('state'), 'normal')
        self.app.group.set('Видео')
        self.app.group_changed()
        self.app.update_idletasks()
        self.assertTrue(self.app.preview._parent_frame.winfo_manager())

    def test_video_filter_updates_export_button_and_actual_file_scope(self):
        from media_groups import photo_pair_index

        self.app.usb_items = [
            {'path':'DCIM/100APPLE/IMG_1.HEIC','name':'IMG_1.HEIC','suffix':'.heic'},
            {'path':'DCIM/100APPLE/IMG_1.MOV','name':'IMG_1.MOV','suffix':'.mov'},
            {'path':'DCIM/100APPLE/CLIP.MOV','name':'CLIP.MOV','suffix':'.mov'},
        ]
        self.app.photo_index=photo_pair_index(self.app.usb_items)
        self.app.scanned=True
        self.app.group.set('Видео')
        self.app.group_changed()
        self.assertEqual(len(self.app._current_export_paths()),2)
        self.assertIn('2',self.app.go.cget('text'))

        self.app.video_filter.set('Видеоролики')
        self.app.video_filter_changed()
        self.assertEqual(self.app._current_export_paths(),{'DCIM/100APPLE/CLIP.MOV'})
        self.assertIn('1',self.app.go.cget('text'))
        self.assertEqual(self.app.go.cget('state'),'normal')

        self.app.selected.discard('DCIM/100APPLE/CLIP.MOV')
        self.app.draw_tiles()
        self.assertEqual(self.app._current_export_paths(),set())
        self.assertEqual(self.app.go.cget('state'),'disabled')

        self.app.video_filter.set('Live Photos')
        self.app.video_filter_changed()
        self.assertEqual(self.app._current_export_paths(),{'DCIM/100APPLE/IMG_1.MOV'})
        self.assertIn('1',self.app.go.cget('text'))

    def test_scan_failure_does_not_enable_partial_export(self):
        self.app.usb_items = [
            {'path':'DCIM/100APPLE/A.HEIC',
             'name':'A.HEIC', 'suffix':'.heic'}]
        self.app.selected = {'DCIM/100APPLE/A.HEIC'}
        self.app.scan_error = 'iPhone disconnected'
        self.app.draw_tiles()
        self.app.update_idletasks()
        self.assertTrue(self.app.empty.winfo_manager())
        self.assertEqual(self.app.go.cget('state'), 'disabled')


if __name__ == '__main__':
    unittest.main()
