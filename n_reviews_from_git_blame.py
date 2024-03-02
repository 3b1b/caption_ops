import requests
import re
import os
import subprocess
from subprocess import check_output
from pathlib import Path
from collections import OrderedDict

from helpers import json_load
from helpers import json_dump
from helpers import get_all_files_with_ending

# Constants
GITHUB_API_URL = "https://api.github.com"
OWNER = "3b1b"
REPO = "captions"
LOCAL_REPO = "/Users/grant/cs/captions/"  # Should change
BRANCH_NAME = "track-reviewers"


# Get the commit history for the file
def get_commit_history(path):
    path = str(path).replace(LOCAL_REPO, "")
    commits_url = f"{GITHUB_API_URL}/repos/{OWNER}/{REPO}/commits?path={path}"
    commits = requests.get(commits_url).json()
    return [commit['sha'] for commit in commits]


def get_local_commit_history(file_path):
    # Prepare the git log command
    command = ['git', '-C', f'{LOCAL_REPO}', 'log', '--pretty=format:%H', '--', file_path]
    
    # Execute the command
    result = subprocess.run(command, stdout=subprocess.PIPE, text=True)
    
    # Split the output by new lines to get a list of commit hashes
    commit_hashes = result.stdout.strip().split('\n')
    
    return commit_hashes


# Checkout each commit and use git blame to get the contributor for each line
def get_contributors_to_translated_lines(path):
    commit_shas = get_local_commit_history(path)
    sent_to_contributors = OrderedDict()
    trans_str = "\"translatedText\": "
    input_str = "\"input\": "

    for sha in reversed(commit_shas):
        # Checkout to specific commit
        try:
            check_output(f"git -C {LOCAL_REPO} checkout {sha}", shell=True)
        except:
            continue
        # Get blame for the specific file at this commit
        blame_output = check_output(f"git -C {LOCAL_REPO} blame {path}", shell=True).decode('utf-8')
        blame_lines = blame_output.split("\n")
        for line in blame_lines:
            if trans_str not in line:
                continue
            sent = line[line.index(trans_str) + len(trans_str) + 1:-2]
            if sent not in sent_to_contributors:
                sent_to_contributors[sent] = list()
            line_contributors = sent_to_contributors[sent]

            contributor = extract_contributor(line)
            if contributor == "Grant Sanderson":
                # These are contributions from automated scripts
                continue
            if contributor not in line_contributors:
                line_contributors.append(contributor)

    check_output(f"git -C {LOCAL_REPO} checkout {BRANCH_NAME}", shell=True)
    return sent_to_contributors


# Helper functions to parse the output of git blame
def extract_line_number(blame_line):
    # Extract line number from the blame line
    words = blame_line.strip().split(" ")
    words = list(filter(lambda w: w, words))
    is_date = [bool(re.findall(r'^\d{4}-\d{2}-\d{2}$', word)) for word in words]
    number = words[is_date.index(True) + 3].replace(")", "")
    return int(number)


def extract_contributor(blame_line):
    # Extract contributor from the blame line
    words = blame_line.strip().split(" ")
    words = list(filter(lambda w: w, words))
    is_date = [bool(re.findall(r'^\d{4}-\d{2}-\d{2}$', word)) for word in words]
    upper = is_date.index(True) if any(is_date) else 4
    name = " ".join(words[2:upper])
    name = name.replace("(", "")
    return name


def update_translation_file(path):
    # Check out new branc, sync with main
    check_output(f"git -C {LOCAL_REPO} checkout {BRANCH_NAME}", shell=True)
    check_output(f"git -C {LOCAL_REPO} pull origin main", shell=True)

    # Assemble lists of reviewers on each line
    n_rev_key = "n_reviews"
    sent_to_contributors = get_contributors_to_translated_lines(path)

    # Update the sentence translation files
    trans = json_load(path)
    all_objs = trans if isinstance(trans, list) else [trans]
    for obj in all_objs:
        sent = obj['translatedText']
        if sent_to_contributors.get(sent, []):
            obj[n_rev_key] = 1
        else:
            obj[n_rev_key] = 0

    json_dump(trans, path)

    # Commit change
    parts_name = ", ".join(path.split(os.sep)[-3:])
    check_output(f"git -C {LOCAL_REPO} add .", shell=True)
    check_output(
        f"git -C {LOCAL_REPO} commit -m \"Updated contributor numbers to {parts_name}\"",
        shell=True
    )


def initialize():
    # Write in zeros
    sent_paths = get_all_files_with_ending("sentence_translations.json")
    title_paths = get_all_files_with_ending("title.json")
    desc_paths = get_all_files_with_ending("description.json")
    for path in [*sent_paths, *desc_paths]:
        try:
            trans = json_load(path)
            for obj in trans:
                obj["n_reviews"] = 0
            json_dump(trans, path)
        except Exception as e:
            print(f"Failed on {path}\n{e}\n\n")

    for path in title_paths:
        try:
            obj = json_load(path)
            obj["n_reviews"] = 0
            json_dump(obj, path)
        except Exception as e:
            print(f"Failed on {path}\n{e}\n\n")


# Main function
def main():
    # Add based on git blame data
    suffixes = []

    for suffix in suffixes:
        path = os.path.join(LOCAL_REPO, suffix)
        try:
            update_translation_file(str(path))
        except Exception as e:
            print(f"Failed on {path}\n{e}\n\n")
            continue
        print(f"\n\n Success on {path} \n\n")
