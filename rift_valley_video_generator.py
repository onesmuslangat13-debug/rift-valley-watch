from pathlib import Path
import json
import re
import subprocess
import sys
import shutil
import hashlib
import math

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH
# VIDEO GENERATOR
# VERSION: RVW_VIDEO_V18_SHORT_REEL_FULL_PHOTO
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

OUTPUT_DIR = BASE_DIR / "output"
AUDIO_DIR = BASE_DIR / "audio"
SOURCE_DIR = BASE_DIR / "assets" / "source"
VIDEO_WORK_DIR = BASE_DIR / "assets" / "video_work"
DATA_DIR = BASE_DIR / "data"

STORY_FILE = DATA_DIR / "selected_story.json"
SCRIPT_FILE = DATA_DIR / "selected_script.json"

SOURCE_IMAGE = SOURCE_DIR / "story_image.jpg"
NARRATION_FILE = AUDIO_DIR / "narration.mp3"

FINAL_VIDEO = OUTPUT_DIR / "rift_valley_watch_reel.mp4"

WIDTH = 1080
HEIGHT = 1920
FPS = 30

# ------------------------------------------------------------
# SHORT-FORM SETTINGS
# ------------------------------------------------------------

MIN_REEL_DURATION = 18
TARGET_REEL_DURATION = 25
MAX_REEL_DURATION = 30

# Approximate narration length for 18–30 second reels.
# gTTS speaking speed varies, so the generator also measures
# the resulting MP3 duration.
MIN_NARRATION_WORDS = 45
TARGET_NARRATION_WORDS = 62
MAX_NARRATION_WORDS = 75

MAX_REAL_PHOTOS = 5

REQUEST_TIMEOUT = 20

HEADLINE_MAX_CHARS = 68

VIDEO_VERSION = "RVW_VIDEO_V18_SHORT_REEL_FULL_PHOTO"

# HTTP headers for article-photo downloads.
HTTP_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/153.0 Safari/537.36"
    )
}


# ============================================================
# LOGGING
# ============================================================

def log(message):
    print(f"[RIFT VALLEY WATCH] {message}", flush=True)


# ============================================================
# COMMAND EXECUTION
# ============================================================

def run_command(command, check=True):
    log("RUNNING: " + " ".join(str(x) for x in command))

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.stdout:
        print(result.stdout, flush=True)

    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}"
        )

    return result


# ============================================================
# JSON HELPERS
# ============================================================

def load_json(path):
    if not path.exists():
        raise FileNotFoundError(f"Missing JSON file: {path}")

    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def text_value(value):
    if value is None:
        return ""

    if isinstance(value, str):
        return value.strip()

    if isinstance(value, (int, float)):
        return str(value)

    return ""


# ============================================================
# HEADLINE CLEANING
# ============================================================

def clean_headline(headline):
    """
    Removes publisher/source suffixes from article headlines.

    Examples:
        Headline | KBC Digital
        Headline | KBC
        Headline - KBC Digital
        Headline — KBC Digital
        Headline (KBC Digital)

    All become:
        Headline
    """

    headline = text_value(headline)

    if not headline:
        return "Rift Valley News"

    # Normalize whitespace.
    headline = re.sub(r"\s+", " ", headline).strip()

    # Remove common publisher suffixes repeatedly.
    publisher_patterns = [
        r"\s*\|\s*KBC\s+Digital\s*$",
        r"\s*\|\s*KBC\s*$",
        r"\s*[-–—]\s*KBC\s+Digital\s*$",
        r"\s*[-–—]\s*KBC\s*$",
        r"\s*\(\s*KBC\s+Digital\s*\)\s*$",
        r"\s*\(\s*KBC\s*\)\s*$",

        r"\s*\|\s*Citizen\s+Digital\s*$",
        r"\s*\|\s*Citizen\s*$",
        r"\s*[-–—]\s*Citizen\s+Digital\s*$",
        r"\s*[-–—]\s*Citizen\s*$",

        r"\s*\|\s*The\s+Star\s*$",
        r"\s*[-–—]\s*The\s+Star\s*$",

        r"\s*\|\s*Nation\s*$",
        r"\s*[-–—]\s*Nation\s*$",
        r"\s*\|\s*Nation\s+Africa\s*$",
        r"\s*[-–—]\s*Nation\s+Africa\s*$",

        r"\s*\|\s*People\s+Daily\s*$",
        r"\s*[-–—]\s*People\s+Daily\s*$",

        r"\s*\|\s*Standard\s*$",
        r"\s*[-–—]\s*Standard\s*$",

        r"\s*\|\s*Kenya\s+News\s+Agency\s*$",
        r"\s*[-–—]\s*Kenya\s+News\s+Agency\s*$",
    ]

    changed = True

    while changed:
        changed = False

        for pattern in publisher_patterns:
            new_headline = re.sub(
                pattern,
                "",
                headline,
                flags=re.IGNORECASE,
            ).strip()

            if new_headline != headline:
                headline = new_headline
                changed = True

    # Remove trailing separators left behind.
    headline = re.sub(r"\s*[\|\-–—:]+\s*$", "", headline).strip()

    # Remove accidental duplicated spaces.
    headline = re.sub(r"\s{2,}", " ", headline)

    return headline


# ============================================================
# GENERAL TEXT CLEANING
# ============================================================

def clean_text(text):
    text = text_value(text)

    if not text:
        return ""

    text = re.sub(r"\s+", " ", text).strip()

    return text


def word_count(text):
    return len(re.findall(r"\b[\w’'-]+\b", text or ""))


# ============================================================
# SENTENCE EXTRACTION
# ============================================================

def split_sentences(text):
    text = clean_text(text)

    if not text:
        return []

    # Protect common abbreviations.
    text = re.sub(r"\bMr\.", "Mr", text)
    text = re.sub(r"\bMrs\.", "Mrs", text)
    text = re.sub(r"\bDr\.", "Dr", text)
    text = re.sub(r"\bProf\.", "Prof", text)

    sentences = re.split(
        r"(?<=[.!?])\s+(?=[A-Z0-9\"“‘])",
        text,
    )

    output = []

    for sentence in sentences:
        sentence = clean_text(sentence)

        if not sentence:
            continue

        if word_count(sentence) < 3:
            continue

        output.append(sentence)

    return output


# ============================================================
# NARRATION SOURCE COLLECTION
# ============================================================

def collect_text_candidates(story, script):
    candidates = []

    story_fields = [
        "narration",
        "script",
        "voiceover",
        "voice_over",
        "narration_text",
        "description",
        "summary",
        "body",
        "content",
        "article",
        "text",
    ]

    script_fields = [
        "narration",
        "script",
        "voiceover",
        "voice_over",
        "voiceover_text",
        "narration_text",
        "text",
        "body",
        "content",
    ]

    for field in script_fields:
        value = text_value(script.get(field))

        if value:
            candidates.append(value)

    for field in story_fields:
        value = text_value(story.get(field))

        if value:
            candidates.append(value)

    return candidates


# ============================================================
# BUILD SHORT NARRATION
# ============================================================

def build_short_narration(story, script):
    """
    Creates a short-form narration designed for approximately
    18–30 seconds.

    Priority:
        1. Existing narration/script.
        2. Story description/summary.
        3. Story body/content.

    The generator keeps the strongest opening information and
    stops once the target word range is reached.
    """

    candidates = collect_text_candidates(story, script)

    all_sentences = []

    for candidate in candidates:
        for sentence in split_sentences(candidate):
            sentence = clean_text(sentence)

            if not sentence:
                continue

            duplicate = False

            normalized = re.sub(
                r"[^a-z0-9]+",
                " ",
                sentence.lower(),
            ).strip()

            for existing in all_sentences:
                existing_norm = re.sub(
                    r"[^a-z0-9]+",
                    " ",
                    existing.lower(),
                ).strip()

                if normalized == existing_norm:
                    duplicate = True
                    break

            if not duplicate:
                all_sentences.append(sentence)

    # --------------------------------------------------------
    # If sentences exist, construct a concise news narration.
    # --------------------------------------------------------

    selected = []
    current_words = 0

    for sentence in all_sentences:
        sentence_words = word_count(sentence)

        if sentence_words < 4:
            continue

        # Don't let one giant article sentence dominate the reel.
        if sentence_words > 45:
            words = sentence.split()

            # Preserve the strongest opening part.
            sentence = " ".join(words[:45]).strip()

            if not sentence.endswith((".", "!", "?")):
                sentence += "."

            sentence_words = word_count(sentence)

        if current_words == 0:
            selected.append(sentence)
            current_words += sentence_words
            continue

        if current_words + sentence_words <= MAX_NARRATION_WORDS:
            selected.append(sentence)
            current_words += sentence_words

        if current_words >= TARGET_NARRATION_WORDS:
            break

    narration = clean_text(" ".join(selected))

    # --------------------------------------------------------
    # If the result is too long, trim cleanly at a sentence
    # boundary first, then by words if absolutely necessary.
    # --------------------------------------------------------

    if word_count(narration) > MAX_NARRATION_WORDS:
        words = narration.split()

        narration = " ".join(
            words[:MAX_NARRATION_WORDS]
        ).strip()

        if not narration.endswith((".", "!", "?")):
            narration += "."

    # --------------------------------------------------------
    # Last-resort fallback.
    # --------------------------------------------------------

    if word_count(narration) < MIN_NARRATION_WORDS:
        title = clean_headline(
            story.get("title")
            or story.get("headline")
            or "Rift Valley News"
        )

        description = clean_text(
            story.get("description")
            or story.get("summary")
            or story.get("body")
            or story.get("content")
            or ""
        )

        fallback_sentences = split_sentences(description)

        parts = [title + "."]

        for sentence in fallback_sentences:
            if word_count(" ".join(parts)) + word_count(sentence) <= MAX_NARRATION_WORDS:
                parts.append(sentence)

            if word_count(" ".join(parts)) >= TARGET_NARRATION_WORDS:
                break

        narration = clean_text(" ".join(parts))

    # --------------------------------------------------------
    # Final word limit.
    # --------------------------------------------------------

    words = narration.split()

    if len(words) > MAX_NARRATION_WORDS:
        narration = " ".join(
            words[:MAX_NARRATION_WORDS]
        ).strip()

        if not narration.endswith((".", "!", "?")):
            narration += "."

    return narration


# ============================================================
# NARRATION
# ============================================================

def get_narration(story, script):
    narration = build_short_narration(story, script)

    count = word_count(narration)

    log("=" * 70)
    log("SHORT REEL NARRATION")
    log("=" * 70)
    log(f"WORDS: {count}")
    log(narration)
    log("=" * 70)

    if count < MIN_NARRATION_WORDS:
        raise RuntimeError(
            f"Narration is too short: {count} words. "
            f"Minimum is {MIN_NARRATION_WORDS}."
        )

    if count > MAX_NARRATION_WORDS:
        raise RuntimeError(
            f"Narration is too long: {count} words. "
            f"Maximum is {MAX_NARRATION_WORDS}."
        )

    return narration


# ============================================================
# AUDIO GENERATION
# ============================================================

def generate_audio(narration):
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    if NARRATION_FILE.exists():
        NARRATION_FILE.unlink()

    log("Generating narration audio...")

    tts = gTTS(
        text=narration,
        lang="en",
        slow=False,
    )

    tts.save(str(NARRATION_FILE))

    if not NARRATION_FILE.exists():
        raise RuntimeError("Narration MP3 was not generated.")

    if NARRATION_FILE.stat().st_size < 1000:
        raise RuntimeError("Narration MP3 is unexpectedly small.")

    duration = get_media_duration(NARRATION_FILE)

    log(f"NARRATION AUDIO DURATION: {duration:.2f} seconds")

    if duration < MIN_REEL_DURATION - 2:
        log(
            "WARNING: narration is shorter than the preferred "
            "minimum reel duration."
        )

    if duration > MAX_REEL_DURATION + 2:
        log(
            "WARNING: narration exceeds the preferred 30-second "
            "reel limit."
        )

    return duration


# ============================================================
# MEDIA DURATION
# ============================================================

def get_media_duration(path):
    result = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path),
        ],
        check=True,
    )

    value = result.stdout.strip()

    try:
        return float(value)
    except Exception:
        raise RuntimeError(
            f"Could not determine duration for {path}"
        )


# ============================================================
# REAL ARTICLE IMAGE COLLECTION
# ============================================================

def collect_story_image_urls(story):
    """
    ONLY uses image URLs already attached to the selected story.

    It intentionally does NOT scrape random <img> tags from the
    article page because those can be adverts, logos, related
    stories, banners, or unrelated images.
    """

    fields = [
        "image_urls",
        "images",
        "article_images",
        "photo_urls",
        "image_candidates",
    ]

    urls = []

    def add(value):
        if isinstance(value, str):
            value = value.strip()

            if value:
                urls.append(value)

        elif isinstance(value, list):
            for item in value:
                add(item)

        elif isinstance(value, dict):
            for key in (
                "url",
                "src",
                "image",
                "image_url",
                "original",
            ):
                if key in value:
                    add(value[key])

    for field in fields:
        if field in story:
            add(story[field])

    # Some story structures store one main image.
    for field in (
        "image_url",
        "image",
        "photo",
        "photo_url",
        "thumbnail",
        "og_image",
    ):
        if field in story:
            add(story[field])

    # Deduplicate while preserving order.
    result = []
    seen = set()

    for url in urls:
        normalized = url.strip()

        if not normalized:
            continue

        key = normalized.lower()

        if key in seen:
            continue

        seen.add(key)
        result.append(normalized)

    return result[:MAX_REAL_PHOTOS]


# ============================================================
# IMAGE URL VALIDATION
# ============================================================

def image_url_is_valid(url):
    if not url:
        return False

    value = url.lower().strip()

    blocked_terms = [
        "logo",
        "icon",
        "avatar",
        "favicon",
        "sprite",
        "placeholder",
        "advert",
        "banner",
        "doubleclick",
        "facebook.com",
        "twitter.com",
        "x.com",
        "google.com",
        "youtube.com",
        "whatsapp.com",
        "tracking",
        "pixel",
    ]

    for term in blocked_terms:
        if term in value:
            return False

    return value.startswith(("http://", "https://"))


# ============================================================
# DOWNLOAD IMAGE
# ============================================================

def download_image(url, destination):
    if not image_url_is_valid(url):
        return False

    try:
        log(f"Downloading article photo: {url}")

        response = requests.get(
            url,
            headers=HTTP_HEADERS,
            timeout=REQUEST_TIMEOUT,
            stream=True,
        )

        response.raise_for_status()

        content_type = (
            response.headers.get("Content-Type", "")
            .lower()
        )

        if (
            content_type
            and "image" not in content_type
            and "octet-stream" not in content_type
        ):
            log(
                f"Skipping non-image response: {content_type}"
            )
            return False

        temp_file = destination.with_suffix(".download")

        with temp_file.open("wb") as f:
            for chunk in response.iter_content(
                chunk_size=64 * 1024
            ):
                if chunk:
                    f.write(chunk)

        if not temp_file.exists():
            return False

        if temp_file.stat().st_size < 10_000:
            temp_file.unlink(missing_ok=True)
            return False

        try:
            with Image.open(temp_file) as img:
                img.verify()
        except Exception:
            temp_file.unlink(missing_ok=True)
            return False

        shutil.move(
            str(temp_file),
            str(destination),
        )

        return True

    except Exception as exc:
        log(f"Image download failed: {exc}")

        try:
            destination.with_suffix(".download").unlink(
                missing_ok=True
            )
        except Exception:
            pass

        return False


# ============================================================
# IMAGE HASH
# ============================================================

def image_hash(path):
    try:
        digest = hashlib.sha1()

        with path.open("rb") as f:
            while True:
                chunk = f.read(1024 * 1024)

                if not chunk:
                    break

                digest.update(chunk)

        return digest.hexdigest()

    except Exception:
        return ""


# ============================================================
# IMAGE VALIDATION
# ============================================================

def validate_image(path):
    try:
        with Image.open(path) as img:
            width, height = img.size

            if width < 250 or height < 250:
                return False

            if width * height < 150_000:
                return False

            return True

    except Exception:
        return False


# ============================================================
# PREPARE ARTICLE PHOTOS
# ============================================================

def prepare_article_photos(story):
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)

    # Remove generated article photos from previous runs.
    for existing in SOURCE_DIR.glob("article_photo_*.jpg"):
        existing.unlink(missing_ok=True)

    image_urls = collect_story_image_urls(story)

    log("=" * 70)
    log("ARTICLE IMAGE PREPARATION")
    log("=" * 70)
    log(f"EXPLICIT IMAGE URLS FOUND: {len(image_urls)}")

    photos = []
    hashes = set()

    for index, url in enumerate(
        image_urls[:MAX_REAL_PHOTOS],
        start=1,
    ):
        destination = (
            SOURCE_DIR
            / f"article_photo_{index}.jpg"
        )

        if not download_image(url, destination):
            continue

        if not validate_image(destination):
            destination.unlink(missing_ok=True)
            continue

        digest = image_hash(destination)

        if digest and digest in hashes:
            destination.unlink(missing_ok=True)
            continue

        if digest:
            hashes.add(digest)

        # Normalize the photo to JPEG.
        try:
            with Image.open(destination) as img:
                img = img.convert("RGB")

                # Prevent huge source images from unnecessarily
                # increasing processing time.
                img.thumbnail(
                    (2400, 2400),
                    Image.Resampling.LANCZOS,
                )

                img.save(
                    destination,
                    "JPEG",
                    quality=94,
                    optimize=True,
                )

        except Exception as exc:
            log(
                f"Could not normalize image "
                f"{destination}: {exc}"
            )

            destination.unlink(missing_ok=True)
            continue

        photos.append(destination)

        log(f"ACCEPTED REAL ARTICLE PHOTO: {destination}")

    # --------------------------------------------------------
    # Fallback to the main story image already created by main.
    # --------------------------------------------------------

    if not photos and SOURCE_IMAGE.exists():
        if validate_image(SOURCE_IMAGE):
            fallback = (
                SOURCE_DIR / "article_photo_1.jpg"
            )

            try:
                with Image.open(SOURCE_IMAGE) as img:
                    img = img.convert("RGB")

                    img.thumbnail(
                        (2400, 2400),
                        Image.Resampling.LANCZOS,
                    )

                    img.save(
                        fallback,
                        "JPEG",
                        quality=94,
                        optimize=True,
                    )

                if validate_image(fallback):
                    photos.append(fallback)

            except Exception as exc:
                log(
                    f"Could not use story_image.jpg: {exc}"
                )

    if not photos:
        raise RuntimeError(
            "No valid real article photos were available."
        )

    log(f"REAL ARTICLE PHOTO COUNT: {len(photos)}")
    log("=" * 70)

    return photos


# ============================================================
# FONT
# ============================================================

def find_font(size, bold=False):
    candidates = []

    if bold:
        candidates.extend(
            [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            ]
        )
    else:
        candidates.extend(
            [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            ]
        )

    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)

    return ImageFont.load_default()


# ============================================================
# TEXT WRAPPING
# ============================================================

def wrap_text(draw, text, font, max_width):
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
# PHOTO FRAME
# ============================================================

def create_full_photo_frame(
    source_path,
    destination,
):
    """
    Creates a 1080x1920 frame where the ENTIRE article photo
    remains visible.

    The original photo is never crop-filled.

    A blurred, enlarged version of the same photo fills the
    background so there are no black bars.
    """

    with Image.open(source_path) as original:
        original = original.convert("RGB")

        # ----------------------------------------------------
        # Background:
        # Fill the vertical canvas with a blurred version
        # of the same photo.
        # ----------------------------------------------------

        background = original.copy()

        scale = max(
            WIDTH / background.width,
            HEIGHT / background.height,
        )

        bg_w = max(
            WIDTH,
            int(background.width * scale),
        )

        bg_h = max(
            HEIGHT,
            int(background.height * scale),
        )

        background = background.resize(
            (bg_w, bg_h),
            Image.Resampling.LANCZOS,
        )

        left = max(
            0,
            (background.width - WIDTH) // 2,
        )

        top = max(
            0,
            (background.height - HEIGHT) // 2,
        )

        background = background.crop(
            (
                left,
                top,
                left + WIDTH,
                top + HEIGHT,
            )
        )

        background = background.filter(
            ImageFilter.GaussianBlur(radius=26)
        )

        # Darken the background slightly.
        overlay = Image.new(
            "RGBA",
            (WIDTH, HEIGHT),
            (0, 0, 0, 75),
        )

        background = background.convert("RGBA")
        background.alpha_composite(overlay)

        # ----------------------------------------------------
        # Foreground:
        # Fit the ENTIRE original image inside the canvas.
        # ----------------------------------------------------

        foreground = original.copy()

        fit_scale = min(
            (WIDTH * 0.94) / foreground.width,
            (HEIGHT * 0.68) / foreground.height,
        )

        fit_w = max(
            1,
            int(foreground.width * fit_scale),
        )

        fit_h = max(
            1,
            int(foreground.height * fit_scale),
        )

        foreground = foreground.resize(
            (fit_w, fit_h),
            Image.Resampling.LANCZOS,
        )

        # Add a subtle border.
        frame = Image.new(
            "RGBA",
            (
                fit_w + 10,
                fit_h + 10,
            ),
            (255, 255, 255, 225),
        )

        frame.alpha_composite(
            foreground.convert("RGBA"),
            (5, 5),
        )

        x = (WIDTH - frame.width) // 2

        # Put the photo in the upper/middle area so the
        # headline panel never covers it.
        y = int(HEIGHT * 0.18)

        if y + frame.height > int(HEIGHT * 0.78):
            y = int(HEIGHT * 0.78) - frame.height

        y = max(80, y)

        background.alpha_composite(
            frame,
            (x, y),
        )

        final = background.convert("RGB")

        final.save(
            destination,
            "JPEG",
            quality=94,
            optimize=True,
        )


# ============================================================
# OVERLAY
# ============================================================

def create_overlay(
    headline,
    county,
    frame_path,
    destination,
):
    """
    Creates branding/headline overlay.

    IMPORTANT:
    No SOURCE, publisher, website, URL, or article source
    is displayed anywhere.
    """

    image = Image.open(frame_path).convert("RGBA")

    draw = ImageDraw.Draw(image)

    # --------------------------------------------------------
    # Top branding
    # --------------------------------------------------------

    top_bar_height = 125

    draw.rectangle(
        (
            0,
            0,
            WIDTH,
            top_bar_height,
        ),
        fill=(8, 15, 25, 238),
    )

    brand_font = find_font(
        50,
        bold=True,
    )

    draw.text(
        (48, 30),
        "RIFT VALLEY WATCH",
        font=brand_font,
        fill=(255, 255, 255, 255),
    )

    # --------------------------------------------------------
    # County label
    # --------------------------------------------------------

    county = clean_text(county)

    if not county:
        county = "RIFT VALLEY"

    county_font = find_font(
        30,
        bold=True,
    )

    county_text = county.upper()

    bbox = draw.textbbox(
        (0, 0),
        county_text,
        font=county_font,
    )

    county_width = bbox[2] - bbox[0]

    county_x = WIDTH - county_width - 48

    draw.text(
        (county_x, 45),
        county_text,
        font=county_font,
        fill=(235, 235, 235, 255),
    )

    # --------------------------------------------------------
    # Headline panel
    # --------------------------------------------------------

    headline = clean_headline(headline)

    headline_font = find_font(
        57,
        bold=True,
    )

    lines = wrap_text(
        draw,
        headline,
        headline_font,
        WIDTH - 100,
    )

    # Limit headline to three lines.
    if len(lines) > 3:
        lines = lines[:3]

        # Add ellipsis if needed.
        if not lines[-1].endswith("..."):
            lines[-1] = lines[-1].rstrip(".") + "..."

    line_height = 70

    panel_height = (
        190
        + len(lines) * line_height
    )

    panel_top = HEIGHT - panel_height

    draw.rectangle(
        (
            0,
            panel_top,
            WIDTH,
            HEIGHT,
        ),
        fill=(5, 10, 18, 238),
    )

    # Accent line.
    draw.rectangle(
        (
            45,
            panel_top + 32,
            220,
            panel_top + 42,
        ),
        fill=(220, 35, 45, 255),
    )

    # "BREAKING" style label.
    label_font = find_font(
        27,
        bold=True,
    )

    draw.text(
        (
            48,
            panel_top + 58,
        ),
        "RIFT VALLEY",
        font=label_font,
        fill=(235, 235, 235, 255),
    )

    y = panel_top + 100

    for line in lines:
        draw.text(
            (
                48,
                y,
            ),
            line,
            font=headline_font,
            fill=(255, 255, 255, 255),
        )

        y += line_height

    image.convert("RGB").save(
        destination,
        "JPEG",
        quality=94,
        optimize=True,
    )


# ============================================================
# SCENE GENERATION
# ============================================================

def create_scene(
    photo_path,
    headline,
    county,
    duration,
    scene_index,
):
    scene_dir = VIDEO_WORK_DIR / "scenes"

    scene_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    frame_path = (
        scene_dir
        / f"frame_{scene_index:02d}.jpg"
    )

    overlay_path = (
        scene_dir
        / f"overlay_{scene_index:02d}.jpg"
    )

    output_path = (
        scene_dir
        / f"scene_{scene_index:02d}.mp4"
    )

    # --------------------------------------------------------
    # FULL PHOTO
    # --------------------------------------------------------

    create_full_photo_frame(
        photo_path,
        frame_path,
    )

    # --------------------------------------------------------
    # OVERLAY
    # --------------------------------------------------------

    create_overlay(
        headline,
        county,
        frame_path,
        overlay_path,
    )

    # --------------------------------------------------------
    # Subtle continuous motion.
    #
    # IMPORTANT:
    # Motion is applied to the whole finished frame.
    # It is deliberately tiny so the complete article photo
    # remains visible.
    # --------------------------------------------------------

    motion_modes = [
        ("zoom_in", 1.00, 1.035),
        ("zoom_out", 1.035, 1.00),
        ("zoom_in", 1.00, 1.025),
        ("zoom_out", 1.025, 1.00),
        ("zoom_in", 1.00, 1.03),
    ]

    mode, start_zoom, end_zoom = motion_modes[
        scene_index % len(motion_modes)
    ]

    frames = max(
        1,
        int(round(duration * FPS)),
    )

    # Keep the movement extremely subtle.
    zoom_delta = end_zoom - start_zoom

    if abs(zoom_delta) < 0.0001:
        zoom_delta = 0.0001

    zoompan_filter = (
        "zoompan="
        f"z='min(max(zoom,{start_zoom:.4f})"
        f"+({zoom_delta:.4f})*(on/{max(frames - 1, 1)}),"
        f"{max(start_zoom, end_zoom):.4f})':"
        "x='iw/2-(iw/zoom/2)':"
        "y='ih/2-(ih/zoom/2)':"
        f"d={frames}:"
        f"s={WIDTH}x{HEIGHT}:"
        f"fps={FPS}"
    )

    run_command(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(overlay_path),
            "-vf",
            zoompan_filter,
            "-t",
            f"{duration:.3f}",
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "21",
            "-pix_fmt",
            "yuv420p",
            str(output_path),
        ],
        check=True,
    )

    if not output_path.exists():
        raise RuntimeError(
            f"Scene was not created: {output_path}"
        )

    return output_path


# ============================================================
# SCENE PLAN
# ============================================================

def build_scene_plan(photos, total_duration):
    """
    Use every distinct real article photo available.

    If only one genuine photo exists, reuse that same photo
    across several scenes with different subtle motion.

    This is intentional: it is better to reuse the real story
    photo than introduce an unrelated image.
    """

    if not photos:
        raise RuntimeError(
            "No article photos available."
        )

    # --------------------------------------------------------
    # Number of scenes.
    #
    # For a 20–30 second reel, 4 scenes gives approximately
    # 5–7 seconds per visual.
    # --------------------------------------------------------

    desired_scenes = min(
        4,
        max(2, len(photos)),
    )

    scene_duration = total_duration / desired_scenes

    plan = []

    for i in range(desired_scenes):
        photo = photos[i % len(photos)]

        plan.append(
            {
                "photo": photo,
                "duration": scene_duration,
            }
        )

    return plan


# ============================================================
# CONCATENATE SCENES
# ============================================================

def concatenate_scenes(scene_files, destination):
    concat_file = (
        VIDEO_WORK_DIR
        / "scenes.txt"
    )

    with concat_file.open(
        "w",
        encoding="utf-8",
    ) as f:
        for scene in scene_files:
            absolute_path = scene.resolve()

            # FFmpeg concat demuxer escaping.
            path_text = str(
                absolute_path
            ).replace(
                "'",
                "'\\''",
            )

            f.write(
                f"file '{path_text}'\n"
            )

    run_command(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-an",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "21",
            "-pix_fmt",
            "yuv420p",
            str(destination),
        ],
        check=True,
    )

    if not destination.exists():
        raise RuntimeError(
            "Silent concatenated video was not created."
        )

    return destination


# ============================================================
# AUDIO + VIDEO
# ============================================================

def combine_audio(
    video_path,
    audio_path,
    destination,
    target_duration,
):
    """
    Audio is the master duration.

    The video is never allowed to end before the narration.
    No -shortest is used.
    """

    run_command(
        [
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
            "aac",
            "-b:a",
            "128k",
            "-t",
            f"{target_duration:.3f}",
            "-movflags",
            "+faststart",
            str(destination),
        ],
        check=True,
    )

    if not destination.exists():
        raise RuntimeError(
            "Final MP4 was not created."
        )

    return destination


# ============================================================
# FINAL QUALITY CONTROL
# ============================================================

def final_qc(video_path, expected_audio_duration):
    log("=" * 70)
    log("FINAL VIDEO QUALITY CONTROL")
    log("=" * 70)

    if not video_path.exists():
        raise RuntimeError(
            "Final MP4 does not exist."
        )

    size = video_path.stat().st_size

    log(
        f"FINAL FILE SIZE: "
        f"{size / (1024 * 1024):.2f} MB"
    )

    if size < 100_000:
        raise RuntimeError(
            "Final MP4 is suspiciously small."
        )

    result = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_streams",
            "-show_format",
            "-of",
            "json",
            str(video_path),
        ],
        check=True,
    )

    try:
        info = json.loads(result.stdout)
    except Exception:
        raise RuntimeError(
            "Could not parse final MP4 metadata."
        )

    streams = info.get("streams", [])

    video_stream = None
    audio_stream = None

    for stream in streams:
        if stream.get("codec_type") == "video":
            video_stream = stream

        if stream.get("codec_type") == "audio":
            audio_stream = stream

    if video_stream is None:
        raise RuntimeError(
            "Final MP4 has no video stream."
        )

    if audio_stream is None:
        raise RuntimeError(
            "Final MP4 has no audio stream."
        )

    width = int(
        video_stream.get("width", 0)
    )

    height = int(
        video_stream.get("height", 0)
    )

    log(
        f"VIDEO SIZE: {width}x{height}"
    )

    if width != WIDTH or height != HEIGHT:
        raise RuntimeError(
            f"Expected {WIDTH}x{HEIGHT}, "
            f"got {width}x{height}"
        )

    duration = float(
        info.get("format", {})
        .get("duration", 0)
    )

    log(
        f"FINAL DURATION: {duration:.2f} seconds"
    )

    log(
        f"EXPECTED AUDIO: "
        f"{expected_audio_duration:.2f} seconds"
    )

    # --------------------------------------------------------
    # Absolute duration checks.
    # --------------------------------------------------------

    if duration < MIN_REEL_DURATION - 1:
        raise RuntimeError(
            "Final reel is shorter than the minimum target."
        )

    if duration > MAX_REEL_DURATION + 1.5:
        raise RuntimeError(
            "Final reel is longer than the 30-second target."
        )

    # --------------------------------------------------------
    # Ensure audio is not materially shorter than video.
    # --------------------------------------------------------

    audio_duration = float(
        audio_stream.get("duration")
        or 0
    )

    log(
        f"AUDIO STREAM DURATION: "
        f"{audio_duration:.2f} seconds"
    )

    if audio_duration < duration - 1.0:
        raise RuntimeError(
            "Audio appears to end before the video."
        )

    log("=" * 70)
    log("FINAL QC PASSED")
    log("=" * 70)

    return True


# ============================================================
# CLEAN WORK DIRECTORY
# ============================================================

def clean_work_directory():
    VIDEO_WORK_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    scenes_dir = (
        VIDEO_WORK_DIR / "scenes"
    )

    if scenes_dir.exists():
        shutil.rmtree(scenes_dir)

    scenes_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    # Remove old intermediate files.
    for name in [
        "silent_video.mp4",
        "final_mux.mp4",
        "scenes.txt",
    ]:
        path = VIDEO_WORK_DIR / name

        if path.exists():
            path.unlink()


# ============================================================
# MAIN
# ============================================================

def main():
    log("=" * 70)
    log("RIFT VALLEY WATCH")
    log("VIDEO GENERATOR")
    log(VIDEO_VERSION)
    log("=" * 70)

    # --------------------------------------------------------
    # Prepare directories.
    # --------------------------------------------------------

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    AUDIO_DIR.mkdir(
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

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Load selected story.
    # --------------------------------------------------------

    story = load_json(STORY_FILE)

    # selected_script.json may not always exist in emergency
    # situations, so allow the story itself to provide the text.
    if SCRIPT_FILE.exists():
        script = load_json(SCRIPT_FILE)
    else:
        script = {}

    # --------------------------------------------------------
    # Headline.
    # --------------------------------------------------------

    raw_headline = (
        story.get("headline")
        or story.get("title")
        or story.get("name")
        or "Rift Valley News"
    )

    headline = clean_headline(raw_headline)

    # --------------------------------------------------------
    # County.
    # --------------------------------------------------------

    county = (
        story.get("county")
        or story.get("location")
        or story.get("region")
        or "Rift Valley"
    )

    county = clean_text(county)

    log("=" * 70)
    log("SELECTED STORY")
    log("=" * 70)
    log(f"HEADLINE: {headline}")
    log(f"COUNTY: {county}")
    log("=" * 70)

    # --------------------------------------------------------
    # Short narration.
    # --------------------------------------------------------

    narration = get_narration(
        story,
        script,
    )

    narration_words = word_count(narration)

    log(
        f"FINAL NARRATION WORD COUNT: "
        f"{narration_words}"
    )

    # --------------------------------------------------------
    # Audio.
    # --------------------------------------------------------

    audio_duration = generate_audio(
        narration
    )

    # --------------------------------------------------------
    # If gTTS produces an unexpectedly long result, fail
    # rather than silently generating a 60–70 second reel.
    # --------------------------------------------------------

    if audio_duration > MAX_REEL_DURATION + 2:
        raise RuntimeError(
            f"Narration audio is {audio_duration:.2f} seconds. "
            f"Maximum allowed is approximately "
            f"{MAX_REEL_DURATION} seconds. "
            f"The narration must be shortened."
        )

    # --------------------------------------------------------
    # Clean old scene work.
    # --------------------------------------------------------

    clean_work_directory()

    # --------------------------------------------------------
    # Article photos.
    # --------------------------------------------------------

    photos = prepare_article_photos(
        story
    )

    log(
        f"REAL ARTICLE PHOTO COUNT: "
        f"{len(photos)}"
    )

    # --------------------------------------------------------
    # Build scene plan.
    # --------------------------------------------------------

    scene_plan = build_scene_plan(
        photos,
        audio_duration,
    )

    log("=" * 70)
    log("SCENE PLAN")
    log("=" * 70)

    for index, item in enumerate(
        scene_plan,
        start=1,
    ):
        log(
            f"SCENE {index}: "
            f"{item['photo'].name} "
            f"for {item['duration']:.2f}s"
        )

    log("=" * 70)

    # --------------------------------------------------------
    # Generate scenes.
    # --------------------------------------------------------

    scene_files = []

    for index, item in enumerate(
        scene_plan,
        start=1,
    ):
        scene = create_scene(
            photo_path=item["photo"],
            headline=headline,
            county=county,
            duration=item["duration"],
            scene_index=index - 1,
        )

        scene_files.append(scene)

    if not scene_files:
        raise RuntimeError(
            "No video scenes were generated."
        )

    # --------------------------------------------------------
    # Concatenate.
    # --------------------------------------------------------

    silent_video = (
        VIDEO_WORK_DIR
        / "silent_video.mp4"
    )

    concatenate_scenes(
        scene_files,
        silent_video,
    )

    # --------------------------------------------------------
    # Final mux.
    # --------------------------------------------------------

    temporary_final = (
        VIDEO_WORK_DIR
        / "final_mux.mp4"
    )

    combine_audio(
        silent_video,
        NARRATION_FILE,
        temporary_final,
        audio_duration,
    )

    # --------------------------------------------------------
    # Replace final output.
    # --------------------------------------------------------

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if FINAL_VIDEO.exists():
        FINAL_VIDEO.unlink()

    shutil.copy2(
        temporary_final,
        FINAL_VIDEO,
    )

    # --------------------------------------------------------
    # Final QC.
    # --------------------------------------------------------

    final_qc(
        FINAL_VIDEO,
        audio_duration,
    )

    # --------------------------------------------------------
    # Final success.
    # --------------------------------------------------------

    log("=" * 70)
    log("RIFT VALLEY WATCH VIDEO GENERATION SUCCESSFUL")
    log("=" * 70)
    log(f"VERSION: {VIDEO_VERSION}")
    log(f"HEADLINE: {headline}")
    log(f"COUNTY: {county}")
    log(f"PHOTOS USED: {len(photos)}")
    log(
        f"NARRATION WORDS: "
        f"{narration_words}"
    )
    log(
        f"NARRATION DURATION: "
        f"{audio_duration:.2f}s"
    )
    log(
        f"FINAL VIDEO: "
        f"{FINAL_VIDEO}"
    )
    log("=" * 70)


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        log("Generation interrupted by user.")
        sys.exit(130)

    except Exception as exc:
        log("=" * 70)
        log("GENERATION FAILED")
        log("=" * 70)
        log(str(exc))
        log("=" * 70)
        sys.exit(1)
