import argparse
import os
from pathlib import Path
from pytube import YouTube

from helpers import urls_to_directories
from helpers import get_videos_information
from helpers import srt_to_txt
from helpers import AUDIO_DIRECTORY
from helpers import CAPTIONS_DIRECTORY

from download import download_youtube_audio

from transcribe_video import load_whisper_model
from transcribe_video import transcribe_file
from transcribe_video import transcription_to_srt

from translate import translate_to_multiple_languages
from translate import TARGET_LANGUAGES

from upload import get_youtube_api
from upload import upload_caption
from upload import upload_all_new_captions


def upload_all_english():
    # I had run this, but it hit it's qury limit.
    # I've gone from 0 up to 66
    # Current limit seems to be like 25 per day?
    # 
    # I'll keep running it later I guess? I need to start with implicit differentiation
    youtube_api = get_youtube_api()

    videos_info = get_videos_information()
    urls = videos_info["Video URL"]
    webids = videos_info["Website id"]
    for index in range(68, len(webids)):
        print(index)
        url = urls[index]

        caption_dir = urls_to_directories(url, root=CAPTIONS_DIRECTORY)[0]
        caption_file = Path(caption_dir, "english.srt")
        if not os.path.exists(caption_file):
            continue
        try:
            upload_caption(
                youtube_api,
                YouTube(url).video_id,
                language_code="en",
                name="(whisper)",
                caption_file=str(caption_file),
            )
        except Exception as e:
            print(f"An error occurred: {str(e)}")
        print("\n")



def auto_caption(video_url, upload=False):
    youtube_api = get_youtube_api() if upload else None

    # Get output directories
    caption_dir = urls_to_directories(video_url, root=CAPTIONS_DIRECTORY)[0]
    audio_dir = urls_to_directories(video_url, root=AUDIO_DIRECTORY)[0]

    # Download
    audio_file = download_youtube_audio(video_url, audio_dir)

    # Transcribe
    model = load_whisper_model()
    transcription = transcribe_file(model, audio_file)
    caption_file = transcription_to_srt(
        transcription,
        out_dir=caption_dir,
        out_name="english",
    )
    srt_to_txt(caption_file)

    # Translate
    translate_to_multiple_languages(caption_file, languages=TARGET_LANGUAGES)

    if upload:
        video_id = YouTube(video_url).video_id
        # Upload english
        try:
            upload_caption(
                youtube_api,
                video_id,
                language_code="en",
                name="",
                caption_file=caption_file,
            )
        except Exception as e:
            print(f"Failed to upload {caption_file}\n\n{e}\n\n")
        # Upload all other languages
        upload_all_new_captions(youtube_api, caption_dir, video_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Video url')
    parser.add_argument('video_url', type=str, help='YouTube url')
    args = parser.parse_args()

    auto_caption(args.video_url)