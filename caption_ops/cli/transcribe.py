from __future__ import annotations

import argparse

from pathlib import Path

from caption_ops.srt_ops import segments_to_captions
from caption_ops.srt_ops import write_srt
from caption_ops.transcribe_video import normalize_notation
from caption_ops.transcribe_video import transcribe_segments


def transcribe_to_captions(media_file, srt_file=None, max_chars=50, tidy_notation=True):
    """
    Transcribes an audio or video file into a captions srt, with no
    caption running longer than max_chars.
    """
    media_file = Path(media_file)
    if srt_file is None:
        srt_file = Path(media_file.parent, "captions.srt")

    segments = transcribe_segments(media_file)
    if tidy_notation:
        segments = normalize_notation(segments)
    captions = segments_to_captions(segments, max_chars_per_segment=max_chars)
    if not captions:
        raise Exception(f"Nothing transcribed from {media_file}")

    write_srt(captions, srt_file)
    return srt_file


def main():
    parser = argparse.ArgumentParser(
        description='Transcribe an audio or video file into a captions srt'
    )
    parser.add_argument('media_file', type=str, help='path to an audio or video file')
    parser.add_argument(
        'srt_file', type=str, nargs='?', default=None,
        help='path to the output srt (defaults to captions.srt alongside the input)',
    )
    parser.add_argument(
        '-n', '--max-chars', type=int, default=50,
        help='maximum number of characters per caption (default 50)',
    )
    parser.add_argument(
        '--raw', action='store_true',
        help='skip the pass rewriting spelled out numbers and math as notation',
    )
    args = parser.parse_args()

    srt_file = transcribe_to_captions(
        args.media_file, args.srt_file, args.max_chars, tidy_notation=not args.raw,
    )
    print(f"Wrote captions to {srt_file}")


if __name__ == "__main__":
    main()
