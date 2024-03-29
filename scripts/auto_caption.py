from __future__ import annotations
from typing import Optional

import argparse
import os
from pytube import YouTube
from pathlib import Path

from helpers import url_to_directory
from helpers import json_load
from helpers import ensure_exists
from helpers import get_all_video_urls
from helpers import AUDIO_DIRECTORY

from download import download_youtube_audio

from transcribe_video import load_whisper_model
from transcribe_video import transcribe_file
from transcribe_video import words_with_timings_to_srt
from transcribe_video import save_word_timings

from translate import translate_to_multiple_languages
from translate import translate_video_details_multiple_languages
from translate import TARGET_LANGUAGES

from srt_ops import write_srt_from_sentences_and_time_ranges

from sentence_timings import get_sentences_with_timings
from sentence_timings import write_sentence_timing_file

from download import find_mismatched_captions

from upload import get_youtube_api
from upload import upload_caption
from upload import upload_video_localizations


def write_whisper_transcription_files(
    audio_file,
    directory,
    word_timings_file_name="word_timings.json",
    captions_file_name="captions.srt",
    sentence_timings_file_name="sentence_timings.json",
    plain_text_file_name="transcript.txt",
):
    word_timings_path = Path(directory, word_timings_file_name)
    captions_path = Path(directory, captions_file_name)
    sentence_timings_path = Path(directory, sentence_timings_file_name)
    plain_text_file_path = Path(directory, plain_text_file_name)

    if not os.path.exists(word_timings_path):
        model = load_whisper_model()
        # Run whisper
        transcription = transcribe_file(model, str(audio_file))
        # Save the times for each individual word
        save_word_timings(transcription, word_timings_path)
    word_timings = json_load(word_timings_path)

    # Write the sentence timings
    if not os.path.exists(sentence_timings_path):
        sentences, time_ranges = get_sentences_with_timings(word_timings)
        write_sentence_timing_file(sentences, time_ranges, sentence_timings_path)

    # Write an srt based on those word timeings
    if not os.path.exists(captions_path):
        write_srt_from_sentences_and_time_ranges(sentences, time_ranges, captions_path)

    # Write the transcription in plain text
    if not os.path.exists(plain_text_file_path):
        Path(plain_text_file_path).write_text("\n".join(sentences))

    return word_timings_path, captions_path, sentence_timings_path


def auto_caption(video_url, upload=True, languages: Optional[list]=None):
    youtube_api = get_youtube_api()

    languages = list(map(str.lower, languages or []))

    # Get output directories
    caption_dir = url_to_directory(video_url)
    audio_dir = url_to_directory(video_url, root=AUDIO_DIRECTORY)

    # Download
    audio_file = Path(audio_dir, "original_audio.mp4")
    if not os.path.exists(audio_file):
        download_youtube_audio(video_url, audio_file)

    # Transcribe
    _, _, sentence_timings_path = write_whisper_transcription_files(
        audio_file,
        directory=ensure_exists(Path(caption_dir, "english"))
    )

    # Translate
    if languages:
        translate_to_multiple_languages(sentence_timings_path, languages)
        translate_video_details_multiple_languages(youtube_api, video_url, languages)

    # Upload the results
    if upload:
        video_id = YouTube(video_url).video_id
        for path in find_mismatched_captions(video_url, ["english", *languages]):
            print(path)
            try:
                upload_caption(youtube_api, video_id, path, replace=True)
            except Exception as e:
                print(f"Failed to upload {path}\n\n{e}\n\n")
        if languages:
            upload_video_localizations(youtube_api, caption_dir, video_id, languages)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Video url')
    parser.add_argument('video', type=str, help='YouTube url, or txt file with list of urls')
    parser.add_argument('--languages', nargs='+', type=str, help='languages')
    parser.add_argument('--no-upload', action='store_false', dest='upload', help='If set, upload will be disabled.')
    args = parser.parse_args()

    # Check if arg was a url, or text file full of urls
    if args.video.endswith(".txt"):
        urls = Path(args.video).read_text().split("\n")
    else:
        urls = [args.video]

    # Pull out languages
    languages = args.languages or []
    if languages and (languages[0] == "all"):
        languages = TARGET_LANGUAGES

    for url in urls:
        auto_caption(
            url,
            upload=args.upload,
            languages=languages,
        )