import os
from functools import lru_cache

import google_auth_oauthlib.flow
import googleapiclient.discovery
import google.auth.transport.requests
from google.oauth2.credentials import Credentials
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError
import html
import time

from pathlib import Path

from helpers import extract_video_id
from helpers import url_to_directory
from helpers import temporary_message
from helpers import get_language_code
from helpers import json_load
from helpers import get_video_id_to_web_id_map
from helpers import get_language_from_code
from helpers import get_all_video_urls

from download import get_caption_languages
from download import download_video_title_and_description

from track_contributors import get_all_video_contributors


SECRETS_FILE_ENV_VARIABLE_NAME = 'YOUTUBE_UPLOADING_KEY'
CRENTIALS_FILE_ENV_VARIABLE_NAME = 'YOUTUBE_CREDENTIALS_FILE'
CREDIT_HEADER = "Thanks to these viewers for their contributions to translations"

@lru_cache()
def get_youtube_api():
    client_secrets_file = os.getenv(SECRETS_FILE_ENV_VARIABLE_NAME)
    credentials_file = os.getenv(CRENTIALS_FILE_ENV_VARIABLE_NAME)
    if client_secrets_file is None:
        raise Exception(f"Environment variable {SECRETS_FILE_ENV_VARIABLE_NAME} not set")
    if credentials_file is None:
        raise Exception(f"Environment variable {CRENTIALS_FILE_ENV_VARIABLE_NAME} not set")

    api_service_name = "youtube"
    api_version = "v3"
    scopes = ["https://www.googleapis.com/auth/youtubepartner"]

    credentials = None

    # Load credentials from the file if they exist
    if os.path.exists(credentials_file):
        credentials = Credentials.from_authorized_user_file(credentials_file, scopes)

    # If there are no valid credentials available, request the user to log in.
    if not credentials or not credentials.valid:
        if credentials and credentials.expired and credentials.refresh_token:
            credentials.refresh(google.auth.transport.requests.Request())
        else:
            flow = google_auth_oauthlib.flow.InstalledAppFlow.from_client_secrets_file(
                client_secrets_file, scopes
            )
            credentials = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open(credentials_file, 'w') as f:
                f.write(credentials.to_json())

    return googleapiclient.discovery.build(
        api_service_name, api_version,
        credentials=credentials
    )


def delete_captions(youtube_api, video_id, language_code):
    web_id = get_video_id_to_web_id_map()[video_id]
    language = get_language_from_code(language_code)
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
        print(f"Failed to retrieve captions from {web_id}\n\n{e}\n\n")

    # Delete the captions
    if caption_id:
        try:
            delete_request = youtube_api.captions().delete(id=caption_id)
            delete_request.execute()
            print(f"Deleted existing {language} captions on {web_id}")
        except Exception as e:
            print(f"Failed to delete {language} captions on {web_id}\n\n{e}\n\n")


def upload_caption(youtube_api, video_id, caption_file, name="", replace=False):
    language_code = get_language_code(Path(caption_file).parent.stem)
    if replace:
        delete_captions(youtube_api, video_id, language_code)
        time.sleep(0.5)  # Needs better use of async
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
    web_id, langauge = str(caption_file).split(os.sep)[-3:-1]
    try:
        with temporary_message(f"Uploading {langauge} captions to {web_id}"):
            insert_request.execute()
        print(f"Uploaded {langauge} captions to {web_id} successfully")
    except Exception as e:
        if "exceeded" in str(e) and "quota" in str(e):
            print("Quota exceeded")
            raise Exception(e)
        else:
            print(f"Failed to upload {langauge} captions to {web_id}")
            print(f"\n{str(e)}\n")


def upload_video_localizations(youtube_api, caption_directory, video_id, languages=None):
    # Get the current video information, including localizations
    if languages is not None:
        languages = [lang.lower() for lang in languages]

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

    # Update the localization based on title and description translations
    successes = []
    failures = []
    for language in os.listdir(caption_directory):
        lang_code = get_language_code(language)
        if lang_code is None:
            continue
        if languages is not None and language not in languages:
            continue
        title_file = os.path.join(caption_directory, language, "title.json")
        desc_file = os.path.join(caption_directory, language, "description.json")

        loc = localizations.get(lang_code, dict())
        old_loc = dict(loc)
        needs_update = False

        if os.path.exists(title_file):
            title = html.unescape(json_load(title_file)['translatedText'])
            if loc.get("title", "") != title:
                needs_update = True
                loc["title"] = title
        if os.path.exists(desc_file):
            desc = "\n".join([
                html.unescape(obj['translatedText'])
                for obj in json_load(desc_file)
            ])
            if loc.get("description", "") != desc:
                needs_update = True
                loc["description"] = desc
        if not needs_update:
            continue

        # Try uploading
        localizations[lang_code] = loc
        try:
            youtube_api.videos().update(
                part="snippet,localizations",
                body=dict(
                    id=video_id,
                    snippet=snippet,
                    localizations=localizations,
                )
            ).execute()
            successes.append(language)
        except HttpError as e:
            failures.append(language)
            localizations[lang_code] = old_loc

    # Print out
    if successes:
        lang_str = ", ".join(successes)
        print(f"Localizations on {web_id} updated for {lang_str}\n")
    if failures:
        lang_str = ", ".join(failures)
        print(f"Failed to update localization on {web_id} for for {lang_str}\n")


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


def upload_new_captions_multiple_videos(video_urls):
    youtube_api = get_youtube_api()
    for video_url in video_urls:
        upload_all_new_captions(
            youtube_api=youtube_api,
            directory=url_to_directory(video_url),
            video_id=extract_video_id(video_url),
        )


def update_description(youtube_api, video_id, new_description):
    # First, fetch the current video details to get the required parts for update
    video_response = youtube_api.videos().list(
        part="snippet",
        id=video_id
    ).execute()
    
    if not video_response['items']:
        return "Video not found."
    
    snippet = video_response['items'][0]['snippet']
    
    # Update the description in the snippet
    snippet['description'] = new_description
    
    # Prepare the update request with the modified snippet
    update_request = youtube_api.videos().update(
        part="snippet",
        body={
            "id": video_id,
            "snippet": snippet
        }
    )
    
    # Execute the update request
    update_response = update_request.execute()


def add_translation_credit_to_description(desc, contributors):
    lines = desc.split("\n")
    if any(l.startswith(CREDIT_HEADER) for l in lines):
        credits_index = next(i for (i, l) in enumerate(lines) if l.startswith(CREDIT_HEADER))
        while True:
            if credits_index >= len(lines):
                break
            if len(lines[credits_index].strip()) == 0:
                break
            if lines[credits_index].startswith("-"):
                break
            lines.pop(credits_index)
    elif any(l.startswith("--") for l in lines):
        credits_index = next(i for (i, l) in enumerate(lines) if l.startswith("--"))
    else:
        if not len(lines[-1].strip()) == 0:
            lines.append("")
        credits_index = len(lines)

    credit_lines = [CREDIT_HEADER]
    for lang in sorted(contributors.keys()):
        names = contributors[lang]
        name_list = ", ".join(names)
        credit_lines.append(f"{lang.capitalize()}: {name_list}")
    credit_lines.append("")

    return "\n".join((
        *lines[:credits_index],
        *credit_lines,
        *lines[credits_index:],
    ))


def add_translation_credit(youtube_api, video_id):
    contributors = get_all_video_contributors(get_video_id_to_web_id_map()[video_id])
    if not contributors:
        return
    title, desc = download_video_title_and_description(youtube_api, video_id)
    new_desc = add_translation_credit_to_description(desc, contributors)
    update_description(youtube_api, video_id, new_desc)


def add_all_contributors():
    youtube_api = get_youtube_api()
    vid_to_wid = get_video_id_to_web_id_map()
    urls = get_all_video_urls()
    for url in urls:
        vid = extract_video_id(url)
        wid = vid_to_wid[vid]
        with temporary_message(f"Adding credits to {wid}"):
            try:
                add_translation_credit(youtube_api, vid)
            except Exception as e:
                print(f"Failed on {wid}")

    from helpers import get_web_id_to_video_id_map

    wid_to_vid = get_web_id_to_video_id_map()
    wids = [
        "area-and-slope",
        "chain-rule-and-product-rule",
        "higher-order-derivatives",
        "implicit-differentiation",
        "integration",
        "limits",
        "taylor-series",
        "derivatives-and-transforms",
        "feynmans-lost-lecture",
        "barber-pole-1",
    ]
    for wid in wids:
        with temporary_message(f"Adding credits to {wid}"):
            add_translation_credit(youtube_api, wid_to_vid[wid])