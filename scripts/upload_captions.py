import argparse

from pathlib import Path


from helpers import get_web_id_to_video_id_map
from upload import get_youtube_api
from upload import upload_caption


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Caption file')
    parser.add_argument('caption_file', type=str, help='Caption file path')
    args = parser.parse_args()

    youtube_api = get_youtube_api()
    caption_file = args.caption_file

    web_id = Path(caption_file).parent.parent.stem
    video_id = get_web_id_to_video_id_map()[web_id]
    upload_caption(youtube_api, video_id, caption_file, replace=True)