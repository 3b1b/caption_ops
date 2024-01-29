import time
import datetime
from pytube import YouTube

from helpers import url_to_directory
from helpers import get_videos_information
from helpers import extract_video_id

from upload import get_youtube_api
from upload import upload_all_new_captions

# 3Blue1Brown
CHANNEL_ID = "UCYO_jab_esuFRV4b17AJtAw"

def upload_all_new_languages():
    youtube_api = get_youtube_api()
    videos_info = get_videos_information()
    urls = videos_info["Video URL"][::-1]

    index = 0
    while index < len(urls):
        url = urls[index]
        video_id = extract_video_id(url)
        caption_dir = url_to_directory(url)
        if not YouTube(url).channel_id == CHANNEL_ID:
            # There's only permission to upload to 3b1b
            continue
        try:
            upload_all_new_captions(youtube_api, caption_dir, video_id)
        except Exception as e:
            # This should only happen when the quota has been reached
            now = datetime.datetime.now().strftime("%H:%M:%S")
            print(f"Time is now {now}, sleeping for 12 hours")
            time.sleep(60 * 60 * 12)
            index -= 1
        index += 1


if __name__ == "__main__":
    upload_all_new_languages()