import Levenshtein
import torch
import numpy as np
import json
from pathlib import Path

import whisper
from whisper.utils import get_writer

from helpers import temporary_message
from helpers import get_sentences
from helpers import json_dump
from helpers import json_load
from helpers import SENTENCE_ENDINGS

from sentence_timings import get_sentence_timings

from srt_ops import write_srt_from_sentences_and_time_ranges

### Transcribing with whisper


def load_whisper_model(model_name="medium.en"):
    with temporary_message("Loading Whisper model"):
        model = whisper.load_model(model_name)
    return model


def transcribe_file(
    model,
    audio_file: str,
    word_timestamps = True
):
    """
    Runs Whisper on an audio file

    Returns
    -------
    A dictionary containing the resulting text ("text") and segment-level details ("segments"), and
    the spoken language ("language"), which is detected when `decode_options["language"]` is None.
    """
    with temporary_message(f"Transcribing file: {audio_file}\n"):
        transcription = model.transcribe(
            audio_file,
            verbose = False,
            language = "en",
            fp16=torch.cuda.is_available(),
            word_timestamps=word_timestamps,
        )
    return transcription


def get_words_with_timings(whisper_segments):
    return [
        [chunk['word'], chunk['start'], chunk["end"]]
        for segment in whisper_segments
        for chunk in segment['words']
    ]


def strongly_matched_transcription_to_srt(transcription: dict, srt_path: str | Path):
    srt_path = Path(srt_path)

    # Record the word timings
    timing_file = Path(srt_path.parent, "word_timings.json")
    words_with_timings = get_words_with_timings(transcription["segments"])
    json_dump(words_with_timings, timing_file)

    words, starts, ends = zip(*words_with_timings)
    sentences = get_sentences("".join(words))
    if len(sentences) == 0:
        print(f"Didn't write {srt_path}, no text")
        return
    # Add warning for long sentences
    if max(map(len, sentences)) > 2000:
        print(
            f"Warning, {srt_path} has a very long sentence," +\
            "and may not have been transcribed with full punctuation."
        )
    time_ranges = get_sentence_timings(words_with_timings, sentences)

    # Write improved captions
    write_srt_from_sentences_and_time_ranges(sentences, time_ranges, srt_path)


def simple_transcription_to_srt(transcription: dict, srt_path: str | Path):
    srt_path = Path(srt_path)
    # Directly write whisper segments to file
    writer = get_writer("srt", str(srt_path.parent))
    writer(transcription, srt_path.stem, {})

