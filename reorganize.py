import os
import shutil
import numpy as np
from pathlib import Path
import json

from helpers import nearest_string
from helpers import get_videos_information
from helpers import srt_to_txt
from helpers import CAPTIONS_DIRECTORY
from helpers import temporary_message
from helpers import url_to_directory
from helpers import ensure_exists

from translate import extract_sentences_with_end_positions
from translate import get_sentence_translation_file
from translate import get_sentence_time_ranges


def change_folder_structure():
    for year in range(2015, 2024):
        year_dir = os.path.join(CAPTIONS_DIRECTORY, str(year))
        for subdir_name in os.listdir(year_dir):
            cap_dir = os.path.join(year_dir, subdir_name)
            if not os.path.isdir(cap_dir):
                continue

            # Move transcript
            transcript_file = os.path.join(cap_dir, "transcript.txt")
            if os.path.exists(transcript_file):
                en_dir = ensure_exists(os.path.join(cap_dir, "english"))
                shutil.move(
                    transcript_file,
                    os.path.join(en_dir, "transcript.txt")
                )

            # Move captions
            srts = [f for f in os.listdir(cap_dir) if f.endswith(".srt")]
            for srt in srts:
                pieces = srt.split("_")
                language = pieces[0].split(".")[0]
                lang_dir = ensure_exists(os.path.join(cap_dir, language))
                if len(pieces) == 1:
                    name = "captions.srt"
                else:
                    name = "_".join(pieces[1:]).replace("ai.srt", "auto_generated.srt")
                shutil.move(
                    os.path.join(cap_dir, srt),
                    os.path.join(lang_dir, name)
                )

            # Move raw translations
            rt_dir = os.path.join(cap_dir, "raw_translations")
            if not os.path.exists(rt_dir):
                continue
            for file in os.listdir(rt_dir):
                language = file.split(".")[0]
                shutil.move(
                    os.path.join(rt_dir, file),
                    os.path.join(cap_dir, language, "sentence_translations.json")
                )
            if len(os.listdir(rt_dir)) == 0:
                shutil.move(rt_dir, f"~/.Trash/{subdir_name}_old_raw")


def reconstruct_all_past_translations():
    videos_info = get_videos_information()
    urls = videos_info["Video URL"]
    english_file = "english.srt"

    for url in urls:
        captions_dir = url_to_directory(url, videos_info=videos_info)
        files = os.listdir(captions_dir)
        if english_file not in files:
            continue
        translated_files = [
            file
            for file in os.listdir(captions_dir)
            if file.endswith("_ai.srt")
        ]
        with temporary_message(captions_dir):
            for translated_file in translated_files:
                reconstruct_raw_translation_from_srts(captions_dir, english_file, translated_file)


def reconstruct_raw_translation_from_srts(captions_dir, english_file, translated_file):
    ## TODO! This currently functions under the assumption that both
    # files are chopped into the same segments. Before running in a
    # way that's meant to robustly recreate a raw translation json,
    # this should be updated. It probably will be fine to change it
    # so that "en_ends" and "tr_ends" have the units of seconds, instead
    # of segmenets

    english_srt = Path(captions_dir, english_file)
    trans_srt = Path(captions_dir, translated_file)
    language_name = trans_srt.stem.split("_")[0]

    with open(english_srt, 'r') as fp:
        en_srt_lines = fp.readlines()
    with open(trans_srt, 'r') as fp:
        tr_srt_lines = fp.readlines()

    en_sents, en_ends = extract_sentences_with_end_positions(en_srt_lines)
    tr_sents, tr_ends = extract_sentences_with_end_positions(tr_srt_lines)

    # Reconstruct aligning sentences
    final_tr_sents = []
    tr_index = 0
    for end in en_ends[1:]:
        tr_sent = ""
        # While the current index is farther away than the next, increment
        while tr_index < len(tr_sents) and abs(tr_ends[tr_index] - end) > abs(tr_ends[tr_index + 1] - end):
            piece = tr_sents[tr_index]
            if len(piece.replace(".", "").strip()) > 0:
                tr_sent += piece + " "
            tr_index += 1
        final_tr_sents.append(tr_sent.strip())

    # Structure the translation prepare save
    translation = [
        dict(
            input=en_sent,
            model="nmt",
            translatedText=tr_sent,
        )
        for en_sent, tr_sent in zip(en_sents, final_tr_sents)
    ]
    trans_file = get_sentence_translation_file(english_srt, language_name)

    # Get time ranges based on english srt file, add if possible
    try:
        time_ranges = get_sentence_time_ranges(en_srt_lines, en_ends)
        for obj, time_range in zip(translation, time_ranges):
            obj["time_range"] = time_range

    except Exception as e:
        print(f"Could not add time ranges to {trans_file}")

    with open(trans_file, 'w', encoding='utf-8') as fp:
        json.dump(translation, fp, indent=1, ensure_ascii=False)


def move_transcriptions(
    curr_transcript_dir,
    target_transcript_dir,
    titles,
    years,
    webids,
    urls
):
    # Copy and rename files from old to new
    stems = os.listdir(curr_transcript_dir)
    threshold = 5

    for title, year, webid, url in zip(titles, years, webids, urls):
        # Find closest name
        stem, dist = nearest_string(title, stems)
        if dist > threshold:
            print(f"No video found for {year}/{title}")
            continue

        # Prepare new path
        curr_path = Path(curr_transcript_dir, stem)
        target_path = Path(target_transcript_dir, str(year), webid)
        if not os.path.exists(target_path):
            os.makedirs(target_path)

        # Copy over files
        name_pairs = [
            ("plain_text.txt", "english.txt"),
            ("subtitles.srt", "english.srt"),
            ("audio.mp4", "original_audio.mp4"),
        ]
        for name1, name2 in name_pairs:
            try:
                shutil.copy(
                    Path(curr_path, name1),
                    Path(target_path, name2),
                )
            except FileNotFoundError:
                print(f"No file {curr_path}/plain_text.txt")

        with open(Path(target_path, "video_information.md"), "w", encoding='utf-8') as file:
            file.write(f"[Video link]({url})")


def create_ordered_videos(output_file, videos, webids, dates, categories):
    views = np.array([video.views for video in videos])
    indices = np.argsort(-views)
    with open(output_file, "w") as file:
        file.write("\n".join([
            f"{webids[n]},{dates[n]},{videos[n].views},{videos[n].watch_url},{categories[n]}"
            for n in indices
        ]))


def move_audio_files(src_dir, trg_dir, ext=".mp4"):
    for root, dirs, files in os.walk(src_dir):
        for file in files:
            if file.endswith(ext):
                path = os.path.join(root, file)
                new_path = path.replace(src_dir, trg_dir)
                os.makedirs(os.path.split(new_path)[0])
                shutil.move(path, new_path)


def all_srt_to_txt():
    src_dir = CAPTIONS_DIRECTORY
    for root, dirs, files in os.walk(src_dir):
        for file in files:
            if file.endswith("english.srt"):
                srt_to_txt(Path(root, file))


def test():
    srt_file = "/Users/grant/cs/captions/2023/prism/english.srt"
