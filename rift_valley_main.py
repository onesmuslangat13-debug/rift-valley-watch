import os
import re
import json
import math
import shutil
import hashlib
import subprocess
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from PIL import Image, ImageOps, ImageEnhance, ImageFilter
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH
# MULTI-VISUAL VIDEO GENERATOR
# ============================================================

VERSION = "RVW_VIDEO_V17_MULTI_VISUAL"

print("=" * 72)
print(f"RIFT VALLEY WATCH VIDEO GENERATOR - {VERSION}")
print("=" * 72)


# ============================================================
# DIRECTORIES
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

OUTPUT_DIR = BASE_DIR / "output"
DATA_DIR = BASE_DIR / "data"
ASSET_DIR = BASE_DIR / "assets" / "source"
WORK_DIR = BASE_DIR / "assets" / "video_work"
AUDIO_DIR = BASE_DIR / "audio"

OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
DATA_DIR.mkdir(parents=True, exist_ok=True)
ASSET_DIR.mkdir(parents=True, exist_ok=True)
WORK_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# FILES
# ============================================================

STORY_FILE = DATA_DIR / "selected_story.json"
SCRIPT_FILE = DATA_DIR / "selected_script.json"

FINAL_IMAGE = ASSET_DIR / "story_image.jpg"

AUDIO_FILE = AUDIO_DIR / "narration.mp3"

OUTPUT_FILE = OUTPUT_DIR / "rift_valley_watch_reel.mp4"


# ============================================================
# VIDEO SETTINGS
# ============================================================

WIDTH = 1080
HEIGHT = 1920

FPS = 30

VIDEO_BITRATE = "5M"

MAX_ARTICLE_IMAGES = 6

MIN_IMAGE_WIDTH = 300
MIN_IMAGE_HEIGHT = 200

SCENE_MIN_SECONDS = 3.5
SCENE_MAX_SECONDS = 7.0

REQUEST_TIMEOUT = 20

USER_AGENT = (
    "Mozilla/5.0 (X11; Linux x86_64) "
    "AppleWebKit/537.36 "
    "(KHTML, like Gecko) "
    "Chrome/130.0 Safari/537.36"
)


# ============================================================
# HTTP SESSION
# ============================================================

SESSION = requests.Session()

SESSION.headers.update(
    {
        "User-Agent": USER_AGENT,
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,image/avif,image/webp,"
            "*/*;q=0.8"
        ),
        "Accept-Language": "en-US,en;q=0.9",
    }
)


# ============================================================
# LOGGING
# ============================================================

def log(message):
    print(f"[RVW] {message}")


# ============================================================
# JSON LOADING
# ============================================================

def load_json(path):
    if not path.exists():
        raise RuntimeError(
            f"Required file does not exist: {path}"
        )

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        raise RuntimeError(
            f"Could not read JSON file {path}: {exc}"
        )


# ============================================================
# STORY
# ============================================================

story = load_json(STORY_FILE)
script_data = load_json(SCRIPT_FILE)


def get_story_value(keys, default=""):
    for key in keys:
        value = story.get(key)

        if value is not None:
            value = str(value).strip()

            if value:
                return value

    return default


headline = get_story_value(
    [
        "title",
        "headline",
        "name",
    ],
    "Rift Valley Watch",
)

county = get_story_value(
    [
        "county",
        "location",
        "region",
    ],
    "Rift Valley",
)

article_url = get_story_value(
    [
        "url",
        "article_url",
        "link",
    ],
    "",
)


# ============================================================
# SCRIPT EXTRACTION
# ============================================================

if isinstance(script_data, dict):

    narration = ""

    for key in [
        "script",
        "narration",
        "voiceover",
        "text",
    ]:
        value = script_data.get(key)

        if value:
            narration = str(value).strip()
            break

else:
    narration = str(script_data).strip()


if not narration:
    raise RuntimeError(
        "Narration script is empty."
    )


log(f"HEADLINE: {headline}")
log(f"COUNTY: {county}")
log(f"ARTICLE URL: {article_url}")
log(f"NARRATION WORDS: {len(narration.split())}")


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_text(text):
    text = str(text)

    text = re.sub(
        r"https?://\S+",
        "",
        text,
        flags=re.IGNORECASE,
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


narration = clean_text(narration)


# ============================================================
# IMAGE HELPERS
# ============================================================

def absolute_url(base_url, value):
    if not value:
        return ""

    value = str(value).strip()

    if value.startswith("//"):
        return "https:" + value

    return urljoin(base_url, value)


def looks_like_image_url(url):
    if not url:
        return False

    lowered = url.lower()

    blocked = [
        "logo",
        "icon",
        "avatar",
        "favicon",
        "sprite",
        "placeholder",
        "advert",
        "banner-ad",
        "tracking",
        "pixel",
        "emoji",
    ]

    for word in blocked:
        if word in lowered:
            return False

    extensions = [
        ".jpg",
        ".jpeg",
        ".png",
        ".webp",
        ".avif",
    ]

    parsed = urlparse(lowered)

    path = parsed.path

    if any(path.endswith(ext) for ext in extensions):
        return True

    return True


def image_score(url):
    lowered = url.lower()

    score = 0

    positive = [
        "article",
        "news",
        "story",
        "featured",
        "hero",
        "main",
        "content",
        "upload",
        "media",
        "image",
        "photo",
    ]

    negative = [
        "logo",
        "icon",
        "avatar",
        "profile",
        "banner",
        "advert",
        "thumbnail",
        "placeholder",
    ]

    for word in positive:
        if word in lowered:
            score += 2

    for word in negative:
        if word in lowered:
            score -= 5

    return score


# ============================================================
# COLLECT ARTICLE IMAGE URLS
# ============================================================

def collect_article_image_urls(url):

    if not url:
        return []

    log("Collecting additional article images...")

    try:
        response = SESSION.get(
            url,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )

        response.raise_for_status()

    except Exception as exc:
        log(
            f"Could not fetch article page for images: {exc}"
        )

        return []

    final_url = response.url

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    candidates = []

    def add_candidate(value, priority=0):

        if not value:
            return

        value = absolute_url(
            final_url,
            value,
        )

        if not value:
            return

        if value.startswith("data:"):
            return

        if not value.startswith("http"):
            return

        if not looks_like_image_url(value):
            return

        candidates.append(
            (
                priority,
                image_score(value),
                value,
            )
        )

    # --------------------------------------------------------
    # OpenGraph
    # --------------------------------------------------------

    for tag in soup.find_all(
        "meta",
        attrs={"property": "og:image"},
    ):

        add_candidate(
            tag.get("content"),
            100,
        )

    # --------------------------------------------------------
    # Twitter image
    # --------------------------------------------------------

    for tag in soup.find_all(
        "meta",
        attrs={"name": "twitter:image"},
    ):

        add_candidate(
            tag.get("content"),
            90,
        )

    for tag in soup.find_all(
        "meta",
        attrs={"property": "twitter:image"},
    ):

        add_candidate(
            tag.get("content"),
            90,
        )

    # --------------------------------------------------------
    # Article image meta
    # --------------------------------------------------------

    for tag in soup.find_all(
        "meta",
        attrs={"name": "image"},
    ):

        add_candidate(
            tag.get("content"),
            80,
        )

    # --------------------------------------------------------
    # IMG tags
    # --------------------------------------------------------

    for img in soup.find_all("img"):

        attrs = img.attrs

        values = [
            attrs.get("src"),
            attrs.get("data-src"),
            attrs.get("data-lazy-src"),
            attrs.get("data-original"),
            attrs.get("data-image"),
        ]

        srcset = attrs.get("srcset")

        if srcset:
            parts = srcset.split(",")

            for part in parts:

                part = part.strip()

                if not part:
                    continue

                pieces = part.split()

                if pieces:
                    values.append(
                        pieces[0]
                    )

        for value in values:

            add_candidate(
                value,
                40,
            )

    # --------------------------------------------------------
    # SOURCE tags
    # --------------------------------------------------------

    for source in soup.find_all("source"):

        srcset = source.get("srcset")

        if not srcset:
            continue

        for part in srcset.split(","):

            pieces = part.strip().split()

            if pieces:
                add_candidate(
                    pieces[0],
                    35,
                )

    # --------------------------------------------------------
    # Remove duplicates
    # --------------------------------------------------------

    unique = {}

    for priority, score, url_value in candidates:

        key = url_value.split("?")[0].lower()

        if key not in unique:
            unique[key] = (
                priority,
                score,
                url_value,
            )
        else:
            old = unique[key]

            if (priority, score) > (
                old[0],
                old[1],
            ):
                unique[key] = (
                    priority,
                    score,
                    url_value,
                )

    results = list(
        unique.values()
    )

    results.sort(
        key=lambda item: (
            item[0],
            item[1],
        ),
        reverse=True,
    )

    urls = [
        item[2]
        for item in results
    ]

    log(
        f"Found {len(urls)} candidate image URLs."
    )

    return urls


# ============================================================
# DOWNLOAD IMAGE
# ============================================================

def download_image(
    url,
    output_path,
):

    try:

        response = SESSION.get(
            url,
            timeout=REQUEST_TIMEOUT,
            stream=True,
            allow_redirects=True,
        )

        response.raise_for_status()

        content_type = (
            response.headers
            .get("content-type", "")
            .lower()
        )

        if (
            content_type
            and not content_type.startswith("image/")
        ):

            log(
                f"Rejected non-image response: {url}"
            )

            return False

        temp_path = output_path.with_suffix(
            ".download"
        )

        with open(
            temp_path,
            "wb",
        ) as f:

            for chunk in response.iter_content(
                chunk_size=65536
            ):

                if chunk:
                    f.write(chunk)

        try:

            with Image.open(temp_path) as image:

                image.load()

                width, height = image.size

                if (
                    width < MIN_IMAGE_WIDTH
                    or height < MIN_IMAGE_HEIGHT
                ):

                    log(
                        f"Rejected small image "
                        f"{width}x{height}: {url}"
                    )

                    temp_path.unlink(
                        missing_ok=True
                    )

                    return False

                image.verify()

        except Exception as exc:

            log(
                f"Invalid image: {url} - {exc}"
            )

            temp_path.unlink(
                missing_ok=True
            )

            return False

        temp_path.replace(
            output_path
        )

        return True

    except Exception as exc:

        log(
            f"Image download failed: {url} - {exc}"
        )

        return False


# ============================================================
# BUILD REAL IMAGE SET
# ============================================================

def prepare_real_images():

    for old in WORK_DIR.glob(
        "article_image_*.*"
    ):

        try:
            old.unlink()
        except Exception:
            pass

    urls = collect_article_image_urls(
        article_url
    )

    # Main image from the main pipeline goes first.
    existing_candidates = []

    if FINAL_IMAGE.exists():
        existing_candidates.append(
            FINAL_IMAGE
        )

    downloaded_images = []

    # --------------------------------------------------------
    # First: preserve the main selected image
    # --------------------------------------------------------

    if FINAL_IMAGE.exists():

        try:

            with Image.open(
                FINAL_IMAGE
            ) as img:

                img.load()

                if (
                    img.width >= MIN_IMAGE_WIDTH
                    and img.height >= MIN_IMAGE_HEIGHT
                ):

                    main_copy = (
                        WORK_DIR
                        / "article_image_01.jpg"
                    )

                    converted = img.convert(
                        "RGB"
                    )

                    converted.save(
                        main_copy,
                        "JPEG",
                        quality=94,
                        optimize=True,
                    )

                    downloaded_images.append(
                        main_copy
                    )

                    log(
                        "Main article image accepted."
                    )

        except Exception as exc:

            log(
                f"Main article image could not be used: {exc}"
            )

    # --------------------------------------------------------
    # Download additional images
    # --------------------------------------------------------

    image_number = 2

    seen_hashes = set()

    for url in urls:

        if (
            len(downloaded_images)
            >= MAX_ARTICLE_IMAGES
        ):
            break

        temp_path = (
            WORK_DIR
            / f"article_image_{image_number:02d}.jpg"
        )

        if not download_image(
            url,
            temp_path,
        ):
            continue

        try:

            with Image.open(
                temp_path
            ) as img:

                img.load()

                # Create a small fingerprint to prevent
                # downloading the exact same image twice.
                fingerprint_source = (
                    img.convert("RGB")
                    .resize((32, 32))
                )

                fingerprint = hashlib.md5(
                    fingerprint_source.tobytes()
                ).hexdigest()

                if fingerprint in seen_hashes:

                    temp_path.unlink(
                        missing_ok=True
                    )

                    continue

                seen_hashes.add(
                    fingerprint
                )

        except Exception:

            temp_path.unlink(
                missing_ok=True
            )

            continue

        downloaded_images.append(
            temp_path
        )

        log(
            f"Accepted article image "
            f"{len(downloaded_images)}: {url}"
        )

        image_number += 1

    # --------------------------------------------------------
    # If article only has one image, retain it.
    # The scene builder will create different visual
    # treatments from that genuine image.
    # --------------------------------------------------------

    if not downloaded_images:

        raise RuntimeError(
            "No usable article image was available."
        )

    log(
        f"REAL ARTICLE IMAGES AVAILABLE: "
        f"{len(downloaded_images)}"
    )

    return downloaded_images


# ============================================================
# IMAGE VISUAL TREATMENTS
# ============================================================

def fit_cover(
    image,
    width,
    height,
    crop_focus=0.5,
    scale=1.0,
):

    image = image.convert(
        "RGB"
    )

    target_ratio = width / height

    image_ratio = image.width / image.height

    if image_ratio > target_ratio:

        crop_height = image.height

        crop_width = int(
            crop_height * target_ratio
        )

        extra = image.width - crop_width

        left = int(
            extra * crop_focus
        )

        right = left + crop_width

        image = image.crop(
            (
                left,
                0,
                right,
                image.height,
            )
        )

    else:

        crop_width = image.width

        crop_height = int(
            crop_width / target_ratio
        )

        extra = image.height - crop_height

        top = int(
            extra * crop_focus
        )

        bottom = top + crop_height

        image = image.crop(
            (
                0,
                top,
                image.width,
                bottom,
            )
        )

    image = image.resize(
        (
            width,
            height,
        ),
        Image.Resampling.LANCZOS,
    )

    if scale != 1.0:

        sw = int(
            width * scale
        )

        sh = int(
            height * scale
        )

        image = image.resize(
            (
                sw,
                sh,
            ),
            Image.Resampling.LANCZOS,
        )

        left = max(
            0,
            (sw - width) // 2,
        )

        top = max(
            0,
            (sh - height) // 2,
        )

        image = image.crop(
            (
                left,
                top,
                left + width,
                top + height,
            )
        )

    return image


def make_visual_variants(
    image_path,
    scene_index,
):

    with Image.open(
        image_path
    ) as source:

        source.load()

        image = source.convert(
            "RGB"
        )

    variants = []

    # Different focal positions create visually distinct
    # compositions even when only one real article photo exists.

    focal_positions = [
        0.20,
        0.38,
        0.52,
        0.68,
        0.82,
    ]

    focal = focal_positions[
        scene_index
        % len(focal_positions)
    ]

    scale_values = [
        1.00,
        1.08,
        1.15,
        1.22,
        1.30,
    ]

    scale = scale_values[
        scene_index
        % len(scale_values)
    ]

    visual = fit_cover(
        image,
        WIDTH,
        HEIGHT,
        crop_focus=focal,
        scale=scale,
    )

    # Subtle professional image treatment.
    if scene_index % 4 == 1:

        visual = ImageEnhance.Contrast(
            visual
        ).enhance(1.06)

    elif scene_index % 4 == 2:

        visual = ImageEnhance.Color(
            visual
        ).enhance(0.94)

    elif scene_index % 4 == 3:

        visual = ImageEnhance.Brightness(
            visual
        ).enhance(0.96)

    # Very subtle sharpening.
    visual = visual.filter(
        ImageFilter.UnsharpMask(
            radius=1.2,
            percent=70,
            threshold=3,
        )
    )

    variants.append(
        visual
    )

    return variants


# ============================================================
# NEWS GRAPHICS
# ============================================================

def draw_news_overlay(
    image,
    county_text,
    headline_text,
):

    # Work in RGBA for clean overlays.
    canvas = image.convert(
        "RGBA"
    )

    # --------------------------------------------------------
    # Top dark broadcast strip
    # --------------------------------------------------------

    top_height = 150

    top = Image.new(
        "RGBA",
        (
            WIDTH,
            top_height,
        ),
        (
            0,
            0,
            0,
            205,
        ),
    )

    canvas.alpha_composite(
        top,
        (
            0,
            0,
        ),
    )

    # --------------------------------------------------------
    # Bottom gradient-like dark area
    # --------------------------------------------------------

    bottom_height = 500

    bottom = Image.new(
        "RGBA",
        (
            WIDTH,
            bottom_height,
        ),
        (
            0,
            0,
            0,
            185,
        ),
    )

    canvas.alpha_composite(
        bottom,
        (
            0,
            HEIGHT - bottom_height,
        ),
    )

    # --------------------------------------------------------
    # Text rendering is intentionally done with FFmpeg later.
    # The image itself remains clean.
    # --------------------------------------------------------

    return canvas.convert(
        "RGB"
    )


# ============================================================
# CREATE SCENE IMAGE
# ============================================================

def create_scene_image(
    source_path,
    scene_number,
):

    scene_path = (
        WORK_DIR
        / f"scene_{scene_number:02d}.jpg"
    )

    with Image.open(
        source_path
    ) as image:

        image.load()

        visual = fit_cover(
            image,
            WIDTH,
            HEIGHT,
            crop_focus=[
                0.15,
                0.30,
                0.48,
                0.65,
                0.82,
            ][
                (scene_number - 1) % 5
            ],
            scale=[
                1.00,
                1.08,
                1.15,
                1.22,
                1.30,
            ][
                (scene_number - 1) % 5
            ],
        )

    visual = draw_news_overlay(
        visual,
        county,
        headline,
    )

    visual.save(
        scene_path,
        "JPEG",
        quality=95,
        optimize=True,
    )

    return scene_path


# ============================================================
# NARRATION AUDIO
# ============================================================

def create_narration():

    if AUDIO_FILE.exists():

        try:

            if AUDIO_FILE.stat().st_size > 5000:

                log(
                    "Existing narration found."
                )

                return AUDIO_FILE

        except Exception:
            pass

    log(
        "Generating narration with Google TTS..."
    )

    temp_audio = (
        AUDIO_FILE.with_suffix(
            ".tmp.mp3"
        )
    )

    try:

        tts = gTTS(
            text=narration,
            lang="en",
            slow=False,
        )

        tts.save(
            str(temp_audio)
        )

        if (
            not temp_audio.exists()
            or temp_audio.stat().st_size < 5000
        ):

            raise RuntimeError(
                "gTTS produced an invalid audio file."
            )

        temp_audio.replace(
            AUDIO_FILE
        )

    except Exception as exc:

        temp_audio.unlink(
            missing_ok=True
        )

        raise RuntimeError(
            f"Narration generation failed: {exc}"
        )

    log(
        f"Narration created: "
        f"{AUDIO_FILE.stat().st_size} bytes"
    )

    return AUDIO_FILE


# ============================================================
# AUDIO DURATION
# ============================================================

def get_media_duration(
    path,
):

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
            f"ffprobe failed: {result.stderr}"
        )

    try:
        duration = float(
            result.stdout.strip()
        )
    except Exception:
        raise RuntimeError(
            "Could not determine media duration."
        )

    if duration <= 0:
        raise RuntimeError(
            "Media duration is invalid."
        )

    return duration


# ============================================================
# SCENE COUNT
# ============================================================

def calculate_scene_count(
    duration,
    image_count,
):

    # Aim for approximately one visual every
    # 4-6 seconds.

    desired = int(
        math.ceil(
            duration / 5.0
        )
    )

    desired = max(
        4,
        desired,
    )

    desired = min(
        8,
        desired,
    )

    # Never exceed what can be visually supported
    # by the real image pool, although each image
    # can have several different crops.

    return desired


# ============================================================
# FFMPEG SCENE CREATION
# ============================================================

def create_scene_video(
    image_path,
    output_path,
    duration,
    scene_number,
):

    # Ken Burns movement differs from scene to scene.
    effects = [
        (
            "zoompan="
            "z='min(zoom+0.0008,1.10)':"
            "x='iw/2-(iw/zoom/2)':"
            "y='ih/2-(ih/zoom/2)':"
            "d=1:s=1080x1920:fps=30"
        ),

        (
            "zoompan="
            "z='if(lte(zoom,1.0),1.0,zoom-0.0007)':"
            "x='iw/2-(iw/zoom/2)':"
            "y='ih/2-(ih/zoom/2)':"
            "d=1:s=1080x1920:fps=30"
        ),

        (
            "zoompan="
            "z='min(zoom+0.0010,1.16)':"
            "x='(iw-iw/zoom)*0.25':"
            "y='(ih-ih/zoom)*0.35':"
            "d=1:s=1080x1920:fps=30"
        ),

        (
            "zoompan="
            "z='min(zoom+0.0009,1.14)':"
            "x='(iw-iw/zoom)*0.70':"
            "y='(ih-ih/zoom)*0.55':"
            "d=1:s=1080x1920:fps=30"
        ),

        (
            "zoompan="
            "z='min(zoom+0.0007,1.12)':"
            "x='(iw-iw/zoom)*0.45':"
            "y='(ih-ih/zoom)*0.20':"
            "d=1:s=1080x1920:fps=30"
        ),
    ]

    effect = effects[
        (scene_number - 1)
        % len(effects)
    ]

    command = [
        "ffmpeg",
        "-y",

        "-loop",
        "1",

        "-i",
        str(image_path),

        "-vf",
        effect,

        "-t",
        f"{duration:.3f}",

        "-r",
        str(FPS),

        "-an",

        "-c:v",
        "libx264",

        "-preset",
        "veryfast",

        "-crf",
        "20",

        "-pix_fmt",
        "yuv420p",

        "-movflags",
        "+faststart",

        str(output_path),
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:

        print(
            result.stderr[-5000:]
        )

        raise RuntimeError(
            f"FFmpeg failed creating scene "
            f"{scene_number}."
        )

    if (
        not output_path.exists()
        or output_path.stat().st_size < 10000
    ):

        raise RuntimeError(
            f"Scene {scene_number} was not created."
        )


# ============================================================
# BUILD SCENE IMAGES
# ============================================================

def build_scene_images(
    real_images,
    scene_count,
):

    scene_sources = []

    for index in range(
        scene_count
    ):

        source = real_images[
            index
            % len(real_images)
        ]

        scene_sources.append(
            source
        )

    scene_images = []

    for index, source in enumerate(
        scene_sources,
        start=1,
    ):

        scene_path = create_scene_image(
            source,
            index,
        )

        scene_images.append(
            scene_path
        )

        log(
            f"Scene image {index}: "
            f"{source.name}"
        )

    return scene_images


# ============================================================
# BUILD SCENE VIDEOS
# ============================================================

def build_scene_videos(
    scene_images,
    total_duration,
):

    scene_count = len(
        scene_images
    )

    # Equal base duration.
    base_duration = (
        total_duration
        / scene_count
    )

    durations = [
        base_duration
        for _ in range(scene_count)
    ]

    # Keep individual scenes within sensible limits.
    if base_duration < SCENE_MIN_SECONDS:

        durations = [
            SCENE_MIN_SECONDS
            for _ in range(scene_count)
        ]

    elif base_duration > SCENE_MAX_SECONDS:

        durations = [
            SCENE_MAX_SECONDS
            for _ in range(scene_count)
        ]

    # Normalize durations to narration length.
    total = sum(durations)

    if total != total_duration:

        factor = (
            total_duration
            / total
        )

        durations = [
            value * factor
            for value in durations
        ]

    scene_videos = []

    for index, (
        image_path,
        duration,
    ) in enumerate(
        zip(
            scene_images,
            durations,
        ),
        start=1,
    ):

        output_path = (
            WORK_DIR
            / f"scene_video_{index:02d}.mp4"
        )

        log(
            f"Rendering scene {index}/{scene_count} "
            f"({duration:.2f}s)"
        )

        create_scene_video(
            image_path,
            output_path,
            duration,
            index,
        )

        scene_videos.append(
            output_path
        )

    return scene_videos


# ============================================================
# CONCATENATE SCENES
# ============================================================

def concatenate_scenes(
    scene_videos,
):

    concat_file = (
        WORK_DIR
        / "concat.txt"
    )

    with open(
        concat_file,
        "w",
        encoding="utf-8",
    ) as f:

        for video in scene_videos:

            escaped = str(
                video.resolve()
            ).replace(
                "'",
                "'\\''",
            )

            f.write(
                f"file '{escaped}'\n"
            )

    combined = (
        WORK_DIR
        / "combined_video.mp4"
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

        "-c",
        "copy",

        "-movflags",
        "+faststart",

        str(combined),
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:

        print(
            result.stderr[-7000:]
        )

        raise RuntimeError(
            "FFmpeg scene concatenation failed."
        )

    if (
        not combined.exists()
        or combined.stat().st_size < 20000
    ):

        raise RuntimeError(
            "Combined scene video was not created."
        )

    return combined


# ============================================================
# TEXT OVERLAY
# ============================================================

def make_overlay_video(
    duration,
):

    overlay_file = (
        WORK_DIR
        / "overlay_video.mp4"
    )

    # Escape text for FFmpeg drawtext.
    safe_headline = (
        headline
        .replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )

    safe_county = (
        county
        .replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )

    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ]

    font_path = ""

    for candidate in font_candidates:

        if Path(candidate).exists():

            font_path = candidate
            break

    if not font_path:
        font_path = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

    safe_font = (
        font_path
        .replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
    )

    filters = []

    # --------------------------------------------------------
    # Top brand
    # --------------------------------------------------------

    filters.append(
        "drawtext="
        f"fontfile='{safe_font}':"
        "text='RIFT VALLEY WATCH':"
        "fontcolor=white:"
        "fontsize=54:"
        "x=55:"
        "y=45:"
        "box=1:"
        "boxcolor=black@0.70:"
        "boxborderw=20"
    )

    # --------------------------------------------------------
    # County
    # --------------------------------------------------------

    filters.append(
        "drawtext="
        f"fontfile='{safe_font}':"
        f"text='{safe_county.upper()}':"
        "fontcolor=white:"
        "fontsize=38:"
        "x=55:"
        "y=118:"
        "box=1:"
        "boxcolor=black@0.55:"
        "boxborderw=12"
    )

    # --------------------------------------------------------
    # Headline
    # --------------------------------------------------------

    filters.append(
        "drawtext="
        f"fontfile='{safe_font}':"
        f"text='{safe_headline}':"
        "fontcolor=white:"
        "fontsize=50:"
        "line_spacing=12:"
        "x=55:"
        "y=h-470:"
        "max_width=970:"
        "box=1:"
        "boxcolor=black@0.78:"
        "boxborderw=28"
    )

    # --------------------------------------------------------
    # Footer
    # --------------------------------------------------------

    filters.append(
        "drawtext="
        f"fontfile='{safe_font}':"
        "text='RIFT VALLEY • KENYA':"
        "fontcolor=white:"
        "fontsize=34:"
        "x=55:"
        "y=h-70:"
        "box=1:"
        "boxcolor=black@0.65:"
        "boxborderw=12"
    )

    filter_complex = ",".join(
        filters
    )

    command = [
        "ffmpeg",
        "-y",

        "-f",
        "lavfi",

        "-i",
        f"color=c=black:s={WIDTH}x{HEIGHT}:r={FPS}",

        "-t",
        f"{duration:.3f}",

        "-vf",
        filter_complex,

        "-an",

        "-c:v",
        "libx264",

        "-preset",
        "veryfast",

        "-crf",
        "23",

        "-pix_fmt",
        "yuv420p",

        str(overlay_file),
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # The overlay video is optional because text can be
    # rendered directly on the final video.
    # Therefore failures here are handled by returning None.

    if result.returncode != 0:
        return None

    return overlay_file


# ============================================================
# FINAL VIDEO WITH TEXT + NARRATION
# ============================================================

def create_final_video(
    combined_video,
    audio_file,
    duration,
):

    # Escape text for drawtext.
    safe_headline = (
        headline
        .replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )

    safe_county = (
        county
        .replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
        .replace("%", "\\%")
        .replace("[", "\\[")
        .replace("]", "\\]")
    )

    font_candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
    ]

    font_path = ""

    for candidate in font_candidates:

        if Path(candidate).exists():

            font_path = candidate
            break

    if not font_path:

        font_path = (
            "/usr/share/fonts/truetype/dejavu/"
            "DejaVuSans-Bold.ttf"
        )

    safe_font = (
        font_path
        .replace("\\", "\\\\")
        .replace(":", "\\:")
        .replace("'", "\\'")
    )

    filters = [

        # ----------------------------------------------------
        # Top dark translucent broadcast bar
        # ----------------------------------------------------

        "drawbox="
        "x=0:"
        "y=0:"
        "w=iw:"
        "h=175:"
        "color=black@0.68:"
        "t=fill",

        # ----------------------------------------------------
        # Bottom dark translucent headline area
        # ----------------------------------------------------

        "drawbox="
        "x=0:"
        "y=ih-550:"
        "w=iw:"
        "h=550:"
        "color=black@0.68:"
        "t=fill",

        # ----------------------------------------------------
        # Brand
        # ----------------------------------------------------

        "drawtext="
        f"fontfile='{safe_font}':"
        "text='RIFT VALLEY WATCH':"
        "fontcolor=white:"
        "fontsize=54:"
        "x=55:"
        "y=45:"
        "box=1:"
        "boxcolor=black@0.55:"
        "boxborderw=18",

        # ----------------------------------------------------
        # County
        # ----------------------------------------------------

        "drawtext="
        f"fontfile='{safe_font}':"
        f"text='{safe_county.upper()}':"
        "fontcolor=white:"
        "fontsize=38:"
        "x=55:"
        "y=118:"
        "box=1:"
        "boxcolor=black@0.40:"
        "boxborderw=10",

        # ----------------------------------------------------
        # Headline
        # ----------------------------------------------------

        "drawtext="
        f"fontfile='{safe_font}':"
        f"text='{safe_headline}':"
        "fontcolor=white:"
        "fontsize=48:"
        "line_spacing=10:"
        "x=55:"
        "y=ih-485:"
        "box=1:"
        "boxcolor=black@0.35:"
        "boxborderw=18",

        # ----------------------------------------------------
        # Footer
        # ----------------------------------------------------

        "drawtext="
        f"fontfile='{safe_font}':"
        "text='RIFT VALLEY • KENYA':"
        "fontcolor=white:"
        "fontsize=34:"
        "x=55:"
        "y=ih-72:"
        "box=1:"
        "boxcolor=black@0.35:"
        "boxborderw=10",
    ]

    filter_complex = ",".join(
        filters
    )

    temp_final = (
        WORK_DIR
        / "final_temp.mp4"
    )

    command = [
        "ffmpeg",
        "-y",

        "-i",
        str(combined_video),

        "-i",
        str(audio_file),

        "-filter_complex",
        filter_complex,

        "-map",
        "0:v:0",

        "-map",
        "1:a:0",

        "-c:v",
        "libx264",

        "-preset",
        "veryfast",

        "-crf",
        "20",

        "-b:v",
        VIDEO_BITRATE,

        "-c:a",
        "aac",

        "-b:a",
        "128k",

        "-ar",
        "44100",

        "-ac",
        "2",

        "-t",
        f"{duration:.3f}",

        "-pix_fmt",
        "yuv420p",

        "-movflags",
        "+faststart",

        str(temp_final),
    ]

    log(
        "Creating final MP4..."
    )

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:

        print(
            result.stderr[-10000:]
        )

        raise RuntimeError(
            "Final MP4 generation failed."
        )

    if (
        not temp_final.exists()
        or temp_final.stat().st_size < 50000
    ):

        raise RuntimeError(
            "Final MP4 was not generated correctly."
        )

    OUTPUT_FILE.unlink(
        missing_ok=True
    )

    temp_final.replace(
        OUTPUT_FILE
    )

    return OUTPUT_FILE


# ============================================================
# VERIFY FINAL VIDEO
# ============================================================

def verify_final_video():

    if not OUTPUT_FILE.exists():

        raise RuntimeError(
            "Rift Valley Watch MP4 was not generated."
        )

    size = OUTPUT_FILE.stat().st_size

    if size < 50000:

        raise RuntimeError(
            "Generated MP4 is suspiciously small."
        )

    duration = get_media_duration(
        OUTPUT_FILE
    )

    log(
        f"FINAL MP4: {OUTPUT_FILE}"
    )

    log(
        f"FINAL SIZE: {size / 1024 / 1024:.2f} MB"
    )

    log(
        f"FINAL DURATION: {duration:.2f} seconds"
    )

    return True


# ============================================================
# MAIN
# ============================================================

def main():

    log(
        "STARTING MULTI-VISUAL RIFT VALLEY WATCH GENERATOR"
    )

    # --------------------------------------------------------
    # Clean only video-work files.
    # Do NOT delete selected_story.json.
    # Do NOT delete selected_script.json.
    # Do NOT delete the main article image.
    # --------------------------------------------------------

    for item in WORK_DIR.iterdir():

        if item.is_file():

            try:
                item.unlink()
            except Exception:
                pass

    # --------------------------------------------------------
    # Narration
    # --------------------------------------------------------

    audio_file = create_narration()

    narration_duration = get_media_duration(
        audio_file
    )

    log(
        f"NARRATION DURATION: "
        f"{narration_duration:.2f} seconds"
    )

    # --------------------------------------------------------
    # Article images
    # --------------------------------------------------------

    real_images = prepare_real_images()

    # --------------------------------------------------------
    # Determine number of visual scenes
    # --------------------------------------------------------

    scene_count = calculate_scene_count(
        narration_duration,
        len(real_images),
    )

    log(
        f"REAL IMAGE COUNT: {len(real_images)}"
    )

    log(
        f"VISUAL SCENE COUNT: {scene_count}"
    )

    # --------------------------------------------------------
    # Build scene images
    # --------------------------------------------------------

    scene_images = build_scene_images(
        real_images,
        scene_count,
    )

    # --------------------------------------------------------
    # Build moving scene videos
    # --------------------------------------------------------

    scene_videos = build_scene_videos(
        scene_images,
        narration_duration,
    )

    # --------------------------------------------------------
    # Concatenate scene videos
    # --------------------------------------------------------

    combined_video = concatenate_scenes(
        scene_videos
    )

    # --------------------------------------------------------
    # Add graphics + narration
    # --------------------------------------------------------

    final_video = create_final_video(
        combined_video,
        audio_file,
        narration_duration,
    )

    # --------------------------------------------------------
    # Verify
    # --------------------------------------------------------

    verify_final_video()

    print()
    print("=" * 72)
    print("RIFT VALLEY WATCH GENERATION SUCCESSFUL")
    print("=" * 72)
    print(f"OUTPUT: {final_video}")
    print(f"IMAGES USED: {len(real_images)}")
    print(f"VISUAL SCENES: {scene_count}")
    print(f"DURATION: {narration_duration:.2f}s")
    print("=" * 72)


if __name__ == "__main__":
    try:

        main()

    except Exception as exc:

        print()
        print("=" * 72)
        print("RIFT VALLEY WATCH GENERATION FAILED")
        print("=" * 72)
        print(f"ERROR: {exc}")
        print("=" * 72)

        raise
