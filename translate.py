import os
import re
import regex
import numpy as np
import itertools as it
import pycountry
from pathlib import Path
import json
import pysrt

from google.cloud import translate_v2 as translate
from google.oauth2 import service_account

from helpers import temporary_message
from helpers import webids_to_directories
from helpers import interpolate
from helpers import ensure_exists
from helpers import get_sentences
from helpers import json_load
from helpers import json_dump
from helpers import sub_rip_time_to_seconds
from helpers import write_srt
from helpers import SENTENCE_ENDINGS

from transcribe_video import get_sentence_timings_from_word_timings

SERVICE_ACCOUNT = ""
TARGET_LANGUAGES = [
    "Spanish",
    "Hindi",
    "Chinese",
    "French",
    "Russian",
    # "German",
    # "Arabic",
    # "Italian",
    # "Portuguese",
    # "Japanese",
    # "Korean",
    # "Ukrainian",
    # "Thai",
    # "Persian",
    # "Indonesian",
    # "Hebrew",
    # "Turkish",
    # "Hungarian",
    # "Vietnamese",
]


def translate_sentences(
    src_sentences,
    target_language_code,
    src_language_code="en",
    chunk_size=50,
    model=None,
):
    # Set up the translation client
    credentials = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT)
    translate_client = translate.Client(credentials=credentials)

    translations = []
    for n in range(0, len(src_sentences), chunk_size):
        translations.extend(translate_client.translate(
            src_sentences[n:n + chunk_size],
            target_language=target_language_code,
            source_language=src_language_code,
            model=model,
        ))
    return translations


def translate_title(video_url, language):
    pass


def get_sentence_translation_file(english_srt, target_language):
    result = Path(
        Path(english_srt).parent.parent,
        target_language.lower(),
        "sentence_translations.json"
    )
    ensure_exists(result.parent)
    return result


# TODO, move to some file devoted to timings
def get_sentence_timings_from_srt(srt_file, end_marks=SENTENCE_ENDINGS):
    subs = pysrt.open(srt_file)
    full_text = ""
    sent_delim_times = [sub_rip_time_to_seconds(subs[0].start)]
    for sub in subs:
        text = sub.text.replace("\n", " ").strip() + " "
        full_text += text

        start = sub_rip_time_to_seconds(sub.start)
        end = sub_rip_time_to_seconds(sub.end)
        end_mark_positions = [match.end() for match in re.finditer(end_marks, text)]
        if len(end_mark_positions) == 0:
            continue
        fractions = np.array(end_mark_positions) / len(text)
        for frac in fractions:
            sent_delim_times.append(interpolate(start, end, frac))

    sentences = [
        (sentence + mark).strip()
        for sentence, mark in zip(
            re.split(end_marks, full_text),
            re.findall(end_marks, full_text),
        )
    ]
    time_ranges = list(zip(sent_delim_times[:-1], sent_delim_times[1:]))
    return sentences, time_ranges


def write_srt_from_sentences_and_time_ranges(
    sentences,
    time_ranges,
    output_file_path,
    max_chars_per_segment=90,
):
    punc = r'(?<=[.!?,:;])\s+|\.$|(?<=[।۔՝։።။។፡。！？])'
    segments = []  # List of triplets (text, start_time, end_time)
    mcps = max_chars_per_segment
    for sentence, time_range in zip(sentences, time_ranges):
        start_time, end_time = time_range
        n_chars = len(sentence)
        if n_chars == 0:
            continue
        # Bias towards cuts which are on punctuation marks,
        # and try to keep the segments from being too uneven
        n_segments = int(np.ceil(n_chars / mcps))
        best_step = (n_chars // n_segments)
        half = mcps // 2
        cuts = [0]
        while cuts[-1] < n_chars:
            lh = cuts[-1]
            rh = lh + mcps
            best_cut = lh + best_step
            if rh >= n_chars:
                cuts.append(n_chars)
                continue
            # Try cutting at a nearby punctuation mark
            punc_indices = [
                lh + half + match.end()
                for match in regex.finditer(punc, sentence[lh + half:rh])
            ]
            if punc_indices:
                index = np.argmin([abs(pi - best_cut) for pi in punc_indices])
                cuts.append(punc_indices[index])
                continue
            # Otherwise, try a nearby space
            space_indices = [
                lh + half + match.end()
                for match in regex.finditer(" ", sentence[lh + half:rh])
            ]
            if space_indices:
                index = np.argmin([abs(si - best_cut) for si in space_indices])
                cuts.append(space_indices[index])
                continue
            # Otherwise, e.g. in character-based languages, just take what you can get
            else:
                cuts.append(best_cut)
        cuts.sort()
        for lh, rh in zip(cuts, cuts[1:]):
            segments.append((
                sentence[lh:rh],
                interpolate(start_time, end_time, lh / n_chars),
                interpolate(start_time, end_time, rh / n_chars),
            ))
    ## Write the srt
    write_srt(segments, output_file_path)


def generate_sentence_translations_with_timings(english_srt, target_language):
    # Get sentences and timings
    word_timing_file = Path(Path(english_srt).parent, "word_timings.json")
    if os.path.exists(word_timing_file):
        en_sentences, time_ranges = get_sentence_timings_from_word_timings(word_timing_file)
    else:
        en_sentences, time_ranges = get_sentence_timings_from_srt(english_srt)

    # Call the Google api to translate, and save to file
    sentence_translation_file = get_sentence_translation_file(english_srt, target_language)
    with temporary_message(f"Translating to {sentence_translation_file}"):
        trg_lang_code = pycountry.languages.get(name=target_language).alpha_2
        translations = translate_sentences(en_sentences, trg_lang_code)
    for obj, time_range in zip(translations, time_ranges):
        obj["time_range"] = time_range

    json_dump(translations, sentence_translation_file)

    return sentence_translation_file


def sentence_translations_to_srt(sentence_translation_file):
    translations = json_load(sentence_translation_file)
    directory = Path(sentence_translation_file).parent
    language = directory.stem

    # Use the time ranges and translated sentences to generate captions
    trans_sentences = [trans['translatedText'] for trans in translations]
    time_ranges = [trans['time_range'] for trans in translations]
    trans_srt = Path(directory, "auto_generated.srt")
    character_based = (language.lower() in ['chinese', 'japanese'])

    write_srt_from_sentences_and_time_ranges(
        sentences=trans_sentences,
        time_ranges=time_ranges,
        output_file_path=trans_srt,
        max_chars_per_segment=(30 if character_based else 90)
    )
    print(f"Successfully wrote {trans_srt}")
    return trans_srt


def translate_srt_file(english_srt, target_language):
    # If it hasn't been translated before, generated the translation
    trans_file = get_sentence_translation_file(english_srt, target_language)
    if not os.path.exists(trans_file):
        generate_sentence_translations_with_timings(english_srt, target_language)
    # Use the translation to wrie the new srt
    return sentence_translations_to_srt(trans_file)


def translate_to_multiple_languages(english_srt, languages, skip_community_generated=True):
    cap_dir = Path(english_srt).parent.parent
    for language in languages:
        lang_dir = ensure_exists(Path(cap_dir, language.lower()))
        if skip_community_generated and any(f.endswith("community.srt") for f in os.listdir(lang_dir)):
            continue
        try:
            translate_srt_file(english_srt, language)
        except Exception as e:
            print(f"Failed to translate {english_srt} to {language}\n{e}\n\n")


def translate_multiple_videos(web_ids, languages):
    for directory in webids_to_directories(web_ids):
        english_srt = Path(directory, "english", "captions.srt")
        translate_to_multiple_languages(english_srt, languages)
