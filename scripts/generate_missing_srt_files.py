#!/usr/bin/env python3
"""
Generate transcription_sentences.srt files from existing word_timings.json files.

This script walks through the audio_tracks directory and creates missing SRT files
by processing the word timings data.
"""

from __future__ import annotations

import json
from pathlib import Path

from sentence_timings import get_sentences_with_timings
from srt_ops import write_srt


def json_load(path: Path) -> dict:
    """Load JSON data from a file."""
    with open(path, 'r') as f:
        return json.load(f)


def process_audio_tracks_directory(base_dir: Path, dry_run: bool = False) -> None:
    """
    Walk through audio_tracks directory and generate missing SRT files.

    Args:
        base_dir: Path to the audio_tracks directory
        dry_run: If True, only print what would be done without actually creating files
    """
    if not base_dir.exists():
        print(f"Error: Directory {base_dir} does not exist")
        return

    generated_count = 0
    skipped_count = 0

    # Walk through all subdirectories
    for word_timings_path in base_dir.rglob("word_timings.json"):
        srt_path = word_timings_path.parent / "transcription_sentences.srt"

        if srt_path.exists():
            skipped_count += 1
            continue

        try:
            # Load word timings and generate SRT
            word_timings = json_load(word_timings_path)
            sentences, time_ranges = get_sentences_with_timings(word_timings)
            segments = [[sent, start, end] for sent, (start, end) in zip(sentences, time_ranges)]

            if dry_run:
                print(f"Would generate: {srt_path}")
            else:
                write_srt(segments, srt_path)
                print(f"Generated: {srt_path}")

            generated_count += 1

        except Exception as e:
            print(f"Error processing {word_timings_path}: {e}")

    print(f"\nSummary:")
    print(f"  Generated: {generated_count} SRT files")
    print(f"  Skipped (already exist): {skipped_count} SRT files")


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(
        description='Generate missing transcription_sentences.srt files from word_timings.json'
    )
    parser.add_argument(
        '--audio-tracks-dir',
        type=str,
        default='/Users/grant/3Blue1Brown Dropbox/3Blue1Brown/audio_tracks',
        help='Path to the audio_tracks directory (default: %(default)s)'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Print what would be done without actually creating files'
    )

    args = parser.parse_args()

    audio_tracks_dir = Path(args.audio_tracks_dir)
    process_audio_tracks_directory(audio_tracks_dir, dry_run=args.dry_run)
