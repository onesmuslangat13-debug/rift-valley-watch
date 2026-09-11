import json
import math
import os
import re
import shutil
import subprocess
import sys
import textwrap
import urllib.parse
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH — V5 VIDEO GENERATOR
# Real-news visual system
# 1080x1920 / 30 FPS / MP4
# ============================================================

ROOT = Path(__file__).resolve().parents[1]
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
WORK_DIR = ROOT / "output" / "v5_work"
IMAGE_DIR = ROOT / "assets" / "source_images"

STORY_FILE = DATA_DIR / "story.json"
SCRIPT_FILE = DATA_DIR / "script.json"
OUTPUT_FILE = OUTPUT_DIR / "rift_valley_watch.mp4"
REPORT_FILE = DATA_DIR / "visual_report.json"

W = 1080
H = 1920
FPS = 30

FONT_REGULAR = "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
FONT_BOLD = "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"

if not os.path.exists(FONT_REGULAR):
    FONT_REGULAR = "DejaVuSans.ttf"
if not os.path.exists(FONT_BOLD):
    FONT_BOLD = "DejaVuSans-Bold.ttf"


# ============================================================
# GENERAL HELPERS
# ============================================================

def run(cmd, check=True):
    print("$", " ".join(str(x) for x in cmd))
    result = subprocess.run(
        [str(x) for x in cmd],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True
    )

    if check and result.returncode != 0:
        print(result.stderr)
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}"
        )

    return result


def ensure_dirs():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    WORK_DIR.mkdir(parents=True, exist_ok=True)
    IMAGE_DIR.mkdir(parents=True, exist_ok=True)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)


def clean_text(text):
    text = str(text or "")
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def safe_filename(text):
    text = clean_text(text)
    text = re.sub(r"[^A-Za-z0-9._-]+", "_", text)
    return text[:120]


def font(size, bold=False):
    try:
        return ImageFont.truetype(
            FONT_BOLD if bold else FONT_REGULAR,
            size
        )
    except Exception:
        return ImageFont.load_default()


def wrap_text(draw, text, fnt, max_width):
    words = clean_text(text).split()
    lines = []
    current = ""

    for word in words:
        trial = word if not current else current + " " + word
        box = draw.textbbox((0, 0), trial, font=fnt)

        if box[2] - box[0] <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines


def draw_wrapped(draw, text, xy, fnt, fill, max_width, spacing=14):
    x, y = xy
    lines = wrap_text(draw, text, fnt, max_width)

    for line in lines:
        draw.text((x, y), line, font=fnt, fill=fill)
        bbox = draw.textbbox((x, y), line, font=fnt)
        y += bbox[3] - bbox[1] + spacing

    return y


def round_rect(draw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(
        box,
        radius=radius,
        fill=fill,
        outline=outline,
        width=width
    )


# ============================================================
# IMAGE DISCOVERY
# ============================================================

def fetch_url(url, timeout=20):
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "Chrome/131 Safari/537.36"
            )
        }
    )

    return urllib.request.urlopen(req, timeout=timeout).read()


def absolute_url(base, value):
    value = clean_text(value)

    if not value:
        return None

    if value.startswith("//"):
        return "https:" + value

    return urllib.parse.urljoin(base, value)


def extract_image_candidates(source_url, story):
    print("\n[1/8] Discovering official source images...")

    candidates = []

    try:
        raw = fetch_url(source_url)
        html = raw.decode("utf-8", errors="ignore")
    except Exception as exc:
        print("Source page could not be fetched:", exc)
        return []

    # OG image first
    patterns = [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)["\']',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
    ]

    for pattern in patterns:
        for match in re.findall(pattern, html, re.I):
            url = absolute_url(source_url, match)
            if url:
                candidates.append(("metadata", url))

    # Image tags
    img_pattern = (
        r"<img[^>]+"
        r"(?:src|data-src|data-lazy-src|data-original)"
        r'=["\']([^"\']+)["\']'
        r"[^>]*>"
    )

    for match in re.findall(img_pattern, html, re.I):
        url = absolute_url(source_url, match)
        if url:
            candidates.append(("html", url))

    # Story relevance keywords
    title = clean_text(story.get("title", "")).lower()
    county = clean_text(story.get("county", "")).lower()

    keywords = set(
        re.findall(r"[a-z0-9]{4,}", title + " " + county)
    )

    scored = []

    for kind, url in candidates:
        low = url.lower()

        score = 0

        if kind == "metadata":
            score += 100

        for word in keywords:
            if word in low:
                score += 8

        reject_words = [
            "logo",
            "icon",
            "avatar",
            "favicon",
            "sprite",
            "placeholder",
            "advert",
            "banner-ad",
            "facebook",
            "twitter-icon",
            "youtube-icon",
            "linkedin-icon"
        ]

        if any(word in low for word in reject_words):
            score -= 100

        scored.append((score, kind, url))

    scored.sort(reverse=True)

    output = []
    seen = set()

    for score, kind, url in scored:
        if url in seen:
            continue

        seen.add(url)

        if score < -50:
            continue

        output.append((score, kind, url))

        if len(output) >= 12:
            break

    print(f"Found {len(output)} candidate image URLs.")
    return output


def download_and_validate_image(url, destination):
    try:
        raw = fetch_url(url, timeout=25)

        temp = destination.with_suffix(".download")

        with open(temp, "wb") as f:
            f.write(raw)

        with Image.open(temp) as img:
            img.load()

            width, height = img.size

            if width < 500 or height < 300:
                temp.unlink(missing_ok=True)
                return False

            # Reject tiny/suspicious aspect ratios
            ratio = width / float(height)

            if ratio < 0.35 or ratio > 4.0:
                temp.unlink(missing_ok=True)
                return False

            image = img.convert("RGB")

            # Blur test for extremely tiny/flat images
            small = image.resize((64, 64))
            extrema = small.convert("L").getextrema()

            if extrema[1] - extrema[0] < 12:
                temp.unlink(missing_ok=True)
                return False

            image.save(destination, "JPEG", quality=92)

        temp.unlink(missing_ok=True)
        return True

    except Exception as exc:
        print("Image rejected:", str(exc)[:160])

        try:
            destination.unlink()
        except Exception:
            pass

        return False


def discover_source_image(story):
    source = story.get("source", {})
    source_url = source.get("url")

    if not source_url:
        return None

    candidates = extract_image_candidates(source_url, story)

    for index, (_, kind, url) in enumerate(candidates):
        destination = (
            IMAGE_DIR /
            f"source_{safe_filename(story.get('title', 'story'))}_{index}.jpg"
        )

        if destination.exists():
            try:
                with Image.open(destination) as img:
                    if img.width >= 500 and img.height >= 300:
                        print("Using cached source image:", destination)
                        return destination
            except Exception:
                destination.unlink(missing_ok=True)

        print(
            f"Trying image {index + 1}/{len(candidates)} "
            f"({kind})"
        )

        if download_and_validate_image(url, destination):
            print("Accepted official-source image:", destination)
            return destination

    print("No suitable official-source image found.")
    return None


# ============================================================
# VISUAL PROCESSING
# ============================================================

def crop_cover(image, width=W, height=H, zoom=1.0):
    image = image.convert("RGB")

    target_ratio = width / float(height)
    image_ratio = image.width / float(image.height)

    if image_ratio > target_ratio:
        new_height = height
        new_width = int(new_height * image_ratio)
    else:
        new_width = width
        new_height = int(new_width / image_ratio)

    image = image.resize((new_width, new_height), Image.Resampling.LANCZOS)

    if zoom != 1.0:
        zw = int(new_width * zoom)
        zh = int(new_height * zoom)
        image = image.resize((zw, zh), Image.Resampling.LANCZOS)

    left = max(0, (image.width - width) // 2)
    top = max(0, (image.height - height) // 2)

    image = image.crop(
        (
            left,
            top,
            left + width,
            top + height
        )
    )

    return image


def photo_background(image_path, zoom=1.0):
    with Image.open(image_path) as img:
        image = crop_cover(img, zoom=zoom)

    # Dark newsroom treatment
    overlay = Image.new("RGBA", (W, H), (4, 12, 24, 95))
    image = image.convert("RGBA")
    image.alpha_composite(overlay)

    # Bottom gradient
    gradient = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    gd = ImageDraw.Draw(gradient)

    for y in range(int(H * 0.45), H):
        alpha = int(
            190 *
            ((y - H * 0.45) / (H * 0.55))
        )

        gd.line(
            [(0, y), (W, y)],
            fill=(0, 0, 0, min(210, alpha))
        )

    image.alpha_composite(gradient)

    return image.convert("RGB")


def gradient_background():
    image = Image.new("RGB", (W, H))
    px = image.load()

    for y in range(H):
        ratio = y / float(H)

        r = int(4 + 4 * ratio)
        g = int(12 + 10 * ratio)
        b = int(25 + 18 * ratio)

        for x in range(W):
            px[x, y] = (r, g, b)

    return image


def add_top_bar(draw, section):
    draw.rectangle(
        (0, 0, W, 105),
        fill=(5, 15, 30)
    )

    draw.rectangle(
        (0, 98, W, 105),
        fill=(225, 35, 42)
    )

    draw.text(
        (55, 30),
        "RIFT VALLEY WATCH",
        font=font(31, True),
        fill=(245, 247, 250)
    )

    draw.text(
        (W - 360, 34),
        section.upper(),
        font=font(24, True),
        fill=(225, 35, 42)
    )


def add_footer(draw, county, date):
    draw.rectangle(
        (0, H - 88, W, H),
        fill=(4, 10, 20)
    )

    draw.text(
        (50, H - 62),
        clean_text(county),
        font=font(22, True),
        fill=(235, 238, 242)
    )

    date_text = clean_text(date)

    bbox = draw.textbbox(
        (0, 0),
        date_text,
        font=font(21, True)
    )

    draw.text(
        (W - (bbox[2] - bbox[0]) - 50, H - 62),
        date_text,
        font=font(21, True),
        fill=(165, 175, 190)
    )


def add_label(draw, text, y=180):
    f = font(28, True)

    box = draw.textbbox(
        (0, 0),
        text,
        font=f
    )

    width = box[2] - box[0] + 44

    round_rect(
        draw,
        (50, y, 50 + width, y + 56),
        12,
        fill=(225, 35, 42)
    )

    draw.text(
        (72, y + 11),
        text,
        font=f,
        fill=(255, 255, 255)
    )


def add_source_badge(draw):
    round_rect(
        draw,
        (50, H - 165, 315, H - 112),
        12,
        fill=(20, 31, 47)
    )

    draw.text(
        (70, H - 151),
        "VERIFIED SOURCE",
        font=font(22, True),
        fill=(130, 220, 170)
    )


# ============================================================
# SCENE IMAGE BUILDERS
# ============================================================

def scene_photo(story, image_path):
    image = photo_background(image_path, zoom=1.04)
    draw = ImageDraw.Draw(image)

    add_top_bar(draw, "THE LATEST")
    add_label(draw, "DEVELOPMENT", 150)

    title = clean_text(story.get("title"))

    draw_wrapped(
        draw,
        title,
        (50, 1180),
        font(61, True),
        (255, 255, 255),
        970,
        spacing=15
    )

    draw.text(
        (52, 1640),
        "Official-source visual",
        font=font(26, True),
        fill=(225, 35, 42)
    )

    add_source_badge(draw)
    add_footer(
        draw,
        story.get("county", ""),
        story.get("date", "")
    )

    return image


def scene_latest(story):
    image = gradient_background()
    draw = ImageDraw.Draw(image)

    add_top_bar(draw, "THE LATEST")
    add_label(draw, "BREAKING DEVELOPMENT", 155)

    draw.text(
        (50, 300),
        "65 KM",
        font=font(128, True),
        fill=(255, 255, 255)
    )

    draw.text(
        (55, 455),
        "ROAD PROJECT",
        font=font(58, True),
        fill=(225, 35, 42)
    )

    draw_wrapped(
        draw,
        story.get("title", ""),
        (55, 610),
        font(55, True),
        (240, 244, 248),
        950,
        spacing=15
    )

    draw.text(
        (55, 1030),
        "BOMET COUNTY",
        font=font(38, True),
        fill=(155, 170, 190)
    )

    draw.text(
        (55, 1120),
        "PROJECT VALUE",
        font=font(27, True),
        fill=(150, 165, 185)
    )

    draw.text(
        (55, 1160),
        "KSh 2.1 BILLION",
        font=font(65, True),
        fill=(255, 255, 255)
    )

    add_footer(draw, story.get("county", ""), story.get("date", ""))

    return image


def scene_location(story):
    image = gradient_background()
    draw = ImageDraw.Draw(image)

    add_top_bar(draw, "WHERE IT IS")
    add_label(draw, "LOCATION", 155)

    draw.text(
        (55, 300),
        "BOMET",
        font=font(105, True),
        fill=(255, 255, 255)
    )

    draw.text(
        (58, 430),
        "CHEPALUNGU CONSTITUENCY",
        font=font(40, True),
        fill=(225, 35, 42)
    )

    # Stylised Kenya/location graphic
    center_x = 540
    center_y = 880

    draw.polygon(
        [
            (center_x - 180, center_y - 280),
            (center_x + 80, center_y - 340),
            (center_x + 170, center_y - 120),
            (center_x + 115, center_y + 170),
            (center_x - 20, center_y + 300),
            (center_x - 175, center_y + 190),
            (center_x - 220, center_y - 40)
        ],
        fill=(15, 37, 59),
        outline=(100, 125, 150)
    )

    # Bomet marker — deliberately stylised, not a claimed exact map boundary
    draw.ellipse(
        (
            center_x - 12,
            center_y - 30,
            center_x + 12,
            center_y - 6
        ),
        fill=(225, 35, 42)
    )

    draw.line(
        (
            center_x,
            center_y - 18,
            center_x + 85,
            center_y - 90
        ),
        fill=(225, 35, 42),
        width=5
    )

    draw.text(
        (center_x + 100, center_y - 115),
        "BOMET",
        font=font(32, True),
        fill=(255, 255, 255)
    )

    draw_wrapped(
        draw,
        "The project is located in Chepalungu Constituency, Bomet County.",
        (55, 1300),
        font(39, True),
        (230, 235, 242),
        950,
        spacing=13
    )

    add_footer(draw, story.get("county", ""), story.get("date", ""))

    return image


def scene_facts(story):
    image = gradient_background()
    draw = ImageDraw.Draw(image)

    add_top_bar(draw, "KEY FACTS")
    add_label(draw, "VERIFIED DATA", 155)

    facts = [
        ("ROAD LENGTH", "65 KM"),
        ("PROJECT COST", "KSh 2.1B"),
        ("STATUS", "ONGOING"),
    ]

    y = 340

    for label, value in facts:
        round_rect(
            draw,
            (50, y, 1030, y + 300),
            24,
            fill=(10, 27, 46),
            outline=(44, 65, 88),
            width=2
        )

        draw.text(
            (85, y + 45),
            label,
            font=font(27, True),
            fill=(145, 162, 182)
        )

        draw.text(
            (85, y + 105),
            value,
            font=font(72, True),
            fill=(255, 255, 255)
        )

        y += 350

    add_footer(draw, story.get("county", ""), story.get("date", ""))

    return image


def scene_route(story):
    image = gradient_background()
    draw = ImageDraw.Draw(image)

    add_top_bar(draw, "THE ROUTE")
    add_label(draw, "ROAD CORRIDOR", 155)

    draw.text(
        (55, 300),
        "65-KILOMETRE",
        font=font(67, True),
        fill=(255, 255, 255)
    )

    draw.text(
        (55, 390),
        "CONNECTION",
        font=font(67, True),
        fill=(225, 35, 42)
    )

    # Route line
    points = [
        (100, 700),
        (300, 620),
        (510, 780),
        (700, 650),
        (930, 820),
    ]

    for i in range(len(points) - 1):
        draw.line(
            (
                points[i][0],
                points[i][1],
                points[i + 1][0],
                points[i + 1][1]
            ),
            fill=(225, 35, 42),
            width=12
        )

    labels = [
        "Kyogong",
        "Kapkesosio",
        "Sigor",
        "Chebunyo",
        "Longisa"
    ]

    for point, label in zip(points, labels):
        x, y = point

        draw.ellipse(
            (x - 18, y - 18, x + 18, y + 18),
            fill=(255, 255, 255),
            outline=(225, 35, 42),
            width=5
        )

        draw.text(
            (x - 5, y + 35),
            label,
            font=font(24, True),
            fill=(230, 235, 242)
        )

    draw_wrapped(
        draw,
        "The reported corridor links Kyogong, Kapkesosio, Sigor and Chebunyo, with another section through Lelaitich, Kipreres and Longisa.",
        (55, 1050),
        font(35, True),
        (225, 230, 238),
        950,
        spacing=12
    )

    add_footer(draw, story.get("county", ""), story.get("date", ""))

    return image


def scene_impact(story):
    image = gradient_background()
    draw = ImageDraw.Draw(image)

    add_top_bar(draw, "WHY IT MATTERS")
    add_label(draw, "EXPECTED IMPACT", 155)

    draw.text(
        (55, 320),
        "ECONOMIC",
        font=font(76, True),
        fill=(255, 255, 255)
    )

    draw.text(
        (55, 410),
        "POTENTIAL",
        font=font(76, True),
        fill=(225, 35, 42)
    )

    impact = (
        "Bomet County Government says the project is expected "
        "to unlock the economic potential of the area and the "
        "wider county."
    )

    draw_wrapped(
        draw,
        impact,
        (55, 610),
        font(45, True),
        (232, 237, 243),
        950,
        spacing=16
    )

    # Simple economic network visual
    nodes = [
        (180, 1150),
        (540, 1020),
        (870, 1170),
        (360, 1430),
        (730, 1460),
    ]

    for i in range(len(nodes)):
        for j in range(i + 1, len(nodes)):
            draw.line(
                (
                    nodes[i][0],
                    nodes[i][1],
                    nodes[j][0],
                    nodes[j][1]
                ),
                fill=(38, 66, 91),
                width=4
            )

    for x, y in nodes:
        draw.ellipse(
            (x - 28, y - 28, x + 28, y + 28),
            fill=(225, 35, 42)
        )

    add_footer(draw, story.get("county", ""), story.get("date", ""))

    return image


def scene_source(story):
    image = gradient_background()
    draw = ImageDraw.Draw(image)

    add_top_bar(draw, "SOURCE")
    add_label(draw, "VERIFICATION", 155)

    draw.text(
        (55, 330),
        "OFFICIAL SOURCE",
        font=font(55, True),
        fill=(130, 220, 170)
    )

    source = story.get("source", {})

    draw_wrapped(
        draw,
        source.get("name", ""),
        (55, 470),
        font(48, True),
        (255, 255, 255),
        950,
        spacing=15
    )

    draw.text(
        (55, 680),
        "SOURCE TYPE",
        font=font(27, True),
        fill=(145, 160, 180)
    )

    draw.text(
        (55, 735),
        source.get("type", "OFFICIAL SOURCE"),
        font=font(38, True),
        fill=(225, 35, 42)
    )

    draw.text(
        (55, 900),
        "REPORT DATE",
        font=font(27, True),
        fill=(145, 160, 180)
    )

    draw.text(
        (55, 955),
        story.get("date", ""),
        font=font(42, True),
        fill=(255, 255, 255)
    )

    draw_wrapped(
        draw,
        "Editorial policy: confirmed facts are separated from unconfirmed details. No completion date, contractor or funding breakdown is presented unless verified.",
        (55, 1180),
        font(32, True),
        (210, 218, 228),
        950,
        spacing=12
    )

    add_footer(draw, story.get("county", ""), story.get("date", ""))

    return image


def scene_outro(story):
    image = gradient_background()
    draw = ImageDraw.Draw(image)

    draw.rectangle(
        (0, 0, W, 12),
        fill=(225, 35, 42)
    )

    draw.text(
        (55, 520),
        "RIFT VALLEY",
        font=font(75, True),
        fill=(255, 255, 255)
    )

    draw.text(
        (55, 615),
        "WATCH",
        font=font(110, True),
        fill=(225, 35, 42)
    )

    draw.line(
        (55, 790, 1025, 790),
        fill=(70, 85, 105),
        width=3
    )

    draw_wrapped(
        draw,
        "Tracking verified developments across the region.",
        (55, 900),
        font(43, True),
        (225, 231, 238),
        900,
        spacing=15
    )

    draw.text(
        (55, 1250),
        "FOLLOW FOR VERIFIED REGIONAL NEWS",
        font=font(29, True),
        fill=(145, 160, 180)
    )

    return image


# ============================================================
# NARRATION
# ============================================================

def build_narration(story):
    title = clean_text(story.get("title", ""))
    summary = clean_text(story.get("summary", ""))

    route = (
        "Kyogong, Kapkesosio, Sigor and Chebunyo, "
        "with another section through Sigor, Lelaitich, "
        "Kipreres and Longisa"
    )

    statement = story.get("official_statement", {})
    quote = clean_text(statement.get("quote", ""))

    return [
        (
            "THE LATEST",
            (
                f"{title}. "
                f"The project is currently under construction in "
                f"{clean_text(story.get('county', 'Bomet County'))}."
            )
        ),
        (
            "WHERE IT IS",
            (
                "The project is located in Chepalungu Constituency "
                "in Bomet County."
            )
        ),
        (
            "KEY FACTS",
            (
                "The road project covers 65 kilometres and carries "
                "a reported cost of 2.1 billion Kenyan shillings. "
                "Construction works are ongoing."
            )
        ),
        (
            "THE ROUTE",
            (
                f"The reported route covers {route}."
            )
        ),
        (
            "WHY IT MATTERS",
            (
                "The Bomet County Government says the project is "
                "expected to unlock economic potential in the area "
                "and the wider county."
            )
        ),
        (
            "OFFICIAL STATEMENT",
            (
                f"Deputy President Kithure Kindiki said: {quote}"
                if quote
                else
                "Government officials have called for close monitoring "
                "of road construction to ensure quality works and "
                "speedy completion."
            )
        ),
        (
            "SOURCE",
            (
                f"This report is based on information published by "
                f"{clean_text(story.get('source', {}).get('name', 'the official source'))}."
            )
        ),
        (
            "OUTRO",
            "Rift Valley Watch. Tracking verified developments across the region."
        )
    ]


def create_tts(text, output_path):
    text = clean_text(text)

    if not text:
        raise ValueError("Cannot create narration from empty text.")

    tts = gTTS(
        text=text,
        lang="en",
        slow=False
    )

    tts.save(str(output_path))


def audio_duration(path):
    result = run(
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

    return float(result.stdout.strip())


# ============================================================
# TIMED CAPTIONS
# ============================================================

def split_caption_words(text, max_words=8):
    words = clean_text(text).split()

    groups = []

    for i in range(0, len(words), max_words):
        groups.append(" ".join(words[i:i + max_words]))

    return groups


def ass_time(seconds):
    seconds = max(0, float(seconds))

    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    secs = int(seconds % 60)
    centis = int((seconds - int(seconds)) * 100)

    return f"{hours}:{minutes:02d}:{secs:02d}.{centis:02d}"


def create_ass(text, duration, output_path):
    groups = split_caption_words(text, 8)

    if not groups:
        groups = [text]

    weights = [
        max(1, len(group.split()))
        for group in groups
    ]

    total = sum(weights)

    lines = [
        "[Script Info]",
        "ScriptType: v4.00+",
        "PlayResX: 1080",
        "PlayResY: 1920",
        "ScaledBorderAndShadow: yes",
        "",
        "[V4+ Styles]",
        "Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
        "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
        "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
        "Alignment, MarginL, MarginR, MarginV, Encoding",
        "Style: News,DejaVu Sans,46,&H00FFFFFF,&H00FFFFFF,"
        "&H00000000,&H99000000,1,0,0,0,100,100,0,0,1,3,1,2,55,55,150,1",
        "",
        "[Events]",
        "Format: Layer, Start, End, Style, Name, MarginL, MarginR, "
        "MarginV, Effect, Text"
    ]

    current = 0.0

    for index, group in enumerate(groups):
        part = duration * weights[index] / total

        start = current
        end = min(duration, current + part)

        # Keep captions readable
        text_value = group.replace("{", "(").replace("}", ")")

        lines.append(
            f"Dialogue: 0,{ass_time(start)},{ass_time(end)},"
            f"News,,0,0,0,,{text_value}"
        )

        current = end

    with open(output_path, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


# ============================================================
# SCENE VIDEO CREATION
# ============================================================

def image_to_video(image_path, audio_path, ass_path, output_path, zoom=False):
    duration = audio_duration(audio_path)

    if duration < 1:
        duration = 1.5

    if zoom:
        # Subtle Ken Burns movement
        vf = (
            "scale=iw*1.08:ih*1.08,"
            "crop=1080:1920:"
            "((iw-1080)/2)+((iw-1080)/4)*sin(t/8):"
            "((ih-1920)/2)+((ih-1920)/4)*cos(t/8),"
            f"subtitles={ass_path.as_posix()}"
        )
    else:
        vf = (
            f"subtitles={ass_path.as_posix()}"
        )

    run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-i",
            str(audio_path),
            "-vf",
            vf,
            "-t",
            f"{duration:.3f}",
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
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            "44100",
            "-shortest",
            str(output_path)
        ]
    )

    return duration


def create_scene_image(scene_name, story, source_image):
    if scene_name == "THE LATEST":
        return scene_latest(story)

    if scene_name == "WHERE IT IS":
        return scene_location(story)

    if scene_name == "KEY FACTS":
        return scene_facts(story)

    if scene_name == "THE ROUTE":
        return scene_route(story)

    if scene_name == "WHY IT MATTERS":
        return scene_impact(story)

    if scene_name == "OFFICIAL STATEMENT":
        if source_image:
            return scene_photo(story, source_image)

        return scene_impact(story)

    if scene_name == "SOURCE":
        return scene_source(story)

    if scene_name == "OUTRO":
        return scene_outro(story)

    return scene_latest(story)


# ============================================================
# CONCATENATION
# ============================================================

def concatenate_videos(video_files, output_file):
    if not video_files:
        raise RuntimeError("No scene videos were created.")

    inputs = []

    for path in video_files:
        inputs.extend(["-i", str(path)])

    filter_parts = []

    for i in range(len(video_files)):
        filter_parts.append(
            f"[{i}:v:0]setpts=PTS-STARTPTS[v{i}]"
        )
        filter_parts.append(
            f"[{i}:a:0]asetpts=PTS-STARTPTS[a{i}]"
        )

    video_labels = "".join(
        f"[v{i}]" for i in range(len(video_files))
    )

    audio_labels = "".join(
        f"[a{i}]" for i in range(len(video_files))
    )

    filter_parts.append(
        f"{video_labels}concat=n={len(video_files)}:v=1:a=0[outv]"
    )

    filter_parts.append(
        f"{audio_labels}concat=n={len(video_files)}:v=0:a=1[outa]"
    )

    filter_complex = ";".join(filter_parts)

    run(
        [
            "ffmpeg",
            "-y",
            *inputs,
            "-filter_complex",
            filter_complex,
            "-map",
            "[outv]",
            "-map",
            "[outa]",
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-crf",
            "19",
            "-pix_fmt",
            "yuv420p",
            "-r",
            str(FPS),
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            "44100",
            "-movflags",
            "+faststart",
            str(output_file)
        ]
    )


# ============================================================
# FINAL QC
# ============================================================

def inspect_video(path):
    result = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size",
            "-show_entries",
            "stream=codec_type,codec_name,width,height,r_frame_rate",
            "-of",
            "json",
            str(path)
        ]
    )

    return json.loads(result.stdout)


def quality_control(path):
    print("\n[8/8] Running final video QC...")

    if not path.exists():
        raise RuntimeError("FINAL QC FAILED: MP4 does not exist.")

    size = path.stat().st_size

    if size < 100000:
        raise RuntimeError("FINAL QC FAILED: MP4 is suspiciously small.")

    info = inspect_video(path)

    streams = info.get("streams", [])
    video_stream = None
    audio_stream = None

    for stream in streams:
        if stream.get("codec_type") == "video":
            video_stream = stream

        if stream.get("codec_type") == "audio":
            audio_stream = stream

    if not video_stream:
        raise RuntimeError("FINAL QC FAILED: no video stream.")

    if not audio_stream:
        raise RuntimeError("FINAL QC FAILED: no audio stream.")

    if video_stream.get("codec_name") != "h264":
        raise RuntimeError("FINAL QC FAILED: video is not H.264.")

    if int(video_stream.get("width", 0)) != 1080:
        raise RuntimeError("FINAL QC FAILED: width is not 1080.")

    if int(video_stream.get("height", 0)) != 1920:
        raise RuntimeError("FINAL QC FAILED: height is not 1920.")

    duration = float(info.get("format", {}).get("duration", 0))

    if duration < 10:
        raise RuntimeError("FINAL QC FAILED: video is too short.")

    if duration > 180:
        raise RuntimeError("FINAL QC FAILED: video exceeds 180 seconds.")

    print("\nFINAL QC: PASSED")
    print(f"File: {path}")
    print(f"Size: {size / 1024 / 1024:.2f} MB")
    print(f"Duration: {duration:.2f} seconds")
    print("Resolution: 1080x1920")
    print("Video: H.264")
    print("Audio: AAC")

    return {
        "passed": True,
        "size_bytes": size,
        "duration_seconds": round(duration, 2),
        "width": 1080,
        "height": 1920,
        "video_codec": "h264",
        "audio_codec": audio_stream.get("codec_name")
    }


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 70)
    print("RIFT VALLEY WATCH V5")
    print("REAL-NEWS VIDEO GENERATOR")
    print("=" * 70)

    ensure_dirs()

    if not STORY_FILE.exists():
        raise FileNotFoundError(
            f"Missing story file: {STORY_FILE}"
        )

    story = load_json(STORY_FILE)

    print("\nStory:")
    print(clean_text(story.get("title", "")))

    print("\nCounty:")
    print(clean_text(story.get("county", "")))

    print("\nSource:")
    print(
        clean_text(
            story.get("source", {}).get("name", "")
        )
    )

    # --------------------------------------------------------
    # 1. Generate verified script
    # --------------------------------------------------------

    print("\n[1/8] Loading verified editorial data...")

    if SCRIPT_FILE.exists():
        script = load_json(SCRIPT_FILE)
    else:
        script = {}

    # --------------------------------------------------------
    # 2. Discover real source image
    # --------------------------------------------------------

    source_image = discover_source_image(story)

    # --------------------------------------------------------
    # 3. Build narration
    # --------------------------------------------------------

    print("\n[2/8] Building newsroom narration...")

    narration = build_narration(story)

    # --------------------------------------------------------
    # 4. Generate scenes
    # --------------------------------------------------------

    print("\n[3/8] Creating visual scenes...")

    scene_files = []
    visual_report = []

    for index, (scene_name, narration_text) in enumerate(narration):
        print(
            f"\nScene {index + 1}/{len(narration)}: "
            f"{scene_name}"
        )

        scene_dir = WORK_DIR / f"scene_{index + 1:02d}"
        scene_dir.mkdir(parents=True, exist_ok=True)

        image_path = scene_dir / "scene.jpg"
        audio_path = scene_dir / "voice.mp3"
        ass_path = scene_dir / "captions.ass"
        video_path = scene_dir / "scene.mp4"

        image = create_scene_image(
            scene_name,
            story,
            source_image
        )

        image.save(
            image_path,
            "JPEG",
            quality=94
        )

        print("Generating narration...")
        create_tts(
            narration_text,
            audio_path
        )

        duration = audio_duration(audio_path)

        print(
            f"Narration duration: "
            f"{duration:.2f}s"
        )

        create_ass(
            narration_text,
            duration,
            ass_path
        )

        zoom = (
            scene_name in
            {
                "THE LATEST",
                "OFFICIAL STATEMENT"
            }
            and source_image is not None
        )

        image_to_video(
            image_path,
            audio_path,
            ass_path,
            video_path,
            zoom=zoom
        )

        scene_files.append(video_path)

        visual_report.append(
            {
                "scene": scene_name,
                "narration": narration_text,
                "duration_seconds": round(duration, 2),
                "image": str(image_path),
                "source_photo_used": bool(
                    source_image and
                    scene_name in {
                        "THE LATEST",
                        "OFFICIAL STATEMENT"
                    }
                ),
                "captions": str(ass_path)
            }
        )

    # --------------------------------------------------------
    # 5. Concatenate
    # --------------------------------------------------------

    print("\n[6/8] Concatenating scenes...")

    if OUTPUT_FILE.exists():
        OUTPUT_FILE.unlink()

    concatenate_videos(
        scene_files,
        OUTPUT_FILE
    )

    # --------------------------------------------------------
    # 6. Save visual report
    # --------------------------------------------------------

    print("\n[7/8] Writing visual report...")

    report = {
        "version": "V5",
        "generator": "Rift Valley Watch V5",
        "source_image_found": bool(source_image),
        "source_image": str(source_image) if source_image else None,
        "scene_count": len(scene_files),
        "scenes": visual_report,
        "output": str(OUTPUT_FILE)
    }

    save_json(
        REPORT_FILE,
        report
    )

    # --------------------------------------------------------
    # 7. Final QC
    # --------------------------------------------------------

    qc = quality_control(
        OUTPUT_FILE
    )

    report["qc"] = qc

    save_json(
        REPORT_FILE,
        report
    )

    # --------------------------------------------------------
    # Finish
    # --------------------------------------------------------

    print("\n" + "=" * 70)
    print("RIFT VALLEY WATCH V5 COMPLETE")
    print("=" * 70)
    print(f"MP4: {OUTPUT_FILE}")
    print(f"Report: {REPORT_FILE}")
    print("=" * 70)


if __name__ == "__main__":
    try:
        main()
    except Exception as exc:
        print("\n" + "=" * 70)
        print("VIDEO GENERATION FAILED")
        print("=" * 70)
        print(str(exc))
        sys.exit(1)
