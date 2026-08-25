from __future__ import annotations
from typing import Optional

import argparse
import os

from pathlib import Path
from transcribe_video import load_whisper_model
from transcribe_video import transcribe_file
from transcribe_video import words_with_timings_to_srt
from transcribe_video import save_word_timings
from sentence_timings import get_sentences_with_timings
from srt_ops import write_srt


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Audio file')
    parser.add_argument('audio_file', type=str, help='path to narration file')
    args = parser.parse_args()

    audio_file = Path(args.audio_file)
    srt_file = Path(audio_file.parent, "transcription_sentences.srt")
    word_timings_path = Path(audio_file.parent, "word_timings.json")

    # Run whisper
    model = load_whisper_model()
    transcription = transcribe_file(model, audio_file, word_timestamps=True)
    word_timings = save_word_timings(transcription, word_timings_path)
    sentences, time_ranges = get_sentences_with_timings(word_timings)
    segments = [[sent, start, end] for sent, (start, end) in zip(sentences, time_ranges)]
    write_srt(segments, srt_file)
    print(f"Wrote transcription to {srt_file}")
