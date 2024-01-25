import os
import re
import numpy as np
import itertools as it
import pycountry
from pathlib import Path
import json

from google.cloud import translate_v2 as translate
from google.oauth2 import service_account

from helpers import unformat_time
from helpers import temporary_message
from helpers import webids_to_directories

SERVICE_ACCOUNT = "/Users/grant/cs/api_keys/translations-412015-42f5073bb160.json"
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


def get_raw_translation_file(english_srt, target_language):
    result = Path(
        Path(english_srt).parent,
        "raw_translations",
        f"{target_language.lower()}.json"
    )
    if not os.path.exists(result.parent):
        os.makedirs(result.parent)
    return result


def get_sentence_time_ranges(srt_lines, end_positions):
    srt_segment_boundaries = [
        list(map(unformat_time, time_line.split(" --> ")))[:2]
        for time_line in srt_lines[1::4]
    ]

    def position_to_time(pos):
        if int(pos) >= len(srt_segment_boundaries):
            left, right = srt_segment_boundaries[-1]
        else:
            left, right = srt_segment_boundaries[int(pos)]
        return interpolate(left, right, pos % 1)

    return [
        tuple(map(position_to_time, [start, end]))
        for start, end in zip(end_positions[:-1], end_positions[1:])
    ]


def extract_sentences_with_end_positions(srt_lines, end_marks=r'[.!?。]'):
    """
    Extracts the text from the srt file, and breaks it into sentences.
    Keep track of where the ends of those sentences fall reletive to segments
    in the srt lines, where each srt segment represents one unit
    """
    full_text = ""
    end_positions = [0.0]

    for n, line in enumerate(srt_lines[2::4]):
        line = line.strip()
        full_text += line + " "

        # Record positions of sentence endings, where each
        # srt segment is considered 1 unit
        sentence_pieces = re.split(end_marks, line)
        if len(sentence_pieces) == 1:
            continue
        piece_lengths = np.array([len(piece) for piece in sentence_pieces])
        if piece_lengths.sum() > 0:
            props = piece_lengths / piece_lengths.sum()
        else:
            props = np.zeros_like(piece_lengths)
        for fractional_part in np.cumsum(props[:-1]):
            end_positions.append(n + fractional_part)

    sentences = [
        sentence.strip() + mark
        for sentence, mark in zip(
            re.split(end_marks, full_text),
            re.findall(end_marks, full_text),
        )
    ]
    return sentences, end_positions


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


def srt_segments_from_setences_and_end_positions(sentences, end_positions, character_based=False):
    srt_segments = [""] * int(np.ceil(max(end_positions)))
    for sentence, start, end in zip(sentences, end_positions[:-1], end_positions[1:]):
        words = list(sentence) if character_based else sentence.split(" ")
        for word, value in zip(words, np.linspace(start, end, len(words) + 1)):
            srt_segments[int(value)] += word
            if not character_based:
                srt_segments[int(value)] += " "
    return srt_segments


def write_srt_from_sentences_and_time_ranges(
    sentences,
    time_ranges,
    output_file_name,
    max_chars_per_segment=90,
):
    punc = r'[\p{P}]'
    segments = []  # List of triplets (text, start_time, end_time)
    mcps = max_chars_per_segment
    for sentence, time_range in zip(sentences, time_ranges):
        start_time, end_time = time_range
        n_chars = len(sentence)
        if n_chars == 0:
            continue
        ## Back to the older tactic
        n_segments = int(np.ceil(n_chars / mcps))
        best_step = (n_chars // n_segments)
        half = mcps // 2
        cuts = [0]
        while cuts[-1] < n_chars:
            lh = cuts[-1]
            rh = lh + mcps
            if rh >= n_chars:
                cuts.append(n_chars)
                continue
            punc_indices = [
                lh + half + match.end()
                for match in regex.finditer(punc, sentence[lh + half:rh])
            ]
            if punc_indices:
                index = np.argmin([abs(pi - (lh + best_step)) for pi in punc_indices])
                cuts.append(punc_indices[index])
                continue
            space_indices = [
                lh + half + match.end()
                for match in regex.finditer(" ", sentence[lh + half:rh])
            ]
            if space_indices:
                index = np.argmin([abs(si - (lh + best_step)) for si in space_indices])
                cuts.append(space_indices[index])
                continue
            else:
                cuts.append(lh + best_step)
        for lh, rh in zip(cuts, cuts[1:]):
            segments.append((
                sentence[lh:rh],
                interpolate(start_time, end_time, lh / n_chars),
                interpolate(start_time, end_time, rh / n_chars),
            ))
    ## Write the srt
    with open(output_file_name, 'w', encoding='utf-8') as srt_file:
        for index, segment in enumerate(segments):
            caption_text, start_time, end_time = segment
            srt_format = "\n".join([
                str(index + 1),
                format_time(start_time) + " --> " + format_time(end_time),
                caption_text.strip() + "\n\n",
            ])
            srt_file.write(srt_format)
    return srt_file


def get_sentence_translations_with_timings(english_srt, target_language, overwrite=False):
    # Pull out english sentences
    with open(english_srt, "r") as file:
        srt_lines = list(file.readlines())
    english_sentences, end_positions = extract_sentences_with_end_positions(srt_lines)

    raw_translation_file = get_raw_translation_file(english_srt, target_language)
    if os.path.exists(raw_translation_file) and not overwrite:
        # Check if it's been done before, and read in
        with open(raw_translation_file, 'r', encoding='utf-8') as fp:
            translations = json.load(fp)
        return translations

    # Otherwise, call the Google api to translate, and save to file
    with temporary_message(f"Translating to {raw_translation_file}"):
        trg_lang_code = pycountry.languages.get(name=target_language).alpha_2
        translations = translate_sentences(english_sentences, trg_lang_code)
    time_ranges = get_sentence_time_ranges(srt_lines, end_positions)
    for obj, time_range in zip(translations, time_ranges):
        obj["time_range"] = time_range
    with open(raw_translation_file, 'w') as fp:
        json.dump(translations, fp, indent=1, ensure_ascii=False)

    return translations


def translate_srt_file(english_srt, target_language):
    translations = get_sentence_translations_with_timings(english_srt, target_language)
    # Use the time ranges and translated sentences to generate captions
    trans_sentences = [trans['translatedText'] for trans in translations]
    time_ranges = [trans['time_range'] for trans in translations]
    trans_file_name = Path(
        Path(english_srt).parent,
        target_language.lower() + "_ai.srt"
    )
    character_based = (target_language.lower() in ['chinese', 'japanese'])
    write_srt_from_sentences_and_time_ranges(
        sentences=trans_sentences,
        time_ranges=time_ranges,
        output_file_name=trans_file_name,
        max_chars_per_segment=(30 if character_based else 90)
    )
    print(f"Successfully wrote {trans_file_name}")
    return trans_file_name


def translate_to_multiple_languages(english_srt, languages):
    files = os.listdir(Path(english_srt).parent)
    for language in languages:
        if any([file.startswith(language.lower()) for file in files]):
            continue
        try:
            translate_srt_file(english_srt, language)
        except Exception as e:
            print(f"Failed to translate {english_srt} to {language}\n{e}\n\n")


def translate_multiple_videos(web_ids, languages):
    for directory in webids_to_directories(web_ids):
        english_srt = Path(directory, "english.srt")
        translate_to_multiple_languages(english_srt, languages)


def run_all_translations():
    web_ids = [
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
        "neural-networks",
        "gradient-descent",
        "backpropagation",
        "backpropagation-calculus",
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
        "convolutions",
        "hamming-codes",
        "hamming-codes-2",
        "sphere-area",
        "basel-problem",
        "prime-spirals",
        "windmills",
        "prism",
        "refractive-index-questions",
        "zeta",
        "quaternions",
        "newtons-fractal",
        "shadows",
        "wordle",
        "groups-and-monsters",
        "bayes-theorem",
        "dandelin-spheres",
        "pythagorean-triples",
        "barber-pole-1",
        "barber-pole-2",
        "fractal-dimension",
        "exponential-and-epidemics",
        "borwein",
        "subsets-puzzle",
        "visual-proofs",
        "feynmans-lost-lecture",
        "inscribed-rectangle-problem",
        "moser-reboot",
        "convolutions2",
        "bitcoin",
        "256-bit-security",
        "three-utilities",
        "higher-dimensions",
        "epidemic-simulations",
        "pdfs",
        "leibniz-formula",
        "eulers-formula-via-group-theory",
        "hilbert-curve",
        "binomial-distributions",
        "inventing-math",
        "hilbert-curve",
        "uncertainty-principle",
        "light-quantum-mechanics",
        "chessboard-puzzle",
        "pi-was-628",
        "ldm-trigonometry",
        "ldm-complex-numbers",
        "ldm-natural-logs",
        "gaussian-integral",
        "ldm-quadratic",
        "ldm-tips-to-problem-solving",
        "ldm-eulers-formula",
        "lockdown-math-announcement",
        "ldm-logarithms",
        "ldm-power-towers",
        "ldm-i-to-i",
        "music-and-measure-theory",
        "holomorphic-dynamics",
        "quaternions-and-3d-rotation",
        "better-bayes",
        "winding-numbers",
        "borsuk-ulam",
        "wallis-product",
        "triangle-of-power",
        "tattoos-on-math",
        "ldm-imaginary-interest",
        "turbulence",
        "hanoi-and-sierpinski",
        "gaussian-convolution",
        "eulers-characteristic-formula",
        "bayes-theorem-quick",
    ]
    languages = TARGET_LANGUAGES


def simple_translation_example():
    # Load credentials from the service account file
    text = """
        In the last video, you and I looked at this demo here, where we shine linearly polarized light through a tube full of sugar water, and we saw how it rather mysteriously results in these colored diagonal stripes. There, I walked through the general outline for an explanation, keeping track of what questions still need to be answered. Namely, why does sugar water twist the polarization direction of light? Why does that twisting rate depend on the color of the light? And why, even if you understand that this twist is happening, would you see any evidence of it when viewing the tube from the side, with no additional polarizing filters? Here, I'd like to begin with the very fundamental idea of what light is, and show how the answer to these questions can emerge from an extremely minimal set of assumptions. In some sense, the fundamental question of electricity and magnetism is how the position and motion of one charged particle influences that of another. For example, one of the first things you learn, say in a high school physics class, is that charges with the same sign tend to repel each other.
    """.strip().split(".")

    target = 'zh'  # Chinese

    credentials = service_account.Credentials.from_service_account_file(SERVICE_ACCOUNT)
    translate_client = translate.Client(credentials=credentials)
    output = translate_client.translate(
        text,
        target_language=target,
        source_language="en",
    )

    print(output['translatedText'])

    # Test the above function
    english_srt = "/Users/grant/cs/captions/2023/barber-pole-1/english.srt"
    target_language = "spanish"
    translate_srt_file(english_srt, target_language)
