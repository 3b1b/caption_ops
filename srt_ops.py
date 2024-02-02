import re
import regex
import numpy as np
from pathlib import Path
import pysrt
import datetime

from helpers import interpolate
from helpers import SENTENCE_ENDING_PATTERN
from helpers import PUNCTUATION_PATTERN


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


def write_srt_from_sentences_and_time_ranges(
    sentences,
    time_ranges,
    output_file_path,
    max_chars_per_segment=90,
):
    mcps = max_chars_per_segment

    texts = []
    starts = []
    ends = []
    for sentence, (start_time, end_time) in zip(sentences, time_ranges):
        n_chars = len(sentence)
        if n_chars == 0:
            continue
        # Bias towards cuts which are on punctuation marks,
        # and try to keep the segments from being too uneven
        n_segments = int(np.ceil(n_chars / mcps))
        best_step = (n_chars // n_segments)
        half = mcps // 2
        cuts = [0]
        while cuts[-1] < n_chars:
            lh = cuts[-1]
            rh = lh + mcps
            best_cut = lh + best_step
            punc_indices, space_indices = [
                [lh + half + match.end() for match in regex.finditer(pattern, sentence[lh + half:rh])]
                for pattern in [PUNCTUATION_PATTERN, " "]
            ]
            if rh >= n_chars:
                # We're at the end of a sentence
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
        for lh, rh in zip(cuts, cuts[1:]):
            texts.append(sentence[lh:rh])
            starts.append(interpolate(start_time, end_time, lh / n_chars))
            ends.append(interpolate(start_time, end_time, rh / n_chars),)
    # Correct the case of time overlaps between sentences causing things to get out of order
    starts.sort()
    ends.sort()

    # Write the srt
    segments = list(zip(texts, starts, ends))
    write_srt(segments, output_file_path)
