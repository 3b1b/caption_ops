import subprocess
import re
from pathlib import Path
from helpers import get_web_id_to_caption_directory_map

LOCAL_REPO = "/Users/grant/cs/captions/"  # Should change

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
        for editor in re.findall(r"^Edit .+ by (.+?) \(", line):
        # Find website contributors
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
    return lang_to_contributors
