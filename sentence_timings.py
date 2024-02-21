import re
import numpy as np
import pysrt
import Levenshtein
from pathlib import Path

from helpers import get_sentences
from helpers import interpolate
from helpers import json_dump
from helpers import json_load
from helpers import SENTENCE_ENDING_PATTERN

from srt_ops import sub_rip_time_to_seconds


def find_closest_aligning_substring_indices(
    full_text,
    sentences,
    max_shift=100,
    radius=20,
    sentence_end_bias=2,
):
    """
    Returns a list of indices such that the substrings of full_text
    between adjascent indices roughly match the corresponding sentence
    """
    sent_end_indices = [
        m.start() for m in re.finditer(SENTENCE_ENDING_PATTERN, full_text)
    ]
    sent_indices = [0]
    for sent1, sent2 in zip(sentences, sentences[1:]):
        last_index = sent_indices[-1]
        mid_guess = last_index + len(sent1)
        guess_range = range(
            max(mid_guess - max_shift, last_index),
            min(mid_guess + max_shift, len(full_text))
        )
        if len(guess_range) == 0:
            sent_indices.append(last_index)
            continue
        left_dist = min(radius, len(sent1))
        right_dist = min(radius, len(sent2))
        query = " ".join([
            sent1[-left_dist:],
            sent2[:right_dist],
        ])
        lds = [
            Levenshtein.distance(
                full_text[guess - left_dist:guess + right_dist],
                query,
            ) + sentence_end_bias * int(guess not in sent_end_indices)
            for guess in guess_range
        ]
        sent_indices.append(guess_range[np.argmin(lds)])
    sent_indices.append(len(full_text))  # Add final fence post
    return sent_indices


def find_closest_aligning_substrings(full_text, sentences, **kwargs):
    indices = find_closest_aligning_substring_indices(full_text, sentences, **kwargs)
    return [full_text[i:j] for i, j in zip(indices, indices[1:])]


def get_sentence_timings(
    # List of triplets, (word, start_time, end_time)
    words_with_timings,
    # The assumption is that these loosely match those formed by
    # concatenating the words from words_with_timings, and can
    # be fuzzily matched to the appropriate positions there
    sentences,
    # Paramaeters fuzzy matching of sentences to indices in the full text,
    # max_shift and radius
    **kwargs
):
    """
    Given the start and end times for a sequence of words, find the
    start and end times for setences they make up. Uses fuzzy matching
    to find alignments of the sentence to the full text
    """
    words, starts, ends = zip(*words_with_timings)
    if sentences is None:
        sentences = get_sentences("".join(words))

    if len(sentences) == 0:
        return []

    # Word indices
    full_text = "".join(words)
    word_lens = list(map(len, words))
    word_indices = np.array([0, *np.cumsum(word_lens[:-1])])

    # Sentence indices, based on fuzzier matching
    sent_indices = find_closest_aligning_substring_indices(full_text, sentences, **kwargs)

    time_ranges = []
    for lh, rh in zip(sent_indices, sent_indices[1:]):
        start = starts[np.argmin(abs(word_indices - lh))]
        end = ends[np.argmin(abs(word_indices - rh)) - 1]
        time_ranges.append([start, end])
    return time_ranges


def get_sentences_with_timings(words_with_timings):
    words, starts, ends = zip(*words_with_timings)
    sentences = get_sentences("".join(words))
    time_ranges = get_sentence_timings(words_with_timings, sentences)
    return sentences, time_ranges


def write_sentence_timing_file(sentences, time_ranges, file_path):
    # Add warning for long sentences
    if max(map(len, sentences)) > 2000:
        print(
            f"Warning, very long sentence detected. Transcription" +\
            "may not have accurately captured full punctuation."
        )
    sentence_timings = [
        [sent, start, end]
        for sent, (start, end) in zip(sentences, time_ranges)
    ]
    json_dump(sentence_timings, file_path)


def extract_sentences(sentence_timings_path):
    return [obj[0] for obj in json_load(sentence_timings_path)]


# Hopefully all functions below here are no longer needed
def get_sentence_timings_from_srt(srt_file, end_marks=SENTENCE_ENDING_PATTERN):
    subs = pysrt.open(srt_file)
    full_text = ""
    sent_delim_times = [sub_rip_time_to_seconds(subs[0].start)]
    for sub in subs:
        text = sub.text.replace("\n", " ").strip() + " "
        full_text += text

        start = sub_rip_time_to_seconds(sub.start)
        end = sub_rip_time_to_seconds(sub.end)
        end_mark_positions = [match.end() for match in re.finditer(end_marks, text)]
        if len(end_mark_positions) == 0:
            continue
        fractions = np.array(end_mark_positions) / len(text)
        for frac in fractions:
            sent_delim_times.append(interpolate(start, end, frac))

    sentences = [
        (sentence + mark).strip()
        for sentence, mark in zip(
            re.split(end_marks, full_text),
            re.findall(end_marks, full_text),
        )
    ]
    starts = sent_delim_times[:-1]
    ends = sent_delim_times[1:]
    return list(zip(sentences, starts, ends))


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

