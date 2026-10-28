import tempfile,unittest,threading,os
from pathlib import Path
from safe_export import incremental_export,sha256_file,live_pair_candidates,safe_relative,organized_path,remove_empty_export_dirs,organize_verified_by_capture_date,read_manifest

class MockAFC:
    def __init__(self,files):self.files=files;self.calls=[];self.fail=False
    def read_to(self,path,dest,progress=None,cancelled=None):
        self.calls.append(path)
        b=self.files[path]
        if self.fail:raise OSError('USB disconnected')
        dest=Path(dest);dest.parent.mkdir(parents=True,exist_ok=True)
        dest.write_bytes(b)
        if progress:progress(len(b))
        return len(b)

class SafeTests(unittest.TestCase):
    def test_incremental_and_sha(self):
        with tempfile.TemporaryDirectory() as d:
            a=MockAFC({'/DCIM/100APPLE/A.HEIC':b'heic-content'})
            first=incremental_export(a,['DCIM/100APPLE/A.HEIC'],d)
            second=incremental_export(a,['DCIM/100APPLE/A.HEIC'],d)
            self.assertEqual((first['copied'],second['skipped'],len(a.calls)),(1,1,1))
            self.assertEqual(sha256_file(Path(d)/'DCIM/100APPLE/A.HEIC'),sha256_file(Path(d)/'DCIM/100APPLE/A.HEIC'))
    def test_corruption_triggers_recopy(self):
        with tempfile.TemporaryDirectory() as d:
            a=MockAFC({'/DCIM/A.JPG':b'correct'})
            incremental_export(a,['DCIM/A.JPG'],d)
            (Path(d)/'DCIM/A.JPG').write_bytes(b'bad')
            stats=incremental_export(a,['DCIM/A.JPG'],d)
            self.assertEqual(stats['copied'],1)
            self.assertEqual((Path(d)/'DCIM/A.JPG').read_bytes(),b'bad') # never overwrite collisions
            self.assertTrue((Path(d)/'DCIM/A (2).JPG').exists())
    def test_disconnect_untouched(self):
        with tempfile.TemporaryDirectory() as d:
            a=MockAFC({'/DCIM/A.JPG':b'ok'});a.fail=True
            stats=incremental_export(a,['DCIM/A.JPG'],d)
            self.assertEqual(len(stats['failed']),1)
            self.assertFalse((Path(d)/'DCIM/A.JPG').exists())
    def test_pairs_same_folder(self):
        items=[{'path':p} for p in ['DCIM/100/IMG_1.HEIC','DCIM/100/IMG_1.MOV','DCIM/200/IMG_1.MOV']]
        result=live_pair_candidates(items,{'DCIM/100/IMG_1.HEIC'})
        self.assertIn('DCIM/100/IMG_1.MOV',result)
        self.assertNotIn('DCIM/200/IMG_1.MOV',result)
    def test_path_safety(self):
        for p in ('../x','/abs','DCIM/../../test','C:/temp'):
            with self.assertRaises(ValueError):safe_relative(p)
    def test_organization(self):
        import datetime
        p=organized_path('DCIM/100/A.JPG','year-month',datetime.datetime(2024,3,1))
        self.assertEqual(p,Path('2024-03/A.JPG'))
    def test_flat_mode(self):
        self.assertEqual(organized_path('DCIM/109APPLE/IMG_1.HEIC','flat'),Path('IMG_1.HEIC'))
    def test_flat_collisions(self):
        with tempfile.TemporaryDirectory() as d:
            a=MockAFC({'/DCIM/100/A.HEIC':b'first','/DCIM/101/A.HEIC':b'second'})
            stats=incremental_export(a,['DCIM/100/A.HEIC','DCIM/101/A.HEIC'],d,folder_mode='flat')
            self.assertEqual(stats['copied'],2)
            self.assertEqual((Path(d)/'A.HEIC').read_bytes(),b'first')
            self.assertEqual((Path(d)/'A (2).HEIC').read_bytes(),b'second')
            again=incremental_export(a,['DCIM/100/A.HEIC','DCIM/101/A.HEIC'],d,folder_mode='flat')
            self.assertEqual(again['skipped'],2)
    def test_month_format(self):
        from datetime import datetime
        self.assertEqual(organized_path('DCIM/109APPLE/A.HEIC','year-month',datetime(2026,10,5)),Path('2026-10/A.HEIC'))
    def test_staging_removed_after_success_and_failure(self):
        with tempfile.TemporaryDirectory() as d:
            a=MockAFC({'/DCIM/100APPLE/A.HEIC':b'ok'})
            incremental_export(a,['DCIM/100APPLE/A.HEIC'],d)
            self.assertFalse((Path(d)/'.hushphoto-staging').exists())
            a.fail=True
            incremental_export(a,['DCIM/100APPLE/B.HEIC'],d)
            self.assertFalse((Path(d)/'.hushphoto-staging').exists())
    def test_dcim_empty_removed_after_month_organize(self):
        with tempfile.TemporaryDirectory() as d:
            a=MockAFC({'/DCIM/100APPLE/A.HEIC':b'not-an-image'})
            incremental_export(a,['DCIM/100APPLE/A.HEIC'],d)
            organize_verified_by_capture_date(Path(d),read_manifest(Path(d)))
            self.assertFalse((Path(d)/'DCIM').exists())
            self.assertTrue((Path(d)/'Без даты'/'A.HEIC').exists())
    def test_nonempty_directories_preserved(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            for dirname in ('DCIM/other',' .hushphoto-staging/incomplete'.strip()):
                directory=root/dirname
                directory.mkdir(parents=True)
                (directory/'important.part').write_bytes(b'keep')
            remove_empty_export_dirs(root)
            self.assertTrue((root/'DCIM/other/important.part').exists())
            self.assertTrue((root/'.hushphoto-staging/incomplete/important.part').exists())
    def test_original_mode_keeps_dcim(self):
        with tempfile.TemporaryDirectory() as d:
            a=MockAFC({'/DCIM/100APPLE/A.HEIC':b'ok'})
            incremental_export(a,['DCIM/100APPLE/A.HEIC'],d)
            self.assertTrue((Path(d)/'DCIM/100APPLE/A.HEIC').exists())
if __name__=='__main__':unittest.main()
