# ============================================================
# RIFT VALLEY WATCH
# MAIN ORCHESTRATOR
# VERSION: RVW_MAIN_V34_REAL_PHOTO_RECOVERY
#
# PURPOSE
# - Run the real-time news engine
# - Read data/story.json
# - Select ONE story
# - Recover the exact photographs belonging to that story
# - Normalize valid source images when necessary
# - Generate narration
# - Write selected_story.json / selected_script.json
# - Run the video renderer
# - Validate the final MP4
#
# IMPORTANT
# - Never mixes unrelated source photographs
# - Rejects Citizen / World Cup / avatar / placeholder visuals
# - Handles .jpg files containing PNG/WebP/other valid image data
# - Handles path separator and escaped-path problems
# ============================================================

from pathlib import Path
from io import BytesIO
import hashlib
import json
import re
import shutil
import subprocess
import sys
import time
import traceback

from PIL import Image, ImageOps
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

SELECTED_STORY_FILE = DATA_DIR / "selected_story.json"
SELECTED_SCRIPT_FILE = DATA_DIR / "selected_script.json"

NARRATION_FILE = AUDIO_DIR / "narration.mp3"

RENDERER_FILE = BASE_DIR / "rift_valley_video_generator.py"
NEWS_ENGINE = BASE_DIR / "scripts" / "news_engine.py"

FINAL_VIDEO = OUTPUT_DIR / "rift_valley_watch_reel.mp4"


# ============================================================
# SETTINGS
# ============================================================

MIN_IMAGE_BYTES = 5000
MIN_IMAGE_WIDTH = 300
MIN_IMAGE_HEIGHT = 200

MIN_AUDIO_BYTES = 1000
MIN_VIDEO_BYTES = 100000

MAX_IMAGES = 6


# ============================================================
# FORBIDDEN STORY TERMS
# ============================================================

FORBIDDEN_TERMS = [
    "rigathi gachagua",
    "gachagua",
]


# ============================================================
# FORBIDDEN VISUAL TERMS
# ============================================================

FORBIDDEN_VISUAL_TERMS = [
    "citizen",
    "citizen digital",
    "citizen tv",
    "ctv",
    "world cup",
    "worldcup",
    "avatar",
    "placeholder",
    "default image",
    "default_image",
    "generic avatar",
    "profile picture",
    "profile_picture",
    "dummy",
    "generic",
    "logo",
    "icon",
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

def log(message=""):
    print(
        f"[MAIN] {message}",
        flush=True,
    )


# ============================================================
# DIRECTORIES
# ============================================================

def ensure_directories():
    for directory in [
        DATA_DIR,
        SOURCE_DIR,
        VIDEO_WORK_DIR,
        AUDIO_DIR,
        OUTPUT_DIR,
    ]:
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )


# ============================================================
# CLEAN WORKING FILES
# ============================================================

def clean_working_files():
    log("Cleaning temporary working files...")

    # Never delete source photographs here.
    if VIDEO_WORK_DIR.exists():
        for item in list(VIDEO_WORK_DIR.iterdir()):
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
                    f"Could not remove {item}: {exc}"
                )

    for file_path in [
        NARRATION_FILE,
        SELECTED_STORY_FILE,
        SELECTED_SCRIPT_FILE,
        FINAL_VIDEO,
    ]:
        try:
            file_path.unlink(
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
            f"Required JSON file does not exist: {path}"
        )

    if path.stat().st_size == 0:
        raise RuntimeError(
            f"Required JSON file is empty: {path}"
        )

    try:
        with path.open(
            "r",
            encoding="utf-8",
        ) as handle:
            return json.load(handle)

    except Exception as exc:
        raise RuntimeError(
            f"Could not parse JSON file {path}: {exc}"
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

    temporary.replace(path)


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    text = str(value)

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
    lowered = clean_text(text).lower()

    return any(
        term in lowered
        for term in FORBIDDEN_TERMS
    )


def contains_forbidden_visual_text(text):
    lowered = clean_text(text).lower()

    return any(
        term in lowered
        for term in FORBIDDEN_VISUAL_TERMS
    )


# ============================================================
# NORMALIZE IMAGE REFERENCE
# ============================================================

def normalize_image_reference(value):
    if value is None:
        return ""

    if isinstance(value, dict):
        value = (
            value.get("local_path")
            or value.get("local_file")
            or value.get("path")
            or value.get("file")
            or value.get("image_path")
            or value.get("image")
            or value.get("photo")
            or ""
        )

    if not isinstance(value, str):
        value = str(value)

    value = value.strip()

    # Some generated JSON/log output has escaped underscores.
    value = value.replace(
        r"\_",
        "_",
    )

    value = value.replace(
        "\\",
        "/",
    )

    value = value.replace(
        "\r",
        "",
    ).replace(
        "\n",
        "",
    )

    while value.startswith("./"):
        value = value[2:]

    return value.strip()


# ============================================================
# IMAGE PATH RESOLUTION
# ============================================================

def resolve_image_path(image_value):
    cleaned = normalize_image_reference(
        image_value
    )

    if not cleaned:
        return None

    # --------------------------------------------------------
    # 1. Absolute path
    # --------------------------------------------------------

    candidate = Path(cleaned)

    if candidate.is_absolute():
        if candidate.exists():
            return candidate.resolve()

    # --------------------------------------------------------
    # 2. Repository-relative path
    # --------------------------------------------------------

    candidate = (
        BASE_DIR / cleaned
    )

    if candidate.exists():
        return candidate.resolve()

    # --------------------------------------------------------
    # 3. Source-relative path
    # --------------------------------------------------------

    candidate = (
        SOURCE_DIR / cleaned
    )

    if candidate.exists():
        return candidate.resolve()

    # --------------------------------------------------------
    # 4. Filename only
    # --------------------------------------------------------

    filename = Path(cleaned).name

    if filename:
        candidate = (
            SOURCE_DIR / filename
        )

        if candidate.exists():
            return candidate.resolve()

    # --------------------------------------------------------
    # 5. Recursive exact filename search
    # --------------------------------------------------------

    if SOURCE_DIR.exists() and filename:
        try:
            for match in SOURCE_DIR.rglob(filename):
                if match.is_file():
                    return match.resolve()
        except Exception:
            pass

    # --------------------------------------------------------
    # 6. Same stem with another extension
    #
    # Example:
    # story_1_image.jpg
    # actual file:
    # story_1_image.webp
    # --------------------------------------------------------

    stem = Path(filename).stem

    if SOURCE_DIR.exists() and stem:
        try:
            for match in SOURCE_DIR.rglob("*"):
                if not match.is_file():
                    continue

                if match.stem.lower() != stem.lower():
                    continue

                if match.suffix.lower() not in (
                    SUPPORTED_IMAGE_EXTENSIONS
                ):
                    continue

                return match.resolve()

        except Exception:
            pass

    return None


# ============================================================
# IMAGE NORMALIZATION
# ============================================================

def normalize_image_file(path):
    """
    Opens the actual image bytes.

    If a valid image has been saved with the wrong extension,
    convert it to a genuine JPEG and replace the original.

    This specifically protects against cases where the news
    engine saves WebP/PNG bytes into a .jpg filename.
    """

    if path is None:
        return None

    path = Path(path)

    if not path.exists():
        return None

    try:
        with Image.open(path) as source:
            width, height = source.size

            if (
                width < MIN_IMAGE_WIDTH
                or height < MIN_IMAGE_HEIGHT
            ):
                return None

            source.load()

            image = ImageOps.exif_transpose(
                source
            ).convert("RGB")

            # Always create a genuine JPEG for renderer stability.
            temporary = path.with_name(
                path.name + ".normalized.jpg"
            )

            image.save(
                temporary,
                format="JPEG",
                quality=92,
                optimize=True,
            )

        if (
            not temporary.exists()
            or temporary.stat().st_size < MIN_IMAGE_BYTES
        ):
            temporary.unlink(
                missing_ok=True
            )
            return None

        # If already a .jpg/.jpeg, replace it.
        # Otherwise retain original and return normalized JPEG.
        if path.suffix.lower() in {
            ".jpg",
            ".jpeg",
        }:
            temporary.replace(path)
            return path.resolve()

        normalized = path.with_name(
            path.stem + "_normalized.jpg"
        )

        if normalized.exists():
            normalized.unlink(
                missing_ok=True
            )

        temporary.replace(normalized)

        return normalized.resolve()

    except Exception as exc:
        log(
            f"Image normalization failed for {path}: {exc}"
        )

        try:
            temporary = path.with_name(
                path.name + ".normalized.jpg"
            )
            temporary.unlink(
                missing_ok=True
            )
        except Exception:
            pass

        return None


# ============================================================
# REAL IMAGE VALIDATION
# ============================================================

def image_is_valid(
    path,
    normalize=False,
):
    if path is None:
        return False

    path = Path(path)

    try:
        if not path.exists():
            return False

        if not path.is_file():
            return False

        if path.stat().st_size < MIN_IMAGE_BYTES:
            return False

        if contains_forbidden_visual_text(
            path.name
        ):
            return False

        # ----------------------------------------------------
        # Direct PIL validation.
        # This does NOT trust the extension.
        # ----------------------------------------------------

        with Image.open(path) as image:
            width, height = image.size

            if width < MIN_IMAGE_WIDTH:
                return False

            if height < MIN_IMAGE_HEIGHT:
                return False

            image.load()

        return True

    except Exception:
        if normalize:
            normalized = normalize_image_file(
                path
            )

            return (
                normalized is not None
                and normalized.exists()
                and normalized.stat().st_size >= MIN_IMAGE_BYTES
            )

        return False


# ============================================================
# IMAGE SIGNATURE
# ============================================================

def image_signature(path):
    try:
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(
                image
            ).convert("RGB")

            image.thumbnail(
                (96, 96)
            )

            digest = hashlib.sha256(
                image.tobytes()
            )

            return digest.hexdigest()

    except Exception:
        return ""


# ============================================================
# STORY IMAGE REFERENCES
# ============================================================

def extract_story_image_values(story):
    values = []

    # Primary list.
    images = story.get(
        "images",
        [],
    )

    if isinstance(
        images,
        list,
    ):
        values.extend(images)

    elif images:
        values.append(images)

    # Secondary fields.
    for field in [
        "image",
        "image_path",
        "local_image",
        "photo",
        "photo_path",
    ]:
        value = story.get(field)

        if value:
            values.append(value)

    # Remove duplicate textual references while
    # preserving order.
    output = []
    seen = set()

    for value in values:
        normalized = normalize_image_reference(
            value
        )

        if not normalized:
            continue

        if normalized in seen:
            continue

        seen.add(normalized)
        output.append(value)

    return output


# ============================================================
# COLLECT EXACT STORY PHOTOS
# ============================================================

def collect_story_images(story):
    values = extract_story_image_values(
        story
    )

    log(
        f"Explicit story image references: {len(values)}"
    )

    images = []
    seen_paths = set()
    seen_signatures = set()

    for value in values:
        log(
            f"IMAGE REFERENCE: {value}"
        )

        path = resolve_image_path(
            value
        )

        if path is None:
            log(
                f"IMAGE NOT RESOLVED: {value}"
            )
            continue

        log(
            f"IMAGE RESOLVED: {path}"
        )

        # First attempt direct validation.
        valid = image_is_valid(
            path,
            normalize=False,
        )

        if not valid:
            log(
                f"IMAGE REQUIRES NORMALIZATION: {path}"
            )

            normalized = normalize_image_file(
                path
            )

            if normalized is None:
                log(
                    f"IMAGE NORMALIZATION FAILED: {path}"
                )
                continue

            path = normalized

        # Final validation.
        if not image_is_valid(
            path,
            normalize=False,
        ):
            log(
                f"IMAGE FAILED FINAL VALIDATION: {path}"
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
            log(
                f"DUPLICATE PHOTO SKIPPED: {path}"
            )
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

        log(
            f"REAL PHOTO ACCEPTED: {path}"
        )

        if len(images) >= MAX_IMAGES:
            break

    log(
        f"Validated selected-story photographs: {len(images)}"
    )

    for index, path in enumerate(
        images,
        start=1,
    ):
        log(
            f"PHOTO {index}: {path}"
        )

    return images


# ============================================================
# STORY SCORE
# ============================================================

def story_score(story):
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
        "SECURITY": 14,
        "HEALTH": 13,
        "EDUCATION": 13,
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
# SELECT ONE STORY
# ============================================================

def select_story(story_payload):
    if isinstance(
        story_payload,
        dict,
    ):
        stories = story_payload.get(
            "stories",
            [],
        )

        if (
            not stories
            and story_payload.get("title")
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
        f"Stories available: {len(stories)}"
    )

    candidates = []

    for story in stories:
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
                f"Rejected forbidden story: {title}"
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
                f"Rejected forbidden source: {source_name}"
            )
            continue

        images = collect_story_images(
            story
        )

        if not images:
            log(
                f"Rejected story with no valid photographs: {title}"
            )
            continue

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

        selected["_score"] = story_score(
            selected
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
            "No valid real article photographs found"
        )

    candidates.sort(
        key=lambda item: item.get(
            "_score",
            0,
        ),
        reverse=True,
    )

    selected = candidates[0]

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
            selected.get("title")
        )
    )

    log(
        f"County: {clean_text(selected.get('county'))}"
    )

    log(
        f"Category: {clean_text(selected.get('category'))}"
    )

    log(
        f"Photos: {len(selected.get('images', []))}"
    )

    return selected


# ============================================================
# NARRATION
# ============================================================

def build_narration_text(story):
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
            f"The latest development is from {county}."
        )

    if category:
        pieces.append(
            f"This is a {category.lower()} update from Rift Valley Watch."
        )

    if source_name:
        pieces.append(
            f"Source: {source_name}."
        )

    narration = clean_text(
        " ".join(pieces)
    )

    if not narration:
        raise RuntimeError(
            "Narration text is empty."
        )

    if contains_forbidden_text(
        narration
    ):
        raise RuntimeError(
            "Selected narration contains a forbidden person/topic."
        )

    return narration


def generate_narration(story):
    narration = build_narration_text(
        story
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
            str(NARRATION_FILE)
        )

    except Exception as exc:
        raise RuntimeError(
            f"Text-to-speech generation failed: {exc}"
        )

    if not NARRATION_FILE.exists():
        raise RuntimeError(
            "Narration file was not created."
        )

    if NARRATION_FILE.stat().st_size < MIN_AUDIO_BYTES:
        raise RuntimeError(
            "Narration file is too small."
        )

    log(
        f"Narration created: {NARRATION_FILE}"
    )

    return narration


# ============================================================
# SELECTED STORY
# ============================================================

def create_selected_story(story):
    save_json(
        SELECTED_STORY_FILE,
        story,
    )

    log(
        f"Selected story written: {SELECTED_STORY_FILE}"
    )


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
        f"Selected script written: {SELECTED_SCRIPT_FILE}"
    )


# ============================================================
# VERIFY SELECTED DATA
# ============================================================

def validate_selected_data():
    log()
    log(
        "=" * 72
    )

    log(
        "VERIFYING SELECTED REAL STORY IMAGES"
    )

    log(
        "=" * 72
    )

    selected_story = load_json(
        SELECTED_STORY_FILE
    )

    references = extract_story_image_values(
        selected_story
    )

    if not references:
        raise RuntimeError(
            "selected_story.json contains no image references."
        )

    valid = []

    seen = set()

    for reference in references:
        log(
            f"VERIFY IMAGE REFERENCE: {reference}"
        )

        path = resolve_image_path(
            reference
        )

        if path is None:
            log(
                f"VERIFY IMAGE NOT FOUND: {reference}"
            )
            continue

        if not image_is_valid(
            path,
            normalize=False,
        ):
            log(
                f"VERIFY IMAGE NORMALIZING: {path}"
            )

            normalized = normalize_image_file(
                path
            )

            if normalized is None:
                log(
                    f"VERIFY IMAGE FAILED: {path}"
                )
                continue

            path = normalized

        if not image_is_valid(
            path,
            normalize=False,
        ):
            log(
                f"VERIFY IMAGE INVALID: {path}"
            )
            continue

        resolved = str(
            path.resolve()
        )

        if resolved in seen:
            continue

        seen.add(
            resolved
        )

        valid.append(
            path
        )

        log(
            f"VERIFY IMAGE PASSED: {path}"
        )

        if len(valid) >= MAX_IMAGES:
            break

    if not valid:
        raise RuntimeError(
            "No real story images found."
        )

    # Rewrite selected story with the actual resolved
    # repository-relative JPEG paths.
    selected_story["images"] = [
        str(
            path.relative_to(
                BASE_DIR
            )
        )
        for path in valid
    ]

    selected_story["image"] = (
        selected_story["images"][0]
    )

    selected_story["image_path"] = (
        selected_story["images"][0]
    )

    save_json(
        SELECTED_STORY_FILE,
        selected_story,
    )

    log(
        f"Real story images found: {len(valid)}"
    )

    for index, path in enumerate(
        valid,
        start=1,
    ):
        log(
            f"REAL STORY IMAGE {index}: {path}"
        )

    return selected_story, valid


# ============================================================
# RUN NEWS ENGINE
# ============================================================

def run_news_engine():
    if not NEWS_ENGINE.exists():
        raise RuntimeError(
            f"News engine not found: {NEWS_ENGINE}"
        )

    log()
    log(
        "=" * 72
    )

    log(
        "RUNNING REAL-TIME NEWS ENGINE"
    )

    log(
        "=" * 72
    )

    result = subprocess.run(
        [
            sys.executable,
            str(NEWS_ENGINE),
        ],
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    output = result.stdout or ""

    if output:
        print(
            output,
            flush=True,
        )

    if result.returncode != 0:
        raise RuntimeError(
            "News engine failed with "
            f"exit code {result.returncode}.\n\n"
            "FULL NEWS ENGINE OUTPUT:\n"
            f"{output[-20000:]}"
        )

    if not STORY_FILE.exists():
        raise RuntimeError(
            "News engine completed but data/story.json was not created."
        )

    if STORY_FILE.stat().st_size == 0:
        raise RuntimeError(
            "News engine created an empty data/story.json."
        )

    log(
        "News engine completed successfully."
    )


# ============================================================
# RUN VIDEO RENDERER
# ============================================================

def run_renderer():
    if not RENDERER_FILE.exists():
        raise RuntimeError(
            f"Video renderer not found: {RENDERER_FILE}"
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

    result = subprocess.run(
        [
            sys.executable,
            str(RENDERER_FILE),
        ],
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    output = result.stdout or ""

    if output:
        print(
            output,
            flush=True,
        )

    if result.returncode != 0:
        raise RuntimeError(
            "Video renderer failed with "
            f"exit code {result.returncode}.\n\n"
            "FULL VIDEO RENDERER OUTPUT:\n"
            f"{output[-25000:]}"
        )

    log(
        "Video renderer completed."
    )


# ============================================================
# FFPROBE
# ============================================================

def run_ffprobe(path):
    ffprobe = shutil.which(
        "ffprobe"
    )

    if not ffprobe:
        log(
            "ffprobe not found; skipping detailed MP4 probe."
        )
        return True

    result = subprocess.run(
        [
            ffprobe,
            "-v",
            "error",
            "-show_entries",
            "format=duration,size",
            "-of",
            "default=noprint_wrappers=1",
            str(path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    output = result.stdout or ""

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
# FINAL VIDEO VALIDATION
# ============================================================

def validate_final_video():
    log()
    log(
        "Validating final MP4..."
    )

    if not FINAL_VIDEO.exists():
        raise RuntimeError(
            f"Final MP4 was not created: {FINAL_VIDEO}"
        )

    size = FINAL_VIDEO.stat().st_size

    log(
        f"Final MP4 size: {size} bytes"
    )

    if size < MIN_VIDEO_BYTES:
        raise RuntimeError(
            "Final MP4 is too small."
        )

    if not run_ffprobe(
        FINAL_VIDEO
    ):
        raise RuntimeError(
            "Final MP4 failed ffprobe validation."
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
        "RIFT VALLEY WATCH GENERATOR COMPLETED SUCCESSFULLY"
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
            story.get("title")
        )
    )

    print()

    print(
        "COUNTY: "
        + clean_text(
            story.get("county")
        )
    )

    print(
        "CATEGORY: "
        + clean_text(
            story.get("category")
        )
    )

    print(
        "SOURCE: "
        + clean_text(
            source.get("name")
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
        # 1. Fetch fresh news and photographs.
        # ----------------------------------------------------

        run_news_engine()

        # ----------------------------------------------------
        # 2. Load story data.
        # ----------------------------------------------------

        story_payload = load_json(
            STORY_FILE
        )

        # ----------------------------------------------------
        # 3. Select ONE story with real photographs.
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
        # 5. Write selected files.
        # ----------------------------------------------------

        create_selected_story(
            selected_story
        )

        create_selected_script(
            selected_story,
            narration,
        )

        # ----------------------------------------------------
        # 6. Re-resolve and normalize exact selected photos.
        # ----------------------------------------------------

        selected_story, images = (
            validate_selected_data()
        )

        # ----------------------------------------------------
        # 7. Rebuild selected script so it contains the
        #    final normalized photo paths.
        # ----------------------------------------------------

        create_selected_script(
            selected_story,
            narration,
        )

        # ----------------------------------------------------
        # 8. Render final video.
        # ----------------------------------------------------

        run_renderer()

        # ----------------------------------------------------
        # 9. Validate final MP4.
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
            f"Elapsed time: {elapsed:.1f} seconds"
        )

        return 0

    except KeyboardInterrupt:
        print()
        print(
            "RIFT VALLEY WATCH GENERATOR INTERRUPTED"
        )
        return 130

    except Exception as exc:
        print()
        print(
            "=" * 72
        )

        print(
            "RIFT VALLEY WATCH VIDEO GENERATOR FAILED"
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
