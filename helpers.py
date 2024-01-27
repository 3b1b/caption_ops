import Levenshtein
import numpy as np
import datetime
import csv
import os
import sys
import re
from functools import lru_cache
from contextlib import contextmanager
from pathlib import Path
import pysrt

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


def sub_rip_time_to_seconds(sub_rip_time):
    return sum((
        sub_rip_time.hours * 3600,
        sub_rip_time.minutes * 60,
        sub_rip_time.seconds,
        sub_rip_time.milliseconds / 1000.0
    ))


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


def write_srt(subtitles, file_name):
    subrip_items = [
        pysrt.SubRipItem(
            index=index,
            start=pysrt.SubRipTime.from_ordinal(int(start_seconds * 1000)),
            end=pysrt.SubRipTime.from_ordinal(int(end_seconds * 1000)),
            text=text,
        )
        for index, (text, start_seconds, end_seconds) in enumerate(subtitles, start=1)
    ]
    # Save the subtitles to an SRT file
    subs = pysrt.SubRipFile(items=subrip_items)
    subs.save(file_name, encoding='utf-8')
    return file_name


def srt_to_txt(srt_file, txt_file_name="transcript"):
    subs = pysrt.open(srt_file)
    text = " ".join([sub.text.replace("\n", " ") for sub in subs])
    if not text.endswith("."):
        text += "."

    txt_path = Path(Path(srt_file).parent, txt_file_name).with_suffix(".txt")
    punc = SENTENCE_ENDINGS
    sentences = [
        sentence.strip() + mark
        for sentence, mark in zip(
            re.split(punc, text),
            re.findall(punc, text),
        )
    ]
    with open(txt_path, "w", encoding='utf-8') as fp:
        fp.write("\n".join(sentences))
    print(f"Wrote {txt_path}")