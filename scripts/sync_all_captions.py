import argparse
import os
from pathlib import Path
from pytube.extract import video_id as extract_video_id
from pytube.extract import RegexMatchError
import numpy as np
import shutil

from download import find_mismatched_captions

from helpers import get_web_id_to_video_id_map
from helpers import get_web_id_to_caption_directory_map
from helpers import url_to_directory
from helpers import json_load
from helpers import get_all_files_with_ending

from translate import sentence_translations_to_srt

from sentence_timings import get_sentence_timings

from srt_ops import write_srt_from_sentences_and_time_ranges

from upload import get_youtube_api
from upload import upload_caption
from upload import upload_video_localizations


def convert_to_url(video_str):
    try:
        extract_video_id(video_str)
        return video_str
    except RegexMatchError:
        pass
    vid = get_web_id_to_video_id_map().get(video_str, None)
    if vid is None:
        raise Exception(f"Cannot find {video_str}")
    return f"https://youtu.be/{vid}"


def sync_srts_to_translations(trans_file):
    trans = json_load(trans_file)
    has_blanks = any(obj['translatedText'] == "" and obj['input'] != "" for obj in trans)
    proportion_reviewed = np.mean([obj['n_reviews'] > 0 for obj in trans])

    if has_blanks:
        return

    # Check if a recent review suggest that any existing community
    # contributions should be considered outdated
    folder = Path(trans_file).parent
    if proportion_reviewed > 0.5:
        community_files = get_all_files_with_ending("community.srt", root=str(folder))
        for file in community_files:
            shutil.move(file, file.replace("community.srt", "community_old.srt"))

    return sentence_translations_to_srt(trans_file)

def sync_all_captions(video_url: str):
    youtube_api = get_youtube_api()
    folder = url_to_directory(video_url)
    video_id = extract_video_id(video_url)

    # Create english srts
    en_folder = Path(folder, "english")
    transcript = Path(en_folder, "transcript.txt")
    captions_file = Path(en_folder, "captions.srt")
    word_timings_file = Path(en_folder, "word_timings.json")

    sentences = list(map(str.strip, transcript.read_text().split("\n")))
    word_timings = json_load(word_timings_file)
    timings = get_sentence_timings(word_timings, sentences)
    write_srt_from_sentences_and_time_ranges(sentences, timings, captions_file)

    # Create translation srts
    for trans_file in get_all_files_with_ending("sentence_translations.json", root=str(folder)):
        sync_srts_to_translations(trans_file)

    # Upload mismatches
    for path in find_mismatched_captions(video_url):
        try:
            upload_caption(youtube_api, video_id, path, replace=True)
        except Exception as e:
            print(f"Failed to upload {path}\n\n{e}\n\n")

    upload_video_localizations(youtube_api, folder, video_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Video url')
    parser.add_argument('video', type=str, help='Video url, web-id, or txt file with one url or web-id per line')
    args = parser.parse_args()

    if args.video.endswith(".txt"):
        videos = Path(args.video).read_text().split("\n")
    else:
        videos = [args.video]

    for video in map(convert_to_url, videos):
        try:
            sync_all_captions(video)
        except Exception as e:
            print(f"Failed to sync {video}\n{e}\n")
