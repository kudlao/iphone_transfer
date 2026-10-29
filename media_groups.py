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
