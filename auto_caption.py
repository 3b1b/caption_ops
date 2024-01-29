import argparse
import os
from pytube import YouTube
from pathlib import Path

from helpers import url_to_directory
from helpers import ensure_exists
from helpers import json_load
from helpers import json_dump
from helpers import get_videos_information
from helpers import AUDIO_DIRECTORY

from download import download_youtube_audio

from transcribe_video import load_whisper_model
from transcribe_video import transcribe_file
from transcribe_video import write_whisper_srt
from transcribe_video import words_with_timings_to_srt
from transcribe_video import save_word_timings

from translate import translate_to_multiple_languages
from translate import translate_title_to_multiple_languages
from translate import TARGET_LANGUAGES

from srt_ops import srt_to_txt

from upload import get_youtube_api
from upload import upload_caption
from upload import upload_all_new_captions


def write_all_transcription_files(model, audio_file, caption_path):
    parent = Path(caption_path).parent
    whisper_srt_path = Path(parent, "whisper_captions.srt")
    timing_file = Path(parent, "word_timings.json")

    # Run whisper
    transcription = transcribe_file(model, str(audio_file))
    # Save the srt that whisper generates
    write_whisper_srt(transcription, whisper_srt_path)
    # Save the times for each individual word
    word_timings = save_word_timings(transcription, timing_file)
    # Write a better srt based on those word timeings
    words_with_timings_to_srt(word_timings, caption_path)
    # Write the transcription in plain text
    srt_to_txt(caption_path)


def recaption_everything():
    videos_info = get_videos_information()
    urls = videos_info["Video URL"]
    web_ids = videos_info["Website id"]
    model = load_whisper_model()

    for url in urls[::-1]:
        caption_dir = url_to_directory(url)
        audio_dir = url_to_directory(url, root=AUDIO_DIRECTORY)
        audio_file = Path(audio_dir, "original_audio.mp4")
        if not os.path.exists(audio_file):
            audio_file = download_youtube_audio(url, audio_dir)
        # Transcribe
        try:
            en_dir = ensure_exists(Path(caption_dir, "english"))
            write_all_transcription_files(model, audio_file, Path(en_dir, "captions.srt"))
        except Exception as e:
            print(f"\n\n{e}\n\n")


def auto_caption(video_url, upload=True):
    youtube_api = get_youtube_api() if upload else None

    # Get output directories
    caption_dir = url_to_directory(video_url)
    audio_dir = url_to_directory(video_url, root=AUDIO_DIRECTORY)

    # Download
    audio_file = download_youtube_audio(video_url, audio_dir)

    # Transcribe
    model = load_whisper_model()
    en_dir = ensure_exists(Path(caption_dir, "english"))
    caption_path = Path(en_dir, "captions.srt")
    write_all_transcription_files(model, audio_file, caption_path)

    # Translate
    translate_to_multiple_languages(caption_path, languages=TARGET_LANGUAGES)
    translate_title_to_multiple_languages(video_url, languages=TARGET_LANGUAGES)

    # Upload the results
    if upload:
        video_id = YouTube(video_url).video_id
        # Upload english
        try:
            upload_caption(youtube_api, video_id, language_code="en", name="", caption_file=caption_path)
        except Exception as e:
            print(f"Failed to upload {caption_path}\n\n{e}\n\n")
        # Upload all other languages
        upload_all_new_captions(youtube_api, caption_dir, video_id)
        # TODO, upload the titles and descriptions


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Video url')
    parser.add_argument('video_url', type=str, help='YouTube url')
    parser.add_argument('--no-upload', action='store_false', dest='upload', help='If set, upload will be disabled.')
    args = parser.parse_args()

    auto_caption(args.video_url, upload=args.upload)