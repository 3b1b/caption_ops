import time
import datetime

from helpers import url_to_directory
from helpers import get_videos_information
from helpers import extract_video_id

from upload import get_youtube_api
from upload import upload_all_new_captions


def upload_all_new_languages():
    # When quota is increased, I need to run this on everything
    # youtube_api = get_youtube_api()
    youtube_apis = [
        get_youtube_api(f"/Users/grant/cs/api_keys/caption_uploading{n + 1}.json")
        for n in range(10)
    ]
    api_index = 0
    youtube_api = youtube_apis[api_index]

    videos_info = get_videos_information()
    urls = videos_info["Video URL"][::-1]

    index = 0
    while index < len(urls):
        url = urls[index]
        video_id = extract_video_id(url)
        caption_dir = url_to_directory(url)
        try:
            upload_all_new_captions(youtube_api, caption_dir, video_id)
        except Exception as e:
            # This should only happen when the quota has been reached
            api_index = (api_index + 1) % len(youtube_apis)
            if api_index == 0:
                now = datetime.datetime.now().strftime("%H:%M:%S")
                print(f"Time is now {now}, sleeping for 12 hours")
                time.sleep(60 * 60 * 12)
            youtube_api = youtube_apis[api_index]
            index -= 1
        index += 1


if __name__ == "__main__":
    upload_all_new_languages()