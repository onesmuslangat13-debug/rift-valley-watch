# ============================================================
# RIFT VALLEY WATCH
# VIDEO GENERATOR
#
# VERSION: RIFT_VALLEY_WATCH_GENERATOR_CLEAN_V2
#
# RULES:
# - NO SOURCE/PUBLISHER ON SCREEN
# - NO SOURCE/PUBLISHER IN NARRATION
# - NO [PHOTOS]
# - NO / PCS OR PHOTO-CREDIT ARTIFACTS
# - NO "VERIFIED REPORT"
# - NO FAKE PHOTO COUNTER
# - ONE REAL IMAGE = ONE CONTINUOUS KEN BURNS SCENE
# - 2-5 REAL DISTINCT IMAGES = REAL PHOTO SLIDESHOW
# - 1080x1920 MP4
# - gTTS narration
# - FFmpeg encoding
# ============================================================

import os
import re
import json
import time
import math
import hashlib
import subprocess
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from gtts import gTTS


# ============================================================
# CONFIGURATION
# ============================================================

GENERATOR_VERSION = "RIFT_VALLEY_WATCH_GENERATOR_CLEAN_V2"

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
ASSETS_DIR = BASE_DIR / "assets"
SOURCE_DIR = ASSETS_DIR / "source"
AUDIO_DIR = BASE_DIR / "audio"
OUTPUT_DIR = BASE_DIR / "output"
TEMP_DIR = BASE_DIR / "temp_rift_valley"

STORY_FILE = DATA_DIR / "selected_story.json"
SCRIPT_FILE = DATA_DIR / "selected_script.json"

# Additional fallbacks
STORY_FALLBACK = DATA_DIR / "story.json"
SCRIPT_FALLBACK = DATA_DIR / "script.json"

LOCAL_SOURCE_IMAGE = SOURCE_DIR / "story_image.jpg"

OUTPUT_FILE = OUTPUT_DIR / "rift_valley_watch_reel.mp4"
AUDIO_FILE = AUDIO_DIR / "narration.mp3"

VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920

FPS = 30

MAX_IMAGES = 5

REQUEST_TIMEOUT = 25

VIDEO_CODEC = "libx264"
AUDIO_CODEC = "aac"

VIDEO_BITRATE = "5M"
AUDIO_BITRATE = "128k"

BRAND = "RIFT VALLEY WATCH"

BOTTOM_BRAND = "RIFT VALLEY • KENYA"


# ============================================================
# DIRECTORY SETUP
# ============================================================

for directory in [
    DATA_DIR,
    ASSETS_DIR,
    SOURCE_DIR,
    AUDIO_DIR,
    OUTPUT_DIR,
    TEMP_DIR,
]:
    directory.mkdir(parents=True, exist_ok=True)


# ============================================================
# LOGGING
# ============================================================

def log(message):
    print(f"[RIFT VALLEY WATCH] {message}", flush=True)


# ============================================================
# JSON HELPERS
# ============================================================

def load_json(path):
    path = Path(path)

    if not path.exists():
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            return data

        return {}

    except Exception as exc:
        log(f"Could not read {path}: {exc}")
        return {}


def first_existing_json(*paths):
    for path in paths:
        if Path(path).exists():
            data = load_json(path)
            if data:
                return data

    return {}


# ============================================================
# TEXT SANITIZATION
# ============================================================

SOURCE_PATTERNS = [
    r"\bsource\s*:\s*[^.]+",
    r"\bsource\s*[-–—]\s*[^.]+",
    r"\bpublished\s+by\s+[^.]+",
    r"\breported\s+by\s+[^.]+",
    r"\baccording\s+to\s+[^.]+",
    r"\bcredit\s*:\s*[^.]+",
    r"\bphoto\s+credit\s*:\s*[^.]+",
    r"\bimage\s+credit\s*:\s*[^.]+",
    r"\bimage\s+courtesy\s+of\s+[^.]+",
    r"\bcourtesy\s+of\s+[^.]+",
]

PHOTO_ARTIFACT_PATTERNS = [
    r"\[\s*photos?\s*\]",
    r"\[\s*photo\s*\]",
    r"\[\s*gallery\s*\]",
    r"\[\s*images?\s*\]",
    r"\(\s*photos?\s*\)",
    r"\bphotos?\s*:",
    r"\bimages?\s*:",
]

CREDIT_FRAGMENT_PATTERNS = [
    r"/\s*PCS\b",
    r"\bPCS\s*[-–—:]",
    r"\bPresidential Communications Service\b",
    r"\bPhoto\s+by\s+[^.]+",
    r"\bPhotos?\s+by\s+[^.]+",
    r"\bCourtesy\s*:\s*[^.]+",
]

SCRAPING_PATTERNS = [
    r"\bgoogle\s+news\b",
    r"\bgoogle\s+news\s+app\b",
    r"\bfacebook\.com\b",
    r"\btwitter\.com\b",
    r"\bx\.com\b",
    r"\bsubscribe\s+to\s+our\s+newsletter\b",
    r"\bread\s+more\b",
    r"\bclick\s+here\b",
]


def clean_whitespace(text):
    if not text:
        return ""

    text = str(text)

    text = text.replace("\u00a0", " ")
    text = text.replace("\r", " ")
    text = text.replace("\n", " ")

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def remove_artifacts(text):
    if not text:
        return ""

    text = str(text)

    # Remove square-bracket editorial tags.
    for pattern in PHOTO_ARTIFACT_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.I)

    # Remove source/publisher attribution.
    for pattern in SOURCE_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.I)

    # Remove image/photo credits.
    for pattern in CREDIT_FRAGMENT_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.I)

    # Remove obvious scraping artifacts.
    for pattern in SCRAPING_PATTERNS:
        text = re.sub(pattern, " ", text, flags=re.I)

    # Remove leading/trailing separators.
    text = re.sub(r"\s*/\s*", " ", text)

    text = re.sub(r"\s*[-–—:]\s*$", "", text)

    # Remove duplicate punctuation.
    text = re.sub(r"\.{2,}", ".", text)
    text = re.sub(r",\s*,+", ", ", text)

    text = clean_whitespace(text)

    return text.strip(" -–—:;,.\"'")


def clean_title(title):
    title = remove_artifacts(title)

    # Remove common headline prefixes.
    title = re.sub(
        r"^(breaking\s*:?\s*)",
        "",
        title,
        flags=re.I,
    )

    title = re.sub(
        r"^(latest\s*:?\s*)",
        "",
        title,
        flags=re.I,
    )

    title = clean_whitespace(title)

    return title.strip(" -–—:;,.\"'")


# ============================================================
# SENTENCE PROCESSING
# ============================================================

def split_sentences(text):
    text = remove_artifacts(text)

    if not text:
        return []

    # Protect common abbreviations.
    protected = text

    protected = re.sub(
        r"\b(Mr|Mrs|Ms|Dr|Prof|Hon|Eng|St|No)\.",
        r"\1<PERIOD>",
        protected,
        flags=re.I,
    )

    parts = re.split(
        r"(?<=[.!?])\s+",
        protected,
    )

    result = []

    for part in parts:
        part = part.replace("<PERIOD>", ".")
        part = clean_whitespace(part)

        if not part:
            continue

        if len(part) < 3:
            continue

        result.append(part)

    return result


def complete_sentences_only(text):
    """
    Keeps only complete sentences.
    Prevents fixed-character truncation from creating broken narration.
    """

    text = remove_artifacts(text)

    if not text:
        return ""

    sentences = split_sentences(text)

    if not sentences:
        return ""

    complete = []

    for sentence in sentences:
        sentence = sentence.strip()

        if not sentence:
            continue

        if sentence[-1] not in ".!?":
            continue

        complete.append(sentence)

    return " ".join(complete)


def sentence_aware_trim(text, max_words=95):
    """
    Trim only at a complete sentence.
    Never cuts a sentence halfway.
    """

    text = remove_artifacts(text)

    sentences = split_sentences(text)

    if not sentences:
        return ""

    selected = []
    count = 0

    for sentence in sentences:
        words = sentence.split()
        word_count = len(words)

        if count + word_count > max_words:
            break

        selected.append(sentence)
        count += word_count

    return " ".join(selected).strip()


# ============================================================
# STORY EXTRACTION
# ============================================================

def get_story():
    story = first_existing_json(
        STORY_FILE,
        SCRIPT_FILE,
        STORY_FALLBACK,
        SCRIPT_FALLBACK,
    )

    if not story:
        raise RuntimeError(
            "No story JSON was found."
        )

    return story


def get_value(data, *keys):
    if not isinstance(data, dict):
        return ""

    for key in keys:
        value = data.get(key)

        if value is None:
            continue

        if isinstance(value, str) and value.strip():
            return value.strip()

        if isinstance(value, (int, float)):
            return str(value)

    return ""


def extract_title(story):
    title = get_value(
        story,
        "title",
        "headline",
        "story_title",
        "name",
    )

    return clean_title(title)


def extract_county(story):
    county = get_value(
        story,
        "county",
        "county_name",
        "location",
        "region",
    )

    county = remove_artifacts(county)

    return county.strip()


def extract_summary(story):
    summary = get_value(
        story,
        "summary",
        "description",
        "excerpt",
        "story_summary",
        "content",
        "body",
        "text",
    )

    return remove_artifacts(summary)


# ============================================================
# NARRATION
# ============================================================

def build_narration(story):
    title = extract_title(story)
    county = extract_county(story)
    summary = extract_summary(story)

    # Clean summary to complete sentences only.
    summary_clean = complete_sentences_only(summary)

    # Keep narration short enough for a reel.
    summary_clean = sentence_aware_trim(
        summary_clean,
        max_words=78,
    )

    pieces = []

    if title:
        pieces.append(title.rstrip(".!?") + ".")

    if county and county.lower() not in title.lower():
        pieces.append(
            f"This report concerns {county} County."
        )

    if summary_clean:
        pieces.append(summary_clean)

    narration = " ".join(pieces)

    narration = remove_artifacts(narration)

    # Final sentence-aware safety.
    narration = complete_sentences_only(narration)

    # If still too long, trim at a sentence.
    narration = sentence_aware_trim(
        narration,
        max_words=100,
    )

    # Absolute fallback.
    if not narration:
        if title:
            narration = title.rstrip(".!?") + "."
        else:
            narration = (
                "A developing story from Kenya's Rift Valley."
            )

    narration = remove_artifacts(narration)

    return narration.strip()


# ============================================================
# FONT HELPERS
# ============================================================

def find_font(size, bold=False):
    candidates = []

    if bold:
        candidates.extend([
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        ])
    else:
        candidates.extend([
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        ])

    candidates.extend([
        "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
    ])

    for candidate in candidates:
        if os.path.exists(candidate):
            try:
                return ImageFont.truetype(
                    candidate,
                    size=size,
                )
            except Exception:
                pass

    return ImageFont.load_default()


# ============================================================
# IMAGE UTILITIES
# ============================================================

def sha256_file(path):
    try:
        h = hashlib.sha256()

        with open(path, "rb") as f:
            while True:
                chunk = f.read(1024 * 1024)

                if not chunk:
                    break

                h.update(chunk)

        return h.hexdigest()

    except Exception:
        return ""


def image_is_valid(path):
    path = Path(path)

    if not path.exists():
        return False

    if path.stat().st_size < 10_000:
        return False

    try:
        with Image.open(path) as img:
            img.verify()

        with Image.open(path) as img:
            width, height = img.size

            if width < 300 or height < 200:
                return False

        return True

    except Exception:
        return False


def normalize_image_url(url):
    if not url:
        return ""

    url = str(url).strip()

    if url.startswith("//"):
        url = "https:" + url

    return url


def is_image_url(value):
    if not value:
        return False

    value = str(value).strip()

    if value.startswith("http://") or value.startswith("https://"):
        return True

    return False


# ============================================================
# IMAGE CANDIDATE EXTRACTION
# ============================================================

IMAGE_KEYS = [
    "images",
    "image_urls",
    "image_url",
    "article_images",
    "photos",
    "photo_urls",
    "gallery",
    "gallery_images",
    "media",
    "media_urls",
    "image",
    "photo",
    "thumbnail",
    "thumbnail_url",
]


def recursively_find_images(value, found=None):
    if found is None:
        found = []

    if value is None:
        return found

    if isinstance(value, str):
        value = value.strip()

        if is_image_url(value):
            found.append(value)

        elif (
            value.lower().endswith(
                (
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".webp",
                    ".bmp",
                )
            )
        ):
            found.append(value)

        return found

    if isinstance(value, list):
        for item in value:
            recursively_find_images(item, found)

        return found

    if isinstance(value, tuple):
        for item in value:
            recursively_find_images(item, found)

        return found

    if isinstance(value, dict):
        for key, item in value.items():
            key_lower = str(key).lower()

            if (
                key_lower in IMAGE_KEYS
                or "image" in key_lower
                or "photo" in key_lower
                or "gallery" in key_lower
            ):
                recursively_find_images(
                    item,
                    found,
                )

        return found

    return found


def extract_image_candidates(story):
    candidates = []

    # Highest priority: local recovered source image.
    if LOCAL_SOURCE_IMAGE.exists():
        candidates.append(
            str(LOCAL_SOURCE_IMAGE)
        )

    # Search JSON for image URLs and paths.
    json_candidates = recursively_find_images(
        story
    )

    candidates.extend(json_candidates)

    # Look in common asset locations.
    possible_dirs = [
        SOURCE_DIR,
        ASSETS_DIR,
        DATA_DIR,
    ]

    for directory in possible_dirs:
        if not directory.exists():
            continue

        for path in sorted(directory.glob("*")):
            if path.suffix.lower() in [
                ".jpg",
                ".jpeg",
                ".png",
                ".webp",
                ".bmp",
            ]:
                candidates.append(str(path))

    # Deduplicate.
    final = []
    seen = set()

    for candidate in candidates:
        candidate = str(candidate).strip()

        if not candidate:
            continue

        key = candidate.lower()

        if key in seen:
            continue

        seen.add(key)
        final.append(candidate)

    return final


# ============================================================
# IMAGE DOWNLOAD
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "Chrome/120 Safari/537.36"
    ),
    "Accept": (
        "image/avif,image/webp,image/apng,"
        "image/svg+xml,image/*,*/*;q=0.8"
    ),
}


def download_image(url, index):
    url = normalize_image_url(url)

    if not url:
        return None

    destination = TEMP_DIR / f"downloaded_{index}.jpg"

    try:
        log(f"Downloading image {index}: {url}")

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )

        response.raise_for_status()

        content = response.content

        if len(content) < 10_000:
            log("Image response is too small.")
            return None

        temporary = TEMP_DIR / f"raw_{index}"

        with open(temporary, "wb") as f:
            f.write(content)

        try:
            with Image.open(temporary) as img:
                img = img.convert("RGB")
                img.save(
                    destination,
                    "JPEG",
                    quality=95,
                )

        except Exception as exc:
            log(f"Downloaded file is not a valid image: {exc}")
            return None

        if image_is_valid(destination):
            return destination

    except Exception as exc:
        log(f"Image download failed: {exc}")

    return None


# ============================================================
# IMAGE RESOLUTION
# ============================================================

def resolve_images(story):
    candidates = extract_image_candidates(story)

    log(f"Image candidates found: {len(candidates)}")

    resolved = []
    hashes = set()

    index = 1

    for candidate in candidates:
        if len(resolved) >= MAX_IMAGES:
            break

        # Local file.
        local_path = Path(candidate)

        if local_path.exists():
            if not image_is_valid(local_path):
                continue

            digest = sha256_file(local_path)

            if digest and digest in hashes:
                continue

            if digest:
                hashes.add(digest)

            resolved.append(local_path)

            log(
                f"Using local image: {local_path}"
            )

            continue

        # Remote URL.
        if is_image_url(candidate):
            downloaded = download_image(
                candidate,
                index,
            )

            index += 1

            if downloaded is None:
                continue

            digest = sha256_file(downloaded)

            if digest and digest in hashes:
                continue

            if digest:
                hashes.add(digest)

            resolved.append(downloaded)

    # Strong fallback: the recovered source image.
    if not resolved and LOCAL_SOURCE_IMAGE.exists():
        if image_is_valid(LOCAL_SOURCE_IMAGE):
            resolved.append(LOCAL_SOURCE_IMAGE)

    if not resolved:
        raise RuntimeError(
            "No usable article image was found."
        )

    # Ensure max five.
    resolved = resolved[:MAX_IMAGES]

    log(
        f"Distinct usable images: {len(resolved)}"
    )

    return resolved


# ============================================================
# IMAGE PREPARATION
# ============================================================

def prepare_image_for_vertical(
    image_path,
    output_path,
):
    """
    Creates a vertical 1080x1920 composition.

    The original photo is NOT stretched.
    A blurred enlarged copy forms the background.
    The actual photo is fitted into the central area.
    """

    image_path = Path(image_path)
    output_path = Path(output_path)

    with Image.open(image_path) as original:
        original = original.convert("RGB")

        # Background.
        bg = original.copy()
        bg.thumbnail(
            (
                VIDEO_WIDTH,
                VIDEO_HEIGHT,
            ),
            Image.Resampling.LANCZOS,
        )

        # Cover entire vertical canvas.
        bg_ratio = max(
            VIDEO_WIDTH / bg.width,
            VIDEO_HEIGHT / bg.height,
        )

        bg = bg.resize(
            (
                int(bg.width * bg_ratio),
                int(bg.height * bg_ratio),
            ),
            Image.Resampling.LANCZOS,
        )

        left = (bg.width - VIDEO_WIDTH) // 2
        top = (bg.height - VIDEO_HEIGHT) // 2

        bg = bg.crop(
            (
                left,
                top,
                left + VIDEO_WIDTH,
                top + VIDEO_HEIGHT,
            )
        )

        bg = bg.filter(
            ImageFilter.GaussianBlur(28)
        )

        canvas = bg.copy()

        # Main photo.
        photo = original.copy()

        max_width = int(VIDEO_WIDTH * 0.94)
        max_height = int(VIDEO_HEIGHT * 0.76)

        ratio = min(
            max_width / photo.width,
            max_height / photo.height,
        )

        new_size = (
            max(1, int(photo.width * ratio)),
            max(1, int(photo.height * ratio)),
        )

        photo = photo.resize(
            new_size,
            Image.Resampling.LANCZOS,
        )

        x = (VIDEO_WIDTH - photo.width) // 2
        y = (VIDEO_HEIGHT - photo.height) // 2

        # Slight dark frame.
        frame = Image.new(
            "RGB",
            (
                photo.width + 12,
                photo.height + 12,
            ),
            (15, 15, 15),
        )

        frame.paste(
            photo,
            (6, 6),
        )

        canvas.paste(
            frame,
            (
                x - 6,
                y - 6,
            ),
        )

        canvas.save(
            output_path,
            "JPEG",
            quality=94,
        )

    return output_path


# ============================================================
# TEXT WRAPPING
# ============================================================

def wrap_text(
    draw,
    text,
    font,
    max_width,
):
    words = text.split()

    lines = []
    current = ""

    for word in words:
        test = (
            word
            if not current
            else current + " " + word
        )

        bbox = draw.textbbox(
            (0, 0),
            test,
            font=font,
        )

        width = bbox[2] - bbox[0]

        if width <= max_width:
            current = test
        else:
            if current:
                lines.append(current)

            current = word

    if current:
        lines.append(current)

    return lines


# ============================================================
# OVERLAY FRAME
# ============================================================

def create_overlay(
    output_path,
    county,
    title,
    image_number=None,
    image_total=None,
    show_counter=False,
):
    """
    Creates a transparent overlay.

    IMPORTANT:
    No source/publisher information is displayed.
    """

    overlay = Image.new(
        "RGBA",
        (
            VIDEO_WIDTH,
            VIDEO_HEIGHT,
        ),
        (0, 0, 0, 0),
    )

    draw = ImageDraw.Draw(
        overlay,
        "RGBA",
    )

    # --------------------------------------------------------
    # TOP BRAND BAR
    # --------------------------------------------------------

    draw.rectangle(
        (
            0,
            0,
            VIDEO_WIDTH,
            205,
        ),
        fill=(0, 0, 0, 225),
    )

    brand_font = find_font(
        54,
        bold=True,
    )

    small_font = find_font(
        31,
        bold=True,
    )

    title_font = find_font(
        57,
        bold=True,
    )

    draw.text(
        (
            54,
            35,
        ),
        BRAND,
        font=brand_font,
        fill=(255, 255, 255, 255),
    )

    county_text = ""

    if county:
        county_text = (
            county.upper()
            + " COUNTY • KENYA"
        )

    if county_text:
        draw.text(
            (
                57,
                115,
            ),
            county_text,
            font=small_font,
            fill=(225, 225, 225, 255),
        )

    # --------------------------------------------------------
    # HEADLINE CARD
    # --------------------------------------------------------

    if title:
        clean_headline = clean_title(title)

        lines = wrap_text(
            draw,
            clean_headline,
            title_font,
            VIDEO_WIDTH - 110,
        )

        # Keep headline to three lines maximum.
        lines = lines[:3]

        box_height = (
            55
            + len(lines) * 72
            + 45
        )

        y1 = VIDEO_HEIGHT - 465
        y2 = y1 + box_height

        draw.rounded_rectangle(
            (
                35,
                y1,
                VIDEO_WIDTH - 35,
                y2,
            ),
            radius=22,
            fill=(0, 0, 0, 215),
        )

        y = y1 + 32

        for line in lines:
            draw.text(
                (
                    62,
                    y,
                ),
                line,
                font=title_font,
                fill=(255, 255, 255, 255),
            )

            y += 72

    # --------------------------------------------------------
    # REAL PHOTO COUNTER ONLY
    # --------------------------------------------------------

    if (
        show_counter
        and image_number
        and image_total
        and image_total > 1
    ):
        counter_font = find_font(
            30,
            bold=True,
        )

        counter = (
            f"{image_number}/{image_total}"
        )

        bbox = draw.textbbox(
            (0, 0),
            counter,
            font=counter_font,
        )

        cw = bbox[2] - bbox[0]
        ch = bbox[3] - bbox[1]

        x = VIDEO_WIDTH - cw - 55
        y = 238

        draw.rounded_rectangle(
            (
                x - 18,
                y - 12,
                x + cw + 18,
                y + ch + 12,
            ),
            radius=14,
            fill=(0, 0, 0, 190),
        )

        draw.text(
            (
                x,
                y,
            ),
            counter,
            font=counter_font,
            fill=(255, 255, 255, 255),
        )

    # --------------------------------------------------------
    # BOTTOM BRANDING
    # --------------------------------------------------------

    footer_font = find_font(
        28,
        bold=True,
    )

    footer = BOTTOM_BRAND

    bbox = draw.textbbox(
        (0, 0),
        footer,
        font=footer_font,
    )

    fw = bbox[2] - bbox[0]

    draw.rectangle(
        (
            0,
            VIDEO_HEIGHT - 82,
            VIDEO_WIDTH,
            VIDEO_HEIGHT,
        ),
        fill=(0, 0, 0, 220),
    )

    draw.text(
        (
            (VIDEO_WIDTH - fw) // 2,
            VIDEO_HEIGHT - 62,
        ),
        footer,
        font=footer_font,
        fill=(255, 255, 255, 255),
    )

    overlay.save(
        output_path,
        "PNG",
    )

    return output_path


# ============================================================
# AUDIO GENERATION
# ============================================================

def generate_audio(narration):
    if not narration:
        raise RuntimeError(
            "No narration was generated."
        )

    if AUDIO_FILE.exists():
        try:
            AUDIO_FILE.unlink()
        except Exception:
            pass

    log("Generating narration...")

    log(
        f"Narration words: "
        f"{len(narration.split())}"
    )

    tts = gTTS(
        text=narration,
        lang="en",
        slow=False,
    )

    tts.save(str(AUDIO_FILE))

    if not AUDIO_FILE.exists():
        raise RuntimeError(
            "Narration audio was not created."
        )

    if AUDIO_FILE.stat().st_size < 10_000:
        raise RuntimeError(
            "Narration audio is suspiciously small."
        )

    return AUDIO_FILE


# ============================================================
# AUDIO DURATION
# ============================================================

def get_media_duration(path):
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(path),
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Unable to determine media duration."
        )

    try:
        return float(result.stdout.strip())
    except Exception:
        raise RuntimeError(
            "Invalid media duration returned by ffprobe."
        )


# ============================================================
# FFMPEG COMMAND RUNNER
# ============================================================

def run_ffmpeg(command):
    log("Running FFmpeg...")

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    print(
        result.stdout,
        flush=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg failed with exit code "
            f"{result.returncode}"
        )


# ============================================================
# SINGLE IMAGE KEN BURNS
# ============================================================

def create_single_image_video(
    image_path,
    overlay_path,
    duration,
    output_path,
):
    """
    One genuine image.
    No fake scene counter.
    Continuous subtle Ken Burns zoom.
    """

    image_path = Path(image_path)
    overlay_path = Path(overlay_path)
    output_path = Path(output_path)

    frames = max(
        1,
        int(math.ceil(duration * FPS)),
    )

    # zoompan:
    # Starts at 1.00
    # Slowly reaches approximately 1.08.
    zoom_expression = (
        "min(zoom+0.00035,1.08)"
    )

    filter_complex = (
        f"[0:v]"
        f"scale="
        f"{VIDEO_WIDTH}:"
        f"{VIDEO_HEIGHT}:"
        f"force_original_aspect_ratio=increase,"
        f"crop="
        f"{VIDEO_WIDTH}:"
        f"{VIDEO_HEIGHT},"
        f"zoompan="
        f"z='{zoom_expression}':"
        f"d=1:"
        f"x='iw/2-(iw/zoom/2)':"
        f"y='ih/2-(ih/zoom/2)':"
        f"s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:"
        f"fps={FPS}"
        f"[base];"
        f"[base][1:v]"
        f"overlay=0:0:"
        f"format=yuv420p"
    )

    command = [
        "ffmpeg",
        "-y",

        "-loop",
        "1",
        "-i",
        str(image_path),

        "-loop",
        "1",
        "-i",
        str(overlay_path),

        "-filter_complex",
        filter_complex,

        "-t",
        f"{duration:.3f}",

        "-r",
        str(FPS),

        "-c:v",
        VIDEO_CODEC,

        "-preset",
        "veryfast",

        "-b:v",
        VIDEO_BITRATE,

        "-pix_fmt",
        "yuv420p",

        "-movflags",
        "+faststart",

        str(output_path),
    ]

    run_ffmpeg(command)

    if not output_path.exists():
        raise RuntimeError(
            "Single-image video was not generated."
        )

    return output_path


# ============================================================
# MULTI IMAGE SLIDESHOW
# ============================================================

def create_multi_image_video(
    images,
    overlays,
    duration,
    output_path,
):
    """
    Creates a real slideshow.

    A counter is shown only because there are
    genuinely different image files.
    """

    count = len(images)

    if count < 2:
        raise ValueError(
            "Multi-image slideshow requires at least 2 images."
        )

    output_path = Path(output_path)

    per_image = duration / count

    input_args = []

    for image in images:
        input_args.extend([
            "-loop",
            "1",
            "-t",
            f"{per_image:.3f}",
            "-i",
            str(image),
        ])

    for overlay in overlays:
        input_args.extend([
            "-loop",
            "1",
            "-t",
            f"{per_image:.3f}",
            "-i",
            str(overlay),
        ])

    filter_parts = []

    # Image streams.
    for i in range(count):
        filter_parts.append(
            f"[{i}:v]"
            f"scale="
            f"{VIDEO_WIDTH}:"
            f"{VIDEO_HEIGHT}:"
            f"force_original_aspect_ratio=increase,"
            f"crop="
            f"{VIDEO_WIDTH}:"
            f"{VIDEO_HEIGHT},"
            f"zoompan="
            f"z='min(zoom+0.00045,1.07)':"
            f"d=1:"
            f"x='iw/2-(iw/zoom/2)':"
            f"y='ih/2-(ih/zoom/2)':"
            f"s={VIDEO_WIDTH}x{VIDEO_HEIGHT}:"
            f"fps={FPS},"
            f"setsar=1"
            f"[img{i}]"
        )

    # Overlay streams.
    for i in range(count):
        overlay_index = count + i

        filter_parts.append(
            f"[{overlay_index}:v]"
            f"format=rgba"
            f"[ov{i}]"
        )

    # Combine image + overlay.
    for i in range(count):
        filter_parts.append(
            f"[img{i}]"
            f"[ov{i}]"
            f"overlay=0:0:"
            f"format=yuv420p"
            f"[scene{i}]"
        )

    concat_inputs = "".join(
        f"[scene{i}]"
        for i in range(count)
    )

    filter_parts.append(
        f"{concat_inputs}"
        f"concat=n={count}:v=1:a=0:"
        f"format=yuv420p"
        f"[vout]"
    )

    filter_complex = ";".join(
        filter_parts
    )

    command = [
        "ffmpeg",
        "-y",
        *input_args,

        "-filter_complex",
        filter_complex,

        "-t",
        f"{duration:.3f}",

        "-map",
        "[vout]",

        "-r",
        str(FPS),

        "-c:v",
        VIDEO_CODEC,

        "-preset",
        "veryfast",

        "-b:v",
        VIDEO_BITRATE,

        "-pix_fmt",
        "yuv420p",

        "-movflags",
        "+faststart",

        str(output_path),
    ]

    run_ffmpeg(command)

    if not output_path.exists():
        raise RuntimeError(
            "Multi-image video was not generated."
        )

    return output_path


# ============================================================
# FINAL VIDEO + AUDIO
# ============================================================

def attach_audio(video_path, audio_path):
    """
    Adds narration without changing the video content.
    """

    video_path = Path(video_path)
    audio_path = Path(audio_path)

    final_path = OUTPUT_FILE

    temporary_final = (
        OUTPUT_DIR /
        "rift_valley_watch_reel_temp.mp4"
    )

    if temporary_final.exists():
        temporary_final.unlink()

    audio_duration = get_media_duration(
        audio_path
    )

    video_duration = get_media_duration(
        video_path
    )

    log(
        f"Video duration: {video_duration:.2f}s"
    )

    log(
        f"Audio duration: {audio_duration:.2f}s"
    )

    command = [
        "ffmpeg",
        "-y",

        "-i",
        str(video_path),

        "-i",
        str(audio_path),

        "-map",
        "0:v:0",

        "-map",
        "1:a:0",

        "-c:v",
        "copy",

        "-c:a",
        AUDIO_CODEC,

        "-b:a",
        AUDIO_BITRATE,

        "-shortest",

        "-movflags",
        "+faststart",

        str(temporary_final),
    ]

    run_ffmpeg(command)

    if not temporary_final.exists():
        raise RuntimeError(
            "Final MP4 was not created."
        )

    # Replace final file.
    if final_path.exists():
        final_path.unlink()

    temporary_final.replace(
        final_path
    )

    return final_path


# ============================================================
# FINAL QC
# ============================================================

def verify_final_video(path):
    path = Path(path)

    if not path.exists():
        raise RuntimeError(
            "Final MP4 does not exist."
        )

    size = path.stat().st_size

    if size < 100_000:
        raise RuntimeError(
            "Final MP4 is suspiciously small."
        )

    command = [
        "ffprobe",
        "-v",
        "error",

        "-show_entries",
        "stream="
        "codec_type,"
        "codec_name,"
        "width,"
        "height,"
        "duration,"
        "r_frame_rate",

        "-show_entries",
        "format="
        "duration,"
        "size",

        "-of",
        "json",

        str(path),
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
