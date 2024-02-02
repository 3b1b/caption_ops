import Levenshtein
import numpy as np
import os
import sys
import re
import json
import pycountry
from functools import lru_cache
from contextlib import contextmanager
from pathlib import Path

from pytube import YouTube
from pytube.extract import video_id as extract_video_id


CAPTIONS_DIRECTORY = "/Users/grant/cs/captions"
AUDIO_DIRECTORY = "/Users/grant/3Blue1Brown Dropbox/3Blue1Brown/audio_tracks"
SENTENCE_ENDING_PATTERN = r'(?<=[.!?])\s+|\.$|(?<=[।۔՝։።။។፡。！？])'
PUNCTUATION_PATTERN = r'(?<=[.!?,:;])\s+|\.$|(?<=[，।۔՝։።။។፡。！？])'

@contextmanager
def temporary_message(message):
    try:
        sys.stdout.write(message)
        sys.stdout.flush()
        yield
    finally:
        # Return to the start of the line and overwrite the message with spaces
        sys.stdout.write('\r' + ' ' * len(message) + '\r')
        sys.stdout.flush()


def interpolate(start, end, alpha):
    return (1 - alpha) * start + alpha * end


def ensure_exists(path):
    if not os.path.exists(path):
        os.makedirs(path)
    return path


# Some string manipulations


def to_snake_case(name):
    return name.lower().replace(" ", "_").replace(":", "_").replace("__", "_").replace("/", "")


def nearest_string(src, trg_list):
    """
    Return nearest string, and distance
    """
    distances = [Levenshtein.distance(src, trg) for trg in trg_list]
    index = np.argmin(distances)
    return trg_list[index], distances[index]


def get_sentences(full_text, end_marks=SENTENCE_ENDING_PATTERN):
    return [
        (sentence + mark).strip()
        for sentence, mark in zip(
            re.split(end_marks, full_text),
            re.findall(end_marks, full_text),
        )
    ]


def get_language_code(language):
    if language.lower() == "hebrew":
        return 'iw'
    lang_obj = pycountry.languages.get(name=language)
    if lang_obj is None:
        return None
    return lang_obj.alpha_2


def get_language_from_code(language_code):
    lang_obj = pycountry.languages.get(alpha_2=language_code)
    if lang_obj is None:
        return None
    return lang_obj.name


# Simple json wrappers


def json_load(filename):
    with open(filename, 'r', encoding='utf-8') as fp:
        result = json.load(fp)
    return result


def json_dump(obj, filename, indent=1, ensure_ascii=False):
    with open(filename, 'w', encoding='utf-8') as fp:
        result = json.dump(
            obj, fp,
            indent=indent,
            ensure_ascii=ensure_ascii,
        )
    return result



# Related to video file organization


def get_all_files_with_ending(ending, root=CAPTIONS_DIRECTORY):
    result = []
    for root, dirs, files in os.walk(root):
        for file in files:
            path = os.path.join(root, file)
            if path.endswith(ending):
                result.append(path)
    return result


@lru_cache()
def get_video_id_to_caption_directory_map():
    result = dict()
    for file in get_all_files_with_ending("video_url.txt"):
        url = Path(file).read_text()
        result[extract_video_id(url)] = os.path.split(file)[0]
    return result


def default_title_to_web_id(title):
    title_words = title.lower().split(" ")
    large_title_words = list(filter(lambda w: len(w) > 3, title_words))
    return "-".join(large_title_words[:3])


def url_to_directory(video_url, root=None):
    vid = extract_video_id(video_url)

    vid_to_dir = get_video_id_to_caption_directory_map()
    if vid in vid_to_dir:
        directory = vid_to_dir[vid]
    else:
        # Construct a path to associate with this video,
        # and save to it a file with the url
        yt = YouTube(video_url)
        year = yt.publish_date.year
        web_id = default_title_to_web_id(yt.title)
        directory = Path(CAPTIONS_DIRECTORY, str(year), web_id)
        if "shorts" in video_url:
            directory = Path(directory, "shorts")
        ensure_exists(directory)
        # Save file containing the video url here so the
        # association can be found later.
        Path(directory, "video_url.txt").write_text(video_url)
        get_video_id_to_caption_directory_map.cache_clear()
    if root is not None:
        directory = str(directory).replace(CAPTIONS_DIRECTORY, root)
    return directory


def get_web_id_to_caption_directory_map():
    vid_to_dir = get_video_id_to_caption_directory_map()
    return {
        Path(directory).stem: directory
        for directory in vid_to_dir.values()
    }


def get_video_id_to_web_id_map():
    vid_to_dir = get_video_id_to_caption_directory_map()
    return {
        vid: Path(path).stem
        for vid, path in vid_to_dir.items()
    }


def get_web_id_to_video_id_map():
    vid_to_dir = get_video_id_to_caption_directory_map()
    return {
        Path(path).stem: vid
        for vid, path in vid_to_dir.items()
    }


def get_all_video_urls():
    vid_to_dir = get_video_id_to_caption_directory_map()
    vids = sorted(
        vid_to_dir.keys(),
        key=lambda k: vid_to_dir[k]
    )
    urls = [f"https://youtu.be/{vid}" for vid in vids]
    return urls[::-1]


def webids_to_directories(web_ids):
    web_id_to_dir = get_web_id_to_caption_directory_map()
    return [web_id_to_dir[web_id] for web_id in web_ids]
