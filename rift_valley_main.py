# ============================================================
# RIFT VALLEY WATCH
# VIDEO GENERATOR V7
#
# COMPLETE REPLACEMENT
#
# Key fixes:
# 1. Uses story["local_image"] first.
# 2. Uses assets/source/story_image.jpg if available.
# 3. Never calls download_image() when a valid local image exists.
# 4. Recovers an article image from the source URL when needed.
# 5. Rejects Google News / Facebook / placeholder images.
# 6. Requires a real source image.
# 7. Uses publisher name only.
# 8. Generates a vertical 1080x1920 MP4.
# 9. Generates narration automatically.
# 10. Performs final MP4 validation.
# ============================================================

import os
import re
import io
import json
import time
import math
import html
import shutil
import hashlib
import tempfile
import subprocess
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from PIL import Image, ImageDraw, ImageFont, ImageFilter

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None

try:
    from gtts import gTTS
except Exception:
    gTTS = None


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"
ASSETS_DIR = ROOT / "assets"
SOURCE_DIR = ASSETS_DIR / "source"
OUTPUT_DIR = ROOT / "output"

DATA_DIR.mkdir(parents=True, exist_ok=True)
SOURCE_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

STORY_FILE = DATA_DIR / "story.json"
SELECTED_STORY_FILE = DATA_DIR / "selected_story.json"

IMAGE_FILE = SOURCE_DIR / "story_image.jpg"

FINAL_VIDEO = OUTPUT_DIR / "rift_valley_watch_reel.mp4"
SCRIPT_FILE = DATA_DIR / "script.txt"
VISUAL_REPORT = OUTPUT_DIR / "visual_report.json"


# ============================================================
# VIDEO SETTINGS
# ============================================================

WIDTH = 1080
HEIGHT = 1920

FPS = 30

TARGET_DURATION = 35

REQUEST_TIMEOUT = 25

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/153.0.0.0 Safari/537.36"
)

HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": (
        "text/html,application/xhtml+xml,application/xml;"
        "q=0.9,image/avif,image/webp,*/*;q=0.8"
    ),
    "Accept-Language": "en-US,en;q=0.9",
}


# ============================================================
# COLORS
# ============================================================

BLACK = (7, 10, 15)
WHITE = (248, 249, 250)
LIGHT = (225, 230, 235)
GREY = (150, 158, 168)
DARK_GREY = (40, 46, 54)

RED = (205, 32, 38)
DARK_RED = (115, 17, 22)

GOLD = (215, 170, 65)

BLUE = (28, 78, 121)

GREEN = (35, 125, 72)


# ============================================================
# FONT DISCOVERY
# ============================================================

def find_font(size, bold=False):
    candidates = []

    if bold:
        candidates.extend([
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/segoeuib.ttf",
        ])
    else:
        candidates.extend([
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/segoeui.ttf",
        ])

    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size=size)

    return ImageFont.load_default()


FONT_SMALL = find_font(30)
FONT_BODY = find_font(38)
FONT_MEDIUM = find_font(48, True)
FONT_LARGE = find_font(64, True)
FONT_HUGE = find_font(92, True)
FONT_TINY = find_font(24)


# ============================================================
# BASIC HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    value = html.unescape(str(value))
    value = re.sub(r"\s+", " ", value)
    return value.strip()


def safe_filename(value):
    value = re.sub(r"[^A-Za-z0-9._-]+", "_", str(value))
    return value[:180]


def run_command(command, check=True):
    print("COMMAND:", " ".join(map(str, command)))

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.stdout:
        print(result.stdout[-4000:])

    if result.stderr:
        print(result.stderr[-4000:])

    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}"
        )

    return result


def ffmpeg_exists():
    return shutil.which("ffmpeg") is not None


def ffprobe_exists():
    return shutil.which("ffprobe") is not None


# ============================================================
# STORY LOADING
# ============================================================

def load_json(path):
    if not path.exists():
        return None

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        print(f"WARNING: Could not read {path}: {exc}")
        return None


def load_story():
    story = load_json(STORY_FILE)

    if not story:
        story = load_json(SELECTED_STORY_FILE)

    if not story:
        raise RuntimeError(
            "No usable story JSON was found in data/story.json "
            "or data/selected_story.json."
        )

    if not isinstance(story, dict):
        raise RuntimeError("Story JSON is not a valid object.")

    return story


# ============================================================
# STORY CLEANING
# ============================================================

def source_name(story):
    source = story.get("source")

    if isinstance(source, dict):
        name = source.get("name") or source.get("publisher")
        if name:
            return clean_text(name)

    if isinstance(source, str):
        value = clean_text(source)

        if value.startswith("http://") or value.startswith("https://"):
            return ""

        return value

    return ""


def source_url(story):
    source = story.get("source")

    if isinstance(source, dict):
        return (
            source.get("url")
            or source.get("link")
            or source.get("source_url")
            or ""
        )

    if isinstance(source, str):
        if source.startswith("http://") or source.startswith("https://"):
            return source

    return ""


def story_title(story):
    title = clean_text(
        story.get("title")
        or story.get("headline")
        or ""
    )

    if not title:
        raise RuntimeError("Story has no title.")

    return title


def story_county(story):
    return clean_text(
        story.get("county")
        or story.get("location")
        or "Rift Valley"
    )


def story_summary(story):
    return clean_text(
        story.get("summary")
        or story.get("description")
        or ""
    )


# ============================================================
# REJECT BAD SOURCES / IMAGES
# ============================================================

BAD_IMAGE_WORDS = [
    "google",
    "google-news",
    "google_news",
    "facebook",
    "fbcdn",
    "favicon",
    "logo",
    "icon",
    "avatar",
    "placeholder",
    "default-image",
    "default_image",
    "sprite",
    "tracking",
    "pixel",
    "blank",
    "spinner",
    "loading",
    ".svg",
]


def looks_like_bad_image_url(url):
    if not url:
        return True

    value = url.lower()

    for word in BAD_IMAGE_WORDS:
        if word in value:
            return True

    return False


def valid_local_image(path):
    if not path:
        return False

    try:
        path = Path(path)

        if not path.exists():
            return False

        if path.stat().st_size < 10_000:
            return False

        with Image.open(path) as img:
            img.verify()

        with Image.open(path) as img:
            width, height = img.size

            if width < 300 or height < 200:
                return False

        return True

    except Exception as exc:
        print(f"INVALID LOCAL IMAGE: {path} -> {exc}")
        return False


# ============================================================
# LOCAL IMAGE DISCOVERY
# ============================================================

def local_image_candidates(story):
    candidates = []

    # Most important: main.py should put this here.
    for key in [
        "local_image",
        "image_path",
        "localImage",
        "local_image_path",
    ]:
        value = story.get(key)

        if value:
            candidates.append(Path(str(value)))

    # Standard project location.
    candidates.extend([
        IMAGE_FILE,
        SOURCE_DIR / "story_image.png",
        SOURCE_DIR / "story_image.webp",
        SOURCE_DIR / "article_image.jpg",
        SOURCE_DIR / "article_image.png",
        SOURCE_DIR / "article_image.webp",
        DATA_DIR / "story_image.jpg",
        DATA_DIR / "story_image.png",
        ROOT / "story_image.jpg",
    ])

    # Remove duplicates while preserving order.
    unique = []

    seen = set()

    for path in candidates:
        try:
            path = Path(path)

            if not path.is_absolute():
                path = ROOT / path

            path = path.resolve()

            key = str(path).lower()

            if key not in seen:
                seen.add(key)
                unique.append(path)

        except Exception:
            continue

    return unique


def find_existing_local_image(story):
    print("\n================ LOCAL IMAGE CHECK ================")

    for path in local_image_candidates(story):
        print("CHECK IMAGE:", path)

        if valid_local_image(path):
            print("VALID LOCAL SOURCE IMAGE:", path)
            return str(path)

    print("NO VALID LOCAL IMAGE FOUND.")

    return None


# ============================================================
# URL IMAGE VALIDATION
# ============================================================

def image_content_is_valid(data):
    try:
        with Image.open(io.BytesIO(data)) as img:
            width, height = img.size

            if width < 300 or height < 200:
                return False

            img.verify()

        return True

    except Exception:
        return False


def save_image_bytes(data, output_path):
    if not image_content_is_valid(data):
        raise RuntimeError("Downloaded file is not a valid image.")

    with Image.open(io.BytesIO(data)) as img:
        img = img.convert("RGB")
        img.save(output_path, "JPEG", quality=95)

    if not valid_local_image(output_path):
        raise RuntimeError("Saved image failed validation.")

    return str(output_path)


# ============================================================
# IMAGE URL EXTRACTION
# ============================================================

def extract_srcset(value):
    results = []

    if not value:
        return results

    for item in value.split(","):
        item = item.strip()

        if not item:
            continue

        parts = item.split()

        if parts:
            results.append(parts[0])

    return results


def extract_image_candidates_from_html(html_text, base_url):
    candidates = []

    if not html_text:
        return candidates

    if BeautifulSoup is None:
        return candidates

    soup = BeautifulSoup(html_text, "html.parser")

    # --------------------------------------------------------
    # META TAGS
    # --------------------------------------------------------

    meta_selectors = [
        ("meta", {"property": "og:image"}),
        ("meta", {"property": "og:image:url"}),
        ("meta", {"name": "twitter:image"}),
        ("meta", {"property": "twitter:image"}),
        ("meta", {"name": "twitter:image:src"}),
        ("meta", {"itemprop": "image"}),
    ]

    for tag_name, attrs in meta_selectors:
        for tag in soup.find_all(tag_name, attrs=attrs):
            value = (
                tag.get("content")
                or tag.get("href")
                or ""
            )

            if value:
                candidates.append(
                    urljoin(base_url, value)
                )

    # --------------------------------------------------------
    # JSON-LD
    # --------------------------------------------------------

    for script in soup.find_all(
        "script",
        attrs={"type": "application/ld+json"},
    ):
        raw = script.string or script.get_text()

        if not raw:
            continue

        try:
            data = json.loads(raw)
        except Exception:
            continue

        def inspect_json(value):
            found = []

            if isinstance(value, dict):
                for key, item in value.items():
                    key_lower = str(key).lower()

                    if key_lower == "image":
                        if isinstance(item, str):
                            found.append(item)

                        elif isinstance(item, list):
                            for x in item:
                                if isinstance(x, str):
                                    found.append(x)

                        elif isinstance(item, dict):
                            for k in ["url", "contentUrl"]:
                                if item.get(k):
                                    found.append(item[k])

                    found.extend(inspect_json(item))

            elif isinstance(value, list):
                for item in value:
                    found.extend(inspect_json(item))

            return found

        for image in inspect_json(data):
            if image:
                candidates.append(
                    urljoin(base_url, str(image))
                )

    # --------------------------------------------------------
    # LINK IMAGE
    # --------------------------------------------------------

    for tag in soup.find_all("link"):
        rel = tag.get("rel") or []

        if isinstance(rel, str):
            rel = [rel]

        rel_text = " ".join(rel).lower()

        if (
            "image_src" in rel_text
            or "image" in rel_text
        ):
            href = tag.get("href")

            if href:
                candidates.append(
                    urljoin(base_url, href)
                )

    # --------------------------------------------------------
    # ARTICLE IMAGES
    # --------------------------------------------------------

    containers = []

    for selector in [
        "article",
        "main",
        "[role='main']",
        ".article",
        ".story",
        ".post",
        ".entry-content",
        ".article-content",
        ".story-content",
    ]:
        containers.extend(soup.select(selector))

    if not containers:
        containers = [soup]

    for container in containers:
        for img in container.find_all("img"):
            attrs = [
                "src",
                "data-src",
                "data-original",
                "data-lazy-src",
                "data-image",
                "data-lazy",
            ]

            for attr in attrs:
                value = img.get(attr)

                if value:
                    candidates.append(
                        urljoin(base_url, value)
                    )

            for attr in [
                "srcset",
                "data-srcset",
                "data-lazy-srcset",
            ]:
                value = img.get(attr)

                for item in extract_srcset(value):
                    candidates.append(
                        urljoin(base_url, item)
                    )

    # --------------------------------------------------------
    # DEDUPLICATE
    # --------------------------------------------------------

    output = []

    seen = set()

    for url in candidates:
        url = str(url).strip()

        if not url:
            continue

        if url.startswith("//"):
            url = "https:" + url

        if not (
            url.startswith("http://")
            or url.startswith("https://")
        ):
            continue

        key = url.lower()

        if key in seen:
            continue

        seen.add(key)

        if looks_like_bad_image_url(url):
            continue

        output.append(url)

    return output


# ============================================================
# WORDPRESS IMAGE RECOVERY
# ============================================================

def wordpress_featured_image(article_url):
    parsed = urlparse(article_url)

    if not parsed.scheme or not parsed.netloc:
        return []

    base = f"{parsed.scheme}://{parsed.netloc}"

    candidates = []

    # First try REST API.
    api_url = base.rstrip("/") + "/wp-json/wp/v2/posts"

    try:
        response = requests.get(
            api_url,
            params={
                "search": "",
                "per_page": 10,
            },
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
        )

        if response.ok:
            posts = response.json()

            for post in posts:
                link = post.get("link", "")

                if link and (
                    parsed.path.rstrip("/")
                    in urlparse(link).path.rstrip("/")
                    or
                    urlparse(link).path.rstrip("/")
                    in parsed.path.rstrip("/")
                ):
                    media_id = post.get("featured_media")

                    if media_id:
                        media_url = (
                            base.rstrip("/")
                            + f"/wp-json/wp/v2/media/{media_id}"
                        )

                        media_response = requests.get(
                            media_url,
                            headers=HEADERS,
                            timeout=REQUEST_TIMEOUT,
                        )

                        if media_response.ok:
                            media = media_response.json()

                            source_url_value = (
                                media.get("source_url")
                            )

                            if source_url_value:
                                candidates.append(
                                    source_url_value
                                )

    except Exception as exc:
        print(
            "WordPress REST image recovery failed:",
            exc,
        )

    return candidates


# ============================================================
# DOWNLOAD IMAGE FROM URL
# ============================================================

def download_image(image_url, output_path=IMAGE_FILE):
    if not image_url:
        raise RuntimeError(
            "No story image URL was provided."
        )

    if looks_like_bad_image_url(image_url):
        raise RuntimeError(
            f"Rejected image URL: {image_url}"
        )

    print("DOWNLOADING SOURCE IMAGE:")
    print(image_url)

    response = requests.get(
        image_url,
        headers={
            **HEADERS,
            "Referer": source_url_from_current_story,
        },
        timeout=REQUEST_TIMEOUT,
        allow_redirects=True,
    )

    response.raise_for_status()

    content_type = (
        response.headers.get("content-type", "")
        .lower()
    )

    if (
        "image" not in content_type
        and not image_content_is_valid(response.content)
    ):
        raise RuntimeError(
            "URL did not return a valid image."
        )

    return save_image_bytes(
        response.content,
        output_path,
    )


# Global reference used by download_image.
source_url_from_current_story = ""


# ============================================================
# FIND SOURCE IMAGE
# ============================================================

def find_source_image(story):
    global source_url_from_current_story

    print("\n============================================================")
    print("SOURCE IMAGE RECOVERY")
    print("============================================================")

    # --------------------------------------------------------
    # 1. LOCAL IMAGE FROM MAIN.PY
    # --------------------------------------------------------

    local = find_existing_local_image(story)

    if local:
        return local, ["LOCAL:" + local]

    # --------------------------------------------------------
    # 2. ARTICLE URL
    # --------------------------------------------------------

    article_url = source_url(story)

    source_url_from_current_story = article_url

    if not article_url:
        raise RuntimeError(
            "Story has no source URL and no local source image."
        )

    print("ARTICLE URL:", article_url)

    candidates = []

    # --------------------------------------------------------
    # 3. FETCH ARTICLE
    # --------------------------------------------------------

    try:
        response = requests.get(
            article_url,
            headers=HEADERS,
            timeout=REQUEST_TIMEOUT,
            allow_redirects=True,
        )

        response.raise_for_status()

        final_url = response.url or article_url

        print("FINAL ARTICLE URL:", final_url)

        candidates.extend(
            extract_image_candidates_from_html(
                response.text,
                final_url,
            )
        )

    except Exception as exc:
        print("ARTICLE IMAGE EXTRACTION FAILED:", exc)

    # --------------------------------------------------------
    # 4. WORDPRESS RECOVERY
    # --------------------------------------------------------

    try:
        candidates.extend(
            wordpress_featured_image(article_url)
        )
    except Exception as exc:
        print(
            "WORDPRESS FALLBACK FAILED:",
            exc,
        )

    # --------------------------------------------------------
    # 5. TEST CANDIDATES
    # --------------------------------------------------------

    unique = []

    seen = set()

    for url in candidates:
        url = str(url).strip()

        if not url:
            continue

        key = url.lower()

        if key in seen:
            continue

        seen.add(key)

        if looks_like_bad_image_url(url):
            continue

        unique.append(url)

    print(
        f"IMAGE CANDIDATES FOUND: {len(unique)}"
    )

    for index, url in enumerate(unique[:30], 1):
        print(f"IMAGE CANDIDATE {index}: {url}")

    for index, url in enumerate(unique[:30], 1):
        try:
            print(
                f"TRYING IMAGE {index}: {url}"
            )

            saved = download_image(
                url,
                IMAGE_FILE,
            )

            if valid_local_image(saved):
                print(
                    "REAL SOURCE IMAGE RECOVERED:",
                    saved,
                )

                return saved, unique

        except Exception as exc:
            print(
                f"IMAGE {index} REJECTED:",
                exc,
            )

    raise RuntimeError(
        "No usable real article image could be recovered. "
        "The reel was stopped rather than generating "
        "a fake or placeholder visual."
    )


# ============================================================
# IMAGE PREPARATION
# ============================================================

def prepare_source_image(image_path):
    if not valid_local_image(image_path):
        raise RuntimeError(
            f"Invalid source image: {image_path}"
        )

    with Image.open(image_path) as img:
        img = img.convert("RGB")

        width, height = img.size

        target_ratio = WIDTH / HEIGHT
        source_ratio = width / height

        if source_ratio > target_ratio:
            new_height = height
            new_width = int(height * target_ratio)

            left = (width - new_width) // 2

            img = img.crop(
                (
                    left,
                    0,
                    left + new_width,
                    height,
                )
            )

        else:
            new_width = width
            new_height = int(width / target_ratio)

            top = (height - new_height) // 2

            img = img.crop(
                (
                    0,
                    top,
                    width,
                    top + new_height,
                )
            )

        img = img.resize(
            (WIDTH, HEIGHT),
            Image.Resampling.LANCZOS,
        )

        img.save(
            IMAGE_FILE,
            "JPEG",
            quality=95,
        )

    return str(IMAGE_FILE)


# ============================================================
# IMAGE EFFECTS
# ============================================================

def load_image(path):
    return Image.open(path).convert("RGB")


def darken(img, amount=0.45):
    overlay = Image.new(
        "RGBA",
        img.size,
        (0, 0, 0, int(255 * amount)),
    )

    base = img.convert("RGBA")

    return Image.alpha_composite(
        base,
        overlay,
    ).convert("RGB")


def add_gradient(img):
    img = img.convert("RGB")

    overlay = Image.new(
        "RGBA",
        img.size,
        (0, 0, 0, 0),
    )

    draw = ImageDraw.Draw(overlay)

    height = img.height

    for y in range(height):
        ratio = y / max(1, height - 1)

        alpha = int(205 * ratio)

        draw.line(
            [(0, y), (img.width, y)],
            fill=(0, 0, 0, alpha),
        )

    return Image.alpha_composite(
        img.convert("RGBA"),
        overlay,
    ).convert("RGB")


# ============================================================
# TEXT WRAPPING
# ============================================================

def wrap_text(draw, text, font, max_width):
    words = clean_text(text).split()

    if not words:
        return []

    lines = []

    current = words[0]

    for word in words[1:]:
        candidate = current + " " + word

        bbox = draw.textbbox(
            (0, 0),
            candidate,
            font=font,
        )

        width = bbox[2] - bbox[0]

        if width <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word

    lines.append(current)

    return lines


def draw_wrapped_text(
    draw,
    text,
    xy,
    font,
    fill,
    max_width,
    line_gap=12,
):
    x, y = xy

    lines = wrap_text(
        draw,
        text,
        font,
        max_width,
    )

    for line in lines:
        draw.text(
            (x, y),
            line,
            font=font,
            fill=fill,
        )

        bbox = draw.textbbox(
            (x, y),
            line,
            font=font,
        )

        y += (
            bbox[3]
            - bbox[1]
            + line_gap
        )

    return y


# ============================================================
# BROADCAST HEADER
# ============================================================

def draw_header(draw, section="RIFT VALLEY WATCH"):
    draw.rectangle(
        (0, 0, WIDTH, 125),
        fill=BLACK,
    )

    draw.rectangle(
        (0, 120, WIDTH, 128),
        fill=RED,
    )

    draw.text(
        (55, 37),
        "RIFT VALLEY WATCH",
        font=FONT_MEDIUM,
        fill=WHITE,
    )

    section = clean_text(section).upper()

    if section:
        bbox = draw.textbbox(
            (0, 0),
            section,
            font=FONT_SMALL,
        )

        tw = bbox[2] - bbox[0]

        draw.text(
            (
                WIDTH - tw - 55,
                46,
            ),
            section,
            font=FONT_SMALL,
            fill=GOLD,
        )


def draw_footer(draw, source=None):
    draw.rectangle(
        (
            0,
            HEIGHT - 145,
            WIDTH,
            HEIGHT,
        ),
        fill=BLACK,
    )

    draw.rectangle(
        (
            0,
            HEIGHT - 145,
            WIDTH,
            HEIGHT - 139,
        ),
        fill=RED,
    )

    source = clean_text(source or "")

    if source:
        draw.text(
            (50, HEIGHT - 112),
            "SOURCE",
            font=FONT_TINY,
            fill=GOLD,
        )

        draw.text(
            (50, HEIGHT - 78),
            source[:60],
            font=FONT_SMALL,
            fill=WHITE,
        )

    draw.text(
        (
            WIDTH - 260,
            HEIGHT - 78,
        ),
        "RIFT VALLEY WATCH",
        font=FONT_TINY,
        fill=GREY,
    )


# ============================================================
# SCENE RENDERING
# ============================================================

def scene_base(
    source_image=None,
    dark=True,
):
    if source_image and valid_local_image(source_image):
        img = load_image(source_image)
        img = img.resize(
            (WIDTH, HEIGHT),
            Image.Resampling.LANCZOS,
        )

        if dark:
            img = darken(img, 0.38)

        img = add_gradient(img)

        return img

    return Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        BLACK,
    )


def scene_photo(story, image_path, index=1):
    title = story_title(story)
    county = story_county(story)
    source = source_name(story)

    if not valid_local_image(image_path):
        raise RuntimeError(
            "scene_photo received an invalid source image."
        )

    img = scene_base(
        image_path,
        dark=True,
    )

    draw = ImageDraw.Draw(img)

    draw_header(
        draw,
        "SOURCE VISUAL",
    )

    draw_wrapped_text(
        draw,
        title,
        (55, 1290),
        FONT_LARGE,
        WHITE,
        970,
        line_gap=12,
    )

    draw.text(
        (55, 1575),
        county.upper(),
        font=FONT_MEDIUM,
        fill=GOLD,
    )

    draw_footer(
        draw,
        source,
    )

    return img


def scene_title(story):
    title = story_title(story)
    county = story_county(story)

    img = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        BLACK,
    )

    draw = ImageDraw.Draw(img)

    draw.rectangle(
        (0, 0, WIDTH, 20),
        fill=RED,
    )

    draw.text(
        (55, 110),
        "BREAKING DEVELOPMENT",
        font=FONT_MEDIUM,
        fill=RED,
    )

    y = 260

    y = draw_wrapped_text(
        draw,
        title,
        (55, y),
        FONT_HUGE,
        WHITE,
        960,
        line_gap=18,
    )

    draw.text(
        (55, y + 55),
        county.upper(),
        font=FONT_MEDIUM,
        fill=GOLD,
    )

    draw.rectangle(
        (55, 1500, 1025, 1508),
        fill=RED,
    )

    draw.text(
        (55, 1550),
        "RIFT VALLEY WATCH",
        font=FONT_MEDIUM,
        fill=WHITE,
    )

    draw.text(
        (55, 1630),
        "Verified regional reporting",
        font=FONT_BODY,
        fill=GREY,
    )

    return img


def scene_location(story):
    county = story_county(story)

    img = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        (11, 18, 27),
    )

    draw = ImageDraw.Draw(img)

    draw_header(
        draw,
        "LOCATION",
    )

    draw.text(
        (60, 260),
        "WHERE",
        font=FONT_MEDIUM,
        fill=GOLD,
    )

    draw_wrapped_text(
        draw,
        county,
        (60, 360),
        FONT_HUGE,
        WHITE,
        950,
        line_gap=15,
    )

    # Editorial location graphic.
    draw.rounded_rectangle(
        (70, 850, 1010, 1430),
        radius=30,
        fill=(20, 30, 43),
        outline=BLUE,
        width=4,
    )

    draw.ellipse(
        (390, 990, 690, 1290),
        outline=RED,
        width=14,
    )

    draw.ellipse(
        (475, 1075, 605, 1205),
        fill=RED,
    )

    draw.text(
        (120, 1330),
        "CHEPALUNGU CONSTITUENCY",
        font=FONT_MEDIUM,
        fill=WHITE,
    )

    draw_footer(
        draw,
        source_name(story),
    )

    return img


def get_fact(story, label):
    facts = story.get("verified_facts") or []

    for fact in facts:
        if not isinstance(fact, dict):
            continue

        if (
            clean_text(
                fact.get("label")
            ).upper()
            == label.upper()
        ):
            return clean_text(
                fact.get("value")
            )

    return ""


def scene_facts(story):
    road_length = get_fact(
        story,
        "ROAD_LENGTH",
    )

    cost = get_fact(
        story,
        "COST",
    )

    location = get_fact(
        story,
        "LOCATION",
    )

    img = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        BLACK,
    )

    draw = ImageDraw.Draw(img)

    draw_header(
        draw,
        "KEY FACTS",
    )

    draw.text(
        (55, 230),
        "THE NUMBERS",
        font=FONT_MEDIUM,
        fill=GOLD,
    )

    # Main number.
    if road_length:
        draw.text(
            (55, 390),
            road_length,
            font=FONT_HUGE,
            fill=WHITE,
        )

        draw.text(
            (60, 510),
            "ROAD PROJECT",
            font=FONT_MEDIUM,
            fill=RED,
        )

    # Cost card.
    if cost:
        draw.rounded_rectangle(
            (55, 700, 1025, 1040),
            radius=30,
            fill=(21, 27, 35),
            outline=GOLD,
            width=4,
        )

        draw.text(
            (90, 760),
            "REPORTED PROJECT COST",
            font=FONT_SMALL,
            fill=GOLD,
        )

        draw_wrapped_text(
            draw,
            cost,
            (90, 840),
            FONT_HUGE,
            WHITE,
            870,
            line_gap=10,
        )

    if location:
        draw.text(
            (55, 1160),
            "LOCATION",
            font=FONT_SMALL,
            fill=GREY,
        )

        draw_wrapped_text(
            draw,
            location,
            (55, 1225),
            FONT_MEDIUM,
            WHITE,
            950,
            line_gap=12,
        )

    draw_footer(
        draw,
        source_name(story),
    )

    return img


def scene_route(story):
    project = get_fact(
        story,
        "PROJECT",
    )

    status = get_fact(
        story,
        "STATUS",
    )

    img = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        (8, 14, 21),
    )

    draw = ImageDraw.Draw(img)

    draw_header(
        draw,
        "PROJECT ROUTE",
    )

    draw.text(
        (55, 240),
        "ROAD LINK",
        font=FONT_MEDIUM,
        fill=GOLD,
    )

    y = draw_wrapped_text(
        draw,
        project,
        (55, 340),
        FONT_LARGE,
        WHITE,
        950,
        line_gap=16,
    )

    # Route line.
    line_y = 1040

    draw.line(
        (
            100,
            line_y,
            980,
            line_y,
        ),
        fill=RED,
        width=12,
    )

    points = [
        150,
        350,
        550,
        750,
        930,
    ]

    for x in points:
        draw.ellipse(
            (
                x - 20,
                line_y - 20,
                x + 20,
                line_y + 20,
            ),
            fill=WHITE,
        )

    if status:
        draw.text(
            (55, 1250),
            "STATUS",
            font=FONT_SMALL,
            fill
