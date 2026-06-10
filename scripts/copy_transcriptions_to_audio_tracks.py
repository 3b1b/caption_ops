#!/usr/bin/env python3
"""
Copy transcription files from captions directory to audio_tracks directory.

Copies:
- full_sentences.srt -> transcription_sentences.srt
- word_timings.json -> word_timings.json
"""

import os
import shutil
from pathlib import Path


def copy_transcription_files():
    """Copy transcription files from captions to audio_tracks directory."""
    captions_dir = Path("/Users/grant/cs/captions")
    audio_tracks_dir = Path("/Users/grant/3Blue1Brown Dropbox/3Blue1Brown/audio_tracks")

    # Track what we copy
    copied_files = []
    skipped_files = []

    # Find all year directories
    if not captions_dir.exists():
        print(f"Error: Captions directory not found: {captions_dir}")
        return

    for year_dir in sorted(captions_dir.iterdir()):
        if not year_dir.is_dir():
            continue

        year = year_dir.name

        # Find all slug directories within the year
        for slug_dir in sorted(year_dir.iterdir()):
            if not slug_dir.is_dir():
                continue

            slug = slug_dir.name
            english_dir = slug_dir / "english"

            if not english_dir.exists():
                continue

            # Copy full_sentences.srt -> transcription_sentences.srt
            source_srt = english_dir / "full_sentences.srt"
            if source_srt.exists():
                dest_dir = audio_tracks_dir / year / slug
                dest_srt = dest_dir / "transcription_sentences.srt"

                # Create destination directory if needed
                dest_dir.mkdir(parents=True, exist_ok=True)

                # Copy the file
                shutil.copy2(source_srt, dest_srt)
                copied_files.append(f"{year}/{slug}/full_sentences.srt -> transcription_sentences.srt")
                print(f"✓ Copied {year}/{slug}/full_sentences.srt")
            else:
                skipped_files.append(f"{year}/{slug}/full_sentences.srt (not found)")

            # Copy word_timings.json
            source_json = english_dir / "word_timings.json"
            if source_json.exists():
                dest_dir = audio_tracks_dir / year / slug
                dest_json = dest_dir / "word_timings.json"

                # Create destination directory if needed
                dest_dir.mkdir(parents=True, exist_ok=True)

                # Copy the file
                shutil.copy2(source_json, dest_json)
                copied_files.append(f"{year}/{slug}/word_timings.json")
                print(f"✓ Copied {year}/{slug}/word_timings.json")
            else:
                skipped_files.append(f"{year}/{slug}/word_timings.json (not found)")

    # Print summary
    print(f"\n{'='*60}")
    print(f"Summary:")
    print(f"  Copied: {len(copied_files)} files")
    if skipped_files:
        print(f"  Skipped: {len(skipped_files)} files (not found)")
    print(f"{'='*60}")


if __name__ == "__main__":
    copy_transcription_files()
