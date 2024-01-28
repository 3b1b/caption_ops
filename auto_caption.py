import argparse
import os
from pytube import YouTube

from helpers import url_to_directory
from helpers import srt_to_txt
from helpers import AUDIO_DIRECTORY

from download import download_youtube_audio

from transcribe_video import load_whisper_model
from transcribe_video import transcribe_file
from transcribe_video import transcription_to_srt

from translate import translate_to_multiple_languages
from translate import TARGET_LANGUAGES

from upload import get_youtube_api
from upload import upload_caption
from upload import upload_all_new_captions


def auto_caption(video_url, upload=True):
    youtube_api = get_youtube_api() if upload else None

    # Get output directories
    caption_dir = url_to_directory(video_url)
    audio_dir = url_to_directory(video_url, root=AUDIO_DIRECTORY)

    # Download
    audio_file = download_youtube_audio(video_url, audio_dir)

    # Transcribe
    model = load_whisper_model()
    transcription = transcribe_file(model, audio_file)
    srt_path = Path(caption_dir, "english", "captions.srt")
    whisper_srt_path = Path(caption_dir, "english", "whisper_captions.srt")
    ensure_exists(srt_path.parent)
    simple_transcription_to_srt(transcription, whisper_srt_path)
    strongly_matched_transcription_to_srt(transcription, srt_path)
    srt_to_txt(srt_path)

    # Translate
    translate_to_multiple_languages(srt_path, languages=TARGET_LANGUAGES)
    translate_title_to_multiple_languages(video_url, languages=TARGET_LANGUAGES)

    if upload:
        video_id = YouTube(video_url).video_id
        # Upload english
        try:
            upload_caption(
                youtube_api,
                video_id,
                language_code="en",
                name="",
                caption_file=caption_file,
            )
        except Exception as e:
            print(f"Failed to upload {caption_file}\n\n{e}\n\n")
        # Upload all other languages
        upload_all_new_captions(youtube_api, caption_dir, video_id)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Video url')
    parser.add_argument('video_url', type=str, help='YouTube url')
    args = parser.parse_args()

    auto_caption(args.video_url)