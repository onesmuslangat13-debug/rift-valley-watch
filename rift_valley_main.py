# ============================================================
# RIFT VALLEY WATCH
# MAIN ORCHESTRATOR
#
# VERSION: RVW_MAIN_V30_STABLE_PIPELINE
#
# FLOW:
#
# news_engine.py
#       ↓
# data/story.json
# data/script.json
#       ↓
# select ONE story
#       ↓
# data/selected_story.json
# data/selected_script.json
#       ↓
# audio/narration.mp3
#       ↓
# rift_valley_video_generator.py
#       ↓
# output/rift_valley_watch_reel.mp4
# ============================================================

from pathlib import Path
import json
import re
import subprocess
import sys
import shutil
import traceback

from gtts import gTTS


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(
    __file__
).resolve().parent

DATA_DIR = BASE_DIR / "data"
SOURCE_DIR = BASE_DIR / "assets" / "source"
VIDEO_WORK_DIR = BASE_DIR / "assets" / "video_work"
AUDIO_DIR = BASE_DIR / "audio"
OUTPUT_DIR = BASE_DIR / "output"

STORY_FILE = DATA_DIR / "story.json"
SCRIPT_FILE = DATA_DIR / "script.json"

SELECTED_STORY_FILE = (
    DATA_DIR /
    "selected_story.json"
)

SELECTED_SCRIPT_FILE = (
    DATA_DIR /
    "selected_script.json"
)

NARRATION_FILE = (
    AUDIO_DIR /
    "narration.mp3"
)

RENDERER_FILE = (
    BASE_DIR /
    "rift_valley_video_generator.py"
)

FINAL_VIDEO = (
    OUTPUT_DIR /
    "rift_valley_watch_reel.mp4"
)


# ============================================================
# SETTINGS
# ============================================================

MIN_AUDIO_BYTES = 1000
MIN_IMAGE_BYTES = 10000
MIN_VIDEO_BYTES = 100000

FORBIDDEN_TERMS = [
    "rigathi gachagua",
    "gachagua",
]


# ============================================================
# LOGGING
# ============================================================

def banner(title):

    print()
    print("=" * 70)
    print(title)
    print("=" * 70)
    print()


def log(message):

    print(
        "[RIFT VALLEY WATCH]",
        message,
        flush=True
    )


# ============================================================
# DIRECTORY SETUP
# ============================================================

def ensure_directories():

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    VIDEO_WORK_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    AUDIO_DIR.mkdir(
        parents=True,
        exist_ok=True
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True
    )


# ============================================================
# CLEAN GENERATED OUTPUT
# ============================================================

def clean_generated_files():

    banner(
        "CLEANING PREVIOUS GENERATED FILES"
    )

    files_to_remove = [
        FINAL_VIDEO,
        NARRATION_FILE,
        AUDIO_DIR / "narration_temp.mp3",
        VIDEO_WORK_DIR / "narration.mp3",
        SELECTED_STORY_FILE,
        SELECTED_SCRIPT_FILE,
    ]

    for file in files_to_remove:

        try:

            if file.exists():

                file.unlink()

                log(
                    f"Removed: {file}"
                )

        except Exception as exc:

            log(
                f"Could not remove {file}: {exc}"
            )

    # Remove old story photos only.
    for file in SOURCE_DIR.glob(
        "story_*"
    ):

        if not file.is_file():
            continue

        try:

            file.unlink()

        except Exception:
            pass


# ============================================================
# LOAD JSON
# ============================================================

def load_json(path):

    if not path.exists():

        raise RuntimeError(
            f"Required JSON file does not exist: {path}"
        )

    try:

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except Exception as exc:

        raise RuntimeError(
            f"Could not load JSON {path}: {exc}"
        )


# ============================================================
# SAVE JSON
# ============================================================

def save_json(
    path,
    payload
):

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            payload,
            f,
            indent=2,
            ensure_ascii=False
        )


# ============================================================
# FORBIDDEN STORY CHECK
# ============================================================

def contains_forbidden_content(
    story
):

    text = " ".join(
        [
            str(
                story.get(
                    "title",
                    ""
                )
            ),
            str(
                story.get(
                    "description",
                    ""
                )
            ),
            str(
                story.get(
                    "source",
                    ""
                )
            ),
        ]
    ).lower()

    for term in FORBIDDEN_TERMS:

        if term in text:
            return True

    return False


# ============================================================
# NORMALIZE IMAGE PATH
# ============================================================

def resolve_image_path(
    value
):

    if not value:
        return None

    value = str(
        value
    ).strip()

    if not value:
        return None

    path = Path(
        value
    )

    if path.is_absolute():
        candidate = path
    else:
        candidate = (
            BASE_DIR /
            value
        )

    candidate = candidate.resolve()

    if not candidate.exists():
        return None

    if not candidate.is_file():
        return None

    return candidate


# ============================================================
# COLLECT STORY IMAGES
# ============================================================

def collect_story_images(
    story
):

    candidates = []

    # New multi-photo field.
    for value in story.get(
        "image_paths",
        []
    ) or []:

        path = resolve_image_path(
            value
        )

        if path:
            candidates.append(
                path
            )

    # Legacy single-photo field.
    for key in [
        "image_path",
        "local_image",
        "image",
    ]:

        path = resolve_image_path(
            story.get(
                key,
                ""
            )
        )

        if path:
            candidates.append(
                path
            )

    # Search source directory as final
    # controlled fallback.
    for path
