from __future__ import annotations
from typing import Optional

import argparse
import os
from pytube import YouTube
from pathlib import Path

from caption_ops.helpers import url_to_directory
from caption_ops.helpers import json_load
from caption_ops.helpers import ensure_exists
from caption_ops.helpers import get_all_video_urls
from caption_ops.helpers import AUDIO_DIRECTORY

from caption_ops.download import download_youtube_audio

from caption_ops.transcribe_video import segments_to_sentences
from caption_ops.transcribe_video import transcribe_segments

from caption_ops.translate import translate_to_multiple_languages
from caption_ops.translate import translate_video_details_multiple_languages
from caption_ops.translate import TARGET_LANGUAGES

from caption_ops.srt_ops import write_srt_from_sentences_and_time_ranges
from caption_ops.srt_ops import write_srt

from caption_ops.sentence_timings import write_sentence_timing_file

from caption_ops.download import find_mismatched_captions

from caption_ops.upload import get_youtube_api
from caption_ops.upload import upload_caption
from caption_ops.upload import upload_video_localizations


def write_whisper_transcription_files(
    audio_file,
    directory,
    captions_file_name="captions.srt",
    sentence_timings_file_name="sentence_timings.json",
    plain_text_file_name="transcript.txt",
    sentence_captions_name="full_sentences.srt",
):
    captions_path = Path(directory, captions_file_name)
    sentence_timings_path = Path(directory, sentence_timings_file_name)
    plain_text_file_path = Path(directory, plain_text_file_name)
    sentence_captions_path = Path(directory, sentence_captions_name)

    # Transcribe, or read back an earlier transcription
    if not os.path.exists(sentence_timings_path):
        sentences, time_ranges = segments_to_sentences(transcribe_segments(audio_file))
        write_sentence_timing_file(sentences, time_ranges, sentence_timings_path)

    segments = json_load(sentence_timings_path)
    sentences = [segment[0] for segment in segments]
    time_ranges = [(segment[1], segment[2]) for segment in segments]

    # One caption per sentence
    write_srt(segments, sentence_captions_path)

    # And one broken into more readable chunks
    if not os.path.exists(captions_path):
        write_srt_from_sentences_and_time_ranges(sentences, time_ranges, captions_path)

    # Write the transcription in plain text
    if not os.path.exists(plain_text_file_path):
        Path(plain_text_file_path).write_text("\n".join(sentences))

    return captions_path, sentence_timings_path


def auto_caption(video_url, upload=True, languages: Optional[list] = None):
    # youtube_api = get_youtube_api()

    languages = list(map(str.lower, languages or []))

    # Get output directories
    caption_dir = url_to_directory(video_url)
    audio_dir = url_to_directory(video_url, root=AUDIO_DIRECTORY)

    # Download
    audio_file = None
    for name in ["only_narration", "original_audio"]:
        for suffix in [".mp3", ".wav"]:
            path = Path(audio_dir, name).with_suffix(suffix)
            if os.path.exists(path):
                audio_file = path
                break
    if audio_file is None:
        raise Exception("No audio file")

    # Transcribe
    _, sentence_timings_path = write_whisper_transcription_files(
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
        # if languages:
        #     upload_video_localizations(youtube_api, caption_dir, video_id, languages)


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