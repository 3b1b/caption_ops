import os
import shutil
import numpy as np
from pathlib import Path
import json
import re
import operator as op

from helpers import nearest_string
from helpers import srt_to_txt
from helpers import temporary_message
from helpers import CAPTIONS_DIRECTORY

from translate import extract_sentences_with_time_ranges
from translate import get_sentence_translation_file
from translate import translate_srt_file
from translate import SENTENCE_ENDINGS
from translate import pycountry
from translate import translate_sentences


def is_fully_populated_translation(translation_file):
    with open(translation_file, 'r', encoding='utf-8') as fp:
        trans = json.load(fp)
    return not any(
        op.and_(
            bool(re.sub(SENTENCE_ENDINGS, "", obj["input"])),
            not bool(re.sub(SENTENCE_ENDINGS, "", obj["translatedText"]))
        )
        for obj in trans
    )


def merge_split_decimals(text):
    pattern = r'(\d+)\.\s+(\d+)'
    return re.sub(pattern, r'\1.\2', text)


def get_all_files_with_ending(ending):
    result = []
    for root, dirs, files in os.walk(CAPTIONS_DIRECTORY):
        for file in files:
            path = os.path.join(root, file)
            if path.endswith(ending):
                result.append(path)
    return result


def get_all_translation_files():
    return get_all_files_with_ending("sentence_translations.json")



def regenerate_transcripts():
    files = []
    for trans_file in get_all_translation_files():
        if is_fully_populated_translation(trans_file):
            files.append(trans_file)
            path = Path(trans_file)
            language = path.parent.stem
            en_srt = Path(path.parent.parent, "english", "captions.srt")
            try:
                translate_srt_file(en_srt, language)
            except Exception as e:
                print(f"Failed to convert {en_srt} to {language}\n\n{e}\n\n")


def stitch_separated_numbers():
    for trans_file in get_all_translation_files():
        with open(trans_file, 'r') as fp:
            trans = json.load(fp)
        if len(trans) == 0:
            continue

        new_trans = [trans[0]]
        for obj2 in trans[1:]:
            obj1 = new_trans[-1]
            s1 = obj1["input"]
            s2 = obj2["input"]
            if re.findall(r'\d\.$', s1) and re.findall(r'^\d', s2):
                ts1 = obj1["translatedText"]
                ts2 = obj2["translatedText"]
                comb_rage = [obj1["time_range"][0], obj2["time_range"][1]]

                obj1["input"] = s1 + s2
                obj1["translatedText"] = ts1 + ts2
                obj1["time_range"] = comb_rage
            else:
                new_trans.append(obj2)

        with open(trans_file, 'w') as fp:
            json.dump(new_trans, fp, indent=1, ensure_ascii=False)



def reconstruct_sentence_translations():
    for trans_file in get_all_translation_files():
        lang_dir = Path(trans_file).parent
        en_srt = Path(lang_dir.parent, "english", "captions.srt")
        lang_srt = Path(lang_dir, "auto_generated.srt")
        if not os.path.exists(lang_srt):
            continue

        # Check translation files
        if is_fully_populated_translation(trans_file):
            continue
        try:
            reconstruct_sentence_translations_from_srt(en_srt, lang_srt)
            print(trans_file)
        except Exception as e:
            print(f"Failed to form {trans_file}\n\n{e}\n\n")


def reconstruct_sentence_translations_from_srt(english_srt, translation_srt):
    en_sents, en_time_ranges = extract_sentences_with_time_ranges(english_srt)
    tr_sents, tr_time_ranges = extract_sentences_with_time_ranges(translation_srt)

    # Reconstruct aligning sentences
    def overlaps(range1, range2):
        start1, end1 = range1
        start2, end2 = range2
        return op.and_(
            abs(start1 - start2) < abs(end1 - start2),
            abs(end1 - end2) < abs(start1 - end2),
        )

    merged_tr_sents = [
        merge_split_decimals("".join(
            tr_sent
            for tr_sent, tr_range in zip(tr_sents, tr_time_ranges)
            if overlaps(tr_range, en_range)
            if re.sub(SENTENCE_ENDINGS, '', tr_sent).strip()
        ))
        for en_range in en_time_ranges
    ]

    # Structure the translation prepare save
    translation = [
        dict(
            input=en_sent,
            translatedText=tr_sent,
            model="nmt",
        )
        for en_sent, tr_sent in zip(en_sents, merged_tr_sents)
    ]
    language_name = Path(translation_srt).parent.stem
    trans_file = get_sentence_translation_file(english_srt, language_name)

    # Add time ranges based on english srt file
    for obj, time_range in zip(translation, en_time_ranges):
        obj["time_range"] = time_range

    with open(trans_file, 'w', encoding='utf-8') as fp:
        json.dump(translation, fp, indent=1, ensure_ascii=False)


def clean_broken_translations():
    key_langs = ['spanish', 'hindi', 'chinese', 'french', 'russian']
    broken_files = []
    for trans_file in get_all_translation_files():
        if not is_fully_populated_translation(trans_file):
            lang = Path(trans_file).parent.stem
            if lang in key_langs:
                broken_files.append(trans_file)

    for file in broken_files:
        if Path(file).parent.parent.stem.startswith("ldm"):
            continue
        with open(file, 'r') as fp:
            trans = json.load(fp)

        indices_to_fix = set()
        for index, group in enumerate(trans):
            if group["input"] and not group["translatedText"]:
                indices_to_fix = indices_to_fix.union({index - 1, index, index + 1})
        indices_to_fix = sorted([i for i in indices_to_fix if 0 <= i < len(trans)])
        en_sents = [trans[i]["input"] for i in indices_to_fix]
        lang_code = pycountry.languages.get(name=Path(file).parent.stem).alpha_2

        with temporary_message(f"Translating lines in {file} to {lang_code}"):
            tr_sents = [group["translatedText"] for group in translate_sentences(en_sents, lang_code)]

        for index, tr_sent in zip(indices_to_fix, tr_sents):
            trans[index]["translatedText"] = tr_sent

        with open(file, 'w') as fp:
            json.dump(trans, fp, indent=1, ensure_ascii=False)


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
