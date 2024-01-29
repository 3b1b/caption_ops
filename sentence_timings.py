import re
import numpy as np
import pysrt
import Levenshtein

from helpers import get_sentences
from helpers import interpolate
from helpers import SENTENCE_ENDINGS

from srt_ops import sub_rip_time_to_seconds


def get_sentence_timings(
    # List of triplets, (word, start_time, end_time)
    words_with_timings,
    # The assumption is that these loosely match those formed by
    # concatenating the words from words_with_timings, and can
    # be fuzzily matched to the appropriate positions there
    sentences,
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

    if len(sentences) == 0:
        return []

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
        if len(guess_range) == 0:
            sent_indices.append(last)
        else:
            substrs = [full_text[i:i + len(sent2)] for i in guess_range]
            lds = [Levenshtein.distance(substr, sent2) for substr in substrs]
            sent_indices.append(guess_range[np.argmin(lds)])
    sent_indices.append(len(full_text))  # Add final fence post

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


# Hopefully all functions below here are no longer needed
def get_sentence_timings_from_srt(srt_file, end_marks=SENTENCE_ENDINGS):
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
    time_ranges = list(zip(sent_delim_times[:-1], sent_delim_times[1:]))
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

