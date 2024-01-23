from helpers import *
from download import *
from reorganize import *
from transcribe_video import *
from translate import *
from upload import *



# Play!

srts = []
for root, dirs, files in os.walk(CAPTIONS_DIRECTORY):
    for file in files:
        if file.endswith(".srt")
            srts.append(os.path.join(root, file))

