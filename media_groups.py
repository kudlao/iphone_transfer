"""Media group rules for the Hush Photo picker.

MOV files belonging to Live Photos are also listed under Videos so users can
independently back up every video file if they choose. Group selections never
implicitly include files from the other group.
"""
PHOTO_SUFFIXES=frozenset({'.heic','.heif','.jpg','.jpeg','.png','.dng','.tif','.tiff'})
VIDEO_SUFFIXES=frozenset({'.mov','.mp4'})

def group_suffixes(group):
    return VIDEO_SUFFIXES if group == 'Видео' else PHOTO_SUFFIXES

def selected_paths_for_group(items, group):
    suffixes=group_suffixes(group)
    return {x['path'] for x in items if x['suffix'] in suffixes}

def is_live_photo_video(item, items):
    """A same-stem photo in the same DCIM directory suggests a Live Photo MOV.

    Conservative filename heuristic, not a definitive Apple asset identifier.
    """
    from pathlib import PurePosixPath
    p=PurePosixPath(item['path'])
    if p.suffix.lower() != '.mov':
        return False
    return any(
        PurePosixPath(other['path']).parent == p.parent
        and PurePosixPath(other['path']).stem.casefold() == p.stem.casefold()
        and other['suffix'].lower() in PHOTO_SUFFIXES
        for other in items
    )

def video_category(item, items):
    return 'Live Photos' if is_live_photo_video(item, items) else 'Видеоролики'

def matches_video_filter(item, items, video_filter):
    return video_filter == 'Все видео' or video_category(item, items) == video_filter
