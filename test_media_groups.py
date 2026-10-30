import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from threading import Event

from media_groups import group_suffixes, selected_paths_for_group
from main import ExportOptions, export_directory
from safe_export import live_pair_candidates
from usb_pipeline import transfer_and_convert


class MediaGroupTests(unittest.TestCase):
    def test_photo_and_video_group_selection(self):
        items = [
            {'path':'DCIM/100APPLE/IMG_1.HEIC','suffix':'.heic'},
            {'path':'DCIM/100APPLE/IMG_1.MOV','suffix':'.mov'},
            {'path':'DCIM/100APPLE/VID_2.MP4','suffix':'.mp4'},
        ]
        self.assertEqual(selected_paths_for_group(items, 'Фото'), {'DCIM/100APPLE/IMG_1.HEIC'})
        self.assertEqual(selected_paths_for_group(items, 'Видео'), {'DCIM/100APPLE/IMG_1.MOV','DCIM/100APPLE/VID_2.MP4'})
        self.assertTrue(group_suffixes('Фото').isdisjoint(group_suffixes('Видео')))

    def test_video_subgroups_and_same_folder(self):
        from media_groups import video_category, matches_video_filter
        items=[
            {'path':'DCIM/100APPLE/IMG_1.HEIC','suffix':'.heic'},
            {'path':'DCIM/100APPLE/IMG_1.MOV','suffix':'.mov'},
            {'path':'DCIM/100APPLE/VID_2.MOV','suffix':'.mov'},
            {'path':'DCIM/200APPLE/VID_2.HEIC','suffix':'.heic'},
            {'path':'DCIM/100APPLE/CLIP.MP4','suffix':'.mp4'},
        ]
        self.assertEqual(video_category(items[1],items),'Live Photos')
        self.assertEqual(video_category(items[2],items),'Видеоролики')
        self.assertEqual(video_category(items[4],items),'Видеоролики')
        self.assertTrue(matches_video_filter(items[1],items,'Live Photos'))
        self.assertFalse(matches_video_filter(items[1],items,'Видеоролики'))
        self.assertTrue(matches_video_filter(items[4],items,'Все видео'))

    def test_local_video_only_does_not_copy_photos(self):
        with TemporaryDirectory() as tmp:
            src=Path(tmp)/'src'; dst=Path(tmp)/'dst'
            src.mkdir(); dst.mkdir()
            (src/'photo.heic').write_bytes(b'not a real photo')
            (src/'video.mov').write_bytes(b'video content')
            (src/'second.mp4').write_bytes(b'mp4 content')
            selected={src/'video.mov',src/'second.mp4'}
            done,total,errors,cancelled=export_directory(src,dst,ExportOptions('original',copy_mov=False),lambda *_:None,selected_paths=selected)
            self.assertEqual((done,total,errors,cancelled),(2,2,[],False))
            self.assertEqual((dst/'video.mov').read_bytes(),b'video content')
            self.assertEqual((dst/'second.mp4').read_bytes(),b'mp4 content')
            self.assertFalse((dst/'photo.heic').exists())

    def test_explicit_mov_is_not_dropped_when_live_mov_disabled(self):
        class FakeAfc:
            def read_to(self, source, dest, progress, cancelled):
                dest.parent.mkdir(parents=True,exist_ok=True)
                dest.write_bytes(b'raw-video')
                return len(b'raw-video')
        items=[{'path':'DCIM/100APPLE/CLIP.MOV','suffix':'.mov'}]
        with TemporaryDirectory() as tmp:
            result,stats,converted=transfer_and_convert(
                FakeAfc(),items,{'DCIM/100APPLE/CLIP.MOV'},Path(tmp),
                ExportOptions('original',copy_mov=False),lambda *_:None,Event())
            self.assertEqual(result[:2],(1,1))
            self.assertEqual(converted,0)
            self.assertEqual((Path(tmp)/'DCIM/100APPLE/CLIP.MOV').read_bytes(),b'raw-video')

    def test_live_photo_pairing_remains_optional(self):
        items=[{'path':'DCIM/a.heic'},{'path':'DCIM/a.mov'}]
        self.assertEqual(live_pair_candidates(items,{'DCIM/a.heic'},True),{'DCIM/a.heic','DCIM/a.mov'})
        self.assertEqual(live_pair_candidates(items,{'DCIM/a.heic'},False),{'DCIM/a.heic'})


if __name__=='__main__':
    unittest.main()
