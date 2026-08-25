from __future__ import annotations

import argparse

from pathlib import Path

import pysrt

from srt_ops import sub_rip_time_to_seconds
from srt_ops import write_srt_from_sentences_and_time_ranges


def split_srt(input_file, output_file=None, max_chars_per_segment=50):
    """
    Take an srt file and rewrite it with a maximum number of
    characters per caption, preferring to cut on punctuation marks,
    then spaces, and interpolating the timings accordingly.
    """
    input_file = Path(input_file)
    if output_file is None:
        output_file = input_file.with_name(f"{input_file.stem}_split.srt")

    subs = pysrt.open(input_file)
    sentences = [sub.text.replace("\n", " ").strip() for sub in subs]
    time_ranges = [
        (sub_rip_time_to_seconds(sub.start), sub_rip_time_to_seconds(sub.end))
        for sub in subs
    ]
    write_srt_from_sentences_and_time_ranges(
        sentences,
        time_ranges,
        output_file,
        max_chars_per_segment=max_chars_per_segment,
    )
    return output_file


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description='Rewrite an srt file with a maximum number of characters per caption'
    )
    parser.add_argument('input_file', type=str, help='path to the input srt file')
    parser.add_argument(
        'output_file', type=str, nargs='?', default=None,
        help='path to the output srt file (defaults to <input>_split.srt)',
    )
    parser.add_argument(
        '-n', '--max-chars', type=int, default=50,
        help='maximum number of characters per caption (default 50)',
    )
    args = parser.parse_args()

    output_file = split_srt(args.input_file, args.output_file, args.max_chars)
    print(f"Wrote captions to {output_file}")
