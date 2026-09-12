# ============================================================
# RIFT VALLEY WATCH
# VIDEO GENERATOR
#
# Output:
#   output/rift_valley_watch_reel.mp4
#
# Requirements:
#   - One verified story
#   - Real article image
#   - 1080x1920 vertical video
#   - ~35 seconds runtime
#   - 6 professional news scenes
#   - Natural gTTS narration
#   - No Google News / Facebook / platform logos
#   - No raw tracking URLs on screen
# ============================================================

import os
import re
import io
import json
import time
import shutil
import hashlib
import subprocess
from pathlib import Path
from urllib.parse import urlparse

import requests
from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"
ASSET_DIR = ROOT / "assets"
SOURCE_DIR = ASSET_DIR / "source"
WORK_DIR = ASSET_DIR / "generated"
OUTPUT_DIR = ROOT / "output"

STORY_FILE = DATA_DIR / "selected_story.json"
SCRIPT_FILE = DATA_DIR / "selected_script.json"

FALLBACK_STORY_FILE = DATA_DIR / "story.json"
FALLBACK_SCRIPT_FILE = DATA_DIR / "script.json"

IMAGE_FILE = SOURCE_DIR / "story_image.jpg"
AUDIO_FILE = WORK_DIR / "narration.mp3"

OUTPUT_FILE = OUTPUT_DIR / "rift_valley_watch_reel.mp4"

VISUAL_METADATA_FILE = DATA_DIR / "visual_metadata.json"

WIDTH = 1080
HEIGHT = 1920

TARGET_DURATION = 35.0
MIN_DURATION = 31.5
MAX_DURATION = 38.5

FPS = 30


# ============================================================
# STORY SETTINGS
# ============================================================

COUNTIES = [
    "Bomet",
    "Kericho",
    "Nakuru",
    "Nandi",
    "Uasin Gishu",
    "Elgeyo-Marakwet",
    "West Pokot",
    "Narok",
]

BLOCKED_IMAGE_TERMS = [
    "google",
    "google-news",
    "google_news",
    "facebook",
    "meta",
    "youtube",
    "tiktok",
    "instagram",
    "twitter",
    "x.com",
    "favicon",
    "logo",
    "icon",
    "avatar",
    "placeholder",
    "default-image",
    "default_image",
]

BLOCKED_SOURCE_TERMS = [
    "google.com",
    "news.google.com",
    "facebook.com",
    "m.facebook.com",
    "youtube.com",
    "tiktok.com",
    "instagram.com",
    "x.com",
    "twitter.com",
]

BOILERPLATE_TERMS = [
    "google news",
    "comprehensive up-to-date news coverage",
    "news from around the web",
    "facebook",
    "log in",
    "sign up",
    "create an account",
    "see more",
    "follow us",
]


# ============================================================
# FONTS
# ============================================================

def find_font(size, bold=False):
    candidates = []

    if bold:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            "C:/Windows/Fonts/arialbd.ttf",
            "C:/Windows/Fonts/Arial Bold.ttf",
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            "C:/Windows/Fonts/arial.ttf",
            "C:/Windows/Fonts/Arial.ttf",
        ]

    for path in candidates:
        if os.path.exists(path):
            return ImageFont.truetype(path, size=size)

    return ImageFont.load_default()


FONT_SMALL = find_font(34)
FONT_MEDIUM = find_font(43)
FONT_LARGE = find_font(62, bold=True)
FONT_XLARGE = find_font(82, bold=True)
FONT_HUGE = find_font(108, bold=True)
FONT_BRAND = find_font(42, bold=True)


# ============================================================
# DIRECTORIES
# ============================================================

def ensure_directories():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# JSON
# ============================================================

def load_json(path):
    if not path.exists():
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        print(f"WARNING: Could not read {path}: {exc}")
        return {}


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    text = str(value)

    text = re.sub(r"<[^>]+>", " ", text)
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_text(value):
    return clean_text(value).lower()


def first_nonempty(*values):
    for value in values:
        text = clean_text(value)
        if text:
            return text

    return ""


def truncate(text, max_chars):
    text = clean_text(text)

    if len(text) <= max_chars:
        return text

    cut = text[:max_chars].rsplit(" ", 1)[0]

    return cut.rstrip(".,;:") + "…"


# ============================================================
# URL / SOURCE HELPERS
# ============================================================

def get_domain(url):
    try:
        parsed = urlparse(str(url))

        domain = parsed.netloc.lower()

        if domain.startswith("www."):
            domain = domain[4:]

        return domain

    except Exception:
        return ""


def source_display_name(source, source_url):
    source = clean_text(source)

    domain = get_domain(source_url)

    if source:
        low = source.lower()

        if "google" in low or "facebook" in low:
            source = ""

    if source:
        return truncate(source, 35)

    if domain:
        mapping = {
            "citizen.digital": "Citizen Digital",
            "nation.africa": "Nation",
            "standardmedia.co.ke": "The Standard",
            "the-star.co.ke": "The Star",
            "capitalfm.co.ke": "Capital FM",
            "kbc.co.ke": "KBC",
            "kenyanews.go.ke": "Kenya News Agency",
            "peopledaily.digital": "People Daily",
            "ntvkenya.co.ke": "NTV Kenya",
            "tuko.co.ke": "TUKO",
            "president.go.ke": "Office of the President",
            "deputypresident.go.ke": "Office of the Deputy President",
            "parliament.go.ke": "Parliament of Kenya",
            "kenha.co.ke": "KeNHA",
            "kura.go.ke": "KURA",
        }

        return mapping.get(domain, domain)

    return "Rift Valley Watch"


def is_blocked_source(source, source_url):
    combined = (
        normalize_text(source)
        + " "
        + normalize_text(source_url)
    )

    return any(term in combined for term in BLOCKED_SOURCE_TERMS)


# ============================================================
# IMAGE VALIDATION
# ============================================================

def is_blocked_image_url(url):
    if not url:
        return True

    low = str(url).lower()

    return any(term in low for term in BLOCKED_IMAGE_TERMS)


def validate_image_bytes(raw):
    try:
        image = Image.open(io.BytesIO(raw))

        width, height = image.size

        if width < 250 or height < 150:
            return False, None

        image.load()

        return True, image

    except Exception:
        return False, None


def download_real_image(image_url):
    if not image_url:
        raise RuntimeError("No real article image URL was provided.")

    if is_blocked_image_url(image_url):
        raise RuntimeError(
            f"Rejected platform/logo image URL: {image_url}"
        )

    print()
    print("------------------------------------------------------------")
    print("IMAGE DOWNLOAD")
    print("------------------------------------------------------------")
    print(f"Image URL: {image_url}")

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/120 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
    }

    try:
        response = requests.get(
            image_url,
            headers=headers,
            timeout=30,
            allow_redirects=True,
        )

        response.raise_for_status()

    except Exception as exc:
        raise RuntimeError(
            f"Unable to download article image: {exc}"
        )

    final_url = response.url

    if is_blocked_image_url(final_url):
        raise RuntimeError(
            f"Image redirected to blocked/platform URL: {final_url}"
        )

    valid, image = validate_image_bytes(response.content)

    if not valid or image is None:
        raise RuntimeError(
            "Downloaded image is invalid or too small."
        )

    # Reject suspiciously tiny/icon-like images.
    width, height = image.size

    if width < 400 or height < 250:
        raise RuntimeError(
            f"Image resolution too small: {width}x{height}"
        )

    # Convert safely to RGB JPEG.
    if image.mode not in ("RGB", "L"):
        image = image.convert("RGB")
    else:
        image = image.convert("RGB")

    image.save(
        IMAGE_FILE,
        format="JPEG",
        quality=94,
        optimize=True,
    )

    print(
        f"REAL IMAGE SAVED: {IMAGE_FILE} "
        f"({width}x{height})"
    )

    return str(IMAGE_FILE)


# ============================================================
# IMAGE PREPARATION
# ============================================================

def prepare_background():
    if not IMAGE_FILE.exists():
        raise RuntimeError(
            f"Missing story image: {IMAGE_FILE}"
        )

    image = Image.open(IMAGE_FILE).convert("RGB")

    target_ratio = WIDTH / HEIGHT
    image_ratio = image.width / image.height

    if image_ratio > target_ratio:
        # Image is too wide.
        new_height = image.height
        new_width = int(new_height * target_ratio)

        left = (image.width - new_width) // 2

        image = image.crop(
            (
                left,
                0,
                left + new_width,
                image.height,
            )
        )

    else:
        # Image is too tall.
        new_width = image.width
        new_height = int(new_width / target_ratio)

        top = max(
            0,
            (image.height - new_height) // 2
        )

        image = image.crop(
            (
                0,
                top,
                image.width,
                top + new_height,
            )
        )

    image = image.resize(
        (WIDTH, HEIGHT),
        Image.Resampling.LANCZOS,
    )

    return image


# ============================================================
# VISUAL HELPERS
# ============================================================

def draw_text_wrapped(
    draw,
    text,
    xy,
    font,
    max_width,
    fill=(255, 255, 255),
    line_spacing=12,
):
    x, y = xy

    words = clean_text(text).split()

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

    line_height = (
        font.getbbox("Ag")[3]
        - font.getbbox("Ag")[1]
    )

    for line in lines:
        draw.text(
            (x, y),
            line,
            font=font,
            fill=fill,
        )

        y += line_height + line_spacing

    return y


def add_overlay(image, opacity=145):
    overlay = Image.new(
        "RGBA",
        image.size,
        (0, 0, 0, opacity),
    )

    return Image.alpha_composite(
        image.convert("RGBA"),
        overlay,
    ).convert("RGB")


def add_top_bar(image):
    draw = ImageDraw.Draw(image)

    draw.rectangle(
        (0, 0, WIDTH, 145),
        fill=(8, 12, 18),
    )

    draw.rectangle(
        (0, 140, WIDTH, 148),
        fill=(230, 180, 40),
    )

    draw.text(
        (55, 40),
        "RIFT VALLEY WATCH",
        font=FONT_BRAND,
        fill=(255, 255, 255),
    )

    draw.text(
        (55, 94),
        "REGIONAL NEWS • VERIFIED UPDATE",
        font=FONT_SMALL,
        fill=(210, 215, 220),
    )

    return image


def add_footer(image, source):
    draw = ImageDraw.Draw(image)

    y = HEIGHT - 105

    draw.rectangle(
        (0, y, WIDTH, HEIGHT),
        fill=(7, 10, 14),
    )

    source_text = (
        "SOURCE: "
        + source_display_name(
            source.get("source_name")
            or source.get("source"),
            source.get("source_url")
            or source.get("url"),
        )
    )

    draw.text(
        (55, y + 22),
        truncate(source_text, 48),
        font=FONT_SMALL,
        fill=(225, 225, 225),
    )

    return image


def add_progress_bar(image, fraction):
    draw = ImageDraw.Draw(image)

    fraction = max(
        0.0,
        min(1.0, fraction),
    )

    y = HEIGHT - 8

    draw.rectangle(
        (0, y, WIDTH, HEIGHT),
        fill=(45, 45, 45),
    )

    draw.rectangle(
        (
            0,
            y,
            int(WIDTH * fraction),
            HEIGHT,
        ),
        fill=(230, 180, 40),
    )

    return image


# ============================================================
# SCENE GENERATION
# ============================================================

def scene_title(story):
    image = prepare_background()
    image = add_overlay(image, 115)
    image = add_top_bar(image)

    draw = ImageDraw.Draw(image)

    county = clean_text(
        story.get("county")
        or "Rift Valley"
    )

    draw.rounded_rectangle(
        (55, 270, 430, 365),
        radius=20,
        fill=(230, 180, 40),
    )

    draw.text(
        (82, 292),
        county.upper(),
        font=FONT_MEDIUM,
        fill=(10, 12, 15),
    )

    title = first_nonempty(
        story.get("title"),
        "Regional Development Update",
    )

    draw_text_wrapped(
        draw,
        title,
        (55, 450),
        FONT_XLARGE,
        960,
        fill=(255, 255, 255),
        line_spacing=20,
    )

    summary = truncate(
        first_nonempty(
            story.get("summary"),
            story.get("description"),
        ),
        180,
    )

    draw_text_wrapped(
        draw,
        summary,
        (55, 940),
        FONT_MEDIUM,
        900,
        fill=(235, 235, 235),
        line_spacing=15,
    )

    add_footer(image, story)

    return image


def scene_location(story):
    image = prepare_background()
    image = add_overlay(image, 150)
    image = add_top_bar(image)

    draw = ImageDraw.Draw(image)

    draw.text(
        (55, 250),
        "WHERE",
        font=FONT_SMALL,
        fill=(230, 180, 40),
    )

    county = first_nonempty(
        story.get("county"),
        "Rift Valley",
    )

    location = first_nonempty(
        story.get("location"),
        story.get("constituency"),
        story.get("area"),
        county,
    )

    draw_text_wrapped(
        draw,
        location,
        (55, 340),
        FONT_HUGE,
        950,
        fill=(255, 255, 255),
        line_spacing=18,
    )

    context = first_nonempty(
        story.get("location_context"),
        story.get("summary"),
        "A development affecting the local community.",
    )

    draw_text_wrapped(
        draw,
        truncate(context, 250),
        (55, 700),
        FONT_MEDIUM,
        900,
        fill=(235, 235, 235),
        line_spacing=16,
    )

    add_footer(image, story)

    return image


def scene_facts(story):
    image = prepare_background()
    image = add_overlay(image, 160)
    image = add_top_bar(image)

    draw = ImageDraw.Draw(image)

    draw.text(
        (55, 245),
        "KEY FACTS",
        font=FONT_MEDIUM,
        fill=(230, 180, 40),
    )

    facts = []

    verified_facts = story.get("verified_facts")

    if isinstance(verified_facts, list):
        facts.extend(
            clean_text(x)
            for x in verified_facts
            if clean_text(x)
        )

    elif isinstance(verified_facts, dict):
        for key, value in verified_facts.items():
            if clean_text(value):
                facts.append(
                    f"{clean_text(key)}: {clean_text(value)}"
                )

    # Common structured fields.
    for key, label in [
        ("amount", "Amount"),
        ("project_value", "Project value"),
        ("distance", "Distance"),
        ("road_length", "Road length"),
        ("beneficiaries", "Beneficiaries"),
        ("timeline", "Timeline"),
    ]:
        value = clean_text(story.get(key))

        if value:
            facts.append(
                f"{label}: {value}"
            )

    if not facts:
        summary = first_nonempty(
            story.get("summary"),
            story.get("description"),
        )

        if summary:
            facts.append(summary)

    facts = facts[:4]

    y = 380

    for fact in facts:
        draw.ellipse(
            (55, y + 12, 80, y + 37),
            fill=(230, 180, 40),
        )

        next_y = draw_text_wrapped(
            draw,
            truncate(fact, 180),
            (110, y),
            FONT_MEDIUM,
            850,
            fill=(255, 255, 255),
            line_spacing=12,
        )

        y = next_y + 55

    add_footer(image, story)

    return image


def scene_project(story):
    image = prepare_background()
    image = add_overlay(image, 155)
    image = add_top_bar(image)

    draw = ImageDraw.Draw(image)

    draw.text(
        (55, 250),
        "WHAT IS HAPPENING",
        font=FONT_MEDIUM,
        fill=(230, 180, 40),
    )

    key_details = []

    for key in [
        "project",
        "project_description",
        "route",
        "route_segments",
        "roads",
        "scope",
        "details",
        "development",
    ]:
        value = story.get(key)

        if isinstance(value, list):
            value = ", ".join(
                clean_text(v)
                for v in value
                if clean_text(v)
            )

        value = clean_text(value)

        if value:
            key_details.append(value)

    if not key_details:
        key_details.append(
            first_nonempty(
                story.get("summary"),
                story.get("description"),
                "A regional development is underway.",
            )
        )

    y = 390

    for detail in key_details[:3]:
        draw.rounded_rectangle(
            (50, y, 1030, y + 230),
            radius=25,
            fill=(12, 17, 24),
            outline=(230, 180, 40),
            width=3,
        )

        draw_text_wrapped(
            draw,
            truncate(detail, 210),
            (85, y + 42),
            FONT_MEDIUM,
            900,
            fill=(255, 255, 255),
            line_spacing=12,
        )

        y += 275

    add_footer(image, story)

    return image


def scene_official(story):
    image = prepare_background()
    image = add_overlay(image, 165)
    image = add_top_bar(image)

    draw = ImageDraw.Draw(image)

    draw.text(
        (55, 250),
        "CONFIRMED",
        font=FONT_MEDIUM,
        fill=(230, 180, 40),
    )

    official = first_nonempty(
        story.get("official_statement"),
        story.get("official_quote"),
        story.get("statement"),
        story.get("quote"),
    )

    speaker = first_nonempty(
        story.get("official_source"),
        story.get("speaker"),
        story.get("quoted_person"),
    )

    if official:
        draw.rounded_rectangle(
            (45, 360, 1035, 1230),
            radius=28,
            fill=(9, 14, 20),
            outline=(230, 180, 40),
            width=3,
        )

        draw.text(
            (85, 420),
            "OFFICIAL STATEMENT",
            font=FONT_SMALL,
            fill=(230, 180, 40),
        )

        draw_text_wrapped(
            draw,
            f"“{truncate(official, 500)}”",
            (85, 515),
            FONT_MEDIUM,
            880,
            fill=(255, 255, 255),
            line_spacing=18,
        )

        if speaker:
            draw.text(
                (85, 1100),
                "— " + truncate(speaker, 65),
                font=FONT_SMALL,
                fill=(215, 215, 215),
            )

    else:
        confirmed = first_nonempty(
            story.get("confirmed"),
            story.get("editorial_confirmed"),
            story.get("summary"),
            "The report has been checked against the available source material.",
        )

        draw_text_wrapped(
            draw,
            confirmed,
            (55, 390),
            FONT_LARGE,
            900,
            fill=(255, 255, 255),
            line_spacing=18,
        )

    add_footer(image, story)

    return image


def scene_source(story):
    image = prepare_background()
    image = add_overlay(image, 175)
    image = add_top_bar(image)

    draw = ImageDraw.Draw(image)

    draw.text(
        (55, 270),
        "SOURCE",
        font=FONT_MEDIUM,
        fill=(230, 180, 40),
    )

    source = source_display_name(
        story.get("source_name")
        or story.get("source"),
        story.get("source_url")
        or story.get("url"),
    )

    draw.text(
        (55, 420),
        source,
        font=FONT_HUGE,
        fill=(255, 255, 255),
    )

    county = first_nonempty(
        story.get("county"),
        "Rift Valley",
    )

    draw_text_wrapped(
        draw,
        f"Verified regional update from {county}.",
        (55, 650),
        FONT_MEDIUM,
        900,
        fill=(230, 230, 230),
        line_spacing=15,
    )

    draw.rounded_rectangle(
        (55, 980, 1025, 1190),
        radius=28,
        fill=(10, 15, 21),
        outline=(230, 180, 40),
        width=3,
    )

    draw.text(
        (95, 1035),
        "RIFT VALLEY WATCH",
        font=FONT_LARGE,
        fill=(255, 255, 255),
    )

    draw.text(
        (95, 1120),
        "Verified. Regional. Independent.",
        font=FONT_SMALL,
        fill=(210, 210, 210),
    )

    add_footer(image, story)

    return image


# ============================================================
# SCENE DEFINITIONS
# ============================================================

def build_scenes(story):
    return [
        ("TITLE", scene_title),
        ("LOCATION", scene_location),
        ("KEY FACTS", scene_facts),
        ("DETAILS", scene_project),
        ("CONFIRMED", scene_official),
        ("SOURCE", scene_source),
    ]


# ============================================================
# IMAGE FRAME WRITING
# ============================================================

def save_scene_images(story):
    scene_dir = WORK_DIR / "scenes"

    if scene_dir.exists():
        shutil.rmtree(scene_dir)

    scene_dir.mkdir(
        parents=True,
        exist_ok=True,
    )

    scenes = build_scenes(story)

    paths = []

    for index, (name, function) in enumerate(
        scenes,
        start=1,
    ):
        print(
            f"Rendering scene {index}/"
            f"{len(scenes)}: {name}"
        )

        image = function(story)

        path = scene_dir / f"scene_{index:02d}.jpg"

        image.save(
            path,
            format="JPEG",
            quality=94,
            optimize=True,
        )

        paths.append(path)

    return paths


# ============================================================
# NARRATION
# ============================================================

def build_narration(story, script=None):
    script = script or {}

    existing = first_nonempty(
        script.get("narration"),
        story.get("narration"),
    )

    # Reject old broken narration.
    if existing:
        low = normalize_text(existing)

        if (
            "google news" not in low
            and "facebook.com" not in low
            and "reported by facebook" not in low
            and len(existing.split()) >= 35
        ):
            return existing

    title = first_nonempty(
        story.get("title"),
        "Regional development update",
    )

    county = first_nonempty(
        story.get("county"),
        "the Rift Valley",
    )

    summary = first_nonempty(
        story.get("summary"),
        story.get("description"),
    )

    official = first_nonempty(
        story.get("official_statement"),
        story.get("official_quote"),
    )

    speaker = first_nonempty(
        story.get("official_source"),
        story.get("speaker"),
        story.get("quoted_person"),
    )

    facts = []

    verified = story.get("verified_facts")

    if isinstance(verified, list):
        facts = [
            clean_text(x)
            for x in verified
            if clean_text(x)
        ]

    elif isinstance(verified, dict):
        facts = [
            f"{clean_text(k)}: {clean_text(v)}"
            for k, v in verified.items()
            if clean_text(v)
        ]

    parts = []

    parts.append(
        f"Here is the latest update from {county}."
    )

    parts.append(
        title.rstrip(".") + "."
    )

    if summary:
        parts.append(
            truncate(summary, 280).rstrip(".") + "."
        )

    for fact in facts[:2]:
        parts.append(
            truncate(fact, 180).rstrip(".") + "."
        )

    if official:
        quote = truncate(official, 220)

        if speaker:
            parts.append(
                f"{speaker} said, "
                f"“{quote}.”"
            )
        else:
            parts.append(
                f"An official statement said, "
                f"“{quote}.”"
            )

    parts.append(
        "Rift Valley Watch will continue to track verified developments across the region."
    )

    narration = " ".join(parts)

    # Avoid overly long narration.
    words = narration.split()

    if len(words) > 105:
        narration = " ".join(words[:105])

    return narration


# ============================================================
# AUDIO
# ============================================================

def create_audio(narration):
    if not narration:
        raise RuntimeError(
            "No narration was provided."
        )

    if len(narration.split()) < 20:
        raise RuntimeError(
            "Narration is too short."
        )

    if AUDIO_FILE.exists():
        AUDIO_FILE.unlink()

    print()
    print("------------------------------------------------------------")
    print("NARRATION")
    print("------------------------------------------------------------")
    print(narration)

    try:
        tts = gTTS(
            text=narration,
            lang="en",
            slow=False,
        )

        tts.save(str(AUDIO_FILE))

    except Exception as exc:
        raise RuntimeError(
            f"gTTS failed: {exc}"
        )

    if not AUDIO_FILE.exists():
        raise RuntimeError(
            "Narration audio was not created."
        )

    if AUDIO_FILE.stat().st_size < 5000:
        raise RuntimeError(
            "Narration audio appears invalid."
        )

    print(
        f"Audio created: {AUDIO_FILE}"
    )

    return AUDIO_FILE


# ============================================================
# FFPROBE
# ============================================================

def run_command(command):
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    return result


def probe_duration(path):
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

    result = run_command(command)

    if result.returncode != 0:
        return 0.0

    try:
        return float(result.stdout.strip())
    except Exception:
        return 0.0


# ============================================================
# AUDIO DURATION
# ============================================================

def get_audio_duration():
    return probe_duration(AUDIO_FILE)


# ============================================================
# TARGET SCENE DURATIONS
# ============================================================

def calculate_scene_durations(audio_duration):
    """
    Always build a video around the requested 35-second target.

    If narration is shorter than the target, the final video
    is still held to the target rather than becoming a 17-second
    reel.

    If narration is longer than target, scene timing follows
    narration so audio is never cut unnecessarily.
    """

    target = TARGET_DURATION

    if audio_duration > MAX_DURATION:
        target = min(
            42.0,
            audio_duration + 0.5,
        )

    elif audio_duration > MIN_DURATION:
        target = max(
            TARGET_DURATION,
            audio_duration + 0.3,
        )

    else:
        target = TARGET_DURATION

    # Six scenes with slightly different pacing.
    weights = [
        0.18,
        0.15,
        0.18,
        0.18,
        0.17,
        0.14,
    ]

    durations = [
        target * weight
        for weight in weights
    ]

    difference = target - sum(durations)

    durations[-1] += difference

    return durations


# ============================================================
# FFMPEG IMAGE VIDEO
# ============================================================

def create_silent_video(scene_paths, durations):
    if len(scene_paths) != len(durations):
        raise RuntimeError(
            "Scene count and duration count do not match."
        )

    silent_video = WORK_DIR / "silent_video.mp4"

    if silent_video.exists():
        silent_video.unlink()

    concat_file = WORK_DIR / "scenes.txt"

    with open(
        concat_file,
        "w",
        encoding="utf-8",
    ) as f:
        for path, duration in zip(
            scene_paths,
            durations,
        ):
            # concat demuxer requires escaped paths.
            safe_path = str(path).replace(
                "\\",
                "/",
            )

            safe_path = safe_path.replace(
                "'",
                r"'\''",
            )

            f.write(
                f"file '{safe_path}'\n"
            )

            f.write(
                f"duration {duration:.4f}\n"
            )

        # Repeat final frame so ffmpeg honors final duration.
        safe_last = str(scene_paths[-1]).replace(
            "\\",
            "/",
        )

        safe_last = safe_last.replace(
            "'",
            r"'\''",
        )

        f.write(
            f"file '{safe_last}'\n"
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
        "-vf",
        (
            f"scale={WIDTH}:{HEIGHT}:"
            "force_original_aspect_ratio=decrease,"
            f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2"
        ),
        "-r",
        str(FPS),
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-crf",
        "19",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        str(silent_video),
    ]

    print()
    print("Creating visual video...")

    result = run_command(command)

    if result.returncode != 0:
        print(result.stderr[-5000:])

        raise RuntimeError(
            f"FFmpeg visual generation failed "
            f"with exit code {result.returncode}"
        )

    if not silent_video.exists():
        raise RuntimeError(
            "Silent video was not created."
        )

    return silent_video


# ============================================================
# AUDIO + VIDEO
# ============================================================

def combine_video_audio(video_path):
    if OUTPUT_FILE.exists():
        OUTPUT_FILE.unlink()

    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(AUDIO_FILE),
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
        "-ar",
        "44100",
        "-ac",
        "2",
        "-shortest",
        "-movflags",
        "+faststart",
        str(OUTPUT_FILE),
    ]

    print()
    print("Combining video + narration...")

    result = run_command(command)

    if result.returncode != 0:
        print(result.stderr[-6000:])

        raise RuntimeError(
            f"FFmpeg audio combination failed "
            f"with exit code {result.returncode}"
        )

    if not OUTPUT_FILE.exists():
        raise RuntimeError(
            "Final MP4 was not created."
        )

    return OUTPUT_FILE


# ============================================================
# FINAL VIDEO VALIDATION
# ============================================================

def validate_video(path):
    if not path.exists():
        raise RuntimeError(
            f"Final video does not exist: {path}"
        )

    duration = probe_duration(path)

    if duration < MIN_DURATION:
        raise RuntimeError(
            f"Final video is too short: "
            f"{duration:.2f}s. "
            f"Required minimum: {MIN_DURATION}s."
        )

    if duration > 45:
        raise RuntimeError(
            f"Final video is unexpectedly long: "
            f"{duration:.2f}s."
        )

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_streams",
        "-of",
        "json",
        str(path),
    ]

    result = run_command(command)

    if result.returncode != 0:
        raise RuntimeError(
            "Unable to inspect final video."
        )

    try:
        data = json.loads(result.stdout)
    except Exception:
        raise RuntimeError(
            "Invalid ffprobe output."
        )

    streams = data.get("streams", [])

    video_stream = None
    audio_stream = None

    for stream in streams:
        if stream.get("codec_type") == "video":
            video_stream = stream

        elif stream.get("codec_type") == "audio":
            audio_stream = stream

    if not video_stream:
        raise RuntimeError(
            "Final video contains no video stream."
        )

    if not audio_stream:
        raise RuntimeError(
            "Final video contains no audio stream."
        )

    width = int(video_stream.get("width", 0))
    height = int(video_stream.get("height", 0))

    codec = video_stream.get("codec_name")

    if width != WIDTH or height != HEIGHT:
        raise RuntimeError(
            f"Wrong video dimensions: "
            f"{width}x{height}. "
            f"Required: {WIDTH}x{HEIGHT}."
        )

    if codec != "h264":
        raise RuntimeError(
            f"Unexpected video codec: {codec}"
        )

    audio_codec = audio_stream.get(
        "codec_name"
    )

    if audio_codec != "aac":
        raise RuntimeError(
            f"Unexpected audio codec: {audio_codec}"
        )

    size_mb = path.stat().st_size / (
        1024 * 1024
    )

    print()
    print("------------------------------------------------------------")
    print("FINAL VIDEO VALIDATION")
    print("------------------------------------------------------------")
    print(f"File:       {path}")
    print(f"Duration:   {duration:.2f}s")
    print(f"Resolution: {width}x{height}")
    print(f"Video:      {codec}")
    print(f"Audio:      {audio_codec}")
    print(f"Size:       {size_mb:.2f} MB")

    return {
        "path": str(path),
        "duration": round(duration, 2),
        "width": width,
        "height": height,
        "video_codec": codec,
        "audio_codec": audio_codec,
        "size_mb": round(size_mb, 2),
    }


# ============================================================
# STORY QC
# ============================================================

def validate_story_for_video(story):
    title = first_nonempty(
        story.get("title")
    )

    summary = first_nonempty(
        story.get("summary"),
        story.get("description"),
    )

    image_url = first_nonempty(
        story.get("image"),
        story.get("image_url"),
    )

    source = first_nonempty(
        story.get("source_name"),
        story.get("source"),
    )

    source_url = first_nonempty(
        story.get("source_url"),
        story.get("url"),
    )

    if not title:
        raise RuntimeError(
            "Story has no title."
        )

    if len(title.split()) < 3:
        raise RuntimeError(
            f"Story title is not substantive: {title}"
        )

    if not summary:
        raise RuntimeError(
            "Story has no substantive summary."
        )

    if any(
        term in normalize_text(title)
        for term in BOILERPLATE_TERMS
    ):
        raise RuntimeError(
            f"Blocked boilerplate title: {title}"
        )

    if any(
        term in normalize_text(summary)
        for term in BOILERPLATE_TERMS
    ):
        raise RuntimeError(
            "Story summary contains platform boilerplate."
        )

    if is_blocked_source(
        source,
        source_url,
    ):
        raise RuntimeError(
            f"Blocked story source: {source}"
        )

    if not image_url:
        raise RuntimeError(
            "Story has no image URL."
        )

    if is_blocked_image_url(image_url):
        raise RuntimeError(
            f"Blocked image URL: {image_url}"
        )

    print("Story QC: PASSED")


# ============================================================
# VISUAL METADATA
# ============================================================

def save_visual_metadata(
    story,
    scene_paths,
    scene_durations,
    video_info,
):
    source_name = source_display_name(
        story.get("source_name")
        or story.get("source"),
        story.get("source_url")
        or story.get("url"),
    )

    metadata = {
        "project": "Rift Valley Watch",
        "generated_at": time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            time.gmtime(),
        ),
        "county": story.get("county"),
        "title": story.get("title"),
        "source": source_name,
        "source_url": story.get("source_url")
        or story.get("url"),
        "image": {
            "source_url": story.get("image")
            or story.get("image_url"),
            "local_path": str(IMAGE_FILE),
        },
        "video": video_info,
        "scenes": [
            {
                "index": i + 1,
                "name": [
                    "TITLE",
                    "LOCATION",
                    "KEY FACTS",
                    "DETAILS",
                    "CONFIRMED",
                    "SOURCE",
                ][i],
                "path": str(path),
                "duration": round(
                    scene_durations[i],
                    3,
                ),
            }
            for i, path in enumerate(scene_paths)
        ],
    }

    save_json(
        VISUAL_METADATA_FILE,
        metadata,
    )

    print(
        f"Visual metadata saved: "
        f"{VISUAL_METADATA_FILE}"
    )


# ============================================================
# LOAD STORY
# ============================================================

def load_story():
    candidates = [
        STORY_FILE,
        FALLBACK_STORY_FILE,
    ]

    for path in candidates:
        if path.exists():
            story = load_json(path)

            if story:
                print(
                    f"Using story: {path}"
                )

                return story

    raise RuntimeError(
        "No story JSON found. Expected "
        "data/selected_story.json or data/story.json."
    )


def load_script():
    candidates = [
        SCRIPT_FILE,
        FALLBACK_SCRIPT_FILE,
    ]

    for path in candidates:
        if path.exists():
            script = load_json(path)

            if script:
                print(
                    f"Using script: {path}"
                )

                return script

    return {}


# ============================================================
# NORMALIZE STORY FIELDS
# ============================================================

def normalize_story(story):
    story = dict(story)

    # Handle alternate field names.
    if not story.get("image"):
        story["image"] = first_nonempty(
            story.get("image_url"),
            story.get("imageUrl"),
            story.get("featured_image"),
            story.get("featuredImage"),
        )

    if not story.get("source_name"):
        story["source_name"] = first_nonempty(
            story.get("publisher"),
            story.get("source"),
            story.get("publisher_name"),
        )

    if not story.get("source_url"):
        story["source_url"] = first_nonempty(
            story.get("url"),
            story.get("article_url"),
            story.get("link"),
        )

    if not story.get("summary"):
        story["summary"] = first_nonempty(
            story.get("description"),
            story.get("excerpt"),
            story.get("content"),
        )

    return story


# ============================================================
# MAIN GENERATOR
# ============================================================

def generate_video(story, script=None):
    ensure_directories()

    story = normalize_story(story)

    validate_story_for_video(story)

    script = script or {}

    # --------------------------------------------------------
    # IMAGE
    # --------------------------------------------------------

    image_url = first_nonempty(
        story.get("image"),
        story.get("image_url"),
    )

    download_real_image(image_url)

    # --------------------------------------------------------
    # NARRATION
    # --------------------------------------------------------

    narration = build_narration(
        story,
        script,
    )

    story["narration"] = narration

    # Keep selected script synchronized.
    script_output = dict(script)

    script_output.update(
        {
            "title": story.get("title"),
            "county": story.get("county"),
            "source": source_display_name(
                story.get("source_name")
                or story.get("source"),
                story.get("source_url")
                or story.get("url"),
            ),
            "narration": narration,
        }
    )

    save_json(
        SCRIPT_FILE,
        script_output,
    )

    save_json(
        STORY_FILE,
        story,
    )

    audio = create_audio(narration)

    # --------------------------------------------------------
    # AUDIO DURATION
    # --------------------------------------------------------

    audio_duration = get_audio_duration()

    print(
        f"Narration duration: "
        f"{audio_duration:.2f}s"
    )

    # --------------------------------------------------------
    # SCENES
    # --------------------------------------------------------

    scene_paths = save_scene_images(
        story
    )

    scene_durations = calculate_scene_durations(
        audio_duration
    )

    print()
    print("Scene durations:")

    for i, duration in enumerate(
        scene_durations,
        start=1,
    ):
        print(
            f"  Scene {i}: {duration:.2f}s"
        )

    # --------------------------------------------------------
    # VISUAL VIDEO
    # --------------------------------------------------------

    silent_video = create_silent_video(
        scene_paths,
        scene_durations,
    )

    # --------------------------------------------------------
    # FINAL MP4
    # --------------------------------------------------------

    final_video = combine_video_audio(
        silent_video
    )

    # --------------------------------------------------------
    # QC
    # --------------------------------------------------------

    video_info = validate_video(
        final_video
    )

    # Hard duration check.
    duration = video_info["duration"]

    if duration < MIN_DURATION:
        raise RuntimeError(
            f"QC FAILED: final runtime "
            f"{duration:.2f}s is below "
            f"{MIN_DURATION}s."
        )

    # --------------------------------------------------------
    # METADATA
    # --------------------------------------------------------

    save_visual_metadata(
        story,
        scene_paths,
        scene_durations,
        video_info,
    )

    print()
    print("============================================================")
    print("RIFT VALLEY WATCH VIDEO COMPLETE")
    print("============================================================")
    print(f"FINAL MP4: {final_video}")
    print(f"DURATION:  {duration:.2f}s")
    print(f"SIZE:      {video_info['size_mb']:.2f} MB")
    print("STATUS:    PASS")
    print("============================================================")

    return final_video


# ============================================================
# STANDALONE EXECUTION
# ============================================================

def main():
    ensure_directories()

    print()
    print("============================================================")
    print("RIFT VALLEY WATCH VIDEO GENERATOR")
    print("============================================================")

    story = load_story()
    script = load_script()

    generate_video(
        story,
        script,
    )


if __name__ == "__main__":
    main()
