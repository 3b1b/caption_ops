import Levenshtein
import torch
import numpy as np
import json
import re
from pathlib import Path
import pysrt

import whisper
from whisper.utils import get_writer

from helpers import temporary_message
from helpers import get_sentences
from helpers import SENTENCE_ENDINGS

### Transcribing with whisper


def get_words_with_timings(whisper_segments):
    return [
        [chunk['word'], chunk['start'], chunk["end"]]
        for segment in whisper_segments
        for chunk in segment['words']
    ]


def get_sentence_timings(
    # List of triplets, (word, start_time, end_time)
    words_with_timings,
    # If none, sentences are formed from the words above
    sentences=None,
    # For fuzzy matching of sentences to indices in the full text
    max_shift=20
):
    """
    Given the start and end times for a sequence of words, find the
    start and end times for setences they make up. Uses fuzzy matching
    to find alignments of the sentence to the full text
    """
    words, starts, ends = zip(*words_with_timings)
    if sentences is None:
        sentences = get_sentences("".join(words))

    # Word indices
    full_text = "".join(words)
    word_lens = list(map(len, words))
    word_indices = np.array([0, *np.cumsum(word_lens[:-1])])

    # Sentence indices, based on fuzzier matching
    sent_indices = [0]
    for sent1, sent2 in zip(sentences, sentences[1:]):
        last = sent_indices[-1]
        guess = last + len(sent1)
        guess_range = list(range(
            max(guess - max_shift, 0),
            min(guess + max_shift, len(full_text)),
        ))
        lds = [
            Levenshtein.distance(full_text[i:i + len(sent2)], sent2)
            for i in guess_range
        ]
        sent_indices.append(guess_range[np.argmin(lds)])
    sent_indices.append(len(full_text))  # Add final fence post

    time_ranges = []
    for lh, rh in zip(sent_indices, sent_indices[1:]):
        start = starts[np.argmin(abs(word_indices - lh))]
        end = ends[np.argmin(abs(word_indices - rh)) - 1]
        time_ranges.append([start, end])
    return time_ranges


def get_sentence_timings_from_word_timings(word_timing_file):
    with open(word_timing_file) as fp:
        word_timings = json.load(fp)
    words, starts, ends = zip(*word_timings)
    sentences = get_sentences("".join(words))
    time_ranges = get_sentence_timings(word_timings, sentences)
    return sentences, time_ranges


def index_of_nearest_match(word, time, all_words, all_times, index_radius=5):
    guess = np.argmin(np.abs(all_times - time))
    lev_dist = Levenshtein.distance(word, all_words[guess])
    indices = list(range(
        max(guess - index_radius, 0),
        min(guess + index_radius, len(all_words))
    ))
    lev_dists = [Levenshtein.distance(word, all_words[i]) for i in indices]
    if min(lev_dists) < lev_dist:
        return indices[np.argmin(lev_dists)]
    else:
        return guess


def refine_sentence_time_ranges(
    sentences: list[str],
    rough_ranges: list,
    words: list[str],
    starts: np.ndarray,
    ends: np.ndarray,
    index_radius=5,
):
    refined_ranges = []
    for sentence, (start, end) in zip(sentences, rough_ranges):
        sent_words = sentence.strip().split(" ")
        start_index = index_of_nearest_match(sent_words[0], start, words, starts, index_radius)
        end_index = index_of_nearest_match(sent_words[-1], end, words, ends, index_radius)
        refined_ranges.append([starts[start_index], ends[end_index]])
    return refined_ranges


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


def strongly_matched_transcription_to_srt(transcription: dict, srt_path: str | Path):
    srt_path = Path(srt_path)

    # Record the word timings
    timing_file = Path(srt_path.parent, "word_timings.json")
    words_with_timings = get_words_with_timings(transcription["segments"])
    with open(timing_file, "w") as fp:
        json.dump(words_with_timings, fp, ensure_ascii=False)

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
    from translate import write_srt_from_sentences_and_time_ranges
    write_srt_from_sentences_and_time_ranges(sentences, time_ranges, srt_path)


def simple_transcription_to_srt(transcription: dict, srt_path: str | Path):
    srt_path = Path(srt_path)
    # Directly write whisper segments to file
    writer = get_writer("srt", str(srt_path.parent))
    writer(transcription, srt_path.stem, {})

