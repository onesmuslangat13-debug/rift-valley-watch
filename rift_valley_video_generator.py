from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont, ImageFilter


# ============================================================
# RIFT VALLEY WATCH - VIDEO GENERATOR
# VERSION: RVW_VIDEO_V33_SYNTAX_STABLE_MULTIPHOTO
#
# PURPOSE
# - Read selected_story.json and selected_script.json
# - Use only valid real article photographs
# - Remove duplicate or near-duplicate images
# - Create one scene per genuinely unique photo
# - Never display a fake scene counter
# - Avoid Citizen TV and unrelated placeholder graphics
# - Create a professional 1080x1920 vertical news reel
# - Add narration and validate the final MP4
# ============================================================


BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
SOURCE_DIR = BASE_DIR / "assets" / "source"
WORK_DIR = BASE_DIR / "assets" / "video_work"
AUDIO_DIR = BASE_DIR / "audio"
OUTPUT_DIR = BASE_DIR / "output"

STORY_FILE = DATA_DIR / "selected_story.json"
SCRIPT_FILE = DATA_DIR / "selected_script.json"
AUDIO_FILE = AUDIO_DIR / "narration.mp3"
FINAL_FILE = OUTPUT_DIR / "rift_valley_watch_reel.mp4"

WIDTH = 1080
HEIGHT = 1920
FPS = 30

MIN_IMAGE_BYTES = 10_000
MIN_VIDEO_BYTES = 100_000

FORBIDDEN_IMAGE_TERMS = (
    "citizen",
    "ctv",
    "world_cup",
    "worldcup",
    "avatar",
    "placeholder",
    "default_image",
    "default-image",
    "profile_picture",
    "profile-picture",
    "dummy",
    "generic",
    "logo",
    "icon",
)


# ============================================================
# BASIC HELPERS
# ============================================================

def print_banner(message):
    print()
    print("=" * 72)
    print(message)
    print("=" * 72)


def ensure_directories():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


def run_command(command, description):
    print()
    print("RUNNING:", description)
    print("COMMAND:", " ".join(str(item) for item in command))

    result = subprocess.run(
        command,
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    print(result.stdout)

    if result.returncode != 0:
        raise RuntimeError(
            f"{description} failed with exit code {result.returncode}"
        )

    return result.stdout


def load_json(path):
    if not path.exists():
        raise RuntimeError(f"Required JSON file does not exist: {path}")

    try:
        with path.open("r", encoding="utf-8") as handle:
            value = json.load(handle)
    except Exception as exc:
        raise RuntimeError(f"Could not read JSON file {path}: {exc}") from exc

    if not isinstance(value, (dict, list)):
        raise RuntimeError(f"JSON file is not an object or list: {path}")

    return value


def save_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)

    with path.open("w", encoding="utf-8") as handle:
        json.dump(value, handle, ensure_ascii=False, indent=2)


def safe_text(value):
    if value is None:
        return ""

    if isinstance(value, (dict, list)):
        return ""

    return str(value).strip()


def clean_text(value, fallback=""):
    text = safe_text(value)

    text = re.sub(r"\s+", " ", text)
    text = text.replace("\x00", "")
    text = text.strip()

    return text or fallback


def source_name(story):
    source = story.get("source", "")

    if isinstance(source, dict):
        name = clean_text(source.get("name"), "Rift Valley Watch")
    else:
        name = clean_text(source, "Rift Valley Watch")

    lowered = name.lower()

    if "citizen" in lowered or lowered == "ctv":
        return "Rift Valley Watch"

    return name


def story_title(story):
    return clean_text(
        story.get("title")
        or story.get("headline")
        or story.get("name"),
        "Rift Valley Regional Update",
    )


def story_county(story):
    return clean_text(
        story.get("county")
        or story.get("location")
        or story.get("region"),
        "Rift Valley",
    )


def story_category(story):
    return clean_text(
        story.get("category")
        or story.get("section")
        or story.get("topic"),
        "REGIONAL UPDATE",
    ).upper()


def story_summary(story):
    return clean_text(
        story.get("summary")
        or story.get("description")
        or story.get("details")
        or story.get("body"),
        "",
    )


def story_facts(story):
    facts = story.get("verified_facts", [])

    if not isinstance(facts, list):
        return []

    result = []

    for item in facts:
        if not isinstance(item, dict):
            continue

        label = clean_text(item.get("label"))
        value = clean_text(item.get("value"))

        if label and value:
            result.append((label.upper(), value))

    return result[:5]


# ============================================================
# IMAGE VALIDATION
# ============================================================

def is_forbidden_image(path):
    name = path.name.lower()
    full_name = str(path).lower()

    for term in FORBIDDEN_IMAGE_TERMS:
        if term in name or term in full_name:
            return True

    return False


def valid_image(path):
    if not path:
        return False

    path = Path(path)

    if not path.exists():
        return False

    if not path.is_file():
        return False

    if is_forbidden_image(path):
        return False

    try:
        if path.stat().st_size < MIN_IMAGE_BYTES:
            return False

        with Image.open(path) as image:
            image.verify()

        with Image.open(path) as image:
            width, height = image.size

        if width < 400 or height < 300:
            return False

        return True

    except Exception:
        return False


def image_hash(path):
    try:
        with Image.open(path) as image:
            image = image.convert("RGB")
            image.thumbnail((64, 64))
            return hashlib.sha256(image.tobytes()).hexdigest()
    except Exception:
        return ""


def perceptual_hash(path):
    try:
        with Image.open(path) as image:
            image = image.convert("L")
            image = image.resize((16, 16))
            pixels = list(image.getdata())
            average = sum(pixels) / len(pixels)

            return "".join(
                "1" if pixel >= average else "0"
                for pixel in pixels
            )
    except Exception:
        return ""


def hamming_distance(first, second):
    if not first or not second:
        return 999

    if len(first) != len(second):
        return 999

    return sum(
        1
        for left, right in zip(first, second)
        if left != right
    )


def unique_images(paths):
    selected = []
    exact_hashes = set()
    perceptual_hashes = []

    for path in paths:
        path = Path(path)

        if not valid_image(path):
            continue

        exact = image_hash(path)

        if exact and exact in exact_hashes:
            continue

        perceptual = perceptual_hash(path)

        if perceptual:
            too_similar = any(
                hamming_distance(perceptual, previous) <= 8
                for previous in perceptual_hashes
            )

            if too_similar:
                continue

        selected.append(path)

        if exact:
            exact_hashes.add(exact)

        if perceptual:
            perceptual_hashes.append(perceptual)

        if len(selected) >= 6:
            break

    return selected


def collect_image_candidates(story):
    candidates = []

    image_fields = (
        "image_paths",
        "images",
        "image_path",
        "local_image",
        "photo",
        "photo_path",
        "image",
    )

    for field in image_fields:
        value = story.get(field)

        if isinstance(value, list):
            for item in value:
                if isinstance(item, dict):
                    item = (
                        item.get("local_path")
                        or item.get("path")
                        or item.get("file")
                        or item.get("image_path")
                    )

                if item:
                    candidates.append(Path(str(item)))

        elif isinstance(value, str):
            candidates.append(Path(value))

    expanded = []

    for path in candidates:
        if not path.is_absolute():
            expanded.append(BASE_DIR / path)
            expanded.append(DATA_DIR / path)
            expanded.append(SOURCE_DIR / path)
        else:
            expanded.append(path)

    for pattern in (
        "story_image*",
        "article_image*",
        "photo*",
        "*.jpg",
        "*.jpeg",
        "*.png",
        "*.webp",
    ):
        expanded.extend(SOURCE_DIR.glob(pattern))

    result = []
    seen = set()

    for path in expanded:
        try:
            resolved = path.resolve()
        except Exception:
            resolved = path

        if str(resolved) in seen:
            continue

        seen.add(str(resolved))
        result.append(resolved)

    return result


# ============================================================
# FONT AND DRAWING HELPERS
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

    candidates.extend(
        [
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
        ]
    )

    for candidate in candidates:
        path = Path(candidate)

        if path.exists():
            try:
                return ImageFont.truetype(str(path), size=size)
            except Exception:
                pass

    return ImageFont.load_default()


def fit_text(draw, text, font, max_width):
    text = clean_text(text)

    if not text:
        return ""

    if draw.textbbox((0, 0), text, font=font)[2] <= max_width:
        return text

    words = text.split()
    output = ""

    for word in words:
        trial = f"{output} {word}".strip()

        if draw.textbbox((0, 0), trial, font=font)[2] <= max_width:
            output = trial
        else:
            break

    return output or text[:40]


def wrap_text(draw, text, font, max_width, max_lines=5):
    words = clean_text(text).split()

    if not words:
        return []

    lines = []
    current = ""

    for word in words:
        trial = f"{current} {word}".strip()
        width = draw.textbbox((0, 0), trial, font=font)[2]

        if width <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)

            current = word

            if len(lines) >= max_lines:
                break

    if current and len(lines) < max_lines:
        lines.append(current)

    if len(lines) == max_lines and len(words) > 0:
        last = lines[-1]

        if not last.endswith("…"):
            lines[-1] = last.rstrip(". ") + "…"

    return lines


def draw_text_block(
    draw,
    text,
    x,
    y,
    width,
    font,
