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

    def test_scanning_device_card_shows_scanning_in_both_lines(self):
        self.app.usb_scanning=True
        self.app._set_iphone_state('scanning')
        self.assertEqual(self.app.connection_state,'scanning')
        self.assertIn('Поиск на iPhone',self.app.connection_badge.cget('text'))
        self.assertIn('Считываем медиатеку',self.app.source_name.cget('text'))
        self.assertNotIn('Подключите',self.app.source_name.cget('text'))

    def test_scan_complete_updates_device_card_to_ready(self):
        self.app.usb_items=[
            {'path':'DCIM/100APPLE/IMG_1.HEIC','name':'IMG_1.HEIC','suffix':'.heic'}]
        self.app.usb_scanning=True
        self.app._set_iphone_state('scanning')
        self.app.events.put(('usb_scan_done',self.app.scan_token))
        with mock.patch.object(self.app,'load_usb_previews'):
            self.app._poll_events()
        self.assertEqual(self.app.connection_state,'ready')
        self.assertIn('Медиатека загружена',self.app.connection_badge.cget('text'))
        self.assertIn('Файлов: 1',self.app.source_name.cget('text'))
        self.assertNotIn('Подключите',self.app.source_name.cget('text'))
        self.assertTrue(self.app.scanned)
        self.assertEqual(self.app.go.cget('state'),'normal')

    def test_export_completion_does_not_mark_phone_disconnected(self):
        self.app.usb_items=[
            {'path':'DCIM/100APPLE/IMG_1.HEIC','name':'IMG_1.HEIC','suffix':'.heic'}]
        self.app.selected={'DCIM/100APPLE/IMG_1.HEIC'}
        self.app.scanned=True
        self.app.draw_tiles()
        self.app._set_iphone_state('ready')
        self.app.set_running(True)
        self.app._set_iphone_state('exporting')
        self.assertIn('Копируем',self.app.source_name.cget('text'))
        self.app.events.put(('done',(1,1,[],False)))
        with mock.patch('modern_ui.messagebox.showinfo'):
            self.app._poll_events()
        self.assertEqual(self.app.connection_state,'exported')
        self.assertIn('Экспорт завершён',self.app.source_name.cget('text'))
        self.assertNotIn('Подключите',self.app.source_name.cget('text'))
        self.assertTrue(self.app.scanned)
        self.assertEqual(self.app.go.cget('state'),'normal')

    def test_cancelled_export_preserves_media_library(self):
        self.app.usb_items=[
            {'path':'DCIM/100APPLE/IMG_1.HEIC','name':'IMG_1.HEIC','suffix':'.heic'}]
        self.app.scanned=True
        self.app.selected={'DCIM/100APPLE/IMG_1.HEIC'}
        self.app.draw_tiles()
        self.app._set_iphone_state('exporting')
        self.app.events.put(('done',(0,1,[],True)))
        with mock.patch('modern_ui.messagebox.showinfo'):
            self.app._poll_events()
        self.assertEqual(self.app.connection_state,'export_cancelled')
        self.assertTrue(self.app.scanned)
        self.assertIn('Экспорт остановлен',self.app.source_name.cget('text'))
        self.assertEqual(self.app.go.cget('state'),'normal')

    def test_partial_non_usb_error_does_not_mark_device_offline(self):
        self.app.scanned=True
        self.app._set_iphone_state('exporting')
        self.app.events.put(('done',(3,4,['Ошибка конвертации JPEG'],False)))
        with mock.patch('modern_ui.messagebox.showinfo'):
            self.app._poll_events()
        self.assertEqual(self.app.connection_state,'export_errors')
        self.assertTrue(self.app.scanned)
        self.assertIn('завершён с ошибками',self.app.source_name.cget('text'))

    def test_non_connection_export_error_does_not_mark_usb_disconnected(self):
        self.app.scanned=True
        self.app._set_iphone_state('ready')
        self.app.events.put(('error','Ошибка преобразования JPEG'))
        with mock.patch('modern_ui.messagebox.showerror'):
            self.app._poll_events()
        self.assertEqual(self.app.connection_state,'transfer_error')
        self.assertNotIn('не отвечает',self.app.connection_badge.cget('text'))
        self.assertTrue(self.app.scanned)
        self.assertFalse(self.app._is_connection_error('Ошибка преобразования JPEG'))
        self.assertTrue(self.app._is_connection_error('iPhone disconnected'))

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
