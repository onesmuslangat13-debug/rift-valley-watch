import os
import re
import json
import math
import shutil
import hashlib
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH
# VIDEO GENERATOR V8
#
# CORE RULE:
# ONE STORY = ONE MP4
#
# Political stories:
#   - Prefer relevant politician photo when available
#   - Then article/source photo
#
# No source card.
# No raw source dictionary on screen.
# No combining multiple stories into one reel.
# ============================================================


ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = ROOT / "data"
ASSETS_DIR = ROOT / "assets"
SOURCE_DIR = ASSETS_DIR / "source"
OUTPUT_DIR = ROOT / "output"
SCENES_DIR = OUTPUT_DIR / "scenes"
AUDIO_DIR = OUTPUT_DIR / "audio"

STORY_FILE = DATA_DIR / "story.json"
SCRIPT_FILE = DATA_DIR / "script.json"
REPORT_FILE = DATA_DIR / "visual_report.json"

WIDTH = 1080
HEIGHT = 1920
FPS = 30

FONT_DIRS = [
    ROOT / "fonts",
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/usr/share/fonts/truetype/liberation2"),
]

VIDEO_BITRATE = "7M"
AUDIO_BITRATE = "192k"


# ============================================================
# DIRECTORY SETUP
# ============================================================

for directory in [
    DATA_DIR,
    ASSETS_DIR,
    SOURCE_DIR,
    OUTPUT_DIR,
    SCENES_DIR,
    AUDIO_DIR,
]:
    directory.mkdir(parents=True, exist_ok=True)


# ============================================================
# FONT HELPERS
# ============================================================

def find_font(size, bold=False):
    candidates = []

    if bold:
        names = [
            "DejaVuSans-Bold.ttf",
            "LiberationSans-Bold.ttf",
            "Montserrat-Bold.ttf",
            "Arial-Bold.ttf",
        ]
    else:
        names = [
            "DejaVuSans.ttf",
            "LiberationSans-Regular.ttf",
            "Montserrat-Regular.ttf",
            "Arial.ttf",
        ]

    for directory in FONT_DIRS:
        for name in names:
            candidates.append(directory / name)

    for path in candidates:
        if path.exists():
            return ImageFont.truetype(str(path), size)

    return ImageFont.load_default()


FONT_SMALL = find_font(42)
FONT_MEDIUM = find_font(54, True)
FONT_LARGE = find_font(78, True)
FONT_XLARGE = find_font(98, True)
FONT_HUGE = find_font(115, True)
FONT_LABEL = find_font(32, True)
FONT_BODY = find_font(48)
FONT_BODY_BOLD = find_font(50, True)


# ============================================================
# GENERAL HELPERS
# ============================================================

def safe_text(value):
    if value is None:
        return ""
    return str(value).strip()


def slugify(value):
    value = safe_text(value).lower()
    value = re.sub(r"[^a-z0-9]+", "_", value)
    value = value.strip("_")
    return value[:80] or "story"


def run_command(command):
    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        print("COMMAND FAILED:")
        print(" ".join(command))
        print(result.stderr[-4000:])
        raise RuntimeError("Command failed")

    return result


def wrap_text(draw, text, font, max_width):
    words = safe_text(text).split()

    if not words:
        return []

    lines = []
    current = ""

    for word in words:
        candidate = word if not current else current + " " + word

        bbox = draw.textbbox((0, 0), candidate, font=font)
        width = bbox[2] - bbox[0]

        if width <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines


def draw_wrapped(
    draw,
    text,
    xy,
    font,
    fill,
    max_width,
    line_spacing=14,
    anchor=None,
):
    lines = wrap_text(draw, text, font, max_width)

    x, y = xy

    for line in lines:
        draw.text(
            (x, y),
            line,
            font=font,
            fill=fill,
            anchor=anchor,
        )

        bbox = draw.textbbox((0, 0), line, font=font)
        height = bbox[3] - bbox[1]

        y += height + line_spacing

    return y


def rounded_rectangle(draw, box, radius, fill, outline=None, width=1):
    draw.rounded_rectangle(
        box,
        radius=radius,
        fill=fill,
        outline=outline,
        width=width,
    )


def fit_crop(image, size):
    target_w, target_h = size

    image = image.convert("RGB")

    src_w, src_h = image.size

    target_ratio = target_w / target_h
    src_ratio = src_w / src_h

    if src_ratio > target_ratio:
        new_h = target_h
        new_w = int(new_h * src_ratio)
    else:
        new_w = target_w
        new_h = int(new_w / src_ratio)

    image = image.resize((new_w, new_h), Image.Resampling.LANCZOS)

    left = max(0, (new_w - target_w) // 2)
    top = max(0, (new_h - target_h) // 2)

    return image.crop(
        (
            left,
            top,
            left + target_w,
            top + target_h,
        )
    )


def fit_contain(image, size, background=(18, 22, 28)):
    target_w, target_h = size

    image = image.convert("RGB")

    image.thumbnail(
        (target_w, target_h),
        Image.Resampling.LANCZOS,
    )

    canvas = Image.new(
        "RGB",
        (target_w, target_h),
        background,
    )

    x = (target_w - image.width) // 2
    y = (target_h - image.height) // 2

    canvas.paste(image, (x, y))

    return canvas


def image_is_valid(path):
    try:
        with Image.open(path) as im:
            width, height = im.size

            if width < 300 or height < 200:
                return False

            if width * height < 120000:
                return False

            return True

    except Exception:
        return False


def image_hash(path):
    try:
        h = hashlib.sha256()

        with open(path, "rb") as f:
            while True:
                chunk = f.read(1024 * 1024)

                if not chunk:
                    break

                h.update(chunk)

        return h.hexdigest()

    except Exception:
        return ""


# ============================================================
# STORY LOADING
# ============================================================

def load_stories():
    if not STORY_FILE.exists():
        raise FileNotFoundError(
            f"Missing {STORY_FILE}"
        )

    with open(STORY_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    if isinstance(data, dict):
        if isinstance(data.get("stories"), list):
            stories = data["stories"]

        elif isinstance(data.get("story"), dict):
            stories = [data["story"]]

        else:
            stories = [data]

    elif isinstance(data, list):
        stories = data

    else:
        raise ValueError("Unsupported story.json format")

    stories = [
        s for s in stories
        if isinstance(s, dict)
    ]

    return stories


# ============================================================
# POLITICAL STORY DETECTION
# ============================================================

POLITICAL_KEYWORDS = [
    "president",
    "deputy president",
    "governor",
    "senator",
    "mp ",
    "member of parliament",
    "cabinet secretary",
    "minister",
    "uda",
    "party",
    "political",
    "election",
    "campaign",
    "rally",
    "parliament",
    "assembly",
    "government",
    "ruto",
    "kindiki",
    "sakaja",
    "murkomen",
    "mandago",
    "koech",
    "bii",
    "sang",
    "chepkwony",
    "rotich",
]


def is_political_story(story):
    category = safe_text(
        story.get("category")
    ).lower()

    title = safe_text(
        story.get("title")
    ).lower()

    summary = safe_text(
        story.get("summary")
    ).lower()

    combined = f"{category} {title} {summary}"

    return (
        "politic" in category
        or any(
            keyword in combined
            for keyword in POLITICAL_KEYWORDS
        )
    )


# ============================================================
# POLITICIAN PHOTO DISCOVERY
# ============================================================

def politician_names_from_story(story):
    """
    Uses explicit politician fields first.
    Then checks title/summary for common Rift Valley political figures.

    The news engine can optionally provide:

    politician:
        {
            "name": "...",
            "image_path": "..."
        }

    or:

    politician_photo: "assets/source/....jpg"
    """

    names = []

    politician = story.get("politician")

    if isinstance(politician, dict):
        name = safe_text(
            politician.get("name")
        )

        if name:
            names.append(name)

    direct_name = safe_text(
        story.get("politician_name")
    )

    if direct_name:
        names.append(direct_name)

    title = safe_text(story.get("title"))
    summary = safe_text(story.get("summary"))

    combined = f"{title} {summary}".lower()

    known_people = [
        ("William Ruto", ["ruto"]),
        ("Kithure Kindiki", ["kindiki"]),
        ("Jonathan Bii", ["jonathan bii"]),
        ("Stephen Sang", ["stephen sang"]),
        ("Isaac Ruto", ["isaac ruto"]),
        ("Eric Keter", ["eric keter"]),
        ("Oscar Sudi", ["oscar sudi"]),
        ("Aden Duale", ["aden duale"]),
        ("Moses Kuria", ["moses kuria"]),
        ("Susan Kihika", ["susan kihika"]),
        ("Jackson Mandago", ["jackson mandago"]),
        ("Aaron Cheruiyot", ["aaron cheruiyot"]),
        ("Arati", ["arati"]),
        ("Patrick Ole Ntutu", ["ole ntutu", "patrick ole ntutu"]),
        ("Kipchumba Murkomen", ["murkomen"]),
    ]

    for full_name, aliases in known_people:
        if any(alias in combined for alias in aliases):
            names.append(full_name)

    return list(dict.fromkeys(names))


def find_politician_photo(story):
    """
    Finds a politician-specific photograph supplied by the news engine.

    Supported fields:

    politician_photo
    politician.image_path
    politician.photo
    visuals[].image_path where type contains POLITICIAN
    """

    candidates = []

    direct = story.get("politician_photo")

    if direct:
        candidates.append(direct)

    politician = story.get("politician")

    if isinstance(politician, dict):
        for key in [
            "image_path",
            "photo",
            "photo_path",
            "image",
        ]:
            value = politician.get(key)

            if value:
                candidates.append(value)

    visuals = story.get("visuals")

    if isinstance(visuals, list):
        for visual in visuals:
            if not isinstance(visual, dict):
                continue

            visual_type = safe_text(
                visual.get("type")
            ).upper()

            if (
                "POLITIC" in visual_type
                or "OFFICIAL" in visual_type
            ):
                for key in [
                    "image_path",
                    "photo",
                    "path",
                    "image",
                ]:
                    value = visual.get(key)

                    if value:
                        candidates.append(value)

    for candidate in candidates:
        path = Path(str(candidate))

        if not path.is_absolute():
            path = ROOT / path

        if path.exists() and image_is_valid(path):
            return path

    # Search source directory using politician name.
    names = politician_names_from_story(story)

    for name in names:
        tokens = [
            token.lower()
            for token in re.findall(
                r"[A-Za-z]+",
                name
            )
            if len(token) >= 4
        ]

        if not tokens:
            continue

        for path in SOURCE_DIR.iterdir():
            if not path.is_file():
                continue

            filename = path.name.lower()

            if all(token in filename for token in tokens):
                if image_is_valid(path):
                    return path

    return None


# ============================================================
# ARTICLE PHOTO DISCOVERY
# ============================================================

def find_story_photo(story):
    candidates = []

    for key in [
        "image_path",
        "photo_path",
        "photo",
        "image",
        "article_image",
    ]:
        value = story.get(key)

        if value:
            candidates.append(value)

    visuals = story.get("visuals")

    if isinstance(visuals, list):
        for visual in visuals:
            if not isinstance(visual, dict):
                continue

            for key in [
                "image_path",
                "photo",
                "path",
                "image",
            ]:
                value = visual.get(key)

                if value:
                    candidates.append(value)

    for candidate in candidates:
        path = Path(str(candidate))

        if not path.is_absolute():
            path = ROOT / path

        if path.exists() and image_is_valid(path):
            return path

    # Search assets/source.
    possible = []

    for path in SOURCE_DIR.iterdir():
        if not path.is_file():
            continue

        if image_is_valid(path):
            possible.append(path)

    if not possible:
        return None

    # Try story ID/title matching.
    text = (
        safe_text(story.get("title"))
        + " "
        + safe_text(story.get("county"))
    ).lower()

    tokens = [
        token
        for token in re.findall(
            r"[a-z0-9]+",
            text
        )
        if len(token) >= 5
    ]

    scored = []

    for path in possible:
        name = path.name.lower()

        score = sum(
            1 for token in tokens
            if token in name
        )

        scored.append(
            (score, path)
        )

    scored.sort(
        key=lambda item: item[0],
        reverse=True
    )

    return scored[0][1]


def choose_story_photo(story):
    """
    Political story:
        politician photo first,
        article photo second.

    Non-political story:
        article photo first.
    """

    political = is_political_story(story)

    politician_photo = None

    if political:
        politician_photo = find_politician_photo(story)

        if politician_photo:
            return politician_photo, "POLITICIAN"

    article_photo = find_story_photo(story)

    if article_photo:
        return article_photo, "ARTICLE"

    return None, "NONE"


# ============================================================
# PHOTO PREPARATION
# ============================================================

def prepare_story_photo(story, index):
    path, photo_type = choose_story_photo(story)

    if not path:
        print(
            f"WARNING: No usable photo found for story {index}"
        )
        return None, "NONE"

    try:
        with Image.open(path) as im:
            im = im.convert("RGB")

            # Slight enhancement.
            im = im.filter(
                ImageFilter.UnsharpMask(
                    radius=1,
                    percent=110,
                    threshold=3,
                )
            )

            destination = (
                SCENES_DIR
                / f"story_{index:02d}_main_photo.jpg"
            )

            im.save(
                destination,
                "JPEG",
                quality=94,
            )

        print(
            f"PHOTO SELECTED [{photo_type}]: {path}"
        )

        return destination, photo_type

    except Exception as exc:
        print(
            f"WARNING: Photo processing failed: {exc}"
        )
        return None, "NONE"


# ============================================================
# IMAGE CANVAS
# ============================================================

def make_background(photo=None):
    if photo and photo.exists():
        try:
            with Image.open(photo) as im:
                bg = fit_crop(
                    im,
                    (WIDTH, HEIGHT),
                )

            bg = bg.filter(
                ImageFilter.GaussianBlur(8)
            )

            overlay = Image.new(
                "RGBA",
                (WIDTH, HEIGHT),
                (5, 9, 15, 150),
            )

            bg = Image.alpha_composite(
                bg.convert("RGBA"),
                overlay,
            )

            return bg.convert("RGB")

        except Exception:
            pass

    return Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        (10, 15, 22),
    )


def add_top_bar(draw, county=None):
    draw.rectangle(
        (0, 0, WIDTH, 105),
        fill=(8, 12, 18),
    )

    draw.rectangle(
        (0, 101, WIDTH, 105),
        fill=(215, 35, 45),
    )

    draw.text(
        (55, 30),
        "RIFT VALLEY WATCH",
        font=FONT_MEDIUM,
        fill=(255, 255, 255),
    )

    if county:
        draw.text(
            (WIDTH - 55, 35),
            safe_text(county).upper(),
            font=FONT_LABEL,
            fill=(220, 225, 232),
            anchor="ra",
        )


def add_bottom_label(draw, text):
    draw.rectangle(
        (0, HEIGHT - 95, WIDTH, HEIGHT),
        fill=(7, 10, 15),
    )

    draw.text(
        (55, HEIGHT - 63),
        safe_text(text).upper(),
        font=FONT_LABEL,
        fill=(225, 230, 235),
        anchor="lm",
    )


# ============================================================
# SCENE CREATION
# ============================================================

def create_intro(story, index):
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        (8, 12, 18),
    )

    draw = ImageDraw.Draw(image)

    draw.rectangle(
        (0, 0, WIDTH, HEIGHT),
        fill=(8, 12, 18),
    )

    draw.rectangle(
        (0, 0, WIDTH, 18),
        fill=(220, 35, 45),
    )

    draw.text(
        (70, 650),
        "RIFT VALLEY",
        font=FONT_HUGE,
        fill=(255, 255, 255),
    )

    draw.text(
        (70, 790),
        "WATCH",
        font=FONT_HUGE,
        fill=(225, 40, 50),
    )

    draw.text(
        (70, 960),
        "REGIONAL NEWS",
        font=FONT_MEDIUM,
        fill=(205, 212, 220),
    )

    draw.text(
        (70, 1070),
        "STORY %02d" % index,
        font=FONT_MEDIUM,
        fill=(255, 255, 255),
    )

    county = safe_text(
        story.get("county")
    )

    if county:
        draw.text(
            (70, 1180),
            county.upper(),
            font=FONT_LABEL,
            fill=(185, 195, 205),
        )

    path = SCENES_DIR / f"story_{index:02d}_01_intro.png"

    image.save(path)

    return path


def create_headline(story, index, photo):
    bg = make_background(photo)
    draw = ImageDraw.Draw(bg)

    add_top_bar(
        draw,
        story.get("county"),
    )

    # Main photo window.
    if photo and photo.exists():
        try:
            with Image.open(photo) as im:
                photo_canvas = fit_crop(
                    im,
                    (WIDTH - 100, 720),
                )

            bg.paste(
                photo_canvas,
                (50, 155),
            )

            draw.rectangle(
                (50, 155, WIDTH - 50, 875),
                outline=(255, 255, 255),
                width=3,
            )

        except Exception:
            pass

    title = safe_text(
        story.get("title")
    )

    draw_wrapped(
        draw,
        title,
        (55, 1010),
        FONT_LARGE,
        (255, 255, 255),
        WIDTH - 110,
        line_spacing=16,
    )

    photo_type = (
        "POLITICAL FIGURE"
        if photo and "politician" in photo.name.lower()
        else ""
    )

    if photo_type:
        draw.text(
            (55, HEIGHT - 145),
            photo_type,
            font=FONT_LABEL,
            fill=(220, 40, 50),
        )

    add_bottom_label(
        draw,
        "BREAKING REGIONAL NEWS",
    )

    path = SCENES_DIR / f"story_{index:02d}_02_headline.png"

    bg.save(path)

    return path


def create_key_facts(story, index):
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        (11, 16, 23),
    )

    draw = ImageDraw.Draw(image)

    add_top_bar(
        draw,
        story.get("county"),
    )

    draw.text(
        (60, 170),
        "KEY FACTS",
        font=FONT_HUGE,
        fill=(255, 255, 255),
    )

    facts = story.get("verified_facts", [])

    if not isinstance(facts, list):
        facts = []

    useful = []

    for fact in facts:
        if not isinstance(fact, dict):
            continue

        label = safe_text(
            fact.get("label")
        )

        value = safe_text(
            fact.get("value")
        )

        if not value:
            continue

        if label.upper() == "IMPACT":
            continue

        useful.append(
            (label, value)
        )

    useful = useful[:5]

    y = 410

    for label, value in useful:
        rounded_rectangle(
            draw,
            (55, y, WIDTH - 55, y + 220),
            24,
            (20, 27, 37),
        )

        draw.text(
            (90, y + 35),
            label.replace("_", " ").upper(),
            font=FONT_LABEL,
            fill=(220, 45, 55),
        )

        draw_wrapped(
            draw,
            value,
            (90, y + 100),
            FONT_BODY_BOLD,
            (245, 247, 250),
            WIDTH - 180,
            line_spacing=8,
        )

        y += 255

        if y > HEIGHT - 280:
            break

    add_bottom_label(
        draw,
        "FACT CHECKED STORY DETAILS",
    )

    path = SCENES_DIR / f"story_{index:02d}_03_key_facts.png"

    image.save(path)

    return path


def create_location(story, index, photo):
    bg = make_background(photo)
    draw = ImageDraw.Draw(bg)

    add_top_bar(
        draw,
        story.get("county"),
    )

    draw.text(
        (60, 170),
        "WHERE IT IS HAPPENING",
        font=FONT_HUGE,
        fill=(255, 255, 255),
    )

    county = safe_text(
        story.get("county")
    )

    location = ""

    for fact in story.get("verified_facts", []):
        if not isinstance(fact, dict):
            continue

        if safe_text(
            fact.get("label")
        ).upper() == "LOCATION":
            location = safe_text(
                fact.get("value")
            )
            break

    if not location:
        location = county

    rounded_rectangle(
        draw,
        (55, 500, WIDTH - 55, 1050),
        30,
        (9, 15, 23),
        outline=(215, 35, 45),
        width=4,
    )

    draw.text(
        (100, 610),
        "COUNTY",
        font=FONT_LABEL,
        fill=(220, 40, 50),
    )

    draw_wrapped(
        draw,
        county,
        (100, 690),
        FONT_XLARGE,
        (255, 255, 255),
        WIDTH - 200,
        line_spacing=12,
    )

    draw.text(
        (100, 850),
        "LOCATION",
        font=FONT_LABEL,
        fill=(220, 40, 50),
    )

    draw_wrapped(
        draw,
        location,
        (100, 915),
        FONT_BODY,
        (230, 235, 240),
        WIDTH - 200,
        line_spacing=10,
    )

    add_bottom_label(
        draw,
        "RIFT VALLEY REGIONAL UPDATE",
    )

    path = SCENES_DIR / f"story_{index:02d}_04_location.png"

    bg.save(path)

    return path


def create_data_card(story, index):
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        (9, 14, 21),
    )

    draw = ImageDraw.Draw(image)

    add_top_bar(
        draw,
        story.get("county"),
    )

    draw.text(
        (60, 170),
        "THE NUMBERS",
        font=FONT_HUGE,
        fill=(255, 255, 255),
    )

    facts = story.get("verified_facts", [])

    selected = []

    priority = [
        "ROAD_LENGTH",
        "COST",
        "BUDGET",
        "VALUE",
        "AMOUNT",
        "NUMBER",
        "PEOPLE",
        "PROJECT_SIZE",
    ]

    for priority_label in priority:
        for fact in facts:
            if not isinstance(fact, dict):
                continue

            label = safe_text(
                fact.get("label")
            ).upper()

            value = safe_text(
                fact.get("value")
            )

            if label == priority_label and value:
                selected.append(
                    (label, value)
                )

    if not selected:
        for fact in facts:
            if not isinstance(fact, dict):
                continue

            label = safe_text(
                fact.get("label")
            )

            value = safe_text(
                fact.get("value")
            )

            if value:
                selected.append(
                    (label, value)
                )

    selected = selected[:3]

    if selected:
        box_h = 360
        gap = 45
        total = (
            len(selected) * box_h
            + (len(selected) - 1) * gap
        )

        y = 650 - total // 2

        for label, value in selected:
            rounded_rectangle(
                draw,
                (55, y, WIDTH - 55, y + box_h),
                28,
                (21, 29, 40),
            )

            draw.text(
                (95, y + 55),
                label.replace("_", " ").upper(),
                font=FONT_LABEL,
                fill=(220, 40, 50),
            )

            draw_wrapped(
                draw,
                value,
                (95, y + 135),
                FONT_XLARGE,
                (255, 255, 255),
                WIDTH - 190,
                line_spacing=10,
            )

            y += box_h + gap

    add_bottom_label(
        draw,
        "KEY DATA",
    )

    path = SCENES_DIR / f"story_{index:02d}_05_data.png"

    image.save(path)

    return path


def create_route(story, index, photo):
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        (9, 14, 21),
    )

    draw = ImageDraw.Draw(image)

    add_top_bar(
        draw,
        story.get("county"),
    )

    draw.text(
        (60, 170),
        "ROUTE / PROJECT AREA",
        font=FONT_HUGE,
        fill=(255, 255, 255),
    )

    route = ""

    for fact in story.get("verified_facts", []):
        if not isinstance(fact, dict):
            continue

        label = safe_text(
            fact.get("label")
        ).upper()

        if (
            label in [
                "PROJECT",
                "ROUTE",
                "CORRIDOR",
            ]
        ):
            route = safe_text(
                fact.get("value")
            )
            break

    if not route:
        visuals = story.get("visuals", [])

        for visual in visuals:
            if not isinstance(visual, dict):
                continue

            if "ROUTE" in safe_text(
                visual.get("type")
            ).upper():
                route = safe_text(
                    visual.get("description")
                )
                break

    if not route:
        route = "Project area shown in the report"

    # Route line.
    y_line = 860

    draw.line(
        (100, y_line, WIDTH - 100, y_line),
        fill=(220, 40, 50),
        width=8,
    )

    words = [
        part.strip()
        for part in re.split(
            r"/|→|—|-",
            route
        )
        if part.strip()
    ]

    words = words[:6]

    if words:
        spacing = (
            WIDTH - 200
        ) / max(1, len(words) - 1)

        for i, word in enumerate(words):
            x = int(100 + spacing * i)

            draw.ellipse(
                (
                    x - 18,
                    y_line - 18,
                    x + 18,
                    y_line + 18,
                ),
                fill=(235, 240, 245),
                outline=(220, 40, 50),
                width=5,
            )

            draw_wrapped(
                draw,
                word,
                (x, y_line + 55),
                FONT_LABEL,
                (240, 243, 247),
                180,
                line_spacing=5,
                anchor="ma",
            )

    draw_wrapped(
        draw,
        route,
        (70, 1150),
        FONT_BODY,
        (220, 225, 230),
        WIDTH - 140,
        line_spacing=10,
    )

    add_bottom_label(
        draw,
        "PROJECT CORRIDOR",
    )

    path = SCENES_DIR / f"story_{index:02d}_06_route.png"

    image.save(path)

    return path


def create_impact(story, index):
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        (10, 15, 22),
    )

    draw = ImageDraw.Draw(image)

    add_top_bar(
        draw,
        story.get("county"),
    )

    draw.text(
        (60, 170),
        "WHY IT MATTERS",
        font=FONT_HUGE,
        fill=(255, 255, 255),
    )

    impact = ""

    for fact in story.get("verified_facts", []):
        if not isinstance(fact, dict):
            continue

        if safe_text(
            fact.get("label")
        ).upper() == "IMPACT":
            impact = safe_text(
                fact.get("value")
            )
            break

    if not impact:
        impact = safe_text(
            story.get("impact")
        )

    if not impact:
        summary = safe_text(
            story.get("summary")
        )

        # Use the actual story summary rather than generic filler.
        impact = summary

    if not impact:
        impact = (
            "The development remains relevant to "
            "the communities and economic activity "
            "identified in the report."
        )

    rounded_rectangle(
        draw,
        (55, 520, WIDTH - 55, 1370),
        35,
        (20, 28, 38),
    )

    draw_wrapped(
        draw,
        impact,
        (105, 650),
        FONT_XLARGE,
        (245, 247, 250),
        WIDTH - 210,
        line_spacing=22,
    )

    add_bottom_label(
        draw,
        "IMPACT",
    )

    path = SCENES_DIR / f"story_{index:02d}_07_impact.png"

    image.save(path)

    return path


def create_official_statement(story, index, politician_photo=None):
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        (9, 14, 21),
    )

    draw = ImageDraw.Draw(image)

    add_top_bar(
        draw,
        story.get("county"),
    )

    draw.text(
        (60, 170),
        "OFFICIAL STATEMENT",
        font=FONT_HUGE,
        fill=(255, 255, 255),
    )

    statement = story.get(
        "official_statement",
        {},
    )

    if not isinstance(statement, dict):
        statement = {}

    speaker = safe_text(
        statement.get("speaker")
    )

    quote = safe_text(
        statement.get("quote")
    )

    if speaker:
        draw.text(
            (75, 480),
            speaker,
            font=FONT_MEDIUM,
            fill=(220, 40, 50),
        )

    if quote:
        draw.text(
            (80, 610),
            "“",
            font=FONT_HUGE,
            fill=(220, 40, 50),
        )

        draw_wrapped(
            draw,
            quote,
            (100, 760),
            FONT_BODY,
            (242, 245, 248),
            WIDTH - 200,
            line_spacing=18,
        )
    else:
        draw_wrapped(
            draw,
            "Officials are expected to provide further updates as implementation continues.",
            (90, 700),
            FONT_BODY,
            (230, 235, 240),
            WIDTH - 180,
            line_spacing=16,
        )

    # If political and a politician image exists,
    # use it on the official statement card.
    if politician_photo and politician_photo.exists():
        try:
            with Image.open(politician_photo) as im:
                portrait = fit_crop(
                    im,
                    (360, 420),
                )

            x = WIDTH - 410
            y = HEIGHT - 580

            image.paste(
                portrait,
                (x, y),
            )

            draw.rectangle(
                (x, y, x + 360, y + 420),
                outline=(220, 40, 50),
                width=4,
            )

        except Exception:
            pass

    add_bottom_label(
        draw,
        "OFFICIAL UPDATE",
    )

    path = SCENES_DIR / f"story_{index:02d}_08_statement.png"

    image.save(path)

    return path


def create_outro(story, index):
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        (8, 12, 18),
    )

    draw = ImageDraw.Draw(image)

    draw.rectangle(
        (0, 0, WIDTH, 16),
        fill=(220, 40, 50),
    )

    draw.text(
        (70, 700),
        "RIFT VALLEY",
        font=FONT_HUGE,
        fill=(255, 255, 255),
    )

    draw.text(
        (70, 840),
        "WATCH",
        font=FONT_HUGE,
        fill=(220, 40, 50),
    )

    draw.text(
        (70, 1050),
        "FOLLOW FOR REGIONAL NEWS",
        font=FONT_MEDIUM,
        fill=(215, 220, 225),
    )

    draw.text(
        (70, 1150),
        "RIFT VALLEY • KENYA",
        font=FONT_LABEL,
        fill=(175, 185, 195),
    )

    path = SCENES_DIR / f"story_{index:02d}_09_outro.png"

    image.save(path)

    return path


# ============================================================
# NARRATION
# ============================================================

def narration_for_scene(story, scene_type):
    title = safe_text(
        story.get("title")
    )

    county = safe_text(
        story.get("county")
    )

    summary = safe_text(
        story.get("summary")
    )

    facts = story.get(
        "verified_facts",
        [],
    )

    if scene_type == "intro":
        return (
            f"Rift Valley Watch. "
            f"Here is the latest regional story "
            f"from {county}."
        )

    if scene_type == "headline":
        return title

    if scene_type == "facts":
        parts = []

        for fact in facts:
            if not isinstance(fact, dict):
                continue

            label = safe_text(
                fact.get("label")
            ).upper()

            value = safe_text(
                fact.get("value")
            )

            if (
                value
                and label != "IMPACT"
            ):
                parts.append(
                    f"{label.replace('_', ' ').title()}: {value}."
                )

            if len(parts) >= 4:
                break

        return " ".join(parts)

    if scene_type == "location":
        return (
            f"The report places this development "
            f"in {county}. "
            f"{summary}"
        )

    if scene_type == "data":
        parts = []

        for fact in facts:
            if not isinstance(fact, dict):
                continue

            label = safe_text(
                fact.get("label")
            ).upper()

            value = safe_text(
                fact.get("value")
            )

            if label in [
                "ROAD_LENGTH",
                "COST",
                "BUDGET",
                "VALUE",
                "NUMBER",
                "PROJECT_SIZE",
            ]:
                parts.append(
                    f"{value}."
                )

        return " ".join(parts)

    if scene_type == "route":
        for fact in facts:
            if not isinstance(fact, dict):
                continue

            label = safe_text(
                fact.get("label")
            ).upper()

            if label in [
                "PROJECT",
                "ROUTE",
                "CORRIDOR",
            ]:
                return (
                    f"The project route or area is "
                    f"{safe_text(fact.get('value'))}."
                )

        return summary

    if scene_type == "impact":
        for fact in facts:
            if not isinstance(fact, dict):
                continue

            if safe_text(
                fact.get("label")
            ).upper() == "IMPACT":
                return safe_text(
                    fact.get("value")
                )

        return summary

    if scene_type == "statement":
        statement = story.get(
            "official_statement",
            {},
        )

        if isinstance(statement, dict):
            speaker = safe_text(
                statement.get("speaker")
            )

            quote = safe_text(
                statement.get("quote")
            )

            if speaker and quote:
                return (
                    f"{speaker} said: {quote}"
                )

            if quote:
                return quote

        return (
            "Officials are expected to provide "
            "further updates."
        )

    if scene_type == "outro":
        return (
            "That is the latest from Rift Valley Watch. "
            "Follow for more regional news."
        )

    return summary


def create_audio(text, output_path):
    text = safe_text(text)

    if not text:
        text = "Rift Valley Watch."

    tts = gTTS(
        text=text,
        lang="en",
        slow=False,
    )

    tts.save(str(output_path))


# ============================================================
# IMAGE → MP4 SCENE
# ============================================================

def image_to_video(image_path, audio_path, output_path):
    command = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(image_path),
        "-i",
        str(audio_path),
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-b:v",
        VIDEO_BITRATE,
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(FPS),
        "-c:a",
        "aac",
        "-b:a",
        AUDIO_BITRATE,
        "-ar",
        "44100",
        "-ac",
        "2",
        "-shortest",
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    run_command(command)


# ============================================================
# STORY ASSEMBLY
# ============================================================

def assemble_story(scene_paths, output_path):
    """
    IMPORTANT:
    This function receives scenes for ONE STORY ONLY.

    It never receives scenes from another story.
    """

    if not scene_paths:
        raise RuntimeError(
            "No scenes available for story."
        )

    concat_file = (
        output_path.parent
        / f"{output_path.stem}_concat.txt"
    )

    with open(
        concat_file,
        "w",
        encoding="utf-8",
    ) as f:

        for scene in scene_paths:
            f.write(
                "file '{}'\n".format(
                    scene.resolve()
                    .as_posix()
                    .replace("'", "'\\''")
                )
            )

    temp_output = (
        output_path.parent
        / f"{output_path.stem}_temp.mp4"
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
        "-c:v",
        "libx264",
        "-preset",
        "medium",
        "-b:v",
        VIDEO_BITRATE,
        "-pix_fmt",
        "yuv420p",
        "-r",
        str(FPS),
        "-c:a",
        "aac",
        "-b:a",
        AUDIO_BITRATE,
        "-ar",
        "44100",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        str(temp_output),
    ]

    run_command(command)

    if output_path.exists():
        output_path.unlink()

    temp_output.rename(output_path)

    try:
        concat_file.unlink()
    except Exception:
        pass


# ============================================================
# MP4 VALIDATION
# ============================================================

def validate_mp4(path):
    if not path.exists():
        return False

    if path.stat().st_size < 100000:
        return False

    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,duration",
        "-show_entries",
        "format=duration",
        "-of",
        "json",
        str(path),
    ]

    result = run_command(command)

    data = json.loads(
        result.stdout
    )

    streams = data.get(
        "streams",
        [],
    )

    if not streams:
        return False

    stream = streams[0]

    width = int(
        stream.get("width", 0)
    )

    height = int(
        stream.get("height", 0)
    )

    if width != WIDTH:
        print(
            f"Invalid width: {width}"
        )
        return False

    if height != HEIGHT:
        print(
            f"Invalid height: {height}"
        )
        return False

    return True


# ============================================================
# SINGLE STORY GENERATOR
# ============================================================

def generate_one_story(story, index):
    """
    Creates ONE complete MP4 for ONE story.
    """

    print()
    print("=" * 70)
    print(f"GENERATING STORY {index:02d}")
    print("=" * 70)

    title = safe_text(
        story.get("title")
    )

    county = safe_text(
        story.get("county")
    )

    print(f"TITLE : {title}")
    print(f"COUNTY: {county}")

    # --------------------------------------------------------
    # PHOTO
    # --------------------------------------------------------

    main_photo, photo_type = prepare_story_photo(
        story,
        index,
    )

    politician_photo = None

    if is_political_story(story):
        politician_photo = find_politician_photo(
            story
        )

        if politician_photo:
            print(
                "POLITICIAN PHOTO: "
                f"{politician_photo}"
            )

    # --------------------------------------------------------
    # CREATE SCENES
    # --------------------------------------------------------

    scene_specs = []

    intro = create_intro(
        story,
        index,
    )

    scene_specs.append(
        ("intro", intro)
    )

    headline = create_headline(
        story,
        index,
        main_photo,
    )

    scene_specs.append(
        ("headline", headline)
    )

    facts = create_key_facts(
        story,
        index,
    )

    scene_specs.append(
        ("facts", facts)
    )

    location = create_location(
        story,
        index,
        main_photo,
    )

    scene_specs.append(
        ("location", location)
    )

    data_card = create_data_card(
        story,
        index,
    )

    scene_specs.append(
        ("data", data_card)
    )

    route = create_route(
        story,
        index,
        main_photo,
    )

    scene_specs.append(
        ("route", route)
    )

    impact = create_impact(
        story,
        index,
    )

    scene_specs.append(
        ("impact", impact)
    )

    statement = create_official_statement(
        story,
        index,
        politician_photo,
    )

    scene_specs.append(
        ("statement", statement)
    )

    outro = create_outro(
        story,
        index,
    )

    scene_specs.append(
        ("outro", outro)
    )

    # --------------------------------------------------------
    # AUDIO + SCENE VIDEO
    # --------------------------------------------------------

    scene_videos = []

    for scene_number, (
        scene_type,
        image_path,
    ) in enumerate(
        scene_specs,
        start=1,
    ):

        print(
            f"Creating scene {scene_number}: "
            f"{scene_type}"
        )

        audio_path = (
            AUDIO_DIR
            / (
                f"story_{index:02d}_"
                f"{scene_number:02d}_"
                f"{scene_type}.mp3"
            )
        )

        video_path = (
            SCENES_DIR
            / (
                f"story_{index:02d}_"
                f"{scene_number:02d}_"
                f"{scene_type}.mp4"
            )
        )

        narration = narration_for_scene(
            story,
            scene_type,
        )

        create_audio(
            narration,
            audio_path,
        )

        image_to_video(
            image_path,
            audio_path,
            video_path,
        )

        scene_videos.append(
            video_path
        )

    # --------------------------------------------------------
    # ONE STORY = ONE FINAL MP4
    # --------------------------------------------------------

    output_path = (
        OUTPUT_DIR
        / f"rift_valley_watch_story_{index:02d}.mp4"
    )

    assemble_story(
        scene_videos,
        output_path,
    )

    if not validate_mp4(output_path):
        raise RuntimeError(
            f"FINAL STORY MP4 FAILED QC: {output_path}"
        )

    print()
    print(
        f"SUCCESS: STORY {index:02d}"
    )

    print(
        f"MP4: {output_path}"
    )

    print(
        f"PHOTO TYPE: {photo_type}"
    )

    return {
        "story_number": index,
        "title": title,
        "county": county,
        "category": safe_text(
            story.get("category")
        ),
        "political_story": is_political_story(
            story
        ),
        "main_photo": (
            str(main_photo)
            if main_photo
            else None
        ),
        "photo_type": photo_type,
        "politician_photo": (
            str(politician_photo)
            if politician_photo
            else None
        ),
        "output": str(output_path),
        "valid": True,
        "scenes": [
            {
                "type": scene_type,
                "image": str(image_path),
            }
            for scene_type, image_path
            in scene_specs
        ],
    }


# ============================================================
# MAIN
# ============================================================

def main():
    print("=" * 70)
    print("RIFT VALLEY WATCH V8")
    print("ONE STORY = ONE REEL")
    print("=" * 70)

    stories = load_stories()

    if not stories:
        raise RuntimeError(
            "No stories found."
        )

    print(
        f"Stories loaded: {len(stories)}"
    )

    # --------------------------------------------------------
    # IMPORTANT:
    # Each iteration is completely independent.
    # No scene list is shared between stories.
    # --------------------------------------------------------

    results = []

    for index, story in enumerate(
        stories,
        start=1,
    ):

        try:
            result = generate_one_story(
                story,
                index,
            )

            results.append(result)

        except Exception as exc:
            print()
            print(
                f"ERROR generating story {index}:"
            )
            print(exc)

            results.append(
                {
                    "story_number": index,
                    "title": safe_text(
                        story.get("title")
                    ),
                    "county": safe_text(
                        story.get("county")
                    ),
                    "valid": False,
                    "error": str(exc),
                }
            )

    # --------------------------------------------------------
    # BACKWARD COMPATIBILITY
    #
    # Current GitHub workflow expects:
    # output/rift_valley_watch.mp4
    #
    # Keep this as a copy of STORY 01 ONLY.
    #
    # It does NOT combine stories.
    # --------------------------------------------------------

    first_valid = next(
        (
            item
            for item in results
            if item.get("valid")
        ),
        None,
    )

    if first_valid:
        first_output = Path(
            first_valid["output"]
        )

        compatibility_output = (
            OUTPUT_DIR
            / "rift_valley_watch.mp4"
        )

        shutil.copy2(
            first_output,
            compatibility_output,
        )

        print()
        print(
            "Compatibility MP4 created:"
        )
        print(
            compatibility_output
        )

    # --------------------------------------------------------
    # VISUAL REPORT
    # --------------------------------------------------------

    report = {
        "generator": "Rift Valley Watch V8",
        "rule": "ONE STORY = ONE MP4",
        "stories_requested": len(stories),
        "stories_generated": len(
            [
                r for r in results
                if r.get("valid")
            ]
        ),
        "results": results,
    }

    with open(
        REPORT_FILE,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            report,
            f,
            indent=2,
            ensure_ascii=False,
        )

    # --------------------------------------------------------
    # FINAL SUMMARY
    # --------------------------------------------------------

    print()
    print("=" * 70)
    print("RIFT VALLEY WATCH GENERATION COMPLETE")
    print("=" * 70)

    for result in results:
        number = result.get(
            "story_number"
        )

        title = result.get(
            "title"
        )

        valid = result.get(
            "valid"
        )

        output = result.get(
            "output"
        )

        print()
        print(
            f"STORY {number:02d}: "
            f"{'SUCCESS' if valid else 'FAILED'}"
        )

        print(
            f"TITLE: {title}"
        )

        if output:
            print(
                f"MP4: {output}"
            )

    print()
    print(
        "IMPORTANT: Stories were NOT combined."
    )

    print(
        f"Visual report: {REPORT_FILE}"
    )


if __name__ == "__main__":
    main()
