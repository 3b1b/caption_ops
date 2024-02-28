import argparse
import os
import pysrt
from pathlib import Path

from helpers import get_web_id_to_video_id_map
from helpers import get_all_files_with_ending
from helpers import json_load
from helpers import json_dump
from helpers import temporary_message
from helpers import get_sentences

from sentence_timings import get_sentence_timings
from sentence_timings import find_closest_aligning_substrings
from sentence_timings import write_sentence_timing_file
from srt_ops import write_srt_from_sentences_and_time_ranges

from upload import get_youtube_api
from upload import upload_caption
from upload import upload_video_localizations


def main(input_file: str, upload=True):
    input_path = Path(input_file)
    if not os.path.exists(input_path):
        raise Exception(f"{input_path} does not exist")

    if input_path.suffix == ".txt":
        full_text = " ".join([
            line.strip()
            for line in input_path.read_text().split("\n")
        ])
    elif input_path.suffix == ".srt":
        subs = pysrt.open(str(input_path))
        full_text = " ".join([sub.text.replace("\n", " ") for sub in subs])
    else:
        raise Exception("input_path must be txt or srt")

    sentences = get_sentences(full_text)

    # Update sentence timings file
    folder = input_path.parent
    word_timings_file = Path(folder, "word_timings.json")
    sent_timings_file = Path(folder, "sentence_timings.json")
    captions_file = Path(folder, "captions.srt")
    transcript_file = Path(folder, "transcript.txt")

    word_timings = json_load(word_timings_file)
    timings = get_sentence_timings(word_timings, sentences)

    # Sync various iterations of the transcription
    write_sentence_timing_file(sentences, timings, sent_timings_file)
    if input_path.suffix == ".txt":
        write_srt_from_sentences_and_time_ranges(sentences, timings, captions_file)
    elif input_path.suffix == ".srt":
        transcript_file.write_text("\n".join(sentences))

    # Update translation files
    trans_files = get_all_files_with_ending(
        "sentence_translations.json",
        root=str(folder.parent),
    )
    for trans_file in trans_files:
        language = Path(trans_file).parent.stem
        with temporary_message(f"Updating {language}"):
            trans = json_load(trans_file)
            trans_inputs = [obj['input'] for obj in trans]
            new_inputs = find_closest_aligning_substrings(full_text, trans_inputs)
            for obj, new_input in zip(trans, new_inputs):
                obj['input'] = new_input.strip()
            json_dump(trans, trans_file)
            
    # Upload the results
    if upload:
        web_id = folder.parent.stem
        video_id = get_web_id_to_video_id_map()[web_id]
        youtube_api = get_youtube_api()
        try:
            upload_caption(youtube_api, video_id, captions_file, replace=True)
        except Exception as e:
            print(f"Failed to upload {captions_file}\n\n{e}\n\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Video ')
    parser.add_argument('file', type=str, help='Transcription file path, either transcription.txt or captions.srt')
    parser.add_argument('--no-upload', action='store_false', dest='upload', help='If set, upload will be disabled.')
    args = parser.parse_args()

    main(args.file, upload=args.upload)
