import os
from pathlib import Path
import pysrt
import numpy as np

from pytube import YouTube
from youtube_transcript_api import YouTubeTranscriptApi

from helpers import extract_video_id
from helpers import get_video_id_to_caption_directory_map
from helpers import ensure_exists
from helpers import temporary_message
from helpers import to_snake_case
from helpers import get_web_id_to_video_id_map
from helpers import get_language_code
from helpers import url_to_directory

from srt_ops import write_srt
from srt_ops import sub_rip_time_to_seconds


def download_youtube_audio(url, file_path):
    yt = YouTube(url)
    with temporary_message(f"Downloading to {file_path}"):
        ensure_exists(Path(file_path).parent)
        yt = yt.streams.filter(only_audio=True, file_extension="mp4").order_by("abr").desc()
        result = yt.first().download(filename=str(file_path))
    return result


def clean_srt_segment_text(text):
    return "\n".join([line.strip() for line in text.split("\n") if line.split()])


def write_yt_transcript_as_srt(transcript, file_path, quiet=False):
    segments = [
        (
            clean_srt_segment_text(s['text']),
            s['start'],
            s['start'] + s['duration']
        )
        for s in transcript.fetch()
    ]
    write_srt(segments, file_path)
    if not quiet:
        print(f"Captions downloaded successfully to '{file_path}'.")


def get_caption_languages(video_id):
    try:
        # Fetch all transcripts
        transcripts = YouTubeTranscriptApi.list_transcripts(video_id)
        return set([t.language_code for t in transcripts])
    except Exception as e:
        print(f"An error occurred: {str(e)}")
        return set()


def sync_from_youtube():
    urls = []
    for url in urls:
        video_id = extract_video_id(url)
        cap_dir = url_to_directory(url)
        transcripts = YouTubeTranscriptApi.list_transcripts(video_id)
        en_trans = [t for t in transcripts if t.language_code == "en"][0]
        caption_file = Path(cap_dir, "english.srt")
        write_yt_transcript_as_srt(en_trans, caption_file)


def does_yt_transcript_match_srt(yt_transcript, srt_file):
    online_segments = yt_transcript.fetch()
    local_segments = pysrt.open(str(srt_file))

    if len(online_segments) != len(local_segments):
        return False

    # Check text
    online_texts = [clean_srt_segment_text(s['text']) for s in online_segments]
    local_texts = [clean_srt_segment_text(s.text) for s in local_segments]
    if any([s1 != s2 for s1, s2 in zip(online_texts, local_texts)]):
        return False

    # Check timings
    online_times = [[s['start'], s['start'] + s['duration']] for s in online_segments]
    local_times = [
        list(map(sub_rip_time_to_seconds, [s.start, s.end]))
        for s in local_segments
    ]
    return np.isclose(online_times, local_times, atol=0.1).all()


def local_captions_match_youtube(srt_file):
    srt_file = Path(srt_file)
    language = srt_file.parent.stem
    web_id = srt_file.parent.parent.stem
    video_id = get_web_id_to_video_id_map()[web_id]

    transcripts = list(YouTubeTranscriptApi.list_transcripts(video_id))
    languages = [t.language.lower() for t in transcripts]
    if language not in languages:
        return False

    # Check YouTube transcript to str similarity
    transcript = transcripts[languages.index(language)]
    return does_yt_transcript_match_srt(transcript, srt_file)


def find_mismatched_captions(video_url, languages=None):
    """
    Searches for all local caption files where the online
    version does not match. Defaults to checking the community
    version in any local language directories.

    If `languages` is passed in, it limits the search to those, otherwise
    it considers all languages in the repository
    """
    cap_dir = Path(url_to_directory(video_url))
    web_id = cap_dir.stem
    video_id = extract_video_id(video_url)

    with temporary_message(f"Pulling {web_id} transcripts"):
        transcripts = list(YouTubeTranscriptApi.list_transcripts(video_id))

    local_languages = [
        lang
        for lang in os.listdir(cap_dir)
        if os.path.isdir(Path(cap_dir, lang))
        if languages is None or lang in languages
    ]
    language_code_to_transcript = {
        t.language_code: t
        for t in transcripts
    }
    mismatches = []
    for language in local_languages:
        language_code = get_language_code(language)
        lang_dir = Path(cap_dir, language)
        srts = [os.path.join(lang_dir, f) for f in os.listdir(lang_dir) if f.endswith(".srt")]
        if not srts:
            continue
        # If any community contributions are available, pick
        community_contributions = [f for f in srts if f.endswith("_community.srt")]
        if community_contributions:
            default_srt = community_contributions[0]
        else:
            default_srt = srts[0]

        # Check for matches against the online transcripts
        online_transcript = language_code_to_transcript.get(language_code, None)
        if online_transcript is None:
            mismatches.append(default_srt)
            continue
        any_matches = any((
            does_yt_transcript_match_srt(online_transcript, srt)
            for srt in srts
        ))
        if not any_matches:
            mismatches.append(default_srt)

    return mismatches


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
    vid_to_dir = get_video_id_to_caption_directory_map()
    for vid, directory in vid_to_dir.items():
        download_captions(vid, directory)


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
