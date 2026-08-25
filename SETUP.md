# Setting this up on another machine

Cloning the repo and installing it is the whole story. The commands below have
been run on a fresh virtualenv, so they should work as written.

## 1. Install

```sh
git clone https://github.com/3b1b/caption_ops.git
cd caption_ops
python3 -m venv venv          # or conda, or nothing, whichever you prefer
source venv/bin/activate
pip install -e .
```

Python 3.10 or newer. The `-e` matters less than the fact that it is installed
at all: it puts `caption-transcribe` and `caption-sentences` on your PATH and
makes `caption_ops` importable from any directory, so nothing depends on where
you cloned it.

You also need **ffmpeg**, which is not a pip package:

```sh
brew install ffmpeg            # macOS
sudo apt install ffmpeg        # Debian / Ubuntu
```

`ffmpeg` and `ffprobe` are found on your PATH, or in `/opt/homebrew/bin`,
`/usr/local/bin`, or `/usr/bin`.

## 2. Set your API keys

Grant's machine keeps keys as files in `~/cs/api_keys`; everywhere else they
come from environment variables. Put whichever of these you need in your
`.zshrc` / `.bashrc`:

```sh
export OPENAI_API_KEY="sk-..."                       # transcription, gpt translation
export DEEPL_KEY_FILE="$HOME/keys/deepl_key.txt"     # deepl translation (a file path)
export YOUTUBE_UPLOADING_KEY="$HOME/keys/caption_uploading.json"        # uploading
export YOUTUBE_CREDENTIALS_FILE="$HOME/keys/youtube_credentials.json"   # where the oauth token gets cached
```

Note that all but the first point at *file paths*, not at the secrets
themselves. `YOUTUBE_CREDENTIALS_FILE` is where the OAuth token gets written
after the first browser consent, so it need not exist yet.

Only `OPENAI_API_KEY` is needed for transcription, which is most of what people
want. The rest are for translating and for pushing captions back to YouTube,
and the YouTube ones require being an owner of the channel.

Check the install with:

```sh
caption-transcribe --help
```

## 3. What you can actually run

**Transcription works standalone.** Point it at any audio or video file
anywhere on disk:

```sh
caption-transcribe lesson.mp4              # -> captions.srt next to the input
caption-transcribe lesson.mp4 -n 40        # at most 40 chars per caption
caption-transcribe lesson.mp4 --raw        # skip the math-notation cleanup
caption-sentences captions.srt             # -> one caption per sentence
```

Long files get cut at silences and sent off in parallel, since the OpenAI API
caps a request at 1400 seconds. If the API call fails it falls back on a local
Whisper model, which downloads model weights the first time and is slow but
needs no key. `caption-transcribe -h` lists the rest.

One other standalone command, run as a module since it has no console script
of its own, shifting every timestamp back by some number of seconds:

```sh
python -m caption_ops.cli.retime_srt captions.srt shifted.srt 1.5
```

**Everything else assumes the 3b1b caption archive.** `auto_caption`,
`sync_captions`, `sync_all_captions`, `sync_transcription_update`,
`upload_all_new_languages` and friends all look up videos by walking
`CAPTIONS_DIRECTORY`, hard-coded at the top of `caption_ops/helpers.py` to
`/Users/grant/cs/captions`. To use them, clone the archive:

```sh
git clone https://github.com/3b1b/captions.git
```

and edit `CAPTIONS_DIRECTORY` in `helpers.py` to wherever you put it. Same for
`AUDIO_DIRECTORY`, which points into Grant's Dropbox and is not shared. Uploads
additionally need channel credentials, so in practice those commands are Grant's
to run.

The `scratch/` directory is ad hoc scripts with absolute paths baked in. Read
before running.

## Summary

If the goal is "transcribe and clean up captions for a video," clone this repo,
`pip install -e .`, install ffmpeg, set `OPENAI_API_KEY`, and you are done. If
the goal is "operate the 3blue1brown caption pipeline," you also need the
captions repo and the channel credentials.
