from functools import lru_cache
from pathlib import Path
import os

from faster_whisper import WhisperModel
from tqdm import tqdm

from helpers import temporary_message
from helpers import get_sentences
from helpers import json_dump

from sentence_timings import get_sentence_timings

from srt_ops import write_srt_from_sentences_and_time_ranges


# Transcribing with faster-whisper


@lru_cache()
def load_whisper_model(model_name="medium.en"):
    with temporary_message("Loading Whisper model"):
        # Use faster-whisper with CPU optimizations
        # compute_type: int8 for speed, float16/float32 for better quality
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
    return model


def transcribe_file(
    model,
    audio_file: str,
    word_timestamps=True
):
    """
    Runs Whisper on an audio file using faster-whisper

    Returns
    -------
    A dictionary containing the resulting text ("text") and segment-level details ("segments"), and
    the spoken language ("language").
    """
    print(f"Transcribing file: {audio_file}")

    # faster-whisper returns (segments, info) where segments is an iterator
    segments, info = model.transcribe(
        audio_file,
        language="en",
        word_timestamps=word_timestamps,
        beam_size=1,  # Match OpenAI Whisper's default
    )

    # Convert segments iterator to list and format to match OpenAI Whisper's output
    segments_list = []
    full_text = []

    # Create progress bar based on audio duration
    with tqdm(total=info.duration, unit='sec', desc='Transcribing') as pbar:
        for segment in segments:
            segment_dict = {
                "start": segment.start,
                "end": segment.end,
                "text": segment.text,
            }

            # Add word-level timestamps if requested
            if word_timestamps and segment.words:
                segment_dict["words"] = [
                    {
                        "word": word.word,
                        "start": word.start,
                        "end": word.end,
                    }
                    for word in segment.words
                ]

            segments_list.append(segment_dict)
            full_text.append(segment.text)

            # Update progress bar to current segment's end time
            pbar.update(segment.end - pbar.n)

    # Return in OpenAI Whisper format for compatibility
    transcription = {
        "text": "".join(full_text),
        "segments": segments_list,
        "language": info.language,
    }

    return transcription


def transcribe_file_api(audio_file: str, word_timestamps=True):
    """
    Transcribes an audio file using OpenAI's Whisper API.

    Returns
    -------
    A dictionary containing the resulting text ("text") and segment-level details ("segments"), and
    the spoken language ("language").
    """
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("openai package not installed. Install with: pip install openai")

    api_key = os.environ.get("OPENAI_KEY")
    if not api_key:
        raise ValueError("OPENAI_KEY environment variable not set")

    with temporary_message(f"Transcribing file via API: {audio_file}\n"):
        client = OpenAI(api_key=api_key)

        with open(audio_file, "rb") as audio:
            # Request verbose JSON format with word-level timestamps
            response = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio,
                language="en",
                response_format="verbose_json",
                timestamp_granularities=["word", "segment"] if word_timestamps else ["segment"],
            )

        # Convert API response to match our expected format
        segments_list = []

        for segment in response.segments:
            segment_dict = {
                "start": segment.start,
                "end": segment.end,
                "text": segment.text,
            }

            # Add word-level timestamps if available
            if word_timestamps and hasattr(response, 'words') and response.words:
                # Filter words that belong to this segment
                segment_words = [
                    {
                        "word": word.word,
                        "start": word.start,
                        "end": word.end,
                    }
                    for word in response.words
                    if word.start >= segment.start and word.end <= segment.end
                ]
                if segment_words:
                    segment_dict["words"] = segment_words

            segments_list.append(segment_dict)

        transcription = {
            "text": response.text,
            "segments": segments_list,
            "language": response.language if hasattr(response, 'language') else "en",
        }

    return transcription


def transcribe_file_with_fallback(audio_file: str, word_timestamps=True):
    """
    Attempts to transcribe using OpenAI API first, falls back to local model if API fails.

    Returns
    -------
    A dictionary containing the resulting text ("text") and segment-level details ("segments"), and
    the spoken language ("language").
    """
    try:
        # Try API first
        return transcribe_file_api(audio_file, word_timestamps=word_timestamps)
    except Exception as e:
        print(f"API transcription failed ({e}), falling back to local model...")
        # Fall back to local model
        model = load_whisper_model()
        return transcribe_file(model, audio_file, word_timestamps=word_timestamps)


def get_words_with_timings(whisper_segments, precision=2):
    return [
        [chunk['word'], round(chunk['start'], precision), round(chunk["end"], precision)]
        for segment in whisper_segments
        for chunk in segment.get('words', [])
    ]


def save_word_timings(whisper_transcription: dict, file_path: str | Path):
    words_with_timings = get_words_with_timings(whisper_transcription["segments"])
    json_dump(words_with_timings, file_path, indent=None)
    return words_with_timings


def words_with_timings_to_srt(words_with_timings: list, srt_path: str | Path):
    words, starts, ends = zip(*words_with_timings)
    sentences = get_sentences("".join(words))
    if len(sentences) == 0:
        print(f"Didn't write {srt_path}, no text")
        return
    # Add warning for long sentences
    if max(map(len, sentences)) > 2000:
        print(
            f"Warning, {srt_path} has a very long sentence," +\
            "and may not have been transcribed with full punctuation."
        )
    time_ranges = get_sentence_timings(words_with_timings, sentences)

    # Write improved captions
    write_srt_from_sentences_and_time_ranges(sentences, time_ranges, srt_path)


def write_whisper_srt(transcription: dict, srt_path: str | Path):
    """
    Write SRT file directly from Whisper segments.
    Note: This implementation works with the faster-whisper output format.
    """
    from datetime import timedelta

    srt_path = Path(srt_path)

    def format_timestamp(seconds):
        """Convert seconds to SRT timestamp format (HH:MM:SS,mmm)"""
        td = timedelta(seconds=seconds)
        hours, remainder = divmod(td.seconds, 3600)
        minutes, seconds = divmod(remainder, 60)
        milliseconds = int(td.microseconds / 1000)
        return f"{hours:02d}:{minutes:02d}:{seconds:02d},{milliseconds:03d}"

    with open(srt_path, 'w', encoding='utf-8') as f:
        for i, segment in enumerate(transcription['segments'], start=1):
            start_time = format_timestamp(segment['start'])
            end_time = format_timestamp(segment['end'])
            text = segment['text'].strip()

            f.write(f"{i}\n")
            f.write(f"{start_time} --> {end_time}\n")
            f.write(f"{text}\n\n")

