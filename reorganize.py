import os
import shutil
import numpy as np
from pathlib import Path
import json
import re
import operator as op
from torch.nn.modules import instancenorm
from tqdm.auto import tqdm as ProgressDisplay

from helpers import get_all_video_urls
from helpers import get_web_id_to_video_id_map
from srt_ops import srt_to_txt
from srt_ops import interpolate
from helpers import temporary_message
from helpers import json_load
from helpers import json_dump
from helpers import get_language_code
from helpers import get_all_files_with_ending
from helpers import CAPTIONS_DIRECTORY
from helpers import SENTENCE_ENDING_PATTERN
from helpers import PUNCTUATION_PATTERN

from translate import get_sentence_translation_file
from translate import sentence_translations_to_srt
from translate import translate_sentences
from srt_ops import write_srt_from_sentences_and_time_ranges

from sentence_timings import get_substring_timings_from_srt
from sentence_timings import get_sentences_with_timings
from sentence_timings import get_sentence_timings
from sentence_timings import write_sentence_timing_file

from upload import get_youtube_api
from download import find_mismatched_captions


def is_fully_populated_translation(translation_file):
    """
    Returns false if any non-empty english sentence
    map to empty translated sentences
    """
    trans = json_load(translation_file)
    return not any(
        op.and_(
            bool(re.sub(SENTENCE_ENDING_PATTERN, "", obj["input"])),
            not bool(re.sub(SENTENCE_ENDING_PATTERN, "", obj["translatedText"]))
        )
        for obj in trans
    )


def merge_split_decimals(text):
    pattern = r'(\d+)\.\s+(\d+)'
    return re.sub(pattern, r'\1.\2', text)


def get_all_translation_files(root=CAPTIONS_DIRECTORY):
    return get_all_files_with_ending("sentence_translations.json", root)


def update_all_mismatches():
    # TODO
    youtube_api = get_youtube_api()
    urls = get_all_video_urls()
    for url in urls:
        for mismatch in find_mismatched_captions(url):
            print(mismatch)


def fix_new_captions():
    for word_timing_file in get_all_files_with_ending("word_timings.json"):
        cap_srt = Path(word_timing_file).parent.joinpath("captions.srt")
        sentences, time_ranges = get_sentences_with_timings(json_load(word_timing_file))
        write_srt_from_sentences_and_time_ranges(sentences, time_ranges, cap_srt)
        print(f"Rewrote {cap_srt}")


def fix_word_timings():
    for timing_file in get_all_files_with_ending("word_timings.json"):
        word_timings = json_load(timing_file)
        words, starts, ends = zip(*word_timings)
        starts = np.round(starts, 2)
        ends = np.round(ends, 2)
        new_timings = list(zip(words, starts, ends))
        json_dump(new_timings, timing_file, indent=None)


def create_sentence_translation_files():
    for path in ProgressDisplay(get_all_files_with_ending("word_timings.json")):
        write_sentence_timing_file(path)


def remove_translation_time_ranges():
    keys = [
      "input",
      "translatedText",
      "model",
      "n_reviews",
    ]
    for path in ProgressDisplay(get_all_files_with_ending("sentence_translations.json")):
        try:
            trans = json_load(path)
            new_trans = []
            for obj in trans:
                new_obj = dict()
                if obj.get("model", "") == "nmt":
                    obj["model"] = "google_nmt"
                for key in keys:
                    if key in obj:
                        new_obj[key] = obj[key]
                new_trans.append(new_obj)
            json_dump(new_trans, path)
        except Exception as e:
            print(f"Failed on {path}\n{e}\n\n")


def add_translation_time_ranges():
    for trans_file in ProgressDisplay(get_all_files_with_ending("sentence_translations.json")):
        trans = json_load(trans_file)
        in_sents = [t['input'] for t in trans]
        word_timings_file = Path(Path(trans_file).parent.parent, "english", "word_timings.json")
        word_timings = json_load(word_timings_file)
        time_ranges = get_sentence_timings(word_timings, in_sents)
        for obj, (start, end) in zip(trans, time_ranges):
            obj['start'] = start
            obj['end'] = end
        json_dump(trans, trans_file)


def update_sentence_timing_in_translation_files():
    for trans_file in get_all_translation_files():
        trans = json_load(trans_file)
        cap_dir = Path(trans_file).parent.parent
        timing_file = Path(cap_dir, "english", "word_timings.json")
        if not os.path.exists(timing_file):
            continue

        # Get word timings
        word_timings = json_load(timing_file)
        if len(word_timings) == 0:
            continue

        try:
            sentences = [obj['input'] for obj in trans]
            time_ranges = get_sentence_timings(word_timings, sentences)
        except Exception as e:
            print(f"Failed on {timing_file}\n\n{e}\n\n")
            continue

        for obj, time_range in zip(trans, time_ranges):
            obj["time_range"] = time_range

        json_dump(trans, trans_file)

        # Rewrite the srt
        if is_fully_populated_translation(trans_file):
            try:
                sentence_translations_to_srt(trans_file)
            except Exception as e:
                print(f"Failed to convert {trans_file} to srt\n\n{e}\n\n")


def regenerate_transcripts():
    for trans_file in get_all_translation_files():
        if is_fully_populated_translation(trans_file):
            try:
                sentence_translations_to_srt(trans_file)
            except Exception as e:
                print(f"Failed to convert {trans_file} to srt\n\n{e}\n\n")


def upload_all_titles():
    web_id_to_video_id = get_web_id_to_video_id_map()
    youtube_api = get_youtube_api()
    for title_file in get_all_files_with_ending("title.json"):
        title = json_load(title_file)["translatedText"]
        language = Path(title_file).parent.stem
        web_id = Path(title_file).parent.parent.stem
        language_code = get_language_code(language)
        upload_video_title(
            youtube_api=youtube_api,
            video_id=web_id_to_video_id[web_id],
            language_code=language_code,
            title=title
        )


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
            incorporate_srt_data_into_sentence_translations(en_srt, lang_srt)
            print(trans_file)
        except Exception as e:
            print(f"Failed to form {trans_file}\n\n{e}\n\n")


def translation_files_from_community_captions():
    srts = get_all_files_with_ending("community.srt")
    for srt in ProgressDisplay(srts):
        srt_path = Path(srt)
        trans_file = Path(srt_path.parent, "sentence_translations.json")
        if os.path.exists(trans_file):
            trans = json_load(trans_file)
            reviewed = [t['n_reviews'] > 0 for t in trans]
            if any(reviewed) or len(trans) == 0:
                # Skip these ones, which have work in them
                continue
        try:
            incorporate_srt_data_into_sentence_translations(srt_path)
        except Exception as e:
            print(f"{srt}\n{e}\n\n")


def incorporate_srt_data_into_sentence_translations(translation_srt):
    translation_srt_path = Path(translation_srt)

    # Either read in, or initialize, the sentence translations
    trans_file = Path(translation_srt_path.parent, "sentence_translations.json")
    if os.path.exists(trans_file):
        translation = json_load(trans_file)
        if len(translation) == 0:
            return
        en_sent_times = [
            [obj['input'], obj['start'], obj['end']]
            for obj in translation
        ]
    else:
        sentence_timings_file = Path(translation_srt_path.parent.parent, "english", "sentence_timings.json")
        en_sent_times = json_load(sentence_timings_file)
        if len(en_sent_times) == 0:
            return
        translation = [
            dict(
                input=en_sent,
                translatedText="",
                n_reviews=0,
                start=start,
                end=end,
            )
            for en_sent, start, end in en_sent_times
        ]

    # Get chunks of the translated text from the srt, with timings
    tr_chunk_times = get_substring_timings_from_srt(
        translation_srt,
        end_marks=PUNCTUATION_PATTERN,
        max_length=90,
    )

    def precedes(tr_sent_group, en_sent_group, alpha=0.5):
        en_sent, en_start, en_end = en_sent_group
        tr_sent, tr_start, tr_end = tr_sent_group
        mid_time = interpolate(tr_start, tr_end, alpha)
        return mid_time < en_end

    # Reconstruct aligning sentences
    tr_sents = []
    index = 0
    for en_sent_group in en_sent_times:
        tr_sent = ""
        while precedes(tr_chunk_times[index], en_sent_group):
            tr_sent += " " + tr_chunk_times[index][0].strip()
            index += 1
            if index >= len(tr_chunk_times):
                break
        tr_sents.append(tr_sent.strip())
        if index >= len(tr_chunk_times):
            break

    # Add these snippets to the translation file
    community_key = "from_community_srt"
    for obj, tr_sent in zip(translation, tr_sents):
        obj.pop(community_key, "")
        if len(tr_sent.strip()) == 0:
            continue
        obj[community_key] = tr_sent

    # Ensure correct order
    key_order = list(translation[0].keys())
    index = 3 if 'model' in key_order else 2
    key_order.insert(index, community_key)
    translation = [
        {
            key: obj[key]
            for key in key_order
            if key in obj
        }
        for obj in translation
    ]

    json_dump(translation, trans_file)



def fix_key_order():
    for trans_file in get_all_files_with_ending("sentence_translations.json"):
        trans = json_load(trans_file)
        language = Path(trans_file).parent.stem
        # Ensure correct order
        key_order = ["input", "translatedText", "model", "from_community_srt", "n_reviews", "start", "end"]
        trans = [
            {
                key: obj[key]
                for key in key_order
                if key in obj
            }
            for obj in trans
        ]

        json_dump(trans, trans_file)


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
        trans = json_load(file)
        indices_to_fix = set()
        for index, group in enumerate(trans):
            if group["input"] and not group["translatedText"]:
                indices_to_fix = indices_to_fix.union({index - 1, index, index + 1})
        indices_to_fix = sorted([i for i in indices_to_fix if 0 <= i < len(trans)])
        en_sents = [trans[i]["input"] for i in indices_to_fix]
        lang_code = get_language_code(Path(file).parent.stem)

        with temporary_message(f"Translating lines in {file} to {lang_code}"):
            tr_sents = [group["translatedText"] for group in translate_sentences(en_sents, lang_code)]

        for index, tr_sent in zip(indices_to_fix, tr_sents):
            trans[index]["translatedText"] = tr_sent

        with open(file, 'w') as fp:
            json.dump(trans, fp, indent=1, ensure_ascii=False)


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
    for file in get_all_files_with_ending(os.path.join("english", "captions.srt")):
        srt_to_txt(file)
