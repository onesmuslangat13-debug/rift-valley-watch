# ============================================================
# RIFT VALLEY WATCH
# MAIN ORCHESTRATOR
# VERSION: RVW_MAIN_V33_REAL_PHOTO_HANDOFF
#
# PURPOSE
# - Run the real-time news engine
# - Read data/story.json
# - Select ONE story for the reel
# - Use the exact real photographs belonging to that story
# - Generate narration
# - Run the video renderer
# - Validate the final MP4
#
# IMPORTANT
# - Uses data/selected_story.json
# - Uses data/selected_script.json
# - Uses assets/source
# - Uses assets/video_work
# - Uses audio
# - Uses output
# ============================================================


from pathlib import Path
import json
import os
import re
import shutil
import subprocess
import sys
import time
import traceback

import requests
from PIL import Image
from gtts import gTTS


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"

SOURCE_DIR = BASE_DIR / "assets" / "source"

VIDEO_WORK_DIR = BASE_DIR / "assets" / "video_work"

AUDIO_DIR = BASE_DIR / "audio"

OUTPUT_DIR = BASE_DIR / "output"

STORY_FILE = DATA_DIR / "story.json"

SCRIPT_FILE = DATA_DIR / "script.json"

SELECTED_STORY_FILE = (
    DATA_DIR / "selected_story.json"
)

SELECTED_SCRIPT_FILE = (
    DATA_DIR / "selected_script.json"
)

NARRATION_FILE = (
    AUDIO_DIR / "narration.mp3"
)

RENDERER_FILE = (
    BASE_DIR / "rift_valley_video_generator.py"
)

NEWS_ENGINE = (
    BASE_DIR / "scripts" / "news_engine.py"
)

FINAL_VIDEO = (
    OUTPUT_DIR / "rift_valley_watch_reel.mp4"
)


# ============================================================
# SETTINGS
# ============================================================

MIN_IMAGE_BYTES = 10000

MIN_IMAGE_WIDTH = 300

MIN_IMAGE_HEIGHT = 200

MIN_AUDIO_BYTES = 1000

MIN_VIDEO_BYTES = 100000

MAX_IMAGES = 6

REQUEST_TIMEOUT = 30


# ============================================================
# FORBIDDEN TERMS
# ============================================================

FORBIDDEN_TERMS = [
    "rigathi gachagua",
    "gachagua",
]


FORBIDDEN_VISUAL_TERMS = [
    "citizen",
    "citizen digital",
    "citizen tv",
    "world cup",
    "worldcup",
    "avatar",
    "placeholder",
    "default image",
    "generic avatar",
    "profile picture",
]


SUPPORTED_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".avif",
}


# ============================================================
# LOGGING
# ============================================================

def log(message):
    print(
        f"[MAIN] {message}",
        flush=True,
    )


# ============================================================
# DIRECTORY SETUP
# ============================================================

def ensure_directories():
    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    VIDEO_WORK_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    AUDIO_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )


# ============================================================
# CLEAN WORKING OUTPUT
# ============================================================

def clean_working_files():
    log("Cleaning temporary working files...")

    # Do NOT delete source photos here.
    # The news engine creates them immediately before
    # selection.

    if VIDEO_WORK_DIR.exists():
        for item in VIDEO_WORK_DIR.iterdir():
            try:
                if item.is_dir():
                    shutil.rmtree(
                        item,
                        ignore_errors=True,
                    )
                else:
                    item.unlink(
                        missing_ok=True,
                    )

            except Exception as exc:
                log(
                    f"Could not remove "
                    f"{item}: {exc}"
                )

    # Remove old narration.
    try:
        NARRATION_FILE.unlink(
            missing_ok=True,
        )
    except Exception:
        pass

    # Remove old selected files.
    try:
        SELECTED_STORY_FILE.unlink(
            missing_ok=True,
        )
    except Exception:
        pass

    try:
        SELECTED_SCRIPT_FILE.unlink(
            missing_ok=True,
        )
    except Exception:
        pass

    # Remove previous final video.
    try:
        FINAL_VIDEO.unlink(
            missing_ok=True,
        )
    except Exception:
        pass


# ============================================================
# JSON
# ============================================================

def load_json(path):
    if not path.exists():
        raise RuntimeError(
            f"Required JSON file does not exist: "
            f"{path}"
        )

    if path.stat().st_size == 0:
        raise RuntimeError(
            f"Required JSON file is empty: "
            f"{path}"
        )

    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as handle:
            return json.load(
                handle
            )

    except Exception as exc:
        raise RuntimeError(
            f"Could not parse JSON file "
            f"{path}: {exc}"
        )


def save_json(path, data):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    temporary = path.with_suffix(
        path.suffix + ".tmp"
    )

    with temporary.open(
        "w",
        encoding="utf-8",
    ) as handle:
        json.dump(
            data,
            handle,
            ensure_ascii=False,
            indent=2,
        )

    temporary.replace(
        path
    )


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    text = str(
        value
    )

    text = text.replace(
        "\r",
        " ",
    )

    text = text.replace(
        "\n",
        " ",
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def contains_forbidden_text(text):
    lowered = clean_text(
        text
    ).lower()

    for term in FORBIDDEN_TERMS:
        if term in lowered:
            return True

    return False


def contains_forbidden_visual_text(text):
    lowered = clean_text(
        text
    ).lower()

    for term in FORBIDDEN_VISUAL_TERMS:
        if term in lowered:
            return True

    return False


# ============================================================
# IMAGE PATH RESOLUTION
# ============================================================

def resolve_image_path(
    image_value
):
    if not image_value:
        return None

    if isinstance(
        image_value,
        dict,
    ):
        image_value = (
            image_value.get("path")
            or image_value.get("file")
            or image_value.get("image")
            or image_value.get("image_path")
            or ""
        )

    image_value = clean_text(
        image_value
    )

    if not image_value:
        return None

    # --------------------------------------------------------
    # Absolute path.
    # --------------------------------------------------------

    candidate = Path(
        image_value
    )

    if candidate.is_absolute():
        if candidate.exists():
            return candidate

    # --------------------------------------------------------
    # Normal repository-relative path.
    # --------------------------------------------------------

    candidate = (
        BASE_DIR / image_value
    )

    if candidate.exists():
        return candidate

    # --------------------------------------------------------
    # Handle paths beginning with ./.
    # --------------------------------------------------------

    cleaned = image_value

    if cleaned.startswith(
        "./"
    ):
        cleaned = cleaned[2:]

    candidate = (
        BASE_DIR / cleaned
    )

    if candidate.exists():
        return candidate

    # --------------------------------------------------------
    # Handle assets/source filename only.
    # --------------------------------------------------------

    filename = Path(
        cleaned
    ).name

    candidate = (
        SOURCE_DIR / filename
    )

    if candidate.exists():
        return candidate

    # --------------------------------------------------------
    # Search source directory recursively.
    # --------------------------------------------------------

    if SOURCE_DIR.exists():
        matches = list(
            SOURCE_DIR.rglob(
                filename
            )
        )

        if matches:
            return matches[0]

    return None


# ============================================================
# REAL IMAGE VALIDATION
# ============================================================

def image_is_valid(
    path
):
    try:
        if path is None:
            return False

        if not path.exists():
            return False

        if not path.is_file():
            return False

        if path.stat().st_size < MIN_IMAGE_BYTES:
            return False

        suffix = path.suffix.lower()

        if suffix not in SUPPORTED_IMAGE_EXTENSIONS:
            return False

        # Reject forbidden filename signals.
        if contains_forbidden_visual_text(
            path.name
        ):
            return False

        # ----------------------------------------------------
        # PIL verification.
        # ----------------------------------------------------

        with Image.open(
            path
        ) as image:
            width, height = image.size

            if width < MIN_IMAGE_WIDTH:
                return False

            if height < MIN_IMAGE_HEIGHT:
                return False

            # Force image decoding.
            image.load()

        return True

    except Exception:
        return False


# ============================================================
# IMAGE SIGNATURE
# ============================================================

def image_signature(
    path
):
    try:
        import hashlib

        digest = hashlib.sha256()

        with path.open(
            "rb"
        ) as handle:
            while True:
                chunk = handle.read(
                    1024 * 1024
                )

                if not chunk:
                    break

                digest.update(
                    chunk
                )

        return digest.hexdigest()

    except Exception:
        return ""


# ============================================================
# COLLECT ONLY THE SELECTED STORY'S PHOTOS
# ============================================================

def collect_story_images(
    story
):
    images = []

    seen_paths = set()

    seen_signatures = set()

    # --------------------------------------------------------
    # PRIMARY SOURCE:
    # exact "images" list from story.json.
    # --------------------------------------------------------

    explicit_images = story.get(
        "images",
        [],
    )

    if not isinstance(
        explicit_images,
        list,
    ):
        explicit_images = [
            explicit_images
        ]

    log(
        "Explicit images in selected story: "
        f"{len(explicit_images)}"
    )

    for image_value in explicit_images:
        path = resolve_image_path(
            image_value
        )

        if path is None:
            log(
                f"Image path not found: "
                f"{image_value}"
            )

            continue

        if not image_is_valid(
            path
        ):
            log(
                f"Image failed validation: "
                f"{path}"
            )

            continue

        resolved = str(
            path.resolve()
        )

        if resolved in seen_paths:
            continue

        signature = image_signature(
            path
        )

        if (
            signature
            and signature in seen_signatures
        ):
            continue

        seen_paths.add(
            resolved
        )

        if signature:
            seen_signatures.add(
                signature
            )

        images.append(
            path
        )

        if len(images) >= MAX_IMAGES:
            break

    # --------------------------------------------------------
    # SECONDARY FIELDS.
    # --------------------------------------------------------

    if len(images) < MAX_IMAGES:
        fallback_fields = [
            "image",
            "image_path",
        ]

        for field in fallback_fields:
            value = story.get(
                field
            )

            if not value:
                continue

            path = resolve_image_path(
                value
            )

            if path is None:
                continue

            if not image_is_valid(
                path
            ):
                continue

            resolved = str(
                path.resolve()
            )

            if resolved in seen_paths:
                continue

            signature = image_signature(
                path
            )

            if (
                signature
                and signature in seen_signatures
            ):
                continue

            seen_paths.add(
                resolved
            )

            if signature:
                seen_signatures.add(
                    signature
                )

            images.append(
                path
            )

            if len(images) >= MAX_IMAGES:
                break

    # --------------------------------------------------------
    # IMPORTANT:
    # Do NOT indiscriminately collect every image from
    # assets/source. That can mix photographs belonging
    # to different stories.
    # --------------------------------------------------------

    log(
        f"Validated selected-story photographs: "
        f"{len(images)}"
    )

    for index, path in enumerate(
        images,
        start=1,
    ):
        log(
            f"PHOTO {index}: "
            f"{path}"
        )

    return images


# ============================================================
# STORY QUALITY SCORE
# ============================================================

def story_score(
    story
):
    title = clean_text(
        story.get("title")
    )

    summary = clean_text(
        story.get("summary")
    )

    county = clean_text(
        story.get("county")
    )

    category = clean_text(
        story.get("category")
    )

    score = 0

    if title:
        score += 20

    if len(title) >= 40:
        score += 5

    if summary:
        score += 10

    if len(summary) >= 80:
        score += 5

    if county:
        score += 20

    if category:
        score += 10

    category_weights = {
        "POLITICS": 20,
        "DEVELOPMENT": 18,
        "INFRASTRUCTURE": 18,
        "BUSINESS & ECONOMY": 17,
        "AGRICULTURE": 15,
        "HEALTH": 13,
        "EDUCATION": 13,
        "SECURITY": 14,
    }

    score += category_weights.get(
        category.upper(),
        5,
    )

    images = story.get(
        "images",
        [],
    )

    if isinstance(
        images,
        list,
    ):
        score += min(
            len(images) * 12,
            60,
        )

    return score


# ============================================================
# SELECT STORY
# ============================================================

def select_story(
    story_payload
):
    if isinstance(
        story_payload,
        dict,
    ):
        stories = story_payload.get(
            "stories",
            [],
        )

        # Some engines may produce a single story object.
        if not stories and story_payload.get(
            "title"
        ):
            stories = [
                story_payload
            ]

    elif isinstance(
        story_payload,
        list,
    ):
        stories = story_payload

    else:
        stories = []

    if not isinstance(
        stories,
        list,
    ):
        stories = []

    log(
        f"Stories available: "
        f"{len(stories)}"
    )

    candidates = []

    for index, story in enumerate(
        stories,
        start=1,
    ):
        if not isinstance(
            story,
            dict,
        ):
            continue

        title = clean_text(
            story.get("title")
        )

        if not title:
            continue

        if contains_forbidden_text(
            title
        ):
            log(
                f"Rejected forbidden story: "
                f"{title}"
            )

            continue

        source = story.get(
            "source",
            {},
        )

        if not isinstance(
            source,
            dict,
        ):
            source = {}

        source_name = clean_text(
            source.get("name")
        )

        if contains_forbidden_visual_text(
            source_name
        ):
            log(
                f"Rejected forbidden source: "
                f"{source_name}"
            )

            continue

        images = collect_story_images(
            story
        )

        if not images:
            log(
                f"Rejected story with no "
                f"validated photographs: "
                f"{title}"
            )

            continue

        # Create a clean copy so the selected story
        # contains only the exact valid image paths.
        selected = dict(
            story
        )

        selected["images"] = [
            str(
                path.relative_to(
                    BASE_DIR
                )
            )
            for path in images
        ]

        selected["image"] = (
            selected["images"][0]
        )

        selected["image_path"] = (
            selected["images"][0]
        )

        selected["_resolved_images"] = [
            str(path)
            for path in images
        ]

        selected["_score"] = (
            story_score(
                selected
            )
        )

        candidates.append(
            selected
        )

        log(
            f"Candidate accepted: "
            f"{title} | "
            f"photos={len(images)} | "
            f"score={selected['_score']}"
        )

    if not candidates:
        raise RuntimeError(
            "No valid real article "
            "photographs found"
        )

    candidates.sort(
        key=lambda item: item.get(
            "_score",
            0,
        ),
        reverse=True,
    )

    selected = candidates[0]

    # Remove internal fields before writing JSON.
    selected.pop(
        "_resolved_images",
        None,
    )

    selected.pop(
        "_score",
        None,
    )

    log()
    log(
        "SELECTED STORY:"
    )

    log(
        clean_text(
            selected.get(
                "title"
            )
        )
    )

    log(
        "County: "
        + clean_text(
            selected.get(
                "county"
            )
        )
    )

    log(
        "Category: "
        + clean_text(
            selected.get(
                "category"
            )
        )
    )

    log(
        "Photos: "
        + str(
            len(
                selected.get(
                    "images",
                    [],
                )
            )
        )
    )

    return selected


# ============================================================
# NARRATION TEXT
# ============================================================

def build_narration_text(
    story
):
    title = clean_text(
        story.get("title")
    )

    summary = clean_text(
        story.get("summary")
    )

    county = clean_text(
        story.get("county")
    )

    category = clean_text(
        story.get("category")
    )

    source = story.get(
        "source",
        {},
    )

    if not isinstance(
        source,
        dict,
    ):
        source = {}

    source_name = clean_text(
        source.get("name")
    )

    pieces = []

    if title:
        pieces.append(
            title + "."
        )

    if summary:
        pieces.append(
            summary
        )

    if county:
        pieces.append(
            f"The latest development "
            f"is from {county}."
        )

    if category:
        pieces.append(
            f"This is a "
            f"{category.lower()} update "
            f"from Rift Valley Watch."
        )

    if source_name:
        pieces.append(
            f"Source: {source_name}."
        )

    narration = " ".join(
        pieces
    )

    narration = clean_text(
        narration
    )

    if contains_forbidden_text(
        narration
    ):
        raise RuntimeError(
            "Selected narration contains "
            "a forbidden person/topic."
        )

    return narration


# ============================================================
# GENERATE NARRATION
# ============================================================

def generate_narration(
    story
):
    narration = build_narration_text(
        story
    )

    if not narration:
        raise RuntimeError(
            "Narration text is empty."
        )

    log(
        "Generating narration..."
    )

    try:
        tts = gTTS(
            text=narration,
            lang="en",
            slow=False,
        )

        tts.save(
            str(
                NARRATION_FILE
            )
        )

    except Exception as exc:
        raise RuntimeError(
            "Text-to-speech generation "
            f"failed: {exc}"
        )

    if not NARRATION_FILE.exists():
        raise RuntimeError(
            "Narration file was not created."
        )

    if (
        NARRATION_FILE.stat().st_size
        < MIN_AUDIO_BYTES
    ):
        raise RuntimeError(
            "Narration file is too small."
        )

    log(
        "Narration created: "
        f"{NARRATION_FILE}"
    )

    return narration


# ============================================================
# SELECTED SCRIPT
# ============================================================

def create_selected_script(
    story,
    narration,
):
    source = story.get(
        "source",
        {},
    )

    if not isinstance(
        source,
        dict,
    ):
        source = {}

    script = {
        "id": story.get(
            "id",
            "",
        ),

        "title": story.get(
            "title",
            "",
        ),

        "county": story.get(
            "county",
            "",
        ),

        "category": story.get(
            "category",
            "",
        ),

        "date": story.get(
            "date",
            "",
        ),

        "source": {
            "name": source.get(
                "name",
                "",
            ),
            "url": source.get(
                "url",
                "",
            ),
        },

        "narration": narration,

        "audio": str(
            NARRATION_FILE.relative_to(
                BASE_DIR
            )
        ),

        "images": story.get(
            "images",
            [],
        ),
    }

    save_json(
        SELECTED_SCRIPT_FILE,
        script,
    )

    log(
        "Selected script written: "
        f"{SELECTED_SCRIPT_FILE}"
    )

    return script


# ============================================================
# SELECTED STORY FILE
# ============================================================

def create_selected_story(
    story
):
    save_json(
        SELECTED_STORY_FILE,
        story,
    )

    log(
        "Selected story written: "
        f"{SELECTED_STORY_FILE}"
    )


# ============================================================
# VERIFY SELECTED DATA
# ============================================================

def validate_selected_data():
    log()
    log(
        "Validating selected story data..."
    )

    selected_story = load_json(
        SELECTED_STORY_FILE
    )

    images = selected_story.get(
        "images",
        [],
    )

    if not isinstance(
        images,
        list,
    ):
        raise RuntimeError(
            "selected_story.json images "
            "field is not a list."
        )

    if not images:
        raise RuntimeError(
            "selected_story.json contains "
            "no images."
        )

    valid = []

    for image in images:
        path = resolve_image_path(
            image
        )

        if path is None:
            log(
                f"Selected image missing: "
                f"{image}"
            )

            continue

        if not image_is_valid(
            path
        ):
            log(
                f"Selected image invalid: "
                f"{path}"
            )

            continue

        valid.append(
            path
        )

    if not valid:
        raise RuntimeError(
            "No valid real article "
            "photographs found"
        )

    log(
        f"Selected story has "
        f"{len(valid)} valid photograph(s)."
    )

    for index, path in enumerate(
        valid,
        start=1,
    ):
        log(
            f"VALID PHOTO {index}: "
            f"{path}"
        )

    return selected_story, valid


# ============================================================
# RUN NEWS ENGINE
# ============================================================

def run_news_engine():
    if not NEWS_ENGINE.exists():
        raise RuntimeError(
            "News engine not found: "
            f"{NEWS_ENGINE}"
        )

    log()
    log(
        "=" * 72
    )

    log(
        "RUNNING REAL-TIME NEWS ENGINE V7"
    )

    log(
        "=" * 72
    )

    command = [
        sys.executable,
        str(
            NEWS_ENGINE
        ),
    ]

    result = subprocess.run(
        command,
        cwd=str(
            BASE_DIR
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    engine_output = (
        result.stdout
        or ""
    )

    if engine_output:
        print(
            engine_output,
            flush=True,
        )

    if result.returncode != 0:
        raise RuntimeError(
            "News engine failed with "
            f"exit code {result.returncode}.\n\n"
            "FULL NEWS ENGINE OUTPUT:\n"
            f"{engine_output[-16000:]}"
        )

    if not STORY_FILE.exists():
        raise RuntimeError(
            "News engine completed but "
            "data/story.json was not created."
        )

    if STORY_FILE.stat().st_size == 0:
        raise RuntimeError(
            "News engine created an empty "
            "data/story.json."
        )

    log(
        "News engine completed successfully."
    )


# ============================================================
# RUN RENDERER
# ============================================================

def run_renderer():
    if not RENDERER_FILE.exists():
        raise RuntimeError(
            "Video renderer not found: "
            f"{RENDERER_FILE}"
        )

    log()
    log(
        "=" * 72
    )

    log(
        "RUNNING VIDEO RENDERER"
    )

    log(
        "=" * 72
    )

    command = [
        sys.executable,
        str(
            RENDERER_FILE
        ),
    ]

    result = subprocess.run(
        command,
        cwd=str(
            BASE_DIR
        ),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    renderer_output = (
        result.stdout
        or ""
    )

    if renderer_output:
        print(
            renderer_output,
            flush=True,
        )

    if result.returncode != 0:
        raise RuntimeError(
            "Video renderer failed with "
            f"exit code {result.returncode}.\n\n"
            "FULL VIDEO RENDERER OUTPUT:\n"
            f"{renderer_output[-20000:]}"
        )

    log(
        "Video renderer completed."
    )


# ============================================================
# FFPROBE
# ============================================================

def run_ffprobe(
    path
):
    ffprobe = shutil.which(
        "ffprobe"
    )

    if not ffprobe:
        log(
            "ffprobe not found; skipping "
            "detailed MP4 probe."
        )

        return True

    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "format=duration,size",
        "-of",
        "default=noprint_wrappers=1",
        str(path),
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    output = (
        result.stdout
        or ""
    )

    if result.returncode != 0:
        log(
            "ffprobe validation failed:"
        )

        log(
            output
        )

        return False

    log(
        "ffprobe:"
    )

    log(
        output.strip()
    )

    return True


# ============================================================
# VALIDATE FINAL VIDEO
# ============================================================

def validate_final_video():
    log()
    log(
        "Validating final MP4..."
    )

    if not FINAL_VIDEO.exists():
        raise RuntimeError(
            "Final MP4 was not created: "
            f"{FINAL_VIDEO}"
        )

    size = FINAL_VIDEO.stat().st_size

    log(
        f"Final MP4 size: "
        f"{size} bytes"
    )

    if size < MIN_VIDEO_BYTES:
        raise RuntimeError(
            "Final MP4 is too small."
        )

    if not run_ffprobe(
        FINAL_VIDEO
    ):
        raise RuntimeError(
            "Final MP4 failed ffprobe "
            "validation."
        )

    log(
        "FINAL VIDEO VALIDATION PASSED."
    )


# ============================================================
# FINAL SUMMARY
# ============================================================

def print_final_summary(
    story,
    images,
):
    source = story.get(
        "source",
        {},
    )

    if not isinstance(
        source,
        dict,
    ):
        source = {}

    print()
    print(
        "=" * 72
    )

    print(
        "RIFT VALLEY WATCH GENERATOR "
        "COMPLETED SUCCESSFULLY"
    )

    print(
        "=" * 72
    )

    print()

    print(
        "SELECTED STORY:"
    )

    print(
        clean_text(
            story.get(
                "title"
            )
        )
    )

    print()

    print(
        "COUNTY: "
        + clean_text(
            story.get(
                "county"
            )
        )
    )

    print(
        "CATEGORY: "
        + clean_text(
            story.get(
                "category"
            )
        )
    )

    print(
        "SOURCE: "
        + clean_text(
            source.get(
                "name"
            )
        )
    )

    print()

    print(
        "REAL ARTICLE PHOTOGRAPHS:"
    )

    for index, image in enumerate(
        images,
        start=1,
    ):
        print(
            f"{index}. {image}"
        )

    print()

    print(
        "NARRATION:"
    )

    print(
        NARRATION_FILE
    )

    print()

    print(
        "FINAL MP4:"
    )

    print(
        FINAL_VIDEO
    )

    print()

    print(
        "STATUS: SUCCESS"
    )

    print(
        "=" * 72
    )


# ============================================================
# MAIN
# ============================================================

def main():
    start_time = time.time()

    try:
        ensure_directories()

        clean_working_files()

        # ----------------------------------------------------
        # 1. Fetch fresh news + photographs.
        # ----------------------------------------------------

        run_news_engine()

        # ----------------------------------------------------
        # 2. Load story JSON.
        # ----------------------------------------------------

        story_payload = load_json(
            STORY_FILE
        )

        # ----------------------------------------------------
        # 3. Select one story.
        # ----------------------------------------------------

        selected_story = select_story(
            story_payload
        )

        # ----------------------------------------------------
        # 4. Generate narration.
        # ----------------------------------------------------

        narration = generate_narration(
            selected_story
        )

        # ----------------------------------------------------
        # 5. Write selected story/script.
        # ----------------------------------------------------

        create_selected_story(
            selected_story
        )

        create_selected_script(
            selected_story,
            narration,
        )

        # ----------------------------------------------------
        # 6. Validate exact selected assets.
        # ----------------------------------------------------

        selected_story, images = (
            validate_selected_data()
        )

        # ----------------------------------------------------
        # 7. Render video.
        # ----------------------------------------------------

        run_renderer()

        # ----------------------------------------------------
        # 8. Validate final MP4.
        # ----------------------------------------------------

        validate_final_video()

        elapsed = (
            time.time()
            - start_time
        )

        print_final_summary(
            selected_story,
            images,
        )

        print(
            f"Elapsed time: "
            f"{elapsed:.1f} seconds"
        )

        return 0

    except KeyboardInterrupt:
        print()
        print(
            "RIFT VALLEY WATCH GENERATOR "
            "INTERRUPTED"
        )

        return 130

    except Exception as exc:
        print()
        print(
            "=" * 72
        )

        print(
            "RIFT VALLEY WATCH "
            "VIDEO GENERATOR FAILED"
        )

        print(
            "=" * 72
        )

        print()
        print(
            f"ERROR: {exc}"
        )

        print()
        print(
            "STATUS: FAILED"
        )

        print()
        print(
            "TRACEBACK:"
        )

        traceback.print_exc()

        print(
            "=" * 72
        )

        return 1


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    sys.exit(
        main()
    )
