import argparse
from pathlib import Path

from helpers import get_web_id_to_video_id_map
from helpers import get_web_id_to_caption_directory_map

from translate import sentence_translations_to_srt

from upload import get_youtube_api
from upload import upload_caption

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Video url')
    parser.add_argument('web_id', type=str, help='Website id')
    parser.add_argument('language', type=str, help='language')
    args = parser.parse_args()

    cap_dir = get_web_id_to_caption_directory_map()[args.web_id]
    trans_file = Path(cap_dir, args.language.lower(), "sentence_translations.json")
    video_id = get_web_id_to_video_id_map()[args.web_id]

    youtube_api = get_youtube_api()
    new_srt = sentence_translations_to_srt(trans_file)
    upload_caption(youtube_api, video_id, new_srt, replace=True)
