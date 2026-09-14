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
# VERSION: RVW_VIDEO_V32_STABLE_MULTIPHOTO
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

W, H, FPS = 1080, 1920, 30
MAX_SCENES = 6
MIN_BYTES = 10000
MIN_W, MIN_H = 400, 300

FORBIDDEN = (
    "citizen", "ctv", "world_cup", "worldcup", "avatar",
    "placeholder", "default_image", "default-image",
    "profile_picture", "profile-picture", "dummy", "generic"
)

BLACK = (8, 8, 10)
WHITE = (248, 248, 248)
GREY = (165, 165, 170)
RED = (205, 28, 38)
YELLOW = (245, 190, 45)


def ensure_dirs():
    for p in (DATA_DIR, SOURCE_DIR, WORK_DIR, AUDIO_DIR, OUTPUT_DIR):
        p.mkdir(parents=True, exist_ok=True)


def clean_work():
    for pattern in ("scene_*.jpg", "scene_*.mp4", "concat.txt",
                    "silent.mp4", "muxed.mp4"):
        for p in WORK_DIR.glob(pattern):
            try:
                p.unlink()
            except OSError:
                pass


def load_json(path):
    if not path.exists() or path.stat().st_size < 2:
        raise RuntimeError(f"Required JSON file missing or empty: {path}")
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def text(value):
    if value is None:
        return ""
    s = re.sub(r"<[^>]+>", " ", str(value))
    return re.sub(r"\s+", " ", s).strip()


def story_object(data):
    if not isinstance(data, dict):
        raise RuntimeError("selected_story.json must contain an object")

    if isinstance(data.get("story"), dict):
        return data["story"]

    if isinstance(data.get("stories"), list) and data["stories"]:
        if isinstance(data["stories"][0], dict):
            return data["stories"][0]

    if data.get("title"):
        return data

    raise RuntimeError("No story object found")


def source_name(story):
    src = story.get("source", "")

    if isinstance(src, dict):
        src = src.get("name", "")

    s = text(src)

    if "citizen" in s.lower():
        return "Rift Valley Watch"

    return s or "Rift Valley Watch"


def title(story):
    return text(story.get("title")) or "Rift Valley Update"


def county(story):
    return text(story.get("county")) or "Rift Valley"


def category(story):
    return (text(story.get("category")) or "REGIONAL NEWS").upper()


def published(story):
    return text(
        story.get("published")
        or story.get("date")
        or ""
    )


def resolve_path(value):
    if not value:
        return None

    p = Path(str(value).strip())
    choices = []

    if p.is_absolute():
        choices.append(p)
    else:
        choices.extend(
            [
                BASE_DIR / p,
                SOURCE_DIR / p.name,
            ]
        )

    for candidate in choices:
        try:
            if candidate.exists() and candidate.is_file():
                return candidate.resolve()
        except OSError:
            pass

    return None


def forbidden_path(path):
    value = str(path).lower()
    return any(term in value for term in FORBIDDEN)


def valid_image(path):
    if not path or not path.exists() or not path.is_file():
        return False

    if forbidden_path(path):
        print("REJECTED IMAGE:", path)
        return False

    try:
        if path.stat().st_size < MIN_BYTES:
            return False

        with Image.open(path) as image:
            if image.width < MIN_W or image.height < MIN_H:
                return False

            image.verify()

        return True

    except Exception:
        return False


def file_hash(path):
    digest = hashlib.sha256()

    try:
        with open(path, "rb") as f:
            for block in iter(
                lambda: f.read(1024 * 1024),
                b"",
            ):
                digest.update(block)

        return digest.hexdigest()

    except Exception:
        return ""


def perceptual_hash(path):
    try:
        with Image.open(path) as image:
            image = image.convert("L")
            image = image.resize(
                (16, 16),
                Image.Resampling.LANCZOS,
            )

            pixels = list(image.getdata())

            if not pixels:
                return ""

            average = sum(pixels) / len(pixels)

            return "".join(
                "1" if value >= average else "0"
                for value in pixels
            )

    except Exception:
        return ""


def hash_distance(a, b):
    if not a or not b or len(a) != len(b):
        return 9999

    return sum(
        left != right
        for left, right in zip(a, b)
    )


def image_candidates(story):
    candidates = []

    values = story.get(
        "image_paths",
        [],
    )

    if isinstance(values, str):
        values = [values]

    if isinstance(values, list):
        for value in values:
            path = resolve_path(value)

            if path:
                candidates.append(path)

    for key in (
        "image_path",
        "local_image",
        "image",
        "photo",
        "photo_path",
    ):
        value = story.get(key)

        if isinstance(value, list):
            for item in value:
                path = resolve_path(item)

                if path:
                    candidates.append(path)

        else:
            path = resolve_path(value)

            if path:
                candidates.append(path)

    try:
        source_files = sorted(
            SOURCE_DIR.iterdir(),
            key=lambda p: p.name.lower(),
        )
    except OSError:
        source_files = []

    for path in source_files:
        if (
            path.is_file()
            and path.name.lower().startswith("story_image")
        ):
            candidates.append(path)

    return candidates


def unique_images(story):
    result = []
    exact_hashes = set()
    visual_hashes = []
    seen_paths = set()

    for path in image_candidates(story):

        try:
            key = str(path.resolve())
        except OSError:
            continue

        if key in seen_paths:
            continue

        seen_paths.add(key)

        if not valid_image(path):
            continue

        exact = file_hash(path)

        if exact and exact in exact_hashes:
            print(
                "SKIPPED EXACT DUPLICATE:",
                path.name,
            )
            continue

        visual = perceptual_hash(path)

        if visual:
            duplicate = any(
                hash_distance(
                    visual,
                    previous,
                ) <= 8
                for previous in visual_hashes
            )

            if duplicate:
                print(
                    "SKIPPED VISUAL DUPLICATE:",
                    path.name,
                )
                continue

        if exact:
            exact_hashes.add(exact)

        if visual:
            visual_hashes.append(visual)

        result.append(path)

        if len(result) >= MAX_SCENES:
            break

    return result


def font(size, bold=False):
    if bold:
        names = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        ]
    else:
        names = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        ]

    for name in names:
        if Path(name).exists():
            try:
                return ImageFont.truetype(
                    name,
                    size,
                )
            except Exception:
                pass

    return ImageFont.load_default()


def wrap(draw, value, fnt, width):
    words = text(value).split()

    lines = []
    current = ""

    for word in words:

        trial = (
            word
            if not current
            else current + " " + word
        )

        box = draw.textbbox(
            (0, 0),
            trial,
            font=fnt,
        )

        if box[2] - box[0] <= width:
            current = trial
        else:
            if current:
                lines.append(current)

            current = word

    if current:
        lines.append(current)

    return lines


def crop_vertical(image):
    image = image.convert("RGB")

    sw, sh = image.size

    target_ratio = W / H
    source_ratio = sw / sh

    if source_ratio > target_ratio:

        new_width = int(
            sh * target_ratio
        )

        left = (
            sw - new_width
        ) // 2

        image = image.crop(
            (
                left,
                0,
                left + new_width,
                sh,
            )
        )

    else:

        new_height = int(
            sw / target_ratio
        )

        top = (
            sh - new_height
        ) // 2

        image = image.crop(
            (
                0,
                top,
                sw,
                top + new_height,
            )
        )

    return image.resize(
        (W, H),
        Image.Resampling.LANC
