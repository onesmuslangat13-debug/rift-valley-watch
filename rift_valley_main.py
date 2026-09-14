# ============================================================
# RIFT VALLEY WATCH
# MAIN ORCHESTRATOR
# VERSION: RVW_MAIN_V36_ROBUST_REAL_PHOTO_RECOVERY
#
# PURPOSE
# - Run the real-time news engine
# - Read data/story.json
# - Select ONE story
# - Recover photographs belonging to that story
# - Support multiple news-engine image schemas
# - Normalize valid source images
# - Reject fake / generic / unrelated visuals
# - Generate narration
# - Write selected_story.json / selected_script.json
# - Run the video renderer
# - Validate the final MP4
#
# IMPORTANT
# - NEVER downloads Google images
# - NEVER searches the web for replacement visuals
# - NEVER mixes unrelated story photographs
# - Only uses photographs already produced by the news engine
# - Handles .jpg files containing PNG/WebP/AVIF image bytes
# - Handles Windows/Linux path separators
# - Handles escaped paths
# - Handles multiple image field names
# - Supports multiple story JSON schemas
# ============================================================

from pathlib import Path
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

# Search depth for source assets.
MAX_SOURCE_SCAN_FILES = 5000

# Filename scoring thresholds.
TITLE_MATCH_MIN_SCORE = 2

# Allowed image formats.
SUPPORTED_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
    ".avif",
    ".bmp",
    ".tif",
    ".tiff",
}


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
    "thumbnail placeholder",
    "no image",
    "no_image",
    "missing image",
    "missing_image",
]


# ============================================================
# COMMON IMAGE FIELD NAMES
#
# The news engine may use any of these.
# ============================================================

IMAGE_FIELDS = [
    "images",
    "image",
    "image_path",
    "image_paths",
    "image_file",
    "image_files",
    "image_url",
    "image_urls",
    "images_url",
    "images_urls",
    "local_image",
    "local_images",
    "local_image_path",
    "local_image_paths",
    "photo",
    "photos",
    "photo_path",
    "photo_paths",
    "photo_url",
    "photo_urls",
    "article_image",
    "article_images",
    "article_image_path",
    "article_image_paths",
    "article_photo",
    "article_photos",
    "article_photo_path",
    "article_photo_paths",
    "media",
    "media_images",
    "assets",
    "visuals",
]


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

    # IMPORTANT:
    # Source photographs are NEVER deleted here.
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


def normalize_search_text(value):
    text = clean_text(value).lower()

    text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text,
    )

    return re.sub(
        r"\s+",
        " ",
        text,
    ).strip()


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
# IMAGE REFERENCE EXTRACTION
# ============================================================

def extract_strings_from_image_value(value):
    """
    Recursively extracts possible local image references
    from strings, lists and dictionaries.

    Supports structures such as:

    "photo.jpg"

    ["photo1.jpg", "photo2.jpg"]

    {
        "path": "photo.jpg",
        "url": "...",
        "local_path": "photo.jpg"
    }

    [
        {"path": "photo1.jpg"},
        {"local_path": "photo2.webp"}
    ]
    """

    output = []

    if value is None:
        return output

    if isinstance(value, str):
        cleaned = normalize_image_reference(
            value
        )

        if cleaned:
            output.append(
                cleaned
            )

        return output

    if isinstance(value, Path):
        output.append(
            str(value)
        )
        return output

    if isinstance(value, list):
        for item in value:
            output.extend(
                extract_strings_from_image_value(
                    item
                )
            )

        return output

    if isinstance(value, tuple):
        for item in value:
            output.extend(
                extract_strings_from_image_value(
                    item
                )
            )

        return output

    if isinstance(value, dict):

        preferred_keys = [
            "local_path",
            "local_file",
            "local_image",
            "path",
            "file",
            "filename",
            "file_path",
            "image_path",
            "photo_path",
            "url",
            "src",
            "image",
            "photo",
        ]

        for key in preferred_keys:
            if key in value:
                output.extend(
                    extract_strings_from_image_value(
                        value.get(key)
                    )
                )

        return output

    return output


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
            or value.get("filename")
            or value.get("file_path")
            or value.get("image_path")
            or value.get("photo_path")
            or value.get("image")
            or value.get("photo")
            or ""
        )

    if not isinstance(value, str):
        value = str(value)

    value = value.strip()

    # Remove JSON / Python escaped underscore.
    value = value.replace(
        r"\_",
        "_",
    )

    # Handle escaped path separators.
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

    # Remove file:// prefix if present.
    if value.lower().startswith(
        "file://"
    ):
        value = value[7:]

    return value.strip()


# ============================================================
# STORY IMAGE REFERENCES
# ============================================================

def extract_story_image_values(story):
    """
    Extract all image references that are explicitly attached
    to the selected story.

    This is deliberately broad because different versions of
    news_engine.py may use different field names.
    """

    values = []

    if not isinstance(
        story,
        dict,
    ):
        return values

    # --------------------------------------------------------
    # 1. Standard image fields.
    # --------------------------------------------------------

    for field in IMAGE_FIELDS:
        if field not in story:
            continue

        value = story.get(field)

        extracted = extract_strings_from_image_value(
            value
        )

        values.extend(
            extracted
        )

    # --------------------------------------------------------
    # 2. Nested media/image structures.
    # --------------------------------------------------------

    for container_name in [
        "media",
        "article",
        "content",
        "visual",
        "visuals",
        "asset",
        "assets",
    ]:
        container = story.get(
            container_name
        )

        if not isinstance(
            container,
            dict,
        ):
            continue

        for field in IMAGE_FIELDS:
            if field not in container:
                continue

            values.extend(
                extract_strings_from_image_value(
                    container.get(field)
                )
            )

    # --------------------------------------------------------
    # 3. De-duplicate textual references.
    # --------------------------------------------------------

    output = []
    seen = set()

    for value in values:
        normalized = normalize_image_reference(
            value
        )

        if not normalized:
            continue

        key = normalized.lower()

        if key in seen:
            continue

        seen.add(key)

        output.append(
            normalized
        )

    return output


# ============================================================
# STORY IDENTIFIERS
# ============================================================

def story_identifiers(story):
    identifiers = []

    if not isinstance(
        story,
        dict,
    ):
        return identifiers

    for field in [
        "id",
        "story_id",
        "article_id",
        "news_id",
        "reference",
        "slug",
        "guid",
        "hash",
        "source_id",
    ]:
        value = clean_text(
            story.get(field)
        )

        if value:
            identifiers.append(
                value
            )

    source = story.get(
        "source",
        {},
    )

    if isinstance(
        source,
        dict,
    ):
        for field in [
            "id",
            "story_id",
            "article_id",
        ]:
            value = clean_text(
                source.get(field)
            )

            if value:
                identifiers.append(
                    value
                )

    return identifiers


# ============================================================
# STORY TITLE TOKENS
# ============================================================

def title_tokens(story):
    title = normalize_search_text(
        story.get("title")
    )

    if not title:
        return []

    words = title.split()

    # Ignore very short generic words.
    ignored = {
        "the",
        "and",
        "for",
        "from",
        "with",
        "this",
        "that",
        "into",
        "over",
        "after",
        "before",
        "says",
        "said",
        "has",
        "have",
        "will",
        "are",
        "was",
        "were",
        "its",
        "his",
        "her",
        "their",
        "about",
        "latest",
        "update",
        "news",
    }

    return [
        word
        for word in words
        if len(word) >= 4
        and word not in ignored
    ]


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
    # 1. Absolute path.
    # --------------------------------------------------------

    candidate = Path(
        cleaned
    )

    if candidate.is_absolute():
        if candidate.exists():
            return candidate.resolve()

    # --------------------------------------------------------
    # 2. Repository-relative path.
    # --------------------------------------------------------

    candidate = (
        BASE_DIR / cleaned
    )

    if candidate.exists():
        return candidate.resolve()

    # --------------------------------------------------------
    # 3. Source-relative path.
    # --------------------------------------------------------

    candidate = (
        SOURCE_DIR / cleaned
    )

    if candidate.exists():
        return candidate.resolve()

    # --------------------------------------------------------
    # 4. Filename only.
    # --------------------------------------------------------

    filename = Path(
        cleaned
    ).name

    if filename:
        candidate = (
            SOURCE_DIR / filename
        )

        if candidate.exists():
            return candidate.resolve()

    # --------------------------------------------------------
    # 5. Recursive exact filename search.
    # --------------------------------------------------------

    if SOURCE_DIR.exists() and filename:
        try:
            for match in SOURCE_DIR.rglob(
                filename
            ):
                if match.is_file():
                    return match.resolve()
        except Exception:
            pass

    # --------------------------------------------------------
    # 6. Same stem with another extension.
    # --------------------------------------------------------

    stem = Path(
        filename
    ).stem

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
# SOURCE DIRECTORY DISCOVERY
# ============================================================

def discover_source_files():
    """
    Returns local image files from assets/source.

    This NEVER downloads anything.
    """

    files = []

    if not SOURCE_DIR.exists():
        return files

    try:
        for path in SOURCE_DIR.rglob("*"):
            if not path.is_file():
                continue

            if path.suffix.lower() not in (
                SUPPORTED_IMAGE_EXTENSIONS
            ):
                continue

            files.append(
                path.resolve()
            )

            if len(files) >= MAX_SOURCE_SCAN_FILES:
                break

    except Exception as exc:
        log(
            f"Source directory scan failed: {exc}"
        )

    return files


# ============================================================
# FILENAME STORY MATCH SCORE
# ============================================================

def filename_story_match_score(
    path,
    story,
):
    """
    Estimates whether a local source filename belongs to the
    story.

    This is used only as a recovery mechanism when the news
    engine did not correctly place the local image reference
    into the JSON.

    Strong identifiers beat title-token matches.
    """

    name = normalize_search_text(
        path.stem
    )

    if not name:
        return 0

    score = 0

    # --------------------------------------------------------
    # Story identifiers.
    # --------------------------------------------------------

    for identifier in story_identifiers(
        story
    ):
        normalized_id = normalize_search_text(
            identifier
        )

        if not normalized_id:
            continue

        compact_id = re.sub(
            r"[^a-z0-9]+",
            "",
            normalized_id,
        )

        compact_name = re.sub(
            r"[^a-z0-9]+",
            "",
            name,
        )

        if (
            normalized_id in name
            or (
                compact_id
                and compact_id in compact_name
            )
        ):
            score += 100

    # --------------------------------------------------------
    # Title tokens.
    # --------------------------------------------------------

    tokens = title_tokens(
        story
    )

    for token in tokens:
        if token in name:
            score += 1

    # --------------------------------------------------------
    # County.
    # --------------------------------------------------------

    county = normalize_search_text(
        story.get("county")
    )

    if county and county in name:
        score += 2

    return score


# ============================================================
# RECOVER STORY PHOTOS FROM LOCAL SOURCE DIRECTORY
# ============================================================

def recover_story_images_from_source_directory(
    story,
    existing_paths,
):
    """
    Attempts local recovery when story.json does not expose
    all downloaded article photographs.

    IMPORTANT:
    This does not use Google.
    This does not use the internet.
    It only examines assets/source.
    """

    recovered = []

    existing_resolved = {
        str(
            Path(path).resolve()
        )
        for path in existing_paths
        if path is not None
    }

    files = discover_source_files()

    if not files:
        log(
            "SOURCE RECOVERY: no local image files found."
        )
        return recovered

    scored = []

    for path in files:

        if str(path) in existing_resolved:
            continue

        if contains_forbidden_visual_text(
            path.name
        ):
            continue

        score = filename_story_match_score(
            path,
            story,
        )

        if score < TITLE_MATCH_MIN_SCORE:
            continue

        scored.append(
            (
                score,
                path,
            )
        )

    scored.sort(
        key=lambda item: (
            item[0],
            item[1].stat().st_mtime
            if item[1].exists()
            else 0,
        ),
        reverse=True,
    )

    for score, path in scored:
        log(
            f"SOURCE RECOVERY CANDIDATE: "
            f"score={score} | {path}"
        )

        recovered.append(
            path
        )

        if len(recovered) >= MAX_IMAGES:
            break

    log(
        f"SOURCE RECOVERY FOUND: {len(recovered)}"
    )

    return recovered


# ============================================================
# IMAGE NORMALIZATION
# ============================================================

def normalize_image_file(path):
    """
    Opens the actual image bytes.

    If a valid image has been saved with the wrong extension,
    convert it to a genuine JPEG.

    The original source image is retained unless it has a JPG
    extension. For non-JPG images a normalized JPEG is created
    beside the original.
    """

    if path is None:
        return None

    path = Path(
        path
    )

    if not path.exists():
        return None

    temporary = None

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

            temporary = path.with_name(
                path.name
                + ".normalized.jpg"
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

        # If original is already JPEG, replace it with a
        # genuine JPEG so the extension and bytes agree.
        if path.suffix.lower() in {
            ".jpg",
            ".jpeg",
        }:
            temporary.replace(
                path
            )

            return path.resolve()

        # Non-JPEG source:
        # create a stable normalized JPEG.
        normalized = path.with_name(
            path.stem
            + "_normalized.jpg"
        )

        if normalized.exists():
            try:
                normalized.unlink()
            except Exception:
                pass

        temporary.replace(
            normalized
        )

        return normalized.resolve()

    except Exception as exc:
        log(
            f"IMAGE NORMALIZATION FAILED: "
            f"{path} | {exc}"
        )

        if temporary is not None:
            try:
                temporary.unlink(
                    missing_ok=True
                )
            except Exception:
                pass

        return None


# ============================================================
# IMAGE VALIDATION
# ============================================================

def image_is_valid(
    path,
    normalize=False,
):
    if path is None:
        return False

    path = Path(
        path
    )

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

        with Image.open(path) as image:

            width, height = image.size

            if width < MIN_IMAGE_WIDTH:
                return False

            if height < MIN_IMAGE_HEIGHT:
                return False

            # Force actual byte decoding.
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
                and normalized.stat().st_size
                >= MIN_IMAGE_BYTES
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
# IMAGE QUALITY CHECK
# ============================================================

def image_quality_reason(path):
    """
    Returns a human-readable rejection reason.
    Empty string means acceptable.
    """

    if path is None:
        return "path is None"

    path = Path(
        path
    )

    if not path.exists():
        return "file does not exist"

    if not path.is_file():
        return "not a file"

    if path.stat().st_size < MIN_IMAGE_BYTES:
        return (
            f"file too small "
            f"({path.stat().st_size} bytes)"
        )

    if contains_forbidden_visual_text(
        path.name
    ):
        return "filename contains forbidden visual term"

    try:
        with Image.open(path) as image:

            width, height = image.size

            if width < MIN_IMAGE_WIDTH:
                return (
                    f"width too small "
                    f"({width}px)"
                )

            if height < MIN_IMAGE_HEIGHT:
                return (
                    f"height too small "
                    f"({height}px)"
                )

            image.load()

            return ""

    except Exception as exc:
        return (
            f"PIL could not decode image: {exc}"
        )


# ============================================================
# ACCEPT / NORMALIZE ONE IMAGE
# ============================================================

def accept_image_candidate(
    path,
    label="",
):
    if path is None:
        return None

    path = Path(
        path
    )

    reason = image_quality_reason(
        path
    )

    if not reason:
        log(
            f"REAL PHOTO VALID: "
            f"{label} | {path}"
        )
        return path.resolve()

    log(
        f"PHOTO CHECK FAILED: "
        f"{label} | {path} | {reason}"
    )

    # Attempt normalization for files whose actual bytes are
    # valid but whose extension/container may be problematic.
    normalized = normalize_image_file(
        path
    )

    if normalized is None:
        return None

    reason_after = image_quality_reason(
        normalized
    )

    if reason_after:
        log(
            f"PHOTO NORMALIZATION INVALID: "
            f"{normalized} | {reason_after}"
        )
        return None

    log(
        f"REAL PHOTO ACCEPTED AFTER NORMALIZATION: "
        f"{normalized}"
    )

    return normalized.resolve()


# ============================================================
# COLLECT EXACT STORY PHOTOS
# ============================================================

def collect_story_images(story):
    """
    First uses explicit references in story.json.

    Then, only if necessary, attempts local filename recovery
    from assets/source.

    No external image search occurs here.
    """

    values = extract_story_image_values(
        story
    )

    log(
        f"Explicit story image references: {len(values)}"
    )

    images = []
    seen_paths = set()
    seen_signatures = set()

    # --------------------------------------------------------
    # PASS 1:
    # Explicit image references.
    # --------------------------------------------------------

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

        accepted = accept_image_candidate(
            path,
            label="explicit story reference",
        )

        if accepted is None:
            continue

        resolved = str(
            accepted.resolve()
        )

        if resolved in seen_paths:
            continue

        signature = image_signature(
            accepted
        )

        if (
            signature
            and signature in seen_signatures
        ):
            log(
                f"DUPLICATE PHOTO SKIPPED: "
                f"{accepted}"
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
            accepted
        )

        log(
            f"REAL PHOTO ACCEPTED: {accepted}"
        )

        if len(images) >= MAX_IMAGES:
            break

    # --------------------------------------------------------
    # PASS 2:
    # Local source recovery.
    #
    # Only used when explicit references yielded fewer than
    # MAX_IMAGES.
    # --------------------------------------------------------

    if len(images) < MAX_IMAGES:

        recovered = (
            recover_story_images_from_source_directory(
                story,
                images,
            )
        )

        for candidate in recovered:

            accepted = accept_image_candidate(
                candidate,
                label="local source recovery",
            )

            if accepted is None:
                continue

            resolved = str(
                accepted.resolve()
            )

            if resolved in seen_paths:
                continue

            signature = image_signature(
                accepted
            )

            if (
                signature
                and signature in seen_signatures
            ):
                log(
                    f"DUPLICATE RECOVERED PHOTO SKIPPED: "
                    f"{accepted}"
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
                accepted
            )

            log(
                f"RECOVERED STORY PHOTO ACCEPTED: "
                f"{accepted}"
            )

            if len(images) >= MAX_IMAGES:
                break

    log(
        f"Validated selected-story photographs: "
        f"{len(images)}"
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
# STORY PAYLOAD NORMALIZATION
# ============================================================

def normalize_story_payload(payload):
    """
    Supports:

    {
        "stories": [...]
    }

    {
        "story": {...}
    }

    [...]

    {...story...}
    """

    if isinstance(
        payload,
        list,
    ):
        return [
            item
            for item in payload
            if isinstance(
                item,
                dict,
            )
        ]

    if isinstance(
        payload,
        dict,
    ):

        stories = payload.get(
            "stories"
        )

        if isinstance(
            stories,
            list,
        ):
            return [
                item
                for item in stories
                if isinstance(
                    item,
                    dict,
                )
            ]

        story = payload.get(
            "story"
        )

        if isinstance(
            story,
            dict,
        ):
            return [
                story
            ]

        if payload.get(
            "title"
        ):
            return [
                payload
            ]

    return []


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

    images = extract_story_image_values(
        story
    )

    score += min(
        len(images) * 12,
        60,
    )

    return score


# ============================================================
# SELECT ONE STORY
# ============================================================

def select_story(story_payload):

    stories = normalize_story_payload(
        story_payload
    )

    log(
        f"Stories available: {len(stories)}"
    )

    candidates = []

    rejected_no_photo = 0
    rejected_forbidden = 0
    rejected_invalid = 0

    for index, story in enumerate(
        stories,
        start=1,
    ):

        title = clean_text(
            story.get("title")
        )

        if not title:
            log(
                f"Story {index}: rejected because title is empty."
            )
            continue

        log()
        log(
            f"========== STORY CANDIDATE {index} =========="
        )

        log(
            f"TITLE: {title}"
        )

        if contains_forbidden_text(
            title
        ):
            rejected_forbidden += 1

            log(
                "REJECTED: forbidden person/topic."
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
            rejected_forbidden += 1

            log(
                f"REJECTED: forbidden source: {source_name}"
            )

            continue

        log(
            f"SOURCE: {source_name or 'unknown'}"
        )

        explicit_values = extract_story_image_values(
            story
        )

        log(
            f"Image references exposed by story: "
            f"{len(explicit_values)}"
        )

        images = collect_story_images(
            story
        )

        if not images:
            rejected_no_photo += 1

            log(
                "REJECTED: no valid article photograph could "
                "be recovered for this story."
            )

            continue

        selected = dict(
            story
        )

        # ----------------------------------------------------
        # Convert to repository-relative paths.
        # ----------------------------------------------------

        relative_images = []

        for path in images:
            try:
                relative = path.relative_to(
                    BASE_DIR
                )

                relative_images.append(
                    str(relative).replace(
                        "\\",
                        "/",
                    )
                )

            except ValueError:
                log(
                    f"REJECTED: image outside repository: "
                    f"{path}"
                )

        if not relative_images:
            rejected_invalid += 1

            log(
                "REJECTED: no repository-relative photographs."
            )

            continue

        selected["images"] = (
            relative_images
        )

        selected["image"] = (
            relative_images[0]
        )

        selected["image_path"] = (
            relative_images[0]
        )

        selected["_score"] = (
            story_score(
                selected
            )
            + len(relative_images) * 8
        )

        candidates.append(
            selected
        )

        log(
            f"Candidate accepted: "
            f"{title} | "
            f"photos={len(relative_images)} | "
            f"score={selected['_score']}"
        )

    log()
    log(
        "============================================================"
    )

    log(
        f"STORY SELECTION RESULTS | "
        f"accepted={len(candidates)} | "
        f"no_photo={rejected_no_photo} | "
        f"forbidden={rejected_forbidden} | "
        f"invalid={rejected_invalid}"
    )

    log(
        "============================================================"
    )

    if not candidates:
        raise RuntimeError(
            "No valid Rift Valley story with a real article "
            "photograph could be produced."
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
        f"County: "
        f"{clean_text(selected.get('county'))}"
    )

    log(
        f"Category: "
        f"{clean_text(selected.get('category'))}"
    )

    log(
        f"Photos: "
        f"{len(selected.get('images', []))}"
    )

    for index, image in enumerate(
        selected.get(
            "images",
            [],
        ),
        start=1,
    ):
        log(
            f"Selected photo {index}: {image}"
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
            str(
                NARRATION_FILE
            )
        )

    except Exception as exc:
        raise RuntimeError(
            f"Text-to-speech generation failed: {exc}"
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
        f"Selected story written: "
        f"{SELECTED_STORY_FILE}"
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
        ).replace(
            "\\",
            "/",
        ),
        "images": story.get(
            "images",
            [],
        ),
        "image": story.get(
            "image",
            "",
        ),
        "image_path": story.get(
            "image_path",
            "",
        ),
    }

    save_json(
        SELECTED_SCRIPT_FILE,
        script,
    )

    log(
        f"Selected script written: "
        f"{SELECTED_SCRIPT_FILE}"
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

    log(
        f"Selected image references: "
        f"{len(references)}"
    )

    valid = []

    seen = set()
    signatures = set()

    # --------------------------------------------------------
    # First validate references in selected_story.json.
    # --------------------------------------------------------

    for reference in references:

        log(
            f"VERIFY IMAGE REFERENCE: {reference}"
        )

        path = resolve_image_path(
            reference
        )

        if path is None:

            log(
                f"VERIFY IMAGE NOT FOUND: "
                f"{reference}"
            )

            continue

        log(
            f"VERIFY IMAGE RESOLVED: "
            f"{path}"
        )

        accepted = accept_image_candidate(
            path,
            label="selected_story.json",
        )

        if accepted is None:
            log(
                f"VERIFY IMAGE FAILED: "
                f"{path}"
            )
            continue

        resolved = str(
            accepted.resolve()
        )

        if resolved in seen:
            continue

        signature = image_signature(
            accepted
        )

        if (
            signature
            and signature in signatures
        ):
            log(
                f"VERIFY DUPLICATE IMAGE SKIPPED: "
                f"{accepted}"
            )
            continue

        seen.add(
            resolved
        )

        if signature:
            signatures.add(
                signature
            )

        valid.append(
            accepted
        )

        log(
            f"VERIFY IMAGE PASSED: "
            f"{accepted}"
        )

        if len(valid) >= MAX_IMAGES:
            break

    # --------------------------------------------------------
    # Emergency local recovery.
    #
    # If selected_story.json references are broken, recover
    # using the selected story identity.
    # --------------------------------------------------------

    if not valid:

        log()
        log(
            "SELECTED JSON REFERENCES DID NOT PRODUCE "
            "A VALID IMAGE."
        )

        log(
            "Attempting local source recovery..."
        )

        recovered = (
            recover_story_images_from_source_directory(
                selected_story,
                [],
            )
        )

        for candidate in recovered:

            accepted = accept_image_candidate(
                candidate,
                label="final source recovery",
            )

            if accepted is None:
                continue

            resolved = str(
                accepted.resolve()
            )

            if resolved in seen:
                continue

            signature = image_signature(
                accepted
            )

            if (
                signature
                and signature in signatures
            ):
                continue

            seen.add(
                resolved
            )

            if signature:
                signatures.add(
                    signature
                )

            valid.append(
                accepted
            )

            if len(valid) >= MAX_IMAGES:
                break

    if not valid:
        raise RuntimeError(
            "No real story images found."
        )

    # --------------------------------------------------------
    # Rewrite selected story with final normalized paths.
    # --------------------------------------------------------

    relative_images = []

    for path in valid:

        try:
            relative = path.relative_to(
                BASE_DIR
            )

        except ValueError:
            raise RuntimeError(
                f"Selected image is outside repository: "
                f"{path}"
            )

        relative_images.append(
            str(relative).replace(
                "\\",
                "/",
            )
        )

    selected_story["images"] = (
        relative_images
    )

    selected_story["image"] = (
        relative_images[0]
    )

    selected_story["image_path"] = (
        relative_images[0]
    )

    save_json(
        SELECTED_STORY_FILE,
        selected_story,
    )

    log(
        f"Real story images found: "
        f"{len(valid)}"
    )

    for index, path in enumerate(
        valid,
        start=1,
    ):
        log(
            f"REAL STORY IMAGE {index}: "
            f"{path}"
        )

    return (
        selected_story,
        valid,
    )


# ============================================================
# RUN NEWS ENGINE
# ============================================================

def run_news_engine():

    if not NEWS_ENGINE.exists():
        raise RuntimeError(
            f"News engine not found: "
            f"{NEWS_ENGINE}"
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
            f"{output[-30000:]}"
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
# RUN VIDEO RENDERER
# ============================================================

def run_renderer():

    if not RENDERER_FILE.exists():
        raise RuntimeError(
            f"Video renderer not found: "
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

    result = subprocess.run(
        [
            sys.executable,
            str(RENDERER_FILE),
        ],
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
            f"{output[-30000:]}"
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
            "ffprobe not found; "
            "skipping detailed MP4 probe."
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
            f"Final MP4 was not created: "
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
        # 6. Re-resolve / normalize exact selected photos.
        # ----------------------------------------------------

        (
            selected_story,
            images,
        ) = validate_selected_data()

        # ----------------------------------------------------
        # 7. Rebuild selected script so it contains final
        #    normalized photo paths.
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
