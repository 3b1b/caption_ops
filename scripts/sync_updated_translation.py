import argparse
import os
from pathlib import Path

from helpers import get_web_id_to_video_id_map
from helpers import get_web_id_to_caption_directory_map

from translate import sentence_translations_to_srt

from upload import get_youtube_api
from upload import upload_caption
from upload import upload_video_localizations

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Video url')
    parser.add_argument('translation_file_path_tail', type=str, help='Translation file path tail')
    args = parser.parse_args()

    web_id, language, file_name = args.translation_file_path_tail.split(os.sep)[-3:]

    os.sep.split()

    youtube_api = get_youtube_api()
    cap_dir = get_web_id_to_caption_directory_map()[web_id]
    video_id = get_web_id_to_video_id_map()[web_id]

    if file_name == "sentence_translations.json":
        trans_file = Path(cap_dir, language, file_name)
        new_srt = sentence_translations_to_srt(trans_file)
        upload_caption(youtube_api, video_id, new_srt, replace=True)
    elif file_name in ["title.json", "description.json"]:
        upload_video_localizations(youtube_api, cap_dir, video_id)
