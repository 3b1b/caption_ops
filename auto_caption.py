import argparse
import os
from pytube import YouTube
from pathlib import Path

from helpers import url_to_directory
from helpers import ensure_exists
from helpers import json_load
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


def recaption_everything():
    from helpers import get_videos_information
    videos_info = get_videos_information()
    urls = videos_info["Video URL"]
    model = load_whisper_model()

    for url in urls[82::-1]:
        caption_dir = url_to_directory(url)
        audio_dir = url_to_directory(url, root=AUDIO_DIRECTORY)
        audio_file = Path(audio_dir, "original_audio.mp4")
        if not os.path.exists(audio_file):
            audio_file = download_youtube_audio(url, audio_dir)
        # Transcribe
        try:
            en_dir = ensure_exists(Path(caption_dir, "english"))
            srt_path = Path(en_dir, "captions.srt")
            whisper_srt_path = Path(en_dir, "whisper_captions.srt")
            timing_file = Path(en_dir, "word_timings.json")

            transcription = transcribe_file(model, str(audio_file))
            word_timing_file = save_word_timings(transcription, timing_file)
            write_whisper_srt(transcription, whisper_srt_path)
            words_with_timings_to_srt(json_load(word_timing_file), srt_path)
            srt_to_txt(srt_path)
        except Exception as e:
            print(f"\n\n{e}\n\n")


def auto_caption(video_url, upload=False):
    youtube_api = get_youtube_api() if upload else None

    # Get output directories
    caption_dir = url_to_directory(video_url)
    audio_dir = url_to_directory(video_url, root=AUDIO_DIRECTORY)

    # Download
    audio_file = download_youtube_audio(video_url, audio_dir)

    # Transcribe
    model = load_whisper_model()
    en_dir = ensure_exists(Path(caption_dir, "english"))
    srt_path = Path(en_dir, "captions.srt")
    whisper_srt_path = Path(en_dir, "whisper_captions.srt")
    timing_file = Path(en_dir, "word_timings.json")

    transcription = transcribe_file(model, audio_file)
    word_timing_file = save_word_timings(transcription, timing_file)
    write_whisper_srt(transcription, whisper_srt_path)
    words_with_timings_to_srt(json_load(word_timing_file), srt_path)
    srt_to_txt(srt_path)

    # Translate
    # TODO, it would make more sense to write this to take in the word_timing_file
    translate_to_multiple_languages(srt_path, languages=TARGET_LANGUAGES)
    translate_title_to_multiple_languages(video_url, languages=TARGET_LANGUAGES)

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