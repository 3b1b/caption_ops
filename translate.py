import os
from pathlib import Path

from google.cloud import translate_v2 as translate
from google.oauth2 import service_account

from helpers import temporary_message
from helpers import webids_to_directories
from helpers import ensure_exists
from helpers import extract_video_id
from helpers import get_language_code
from helpers import json_load
from helpers import json_dump
from helpers import url_to_directory

from download import download_video_title_and_description

from srt_ops import write_srt_from_sentences_and_time_ranges

from sentence_timings import get_sentences_with_timings

SERVICE_ACCOUNT_ENV_VARIABLE_NAME = 'GOOGLE_TRANSLATION_SERVICE_ACCOUNT'
TARGET_LANGUAGES = [
    "Spanish",
    "Hindi",
    "Chinese",
    "French",
    "Russian",
    "German",
    "Arabic",
    "Italian",
    "Portuguese",
    "Japanese",
    "Korean",
    "Ukrainian",
    "Thai",
    "Persian",
    "Indonesian",
    "Hebrew",
    "Turkish",
    "Hungarian",
    "Vietnamese",
]


def get_google_translate_client(service_account_file=None):
    if service_account_file is None:
        service_account_file = os.getenv(SERVICE_ACCOUNT_ENV_VARIABLE_NAME)
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
    target_language_code = get_language_code(target_language)
    for n in range(0, len(src_sentences), chunk_size):
        translations.extend(translate_client.translate(
            src_sentences[n:n + chunk_size],
            target_language=target_language_code,
            source_language=src_language_code,
            model=model,
        ))
    return translations


def get_sentence_translation_file(word_timing_file, target_language):
    result = Path(
        Path(word_timing_file).parent.parent,
        target_language.lower(),
        "sentence_translations.json"
    )
    ensure_exists(result.parent)
    return result


def generate_sentence_translations_with_timings(word_timing_file, target_language):
    # Get sentences and timings
    if not os.path.exists(word_timing_file):
        raise Exception(f"No file {word_timing_file}")
    en_sentences, time_ranges = get_sentences_with_timings(json_load(word_timing_file))

    # Call the Google api to translate, and save to file
    sentence_translation_file = get_sentence_translation_file(word_timing_file, target_language)
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
    character_based = (language.lower() in ['chinese', 'japanese', 'korean'])

    write_srt_from_sentences_and_time_ranges(
        sentences=trans_sentences,
        time_ranges=time_ranges,
        output_file_path=trans_srt,
        max_chars_per_segment=(30 if character_based else 90),
    )
    print(f"Successfully wrote {trans_srt}")
    return trans_srt


def write_translated_srt(word_timing_file, target_language):
    # If it hasn't been translated before, generated the translation
    trans_file = get_sentence_translation_file(word_timing_file, target_language)
    if not os.path.exists(trans_file):
        generate_sentence_translations_with_timings(word_timing_file, target_language)
    # Use the translation to wrie the new srt
    return sentence_translations_to_srt(trans_file)


def translate_to_multiple_languages(word_timing_file, languages, skip_community_generated=True):
    cap_dir = Path(word_timing_file).parent.parent
    for language in languages:
        lang_dir = ensure_exists(Path(cap_dir, language.lower()))
        if skip_community_generated and any(f.endswith("community.srt") for f in os.listdir(lang_dir)):
            continue
        try:
            write_translated_srt(word_timing_file, language)
        except Exception as e:
            print(f"Failed to translate {cap_dir.stem} to {language}\n{e}\n\n")


def translate_multiple_videos(web_ids, languages):
    for directory in webids_to_directories(web_ids):
        english_srt = Path(directory, "english", "captions.srt")
        translate_to_multiple_languages(english_srt, languages)


def translate_video_details(youtube_api, video_url, language, overwrite=False):
    vid = extract_video_id(video_url)
    title, desc = download_video_title_and_description(youtube_api, vid)
    # Remove footer
    if "---" in desc:
        desc = desc[:desc.index("---")]

    # Where to write them
    cap_dir = url_to_directory(video_url)
    lag_dir = ensure_exists(Path(cap_dir, language.lower()))
    title_file = Path(lag_dir, "title.json")
    desc_file = Path(lag_dir, "description.json")

    # Translate title
    if not os.path.exists(title_file) or overwrite:
        with temporary_message(f"Translating title to {language}"):
            trans = translate_sentences([title], language)[0]
        json_dump(trans, title_file)

    # Translate description
    if not os.path.exists(desc_file) or overwrite:
        with temporary_message(f"Translating description to {language}"):
            trans = translate_sentences(desc.split("\n"), language)
        json_dump(trans, desc_file)


def translate_video_details_multiple_languages(youtube_api, video_url, languages):
    for language in languages:
        translate_video_details(youtube_api, video_url, language)
