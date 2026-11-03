"""Headed Windows GUI smoke tests catch Tk geometry-manager regressions."""
import sys
import tempfile
from pathlib import Path
from PIL import Image
import unittest
from unittest import mock


@unittest.skipUnless(sys.platform == 'win32', 'Requires a Windows GUI session')
class LayoutTests(unittest.TestCase):
    def setUp(self):
        from modern_ui import App
        with mock.patch('preview_cache.clear_preview_cache'):
            self.app = App()
        self.app.withdraw()

    def tearDown(self):
        if self.app.winfo_exists():
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

    def test_preview_is_painted_without_resetting_scroll_or_selection(self):
        with tempfile.TemporaryDirectory() as d:
            filename=Path(d)/'preview.jpg'
            Image.new('RGB',(120,100),'blue').save(filename)
            key='DCIM/100APPLE/IMG_1.HEIC'
            self.app.usb_items=[{'path':key,'name':'IMG_1.HEIC','suffix':'.heic'}]
            self.app.scanned=True
            self.app.selected={key}
            self.app.draw_tiles()
            self.app.update_idletasks()
            label=self.app.usb_tile_labels[key]
            before=self.app.preview._parent_canvas.yview()
            self.app._paint_usb_thumbnail(key,filename)
            self.app.update_idletasks()
            self.assertTrue(label.cget('image'))
            self.assertEqual(before,self.app.preview._parent_canvas.yview())
            self.assertTrue(self.app.tile_checks[0].get())
            self.assertTrue(self.app.preview._parent_frame.winfo_manager())

    def test_window_close_clears_only_preview_cache(self):
        from preview_cache import cache_file
        with tempfile.TemporaryDirectory() as d:
            self.app.preview_cache=Path(d)/'previews'
            self.app.preview_cache.mkdir()
            cached=cache_file(self.app.preview_cache,'DCIM/IMG_1.HEIC')
            cached.write_bytes(b'preview')
            original=Path(d)/'original.heic'
            original.write_bytes(b'original')
            self.app.close_app()
            self.assertFalse(cached.exists())
            self.assertTrue(original.exists())
            self.assertFalse(self.app.winfo_exists())

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
        self.assertEqual(self.app.go.cget('text'),'Экспортировать')
        self.assertEqual(self.app.count.cget('text'),'Выбрано: 2')

        self.app.video_filter.set('Видеоролики')
        self.app.video_filter_changed()
        self.assertEqual(self.app._current_export_paths(),{'DCIM/100APPLE/CLIP.MOV'})
        self.assertEqual(self.app.go.cget('text'),'Экспортировать')
        self.assertEqual(self.app.count.cget('text'),'Выбрано: 1')
        self.assertEqual(self.app.go.cget('state'),'normal')

        self.app.selected.discard('DCIM/100APPLE/CLIP.MOV')
        self.app.draw_tiles()
        self.assertEqual(self.app._current_export_paths(),set())
        self.assertEqual(self.app.go.cget('state'),'disabled')

        self.app.video_filter.set('Live Photos')
        self.app.video_filter_changed()
        self.assertEqual(self.app._current_export_paths(),{'DCIM/100APPLE/IMG_1.MOV'})
        self.assertEqual(self.app.go.cget('text'),'Экспортировать')
        self.assertEqual(self.app.count.cget('text'),'Выбрано: 1')

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
        self.app._poll_events()
        self.assertEqual(self.app.connection_state,'ready')
        self.assertIn('Медиатека загружена',self.app.connection_badge.cget('text'))
        self.assertIn('Можно выбирать и экспортировать',self.app.source_name.cget('text'))
        self.assertNotIn('1',self.app.source_name.cget('text'))
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

    def test_true_usb_disconnect_requires_rescan_but_conversion_error_does_not(self):
        self.app.usb_items=[
            {'path':'DCIM/100APPLE/IMG_1.HEIC','name':'IMG_1.HEIC','suffix':'.heic'}]
        self.app.scanned=True
        self.app.selected={'DCIM/100APPLE/IMG_1.HEIC'}
        self.app.draw_tiles()
        self.app.events.put(('error','iPhone disconnected'))
        with mock.patch('modern_ui.messagebox.showerror'):
            self.app._poll_events()
        self.assertEqual(self.app.connection_state,'disconnected')
        self.assertFalse(self.app.scanned)
        self.assertEqual(self.app.go.cget('state'),'disabled')
        self.assertFalse(self.app.selected)
        self.assertIn('iPhone не отвечает',self.app.connection_badge.cget('text'))
        self.assertTrue(self.app.empty.winfo_manager())

    def test_device_is_auto_scanned_once_per_connection(self):
        with mock.patch.object(self.app,'refresh') as refresh:
            self.app._handle_device_presence(True)
            self.app._handle_device_presence(True)
            refresh.assert_called_once_with()
            self.assertTrue(self.app._device_connected)

    def test_auto_detection_retries_after_unlock_with_a_bound(self):
        self.app._device_connected=True
        self.app.scan_error='Trust not yet accepted'
        self.app.connection_state='error'
        self.app._auto_scan_retry_after=0
        self.app._auto_scan_retry_count=0
        with mock.patch.object(self.app,'refresh') as refresh:
            self.app._handle_device_presence(True)
            refresh.assert_called_once_with()
            self.assertEqual(self.app._auto_scan_retry_count,1)
            refresh.reset_mock()
            self.app._handle_device_presence(True)
            refresh.assert_not_called()
            self.app._auto_scan_retry_after=0
            self.app._auto_scan_retry_count=2
            self.app._handle_device_presence(True)
            refresh.assert_not_called()

    def test_unplug_needs_two_observations_before_reset(self):
        self.app.usb_items=[
            {'path':'DCIM/100APPLE/IMG_1.HEIC',
             'name':'IMG_1.HEIC','suffix':'.heic'}]
        self.app.selected={'DCIM/100APPLE/IMG_1.HEIC'}
        self.app.scanned=True
        self.app._device_connected=True
        self.app._set_iphone_state('ready')
        self.app.draw_tiles()
        self.app._handle_device_presence(False)
        self.assertTrue(self.app.scanned)
        self.app._handle_device_presence(False)
        self.assertFalse(self.app.scanned)
        self.assertEqual(self.app.connection_state,'disconnected')
        with mock.patch.object(self.app,'refresh') as refresh:
            self.app._handle_device_presence(True)
            refresh.assert_called_once_with()

    def test_cancelled_search_does_not_auto_restart_until_replug(self):
        self.app.usb_scanning=True
        self.app.stop_scan()
        self.assertTrue(self.app._auto_scan_suppressed)
        self.app.usb_scanning=False
        with mock.patch.object(self.app,'refresh') as refresh:
            self.app._handle_device_presence(True)
            refresh.assert_not_called()

    def test_minimal_counts_are_shown_once(self):
        self.app.usb_items=[
            {'path':f'DCIM/100APPLE/IMG_{i}.MOV',
             'name':f'IMG_{i}.MOV','suffix':'.mov'} for i in range(71)]
        self.app.scanned=True
        self.app.group.set('Видео')
        self.app.video_filter.set('Видеоролики')
        self.app.group_changed()
        self.assertEqual(self.app.count.cget('text'),'Выбрано: 71')
        self.assertEqual(self.app.go.cget('text'),'Экспортировать')
        self.assertNotIn('71',self.app.page_info.cget('text'))
        self.assertNotIn('71',self.app.source_name.cget('text'))

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
