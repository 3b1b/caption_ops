import argparse
import os
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


def main(txt_path, upload=True):
    if not os.path.exists(txt_path):
        raise Exception(f"{txt_path} does not exist")

    txt_path = Path(txt_path)
    full_text = " ".join([
        line.strip()
        for line in txt_path.read_text().split("\n")
    ])
    sentences = get_sentences(full_text)

    # Update sentence timings file
    word_timings_file = Path(txt_path.parent, "word_timings.json")
    sent_timings_file = Path(txt_path.parent, "sentence_timings.json")
    captions_file = Path(txt_path.parent, "captions.srt")

    word_timings = json_load(word_timings_file)
    timings = get_sentence_timings(word_timings, sentences)
    write_sentence_timing_file(sentences, timings, sent_timings_file)

    # Update translation files
    trans_files = get_all_files_with_ending(
        "sentence_translations.json",
        root=txt_path.parent.parent,
    )
    for trans_file in trans_files:
        with temporary_message(f"Updating {trans_file}"):
            trans = json_load(trans_file)
            trans_inputs = [obj['input'] for obj in trans]
            new_inputs = find_closest_aligning_substrings(full_text, trans_inputs)
            for obj, new_input in zip(trans, new_inputs):
                obj['input'] = new_input.strip()
            json_dump(trans, trans_file)
            
    # Update srt
    write_srt_from_sentences_and_time_ranges(sentences, timings, captions_file)
    if upload:
        web_id = txt_path.parent.parent.stem
        video_id = get_web_id_to_video_id_map()[web_id]
        youtube_api = get_youtube_api()
        try:
            upload_caption(youtube_api, video_id, captions_file, replace=True)
        except Exception as e:
            print(f"Failed to upload {captions_file}\n\n{e}\n\n")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Video ')
    parser.add_argument('file', type=str, help='Transcription file path')
    args = parser.parse_args()

    main(args.file)
