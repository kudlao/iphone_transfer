import tempfile
import unittest
from io import BytesIO
from pathlib import Path
from PIL import Image
from preview_cache import (thumbnail_from_afc, cache_file, trim_cache,
                           clear_legacy_cache, clear_preview_cache, visible_preview_paths, MAX_CACHE_BYTES)

class FakeAFC:
    def __init__(self, data, fail=False):
        self.data=data
        self.calls=0
        self.fail=fail
    def read_to(self, path, dest, progress=None, cancelled=None):
        self.calls+=1
        if self.fail:
            Path(dest).write_bytes(b'partial')
            raise ConnectionError('USB disconnected')
        Path(dest).write_bytes(self.data)
        return len(self.data)

class PreviewCacheTests(unittest.TestCase):
    def image_bytes(self):
        img=Image.new('RGB', (1200, 800), 'blue')
        output=BytesIO(); img.save(output, format='PNG')
        return output.getvalue()

    def test_thumbnail_only_and_reuse(self):
        data=self.image_bytes(); afc=FakeAFC(data)
        with tempfile.TemporaryDirectory() as d:
            cache=Path(d)/'previews'
            first=thumbnail_from_afc(afc, 'DCIM/IMG_12.PNG', cache)
            with Image.open(first) as preview:
                self.assertLessEqual(max(preview.size),320)
                self.assertEqual(preview.format,'JPEG')
            self.assertEqual(list(cache.rglob('*')), [first])
            self.assertLess(first.stat().st_size,len(data))
            second=thumbnail_from_afc(afc,'DCIM/IMG_12.PNG',cache)
            self.assertEqual(first,second)
            self.assertEqual(afc.calls,1)

    def test_failure_leaves_no_cache_original(self):
        with tempfile.TemporaryDirectory() as d:
            cache=Path(d)/'previews'
            with self.assertRaises(ConnectionError):
                thumbnail_from_afc(FakeAFC(b'', fail=True),'DCIM/B.PNG',cache)
            self.assertEqual(list(cache.glob('*')),[])

    def test_visible_viewport_loads_more_on_scroll(self):
        cards=[(f'IMG_{i}.HEIC', i*185, 170) for i in range(12)]
        initial=visible_preview_paths(cards,top=0,viewport_height=350,margin=0)
        scrolled=visible_preview_paths(cards,top=740,viewport_height=350,margin=0)
        self.assertEqual(initial,['IMG_0.HEIC','IMG_1.HEIC'])
        self.assertEqual(scrolled,['IMG_4.HEIC','IMG_5.HEIC'])
        self.assertFalse(set(initial).intersection(scrolled))
        self.assertIn('IMG_3.HEIC',visible_preview_paths(
            cards,top=740,viewport_height=350,margin=160))

    def test_close_clears_owned_jpegs_and_partial_files_only(self):
        with tempfile.TemporaryDirectory() as d:
            cache=Path(d)/'previews'
            cache.mkdir()
            photo=cache_file(cache,'DCIM/100APPLE/IMG_1.HEIC')
            photo.write_bytes(b'jpeg-preview')
            part=Path(str(photo)+'.part')
            part.write_bytes(b'incomplete-preview')
            user_file=cache/'notes.txt'
            user_file.write_text('unrelated')
            external=Path(d)/'Exported-HEIC.heic'
            external.write_bytes(b'actual original')
            self.assertEqual(clear_preview_cache(cache),2)
            self.assertFalse(photo.exists())
            self.assertFalse(part.exists())
            self.assertTrue(user_file.exists())
            self.assertTrue(external.exists())
            self.assertEqual(clear_preview_cache(cache),0)

    def test_eviction_lru(self):
        with tempfile.TemporaryDirectory() as d:
            cache=Path(d)
            for n in range(3):
                p=cache/f'{n}.jpg'; p.write_bytes(b'x'*100)
                import os
                os.utime(p,(100+n,100+n))
            self.assertEqual(trim_cache(cache,max_bytes=200),200)
            self.assertFalse((cache/'0.jpg').exists())

    def test_legacy_cleanup_only_previews(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)/'previews'
            stale=root/'DCIM'/'100APPLE'/'IMG_1.HEIC'
            stale.parent.mkdir(parents=True); stale.write_bytes(b'old original')
            thumb=root/'known.jpg';thumb.write_bytes(b'jpeg')
            clear_legacy_cache(root)
            self.assertFalse(stale.exists())
            self.assertTrue(thumb.is_file())

if __name__=='__main__': unittest.main()
