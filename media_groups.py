"""Fast media classification for the Hush Photo picker.

A MOV paired with a photo of the same stem in the same directory is classified
as Live Photos. This is a filename heuristic, not Apple asset-id verification.
"""
from pathlib import PurePosixPath

PHOTO_SUFFIXES=frozenset({'.heic','.heif','.jpg','.jpeg','.png','.dng','.tif','.tiff'})
VIDEO_SUFFIXES=frozenset({'.mov','.mp4'})

def group_suffixes(group):
    return VIDEO_SUFFIXES if group == 'Видео' else PHOTO_SUFFIXES

def selected_paths_for_group(items, group):
    suffixes=group_suffixes(group)
    return {x['path'] for x in items if x['suffix'].lower() in suffixes}

def photo_pair_index(items):
    """Build once in O(n), then use O(1) per video instead of scanning all items."""
    result=set()
    for item in items:
        p=PurePosixPath(item['path'])
        if p.suffix.lower() in PHOTO_SUFFIXES:
            result.add((str(p.parent).casefold(),p.stem.casefold()))
    return result

def is_live_photo_video(item, items=None, photo_index=None):
    p=PurePosixPath(item['path'])
    if p.suffix.lower() != '.mov':
        return False
    if photo_index is None:
        photo_index=photo_pair_index(items or [])
    return (str(p.parent).casefold(),p.stem.casefold()) in photo_index

def video_category(item, items=None, photo_index=None):
    return 'Live Photos' if is_live_photo_video(item,items,photo_index) else 'Видеоролики'

def matches_video_filter(item, items, video_filter, photo_index=None):
    return video_filter == 'Все видео' or video_category(item,items,photo_index) == video_filter
