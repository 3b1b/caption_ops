import re
import regex
import numpy as np
from pathlib import Path
import pysrt
import datetime

from caption_ops.helpers import interpolate
from caption_ops.helpers import SENTENCE_ENDING_PATTERN
from caption_ops.helpers import CAPTION_BREAK_PATTERN


SENTENCE_ENDING_CHARS = tuple(".!?।۔՝։።။។፡。！？")


def format_time(seconds):
    # Function to convert seconds to HH:MM:SS,mmm format
    delta = datetime.timedelta(seconds=seconds)
    hours, remainder = divmod(delta.seconds, 3600)
    minutes, seconds = divmod(remainder, 60)
    milliseconds = delta.microseconds // 1000
    return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"


def unformat_time(timestamp):
    if not (timestamp.count(":") == 2 and timestamp.count(",") <= 1):
        raise Exception(f"Incorrectly formatted timestamp: {timestamp}")
    if "," in timestamp:
        hms, miliseconds = timestamp.split(",")
    else:
        hms = timestamp
        miliseconds = 0
    hours, minutes, seconds = hms.split(":")
    return 3600 * int(hours) + 60 * int(minutes) + int(seconds) + 0.001 * int(miliseconds)


def sub_rip_time_to_seconds(sub_rip_time):
    return sum((
        sub_rip_time.hours * 3600,
        sub_rip_time.minutes * 60,
        sub_rip_time.seconds,
        sub_rip_time.milliseconds / 1000.0
    ))


def write_srt(segments, file_name):
    subrip_items = [
        pysrt.SubRipItem(
            index=index,
            start=pysrt.SubRipTime.from_ordinal(int(start_seconds * 1000)),
            end=pysrt.SubRipTime.from_ordinal(int(end_seconds * 1000)),
            text=text,
        )
        for index, (text, start_seconds, end_seconds) in enumerate(segments, start=1)
    ]
    # Save the subtitles to an SRT file
    subs = pysrt.SubRipFile(items=subrip_items)
    subs.save(file_name, encoding='utf-8')
    return file_name


def srt_to_txt(srt_file, txt_file_name="transcript"):
    subs = pysrt.open(srt_file)
    text = " ".join([sub.text.replace("\n", " ") for sub in subs])
    if not re.findall("[.!?]$", text):
        text += "."

    txt_path = Path(Path(srt_file).parent, txt_file_name).with_suffix(".txt")
    punc = SENTENCE_ENDING_PATTERN
    sentences = [
        sentence.strip() + mark
        for sentence, mark in zip(
            re.split(punc, text),
            re.findall(punc, text),
        )
    ]
    with open(txt_path, "w", encoding='utf-8') as fp:
        fp.write("\n".join(sentences))


def split_segment(text, start_time, end_time, max_chars):
    """
    Cuts one timed piece of text into pieces of at most max_chars, biasing
    towards cuts which land on punctuation marks, and keeping the pieces
    from being too uneven.

    Returns
    -------
    A list of [text, start_time, end_time] pieces.
    """
    n_chars = len(text)
    if n_chars == 0:
        return []

    n_segments = int(np.ceil(n_chars / max_chars))
    best_step = (n_chars // n_segments)
    half = max_chars // 2
    cuts = [0]
    while cuts[-1] < n_chars:
        lh = cuts[-1]
        rh = lh + max_chars
        best_cut = lh + best_step
        punc_indices, space_indices = [
            [lh + half + match.end() for match in regex.finditer(pattern, text[lh + half:rh])]
            for pattern in [CAPTION_BREAK_PATTERN, " "]
        ]
        if rh >= n_chars:
            # We're at the end
            cuts.append(n_chars)
        elif punc_indices:
            # Try to cut on a punctuation mark
            index = np.argmin([abs(pi - best_cut) for pi in punc_indices])
            cuts.append(punc_indices[index])
        elif space_indices:
            # Otherwise, at least cut on a space
            index = np.argmin([abs(si - best_cut) for si in space_indices])
            cuts.append(space_indices[index])
        else:
            # Otherwise, e.g. in character-based languages, just take what you can get
            cuts.append(best_cut)

    return [
        [
            text[lh:rh].strip(),
            interpolate(start_time, end_time, lh / n_chars),
            interpolate(start_time, end_time, rh / n_chars),
        ]
        for lh, rh in zip(cuts, cuts[1:])
        if text[lh:rh].strip()
    ]


def segments_to_captions(segments, max_chars_per_segment=50, join_neighbors=True):
    """
    Turns timed segments into captions of at most max_chars_per_segment,
    splitting up any which run long, and, unless told otherwise, joining up
    consecutive ones which are short enough to share a line.

    Returns
    -------
    A list of [text, start_time, end_time] captions.
    """
    pieces = [
        piece
        for text, start_time, end_time in segments
        for piece in split_segment(text.strip(), start_time, end_time, max_chars_per_segment)
    ]

    # Join up neighbors which fit together on one line, but never across the
    # end of a sentence, so that sentences can be read back off of the result
    captions = []
    for text, start_time, end_time in pieces:
        fits = captions and len(captions[-1][0]) + 1 + len(text) <= max_chars_per_segment
        mid_sentence = captions and not captions[-1][0].endswith(SENTENCE_ENDING_CHARS)
        if join_neighbors and fits and mid_sentence:
            captions[-1][0] += " " + text
            captions[-1][2] = end_time
        else:
            captions.append([text, start_time, end_time])

    # Correct the case of time overlaps causing things to get out of order,
    # nudging each caption to begin no sooner than the last one ended
    for index in range(1, len(captions)):
        captions[index][1] = max(captions[index][1], captions[index - 1][2])
        captions[index][2] = max(captions[index][2], captions[index][1])

    return captions


def write_srt_from_sentences_and_time_ranges(
    sentences,
    time_ranges,
    output_file_path,
    max_chars_per_segment=90,
):
    segments = [
        [sentence, start_time, end_time]
        for sentence, (start_time, end_time) in zip(sentences, time_ranges)
    ]
    # Sentences stay on their own lines here, for the sake of the
    # translation pipelines which line captions up with sentences
    captions = segments_to_captions(
        segments, max_chars_per_segment, join_neighbors=False,
    )
    write_srt(captions, output_file_path)
