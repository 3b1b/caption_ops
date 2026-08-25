import os
import shutil
import numpy as np
from pathlib import Path
import json
import re
import operator as op
from torch.nn.modules import instancenorm
from tqdm.auto import tqdm as ProgressDisplay

from caption_ops.helpers import get_all_video_urls
from caption_ops.helpers import get_web_id_to_video_id_map
from caption_ops.srt_ops import srt_to_txt
from caption_ops.srt_ops import interpolate
from caption_ops.helpers import temporary_message
from caption_ops.helpers import json_load
from caption_ops.helpers import json_dump
from caption_ops.helpers import get_language_code
from caption_ops.helpers import get_all_files_with_ending
from caption_ops.helpers import CAPTIONS_DIRECTORY
from caption_ops.helpers import SENTENCE_ENDING_PATTERN
from caption_ops.helpers import PUNCTUATION_PATTERN

from caption_ops.translate import get_sentence_translation_file
from caption_ops.translate import sentence_translations_to_srt
from caption_ops.translate import translate_sentences
from caption_ops.srt_ops import write_srt_from_sentences_and_time_ranges

from caption_ops.sentence_timings import get_substring_timings_from_srt
from caption_ops.sentence_timings import get_sentences_with_timings
from caption_ops.sentence_timings import get_sentence_timings
from caption_ops.sentence_timings import write_sentence_timing_file

from caption_ops.upload import get_youtube_api
from caption_ops.download import find_mismatched_captions



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
        if any("start" not in obj or "end" not in obj for obj in trans):
            print(trans_file)

    for trans_file in get_all_files_with_ending("title.json"):
        trans = [json_load(trans_file)]
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

        json_dump(trans[0], trans_file)


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


def fill_empty_translations(web_ids):
    from caption_ops.translate import TARGET_LANGUAGES

    wid_to_dir = get_web_id_to_caption_directory_map()
    n_chars = 0
    trans_map = {lang: dict() for lang in TARGET_LANGUAGES}

    for web_id in web_ids:
        folder = wid_to_dir[web_id]
        transcript = json_load(Path(folder, "english", "sentence_timings.json"))
        en_sents = [t[0] for t in transcript]
        for language in TARGET_LANGUAGES:
            if get_all_files_with_ending("community.srt", root=Path(folder, language)):
                continue
            translation_file = Path(folder, language, "sentence_translations.json")
            if not os.path.exists(translation_file):
                continue
            try:
                translation = json_load(translation_file)
            except Exception as e:
                print(e)

            if len(translation) == len(en_sents):
                continue

            if any([obj['n_reviews'] > 0 for obj in translation]):
                continue

            # Read in known translations
            for obj in translation:
                trans_map[language][obj['input'].strip()] = obj['translatedText']
            # Gather unknown translations
            unknown_sents = [
                sent.strip()
                for sent in en_sents
                if sent not in trans_map[language]
            ]
            n_chars += sum(map(len, unknown_sents))

            with temporary_message(f"Translating {web_id}, {language}"):
                unknown_sent_translations = translate_sentences(unknown_sents, language)
            for obj in unknown_sent_translations:
                trans_map[language][obj['input'].strip()] = obj['translatedText']

            updated_translation = [
                dict(
                    input=sent.strip(),
                    translatedText=trans_map[language][sent.strip()],
                    model="DeepL",
                    n_reviews=0,
                    start=start,
                    end=end,
                )
                for sent, start, end in transcript
            ]
            json_dump(updated_translation, translation_file)


def test():
    web_ids = [
        "neural-networks",
        "gradient-descent",
        "backpropagation",
        "backpropagation-calculus",
        "gpt",
        "attention",
        "essence-of-calculus",
        "divergence-and-curl",
        "taylor-series",
        "eulers-number",
        "derivatives-and-transforms",
        "derivatives",
        "derivative-formulas-geometrically",
        "integration",
        "limits",
        "implicit-differentiation",
        "chain-rule-and-product-rule",
        "area-and-slope",
        "brachistochrone",
        "higher-order-derivatives",
        "vectors",
        "span",
        "linear-transformations",
        "eigenvalues",
        "determinant",
        "matrix-multiplication",
        "inverse-matrices",
        "eola-preview",
        "dot-products",
        "3d-transformations",
        "change-of-basis",
        "cross-products",
        "nonsquare-matrices",
        "abstract-vector-spaces",
        "cross-products-extended",
        "cramers-rule",
        "quick-eigen",
        "fourier-series",
        "differential-equations",
        "eulers-formula-dynamically",
        "matrix-exponents",
        "pdes",
        "heat-equation",
        "hardest-problem",
        "clacks",
        "clacks-solution",
        "clacks-via-light",
        "fourier-transforms",
        "clt",
        "convolutions2",
        "convolutions",
        "gaussian-integral",
        "gaussian-convolution",
        "hamming-codes",
        "hamming-codes-2",
        "moser-reboot",
        "borwein",
        "subsets-puzzle",
        "visual-proofs",
        "sphere-area",
        "basel-problem",
        "prime-spirals",
        "windmills",
        "barber-pole-1",
        "barber-pole-2",
        "prism",
        "refractive-index-questions",
        "zeta",
        "quaternions",
        "newtons-fractal",
        "holomorphic-dynamics",
        "shadows",
        "wordle",
        "groups-and-monsters",
        "bayes-theorem",
        "dandelin-spheres",
        "pythagorean-triples",
        "fractal-dimension",
        "exponential-and-epidemics",
        "feynmans-lost-lecture",
        "inscribed-rectangle-problem",
        "borsuk-ulam",
        "bitcoin",
        "256-bit-security",
        "higher-dimensions",
        "epidemic-simulations",
        "pdfs",
        "leibniz-formula",
        "eulers-formula-via-group-theory",
        "hilbert-curve",
        "uncertainty-principle",
        "light-quantum-mechanics",
        "chessboard-puzzle",
        "pi-was-628",
    ]


def compare_with_old_transcripts():
    from caption_ops.sentence_timings import find_closest_aligning_substrings
    from caption_ops.sentence_timings import get_sentence_timings
    from caption_ops.cli.sync_transcription_update import main as sync_transcript

    old_trans_dir = "/Users/grant/Downloads/old_transcripts"
    transcripts = get_all_files_with_ending("transcript.txt")

    # Old
    for trans in map(Path, transcripts):
        web_id = trans.parent.parent.stem
        old_trans = Path(old_trans_dir, web_id).with_suffix(".txt")
        if not os.path.exists(old_trans):
            print(f"Cannot find {old_trans}")
            continue
        sentences = trans.read_text().split("\n")
        old_text = old_trans.read_text().replace("\n", " ")
        old_sentences = find_closest_aligning_substrings(old_text, sentences, max_shift=300)
        old_sentences = list(map(str.strip, old_sentences))

        final_sentences = []
        threshold = 8
        for sent1, sent2 in zip(sentences, old_sentences):
            bigger = threshold < len(sent2) - len(sent1) < 200
            final_sentences.append(sent2 if bigger else sent1)

        trans.write_text("\n".join(final_sentences))


def upload_missing_captions():
    from caption_ops.helpers import get_video_id_to_web_id_map
    from caption_ops.helpers import extract_video_id
    from caption_ops.helpers import url_to_directory
    from caption_ops.upload import upload_caption
    from youtube_transcript_api import YouTubeTranscriptApi


    urls = get_all_video_urls()
    vid_to_wid = get_video_id_to_web_id_map()
    youtube_api = get_youtube_api()

    for url in urls:
        video_id = extract_video_id(url)
        wid = vid_to_wid[video_id]
        with temporary_message(f"Searching {wid}"):
            ts = YouTubeTranscriptApi.list_transcripts(video_id)
            if not "en" in [t.language_code for t in ts]:
                srt = Path(url_to_directory(url), "english", "captions.srt")
                upload_caption(youtube_api, video_id, srt)


def fix_hamming():
    from caption_ops.helpers import webids_to_directories
    from caption_ops.sentence_timings import get_sentences

    # old_folder = "/Users/grant/Downloads/old_transcripts"

    web_id = "hamming-codes-2"
    folder = Path(webids_to_directories([web_id])[0])

    words, starts, end = zip(*(json_load(Path(folder, "english", "word_timings.json"))))
    sents1 = get_sentences("".join(words))
    sents2 = Path(folder, "english", "transcript.txt").read_text().split("\n")
    # sents2 = get_sentences(Path(old_folder, f"{web_id}.txt").read_text())

    for trans_file in folder.rglob("sentence_translations.json"):
        trans = json_load(trans_file)
        if len(trans) == len(sents1):
            sents = sents1
        elif len(trans) == len(sents2):
            sents = sents2
        else:
            sents = []
            print(trans_file)
        for obj, sent in zip(trans, sents):
            obj['input'] = sent
        json_dump(trans, trans_file)


def search_for_mismatches():
    from caption_ops.upload import upload_caption
    from caption_ops.upload import get_youtube_api
    from caption_ops.helpers import get_all_video_urls
    from caption_ops.helpers import extract_video_id
    from caption_ops.helpers import url_to_directory
    from caption_ops.helpers import YouTube

    youtube_api = get_youtube_api()
    urls = get_all_video_urls()

    for url in urls[51:]:
        video_id = extract_video_id(url)
        webid = Path(url_to_directory(url)).stem
        if YouTube(url).author != "3Blue1Brown":
            continue
        print(f"Searching {webid}\n")
        mismatches = find_mismatched_captions(url)
        if mismatches:
            print(webid, [m.split("/")[-2] for m in mismatches])
            for path in mismatches:
                try:
                    upload_caption(youtube_api, video_id, path, replace=True)
                except Exception as e:
                    pass


def music_free_slots():
    from caption_ops.upload import *
    from caption_ops.helpers import *

    youtube_api = get_youtube_api()
    video_id = "Cz4Q4QOuoo8"  # Refractive index
    vid_to_wid = get_video_id_to_web_id_map()
    vid_to_dir = get_video_id_to_caption_directory_map()
    caption_file = Path(vid_to_dir[video_id], "english", "captions.srt")

    upload_caption(youtube_api, video_id, caption_file, name="(No music)", replace=False, language_code='en')
