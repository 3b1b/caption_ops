import time
import datetime

from helpers import url_to_directory
from helpers import get_all_video_urls
from helpers import extract_video_id

from upload import get_youtube_api
from upload import upload_all_new_captions

def upload_all_new_languages():
    youtube_api = get_youtube_api()
    urls = get_all_video_urls()
    while urls:
        url = urls.pop()
        video_id = extract_video_id(url)
        caption_dir = url_to_directory(url)
        try:
            upload_all_new_captions(youtube_api, caption_dir, video_id)
        except Exception as e:
            # This should only happen when the quota has been reached
            now = datetime.datetime.now().strftime("%H:%M:%S")
            print(f"Time is now {now}, sleeping for 12 hours")
            urls.append(url)
            time.sleep(60 * 60 * 12)


if __name__ == "__main__":
    upload_all_new_languages()