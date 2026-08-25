from concurrent.futures import ThreadPoolExecutor
from functools import lru_cache
from pathlib import Path
import json
import re
import shutil
import subprocess
import tempfile

from faster_whisper import WhisperModel
from tqdm import tqdm

from caption_ops.helpers import get_openai_api_key
from caption_ops.helpers import get_sentences
from caption_ops.helpers import interpolate
from caption_ops.helpers import temporary_message


TRANSCRIPTION_MODEL = "gpt-4o-transcribe-diarize"
LOCAL_TRANSCRIPTION_MODEL = "medium.en"

# The diarizing models, which are the only ones handing back timings finer
# than the full transcript, refuse anything longer than the maximum below.
# Requests also come back at only about half of real time no matter how much
# audio they're given, so chunks are kept small and sent off in parallel.
MAX_API_DURATION = 1400
TARGET_CHUNK_DURATION = 300
MAX_PARALLEL_REQUESTS = 8

# Whisper listens to 16kHz mono audio anyway, so compressing to that costs
# nothing in accuracy, keeps uploads well under the size limit, and pulls the
# audio out of video files along the way
AUDIO_ARGS = ["-vn", "-ac", "1", "-ar", "16000", "-b:a", "48k"]


# Preparing audio


class MissingFFmpeg(Exception):
    pass


# Somewhere to look besides PATH, which is nearly empty when called from
# something like an OSX Shortcut
FFMPEG_DIRECTORIES = ["/opt/homebrew/bin", "/usr/local/bin", "/usr/bin"]


@lru_cache()
def get_ffmpeg_path(name="ffmpeg"):
    path = shutil.which(name)
    if path:
        return path
    for directory in FFMPEG_DIRECTORIES:
        candidate = Path(directory, name)
        if candidate.exists():
            return str(candidate)
    raise MissingFFmpeg(
        f"Could not find {name}, looked on PATH and in {', '.join(FFMPEG_DIRECTORIES)}"
    )


def run_ffmpeg(args: list):
    return subprocess.run(
        [get_ffmpeg_path(), "-y", "-loglevel", "error", *args],
        check=True,
    )


def get_duration(media_file: str | Path):
    result = subprocess.run(
        [
            get_ffmpeg_path("ffprobe"), "-v", "error", "-of", "csv=p=0",
            "-show_entries", "format=duration", str(media_file),
        ],
        check=True, capture_output=True, text=True,
    )
    return float(result.stdout.strip())


def extract_audio(media_file: str | Path, output_file: str | Path, start=None, end=None):
    """
    Pulls a compact mono mp3 out of an audio or video file, optionally
    only the portion between the given times.
    """
    args = []
    if start is not None:
        args.extend(["-ss", str(start)])
    if end is not None:
        args.extend(["-to", str(end)])
    run_ffmpeg([*args, "-i", str(media_file), *AUDIO_ARGS, str(output_file)])
    return output_file


def find_silences(media_file: str | Path, noise="-30dB", min_duration=0.25):
    """
    Returns the midpoint of each stretch of near silence, as good places
    to cut a long file without slicing through the middle of a word.
    """
    result = subprocess.run(
        [
            get_ffmpeg_path(), "-loglevel", "info", "-i", str(media_file), "-vn",
            "-af", f"silencedetect=noise={noise}:d={min_duration}",
            "-f", "null", "-",
        ],
        capture_output=True, text=True,
    )
    starts = [float(m) for m in re.findall(r"silence_start: (-?[\d.]+)", result.stderr)]
    ends = [float(m) for m in re.findall(r"silence_end: (-?[\d.]+)", result.stderr)]
    return [0.5 * (start + end) for start, end in zip(starts, ends)]


def get_chunk_ranges(duration, silences, target=TARGET_CHUNK_DURATION, maximum=MAX_API_DURATION):
    """
    Divides a file up into (start, end) ranges of roughly the target length,
    and never longer than the maximum, cutting during silences where possible.
    """
    cuts = [0.0]
    # Keep cutting until what's left makes a reasonably sized last chunk
    while duration - cuts[-1] > 1.5 * target:
        low = cuts[-1]
        best_cut = low + target
        # Any silence far enough along to make progress, but not so far as
        # to leave a chunk the API would refuse
        candidates = [time for time in silences if low + 1 < time < low + maximum]
        if candidates:
            cuts.append(min(candidates, key=lambda time: abs(time - best_cut)))
        else:
            print("Warning, found no silence to cut on, so cutting mid-speech")
            cuts.append(best_cut)
    cuts.append(duration)
    return list(zip(cuts, cuts[1:]))


# Transcribing to timed segments


def transcribe_segments_api(media_file: str | Path, model=TRANSCRIPTION_MODEL):
    """
    Transcribes an audio or video file with the OpenAI API.

    Returns
    -------
    A list of [text, start_time, end_time] segments, which tend to break at
    clause boundaries rather than at full sentences.
    """
    try:
        from openai import OpenAI
    except ImportError:
        raise ImportError("openai package not installed. Install with: pip install openai")

    client = OpenAI(api_key=get_openai_api_key())
    media_file = Path(media_file)

    with tempfile.TemporaryDirectory() as temp_dir:
        with temporary_message(f"Looking for good places to cut {media_file.name}"):
            duration = get_duration(media_file)
            chunk_ranges = get_chunk_ranges(duration, find_silences(media_file))

        progress_bar = tqdm(total=len(chunk_ranges), desc="Transcribing", unit="chunk")

        def transcribe_chunk(args):
            n, (start, end) = args
            chunk_file = Path(temp_dir, f"chunk{n}.mp3")
            extract_audio(media_file, chunk_file, start=start, end=end)
            with open(chunk_file, "rb") as audio:
                response = client.audio.transcriptions.create(
                    model=model,
                    file=audio,
                    language="en",
                    response_format="diarized_json",
                    # Required by the diarizing models
                    chunking_strategy="auto",
                )
            progress_bar.update(1)
            # Times come back relative to the start of the chunk
            return [
                [segment.text, segment.start + start, segment.end + start]
                for segment in response.segments
            ]

        with ThreadPoolExecutor(max_workers=MAX_PARALLEL_REQUESTS) as executor:
            # Results come back in the order the chunks were sent
            chunk_segments = list(executor.map(transcribe_chunk, enumerate(chunk_ranges)))
        progress_bar.close()

    return [segment for chunk in chunk_segments for segment in chunk]


@lru_cache()
def load_whisper_model(model_name=LOCAL_TRANSCRIPTION_MODEL):
    with temporary_message("Loading Whisper model"):
        # compute_type: int8 for speed, float16/float32 for better quality
        model = WhisperModel(model_name, device="cpu", compute_type="int8")
    return model


def transcribe_segments_local(media_file: str | Path, model_name=LOCAL_TRANSCRIPTION_MODEL):
    """
    Transcribes an audio or video file with a local copy of Whisper.

    Returns
    -------
    A list of [text, start_time, end_time] segments.
    """
    model = load_whisper_model(model_name)
    segments, info = model.transcribe(
        str(media_file),
        language="en",
        beam_size=1,  # Match OpenAI Whisper's default
    )
    result = []
    with tqdm(total=info.duration, unit='sec', desc='Transcribing') as progress_bar:
        for segment in segments:
            result.append([segment.text, segment.start, segment.end])
            progress_bar.update(segment.end - progress_bar.n)
    return result


def transcribe_segments(media_file: str | Path):
    """
    Transcribes via the API where possible, since it's both faster and better
    punctuated, falling back on a local model otherwise.

    Returns
    -------
    A list of [text, start_time, end_time] segments.
    """
    try:
        print(f"Transcribing by API...")
        return transcribe_segments_api(media_file)
    except MissingFFmpeg:
        raise
    except Exception as e:
        print(f"API transcription failed ({e}), falling back on the local model...")
        return transcribe_segments_local(media_file)


# Cleaning up how the transcription is written


NOTATION_MODEL = "gpt-5.4-mini"
NOTATION_BATCH_SIZE = 40

# The diarizing models take no prompt of their own, so anything we want to tell
# the transcriber about the subject matter has to happen in a pass like this
NOTATION_INSTRUCTIONS = """
You are tidying up the transcription of a 3Blue1Brown video, a YouTube channel
about mathematics, to be shown as captions. Rewrite only how things are
written, never what is said.

Do change:
- Spelled out numbers become digits, e.g. "twenty twenty five by twenty twenty
  five" -> "2025x2025", "negative zero point five" -> "-0.5", "two thirds" -> "2/3".
- Single letters standing in for variables stay capitalized as spoken, and
  spoken math notation which is unambiguous becomes symbols, e.g.
  "x squared" -> "x^2", "e to the i t" -> "e^(it)".
- Spoken Greek letter names become the letters themselves, e.g. "pi" -> "π",
  "theta" -> "θ", "lambda" -> "λ", "sigma" -> "σ", "epsilon" -> "ε",
  "omega" -> "ω", "phi" -> "φ", "mu" -> "µ", "delta" -> "δ", "alpha" -> "α".
  Capital forms where that is what's meant, e.g. "capital sigma" -> "Σ".
  Leave the word alone where it is being used as an ordinary word rather than
  as a symbol, as in "pi is irrational" or the name of a letter being taught.
- An index spoken after a variable becomes a subscript, e.g. "lambda one"
  -> "λ_1", "x sub i" -> "x_i", "a n plus one" -> "a_(n+1)". Only do this
  where the number is plainly an index rather than a quantity, so
  "lambda one" -> "λ_1" but "one lambda" stays as it is.
- Fix the spelling of names and jargon, e.g. Euler, Fourier, Taylor, Pythagorean,
  eigenvector, sine, cosine, radian, matrix, 3Blue1Brown.

Do not change:
- The wording, word order, or punctuation of anything else.
- Filler words, false starts, or contractions. Leave them exactly as they are.
- Anything you are unsure about. Leaving a phrase alone is always the safe choice.

You will be given a JSON array of transcript pieces. Reply with a JSON object of
the form {"texts": [...]}, holding exactly as many strings, in the same order,
each the tidied version of the input at the same position. A piece may begin or
end mid-sentence; leave it that way.
"""


def normalize_notation(segments: list, model=NOTATION_MODEL):
    """
    Rewrites the transcription in the notation a reader expects, e.g. turning
    "twenty twenty five by twenty twenty five" into "2025x2025", which also
    keeps such phrases from eating up several captions' worth of space.

    Timings are untouched, and any batch the model mangles is left as it was.
    """
    from openai import OpenAI

    client = OpenAI(api_key=get_openai_api_key())
    batches = [
        segments[index:index + NOTATION_BATCH_SIZE]
        for index in range(0, len(segments), NOTATION_BATCH_SIZE)
    ]

    progress_bar = tqdm(total=len(batches), desc="Tidying notation", unit="batch")

    def clean_batch(batch):
        texts = [text for text, _, _ in batch]
        try:
            response = client.chat.completions.create(
                model=model,
                response_format={"type": "json_object"},
                messages=[
                    {"role": "system", "content": NOTATION_INSTRUCTIONS},
                    {"role": "user", "content": json.dumps(texts)},
                ],
            )
            new_texts = json.loads(response.choices[0].message.content)["texts"]
            if len(new_texts) != len(texts) or not all(isinstance(t, str) for t in new_texts):
                raise ValueError(f"Expected {len(texts)} strings, got {new_texts}")
        except Exception as e:
            print(f"Leaving a batch as it was, tidying it failed ({e})")
            new_texts = texts
        progress_bar.update(1)
        return [
            [new_text or text, start, end]
            for new_text, (text, start, end) in zip(new_texts, batch)
        ]

    with ThreadPoolExecutor(max_workers=MAX_PARALLEL_REQUESTS) as executor:
        results = list(executor.map(clean_batch, batches))
    progress_bar.close()

    return [segment for batch in results for segment in batch]


# Grouping segments into sentences


def segments_to_sentences(segments: list):
    """
    Joins up segments, which tend to break mid-sentence, into full sentences,
    interpolating the timings for any sentence break which lands in the
    middle of a segment.

    Returns
    -------
    A list of sentences, and a list of matching (start_time, end_time) pairs.
    """
    # Concatenate the segments, tracking where in the full text each one sits
    full_text = ""
    spans = []
    for text, start, end in segments:
        text = text.strip()
        if not text:
            continue
        if full_text:
            full_text += " "
        spans.append([len(full_text), len(full_text) + len(text), start, end])
        full_text += text

    if not spans:
        return [], []

    def time_at(index):
        # Read off the time at a given point in the text, assuming that within
        # any one segment the words come at a constant rate
        for char_start, char_end, start, end in spans:
            if index <= char_end:
                alpha = (index - char_start) / max(char_end - char_start, 1)
                return interpolate(start, end, min(max(alpha, 0), 1))
        return spans[-1][3]

    sentences = get_sentences(full_text)
    time_ranges = []
    cursor = 0
    for sentence in sentences:
        start_index = full_text.find(sentence, cursor)
        if start_index < 0:
            start_index = cursor
        cursor = start_index + len(sentence)
        time_ranges.append((time_at(start_index), time_at(cursor)))

    if sentences and max(map(len, sentences)) > 2000:
        print(
            "Warning, a very long sentence was found, so the transcription " +\
            "may not have picked up on the punctuation."
        )

    return sentences, time_ranges
