from pathlib import Path
import json
import re
import subprocess
import sys
import shutil
import hashlib
import math

import requests
from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH
# VIDEO GENERATOR
# VERSION: RVW_VIDEO_V17_REAL_STORY_IMAGES_FULL_AUDIO
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

MIN_NARRATION_WORDS = 80
MAX_NARRATION_WORDS = 145

MIN_DURATION = 15
MAX_REAL_PHOTOS = 5

FPS = 30

REQUEST_TIMEOUT = 20

HEADLINE_MAX_CHARS = 68

VIDEO_VERSION = "RVW_VIDEO_V17_REAL_STORY_IMAGES_FULL_AUDIO"


# ============================================================
# DIRECTORIES
# ============================================================

for directory in [
    OUTPUT_DIR,
    AUDIO_DIR,
    SOURCE_DIR,
    VIDEO_WORK_DIR,
    DATA_DIR,
]:
    directory.mkdir(parents=True, exist_ok=True)


# ============================================================
# LOGGING
# ============================================================

def log(message):
    print(f"[RIFT VALLEY WATCH] {message}", flush=True)


def fail(message):
    print(f"\nERROR: {message}\n", flush=True)
    sys.exit(1)


# ============================================================
# COMMAND HELPERS
# ============================================================

def command_exists(command):
    return shutil.which(command) is not None


def run_command(command, description=None):
    if description:
        log(description)

    log(
        "RUNNING: "
        + " ".join(str(x) for x in command)
    )

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    if result.stdout:
        print(result.stdout, flush=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code "
            f"{result.returncode}: "
            f"{description or ' '.join(map(str, command))}"
        )

    return result


# ============================================================
# JSON
# ============================================================

def load_json(path):
    if not path.exists():
        return {}

    try:
        with open(
            path,
            "r",
            encoding="utf-8",
        ) as file:
            return json.load(file)

    except Exception as exc:
        log(
            f"Could not read JSON "
            f"{path}: {exc}"
        )
        return {}


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    if isinstance(value, (list, tuple)):
        value = " ".join(
            str(x)
            for x in value
        )

    if isinstance(value, dict):
        value = (
            value.get("text")
            or value.get("content")
            or ""
        )

    value = str(value)

    value = value.replace(
        "\r",
        " ",
    )

    value = value.replace(
        "\n",
        " ",
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


def word_count(text):
    return len(
        re.findall(
            r"\b[\w’'-]+\b",
            clean_text(text),
        )
    )


def split_sentences(text):
    text = clean_text(text)

    if not text:
        return []

    parts = re.split(
        r"(?<=[.!?])\s+",
        text,
    )

    result = []

    for part in parts:
        part = clean_text(part)

        if not part:
            continue

        if len(part) < 8:
            continue

        result.append(part)

    return result


def deduplicate_sentences(sentences):
    result = []
    seen = set()

    for sentence in sentences:
        sentence = clean_text(sentence)

        if not sentence:
            continue

        key = re.sub(
            r"[^a-z0-9]+",
            " ",
            sentence.lower(),
        ).strip()

        if key in seen:
            continue

        seen.add(key)
        result.append(sentence)

    return result


def trim_words(text, maximum):
    words = clean_text(text).split()

    if len(words) <= maximum:
        return clean_text(text)

    trimmed = " ".join(
        words[:maximum]
    )

    if not trimmed.endswith(
        (".", "!", "?")
    ):
        trimmed += "."

    return trimmed


# ============================================================
# NARRATION
# ============================================================

def get_narration():
    script = load_json(SCRIPT_FILE)
    story = load_json(STORY_FILE)

    direct_fields = [
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

    candidates = []

    for field in direct_fields:
        value = script.get(field)

        if isinstance(value, str):
            value = clean_text(value)

            if (
                word_count(value)
                >= MIN_NARRATION_WORDS
            ):
                candidates.append(value)

    for field in direct_fields:
        value = story.get(field)

        if isinstance(value, str):
            value = clean_text(value)

            if (
                word_count(value)
                >= MIN_NARRATION_WORDS
            ):
                candidates.append(value)

    if candidates:
        candidates.sort(
            key=word_count,
            reverse=True,
        )

        narration = candidates[0]

        return trim_words(
            narration,
            MAX_NARRATION_WORDS,
        )

    # --------------------------------------------------------
    # Build narration from available article content
    # --------------------------------------------------------

    source_texts = []

    preferred_fields = [
        "description",
        "summary",
        "body",
        "content",
        "article",
        "text",
    ]

    for field in preferred_fields:
        for source in [
            script,
            story,
        ]:
            value = clean_text(
                source.get(field)
            )

            if value:
                source_texts.append(value)

    title = clean_text(
        story.get("headline")
        or story.get("title")
        or script.get("headline")
        or script.get("title")
    )

    county = clean_text(
        story.get("county")
        or story.get("location")
        or script.get("county")
    )

    all_sentences = []

    for text in source_texts:
        all_sentences.extend(
            split_sentences(text)
        )

    all_sentences = deduplicate_sentences(
        all_sentences
    )

    selected = []

    if title:
        selected.append(
            title + "."
            if not title.endswith(
                (".", "!", "?")
            )
            else title
        )

    if county:
        county_sentence = (
            f"The latest development "
            f"is unfolding in {county}."
        )

        if county_sentence.lower() not in {
            x.lower()
            for x in selected
        }:
            selected.append(
                county_sentence
            )

    for sentence in all_sentences:
        candidate = " ".join(
            selected + [sentence]
        )

        if (
            word_count(candidate)
            <= MAX_NARRATION_WORDS
        ):
            selected.append(sentence)

        if (
            word_count(
                " ".join(selected)
            )
            >= MIN_NARRATION_WORDS
        ):
            break

    narration = clean_text(
        " ".join(selected)
    )

    if (
        word_count(narration)
        < MIN_NARRATION_WORDS
    ):
        combined = " ".join(
            source_texts
        )

        narration = clean_text(
            f"{title}. {combined}"
            if title
            else combined
        )

    narration = trim_words(
        narration,
        MAX_NARRATION_WORDS,
    )

    return narration


# ============================================================
# AUDIO
# ============================================================

def generate_audio(narration):
    narration = clean_text(narration)

    count = word_count(narration)

    log(
        f"NARRATION WORD COUNT: {count}"
    )

    if count < MIN_NARRATION_WORDS:
        raise RuntimeError(
            f"Narration is too short: "
            f"{count} words. "
            f"Minimum required: "
            f"{MIN_NARRATION_WORDS}."
        )

    if NARRATION_FILE.exists():
        try:
            NARRATION_FILE.unlink()
        except Exception:
            pass

    log(
        "GENERATING NARRATION AUDIO"
    )

    tts = gTTS(
        text=narration,
        lang="en",
        slow=False,
    )

    tts.save(
        str(NARRATION_FILE)
    )

    if not NARRATION_FILE.exists():
        raise RuntimeError(
            "Narration MP3 was not created."
        )

    if NARRATION_FILE.stat().st_size < 1000:
        raise RuntimeError(
            "Narration MP3 appears to be invalid."
        )

    log(
        f"NARRATION CREATED: "
        f"{NARRATION_FILE}"
    )

    return NARRATION_FILE


# ============================================================
# MEDIA INFORMATION
# ============================================================

def get_media_duration(path):
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
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Could not determine media duration: "
            f"{path}\n{result.stderr}"
        )

    try:
        return float(
            result.stdout.strip()
        )

    except Exception:
        raise RuntimeError(
            f"Invalid duration returned "
            f"by ffprobe for {path}"
        )


def calculate_duration(audio_path):
    duration = get_media_duration(
        audio_path
    )

    if duration < MIN_DURATION:
        duration = MIN_DURATION

    # No artificial 60-second cap.
    # Full narration determines video duration.
    return duration


# ============================================================
# IMAGE URL HELPERS
# ============================================================

def normalise_url(url):
    url = clean_text(url)

    if not url:
        return ""

    if url.startswith("//"):
        return "https:" + url

    if url.startswith("http://"):
        return "https://" + url[7:]

    return url


def image_url_is_valid(url):
    url = normalise_url(url)

    if not url:
        return False

    lowered = url.lower()

    if lowered.startswith("data:"):
        return False

    if not lowered.startswith(
        (
            "http://",
            "https://",
        )
    ):
        return False

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
        "google",
        "youtube",
        "whatsapp",
    ]

    for term in blocked_terms:
        if term in lowered:
            return False

    return True


def collect_story_image_urls(story):
    """
    ONLY use image URLs explicitly associated
    with the selected story.

    Do NOT scrape arbitrary <img> elements
    from the article page.
    """

    fields = [
        "image_urls",
        "images",
        "article_images",
        "photos",
    ]

    single_fields = [
        "image_url",
        "image",
        "photo",
        "featured_image",
        "thumbnail",
        "imageUrl",
        "featuredImage",
    ]

    urls = []

    def add(value):
        if isinstance(value, str):
            value = normalise_url(value)

            if (
                image_url_is_valid(value)
                and value not in urls
            ):
                urls.append(value)

        elif isinstance(value, list):
            for item in value:
                add(item)

        elif isinstance(value, dict):
            for key in [
                "url",
                "src",
                "image",
                "image_url",
                "href",
            ]:
                if key in value:
                    add(value[key])

    for field in fields:
        add(story.get(field))

    for field in single_fields:
        add(story.get(field))

    return urls[:MAX_REAL_PHOTOS]


# ============================================================
# IMAGE DOWNLOAD
# ============================================================

def download_image(url, destination):
    try:
        headers = {
            "User-Agent": (
                "Mozilla/5.0 "
                "(X11; Linux x86_64) "
                "AppleWebKit/537.36 "
                "Chrome/120 Safari/537.36"
            )
        }

        response = requests.get(
            url,
            headers=headers,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )

        response.raise_for_status()

        content = response.content

        if len(content) < 5000:
            return False

        temp_file = destination.with_suffix(
            ".download"
        )

        with open(
            temp_file,
            "wb",
        ) as file:
            file.write(content)

        try:
            with Image.open(
                temp_file
            ) as image:
                image.verify()

        except Exception:
            temp_file.unlink(
                missing_ok=True
            )
            return False

        shutil.move(
            str(temp_file),
            str(destination),
        )

        return True

    except Exception as exc:
        log(
            f"Image download failed: "
            f"{url} -> {exc}"
        )
        return False


# ============================================================
# IMAGE PREPARATION
# ============================================================

def image_hash(path):
    try:
        digest = hashlib.sha1()

        with open(
            path,
            "rb",
        ) as file:
            while True:
                chunk = file.read(
                    65536
                )

                if not chunk:
                    break

                digest.update(chunk)

        return digest.hexdigest()

    except Exception:
        return ""


def validate_image(path):
    try:
        with Image.open(path) as image:
            width, height = image.size

            if (
                width < 250
                or height < 250
            ):
                return False

            image.verify()

        return True

    except Exception:
        return False


def prepare_image(
    source,
    destination,
):
    try:
        with Image.open(source) as image:
            image = image.convert("RGB")

            width, height = image.size

            if (
                width < 250
                or height < 250
            ):
                return False

            scale = max(
                WIDTH / width,
                HEIGHT / height,
                1.0,
            )

            new_width = int(
                width * scale
            )

            new_height = int(
                height * scale
            )

            image = image.resize(
                (
                    new_width,
                    new_height,
                ),
                Image.Resampling.LANCZOS,
            )

            image.save(
                destination,
                "JPEG",
                quality=94,
                optimize=True,
            )

        return True

    except Exception as exc:
        log(
            f"Could not prepare image "
            f"{source}: {exc}"
        )
        return False


def prepare_article_photos(story):
    log(
        "COLLECTING REAL ARTICLE PHOTOS"
    )

    urls = collect_story_image_urls(
        story
    )

    log(
        f"EXPLICIT STORY IMAGE URLS FOUND: "
        f"{len(urls)}"
    )

    prepared = []

    seen_hashes = set()

    # --------------------------------------------------------
    # Explicit article image URLs only
    # --------------------------------------------------------

    for index, url in enumerate(
        urls
    ):
        if len(prepared) >= MAX_REAL_PHOTOS:
            break

        raw_path = (
            VIDEO_WORK_DIR
            / f"real_article_{index + 1}_raw.jpg"
        )

        prepared_path = (
            VIDEO_WORK_DIR
            / f"real_article_{index + 1}.jpg"
        )

        if raw_path.exists():
            raw_path.unlink()

        if not download_image(
            url,
            raw_path,
        ):
            continue

        if not validate_image(
            raw_path
        ):
            raw_path.unlink(
                missing_ok=True
            )
            continue

        if not prepare_image(
            raw_path,
            prepared_path,
        ):
            raw_path.unlink(
                missing_ok=True
            )
            continue

        digest = image_hash(
            prepared_path
        )

        if (
            digest
            and digest in seen_hashes
        ):
            prepared_path.unlink(
                missing_ok=True
            )
            continue

        if digest:
            seen_hashes.add(
                digest
            )

        prepared.append(
            prepared_path
        )

        log(
            f"REAL ARTICLE PHOTO "
            f"{len(prepared)} READY"
        )

    # --------------------------------------------------------
    # Existing downloaded article image fallback
    # --------------------------------------------------------

    if (
        not prepared
        and SOURCE_IMAGE.exists()
    ):
        fallback_path = (
            VIDEO_WORK_DIR
            / "real_article_fallback.jpg"
        )

        if prepare_image(
            SOURCE_IMAGE,
            fallback_path,
        ):
            prepared.append(
                fallback_path
            )

            log(
                "USING EXISTING "
                "story_image.jpg "
                "AS ARTICLE PHOTO FALLBACK"
            )

    if not prepared:
        raise RuntimeError(
            "No valid article image "
            "was available."
        )

    log(
        f"VALID REAL ARTICLE PHOTOS "
        f"AVAILABLE: {len(prepared)}"
    )

    return prepared


# ============================================================
# FONTS
# ============================================================

def find_font(
    size,
    bold=False,
):
    if bold:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
        ]

    else:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
        ]

    for candidate in candidates:
        path = Path(candidate)

        if path.exists():
            try:
                return ImageFont.truetype(
                    str(path),
                    size=size,
                )
            except Exception:
                pass

    return ImageFont.load_default()


# ============================================================
# STORY INFORMATION
# ============================================================

def get_story_title(story):
    title = (
        story.get("headline")
        or story.get("title")
        or story.get("name")
        or "Rift Valley Watch"
    )

    return clean_text(title)


def get_story_county(story):
    county = (
        story.get("county")
        or story.get("location")
        or story.get("region")
        or "Rift Valley"
    )

    return clean_text(county)


# ============================================================
# IMAGE CROP
# ============================================================

def make_vertical_frame(
    image_path,
    output_path,
    crop_position=0.5,
):
    with Image.open(
        image_path
    ) as source:

        source = source.convert(
            "RGB"
        )

        width, height = source.size

        target_ratio = (
            WIDTH / HEIGHT
        )

        source_ratio = (
            width / height
        )

        if source_ratio > target_ratio:
            crop_width = int(
                height * target_ratio
            )

            max_left = (
                width - crop_width
            )

            left = int(
                max_left * crop_position
            )

            left = max(
                0,
                min(
                    left,
                    max_left,
                ),
            )

            box = (
                left,
                0,
                left + crop_width,
                height,
            )

        else:
            crop_height = int(
                width / target_ratio
            )

            max_top = (
                height - crop_height
            )

            top = int(
                max_top * crop_position
            )

            top = max(
                0,
                min(
                    top,
                    max_top,
                ),
            )

            box = (
                0,
                top,
                width,
                top + crop_height,
            )

        cropped = source.crop(
            box
        )

        cropped = cropped.resize(
            (
                WIDTH,
                HEIGHT,
            ),
            Image.Resampling.LANCZOS,
        )

        cropped.save(
            output_path,
            "JPEG",
            quality=94,
        )


# ============================================================
# OVERLAY
# ============================================================

def create_overlay(
    title,
    county,
    output_path,
):
    image = Image.new(
        "RGBA",
        (
            WIDTH,
            HEIGHT,
        ),
        (0, 0, 0, 0),
    )

    draw = ImageDraw.Draw(
        image
    )

    # Top branding panel.
    draw.rectangle(
        (0, 0, WIDTH, 115),
        fill=(0, 0, 0, 125),
    )

    # Bottom headline panel.
    draw.rectangle(
        (
            0,
            HEIGHT - 510,
            WIDTH,
            HEIGHT,
        ),
        fill=(0, 0, 0, 175),
    )

    # --------------------------------------------------------
    # Brand
    # --------------------------------------------------------

    brand_font = find_font(
        52,
        bold=True,
    )

    draw.text(
        (55, 32),
        "RIFT VALLEY WATCH",
        font=brand_font,
        fill=(255, 255, 255, 255),
    )

    # --------------------------------------------------------
    # County
    # --------------------------------------------------------

    county_font = find_font(
        38,
        bold=True,
    )

    draw.rounded_rectangle(
        (
            55,
            140,
            55 + 310,
            205,
        ),
        radius=12,
        fill=(210, 0, 0, 235),
    )

    draw.text(
        (75, 151),
        county.upper()[:18],
        font=county_font,
        fill=(255, 255, 255, 255),
    )

    # --------------------------------------------------------
    # Headline
    # --------------------------------------------------------

    headline_font = find_font(
        60,
        bold=True,
    )

    words = title.split()

    lines = []
    current = ""

    for word in words:
        candidate = (
            word
            if not current
            else current + " " + word
        )

        bbox = draw.textbbox(
            (0, 0),
            candidate,
            font=headline_font,
        )

        if (
            bbox[2]
            <= WIDTH - 110
        ):
            current = candidate

        else:
            if current:
                lines.append(
                    current
                )

            current = word

    if current:
        lines.append(
            current
        )

    lines = lines[:4]

    y = HEIGHT - 465

    for line in lines:
        draw.text(
            (55, y),
            line,
            font=headline_font,
            fill=(255, 255, 255, 255),
            stroke_width=2,
            stroke_fill=(0, 0, 0, 220),
        )

        y += 72

    image.save(
        output_path,
        "PNG",
    )


# ============================================================
# MOTION VIDEO
# ============================================================

def create_scene(
    image_path,
    duration,
    scene_index,
):
    scene_dir = (
        VIDEO_WORK_DIR
        / f"scene_{scene_index}"
    )

    scene_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    frame_path = (
        scene_dir / "frame.jpg"
    )

    overlay_path = (
        scene_dir / "overlay.png"
    )

    scene_video = (
        scene_dir / "scene.mp4"
    )

    # Different crop positions prevent
    # repeated scenes looking identical.
    crop_positions = [
        0.18,
        0.38,
        0.50,
        0.65,
        0.82,
    ]

    crop_position = crop_positions[
        scene_index
        % len(crop_positions)
    ]

    make_vertical_frame(
        image_path,
        frame_path,
        crop_position,
    )

    story = load_json(
        STORY_FILE
    )

    title = get_story_title(
        story
    )

    county = get_story_county(
        story
    )

    create_overlay(
        title,
        county,
        overlay_path,
    )

    zoom_direction = (
        1
        if scene_index % 2 == 0
        else -1
    )

    zoom_start = 1.00
    zoom_end = 1.10

    if zoom_direction < 0:
        zoom_start = 1.10
        zoom_end = 1.00

    frames = max(
        1,
        int(duration * FPS),
    )

    zoom_filter = (
        f"zoompan="
        f"z='"
        f"{zoom_start}+"
        f"({zoom_end}-{zoom_start})*on/{frames}"
        f"':"
        f"x='iw/2-(iw/zoom/2)':"
        f"y='ih/2-(ih/zoom/2)':"
        f"d=1:"
        f"s={WIDTH}x{HEIGHT}:"
        f"fps={FPS}"
    )

    filter_complex = (
        f"[0:v]"
        f"{zoom_filter},"
        f"scale={WIDTH}:{HEIGHT}:"
        f"force_original_aspect_ratio=decrease,"
        f"pad={WIDTH}:{HEIGHT}:"
        f"(ow-iw)/2:(oh-ih)/2,"
        f"format=yuv420p[base];"
        f"[1:v]"
        f"format=rgba[overlay];"
        f"[base][overlay]"
        f"overlay=0:0:"
        f"format=auto[v]"
    )

    command = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(frame_path),
        "-loop",
        "1",
        "-i",
        str(overlay_path),
        "-filter_complex",
        filter_complex,
        "-map",
        "[v]",
        "-t",
        f"{duration:.3f}",
        "-r",
        str(FPS),
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-an",
        str(scene_video),
    ]

    run_command(
        command,
        f"CREATING SCENE "
        f"{scene_index}",
    )

    if not scene_video.exists():
        raise RuntimeError(
            f"Scene video was not created: "
            f"{scene_video}"
        )

    return scene_video


# ============================================================
# SCENE PLAN
# ============================================================

def build_scene_plan(
    photo_paths,
    total_duration,
):
    if not photo_paths:
        raise RuntimeError(
            "No article photos available "
            "for scene creation."
        )

    count = min(
        len(photo_paths),
        MAX_REAL_PHOTOS,
    )

    photos = photo_paths[
        :count
    ]

    # One real article photo creates
    # multiple visual scenes using crops.
    scene_count = count

    if scene_count == 1:
        scene_count = 4

    selected_photos = []

    for index in range(
        scene_count
    ):
        selected_photos.append(
            photos[
                index
                % len(photos)
            ]
        )

    base_duration = (
        total_duration
        / scene_count
    )

    durations = []

    for index in range(
        scene_count
    ):
        if (
            index
            == scene_count - 1
        ):
            used = sum(
                durations
            )

            duration = (
                total_duration
                - used
            )

        else:
            duration = (
                base_duration
            )

        durations.append(
            duration
        )

    return list(
        zip(
            selected_photos,
            durations,
        )
    )


# ============================================================
# CONCATENATE SCENES
# ============================================================

def concatenate_scenes(
    scene_videos,
):
    if not scene_videos:
        raise RuntimeError(
            "No scene videos were created."
        )

    concat_file = (
        VIDEO_WORK_DIR
        / "scenes.txt"
    )

    silent_video = (
        VIDEO_WORK_DIR
        / "silent_video.mp4"
    )

    with open(
        concat_file,
        "w",
        encoding="utf-8",
    ) as file:

        for scene in scene_videos:
            absolute_path = (
                scene.resolve()
            )

            escaped = str(
                absolute_path
            ).replace(
                "'",
                "'\\''",
            )

            file.write(
                f"file '{escaped}'\n"
            )

    command = [
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
        "20",
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(FPS),
        str(silent_video),
    ]

    run_command(
        command,
        "COMBINING ALL VIDEO SCENES",
    )

    if not silent_video.exists():
        raise RuntimeError(
            "Combined silent video "
            "was not created."
        )

    return silent_video


# ============================================================
# AUDIO MUX
# ============================================================

def combine_audio(
    silent_video,
    audio_path,
    output_path,
    target_duration,
):
    log(
        "MUXING FULL NARRATION "
        "INTO FINAL VIDEO"
    )

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(silent_video),
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
        "192k",
        "-ar",
        "44100",
        "-t",
        f"{target_duration:.3f}",
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    # No "-shortest".
    #
    # Narration duration is the master duration.
    # This prevents premature ending.

    run_command(
        command,
        "CREATING FINAL MP4",
    )

    if not output_path.exists():
        raise RuntimeError(
            "Final MP4 was not created."
        )

    return output_path


# ============================================================
# FINAL QUALITY CONTROL
# ============================================================

def final_qc(
    video_path,
    expected_audio_duration,
):
    log("=" * 60)
    log(
        "FINAL VIDEO QUALITY CONTROL"
    )
    log("=" * 60)

    if not video_path.exists():
        raise RuntimeError(
            "Final MP4 does not exist."
        )

    if video_path.stat().st_size < 100000:
        raise RuntimeError(
            "Final MP4 is suspiciously small."
        )

    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "stream="
            "index,"
            "codec_type,"
            "codec_name,"
            "width,"
            "height,"
            "duration",
            "-show_entries",
            "format=duration,size",
            "-of",
            "json",
            str(video_path),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if probe.returncode != 0:
        raise RuntimeError(
            "Final MP4 failed "
            "ffprobe validation."
        )

    try:
        info = json.loads(
            probe.stdout
        )

    except Exception:
        raise RuntimeError(
            "Could not parse final MP4 "
            "ffprobe output."
        )

    streams = info.get(
        "streams",
        [],
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
            "Final MP4 contains "
            "no video stream."
        )

    if audio_stream is None:
        raise RuntimeError(
            "Final MP4 contains "
            "no audio stream."
        )

    width = int(
        video_stream.get(
            "width"
        )
        or 0
    )

    height = int(
        video_stream.get(
            "height"
        )
        or 0
    )

    if (
        width != WIDTH
        or height != HEIGHT
    ):
        raise RuntimeError(
            f"Wrong video resolution: "
            f"{width}x{height}. "
            f"Expected "
            f"{WIDTH}x{HEIGHT}."
        )

    video_duration = (
        get_media_duration(
            video_path
        )
    )

    audio_duration = float(
        audio_stream.get(
            "duration"
        )
        or expected_audio_duration
    )

    log(
        f"FINAL VIDEO DURATION: "
        f"{video_duration:.2f}s"
    )

    log(
        f"FINAL AUDIO DURATION: "
        f"{audio_duration:.2f}s"
    )

    log(
        f"EXPECTED NARRATION "
        f"DURATION: "
        f"{expected_audio_duration:.2f}s"
    )

    difference = abs(
        video_duration
        - expected_audio_duration
    )

    if difference > 1.5:
        raise RuntimeError(
            "Final video duration "
            "does not match the "
            "full narration duration."
        )

    if (
        audio_duration
        < expected_audio_duration - 1.5
    ):
        raise RuntimeError(
            "Audio appears to have "
            "been prematurely truncated."
        )

    log(
        "RESOLUTION: 1080x1920"
    )

    log(
        "AUDIO: PRESENT"
    )

    log(
        "FULL NARRATION: PRESENT"
    )

    log(
        "FINAL QC: PASSED"
    )

    return True


# ============================================================
# CLEAN WORK DIRECTORY
# ============================================================

def clean_work_directory():
    if not VIDEO_WORK_DIR.exists():
        VIDEO_WORK_DIR.mkdir(
            parents=True,
            exist_ok=True,
        )
        return

    for item in VIDEO_WORK_DIR.iterdir():
        try:
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

        except Exception as exc:
            log(
                f"Could not remove "
                f"{item}: {exc}"
            )


# ============================================================
# MAIN
# ============================================================

def main():
    print()
    print("=" * 70)
    print("RIFT VALLEY WATCH")
    print("VIDEO GENERATOR")
    print("=" * 70)
    print(
        f"GENERATOR VERSION: "
        f"{VIDEO_VERSION}"
    )
    print("=" * 70)
    print()

    if not command_exists(
        "ffmpeg"
    ):
        fail(
            "FFmpeg is not installed "
            "or not available."
        )

    if not command_exists(
        "ffprobe"
    ):
        fail(
            "FFprobe is not installed "
            "or not available."
        )

    if not STORY_FILE.exists():
        fail(
            f"Selected story file "
            f"not found: {STORY_FILE}"
        )

    story = load_json(
        STORY_FILE
    )

    if not story:
        fail(
            "selected_story.json "
            "is empty."
        )

    log(
        f"HEADLINE: "
        f"{get_story_title(story)}"
    )

    log(
        f"COUNTY: "
        f"{get_story_county(story)}"
    )

    # --------------------------------------------------------
    # Clean video working files only.
    # --------------------------------------------------------

    clean_work_directory()

    # --------------------------------------------------------
    # NARRATION
    # --------------------------------------------------------

    narration = get_narration()

    if (
        word_count(narration)
        < MIN_NARRATION_WORDS
    ):
        fail(
            f"Narration has only "
            f"{word_count(narration)} "
            f"words. Minimum is "
            f"{MIN_NARRATION_WORDS}."
        )

    narration = trim_words(
        narration,
        MAX_NARRATION_WORDS,
    )

    log(
        f"FINAL NARRATION "
        f"WORD COUNT: "
        f"{word_count(narration)}"
    )

    log(
        "NARRATION:"
    )

    print(
        narration,
        flush=True,
    )

    # --------------------------------------------------------
    # AUDIO
    # --------------------------------------------------------

    audio_path = generate_audio(
        narration
    )

    audio_duration = (
        calculate_duration(
            audio_path
        )
    )

    log(
        f"FULL AUDIO DURATION: "
        f"{audio_duration:.2f}s"
    )

    # --------------------------------------------------------
    # ARTICLE PHOTOS
    # --------------------------------------------------------

    photos = prepare_article_photos(
        story
    )

    log(
        f"REAL ARTICLE PHOTO COUNT: "
        f"{len(photos)}"
    )

    # --------------------------------------------------------
    # SCENE PLAN
    # --------------------------------------------------------

    scene_plan = build_scene_plan(
        photos,
        audio_duration,
    )

    log(
        f"TOTAL VIDEO SCENES: "
        f"{len(scene_plan)}"
    )

    scene_videos = []

    for index, (
        photo,
        duration,
    ) in enumerate(
        scene_plan,
        start=1,
    ):
        log(
            f"SCENE {index}: "
            f"{photo.name} "
            f"FOR {duration:.2f}s"
        )

        scene_video = create_scene(
            photo,
            duration,
            index - 1,
        )

        scene_videos.append(
            scene_video
        )

    # --------------------------------------------------------
    # CONCATENATE SCENES
    # --------------------------------------------------------

    silent_video = concatenate_scenes(
        scene_videos
    )

    # --------------------------------------------------------
    # OUTPUT
    # --------------------------------------------------------

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if FINAL_VIDEO.exists():
        try:
            FINAL_VIDEO.unlink()

        except Exception as exc:
            raise RuntimeError(
                f"Could not remove "
                f"existing final MP4: "
                f"{exc}"
            )

    # --------------------------------------------------------
    # MUX FULL AUDIO
    # --------------------------------------------------------

    combine_audio(
        silent_video,
        audio_path,
        FINAL_VIDEO,
        audio_duration,
    )

    # --------------------------------------------------------
    # FINAL QC
    # --------------------------------------------------------

    final_qc(
        FINAL_VIDEO,
        audio_duration,
    )

    # --------------------------------------------------------
    # SUCCESS
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print(
        "RIFT VALLEY WATCH "
        "VIDEO GENERATION SUCCESSFUL"
    )
    print("=" * 70)

    print(
        f"FINAL MP4: "
        f"{FINAL_VIDEO}"
    )

    print(
        f"DURATION: "
        f"{get_media_duration(FINAL_VIDEO):.2f}s"
    )

    print(
        f"SIZE: "
        f"{FINAL_VIDEO.stat().st_size / (1024 * 1024):.2f} MB"
    )

    print(
        f"REAL ARTICLE "
        f"PHOTOS/SCENES: "
        f"{len(scene_plan)}"
    )

    print("=" * 70)
    print()


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    try:
        main()

    except KeyboardInterrupt:
        print()
        print(
            "Generation cancelled."
        )
        sys.exit(1)

    except Exception as exc:
        print()
        print("=" * 70)
        print(
            "GENERATION FAILED"
        )
        print("=" * 70)
        print(
            str(exc)
        )
        print("=" * 70)
        sys.exit(1)
