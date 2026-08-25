# caption_ops

Transcribing, captioning and translating 3Blue1Brown videos.

## Setup

```sh
pip install -e .
```

That makes `caption_ops` importable from anywhere and puts the commands below
on your PATH, so nothing depends on the current directory. Api keys are read
from `/Users/grant/cs/api_keys`.

## Transcribing

```sh
caption-transcribe lesson.mp4              # -> captions.srt, 50 chars per caption
caption-transcribe lesson.mp4 -n 40        # a different maximum
caption-transcribe lesson.mp4 --raw        # skip the notation cleanup
caption-sentences captions.srt             # -> transcription_sentences.srt
```

`caption-transcribe` takes audio or video, and transcribes with the OpenAI
API, falling back on a local Whisper model if that fails. Long files are cut
into chunks at silences and sent off in parallel, since the API caps requests
at 1400 seconds. A cleanup pass then rewrites spelled out numbers and math as
notation, which is steered by `NOTATION_INSTRUCTIONS` in
`caption_ops/transcribe_video.py`.

`caption-sentences` groups those captions into one caption per sentence, which
is the form handed off to translators.

## Layout

```
caption_ops/          the library
  helpers.py          paths, api keys, text utilities
  transcribe_video.py transcription, chunking, notation cleanup
  srt_ops.py          reading and writing srts, splitting into captions
  sentence_timings.py lining sentences up with timings
  translate.py        translation, and gpt_translate.py
  download.py         pulling audio and captions off of youtube
  upload.py           pushing captions and metadata back up
  cli/                one module per command
scratch/              ad hoc scripts, run by hand rather than as commands
```

The other commands in `caption_ops/cli` have no console script of their own,
and are run with e.g. `python -m caption_ops.cli.auto_caption`.
