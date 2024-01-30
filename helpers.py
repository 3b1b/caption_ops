import Levenshtein
import numpy as np
import csv
import os
import sys
import re
import json
import pycountry
from functools import lru_cache
from contextlib import contextmanager

from pytube import YouTube
from pytube.extract import video_id as extract_video_id


ALL_VIDEOS_FILE = "/Users/grant/Downloads/all_videos.csv"
CAPTIONS_DIRECTORY = "/Users/grant/cs/captions"
AUDIO_DIRECTORY = "/Users/grant/3Blue1Brown Dropbox/3Blue1Brown/audio_tracks"
SENTENCE_ENDINGS = r'(?<=[.!?])\s+|\.$|(?<=[।۔՝։።။។፡。！？])'

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


def get_sentences(full_text, end_marks=SENTENCE_ENDINGS):
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
    return pycountry.languages.get(name=language).alpha_2


# Related to video file organization

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

@lru_cache()
def get_videos_information(filename=ALL_VIDEOS_FILE):
    with open(filename, mode='r', newline='', encoding='utf-8') as file:
        reader = csv.DictReader(file)
        columns = {}
        for row in reader:
            for header, value in row.items():
                columns.setdefault(header, []).append(value)
        return columns


def get_video_id_to_web_id():
    videos_info = get_videos_information()
    return dict(zip(
        videos_info["Slug"],
        videos_info["Website id"]
    ))


def get_web_id_to_video_id():
    videos_info = get_videos_information()
    return dict(zip(
        videos_info["Website id"],
        videos_info["Slug"],
    ))


def get_caption_directory(year, webid, root=CAPTIONS_DIRECTORY):
    return os.path.join(root, str(year), webid)


def get_audio_directory(year, webid, root=AUDIO_DIRECTORY):
    return get_caption_directory(year, webid, root)


def url_to_directory(video_url, root=CAPTIONS_DIRECTORY, videos_info=None):
    if videos_info is None:
        videos_info = get_videos_information()

    video_id = extract_video_id(video_url)
    if video_id in videos_info["Slug"]:
        index = videos_info["Slug"].index(video_id)
        year = videos_info["Date posted"][index].split("/")[-1]
        web_id = videos_info["Website id"][index]
    else:
        yt = YouTube(video_url)
        year = yt.publish_date.year
        web_id = to_snake_case(yt.title.split("|")[0].strip())

    # Directory
    return ensure_exists(get_caption_directory(year, web_id, root=root))


def urls_to_directories(video_urls, root=CAPTIONS_DIRECTORY):
    videos_info = get_videos_information()
    return [
        url_to_directory(url, root, videos_info)
        for url in video_urls
    ]


def webids_to_directories(web_ids, root=CAPTIONS_DIRECTORY):
    video_info = get_videos_information()
    web_id_to_year = {
        web_id: date.split("/")[-1]
        for web_id, date in zip(video_info["Website id"], video_info["Date posted"])
    }
    return [
        get_caption_directory(web_id_to_year[web_id], web_id, root=root)
        for web_id in web_ids
    ]
