import argparse
import os

from pathlib import Path

from scripts.sync_all_captions import convert_to_url
from scripts.sync_all_captions import sync_srts_to_translations

from helpers import get_web_id_to_video_id_map
from helpers import url_to_directory
from helpers import extract_video_id

from upload import get_youtube_api
from upload import upload_caption
from upload import upload_video_localizations


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('video', type=str, help='Either a url, or web-id')
    parser.add_argument('language', type=str, help='Language')
    args = parser.parse_args()

    youtube_api = get_youtube_api()
    url = convert_to_url(args.video)
    video_id = extract_video_id(url)
    folder = url_to_directory(url)
    trans_file = Path(folder, args.language, "sentence_translations.json")
    if not os.path.exists(trans_file):
        raise Exception(f"Could not find file {trans_file}")

    srt_file = sync_srts_to_translations(trans_file)
    upload_caption(youtube_api, video_id, srt_file, replace=True)
    upload_video_localizations(
        youtube_api,
        trans_file.parent.parent,
        video_id,
        languages=[args.language]
    )