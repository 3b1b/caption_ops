import os
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
from pytube import YouTube
import pycountry

from googleapiclient.http import MediaFileUpload

from helpers import urls_to_directories
from helpers import temporary_message

from download import get_caption_languages
from download import download_video_description


scopes = ["https://www.googleapis.com/auth/youtube.force-ssl"]
SECRETS_FILE = "/Users/grant/cs/api_keys/caption_uploading1.json"


def get_youtube_api(client_secrets_file=SECRETS_FILE):
    # Authorization
    api_service_name = "youtube"
    api_version = "v3"

    # Get credentials and create an API client
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
        client_secrets_file=client_secrets_file,
        scopes=scopes
    )
    credentials = flow.run_local_server(port=0)
    return googleapiclient.discovery.build(
        api_service_name, api_version,
        credentials=credentials
    )


def delete_captions(youtube_api, video_id, language_code):
    # Check the current caption ids
    caption_id = None
    try:
        request = youtube_api.captions().list(part="snippet", videoId=video_id)
        response = request.execute()
        for item in response["items"]:
            if item["snippet"]["language"] == language_code:
                caption_id = item["id"]
                break
    except Exception as e:
        print(f"Failed to retrieve captions on {video_id}\n\n{e}\n\n")

    # Delete the captions
    if caption_id:
        try:
            delete_request = youtube_api.captions().delete(id=caption_id)
            delete_request.execute()
            print(f"Deleted existing {language_code} on {video_id}")
        except Exception as e:
            print(f"Failed to delete {language_code} on {video_id}\n\n{e}\n\n")


def upload_caption(youtube_api, video_id, language_code, name, caption_file, replace=False):
    if replace:
        delete_captions(youtube_api, video_id, language_code)
    # Insert new captions
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
            insert_request.execute()
        print(f"Captions from {caption_file} uploaded.")
    except Exception as e:
        if "exceeded" in str(e) and "quota" in str(e):
            print("Quota exceeded")
            raise Exception(e)
        else:
            print(f"Failed to upload {caption_file}\n\n{str(e)}\n")


def upload_video_title_and_description(youtube_api, video_id, language_code, title, description=None):
    # Just use the same description, because why not?
    if description is None:
        description = download_video_description(youtube_api, video_id)
    videos_update_request = youtube_api.videos().update(
        part="snippet,localizations",
        body={
            "id": video_id,
            "snippet": {
                "categoryId": "27"  # Educational videos
            },
            "localizations": {
                language_code: {
                    "title": title,
                    "description": description
                }
            }
        }
    )
    try:
        videos_update_request.execute()
        print(f"Details for video ID {video_id} updated: Title - '{title}' in {language_code}.")
    except Exception as e:
        print(f"Failed to update details for video ID {video_id}\n\n{str(e)}\n")


def upload_all_new_captions(youtube_api, directory, video_id):
    with temporary_message(f"Searching {directory}"):
        existing_language_codes = get_caption_languages(video_id)

    for language in os.listdir(directory):
        language_dir = os.path.join(directory, language)
        if not os.path.isdir(language_dir):
            continue
        lang_obj = pycountry.languages.get(name=language)
        if lang_obj is None:
            continue
        if lang_obj.alpha_2 in existing_language_codes:
            continue
        srts = [
            os.path.join(language_dir, file)
            for file in os.listdir(language_dir)
            if file.endswith(".srt")
        ]
        if not srts:
            continue
        upload_caption(
            youtube_api,
            video_id=video_id,
            language_code=lang_obj.alpha_2,
            name="",
            caption_file=srts[0]
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