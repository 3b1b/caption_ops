from __future__ import annotations

import argparse

from pathlib import Path

import pysrt

from caption_ops.srt_ops import sub_rip_time_to_seconds
from caption_ops.srt_ops import write_srt
from caption_ops.transcribe_video import segments_to_sentences


def captions_to_sentence_srt(srt_file, output_file=None):
    """
    Groups the captions of an srt file into one caption per sentence,
    say to hand off to a translator.
    """
    srt_file = Path(srt_file)
    if output_file is None:
        output_file = Path(srt_file.parent, "transcription_sentences.srt")

    subs = pysrt.open(srt_file)
    segments = [
        [
            sub.text.replace("\n", " "),
            sub_rip_time_to_seconds(sub.start),
            sub_rip_time_to_seconds(sub.end),
        ]
        for sub in subs
    ]
    sentences, time_ranges = segments_to_sentences(segments)
    if not sentences:
        raise Exception(f"No sentences found in {srt_file}")

    write_srt(
        [
            [sentence, start_time, end_time]
            for sentence, (start_time, end_time) in zip(sentences, time_ranges)
        ],
        output_file,
    )
    return output_file


def main():
    parser = argparse.ArgumentParser(
        description='Group the captions of an srt file into one caption per sentence'
    )
    parser.add_argument('srt_file', type=str, help='path to the input srt file')
    parser.add_argument(
        'output_file', type=str, nargs='?', default=None,
        help='path to the output srt (defaults to transcription_sentences.srt alongside the input)',
    )
    args = parser.parse_args()

    output_file = captions_to_sentence_srt(args.srt_file, args.output_file)
    print(f"Wrote sentences to {output_file}")


if __name__ == "__main__":
    main()
