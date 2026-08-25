#  This is scrappy code I used to remove translated titles on videos which don't yet have an alternate audio track.

import requests
import json
import re

from google_auth_oauthlib.flow import InstalledAppFlow
from google.oauth2.credentials import Credentials
from google.auth.transport.requests import Request
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import os
import pickle

from caption_ops.helpers import get_video_id_to_web_id_map
from caption_ops.helpers import get_all_video_urls
from caption_ops.helpers import extract_video_id


# If modifying these scopes, delete the token.pickle file
SCOPES = ['https://www.googleapis.com/auth/youtube.force-ssl']
VID_TO_WID = get_video_id_to_web_id_map()


def get_video_audio_tracks(video_id):
    """
    Attempts to retrieve available audio tracks for a YouTube video by parsing the initial player response.

    Args:
        video_id (str): The YouTube video ID (the slug in the URL)

    Returns:
        list: A list of dictionaries containing language information for available audio tracks

    Raises:
        ValueError: If the video ID is invalid or the response cannot be parsed
    """
    try:
        # Get the watch page
        url = f"https://www.youtube.com/watch?v={video_id}"
        response = requests.get(url)
        response.raise_for_status()

        # Find the ytInitialPlayerResponse in the page
        player_response_match = re.search(r'ytInitialPlayerResponse\s*=\s*({.+?});', response.text)
        if not player_response_match:
            raise ValueError("Could not find player response data")

        # Parse the player response
        player_data = json.loads(player_response_match.group(1))

        # Look for audioTracks in the captions or streamingData
        audio_tracks = []

        # Try to find audio tracks in different possible locations
        if 'streamingData' in player_data:
            if 'adaptiveFormats' in player_data['streamingData']:
                for format in player_data['streamingData']['adaptiveFormats']:
                    if 'audioTrack' in format:
                        track_info = format['audioTrack']
                        if track_info not in audio_tracks:
                            audio_tracks.append(track_info)

            if 'formats' in player_data['streamingData']:
                for format in player_data['streamingData']['formats']:
                    if 'audioTrack' in format:
                        track_info = format['audioTrack']
                        if track_info not in audio_tracks:
                            audio_tracks.append(track_info)

        # Also check captions object which might contain audio track info
        if 'captions' in player_data:
            captions_data = player_data['captions']
            if 'audioTracks' in captions_data:
                for track in captions_data['audioTracks']:
                    if track not in audio_tracks:
                        audio_tracks.append(track)

        return audio_tracks

    except requests.RequestException as e:
        raise ValueError(f"Error fetching video page: {str(e)}")
    except json.JSONDecodeError as e:
        raise ValueError(f"Error parsing player data: {str(e)}")
    except Exception as e:
        raise ValueError(f"Unexpected error: {str(e)}")


def get_authenticated_service():
    """
    Creates and returns an authenticated YouTube API service.
    Handles the OAuth2 flow including token refresh.
    """
    creds = None
    # The file token.pickle stores the user's access and refresh tokens
    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)

    # If there are no (valid) credentials available, prompt the user to log in
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            flow = InstalledAppFlow.from_client_secrets_file(
                '/Users/grant/cs/api_keys/caption_uploading.json', SCOPES
            )
            creds = flow.run_local_server(port=0)
        # Save the credentials for the next run
        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    return build('youtube', 'v3', credentials=creds)


def cleanup_video_localizations(video_id, allowed_languages, youtube):
    """
    Removes all title localizations except for English and specified languages.

    Args:
        video_id (str): The YouTube video ID
        allowed_languages (list): List of language codes to preserve (e.g., ['es', 'fr'])
        youtube: Authenticated YouTube API service

    Returns:
        dict: Summary of changes made
    """
    try:
        # Always include 'en' in allowed languages if not present
        allowed_languages = set(allowed_languages + ['en'])

        # Get current video details with localizations
        request = youtube.videos().list(
            part='snippet,localizations',
            id=video_id
        )
        response = request.execute()

        if not response['items']:
            return {'error': 'Video not found'}

        video = response['items'][0]
        current_snippet = video['snippet']
        current_localizations = video.get('localizations', {})

        # Keep track of changes
        summary = {
            'original_count': len(current_localizations),
            'removed': [],
            'kept': []
        }

        # Filter localizations to keep only allowed languages
        new_localizations = {}
        for lang, content in current_localizations.items():
            if lang in allowed_languages:
                new_localizations[lang] = content
                summary['kept'].append(lang)
            else:
                summary['removed'].append(lang)

        # Prepare the update request
        update_request = youtube.videos().update(
            part='localizations,snippet',
            body={
                'id': video_id,
                'snippet': {
                    'title': current_snippet['title'],
                    'description': current_snippet['description'],
                    'categoryId': current_snippet['categoryId'],
                    'defaultLanguage': 'en'
                },
                'localizations': new_localizations
            }
        )

        # Execute the update
        update_response = update_request.execute()

        print(f"Removed {", ".join(summary['removed'])} from {VID_TO_WID[video_id]}")

        summary['final_count'] = len(new_localizations)
        return summary

    except HttpError as e:
        print(f"An HTTP error occurred: {e.resp.status} {e.content}")
        raise


def clean_video(video_id, youtube):
    audio_tracks = get_video_audio_tracks(video_id)
    allowed_languages = [
        track['id'].split('.')[0]
        for track in audio_tracks
    ]
    cleanup_video_localizations(video_id, allowed_languages, youtube)


def get_all_audio_tracks():
    # all_urls = get_all_video_urls()

    translations = []

    for url in all_urls:
        video_id = extract_video_id(url)
        audio_tracks = get_video_audio_tracks(video_id)
        wid = VID_TO_WID.get(video_id, "")
        print(f"Searching {wid}")
        for item in audio_tracks:
            name = item.get("displayName")
            if name.startswith("English"):
                pass
            translations.append((wid, url, name))

    translations_by_language = dict()
    for wid, url, name in translations:
        if name not in translations_by_language:
            translations_by_language[name] = []
        translations_by_language[name].append((url, wid))

    for language in translations_by_language.keys():
        print("\n" + language)
        for pair in translations_by_language[language]:
            print("\t".join(pair))


# Example usage

def test():
    youtube = get_authenticated_service()

    all_urls = get_all_video_urls()

    for url in all_urls[30:]:
        video_id = extract_video_id(url)
        print(f"Working on {VID_TO_WID[video_id]}")
        try:
            clean_video(video_id, youtube)
        except Exception as e:
            pass

