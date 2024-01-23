import os
import shutil
import numpy as np
from pathlib import Path
import json

from helpers import nearest_string
from helpers import srt_to_txt
from helpers import CAPTIONS_DIRECTORY
from helpers import temporary_message

from translate import extract_sentences_with_end_positions
from translate import get_raw_translation_file


def pull_out_all_past_translations():
    years = list(map(str, range(2015, 2024)))
    english_file = "english.srt"
    for year in years:
        year_path = Path(CAPTIONS_DIRECTORY, year)
        for subdir in os.listdir(year_path):
            captions_dir = Path(year_path, subdir)
            if not os.path.isdir(captions_dir):
                continue
            files = os.listdir(captions_dir)
            if english_file not in files:
                continue
            translated_files = [
                file
                for file in os.listdir(captions_dir)
                if file.endswith("_ai.srt")
            ]
            with temporary_message(subdir):
                for translated_file in translated_files:
                    pull_out_past_translations(captions_dir, english_file, translated_file)


def pull_out_past_translations(captions_dir, english_file, translated_file):
    english_srt = Path(captions_dir, english_file)
    trans_srt = Path(captions_dir, translated_file)
    language_name = trans_srt.stem.split("_")[0]

    with open(english_srt, 'r') as fp:
        en_srt_lines = fp.readlines()
    with open(trans_srt, 'r') as fp:
        tr_srt_lines = fp.readlines()

    en_sents, en_ends = extract_sentences_with_end_positions(en_srt_lines)
    tr_sents, tr_ends = extract_sentences_with_end_positions(tr_srt_lines)

    final_tr_sents = []
    tr_index = 0
    for en_end in en_ends[1:]:
        tr_sent = ""
        while tr_index < len(tr_ends) - 1 and tr_ends[tr_index] < en_end:
            tr_sent += tr_sents[tr_index] + " "
            tr_index += 1
        final_tr_sents.append(tr_sent.strip())

    translation = [
        dict(
            input=en_sent,
            model="nmt",
            translatedText=tr_sent
        )
        for en_sent, tr_sent in zip(en_sents, final_tr_sents)
    ]
    trans_file = get_raw_translation_file(english_srt, language_name)
    with open(trans_file, 'w', encoding='utf-8') as fp:
        json.dump(translation, fp)



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
