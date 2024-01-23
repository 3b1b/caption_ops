import torch
from pathlib import Path

import whisper
from whisper.utils import get_writer

from helpers import temporary_message

### Transcribing with whisper

def transcribe_file(
    model,
    audio_file: str,
):
    """
    Runs Whisper on an audio file

    Returns
    -------
    A dictionary containing the resulting text ("text") and segment-level details ("segments"), and
    the spoken language ("language"), which is detected when `decode_options["language"]` is None.
    """
    with temporary_message(f"Transcribing file: {audio_file}\n"):
        result = model.transcribe(
            audio_file,
            verbose = False,
            language = "en",
            fp16=torch.cuda.is_available(),
        )
    return result

def load_whisper_model(model_name="medium.en"):
    # DEVICE = "mps" if torch.backends.mps.is_available() else "cpu"
    with temporary_message("Loading Whisper model"):
        model = whisper.load_model(model_name)
    return model


def transcription_to_srt(
    # What transcribe_file return
    transcription: dict,  
    out_dir: str,
    out_name: str = "english",
):
    writer = get_writer("srt", out_dir)
    writer(transcription, out_name, {})
    return str(Path(out_dir, out_name).with_suffix(".srt"))


def test():
    import torch
    import whisper

    model_name = "medium.en"
    audio_file = '/Users/grant/3Blue1Brown Dropbox/3Blue1Brown/audio_tracks/2023/refractive-index-questions/original_audio.mp4'

    model = whisper.load_model(model_name)

    result = model.transcribe(
        audio_file,
        verbose = False,
        language = "en",
        fp16=torch.cuda.is_available(),
    )

