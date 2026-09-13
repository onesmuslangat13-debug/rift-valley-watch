from pathlib import Path
import json
import re
import subprocess
import sys
import shutil
import hashlib
import math
import traceback
import textwrap

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH
# VIDEO GENERATOR
# VERSION: RVW_VIDEO_V19_STABLE_SHORT_REEL
#
# PURPOSE
# - 15–30 second vertical news reel
# - Uses only genuine images supplied by selected_story.json
# - Supports multiple article photos/scenes
# - Automatically shortens narration when TTS is too long
# - Keeps entire article photo visible
# - No publisher/source/URL displayed on video
# - No unrelated image scraping
# - Final output: output/rift_valley_watch_reel.mp4
# ============================================================


VERSION = "RVW_VIDEO_V19_STABLE_SHORT_REEL"


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

OUTPUT_DIR = BASE_DIR / "output"
AUDIO_DIR = BASE_DIR / "audio"
SOURCE_DIR = BASE_DIR / "assets" / "source"
VIDEO_WORK_DIR = BASE_DIR / "assets" / "video_work"
DATA_DIR = BASE_DIR / "data"

STORY_FILE = DATA_DIR / "selected_story.json"
SCRIPT_FILE = DATA_DIR / "selected_script.json"

FINAL_VIDEO = OUTPUT_DIR / "rift_valley_watch_reel.mp4"
NARRATION_FILE = AUDIO_DIR / "narration.mp3"


# ============================================================
# REEL SETTINGS
# ============================================================

VIDEO_WIDTH = 1080
VIDEO_HEIGHT = 1920
FPS = 30

MIN_REEL_DURATION = 15.0
TARGET_REEL_DURATION = 25.0
MAX_REEL_DURATION = 30.0

SAFE_AUDIO_MAX = 29.0

MIN_NARRATION_WORDS = 40
TARGET_NARRATION_WORDS = 54
MAX_NARRATION_WORDS = 68

MAX_PHOTOS = 5

REQUEST_TIMEOUT = 20

BACKGROUND_BLUR = 28

FONT_DIRS = [
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/usr/share/fonts/truetype/liberation2"),
    Path("/usr/share/fonts/truetype/noto"),
    Path("/usr/share/fonts"),
]


# ============================================================
# LOGGING
# ============================================================

def log(message=""):
    print(f"[RIFT VALLEY WATCH] {message}", flush=True)


def banner(title):
    log("=" * 70)
    log(title)
    log("=" * 70)


def fail(message):
    banner("GENERATION FAILED")
    log(message)
    log("=" * 70)
    raise RuntimeError(message)


# ============================================================
# COMMAND RUNNER
# ============================================================

def run_command(command, check=True, capture=False):
    log("RUNNING: " + " ".join(str(x) for x in command))

    if capture:
        result = subprocess.run(
            command,
            cwd=str(BASE_DIR),
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT
        )

        if result.stdout:
            print(result.stdout, flush=True)

        if check and result.returncode != 0:
            raise RuntimeError(
                f"Command failed with exit code {result.returncode}: "
                f"{' '.join(str(x) for x in command)}"
            )

        return result

    result = subprocess.run(
        command,
        cwd=str(BASE_DIR)
    )

    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}: "
            f"{' '.join(str(x) for x in command)}"
        )

    return result


# ============================================================
# DIRECTORY SETUP
# ============================================================

def prepare_directories():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_WORK_DIR.mkdir(parents=True, exist_ok=True)

    for item in VIDEO_WORK_DIR.iterdir():
        try:
            if item.is_file() or item.is_symlink():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)
        except Exception:
            pass


# ============================================================
# JSON HELPERS
# ============================================================

def load_json(path):
    if not path.exists():
        fail(f"Required JSON file does not exist: {path}")

    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        fail(f"Could not read JSON file {path}: {exc}")


def first_value(data, keys):
    if not isinstance(data, dict):
        return ""

    for key in keys:
        value = data.get(key)

        if value is None:
            continue

        if isinstance(value, str):
            value = value.strip()
            if value:
                return value

        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str) and item.strip():
                    return item.strip()

    return ""


# ============================================================
# STORY LOADING
# ============================================================

def load_story():
    story = load_json(STORY_FILE)

    if isinstance(story, list):
        if not story:
            fail("selected_story.json contains an empty list.")
        story = story[0]

    if not isinstance(story, dict):
        fail("selected_story.json does not contain a story object.")

    return story


def load_script():
    if not SCRIPT_FILE.exists():
        return {}

    try:
        data = load_json(SCRIPT_FILE)

        if isinstance(data, list):
            return data[0] if data else {}

        return data if isinstance(data, dict) else {}

    except Exception:
        return {}


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_whitespace(text):
    if not text:
        return ""

    text = str(text)
    text = text.replace("\r", " ")
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def clean_headline(text):
    text = clean_whitespace(text)

    if not text:
        return ""

    # Remove publisher suffixes.
    publisher_patterns = [
        r"\s*\|\s*KBC(?:\s+Digital)?\s*$",
        r"\s*\|\s*Citizen(?:\s+Digital)?\s*$",
        r"\s*\|\s*Citizen\s+TV\s*$",
        r"\s*\|\s*The\s+Star\s*$",
        r"\s*\|\s*Nation\s*$",
        r"\s*\|\s*Nation\s+Africa\s*$",
        r"\s*\|\s*Daily\s+Nation\s*$",
    ]

    for pattern in publisher_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)

    # Remove common trailing website/publisher fragments.
    text = re.sub(
        r"\s*[-–—]\s*(KBC|Citizen|The Star|Nation Africa|Daily Nation)\s*$",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(r"\s+", " ", text).strip()

    return text


def clean_article_text(text):
    text = clean_whitespace(text)

    if not text:
        return ""

    # Remove source/publisher suffixes.
    text = re.sub(
        r"\s*\|\s*(KBC(?:\s+Digital)?|Citizen(?:\s+Digital)?|The\s+Star|Nation(?:\s+Africa)?)\s*$",
        "",
        text,
        flags=re.IGNORECASE
    )

    # Remove common website boilerplate.
    text = re.sub(
        r"\bRead more\b.*$",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"\bClick here to read more\b.*$",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    ).strip()

    return text


def split_sentences(text):
    text = clean_article_text(text)

    if not text:
        return []

    # Protect common abbreviations.
    replacements = {
        "Mr.": "Mr<prd>",
        "Mrs.": "Mrs<prd>",
        "Ms.": "Ms<prd>",
        "Dr.": "Dr<prd>",
        "Prof.": "Prof<prd>",
        "Hon.": "Hon<prd>",
        "CS.": "CS<prd>",
        "e.g.": "eg<prd>",
        "i.e.": "ie<prd>",
    }

    protected = text

    for old, new in replacements.items():
        protected = protected.replace(old, new)

    parts = re.split(r"(?<=[.!?])\s+", protected)

    result = []

    for part in parts:
        part = part.replace("<prd>", ".")
        part = clean_whitespace(part)

        if len(part.split()) >= 3:
            result.append(part)

    return result


# ============================================================
# NARRATION SOURCE EXTRACTION
# ============================================================

def collect_text_candidates(story, script):
    candidates = []

    fields = [
        "narration",
        "script",
        "voiceover",
        "voice_over",
        "summary",
        "description",
        "content",
        "article_text",
        "text",
        "body",
        "excerpt",
    ]

    for key in fields:
        value = first_value(script, [key])
        if value:
            candidates.append(value)

    for key in fields:
        value = first_value(story, [key])
        if value:
            candidates.append(value)

    return candidates


def remove_headline_duplication(text, headline):
    text = clean_article_text(text)
    headline = clean_headline(headline)

    if not text or not headline:
        return text

    normalized_text = re.sub(
        r"[^a-z0-9]+",
        " ",
        text.lower()
    ).strip()

    normalized_headline = re.sub(
        r"[^a-z0-9]+",
        " ",
        headline.lower()
    ).strip()

    if normalized_headline and normalized_text.startswith(normalized_headline):
        remaining = text[len(headline):].strip(" .:-–—|")
        if remaining:
            return remaining

    return text


def build_narration(story, script, target_words=TARGET_NARRATION_WORDS):
    headline = clean_headline(
        first_value(
            story,
            [
                "headline",
                "title",
                "story_title",
                "article_title",
            ]
        )
    )

    county = clean_whitespace(
        first_value(
            story,
            [
                "county",
                "location",
                "region",
            ]
        )
    )

    candidates = collect_text_candidates(story, script)

    sentences = []

    for candidate in candidates:
        candidate = clean_article_text(candidate)
        candidate = remove_headline_duplication(candidate, headline)

        if not candidate:
            continue

        for sentence in split_sentences(candidate):
            if sentence not in sentences:
                sentences.append(sentence)

    # Remove extremely short or obviously useless fragments.
    filtered = []

    for sentence in sentences:
        words = sentence.split()

        if len(words) < 5:
            continue

        if re.fullmatch(r"[\W_]+", sentence):
            continue

        filtered.append(sentence)

    sentences = filtered

    # Build from the strongest available factual sentences.
    selected = []

    intro = ""

    if county and headline:
        intro = f"In {county}, {headline}."

    elif headline:
        intro = f"{headline}."

    if intro:
        selected.append(intro)

    current_words = len(" ".join(selected).split())

    for sentence in sentences:
        if sentence in selected:
            continue

        sentence_words = len(sentence.split())

        if current_words >= target_words:
            break

        # Avoid adding an enormous paragraph that destroys reel length.
        if current_words + sentence_words > MAX_NARRATION_WORDS:
            remaining = target_words - current_words

            if remaining >= 8:
                shortened = shorten_sentence(sentence, remaining)

                if shortened:
                    selected.append(shortened)
                    current_words = len(" ".join(selected).split())

            break

        selected.append(sentence)
        current_words += sentence_words

    narration = " ".join(selected)
    narration = clean_article_text(narration)

    # Final cleanup.
    narration = narration.replace(" […] ", " ")
    narration = narration.replace("[…]", "")
    narration = narration.replace("...", ".")
    narration = re.sub(r"\s+", " ", narration).strip()

    # Ensure punctuation.
    if narration and narration[-1] not in ".!?":
        narration += "."

    return narration


def shorten_sentence(sentence, max_words):
    words = clean_article_text(sentence).split()

    if len(words) <= max_words:
        return " ".join(words)

    if max_words < 8:
        return ""

    # Prefer a clean punctuation boundary.
    candidate = words[:max_words]

    # Remove awkward trailing conjunctions/prepositions.
    bad_endings = {
        "and",
        "or",
        "but",
        "to",
        "of",
        "for",
        "with",
        "that",
        "which",
        "who",
        "as",
        "in",
        "on",
        "at",
        "from",
        "by",
    }

    while candidate and candidate[-1].lower().strip(".,!?") in bad_endings:
        candidate.pop()

    if len(candidate) < 6:
        return ""

    result = " ".join(candidate).rstrip(" ,;:-")

    if result and result[-1] not in ".!?":
        result += "."

    return result


def count_words(text):
    return len(re.findall(r"\b[\w’'-]+\b", text))


# ============================================================
# TTS
# ============================================================

def probe_duration(path):
    if not path.exists():
        return 0.0

    result = subprocess.run(
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
        cwd=str(BASE_DIR),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"ffprobe failed for {path}: {result.stderr.strip()}"
        )

    try:
        return float(result.stdout.strip())
    except Exception:
        raise RuntimeError(
            f"Could not read audio duration for {path}: {result.stdout}"
        )


def generate_tts(text, output_path):
    output_path.parent.mkdir(parents=True, exist_ok=True)

    temp_path = output_path.with_suffix(".tmp.mp3")

    try:
        if temp_path.exists():
            temp_path.unlink()

        tts = gTTS(
            text=text,
            lang="en",
            slow=False
        )

        tts.save(str(temp_path))

        if not temp_path.exists() or temp_path.stat().st_size < 1000:
            raise RuntimeError("gTTS produced an invalid audio file.")

        temp_path.replace(output_path)

    except Exception:
        if temp_path.exists():
            try:
                temp_path.unlink()
            except Exception:
                pass

        raise


def shorten_narration_for_audio(narration):
    words = narration.split()

    if len(words) <= MIN_NARRATION_WORDS:
        return narration

    # Progressive reduction.
    target_sizes = []

    current = len(words)

    while current > MIN_NARRATION_WORDS:
        next_size = max(
            MIN_NARRATION_WORDS,
            current - 8
        )

        if next_size not in target_sizes:
            target_sizes.append(next_size)

        current = next_size

    for target in target_sizes:
        candidate = shorten_text_to_word_limit(narration, target)

        if candidate:
            yield candidate


def shorten_text_to_word_limit(text, target_words):
    sentences = split_sentences(text)

    if not sentences:
        words = text.split()

        if len(words) <= target_words:
            return text

        result = " ".join(words[:target_words]).rstrip(" ,;:-")
        if result and result[-1] not in ".!?":
            result += "."
        return result

    selected = []
    count = 0

    for sentence in sentences:
        words = sentence.split()

        if count + len(words) <= target_words:
            selected.append(sentence)
            count += len(words)
            continue

        remaining = target_words - count

        if remaining >= 8:
            shortened = shorten_sentence(sentence, remaining)

            if shortened:
                selected.append(shortened)
                count += len(shortened.split())

        break

    result = " ".join(selected).strip()

    if result and result[-1] not in ".!?":
        result += "."

    return result


def generate_short_audio(narration):
    """
    Generate TTS and automatically shorten text until the resulting
    audio is comfortably below 30 seconds.
    """

    candidates = [narration]

    for candidate in shorten_narration_for_audio(narration):
        if candidate not in candidates:
            candidates.append(candidate)

    # Add an aggressively compressed fallback.
    fallback_sizes = [
        60,
        54,
        50,
        46,
        42,
        40,
    ]

    for size in fallback_sizes:
        candidate = shorten_text_to_word_limit(narration, size)

        if candidate and candidate not in candidates:
            candidates.append(candidate)

    last_duration = None
    last_text = narration

    for index, candidate in enumerate(candidates):
        word_count = count_words(candidate)

        if word_count < MIN_NARRATION_WORDS:
            continue

        log("=" * 70)
        log(
            f"TTS ATTEMPT {index + 1}: "
            f"{word_count} words"
        )
        log(candidate)
        log("=" * 70)

        try:
            generate_tts(
                candidate,
                NARRATION_FILE
            )

            duration = probe_duration(NARRATION_FILE)

            log(
                f"NARRATION AUDIO DURATION: "
                f"{duration:.2f} seconds"
            )

            last_duration = duration
            last_text = candidate

            if duration <= SAFE_AUDIO_MAX:
                log(
                    f"ACCEPTED NARRATION: "
                    f"{word_count} words / "
                    f"{duration:.2f} seconds"
                )

                return candidate, duration

            log(
                f"WARNING: narration is {duration:.2f} seconds. "
                f"Shortening automatically."
            )

        except Exception as exc:
            log(f"TTS ATTEMPT FAILED: {exc}")

    # If everything failed, leave the last generated audio available
    # but reject it clearly.
    if last_duration is not None:
        fail(
            f"Could not shorten narration below "
            f"{SAFE_AUDIO_MAX:.1f} seconds. "
            f"Last duration was {last_duration:.2f} seconds."
        )

    fail("Unable to generate narration audio.")


# ============================================================
# IMAGE URL EXTRACTION
# ============================================================

def normalize_image_url(value):
    if not value:
        return ""

    value = str(value).strip()

    if value.startswith("//"):
        value = "https:" + value

    if not value.startswith(("http://", "https://")):
        return ""

    return value


def extract_image_urls(story):
    """
    IMPORTANT:
    Only use explicit image URLs saved in selected_story.json.
    We deliberately do NOT scrape arbitrary <img> tags from article pages.
    """

    candidates = []

    possible_fields = [
        "image_urls",
        "images",
        "image_urls_list",
        "photo_urls",
        "photos",
        "article_images",
        "story_images",
    ]

    for field in possible_fields:
        value = story.get(field)

        if isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    candidates.append(item)

                elif isinstance(item, dict):
                    for key in [
                        "url",
                        "image_url",
                        "src",
                        "href",
                        "original",
                    ]:
                        if item.get(key):
                            candidates.append(item[key])
                            break

        elif isinstance(value, str):
            candidates.append(value)

    # Also support the primary image field.
    for field in [
        "image_url",
        "image",
        "photo_url",
        "photo",
        "featured_image",
        "featured_image_url",
    ]:
        value = story.get(field)

        if isinstance(value, str):
            candidates.append(value)

        elif isinstance(value, dict):
            for key in [
                "url",
                "src",
                "image_url",
                "original",
            ]:
                if value.get(key):
                    candidates.append(value[key])
                    break

    # Preserve order while removing duplicates.
    final = []
    seen = set()

    for candidate in candidates:
        url = normalize_image_url(candidate)

        if not url:
            continue

        key = url.lower().split("?")[0]

        if key in seen:
            continue

        seen.add(key)
        final.append(url)

    return final[:20]


# ============================================================
# IMAGE DOWNLOAD
# ============================================================

def image_extension_from_content_type(content_type):
    content_type = (content_type or "").lower()

    if "png" in content_type:
        return ".png"

    if "webp" in content_type:
        return ".webp"

    if "gif" in content_type:
        return ".gif"

    if "bmp" in content_type:
        return ".bmp"

    return ".jpg"


def download_image(url, destination):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) "
            "Chrome/120 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    }

    try:
        response = requests.get(
            url,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
            stream=True,
            allow_redirects=True
        )

        response.raise_for_status()

        content_type = response.headers.get("Content-Type", "")

        if "image" not in content_type.lower():
            log(
                f"SKIP IMAGE: content type is not an image: "
                f"{content_type}"
            )
            return False

        temp = destination.with_suffix(".download")

        with temp.open("wb") as f:
            for chunk in response.iter_content(chunk_size=1024 * 64):
                if chunk:
                    f.write(chunk)

        if not temp.exists() or temp.stat().st_size < 5000:
            try:
                temp.unlink()
            except Exception:
                pass

            return False

        try:
            with Image.open(temp) as im:
                width, height = im.size

                if width < 250 or height < 250:
                    log(
                        f"SKIP SMALL IMAGE: "
                        f"{width}x{height}"
                    )

                    temp.unlink()
                    return False

                im.verify()

        except Exception as exc:
            log(f"SKIP INVALID IMAGE: {exc}")

            try:
                temp.unlink()
            except Exception:
                pass

            return False

        temp.replace(destination)

        return True

    except Exception as exc:
        log(f"IMAGE DOWNLOAD FAILED: {exc}")
        return False


def prepare_story_images(story):
    urls = extract_image_urls(story)

    banner("ARTICLE IMAGE SELECTION")

    if not urls:
        fail(
            "No explicit article image URLs were found in "
            "selected_story.json."
        )

    log(f"Explicit image URLs available: {len(urls)}")

    image_paths = []

    for index, url in enumerate(urls[:MAX_PHOTOS], start=1):
        extension = ".jpg"

        try:
            response_head = requests.head(
                url,
                timeout=8,
                allow_redirects=True,
                headers={
                    "User-Agent": "Mozilla/5.0"
                }
            )

            extension = image_extension_from_content_type(
                response_head.headers.get("Content-Type", "")
            )

        except Exception:
            pass

        destination = (
            SOURCE_DIR /
            f"story_image_{index}{extension}"
        )

        log(f"IMAGE {index}: {url}")

        if download_image(url, destination):
            image_paths.append(destination)
            log(f"ACCEPTED IMAGE {index}: {destination.name}")

        if len(image_paths) >= MAX_PHOTOS:
            break

    # Also maintain the legacy expected file.
    if image_paths:
        legacy = SOURCE_DIR / "story_image.jpg"

        try:
            with Image.open(image_paths[0]) as im:
                converted = im.convert("RGB")
                converted.save(
                    legacy,
                    "JPEG",
                    quality=95
                )

            if legacy not in image_paths:
                image_paths.insert(0, legacy)

        except Exception as exc:
            log(f"Could not create legacy story_image.jpg: {exc}")

    if not image_paths:
        fail(
            "No valid article images could be downloaded from the "
            "explicit image URLs."
        )

    # Remove duplicate physical images by hash.
    unique_paths = []
    hashes = set()

    for path in image_paths:
        try:
            data = path.read_bytes()
            digest = hashlib.sha256(data).hexdigest()

            if digest in hashes:
                continue

            hashes.add(digest)
            unique_paths.append(path)

        except Exception:
            continue

    log(f"VALID ARTICLE PHOTOS: {len(unique_paths)}")

    return unique_paths[:MAX_PHOTOS]


# ============================================================
# FONT HELPERS
# ============================================================

def find_font(preferred_names, size):
    for directory in FONT_DIRS:
        if not directory.exists():
            continue

        for name in preferred_names:
            direct = directory / name

            if direct.exists():
                try:
                    return ImageFont.truetype(
                        str(direct),
                        size
                    )
                except Exception:
                    pass

        try:
            for candidate in directory.rglob("*.ttf"):
                lower = candidate.name.lower()

                for preferred in preferred_names:
                    if preferred.lower() in lower:
                        try:
                            return ImageFont.truetype(
                                str(candidate),
                                size
                            )
                        except Exception:
                            pass
        except Exception:
            pass

    return ImageFont.load_default()


def get_fonts():
    headline = find_font(
        [
            "DejaVuSans-Bold.ttf",
            "LiberationSans-Bold.ttf",
            "NotoSans-Bold.ttf",
        ],
        76
    )

    county = find_font(
        [
            "DejaVuSans-Bold.ttf",
            "LiberationSans-Bold.ttf",
            "NotoSans-Bold.ttf",
        ],
        42
    )

    body = find_font(
        [
            "DejaVuSans.ttf",
            "LiberationSans-Regular.ttf",
            "NotoSans-Regular.ttf",
        ],
        34
    )

    label = find_font(
        [
            "DejaVuSans-Bold.ttf",
            "LiberationSans-Bold.ttf",
            "NotoSans-Bold.ttf",
        ],
        30
    )

    return headline, county, body, label


# ============================================================
# IMAGE PROCESSING
# ============================================================

def crop_to_cover(image, width, height):
    source = image.convert("RGB")

    sw, sh = source.size

    source_ratio = sw / sh
    target_ratio = width / height

    if source_ratio > target_ratio:
        new_height = height
        new_width = int(height * source_ratio)
    else:
        new_width = width
        new_height = int(width / source_ratio)

    resized = source.resize(
        (new_width, new_height),
        Image.Resampling.LANCZOS
    )

    left = max(0, (new_width - width) // 2)
    top = max(0, (new_height - height) // 2)

    return resized.crop(
        (
            left,
            top,
            left + width,
            top + height
        )
    )


def fit_inside(image, max_width, max_height):
    source = image.convert("RGB")

    sw, sh = source.size

    scale = min(
        max_width / sw,
        max_height / sh
    )

    nw = max(1, int(sw * scale))
    nh = max(1, int(sh * scale))

    return source.resize(
        (nw, nh),
        Image.Resampling.LANCZOS
    )


def rounded_rectangle_mask(size, radius):
    mask = Image.new("L", size, 0)
    draw = ImageDraw.Draw(mask)

    draw.rounded_rectangle(
        (0, 0, size[0] - 1, size[1] - 1),
        radius=radius,
        fill=255
    )

    return mask


def create_full_photo_frame(
    image_path,
    headline,
    county,
    scene_index,
    total_scenes
):
    with Image.open(image_path) as original:
        source = original.convert("RGB")

    # --------------------------------------------------------
    # Background
    # --------------------------------------------------------

    background = crop_to_cover(
        source,
        VIDEO_WIDTH,
        VIDEO_HEIGHT
    )

    background = background.filter(
        ImageFilter.GaussianBlur(BACKGROUND_BLUR)
    )

    background = background.resize(
        (VIDEO_WIDTH, VIDEO_HEIGHT),
        Image.Resampling.LANCZOS
    )

    # Darken background slightly.
    overlay_dark = Image.new(
        "RGBA",
        background.size,
        (0, 0, 0, 95)
    )

    canvas = background.convert("RGBA")
    canvas.alpha_composite(overlay_dark)

    # --------------------------------------------------------
    # Main photo
    # --------------------------------------------------------

    max_photo_width = 960
    max_photo_height = 1180

    photo = fit_inside(
        source,
        max_photo_width,
        max_photo_height
    )

    photo_x = (VIDEO_WIDTH - photo.width) // 2
    photo_y = 300

    # White photo frame.
    frame_padding = 12

    frame = Image.new(
        "RGBA",
        (
            photo.width + frame_padding * 2,
            photo.height + frame_padding * 2
        ),
        (255, 255, 255, 255)
    )

    frame.alpha_composite(
        photo.convert("RGBA"),
        (
            frame_padding,
            frame_padding
        )
    )

    canvas.alpha_composite(
        frame,
        (
            photo_x - frame_padding,
            photo_y - frame_padding
        )
    )

    # --------------------------------------------------------
    # Top branding
    # --------------------------------------------------------

    draw = ImageDraw.Draw(canvas)

    fonts = get_fonts()
    headline_font = fonts[0]
    county_font = fonts[1]
    body_font = fonts[2]
    label_font = fonts[3]

    # Brand strip.
    draw.rounded_rectangle(
        (48, 55, 500, 132),
        radius=20,
        fill=(0, 0, 0, 210)
    )

    draw.text(
        (78, 72),
        "RIFT VALLEY WATCH",
        font=label_font,
        fill=(255, 255, 255, 255)
    )

    # Breaking/news indicator.
    draw.rounded_rectangle(
        (VIDEO_WIDTH - 285, 55, VIDEO_WIDTH - 48, 132),
        radius=20,
        fill=(0, 0, 0, 210)
    )

    draw.text(
        (VIDEO_WIDTH - 255, 72),
        "NEWS UPDATE",
        font=label_font,
        fill=(255, 255, 255, 255)
    )

    # --------------------------------------------------------
    # Headline panel
    # --------------------------------------------------------

    headline_clean = clean_headline(headline)

    headline_lines = textwrap.wrap(
        headline_clean,
        width=28
    )

    headline_lines = headline_lines[:3]

    panel_height = (
        210 +
        len(headline_lines) * 86
    )

    panel_top = VIDEO_HEIGHT - panel_height - 80

    draw.rounded_rectangle(
        (
            45,
            panel_top,
            VIDEO_WIDTH - 45,
            VIDEO_HEIGHT - 80
        ),
        radius=28,
        fill=(0, 0, 0, 225)
    )

    if county:
        county_text = county.upper()

        draw.text(
            (80, panel_top + 34),
            county_text,
            font=county_font,
            fill=(255, 255, 255, 255)
        )

        headline_y = panel_top + 95

    else:
        headline_y = panel_top + 48

    for line in headline_lines:
        draw.text(
            (80, headline_y),
            line,
            font=headline_font,
            fill=(255, 255, 255, 255)
        )

        headline_y += 86

    # Scene indicator, without source information.
    scene_text = f"{scene_index}/{total_scenes}"

    bbox = draw.textbbox(
        (0, 0),
        scene_text,
        font=label_font
    )

    tw = bbox[2] - bbox[0]
    th = bbox[3] - bbox[1]

    draw.rounded_rectangle(
        (
            VIDEO_WIDTH - tw - 80,
            VIDEO_HEIGHT - 155,
            VIDEO_WIDTH - 50,
            VIDEO_HEIGHT - 105
        ),
        radius=16,
        fill=(0, 0, 0, 190)
    )

    draw.text(
        (
            VIDEO_WIDTH - tw - 65,
            VIDEO_HEIGHT - 149
        ),
        scene_text,
        font=label_font,
        fill=(255, 255, 255, 255)
    )

    # --------------------------------------------------------
    # Bottom accent line
    # --------------------------------------------------------

    draw.rectangle(
        (
            45,
            VIDEO_HEIGHT - 65,
            VIDEO_WIDTH - 45,
            VIDEO_HEIGHT - 57
        ),
        fill=(255, 255, 255, 255)
    )

    return canvas.convert("RGB")


# ============================================================
# SCENE CREATION
# ============================================================

def create_scene(
    image_path,
    headline,
    county,
    duration,
    scene_index,
    total_scenes
):
    frame_path = (
        VIDEO_WORK_DIR /
        f"scene_{scene_index:02d}.jpg"
    )

    video_path = (
        VIDEO_WORK_DIR /
        f"scene_{scene_index:02d}.mp4"
    )

    log(
        f"Creating scene {scene_index}/{total_scenes}: "
        f"{image_path.name} "
        f"({duration:.2f}s)"
    )

    frame = create_full_photo_frame(
        image_path,
        headline,
        county,
        scene_index,
        total_scenes
    )

    frame.save(
        frame_path,
        "JPEG",
        quality=95,
        optimize=True
    )

    run_command(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(frame_path),
            "-t",
            f"{duration:.3f}",
            "-vf",
            (
                f"scale={VIDEO_WIDTH}:{VIDEO_HEIGHT}:"
                f"force_original_aspect_ratio=decrease,"
                f"pad={VIDEO_WIDTH}:{VIDEO_HEIGHT}:"
                f"(ow-iw)/2:(oh-ih)/2"
            ),
            "-r",
            str(FPS),
            "-pix_fmt",
            "yuv420p",
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "22",
            "-movflags",
            "+faststart",
            str(video_path)
        ]
    )

    if not video_path.exists() or video_path.stat().st_size < 10000:
        raise RuntimeError(
            f"Scene video was not created: {video_path}"
        )

    return video_path


# ============================================================
# SCENE PLAN
# ============================================================

def build_scene_plan(image_paths, total_duration):
    if not image_paths:
        fail("No valid images available for scene generation.")

    usable = image_paths[:MAX_PHOTOS]

    if total_duration <= 17:
        scene_count = min(2, len(usable))

    elif total_duration <= 23:
        scene_count = min(3, len(usable))

    else:
        scene_count = min(4, len(usable))

    if scene_count <= 0:
        scene_count = 1

    selected_images = []

    for index in range(scene_count):
        selected_images.append(
            usable[index % len(usable)]
        )

    base_duration = total_duration / scene_count

    durations = []

    for _ in range(scene_count):
        durations.append(base_duration)

    # Ensure exact sum.
    difference = total_duration - sum(durations)

    if durations:
        durations[-1] += difference

    return list(zip(selected_images, durations))


# ============================================================
# CONCATENATE SCENES
# ============================================================

def concatenate_scenes(scene_paths, output_path):
    if not scene_paths:
        raise RuntimeError("No scene videos to concatenate.")

    concat_file = VIDEO_WORK_DIR / "concat.txt"

    with concat_file.open("w", encoding="utf-8") as f:
        for path in scene_paths:
            absolute = path.resolve()
            safe_path = str(absolute).replace("'", "'\\''")
            f.write(f"file '{safe_path}'\n")

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
            "-c",
            "copy",
            "-movflags",
            "+faststart",
            str(output_path)
        ]
    )

    if not output_path.exists():
        raise RuntimeError(
            f"Concatenated video was not created: {output_path}"
        )

    return output_path


# ============================================================
# AUDIO MUX
# ============================================================

def combine_audio(video_path, audio_path, output_path):
    duration = probe_duration(audio_path)

    log(
        f"MUXING AUDIO: {duration:.2f} seconds"
    )

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
            "-
