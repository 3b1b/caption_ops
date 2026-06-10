from helpers import get_video_id_to_web_id_map
from helpers import get_all_video_urls
from helpers import url_to_directory
from helpers import extract_video_id
from helpers import get_video_id_to_caption_directory_map
from helpers import CAPTIONS_DIRECTORY

import pyperclip

from pathlib import Path


URLS = [
    "https://youtu.be/zLzLxVeqdQg",
    "https://youtu.be/F_0yfvm0UoU",
    "https://youtu.be/84hEmGHw3J8",
    "https://youtu.be/K8P8uFahAgc",
    "https://youtu.be/-9OUyo8NFZg",
    "https://youtu.be/XFDM1ip5HdU",
    "https://youtu.be/1SMmc9gQmHQ",
    "https://youtu.be/cyW5z-M2yzw",
    "https://youtu.be/RU0wScIj36o",
    "https://youtu.be/Iq1a_KJTWJ8",
    "https://youtu.be/Cld0p3a43fU",
    "https://youtu.be/sULa9Lc4pck",
    "https://youtu.be/kjBOesZCoqc",
    "https://youtu.be/k7RM-ot2NWY",
    "https://youtu.be/fNk_zzaMoSs",
    "https://youtu.be/kYB8IZa5AuE",
    "https://youtu.be/XkY2DOUCWMU",
    "https://youtu.be/rHLEWRxRGiM",
    "https://youtu.be/Ip3X9LOh2dk",
    "https://youtu.be/uQhTuRlWMxw",
    "https://youtu.be/v8VSDg_WQlA",
    "https://youtu.be/LyGKycYT2v0",
    "https://youtu.be/BaM7OCEm3G0",
    "https://youtu.be/eu6i7WJeinw",
    "https://youtu.be/P2LTAUO1TdA",
    "https://youtu.be/PFDu9oVAE-g",
    "https://youtu.be/TgKwz5Ikpc8",
    "https://youtu.be/AmgkSdhK4K8",
    "https://youtu.be/bdMfjfT0lKk",
    "https://youtu.be/2SUvWfNJSsM",
    "https://youtu.be/sD0NjbwqlYw",
    "https://youtu.be/IxNb1WG_Ido",
    "https://youtu.be/gB9n2gHsHN4",
    "https://youtu.be/FhSFkLhDANA",
    "https://youtu.be/mvmuCPvRoWQ",
    "https://youtu.be/WUvTyaaNkzM",
    "https://youtu.be/9vKqVkMQHKk",
    "https://youtu.be/S0_qX4VJhMQ",
    "https://youtu.be/YG15m2VwSjA",
    "https://youtu.be/m2MIpDrF7Es",
    "https://youtu.be/qb40J4N1fa4",
    "https://youtu.be/kfF40MiS7zA",
    "https://youtu.be/rfG8ce4nNh0",
    "https://youtu.be/FnJqaIESC2s",
    "https://youtu.be/BLkz5LGWihw",
    "https://youtu.be/3d6DsjIBzJ4",
    "https://youtu.be/NaL_Cb42WyY",
    "https://youtu.be/QJYmyhnaaek",
    "https://youtu.be/bBC-nXj3Ng4",
    "https://youtu.be/S9JGmA5_unY",
    "https://youtu.be/3s7h2MHQtxc",
    "https://youtu.be/zwAD6dRSVyI",
    "https://youtu.be/MzRCDLre1b4",
    "https://youtu.be/aircAruvnKk",
    "https://youtu.be/IHZwWFHWa-w",
    "https://youtu.be/tIeHLnjs5U8",
    "https://youtu.be/Ilg3gGewQ5U",
    "https://youtu.be/OkmNXy7er84",
    "https://youtu.be/VvCytJvd4H0",
    "https://youtu.be/spUNpyF58BY",
    "https://youtu.be/MBnnXbOM5S4",
    "https://youtu.be/d-o3eB9sfls",
    "https://youtu.be/bcPTiiiYDs8",
    "https://youtu.be/b7FxPsqfkOY",
    "https://youtu.be/8GPy_UMV-08",
    "https://youtu.be/CfW845LNObM",
    "https://youtu.be/rB83DpBJQsE",
    "https://youtu.be/xdIjYBtnvZU",
    "https://youtu.be/pQa_tWZmlGs",
    "https://youtu.be/Qe6o9j4IjTo",
    "https://youtu.be/d4EgbgTm0Bg",
    "https://youtu.be/zjMuIxRvygQ",
    "https://youtu.be/_UoTTq651dE",
    "https://youtu.be/yuVqxCSsE7c",
    "https://youtu.be/GNcFjFmqEc8",
    "https://youtu.be/HEfHFsfGXjs",
    "https://youtu.be/jsYwFizhncE",
    "https://youtu.be/brU5yLm9DZM",
    "https://youtu.be/jBsC34PxzoM",
    "https://youtu.be/p_di4Zn4wz4",
    "https://youtu.be/ly4S0oi3Yz8",
    "https://youtu.be/ToIXSwZ1pJU",
    "https://youtu.be/r6sGWTCMz2k",
    "https://youtu.be/-qgreAUpPwM",
    "https://youtu.be/v0YEaeIClKY",
    "https://youtu.be/M64HUIJFTZM",
    "https://youtu.be/EK32jo7i5LQ",
    "https://youtu.be/Agbh95KyWxY",
    "https://youtu.be/U_85TaXbeIo",
    "https://youtu.be/HZGCoVF3YvM",
    "https://youtu.be/Kas0tIxDvrg",
    "https://youtu.be/8idr1WZ1A7Q",
    "https://youtu.be/gxAaO2rsdIs",
    "https://youtu.be/ZA4JkHKZM50",
    "https://youtu.be/ppWPuXsnf1Q",
    "https://youtu.be/MHXO86wKeDY",
    "https://youtu.be/yBw67Fb31Cs",
    "https://youtu.be/5PcpBw5Hbwo",
    "https://youtu.be/ZxYOEwM6Wbk",
    "https://youtu.be/IAEASE5GjdI",
    "https://youtu.be/cEvgcoyZvB4",
    "https://youtu.be/4PDoT7jtxmw",
    "https://youtu.be/elQVZLLiod4",
    "https://youtu.be/D__UaR5MQao",
    "https://youtu.be/pq9LcwC7CoY",
    "https://youtu.be/QvuQH4_05LI",
    "https://youtu.be/wTJI_WuZSwE",
    "https://youtu.be/mH0oCDa74tE",
    "https://youtu.be/X8jsijhllIA",
    "https://youtu.be/b3NxrZOu_CE",
    "https://youtu.be/lG4VkPoG3ko",
    "https://youtu.be/O85OWBJ2ayo",
    "https://youtu.be/e50Bj7jn9IQ",
    "https://youtu.be/ojjzXyQCzso",
    "https://youtu.be/-RdOwhmqP5s",
    "https://youtu.be/LqbZpur38nw",
    "https://youtu.be/F3Qixy-r_rQ",
    "https://youtu.be/ltLUadnCyi0",
    "https://youtu.be/v68zYyaEmEA",
    "https://youtu.be/fRed0Xmc2Wg",
    "https://youtu.be/bOXCLR3Wric",
    "https://youtu.be/hZuYICAEN9Y",
    "https://youtu.be/VYQVlVoWoPY",
    "https://youtu.be/cDofhN-RJqg",
    "https://youtu.be/851U557j6HE",
    "https://youtu.be/KuXjwB4LzSA",
    "https://youtu.be/zeJD6dqJ5lo",
    "https://youtu.be/cy8r7WSuT1I",
    "https://youtu.be/IaSGqQa5O-M",
    "https://youtu.be/NOCsdhzo6Jg",
    "https://youtu.be/YtkIWDE36qU",
    "https://youtu.be/d_qvLDhkg00",
    "https://youtu.be/QCX62YJCmGk",
    "https://youtu.be/aXRTczANuIs",
    "https://youtu.be/6a1fLEToyvU",
    "https://youtu.be/KTzGBJPuJwM",
    "https://youtu.be/Cz4Q4QOuoo8",
    "https://youtu.be/wjZofJX0v4M",
    "https://youtu.be/eMlx5fFNoYc",
    "https://youtu.be/W3I3kAg2J7w",
    "https://youtu.be/eMlx5fFNoYc",
    "https://youtu.be/EmKQsSDlaa4",
    "https://youtu.be/rbu7Zu5X1zI",
    "https://youtu.be/piJkuavhV50",
    "https://youtu.be/LPZh9BOjkQs",
    "https://youtu.be/IQqtsm-bBRU",
]


def test():
    local_root = '/Users/grant/3Blue1Brown Dropbox/3Blue1Brown/audio_tracks'
    db_root = 'https://www.dropbox.com/home/3Blue1Brown/audio_tracks'
    urls = URLS

    vid_to_dir = get_video_id_to_caption_directory_map()

    music_tracks = []
    narration_tracks = []
    for url in urls:
        if url:
            vid = extract_video_id(url)
        else:
            vid = "invalid_url"

        folder = vid_to_dir.get(vid, "")

        for lst, name in [(music_tracks, "only_music.mp3"), (narration_tracks, "only_narration.mp3")]:
            local_file = Path(folder.replace(CAPTIONS_DIRECTORY, local_root), name)
            if local_file.exists():
                lst.append(str(local_file).replace(local_root, db_root))
            else:
                lst.append("")

    pyperclip.copy("\n".join(music_tracks))
