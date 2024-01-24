import os
from pathlib import Path

from pytube import YouTube
from youtube_transcript_api import YouTubeTranscriptApi

from helpers import temporary_message
from helpers import get_videos_information
from helpers import to_snake_case
from helpers import format_time
from helpers import get_caption_directory
from helpers import urls_to_directories


def download_youtube_audio(url, directory, name="original_audio"):
    yt = YouTube(url)
    file_path = Path(directory, name).with_suffix(".mp4")
    with temporary_message(f"Downloading to {file_path}"):
        yt = yt.streams.filter(only_audio=True, file_extension="mp4").order_by("abr").desc()
        result = yt.first().download(filename=str(file_path))
    return result


def write_yt_transcript_as_srt(transcript, filepath):
    with open(filepath, 'w', encoding='utf-8') as srt_file:
        for idx, segment in enumerate(transcript.fetch()):
            caption_text = segment['text']
            start_time = segment['start']
            end_time = segment['start'] + segment['duration']
            srt_format = "\n".join([
                str(idx + 1),
                format_time(start_time) + " --> " + format_time(end_time),
                caption_text + "\n\n",
            ])
            srt_file.write(srt_format)
    print(f"Captions downloaded successfully to '{filepath}'.")


def get_caption_languages(video_id):
    try:
        # Fetch all transcripts
        transcripts = YouTubeTranscriptApi.list_transcripts(video_id)
        result = [t.language_code for t in transcripts]
        for code in result:
            if len(code) > 2:
                result.append(code[:2])
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

    for webid, date, video_id in zip(webids, dates, video_ids):
        year = date.split("/")[-1]
        directory = get_caption_directory(year, webid)
        download_captions(video_id, directory)


if __name__ == "__main__":
    # Get video information
    columns = get_videos_information()
    video_ids = columns["Slug"]
    urls = columns["Video URL"]
    webids = columns["Website id"]
    dates = columns["Date posted"]
    categories = columns["Category"]

    # Step in
    from IPython.terminal.embed import InteractiveShellEmbed
    ipshell = InteractiveShellEmbed.instance()
    ipshell() # this call anywhere in your program will start IPython
