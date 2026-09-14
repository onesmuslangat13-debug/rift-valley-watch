from pathlib import Path
import json
import re
import subprocess
import sys
import shutil
import traceback
import hashlib

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH
# VIDEO GENERATOR
# VERSION: RVW_VIDEO_V20_REAL_PHOTO_FILTER
# ============================================================

VERSION = "RVW_VIDEO_V20_REAL_PHOTO_FILTER"

BASE_DIR = Path(__file__).resolve().parent

OUTPUT_DIR = BASE_DIR / "output"
DATA_DIR = BASE_DIR / "data"
SOURCE_DIR = BASE_DIR / "assets" / "source"
WORK_DIR = BASE_DIR / "assets" / "video_work"
AUDIO_DIR = BASE_DIR / "audio"

STORY_FILE = DATA_DIR / "selected_story.json"
SCRIPT_FILE = DATA_DIR / "selected_script.json"

FINAL_VIDEO = OUTPUT_DIR / "rift_valley_watch_reel.mp4"
NARRATION_FILE = AUDIO_DIR / "narration.mp3"

WIDTH = 1080
HEIGHT = 1920
FPS = 30

MIN_REEL_DURATION = 15.0
MAX_REEL_DURATION = 30.0
SAFE_AUDIO_MAX = 29.0

MIN_NARRATION_WORDS = 40
MAX_NARRATION_WORDS = 68

MAX_PHOTOS = 5
MAX_SCENES = 4

REQUEST_TIMEOUT = 20

MIN_IMAGE_WIDTH = 350
MIN_IMAGE_HEIGHT = 250
MIN_IMAGE_AREA = 150000

USER_AGENT = (
    "Mozilla/5.0 "
    "(Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/120.0 Safari/537.36"
)

BAD_IMAGE_TERMS = [
    "avatar",
    "default-avatar",
    "default_avatar",
    "placeholder",
    "profile-picture",
    "profile_picture",
    "profile-image",
    "profile_image",
    "user-image",
    "user_image",
    "anonymous",
    "no-image",
    "no_image",
    "noimage",
    "missing-image",
    "missing_image",
    "generic-image",
    "generic_image",
    "dummy",
    "thumbnail-placeholder",
    "logo",
    "icon",
    "favicon",
    "sprite",
    "world-cup",
    "world_cup",
    "worldcup",
    "advert",
    "advertisement",
    "banner",
    "loading",
    "loader",
    "1x1",
    "pixel"
]


# ============================================================
# LOGGING
# ============================================================

def log(message=""):
    print(f"[RIFT VALLEY WATCH] {message}", flush=True)


def section(title):
    print("", flush=True)
    print("=" * 70, flush=True)
    print(f"[RIFT VALLEY WATCH] {title}", flush=True)
    print("=" * 70, flush=True)


# ============================================================
# DIRECTORIES
# ============================================================

def prepare_directories():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# COMMANDS
# ============================================================

def require_command(command):
    if shutil.which(command) is None:
        raise RuntimeError(
            f"Required command not found: {command}"
        )


def run_command(command):
    log("RUNNING: " + " ".join(str(x) for x in command))

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    if result.stdout:
        print(result.stdout, flush=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}"
        )

    return result


# ============================================================
# JSON
# ============================================================

def load_json(path):
    if not path.exists():
        raise RuntimeError(
            f"Required file not found: {path}"
        )

    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)

    except Exception as exc:
        raise RuntimeError(
            f"Could not read {path}: {exc}"
        )


# ============================================================
# TEXT
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    text = str(value)

    text = re.sub(
        r"<[^>]+>",
        " ",
        text
    )

    text = re.sub(
        r"https?://\S+",
        " ",
        text
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def word_count(text):
    return len(
        re.findall(
            r"\b[\w’'-]+\b",
            text
        )
    )


def split_sentences(text):
    text = clean_text(text)

    if not text:
        return []

    parts = re.split(
        r"(?<=[.!?])\s+",
        text
    )

    result = []

    for part in parts:
        part = part.strip()

        if not part:
            continue

        if word_count(part) < 4:
            continue

        result.append(part)

    return result


def clean_headline(value):
    text = clean_text(value)

    text = re.sub(
        r"\s*\|\s*(KBC(?: Digital)?|Citizen(?: Digital)?|The Star|Nation|Nation Africa|Daily Nation)\s*$",
        "",
        text,
        flags=re.IGNORECASE
    )

    text = re.sub(
        r"\s*-\s*(KBC(?: Digital)?|Citizen(?: Digital)?|The Star|Nation|Nation Africa|Daily Nation)\s*$",
        "",
        text,
        flags=re.IGNORECASE
    )

    return text.strip(" -|")


def first_value(data, keys):
    if not isinstance(data, dict):
        return ""

    for key in keys:
        value = data.get(key)

        if isinstance(value, str):
            value = clean_text(value)

            if value:
                return value

    return ""


# ============================================================
# STORY
# ============================================================

def get_headline(story):
    headline = first_value(
        story,
        [
            "headline",
            "title",
            "story_title",
            "name"
        ]
    )

    return clean_headline(headline)


def collect_text_fields(data):
    if not isinstance(data, dict):
        return []

    fields = [
        "narration",
        "script",
        "voiceover",
        "summary",
        "description",
        "content",
        "body",
        "article_text",
        "text",
        "story",
        "details",
        "excerpt"
    ]

    result = []

    for field in fields:
        value = data.get(field)

        if isinstance(value, str):
            value = clean_text(value)

            if value:
                result.append(value)

    article = data.get("article")

    if isinstance(article, dict):
        for field in fields:
            value = article.get(field)

            if isinstance(value, str):
                value = clean_text(value)

                if value:
                    result.append(value)

    return result


def build_narration(story, script):
    headline = get_headline(story)

    blocks = []

    blocks.extend(
        collect_text_fields(script)
    )

    blocks.extend(
        collect_text_fields(story)
    )

    sentences = []

    if headline:
        sentences.append(
            headline + "."
        )

    for block in blocks:
        for sentence in split_sentences(block):
            if sentence not in sentences:
                sentences.append(sentence)

    if not sentences:
        raise RuntimeError(
            "No usable narration text was found."
        )

    result = []
    total = 0

    for sentence in sentences:
        count = word_count(sentence)

        if total >= MAX_NARRATION_WORDS:
            break

        result.append(sentence)
        total += count

        if total >= MAX_NARRATION_WORDS:
            break

    return " ".join(result).strip()


def shorten_narration(text, target_words):
    sentences = split_sentences(text)

    if not sentences:
        words = text.split()

        return " ".join(
            words[:target_words]
        )

    result = []
    total = 0

    for sentence in sentences:
        count = word_count(sentence)

        if total + count <= target_words:
            result.append(sentence)
            total += count
        else:
            break

        if total >= target_words:
            break

    shortened = " ".join(result).strip()

    if word_count(shortened) < MIN_NARRATION_WORDS:
        words = text.split()

        shortened = " ".join(
            words[:target_words]
        )

    return shortened


# ============================================================
# IMAGE URL COLLECTION
# ============================================================

def add_image_value(value, urls):
    if not value:
        return

    if isinstance(value, str):
        value = value.strip()

        if value.startswith("http"):
            if value not in urls:
                urls.append(value)

        return

    if isinstance(value, list):
        for item in value:
            add_image_value(
                item,
                urls
            )

        return

    if isinstance(value, dict):
        for key in [
            "url",
            "src",
            "href",
            "image",
            "image_url",
            "original",
            "contentUrl",
            "content_url"
        ]:
            if key in value:
                add_image_value(
                    value.get(key),
                    urls
                )


def collect_image_urls(story):
    urls = []

    fields = [
        "image_urls",
        "images",
        "photos",
        "article_images",
        "image_candidates",
        "image_url",
        "image",
        "photo",
        "thumbnail"
    ]

    for field in fields:
        add_image_value(
            story.get(field),
            urls
        )

    article = story.get("article")

    if isinstance(article, dict):
        for field in fields:
            add_image_value(
                article.get(field),
                urls
            )

    return urls[:MAX_PHOTOS]


# ============================================================
# IMAGE VALIDATION
# ============================================================

def normalise_url(url):
    return clean_text(url).lower()


def url_looks_bad(url):
    value = normalise_url(url)

    for term in BAD_IMAGE_TERMS:
        if term in value:
            return True

    return False


def image_hash(path):
    try:
        with Image.open(path) as image:
            image = image.convert("RGB")
            image.thumbnail((64, 64))

            return hashlib.md5(
                image.tobytes()
            ).hexdigest()

    except Exception:
        return ""


def verify_image(path):
    try:
        with Image.open(path) as image:
            image.verify()

        return True

    except Exception:
        return False


def image_is_valid_news_photo(path, url):
    if not path.exists():
        return False, "file does not exist"

    if url_looks_bad(url):
        return False, "URL looks like a placeholder, logo or banner"

    if not verify_image(path):
        return False, "invalid image file"

    try:
        with Image.open(path) as image:
            width, height = image.size

            if width < MIN_IMAGE_WIDTH:
                return False, f"image too narrow: {width}px"

            if height < MIN_IMAGE_HEIGHT:
                return False, f"image too short: {height}px"

            if width * height < MIN_IMAGE_AREA:
                return False, "image area is too small"

            ratio = width / height

            if ratio < 0.55:
                return False, "portrait profile-style image"

            if ratio > 4.5:
                return False, "extremely wide banner image"

            if width <= 500 and height <= 500:
                return False, "small square image"

            if width == height:
                return False, "square image"

            extrema = image.convert("RGB").getextrema()

            if all(
                channel_min >= 245 and channel_max >= 245
                for channel_min, channel_max in extrema
            ):
                return False, "blank white image"

            if all(
                channel_min <= 8 and channel_max <= 12
                for channel_min, channel_max in extrema
            ):
                return False, "blank black image"

    except Exception as exc:
        return False, f"image inspection failed: {exc}"

    return True, "accepted"


# ============================================================
# IMAGE DOWNLOAD
# ============================================================

def download_image(url, number):
    log(
        f"Checking article photo {number}: {url}"
    )

    if url_looks_bad(url):
        log(
            "REJECTED BEFORE DOWNLOAD: "
            "placeholder, logo, banner or unrelated asset"
        )

        return None

    try:
        response = requests.get(
            url,
            timeout=REQUEST_TIMEOUT,
            headers={
                "User-Agent": USER_AGENT,
                "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8"
            },
            allow_redirects=True
        )

        response.raise_for_status()

        if not response.content:
            log("Rejected empty image response")
            return None

        path = (
            SOURCE_DIR /
            f"story_image_{number}.jpg"
        )

        with path.open("wb") as handle:
            handle.write(response.content)

        valid, reason = image_is_valid_news_photo(
            path,
            url
        )

        if not valid:
            log(
                f"REJECTED IMAGE {number}: {reason}"
            )

            path.unlink(
                missing_ok=True
            )

            return None

        image_signature = image_hash(path)

        if not image_signature:
            log(
                f"REJECTED IMAGE {number}: "
                "could not create image signature"
            )

            path.unlink(
                missing_ok=True
            )

            return None

        log(
            f"ACCEPTED IMAGE {number}: "
            f"{path.name}"
        )

        return {
            "path": path,
            "url": url,
            "hash": image_signature
        }

    except Exception as exc:
        log(
            f"Image download failed: {exc}"
        )

        return None


def clean_old_source_images():
    for item in SOURCE_DIR.glob("story_image_*.jpg"):
        try:
            item.unlink()
        except Exception:
            pass

    compatibility = SOURCE_DIR / "story_image.jpg"

    try:
        compatibility.unlink(
            missing_ok=True
        )
    except Exception:
        pass


def download_story_images(story):
    section(
        "SELECTING REAL ARTICLE PHOTOS"
    )

    clean_old_source_images()

    urls = collect_image_urls(story)

    log(
        f"Explicit article image URLs: "
        f"{len(urls)}"
    )

    if not urls:
        raise RuntimeError(
            "selected_story.json contains no "
            "explicit article image URLs."
        )

    accepted = []
    accepted_hashes = set()

    for number, url in enumerate(
        urls,
        start=1
    ):
        result = download_image(
            url,
            number
        )

        if not result:
            continue

        signature = result["hash"]

        if signature in accepted_hashes:
            log(
                "REJECTED DUPLICATE IMAGE: "
                f"{result['path'].name}"
            )

            result["path"].unlink(
                missing_ok=True
            )

            continue

        accepted_hashes.add(signature)
        accepted.append(result)

        if len(accepted) >= MAX_SCENES:
            break

    if not accepted:
        raise RuntimeError(
            "No genuine article photos could be downloaded."
        )

    compatibility = (
        SOURCE_DIR /
        "story_image.jpg"
    )

    try:
        shutil.copy2(
            accepted[0]["path"],
            compatibility
        )
    except Exception as exc:
        log(
            f"Compatibility image copy failed: {exc}"
        )

    log(
        f"VALID ARTICLE PHOTOS: "
        f"{len(accepted)}"
    )

    for item in accepted:
        log(
            f"PHOTO: {item['path'].name}"
        )

    return [
        item["path"]
        for item in accepted
    ]


# ============================================================
# FONTS
# ============================================================

def get_font(size, bold=False):
    if bold:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            "C:/Windows/Fonts/arialbd.ttf"
        ]

    else:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "C:/Windows/Fonts/arial.ttf"
        ]

    for candidate in candidates:
        path = Path(candidate)

        if path.exists():
            try:
                return ImageFont.truetype(
                    str(path),
                    size
                )

            except Exception:
                pass

    return ImageFont.load_default()


# ============================================================
# IMAGE LAYOUT
# ============================================================

def resize_cover(image, width, height):
    image = image.convert("RGB")

    scale = max(
        width / image.width,
        height / image.height
    )

    new_width = int(
        image.width * scale
    )

    new_height = int(
        image.height * scale
    )

    image = image.resize(
        (new_width, new_height),
        Image.Resampling.LANCZOS
    )

    left = max(
        0,
        (new_width - width) // 2
    )

    top = max(
        0,
        (new_height - height) // 2
    )

    return image.crop(
        (
            left,
            top,
            left + width,
            top + height
        )
    )


def resize_inside(image, width, height):
    image = image.convert("RGB")

    scale = min(
        width / image.width,
        height / image.height
    )

    new_width = max(
        1,
        int(image.width * scale)
    )

    new_height = max(
        1,
        int(image.height * scale)
    )

    return image.resize(
        (
            new_width,
            new_height
        ),
        Image.Resampling.LANCZOS
    )


def wrap_text(text, font, max_width, draw):
    words = text.split()

    lines = []
    current = ""

    for word in words:
        candidate = (
            word
            if not current
            else current + " " + word
        )

        box = draw.textbbox(
            (0, 0),
            candidate,
            font=font
        )

        if box[2] - box[0] <= max_width:
            current = candidate

        else:
            if current:
                lines.append(current)

            current = word

    if current:
        lines.append(current)

    return lines


def make_scene_frame(
    image_path,
    headline,
    scene_number,
    scene_total
):
    with Image.open(image_path) as source:
        source = source.convert("RGB")

        background = resize_cover(
            source,
            WIDTH,
            HEIGHT
        )

        background = background.filter(
            ImageFilter.GaussianBlur(24)
        )

        canvas = background.copy()

        dark = Image.new(
            "RGBA",
            (
                WIDTH,
                HEIGHT
            ),
            (0, 0, 0, 85)
        )

        canvas = Image.alpha_composite(
            canvas.convert("RGBA"),
            dark
        )

        photo = resize_inside(
            source,
            WIDTH - 70,
            HEIGHT - 500
        )

        photo_x = (
            WIDTH - photo.width
        ) // 2

        photo_y = 205

        shadow = Image.new(
            "RGBA",
            (
                photo.width + 30,
                photo.height + 30
            ),
            (0, 0, 0, 0)
        )

        shadow_draw = ImageDraw.Draw(
            shadow
        )

        shadow_draw.rounded_rectangle(
            (
                10,
                10,
                photo.width + 20,
                photo.height + 20
            ),
            radius=20,
            fill=(0, 0, 0, 150)
        )

        canvas.alpha_composite(
            shadow,
            (
                photo_x - 5,
                photo_y - 5
            )
        )

        canvas.alpha_composite(
            photo.convert("RGBA"),
            (
                photo_x,
                photo_y
            )
        )

        draw = ImageDraw.Draw(
            canvas
        )

        draw.rectangle(
            (
                0,
                0,
                WIDTH,
                140
            ),
            fill=(5, 15, 28, 245)
        )

        brand_font = get_font(
            45,
            bold=True
        )

        draw.text(
            (
                45,
                35
            ),
            "RIFT VALLEY WATCH",
            font=brand_font,
            fill=(255, 255, 255)
        )

        if scene_total > 1:
            scene_font = get_font(
                25,
                bold=True
            )

            label = (
                f"{scene_number}/"
                f"{scene_total}"
            )

            box = draw.textbbox(
                (
                    0,
                    0
                ),
                label,
                font=scene_font
            )

            box_width = (
                box[2] -
                box[0] +
                35
            )

            draw.rounded_rectangle(
                (
                    WIDTH - box_width - 35,
                    40,
                    WIDTH - 35,
                    92
                ),
                radius=18,
                fill=(255, 255, 255, 35)
            )

            draw.text(
                (
                    WIDTH - box_width - 17,
                    50
                ),
                label,
                font=scene_font,
                fill=(255, 255, 255)
            )

        panel_top = HEIGHT - 470

        draw.rounded_rectangle(
            (
                30,
                panel_top,
                WIDTH - 30,
                HEIGHT - 30
            ),
            radius=28,
            fill=(5, 12, 24, 242)
        )

        headline_font = get_font(
            42,
            bold=True
        )

        lines = wrap_text(
            headline,
            headline_font,
            WIDTH - 110,
            draw
        )

        y = panel_top + 38

        for line in lines[:5]:
            draw.text(
                (
                    58,
                    y
                ),
                line,
                font=headline_font,
                fill=(255, 255, 255)
            )

            y += 57

        small_font = get_font(
            21,
            bold=True
        )

        draw.text(
            (
                58,
                HEIGHT - 72
            ),
            "LATEST REGIONAL UPDATE",
            font=small_font,
            fill=(220, 230, 240)
        )

        return canvas.convert("RGB")


# ============================================================
# TTS
# ============================================================

def audio_duration(path):
    result = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(path)
        ]
    )

    value = result.stdout.strip()

    try:
        return float(value)

    except Exception:
        raise RuntimeError(
            "Could not determine narration duration."
        )


def generate_tts(text):
    if NARRATION_FILE.exists():
        NARRATION_FILE.unlink()

    log(
        f"Generating narration: "
        f"{word_count(text)} words"
    )

    speech = gTTS(
        text=text,
        lang="en",
        slow=False
    )

    speech.save(
        str(NARRATION_FILE)
    )

    if not NARRATION_FILE.exists():
        raise RuntimeError(
            "gTTS did not create narration.mp3."
        )

    duration = audio_duration(
        NARRATION_FILE
    )

    log(
        f"TTS duration: "
        f"{duration:.2f}s"
    )

    return duration


def create_safe_narration(base_text):
    section(
        "AUTOMATIC NARRATION LENGTH CONTROL"
    )

    candidates = []

    original = clean_text(
        base_text
    )

    candidates.append(original)

    for target in [
        64,
        60,
        56,
        52,
        48,
        45,
        42,
        40
    ]:
        candidate = shorten_narration(
            original,
            target
        )

        if (
            candidate
            and candidate not in candidates
        ):
            candidates.append(candidate)

    best_text = None
    best_duration = None

    for number, candidate in enumerate(
        candidates,
        start=1
    ):
        count = word_count(
            candidate
        )

        if count < MIN_NARRATION_WORDS:
            continue

        log(
            f"ATTEMPT {number}: "
            f"{count} words"
        )

        try:
            duration = generate_tts(
                candidate
            )

            if (
                best_duration is None
                or duration < best_duration
            ):
                best_duration = duration
                best_text = candidate

            if duration <= SAFE_AUDIO_MAX:
                log(
                    "SAFE TTS LENGTH FOUND"
                )

                return (
                    candidate,
                    duration
                )

        except Exception as exc:
            log(
                f"TTS attempt failed: {exc}"
            )

    if (
        best_text
        and best_duration is not None
        and best_duration <= MAX_REEL_DURATION + 1
    ):
        return (
            best_text,
            best_duration
        )

    raise RuntimeError(
        "Could not create narration within "
        "the 30-second reel limit."
    )


# ============================================================
# SCENES
# ============================================================

def clean_work_directory():
    if not WORK_DIR.exists():
        WORK_DIR.mkdir(
            parents=True,
            exist_ok=True
        )

    for item in WORK_DIR.iterdir():
        try:
            if item.is_file():
                item.unlink()

            elif item.is_dir():
                shutil.rmtree(item)

        except Exception:
            pass


def prepare_scene_frames(
    images,
    headline
):
    section(
        "CREATING MULTIPLE PHOTO SCENES"
    )

    clean_work_directory()

    selected = images[:MAX_SCENES]

    if len(selected) == 1:
        selected = [
            selected[0],
            selected[0],
            selected[0]
        ]

    total = len(selected)

    frames = []

    for index, image_path in enumerate(
        selected,
        start=1
    ):
        frame = make_scene_frame(
            image_path,
            headline,
            index,
            total
        )

        frame_path = (
            WORK_DIR /
            f"scene_{index:02d}.jpg"
        )

        frame.save(
            frame_path,
            "JPEG",
            quality=95
        )

        frames.append(
            frame_path
        )

        log(
            f"SCENE {index}: "
            f"{image_path.name}"
        )

    return frames


def scene_durations(
    total_duration,
    number
):
    if number <= 1:
        return [
            total_duration
        ]

    base = (
        total_duration /
        number
    )

    durations = [
        base
        for _ in range(number)
    ]

    if number >= 3:
        durations[0] += 0.3
        durations[-1] -= 0.3

    return durations


def render_scene(
    frame,
    duration,
    output
):
    run_command(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(frame),
            "-t",
            f"{duration:.3f}",
            "-vf",
            (
                f"scale={WIDTH}:{HEIGHT}:"
                "force_original_aspect_ratio=decrease,"
                f"pad={WIDTH}:{HEIGHT}:"
                "(ow-iw)/2:(oh-ih)/2"
            ),
            "-r",
            str(FPS),
            "-c:v",
            "libx264",
            "-preset",
            "veryfast",
            "-crf",
            "20",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(output)
        ]
    )


def build_silent_video(
    frames,
    duration
):
    section(
        "BUILDING SILENT VIDEO"
    )

    durations = scene_durations(
        duration,
        len(frames)
    )

    scene_files = []

    for index, (
        frame,
        scene_duration
    ) in enumerate(
        zip(frames, durations),
        start=1
    ):
        scene_file = (
            WORK_DIR /
            f"video_scene_{index:02d}.mp4"
        )

        log(
            f"Rendering scene {index}: "
            f"{scene_duration:.2f}s"
        )

        render_scene(
            frame,
            scene_duration,
            scene_file
        )

        scene_files.append(
            scene_file
        )

    concat_file = (
        WORK_DIR /
        "concat.txt"
    )

    with concat_file.open(
        "w",
        encoding="utf-8"
    ) as handle:
        for scene in scene_files:
            path = str(
                scene.resolve()
            )

            path = path.replace(
                "'",
                "'\\''"
            )

            handle.write(
                "file '" +
                path +
                "'\n"
            )

    silent_video = (
        WORK_DIR /
        "silent_video.mp4"
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
            "-c",
            "copy",
            "-an",
            str(silent_video)
        ]
    )

    if not silent_video.exists():
        raise RuntimeError(
            "Silent video was not created."
        )

    return silent_video


# ============================================================
# AUDIO + VIDEO
# ============================================================

def combine_audio(
    video,
    audio,
    duration
):
    section(
        "COMBINING VIDEO AND NARRATION"
    )

    if FINAL_VIDEO.exists():
        FINAL_VIDEO.unlink()

    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video),
            "-i",
            str(audio),
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
            f"{duration:.3f}",
            "-movflags",
            "+faststart",
            str(FINAL_VIDEO)
        ]
    )

    if not FINAL_VIDEO.exists():
        raise RuntimeError(
            "Final MP4 was not created."
        )


# ============================================================
# FINAL QC
# ============================================================

def final_qc():
    section(
        "FINAL MP4 QUALITY CONTROL"
    )

    if not FINAL_VIDEO.exists():
        raise RuntimeError(
            "Final MP4 does not exist."
        )

    result = run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            (
                "stream=codec_type,codec_name,"
                "width,height,duration:"
                "format=duration"
            ),
            "-of",
            "json",
            str(FINAL_VIDEO)
        ]
    )

    try:
        info = json.loads(
            result.stdout
        )

    except Exception as exc:
        raise RuntimeError(
            f"Could not parse ffprobe: {exc}"
        )

    streams = info.get(
        "streams",
        []
    )

    video_stream = None
    audio_stream = None

    for stream in streams:
        if (
            stream.get("codec_type")
            == "video"
        ):
            video_stream = stream

        if (
            stream.get("codec_type")
            == "audio"
        ):
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
        video_stream.get(
            "width",
            0
        )
    )

    height = int(
        video_stream.get(
            "height",
            0
        )
    )

    duration = float(
        info.get(
            "format",
            {}
        ).get(
            "duration",
            0
        )
    )

    log(
        f"FINAL RESOLUTION: "
        f"{width}x{height}"
    )

    log(
        f"FINAL DURATION: "
        f"{duration:.2f}s"
    )

    log(
        f"VIDEO CODEC: "
        f"{video_stream.get('codec_name')}"
    )

    log(
        f"AUDIO CODEC: "
        f"{audio_stream.get('codec_name')}"
    )

    if width != WIDTH:
        raise RuntimeError(
            f"Wrong video width: {width}"
        )

    if height != HEIGHT:
        raise RuntimeError(
            f"Wrong video height: {height}"
        )

    if duration < MIN_REEL_DURATION:
        raise RuntimeError(
            f"Video too short: {duration:.2f}s"
        )

    if duration > MAX_REEL_DURATION + 1:
        raise RuntimeError(
            f"Video too long: {duration:.2f}s"
        )

    size_mb = (
        FINAL_VIDEO.stat().st_size /
        1024 /
        1024
    )

    log(
        f"FINAL FILE SIZE: "
        f"{size_mb:.2f} MB"
    )

    if size_mb < 0.05:
        raise RuntimeError(
            "Final MP4 is suspiciously small."
        )

    log(
        "FINAL QC PASSED"
    )


# ============================================================
# MAIN
# ============================================================

def main():
    section(VERSION)

    log(
        "VIDEO GENERATOR STARTED"
    )

    log(
        f"BASE DIRECTORY: {BASE_DIR}"
    )

    prepare_directories()

    require_command(
        "ffmpeg"
    )

    require_command(
        "ffprobe"
    )

    section(
        "LOADING SELECTED STORY"
    )

    story = load_json(
        STORY_FILE
    )

    script = {}

    if SCRIPT_FILE.exists():
        try:
            script = load_json(
                SCRIPT_FILE
            )

        except Exception as exc:
            log(
                f"Warning: selected_script.json "
                f"could not be loaded: {exc}"
            )

    if not isinstance(
        story,
        dict
    ):
        raise RuntimeError(
            "selected_story.json must contain an object."
        )

    if not isinstance(
        script,
        dict
    ):
        script = {}

    headline = get_headline(
        story
    )

    county = first_value(
        story,
        [
            "county",
            "location",
            "region"
        ]
    )

    log(
        f"HEADLINE: {headline}"
    )

    log(
        f"COUNTY: "
        f"{county or 'Not specified'}"
    )

    section(
        "PREPARING NARRATION"
    )

    base_narration = build_narration(
        story,
        script
    )

    log(
        f"BASE NARRATION WORDS: "
        f"{word_count(base_narration)}"
    )

    narration, duration = (
        create_safe_narration(
            base_narration
        )
    )

    log(
        f"FINAL NARRATION WORD COUNT: "
        f"{word_count(narration)}"
    )

    log(
        f"FINAL NARRATION: "
        f"{narration}"
    )

    log(
        f"FINAL AUDIO DURATION: "
        f"{duration:.2f}s"
    )

    if duration > SAFE_AUDIO_MAX:
        raise RuntimeError(
            f"Narration remains too long: "
            f"{duration:.2f}s"
        )

    images = download_story_images(
        story
    )

    frames = prepare_scene_frames(
        images,
        headline
    )

    if not frames:
        raise RuntimeError(
            "No video scenes were created."
        )

    silent_video = build_silent_video(
        frames,
        duration
    )

    combine_audio(
        silent_video,
        NARRATION_FILE,
        duration
    )

    final_qc()

    section(
        "GENERATION COMPLETE"
    )

    log(
        f"MP4 CREATED: "
        f"{FINAL_VIDEO}"
    )

    log(
        f"ABSOLUTE PATH: "
        f"{FINAL_VIDEO.resolve()}"
    )

    log(
        "Rift Valley Watch MP4 generated successfully."
    )

    return 0


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    try:
        sys.exit(
            main()
        )

    except KeyboardInterrupt:
        section(
            "GENERATION CANCELLED"
        )

        sys.exit(130)

    except Exception as exc:
        section(
            "GENERATION FAILED"
        )

        log(
            f"ERROR: {exc}"
        )

        traceback.print_exc()

        sys.exit(1)
