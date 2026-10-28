"""Crash-safe, incrementally resumable file exports. No write access to phone.

Source is an AFC backend with read_to(path,destination, progress, cancelled).
AFCCommandLine itself may delete partials; retries restart the *current* file.
Completed and SHA-256 verified files are not transferred again.
"""
from __future__ import annotations
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from datetime import datetime
import hashlib
import json
import os
import shutil
import threading
import time

MEDIA_EXTS={'.heic','.heif','.jpg','.jpeg','.png','.tif','.tiff','.dng','.mov','.mp4','.aae'}
PHOTO_EXTS={'.heic','.heif','.jpg','.jpeg','.png','.tif','.tiff','.dng'}

def sha256_file(path:Path)->str:
    sha=hashlib.sha256()
    with open(path,'rb') as f:
        for data in iter(lambda:f.read(1024*1024),b''):sha.update(data)
    return sha.hexdigest()

def safe_relative(path:str)->Path:
    p=PurePosixPath(path)
    if not path or p.is_absolute() or '..' in p.parts or any(':' in x or '\\' in x for x in p.parts):
        raise ValueError('Небезопасный путь iPhone')
    return Path(*p.parts)

def read_manifest(dest:Path)->dict:
    path=dest/'.hushphoto-manifest.json'
    if not path.exists():return {'version':1,'entries':{}}
    try:
        obj=json.loads(path.read_text(encoding='utf-8'))
        return obj if obj.get('version')==1 and isinstance(obj.get('entries'),dict) else {'version':1,'entries':{}}
    except (OSError,ValueError):return {'version':1,'entries':{}}

def write_manifest(dest:Path,obj:dict):
    path=dest/'.hushphoto-manifest.json'
    tmp=path.with_suffix('.json.tmp')
    tmp.write_text(json.dumps(obj,ensure_ascii=False,indent=2),encoding='utf-8')
    os.replace(tmp,path)

def organized_path(source:str,folder_mode:str='original',taken_date=None)->Path:
    rel=safe_relative(source)
    if folder_mode=='original':return rel
    if folder_mode=='year-month':
        dt=taken_date or datetime.now()
        return Path(f'{dt.year:04d}-{dt.month:02d}',rel.name)
    if folder_mode=='flat':return Path(rel.name)
    raise ValueError('Неизвестный режим каталогов')

def collision_safe(path:Path,sha:str):
    if not path.exists():return path
    if sha256_file(path)==sha:return path
    i=2
    while True:
        new=path.with_name(f'{path.stem} ({i}){path.suffix}')
        if not new.exists() or sha256_file(new)==sha:return new
        i+=1

def remove_empty_export_dirs(dest_root:Path):
    """Remove only empty, app-created staging/DCIM directories.

    Never recursively delete files: incomplete exports or files not managed by
    Hush Photo must remain untouched. Do not follow directory symlinks.
    """
    dest_root=Path(dest_root)
    for dirname in ('.hushphoto-staging', 'DCIM'):
        base=dest_root/dirname
        if not base.is_dir() or base.is_symlink():
            continue
        dirs=sorted((p for p in base.rglob('*') if p.is_dir() and not p.is_symlink()),
                    key=lambda x:len(x.parts),reverse=True)
        for directory in [*dirs,base]:
            try:
                directory.rmdir()  # succeeds only if empty
            except OSError:
                pass

def copy_verified(afc,source:str,dest_root:Path,manifest:dict,progress=None,cancelled=None,folder_mode='original',taken_date=None):
    rel=organized_path(source,folder_mode,taken_date)
    dest=dest_root/rel
    previous=manifest['entries'].get(source)
    if previous:
        old=dest_root/safe_relative(previous['destination'])
        if old.is_file() and old.stat().st_size==previous['size'] and sha256_file(old)==previous['sha256']:
            return 'skipped',old,0
    dest.parent.mkdir(parents=True,exist_ok=True)
    # Always write to staging first; a failed AFC transfer must not alter an existing export.
    staging=dest_root/'.hushphoto-staging'/rel
    staging.parent.mkdir(parents=True,exist_ok=True)
    if staging.exists():staging.unlink()
    try:
        transferred=afc.read_to('/'+source.lstrip('/'),staging,progress,cancelled)
        if cancelled is not None and cancelled.is_set():raise InterruptedError('Отменено')
        if not staging.is_file():raise IOError('Источник не был сохранён')
        if transferred!=staging.stat().st_size:raise IOError('Размер передачи не совпадает')
        digest=sha256_file(staging)
        # If file with same name exists, do not overwrite unless its content is identical.
        final=collision_safe(dest,digest)
        if final.exists():staging.unlink()
        else:os.replace(staging,final)
        manifest['entries'][source]={'destination':str(final.relative_to(dest_root)).replace('\\','/'),
           'sha256':digest,'size':final.stat().st_size,'exported_at':datetime.now().isoformat()}
        write_manifest(dest_root,manifest)
        return 'copied',final,transferred
    finally:
        if staging.exists():staging.unlink()

def incremental_export(afc,paths,destination,progress=None,cancelled=None,folder_mode='original',dates=None):
    destination=Path(destination);destination.mkdir(parents=True,exist_ok=True)
    manifest=read_manifest(destination); stats={'copied':0,'skipped':0,'failed':[],'cancelled':False,'bytes':0}
    total=len(paths);started=time.monotonic()
    for index,path in enumerate(paths):
        if cancelled is not None and cancelled.is_set():stats['cancelled']=True;break
        try:
            progress and progress(stats['bytes'],0,path,index,total)
            status,out,size=copy_verified(afc,path,destination,manifest,
                lambda n:progress and progress(stats['bytes']+n,0,path,index,total),cancelled,
                folder_mode,(dates or {}).get(path))
            stats[status]+=1;stats['bytes']+=size
        except InterruptedError:
            stats['cancelled']=True;break
        except Exception as e:stats['failed'].append(f'{path}: {e}')
        progress and progress(stats['bytes'],0,path,index+1,total)
    remove_empty_export_dirs(destination)
    report=destination/'hushphoto_last_export.json'
    report.write_text(json.dumps({'date':datetime.now().isoformat(),'total':total,**stats},ensure_ascii=False,indent=2),encoding='utf-8')
    return stats

def live_pair_candidates(items,selected,include_mov=True):
    """Conservative: same stem AND directory. Never pair across folders.
    Metadata content identifiers require an additional native parser and are not inferred.
    """
    result=set(selected)
    by_key={}
    for item in items:
        p=PurePosixPath(item['path'])
        by_key.setdefault((str(p.parent).casefold(),p.stem.casefold()),[]).append(item['path'])
    if include_mov:
        for selected_path in list(selected):
            p=PurePosixPath(selected_path)
            if p.suffix.lower() in PHOTO_EXTS:
                result.update(x for x in by_key.get((str(p.parent).casefold(),p.stem.casefold()),[]) if PurePosixPath(x).suffix.lower()=='.mov')
    return result


def capture_datetime(path:Path):
    """Capture timestamp from photo metadata, never filesystem modification time."""
    from PIL import Image
    try:
        with Image.open(path) as image:
            ex = image.getexif()
            raw = ex.get(36867) or ex.get(306)
            try:raw = ex.get_ifd(0x8769).get(36867) or raw
            except (KeyError, AttributeError):pass
        if raw:
            return datetime.strptime(str(raw)[:19], '%Y:%m:%d %H:%M:%S')
    except (OSError,ValueError,TypeError):pass
    return None

def organize_verified_by_capture_date(destination:Path, manifest:dict):
    """Move verified originals by EXIF capture date (fallback: do not move).
    MOV pairs inherit date from same-stem image only; unverified/corrupt entries ignored.
    """
    from PIL import Image
    dest=Path(destination)
    dates={}
    for source,entry in manifest['entries'].items():
        if Path(source).suffix.lower() not in PHOTO_EXTS:continue
        path=dest/safe_relative(entry['destination'])
        if not path.exists() or sha256_file(path)!=entry['sha256']:continue
        dt=capture_datetime(path)
        if dt:dates[source]=dt
    for source in list(manifest['entries']):
        if source in dates:continue
        p=PurePosixPath(source)
        if p.suffix.lower()=='.mov':
            matches=[v for k,v in dates.items() if PurePosixPath(k).parent==p.parent and PurePosixPath(k).stem.casefold()==p.stem.casefold()]
            if len(matches)==1:dates[source]=matches[0]
    moved=0
    for source in list(manifest['entries']):
        dt=dates.get(source)
        if dt is None:
            # Unknown capture date: do not fabricate a month.
            folder='Без даты'
        else:
            folder=f'{dt.year:04d}-{dt.month:02d}'
        entry=manifest['entries'][source]; old=dest/safe_relative(entry['destination'])
        if not old.is_file() or sha256_file(old)!=entry['sha256']:continue
        proposed=dest/folder/old.name
        proposed.parent.mkdir(parents=True,exist_ok=True)
        target=collision_safe(proposed,entry['sha256'])
        if target!=old:
            if target.exists():old.unlink()
            else:os.replace(old,target)
            entry['destination']=str(target.relative_to(dest)).replace('\\','/')
            moved+=1
    if moved:write_manifest(dest,manifest)
    remove_empty_export_dirs(dest)
    return moved
