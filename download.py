import os
from pathlib import Path
import pysrt
import numpy as np

from pytube import YouTube
from youtube_transcript_api import YouTubeTranscriptApi

from helpers import temporary_message
from helpers import get_videos_information
from helpers import to_snake_case
from helpers import get_caption_directory
from helpers import urls_to_directories
from helpers import get_web_id_to_video_id

from srt_ops import write_srt
from srt_ops import sub_rip_time_to_seconds

def download_youtube_audio(url, directory, name="original_audio"):
    yt = YouTube(url)
    file_path = Path(directory, name).with_suffix(".mp4")
    with temporary_message(f"Downloading to {file_path}"):
        yt = yt.streams.filter(only_audio=True, file_extension="mp4").order_by("abr").desc()
        result = yt.first().download(filename=str(file_path))
    return result


def write_yt_transcript_as_srt(transcript, file_path, quiet=False):
    segments = [
        (s['text'], s['start'], s['start'] + s['duration'])
        for s in transcript.fetch()
    ]
    write_srt(segments, file_path)
    if not quiet:
        print(f"Captions downloaded successfully to '{file_path}'.")


def get_caption_languages(video_id):
    try:
        # Fetch all transcripts
        transcripts = YouTubeTranscriptApi.list_transcripts(video_id)
        result = set([
            t.language_code
            for t in transcripts
        ])
        # Hebrew edge case
        if "iw" in result:
            result.add("he")
        return set(result)
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        return set()


def sync_from_youtube():
    video_urls = []
    directories = urls_to_directories(video_urls)
    for video_url, caption_dir in zip(video_urls, directories):
        video_id = YouTube(video_url).video_id
        transcripts = YouTubeTranscriptApi.list_transcripts(video_id)
        en_trans = [t for t in transcripts if t.language_code == "en"][0]
        caption_file = Path(caption_dir, "english.srt")
        write_yt_transcript_as_srt(en_trans, caption_file)


def does_yt_transcript_match_srt(yt_transcript, srt_file):
    online_segments = yt_transcript.fetch()
    online_texts = [s['text'].strip() for s in online_segments]
    online_times = [[s['start'], s['start'] + s['duration']] for s in online_segments]

    local_segments = pysrt.open(str(srt_file))
    local_texts = [s.text.strip() for s in local_segments]
    local_times = [
        list(map(sub_rip_time_to_seconds, [s.start, s.end]))
        for s in local_segments
    ]

    if len(online_segments) != len(local_segments):
        return False

    text_matches = all([s1 == s2 for s1, s2 in zip(online_texts, local_texts)])
    time_matches = np.isclose(online_times, local_times, atol=0.1).all()

    return text_matches and time_matches


def local_captions_match_youtube(srt_file):
    # TODO, Write a version of this that looks through one directory
    # at a time, calling YouTubeTranscriptApi.list_transcripts only as needed
    srt_file = Path(srt_file)
    language = srt_file.parent.stem
    web_id = srt_file.parent.parent.stem
    video_id = get_web_id_to_video_id()[web_id]

    transcripts = list(YouTubeTranscriptApi.list_transcripts(video_id))
    languages = [t.language.lower() for t in transcripts]
    if language not in languages:
        return False

    # Check YouTube transcript to str similarity
    transcript = transcripts[languages.index(language)]
    return does_yt_transcript_match_srt(transcript, srt_file)


# Function to download captions as SRT files
def download_captions(video_id, directory, suffix="community"):
    try:
        # Fetch all transcripts
        transcripts = YouTubeTranscriptApi.list_transcripts(video_id)

        for transcript in transcripts:
            # Skip english
            if transcript.language_code == "en":
                continue
            filename = "".join([
                to_snake_case(transcript.language),
                "_" + suffix if suffix else "",
                ".srt"
            ])
            write_yt_transcript_as_srt(
                transcript,
                os.path.join(directory, filename)
            )

    except Exception as e:
        print(f"An error occurred: {str(e)}")


def download_all_captions():
    columns = get_videos_information()
    video_ids = columns["Slug"]
    web_ids = columns["Website id"]
    dates = columns["Date posted"]

    for webid, date, video_id in zip(web_ids, dates, video_ids):
        year = date.split("/")[-1]
        directory = get_caption_directory(year, webid)
        download_captions(video_id, directory)


def download_video_title_and_description(youtube_api, video_id):
    videos_list_request = youtube_api.videos().list(
        part="snippet,localizations",
        id=video_id
    )
    try:
        response = videos_list_request.execute()
        # Extracting the description from the first item in the response
        title = response['items'][0]['snippet']['title']
        description = response['items'][0]['snippet']['description']
        return title, description
    except Exception as e:
        print(f"Failed to get description for video ID {video_id}\n\n{str(e)}\n")
        return "", ""
