import Levenshtein
import numpy as np
import datetime
import csv
import os
import sys
from functools import lru_cache
from contextlib import contextmanager
from pathlib import Path

from pytube import YouTube


ALL_VIDEOS_FILE = "/Users/grant/Downloads/all_videos.csv"
CAPTIONS_DIRECTORY = "/Users/grant/cs/captions"
AUDIO_DIRECTORY = "/Users/grant/3Blue1Brown Dropbox/3Blue1Brown/audio_tracks"


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


def format_time(seconds):
    # Function to convert seconds to HH:MM:SS,mmm format
    delta = datetime.timedelta(seconds=seconds)
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    milliseconds = delta.microseconds // 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def unformat_time(timestamp):
    if not (timestamp.count(":") == 2 and timestamp.count(",") <= 1):
        raise Exception(f"Incorrectly formatted timestamp: {timestamp}")
    if "," in timestamp:
        hms, miliseconds = timestamp.split(",")
    else:
        hms = timestamp
        miliseconds = 0
    hours, minutes, seconds = hms.split(":")
    return 3600 * int(hours) + 60 * int(minutes) + int(seconds) + 0.001 * int(miliseconds)

# Related to video file organization

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


def get_caption_directory(year, webid, root=CAPTIONS_DIRECTORY):
    return os.path.join(root, str(year), webid)


def get_audio_directory(year, webid, root=AUDIO_DIRECTORY):
    return get_caption_directory(year, webid, root)


def url_to_directory(video_url, root=CAPTIONS_DIRECTORY, video_id_to_web_id=None):
    if video_id_to_web_id is None:
        video_id_to_web_id = get_video_id_to_web_id()

    yt = YouTube(video_url)
    year = yt.publish_date.year
    web_id = video_id_to_web_id.get(
        yt.video_id,
        # Default id value
        to_snake_case(yt.title.split("|")[0].strip()),
    )
    caption_directory = get_caption_directory(year, web_id, root=root)
    if not os.path.exists(caption_directory):
        os.makedirs(caption_directory)
    return caption_directory


def urls_to_directories(video_urls, root=CAPTIONS_DIRECTORY):
    video_id_to_web_id = get_video_id_to_web_id()
    return [
        url_to_directory(url, root, video_id_to_web_id)
        for url in video_urls
    ]


def webids_to_directories(web_ids, root=CAPTIONS_DIRECTORY):
    video_info = get_videos_information()
    years = [
        video_info["Date posted"][video_info["Website id"].index(webid)].split("/")[-1]
        for webid in web_ids
    ]
    return [
        get_caption_directory(year, webid, root=root)
        for year, webid in zip(years, web_ids)
    ]


def srt_to_txt(srt_file, txt_file_name="transcript"):
    with open(srt_file, "r") as file:
        lines = file.readlines()
    text = " ".join(
        line.strip()
        for line in lines[2::4]
    )
    txt_path = Path(Path(srt_file).parent, txt_file_name).with_suffix(".txt")
    print(f"Writing {txt_path}")
    with open(txt_path, "w", encoding='utf-8') as file:
        file.write(text)