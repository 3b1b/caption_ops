import os
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
from pytube import YouTube
import pycountry
from pathlib import Path

from googleapiclient.http import MediaFileUpload

from helpers import urls_to_directories
from helpers import temporary_message

from download import get_caption_languages


scopes = ["https://www.googleapis.com/auth/youtube.force-ssl"]
SECRETS_FILE = "/Users/grant/cs/api_keys/caption_uploading.json"
# SECRETS_FILE = "/Users/grant/cs/api_keys/caption_uploading5.json"


def get_youtube_api():
    # Authorization
    api_service_name = "youtube"
    api_version = "v3"

    # Get credentials and create an API client
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
        SECRETS_FILE, scopes
    )
    credentials = flow.run_local_server(port=0)
    return googleapiclient.discovery.build(
        api_service_name, api_version,
        credentials=credentials
    )


def upload_caption(youtube_api, video_id, language_code, name, caption_file):
    insert_request = youtube_api.captions().insert(
        part="snippet",
        body={
            "snippet": {
                "videoId": video_id,
                "language": language_code,
                "name": name,
                "isDraft": False
            }
        },
        media_body=MediaFileUpload(caption_file)
    )
    try:
        with temporary_message(f"Uploading {caption_file} to {video_id}"):
            response = insert_request.execute()
        print(f"Captions from {caption_file} uploaded.")
    except Exception as e:
        print(f"Failed to upload {caption_file}\n\n{str(e)}\n")


def upload_all_new_captions(youtube_api, directory, video_id):
    existing_language_codes = get_caption_languages(video_id)
    for file in os.listdir(directory):
        if not file.endswith(".srt"):
            continue
        language = pycountry.languages.get(name=file.split("_")[0])
        if language is None:
            continue
        if language.alpha_2 in existing_language_codes:
            continue
        upload_caption(
            youtube_api,
            video_id=video_id,
            language_code=language.alpha_2,
            name="",
            caption_file=Path(directory, file)
        )


def upload_new_captions_multiple_videos(video_urls):
    youtube_api = get_youtube_api()
    caption_directories = urls_to_directories(video_urls)
    for video_url, caption_dir in zip(video_urls, caption_directories):
        upload_all_new_captions(
            youtube_api,
            caption_dir,
            YouTube(video_url).video_id,
        )