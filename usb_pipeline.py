"""USB pipeline built on verified AFC; retain original HEIC/MOV; optionally make JPEG/TIFF.
JPEG is an SDR derivative. HDR original remains intact when mode=both/original.
"""
from pathlib import Path
from datetime import datetime
from safe_export import incremental_export,read_manifest,PHOTO_EXTS,live_pair_candidates,sha256_file,organize_verified_by_capture_date
from main import convert_image
import json

def transfer_and_convert(afc, items, selected, destination, options, progress, cancelled,folders='original'):
    destination=Path(destination)
    paths=sorted(live_pair_candidates(items,selected,options.copy_mov))
    # Explicitly selected videos are always preserved. copy_mov only governs
    # automatically attached Live Photo clips (handled by live_pair_candidates).
    # Export date folders only when a reliable capture timestamp can be parsed from existing media metadata.
    # AFC has no universal capture date in listing, so fall back to original directory structure.
    resolved_folders='original' if folders=='year-month' else folders
    stats=incremental_export(afc,paths,destination,progress,cancelled,folder_mode=resolved_folders)
    manifest=read_manifest(destination)
    if folders=='year-month':
        organize_verified_by_capture_date(destination,manifest)
        manifest=read_manifest(destination)
    derivatives=0
    errors=list(stats['failed'])
    if not stats['cancelled'] and options.mode in ('jpeg','both','tiff'):
        for index,source in enumerate(paths):
            if cancelled.is_set():stats['cancelled']=True;break
            if Path(source).suffix.lower() not in PHOTO_EXTS:continue
            entry=manifest['entries'].get(source)
            if not entry:continue
            original=destination/entry['destination']
            kind='tiff' if options.mode=='tiff' else 'jpeg'
            extension='.tiff' if kind=='tiff' else '.jpg'
            if kind=='jpeg' and original.suffix.lower() in ('.jpg','.jpeg'):continue
            derived=original.with_suffix(extension)
            try:
                # Avoid silently replacing an unrelated existing file.
                if derived.exists():
                    if derived.stat().st_mtime_ns>=original.stat().st_mtime_ns:continue
                    n=2
                    while derived.exists():
                        derived=original.with_name(f'{original.stem} ({n}){extension}');n+=1
                tmp=derived.with_name(derived.name+'.part')
                try:
                    convert_image(original,tmp,kind,options.quality)
                    tmp.replace(derived)
                finally:
                    tmp.unlink(missing_ok=True)
                derivatives+=1
            except Exception as e:errors.append(f'{source}: преобразование: {e}')
    # Never delete originals by default, including jpeg-only mode; safe archival policy.
    return (stats['copied']+stats['skipped'],len(paths),errors,stats['cancelled']),stats,derivatives
