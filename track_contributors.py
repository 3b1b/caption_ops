import subprocess
import re
import pandas
import csv
from functools import lru_cache

from pathlib import Path
from helpers import get_web_id_to_caption_directory_map
from helpers import CAPTIONS_DIRECTORY

LOCAL_REPO = CAPTIONS_DIRECTORY  # Should change

@lru_cache()
def manual_entries():
    file = Path(Path(__file__).parent, "data", "manually-added-contributors.csv")
    df = pandas.read_csv(file)
    result = dict()
    with open(file, newline='') as csvfile:
        rows = csv.reader(csvfile)
        for webid, language, name in rows:
            if webid not in result:
                result[webid] = dict()
            if language not in result[webid]:
                result[webid][language] = list()
            if name not in result[webid][language]:
                result[webid][language].append(name)
    return result


def get_contributor_names(folder):
    proc = subprocess.run(
        ["git", "-C", f"{LOCAL_REPO}", "log", folder],
        capture_output=True,
        check=True,
        shell=False
    )
    text = proc.stdout.decode("utf-8")
    contributors = set()
    for line in text.split("\n"):
        line = line.strip()
        # Find commit author
        for author in re.findall(r"^Author: (.+?) <", line):
            contributors.add(author)
        # Find website contributors
        for editor in re.findall(r"^Edit .+ by (.+?) \(", line):
            contributors.add(editor)
    contributors.difference_update({"Grant Sanderson"})
    return sorted(list(contributors))
        

def get_all_video_contributors(web_id):
    folder = Path(get_web_id_to_caption_directory_map()[web_id])
    lang_to_contributors = dict()
    trans_files = sorted(list(folder.rglob("sentence_translations.json")))
    for trans_file in trans_files:
        lang_folder = trans_file.parent
        contributors = get_contributor_names(lang_folder)
        if len(contributors) == 0:
            continue
        lang_to_contributors[lang_folder.stem] = contributors

    # Add manual entrie
    added_entries = manual_entries().get(web_id, dict())
    for lang in added_entries:
        if lang not in lang_to_contributors:
            lang_to_contributors[lang] = []
        lang_to_contributors[lang].extend(added_entries[lang])

    # Sort and clean
    for lang, names in lang_to_contributors.items():
        names = [n.replace("@", "") for n in names]
        clean_list = sorted(list(set(names)))
        lang_to_contributors[lang] = clean_list

    return lang_to_contributors
