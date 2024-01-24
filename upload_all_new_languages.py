from pytube import YouTube

from helpers import url_to_directory
from helpers import get_videos_information

from upload import get_youtube_api
from upload import upload_all_new_captions


def upload_all_new_languages():
    # When quota is increased, I need to run this on everything
    youtube_api = get_youtube_api()
    videos_info = get_videos_information()
    urls = videos_info["Video URL"][::-1]
    for url in urls:
        caption_dir = url_to_directory(url)
        video_id = YouTube(url).video_id
        try:
            upload_all_new_captions(youtube_api, caption_dir, video_id)
        except Exception as e:
            print(f"An error occurred: {str(e)}")
        print("\n")


if __name__ == "__main__":
    upload_all_new_languages()