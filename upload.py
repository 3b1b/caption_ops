import os
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
from pytube import YouTube
import pycountry

from googleapiclient.http import MediaFileUpload

from helpers import urls_to_directories
from helpers import temporary_message
from helpers import json_load

from download import get_caption_languages


SECRETS_FILE = os.getenv('YOUTUBE_UPLOADING_KEY')


def get_youtube_api(client_secrets_file=SECRETS_FILE):
    # Authorization
    api_service_name = "youtube"
    api_version = "v3"

    # Get credentials and create an API client
    flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
        client_secrets_file=client_secrets_file,
        scopes=["https://www.googleapis.com/auth/youtube.force-ssl"]
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


def upload_video_localizations(youtube_api, video_id, languages_to_details):
    if len(languages_to_details) == 0:
        pass

    # Get the current localizations
    try:
        videos_list_response = youtube_api.videos().list(
            part="snippet,localizations",
            id=video_id
        ).execute()
        
        curr_data = videos_list_response['items'][0]
        localizations = curr_data.get('localizations', {})
    except Exception as e:
        print(f"Failed to retrieve existing video snippet\n\n{e}\n\n")
        return

    if "he" in languages_to_details:
        languages_to_details["iw"] = languages_to_details.pop('he')

    for lang_code, details in languages_to_details.items():
        if details["description"] is None:
            # Just use the same description, because why not?
            details["description"] = curr_data['snippet']['description']
        if len(details["title"]) == 0:
            # Don't update for blank titles
            continue
        # Update the specific localization
        localizations[lang_code] = details

    snippet = curr_data['snippet']
    body_data = {
        "id": video_id,
        "snippet": {
            "title": snippet['title'],  # include only if you need to update the default language title
            "description": snippet['description'],  # include only if you need to update the default language description
            "categoryId": snippet['categoryId'],
            # ... include other fields you need to update
        },
        "localizations": localizations
    }

    videos_update_request = youtube_api.videos().update(
        part="snippet,localizations",
        body=body_data
    )

    try:
        videos_update_request.execute()
        print(f"Details for video ID {curr_data['snippet']['title']} updated.")
    except Exception as e:
        print(f"Failed to update details for video {video_id}\n\n{str(e)}\n")


def upload_all_new_captions(youtube_api, directory, video_id):
    with temporary_message(f"Searching {directory}"):
        existing_language_codes = get_caption_languages(video_id)

    lang_to_details = dict()
    for language in os.listdir(directory):
        language_dir = os.path.join(directory, language)
        if not os.path.isdir(language_dir):
            continue
        lang_obj = pycountry.languages.get(name=language)
        if lang_obj is None:
            continue
        lang_code = lang_obj.alpha_2
        caption_file = os.path.join(language_dir, "auto_generated.srt")
        if os.path.exists(caption_file) and not lang_code in existing_language_codes:
            upload_caption(
                youtube_api,
                video_id=video_id,
                language_code=lang_code,
                name="",
                caption_file=caption_file
            )

        title_file = os.path.join(language_dir, "title.json")
        if os.path.exists(title_file):
            lang_to_details[lang_code] = dict(
                title=json_load(title_file)['translatedText'],
                description=None,  # TODO
            )

    # Todo, update the localizations. The function above currently does
    # not work.
    # upload_video_localizations(youtube_api, video_id, lang_to_details)


def upload_new_captions_multiple_videos(video_urls):
    youtube_api = get_youtube_api()
    caption_directories = urls_to_directories(video_urls)
    for video_url, caption_dir in zip(video_urls, caption_directories):
        upload_all_new_captions(
            youtube_api,
            caption_dir,
            YouTube(video_url).video_id,
        )