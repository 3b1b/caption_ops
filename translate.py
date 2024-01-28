import os
import pycountry
from pathlib import Path
from pytube import YouTube

from google.cloud import translate_v2 as translate
from google.oauth2 import service_account

from helpers import temporary_message
from helpers import webids_to_directories
from helpers import ensure_exists
from helpers import json_load
from helpers import json_dump
from helpers import url_to_directory

from srt_ops import write_srt_from_sentences_and_time_ranges

from sentence_timings import get_sentence_timings_from_srt
from sentence_timings import get_sentence_timings

SERVICE_ACCOUNT_PATH = ""
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


def get_google_translate_client(service_account_file=SERVICE_ACCOUNT_PATH):
    # Set up the translation client
    if not os.path.exists(service_account_file):
        raise Exception("No service account credentials for translating with the Google API")
    credentials = credentials = service_account.Credentials.from_service_account_file(service_account_file)
    return translate.Client(credentials=credentials)


def translate_sentences(
    src_sentences,
    target_language,
    src_language_code="en",
    chunk_size=50,
    model=None,
):
    translate_client = get_google_translate_client()
    translations = []
    target_language_code = pycountry.languages.get(name=target_language).alpha_2
    for n in range(0, len(src_sentences), chunk_size):
        translations.extend(translate_client.translate(
            src_sentences[n:n + chunk_size],
            target_language=target_language_code,
            source_language=src_language_code,
            model=model,
        ))
    return translations


def get_sentence_translation_file(english_srt, target_language):
    result = Path(
        Path(english_srt).parent.parent,
        target_language.lower(),
        "sentence_translations.json"
    )
    ensure_exists(result.parent)
    return result


def generate_sentence_translations_with_timings(english_srt, target_language):
    # Get sentences and timings
    word_timing_file = Path(Path(english_srt).parent, "word_timings.json")
    if os.path.exists(word_timing_file):
        en_sentences, time_ranges = get_sentence_timings(json_load(word_timing_file))
    else:
        en_sentences, time_ranges = get_sentence_timings_from_srt(english_srt)

    # Call the Google api to translate, and save to file
    sentence_translation_file = get_sentence_translation_file(english_srt, target_language)
    with temporary_message(f"Translating to {sentence_translation_file}"):
        translations = translate_sentences(en_sentences, target_language)
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


def translate_video_title(video_url, language, overwrite=False):
    file = Path(url_to_directory(video_url), language.lower(), "title.json")
    if os.path.exists(file) and not overwrite:
        return
    title = YouTube(video_url).title
    with temporary_message(f"Translating to {language}"):
        trans = translate_sentences([title], language)[0]
    ensure_exists(file.parent)
    json_dump(trans, file)


def translate_title_to_multiple_languages(video_url, languages):
    for language in languages:
        translate_video_title(video_url, language)
