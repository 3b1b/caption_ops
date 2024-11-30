import os
import openai
from pathlib import Path
from tqdm.auto import tqdm as ProgressDisplay

from helpers import json_load
from helpers import json_dump
from helpers import ensure_exists
from helpers import temporary_message

from translate import translate_sentences


def gpt4_translate(sentences, language, formality="informal", n_context_sentences=2):
    openai.api_key = os.getenv('OPENAI_KEY')
    sys_message = {
        "role": "system",
        "content": f"Translate the user's sentences to {language}. Use {formality} second person. The translation should sound natural spoken in a narrated educational video."
    }

    translations = []
    message_history = []
    for sentence in ProgressDisplay(sentences):
        low_index = max(0, len(message_history) - 2 * n_context_sentences)
        new_message = {"role": "user", "content": sentence}
        messages = [sys_message, *message_history[low_index:], new_message]
        message_history.append(new_message)

        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=messages,
            # This is capping it at vaguely 2x the tokens of the input
            max_tokens=len(sentence),
            # Low temperature to minimize variability in translation
            temperature=0.3
        )

        # Extract the translations from the response
        try:
            new_translation = response['choices'][0]['message']['content']
        except Exception as e:
            # Error handling for each sentence?
            new_translation = "Translation Error"
        translations.append(new_translation)
        message_history.append({"role": "assistant", "content": new_translation})

    return translations


def gpt4_abbreviate(sentence, language, proportion):
    openai.api_key = os.getenv('OPENAI_KEY')

    percent = round(proportion, 1) * 100
    prompt = f"""
    Make this {language} sentence about {percent}% as long, maintaining the same meaning and intent.

    {sentence}
    """

    try:
        response = openai.ChatCompletion.create(
            model="gpt-4o",
            messages=[
                {"role": "system", "content": "You are a helpful assistant that abbreviates sentences in foreign languages, without losing meaning"},
                {"role": "user", "content": prompt}
            ],
            # Low temperature to minimize variability in translation
            temperature=0.0
        )

        # Extract and return the abbreviated sentence
        return response.choices[0].message['content'].strip()

    except Exception as e:
        print(f"An error occurred: {e}")
        return None


def test_abbreviation():
    folder = "/Users/grant/cs/captions/2024/shorts/mandelbrot/"
    language = "french"
    trans = json_load(Path(folder, language.lower(), "sentence_translations.json"))

    sentence = trans[0]['translatedText']
    new_sent = gpt4_abbreviate(sentence, language, 0.9)


def create_survey_sample(subfolder, language):
    language = language.lower()
    transcript_file = f"/Users/grant/cs/captions/{subfolder}/english/sentence_timings.json"
    sents, starts, ends = zip(*json_load(transcript_file))
    with temporary_message(f"DeepL to {language}"):
        deepl_translation_full = translate_sentences(sents, language)
        deepl_translation = [obj['translatedText'] for obj in deepl_translation_full]
    with temporary_message(f"GPT-4o to {language}"):
        gpt4o_translation = gpt4_translate(sents, language)

    sample = []
    for en, opt1, opt2 in zip(sents, deepl_translation, gpt4o_translation):
        # Option 1 is DeepL
        # Option 2 is GPT4-o
        sample.append(dict(
            original=en,
            translation_1=opt1,
            translation_2=opt2,
        ))

    output_folder = "/Users/grant/3Blue1Brown Dropbox/3Blue1Brown/translation_experiments/mandelbrot"
    output_file = Path(output_folder, language).with_suffix(".json")
    json_dump(sample, output_file)


def test():
    subfolder = "2024/shorts/mandelbrot"
    languages = [
        "Albanian",
        "Arabic",
        "Bengali",
        "Bulgarian",
        "Catalan",
        "Chinese",
        "Croatian",
        "Czech",
        "Danish",
        "Dutch",
        "Estonian",
        "Finnish",
        # "French",
        "Georgian",
        "German",
        "Greek",
        "Gujarati",
        "Hebrew",
        "Hindi",
        "Hungarian",
        "Indonesian",
        "Italian",
        "Japanese",
        "Korean",
        "Lithuanian",
        "Marathi",
        "Norwegian",
        "Persian",
        "Polish",
        "Portuguese",
        "Romanian",
        "Russian",
        "Serbian",
        "Slovak",
        "Slovenian",
        "Spanish",
        "Swedish",
        "Tagalog",
        "Tamil",
        "Telugu",
        "Thai",
        "Turkish",
        "Ukrainian",
        "Urdu",
        "Vietnamese",
    ]

    for language in languages:
        create_survey_sample(subfolder, language)
