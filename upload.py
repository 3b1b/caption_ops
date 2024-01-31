import os
import google_auth_oauthlib.flow
import googleapiclient.discovery
import googleapiclient.errors
import html

from pytube import YouTube
from pathlib import Path

from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

from helpers import urls_to_directories
from helpers import temporary_message
from helpers import get_language_code
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
    credentials = flow.run_local_server(
        port=0,
        authorization_prompt_message=""
    )
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


def upload_caption(youtube_api, video_id, caption_file, name="", replace=False):
    language_code = get_language_code(Path(caption_file).parent.stem)
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


def upload_video_localizations(youtube_api, video_id, caption_directory):
    # Get the current video information, including localizations
    web_id = os.path.split(caption_directory)[-1]
    try:
        videos_list_response = youtube_api.videos().list(
            part="snippet,localizations",
            id=video_id
        ).execute()
        
        curr_data = videos_list_response['items'][0]
        snippet = curr_data['snippet']
        snippet['defaultLanguage'] = "en"
        localizations = curr_data.get('localizations', dict())
    except Exception as e:
        print(f"Failed to retrieve existing video snippet for {video_id}\n\n{e}\n\n")
        return

    # Update the localization based on title translates (descriptions tbd)
    for language in os.listdir(caption_directory):
        title_file = os.path.join(caption_directory, language, "title.json")
        if not os.path.exists(title_file):
            continue

        lang_code = get_language_code(language)
        loc = localizations.get(lang_code, dict())
        old_loc = dict(loc)
        loc["title"] = html.unescape(json_load(title_file)['translatedText'])
        if "description" not in loc:
            # TODO, should read in some translated description instead
            loc["description"] = snippet["description"]

        # Try uploading
        try:
            localizations[lang_code] = loc
            youtube_api.videos().update(
                part="snippet,localizations",
                body=dict(
                    id=video_id,
                    snippet=snippet,
                    localizations=localizations,
                )
            ).execute()
            print(f"{language} localization added to {web_id}")
        except HttpError as e:
            print(f"\nFailed to add {language} localization for {web_id}")
            localizations.pop(lang_code)
            if old_loc:
                localizations[lang_code] = old_loc


def upload_all_new_captions(youtube_api, directory, video_id):
    with temporary_message(f"Searching {directory}"):
        existing_language_codes = get_caption_languages(video_id)

    for language in os.listdir(directory):
        language_dir = os.path.join(directory, language)
        if not os.path.isdir(language_dir):
            continue
        lang_code = get_language_code(language)
        caption_file = os.path.join(language_dir, "auto_generated.srt")
        if os.path.exists(caption_file) and not lang_code in existing_language_codes:
            upload_caption(
                youtube_api,
                video_id=video_id,
                caption_file=caption_file,
            )

    # Todo, update the localizations. The function above currently does
    # not work.
    upload_video_localizations(youtube_api, video_id, directory)


def upload_new_captions_multiple_videos(video_urls):
    youtube_api = get_youtube_api()
    caption_directories = urls_to_directories(video_urls)
    for video_url, caption_dir in zip(video_urls, caption_directories):
        upload_all_new_captions(
            youtube_api,
            caption_dir,
            YouTube(video_url).video_id,
        )