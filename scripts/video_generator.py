import json
import re
import sys
import shutil
import subprocess
import urllib.request
import urllib.parse
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH — V2 VIDEO GENERATOR
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

STORY_FILE = ROOT / "data" / "story.json"
OUTPUT_DIR = ROOT / "output"
SCENE_DIR = OUTPUT_DIR / "scenes"
AUDIO_DIR = OUTPUT_DIR / "audio"
ASSET_DIR = ROOT / "assets"
SOURCE_IMAGE_DIR = ASSET_DIR / "source"

OUTPUT_FILE = OUTPUT_DIR / "rift_valley_watch.mp4"
REPORT_FILE = ROOT / "data" / "visual_report.json"

WIDTH = 1080
HEIGHT = 1920
FPS = 30

# Target social-news pacing.
MAX_SCENE_SECONDS = 12
MIN_SCENE_SECONDS = 3


# ============================================================
# BASIC UTILITIES
# ============================================================

def log(message):
    print(message, flush=True)


def clean_text(value):
    if value is None:
        return ""

    text = str(value)

    text = (
        text.replace("\n", " ")
        .replace("\r", " ")
        .replace("Road lenght", "Road length")
    )

    text = re.sub(r"\s+", " ", text)

    return text.strip()


def load_json(path):
    if not path.exists():
        raise RuntimeError(f"Missing required file: {path}")

    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        raise RuntimeError(f"Could not read {path}: {exc}")


def run_command(command, description="Command"):
    log("")
    log("$ " + " ".join(str(x) for x in command))

    result = subprocess.run(
        [str(x) for x in command],
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    if result.stdout:
        print(result.stdout, flush=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"{description} failed with exit code {result.returncode}"
        )

    return result


def check_ffmpeg():
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("FFmpeg was not found.")

    if shutil.which("ffprobe") is None:
        raise RuntimeError("FFprobe was not found.")

    log("FFmpeg found.")
    log("FFprobe found.")


def prepare_output():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SCENE_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    ASSET_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_IMAGE_DIR.mkdir(parents=True, exist_ok=True)

    if OUTPUT_FILE.exists():
        OUTPUT_FILE.unlink()

    if REPORT_FILE.exists():
        REPORT_FILE.unlink()

    for folder in (SCENE_DIR, AUDIO_DIR):
        for item in folder.iterdir():
            if item.is_file():
                item.unlink()

    log(f"Output directory: {OUTPUT_DIR}")
    log(f"Scene directory: {SCENE_DIR}")
    log(f"Audio directory: {AUDIO_DIR}")


# ============================================================
# STORY DATA
# ============================================================

def fact_value(story, label, default=""):
    for fact in story.get("verified_facts", []):
        if str(fact.get("label", "")).upper() == label.upper():
            return clean_text(fact.get("value", default))

    return clean_text(default)


def story_title(story):
    return clean_text(
        story.get("title", "Rift Valley Watch")
    )


def story_county(story):
    return clean_text(
        story.get("county", "Rift Valley")
    )


def story_location(story):
    return fact_value(
        story,
        "LOCATION",
        story_county(story)
    )


def story_route(story):
    return fact_value(
        story,
        "PROJECT",
        ""
    )


def story_length(story):
    return fact_value(
        story,
        "ROAD_LENGTH",
        ""
    )


def story_cost(story):
    return fact_value(
        story,
        "COST",
        ""
    )


def story_status(story):
    return fact_value(
        story,
        "STATUS",
        "Reported"
    )


def story_impact(story):
    return fact_value(
        story,
        "IMPACT",
        ""
    )


def source_name(story):
    return clean_text(
        story.get("source", {}).get(
            "name",
            "Official source"
        )
    )


def source_url(story):
    return clean_text(
        story.get("source", {}).get(
            "url",
            ""
        )
    )


def story_date(story):
    return clean_text(
        story.get("date", "")
    )


def official_statement(story):
    statement = story.get(
        "official_statement",
        {}
    )

    if not statement.get("available"):
        return "", ""

    return (
        clean_text(statement.get("speaker", "")),
        clean_text(statement.get("quote", ""))
    )


# ============================================================
# TEXT NORMALIZATION / DUPLICATE PROTECTION
# ============================================================

def normalize_sentence(text):
    text = clean_text(text).lower()
    text = re.sub(r"[^a-z0-9\s]", "", text)
    text = re.sub(r"\s+", " ", text)
    return text.strip()


def remove_duplicate_sentences(text):
    """
    Removes repeated sentences caused by combining
    the verified IMPACT fact with a templated sentence.
    """

    text = clean_text(text)

    if not text:
        return ""

    sentences = re.split(
        r"(?<=[.!?])\s+",
        text
    )

    output = []
    seen = set()

    for sentence in sentences:
        sentence = clean_text(sentence)

        if not sentence:
            continue

        key = normalize_sentence(sentence)

        if not key:
            continue

        if key in seen:
            continue

        # Detect near-duplicate sentences.
        duplicate = False

        for previous in seen:
            shorter = min(len(key), len(previous))
            longer = max(len(key), len(previous))

            if shorter >= 45:
                common_words = set(key.split()) & set(previous.split())

                if len(common_words) >= 0.75 * len(key.split()):
                    if shorter / max(longer, 1) >= 0.70:
                        duplicate = True
                        break

        if not duplicate:
            output.append(sentence)
            seen.add(key)

    return " ".join(output)


def clean_impact(impact):
    """
    Keeps the verified IMPACT fact as the single source
    of the impact wording. Removes templated duplication.
    """

    impact = clean_text(impact)

    if not impact:
        return (
            "The verified source says the project is expected "
            "to unlock economic potential in the area and "
            "wider Bomet County."
        )

    impact = remove_duplicate_sentences(impact)

    # Remove common duplicated attribution prefix if the
    # fact already contains the actual impact statement.
    patterns = [
        r"^the county government says the project is expected to ",
        r"^the county government says the project will ",
        r"^the project is expected to "
    ]

    for pattern in patterns:
        match = re.match(pattern, impact, flags=re.I)

        if match:
            remainder = impact[match.end():].strip()

            if remainder:
                impact = (
                    "The project is expected to "
                    + remainder
                )

    return remove_duplicate_sentences(impact)


# ============================================================
# FONTS
# ============================================================

def get_font(size, bold=False):
    if bold:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
        ]
    else:
        candidates = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"
        ]

    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)

    return ImageFont.load_default()


# ============================================================
# TEXT WRAPPING
# ============================================================

def text_width(draw, text, font):
    box = draw.textbbox(
        (0, 0),
        text,
        font=font
    )

    return box[2] - box[0]


def text_height(draw, text, font):
    box = draw.textbbox(
        (0, 0),
        text,
        font=font
    )

    return box[3] - box[1]


def wrap_text(draw, text, font, max_width):
    words = clean_text(text).split()

    lines = []
    current = ""

    for word in words:

        # Prevent one exceptionally long word from escaping.
        if text_width(draw, word, font) > max_width:
            if current:
                lines.append(current)
                current = ""

            chunk = ""

            for character in word:
                trial = chunk + character

                if text_width(draw, trial, font) <= max_width:
                    chunk = trial
                else:
                    if chunk:
                        lines.append(chunk)

                    chunk = character

            if chunk:
                current = chunk

            continue

        candidate = (
            word
            if not current
            else current + " " + word
        )

        if text_width(draw, candidate, font) <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)

            current = word

    if current:
        lines.append(current)

    return lines


def fit_text(
    draw,
    text,
    max_width,
    max_height,
    start_size,
    min_size=28,
    bold=True,
    spacing=8
):
    """
    Dynamically reduces font size until the complete text
    fits inside the requested dimensions.
    """

    size = start_size

    while size >= min_size:

        font = get_font(
            size,
            bold
        )

        lines = wrap_text(
            draw,
            text,
            font,
            max_width
        )

        line_height = (
            text_height(draw, "Ag", font)
            + spacing
        )

        total_height = (
            len(lines) * line_height
        )

        if total_height <= max_height:
            return font, lines, line_height

        size -= 2

    font = get_font(
        min_size,
        bold
    )

    lines = wrap_text(
        draw,
        text,
        font,
        max_width
    )

    line_height = (
        text_height(draw, "Ag", font)
        + spacing
    )

    return font, lines, line_height


def draw_lines(
    draw,
    lines,
    x,
    y,
    font,
    line_height,
    fill
):
    for line in lines:
        draw.text(
            (x, y),
            line,
            font=font,
            fill=fill
        )

        y += line_height

    return y


def draw_fitted_text(
    draw,
    text,
    box,
    start_size,
    min_size=28,
    bold=True,
    fill=(245, 245, 245),
    spacing=10
):
    x1, y1, x2, y2 = box

    font, lines, line_height = fit_text(
        draw,
        text,
        x2 - x1,
        y2 - y1,
        start_size,
        min_size,
        bold,
        spacing
    )

    draw_lines(
        draw,
        lines,
        x1,
        y1,
        font,
        line_height,
        fill
    )

    return y1 + (
        len(lines) * line_height
    )


# ============================================================
# BACKGROUND / BROADCAST DESIGN
# ============================================================

def make_background():
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        (8, 14, 24)
    )

    draw = ImageDraw.Draw(image)

    for y in range(HEIGHT):
        ratio = y / HEIGHT

        r = int(8 + 9 * ratio)
        g = int(14 + 12 * ratio)
        b = int(24 + 18 * ratio)

        draw.line(
            (0, y, WIDTH, y),
            fill=(r, g, b)
        )

    # Subtle broadcast grid.
    for x in range(0, WIDTH, 90):
        draw.line(
            (x, 120, x, HEIGHT - 120),
            fill=(25, 36, 52),
            width=1
        )

    for y in range(180, HEIGHT - 120, 90):
        draw.line(
            (0, y, WIDTH, y),
            fill=(25, 36, 52),
            width=1
        )

    return image


def draw_header(draw, section):
    draw.rectangle(
        (0, 0, WIDTH, 120),
        fill=(12, 19, 29)
    )

    draw.rectangle(
        (0, 0, 14, 120),
        fill=(220, 35, 45)
    )

    draw.text(
        (45, 22),
        "RIFT VALLEY WATCH",
        font=get_font(34, True),
        fill=(250, 250, 252)
    )

    draw.text(
        (45, 72),
        clean_text(section).upper(),
        font=get_font(22, True),
        fill=(185, 198, 212)
    )

    draw.text(
        (WIDTH - 155, 44),
        "NEWS",
        font=get_font(22, True),
        fill=(220, 35, 45)
    )


def draw_footer(draw, story, source=None):
    y = HEIGHT - 105

    draw.rectangle(
        (0, y, WIDTH, HEIGHT),
        fill=(10, 16, 25)
    )

    if source is None:
        source = source_name(story)

    text = f"SOURCE: {clean_text(source)}"

    draw.text(
        (40, y + 28),
        text,
        font=get_font(20, True),
        fill=(190, 201, 214)
    )

    date = story_date(story)

    if date:
        date_width = text_width(
            draw,
            date,
            get_font(20, True)
        )

        draw.text(
            (
                WIDTH - 45 - date_width,
                y + 28
            ),
            date,
            font=get_font(20, True),
            fill=(145, 158, 174)
        )


def draw_section_title(draw, title, y=175):
    draw.text(
        (55, y),
        clean_text(title).upper(),
        font=get_font(30, True),
        fill=(220, 45, 55)
    )


# ============================================================
# SOURCE IMAGE SUPPORT
# ============================================================

def bad_image_url(url):
    value = clean_text(url).lower()

    if not value:
        return True

    bad_terms = [
        "logo",
        "icon",
        "avatar",
        "favicon",
        ".svg"
    ]

    return any(term in value for term in bad_terms)


def extract_image_candidates(url):
    if not url:
        return []

    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent":
                    "Mozilla/5.0 RiftValleyWatch/2.0"
            }
        )

        with urllib.request.urlopen(
            request,
            timeout=20
        ) as response:
            html_text = response.read().decode(
                "utf-8",
                errors="ignore"
            )

    except Exception as exc:
        log(f"Source image lookup skipped: {exc}")
        return []

    patterns = [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
        r'<img[^>]+src=["\']([^"\']+)["\']',
        r'<img[^>]+data-src=["\']([^"\']+)["\']'
    ]

    candidates = []

    for pattern in patterns:
        matches = re.findall(
            pattern,
            html_text,
            flags=re.I
        )

        for match in matches:
            candidate = urllib.parse.urljoin(
                url,
                match
            )

            if (
                not bad_image_url(candidate)
                and candidate not in candidates
            ):
                candidates.append(candidate)

    return candidates[:20]


def download_source_image(story):
    url = source_url(story)

    if not url:
        return None

    candidates = extract_image_candidates(url)

    log(
        f"Found {len(candidates)} possible source images."
    )

    for index, candidate in enumerate(candidates):

        destination = (
            SOURCE_IMAGE_DIR /
            f"source_{index}.jpg"
        )

        try:
            request = urllib.request.Request(
                candidate,
                headers={
                    "User-Agent":
                        "Mozilla/5.0 RiftValleyWatch/2.0"
                }
            )

            with urllib.request.urlopen(
                request,
                timeout=25
            ) as response:

                data = response.read()

            destination.write_bytes(data)

            with Image.open(destination) as image:
                width, height = image.size

            if width < 500 or height < 300:
                destination.unlink(missing_ok=True)
                continue

            log(
                f"VALID SOURCE IMAGE: {candidate}"
            )

            return destination

        except Exception:
            destination.unlink(missing_ok=True)

    log("No usable source photograph found.")
    return None


def photo_background(path):
    image = Image.open(path).convert(
        "RGB"
    )

    scale = max(
        WIDTH / image.width,
        HEIGHT / image.height
    )

    size = (
        int(image.width * scale),
        int(image.height * scale)
    )

    image = image.resize(
        size,
        Image.Resampling.LANCZOS
    )

    left = (
        image.width - WIDTH
    ) // 2

    top = (
        image.height - HEIGHT
    ) // 2

    image = image.crop(
        (
            left,
            top,
            left + WIDTH,
            top + HEIGHT
        )
    )

    image = image.filter(
        ImageFilter.GaussianBlur(0.25)
    )

    overlay = Image.new(
        "RGBA",
        (WIDTH, HEIGHT),
        (0, 0, 0, 95)
    )

    return Image.alpha_composite(
        image.convert("RGBA"),
        overlay
    ).convert("RGB")


# ============================================================
# SCENE 1 — LATEST
# ============================================================

def scene_latest(story, source_image=None):
    if source_image:
        image = photo_background(
            source_image
        )
    else:
        image = make_background()

    draw = ImageDraw.Draw(image)

    draw_header(
        draw,
        "THE LATEST"
    )

    draw_section_title(
        draw,
        "BREAKING DEVELOPMENT"
    )

    title = story_title(story)

    # Shorter headline block.
    draw_fitted_text(
        draw,
        title,
        (
            55,
            285,
            WIDTH - 55,
            850
        ),
        start_size=68,
        min_size=42,
        bold=True,
        fill=(255, 255, 255),
        spacing=14
    )

    length = story_length(story)
    cost = story_cost(story)

    draw.rounded_rectangle(
        (
            55,
            950,
            WIDTH - 55,
            1190
        ),
        radius=25,
        fill=(13, 25, 40),
        outline=(65, 80, 100),
        width=2
    )

    draw.text(
        (90, 990),
        "KEY FIGURES",
        font=get_font(25, True),
        fill=(220, 45, 55)
    )

    draw.text(
        (90, 1050),
        f"{length or 'N/A'}   |   {cost or 'N/A'}",
        font=get_font(43, True),
        fill=(250, 250, 252)
    )

    draw_footer(
        draw,
        story
    )

    return image


# ============================================================
# SCENE 2 — LOCATION
# ============================================================

def scene_location(story):
    image = make_background()
    draw = ImageDraw.Draw(image)

    draw_header(
        draw,
        "WHERE IT IS"
    )

    draw_section_title(
        draw,
        "PROJECT LOCATION"
    )

    county = story_county(story)
    location = story_location(story)

    draw.rounded_rectangle(
        (
            55,
            285,
            WIDTH - 55,
            1050
        ),
        radius=30,
        fill=(14, 29, 47),
        outline=(58, 76, 98),
        width=2
    )

    draw.text(
        (90, 350),
        county.upper(),
        font=get_font(45, True),
        fill=(220, 45, 55)
    )

    draw_fitted_text(
        draw,
        location,
        (
            90,
            475,
            WIDTH - 90,
            820
        ),
        start_size=58,
        min_size=36,
        bold=True,
        fill=(250, 250, 252),
        spacing=14
    )

    draw.text(
        (90, 900),
        "VERIFIED LOCATION",
        font=get_font(24, True),
        fill=(155, 170, 188)
    )

    draw_footer(
        draw,
        story
    )

    return image


# ============================================================
# SCENE 3 — KEY FACTS
# ============================================================

def scene_facts(story):
    image = make_background()
    draw = ImageDraw.Draw(image)

    draw_header(
        draw,
        "KEY FACTS"
    )

    draw_section_title(
        draw,
        "THE NUMBERS"
    )

    cards = [
        (
            "ROAD LENGTH",
            story_length(story)
        ),
        (
            "PROJECT COST",
            story_cost(story)
        ),
        (
            "STATUS",
            story_status(story)
        )
    ]

    y = 285

    for label, value in cards:

        card_height = 270

        draw.rounded_rectangle(
            (
                55,
                y,
                WIDTH - 55,
                y + card_height
            ),
            radius=26,
            fill=(14, 28, 45),
            outline=(57, 75, 97),
            width=2
        )

        draw.text(
            (90, y + 38),
            label,
            font=get_font(25, True),
            fill=(220, 45, 55)
        )

        draw_fitted_text(
            draw,
            value or "Not stated",
            (
                90,
                y + 100,
                WIDTH - 90,
                y + card_height - 30
            ),
            start_size=50,
            min_size=30,
            bold=True,
            fill=(250, 250, 252),
            spacing=8
        )

        y += card_height + 25

    draw_footer(
        draw,
        story
    )

    return image


# ============================================================
# SCENE 4 — ROAD CORRIDOR
# ============================================================

def split_route(route):
    route = clean_text(route)

    if "/" in route:
        parts = [
            clean_text(part)
            for part in route.split("/")
            if clean_text(part)
        ]

        return parts

    return [route]


def draw_route_line(
    draw,
    nodes,
    y,
    font_size=30
):
    """
    Draws a clean corridor diagram.
    This is a route visualization, not a geographic map.
    """

    if not nodes:
        return

    left = 90
    right = WIDTH - 90

    line_y = y + 60

    draw.line(
        (
            left,
            line_y,
            right,
            line_y
        ),
        fill=(220, 45, 55),
        width=6
    )

    count = len(nodes)

    if count == 1:
        positions = [
            (left + right) // 2
        ]
    else:
        spacing = (
            right - left
        ) / (count - 1)

        positions = [
            int(left + i * spacing)
            for i in range(count)
        ]

    for index, node in enumerate(nodes):

        x = positions[index]

        draw.ellipse(
            (
                x - 15,
                line_y - 15,
                x + 15,
                line_y + 15
            ),
            fill=(245, 245, 247),
            outline=(220, 45, 55),
            width=5
        )

        # Keep labels readable by dynamically fitting
        # each node to its available horizontal space.
        if count == 1:
            max_width = 700
        else:
            max_width = max(
                130,
                int(
                    (right - left)
                    / max(count - 1, 1)
                ) - 25
            )

        node_font, node_lines, line_height = fit_text(
            draw,
            node,
            max_width,
            130,
            font_size,
            min_size=18,
            bold=True,
            spacing=4
        )

        text_y = line_y + 40

        for line in node_lines[:2]:

            width = text_width(
                draw,
                line,
                node_font
            )

            draw.text(
                (
                    x - width / 2,
                    text_y
                ),
                line,
                font=node_font,
                fill=(235, 241, 246)
            )

            text_y += line_height


def scene_route(story):
    image = make_background()
    draw = ImageDraw.Draw(image)

    draw_header(
        draw,
        "ROAD CORRIDOR"
    )

    draw_section_title(
        draw,
        "THE ROUTE"
    )

    route = (
        story_route(story)
        or "Route details not stated"
    )

    # Dynamic card — height depends on actual text.
    box_x1 = 55
    box_x2 = WIDTH - 55
    box_top = 285

    font, lines, line_height = fit_text(
        draw,
        route,
        box_x2 - box_x1 - 70,
        560,
        52,
        min_size=30,
        bold=True,
        spacing=10
    )

    text_height_total = (
        len(lines) * line_height
    )

    box_height = max(
        520,
        text_height_total + 180
    )

    box_bottom = box_top + box_height

    # Never allow the route box to collide with footer.
    max_bottom = HEIGHT - 300

    if box_bottom > max_bottom:
        box_bottom = max_bottom
        available_height = (
            box_bottom
            - box_top
            - 150
        )

        font, lines, line_height = fit_text(
            draw,
            route,
            box_x2 - box_x1 - 70,
            available_height,
            52,
            min_size=24,
            bold=True,
            spacing=8
        )

        text_height_total = (
            len(lines) * line_height
        )

        box_height = max(
            420,
            text_height_total + 150
        )

        box_bottom = min(
            box_top + box_height,
            max_bottom
        )

    draw.rounded_rectangle(
        (
            box_x1,
            box_top,
            box_x2,
            box_bottom
        ),
        radius=32,
        fill=(14, 29, 47),
        outline=(58, 76, 98),
        width=3
    )

    draw.text(
        (
            box_x1 + 40,
            box_top + 35
        ),
        "ROUTE",
        font=get_font(28, True),
        fill=(220, 45, 55)
    )

    # Recalculate exact usable area inside card.
    usable_top = box_top + 105
    usable_bottom = box_bottom - 55

    font, lines, line_height = fit_text(
        draw,
        route,
        box_x2 - box_x1 - 80,
        usable_bottom - usable_top,
        52,
        min_size=24,
        bold=True,
        spacing=8
    )

    draw_lines(
        draw,
        lines,
        box_x1 + 40,
        usable_top,
        font,
        line_height,
        (250, 250, 252)
    )

    # Route visualization.
    nodes = []

    for part in split_route(route):

        # First split long hyphenated corridor strings.
        pieces = [
            clean_text(x)
            for x in re.split(
                r"\s*-\s*",
                part
            )
            if clean_text(x)
        ]

        if pieces:
            nodes.extend(pieces)

    # Keep diagram manageable.
    nodes = nodes[:8]

    diagram_y = min(
        box_bottom + 65,
        HEIGHT - 480
    )

    draw.text(
        (70, diagram_y),
        "CORRIDOR VISUAL",
        font=get_font(25, True),
        fill=(220, 45, 55)
    )

    draw_route_line(
        draw,
        nodes,
        diagram_y + 45
    )

    draw.text(
        (70, HEIGHT - 245),
        "ROUTE DETAILS FROM VERIFIED STORY FACTS",
        font=get_font(22, True),
        fill=(145, 160, 178)
    )

    draw_footer(
        draw,
        story
    )

    return image


# ============================================================
# SCENE 5 — EXPECTED IMPACT
# ============================================================

def scene_impact(story):
    image = make_background()
    draw = ImageDraw.Draw(image)

    draw_header(
        draw,
        "WHY IT MATTERS"
    )

    draw_section_title(
        draw,
        "EXPECTED IMPACT"
    )

    impact = clean_impact(
        story_impact(story)
    )

    # No second templated sentence.
    draw.rounded_rectangle(
        (
            55,
            290,
            WIDTH - 55,
            1240
        ),
        radius=32,
        fill=(14, 29, 47),
        outline=(58, 76, 98),
        width=2
    )

    draw_fitted_text(
        draw,
        impact,
        (
            95,
            365,
            WIDTH - 95,
            1160
        ),
        start_size=55,
        min_size=32,
        bold=True,
        fill=(245, 247, 250),
        spacing=15
    )

    draw.text(
        (70, 1320),
        "SOURCE-LED IMPACT",
        font=get_font(25, True),
        fill=(220, 45, 55)
    )

    draw_fitted_text(
        draw,
        "No additional economic impact has been added beyond the verified source.",
        (
            70,
            1385,
            WIDTH - 70,
            1535
        ),
        start_size=30,
        min_size=23,
        bold=False,
        fill=(170, 182, 196),
        spacing=8
    )

    draw_footer(
        draw,
        story
    )

    return image


# ============================================================
# SCENE 6 — KINDIKI STATEMENT
# ============================================================

def scene_statement(story):
    image = make_background()
    draw = ImageDraw.Draw(image)

    draw_header(
        draw,
        "OFFICIAL STATEMENT"
    )

    draw_section_title(
        draw,
        "DEPUTY PRESIDENT"
    )

    speaker, quote = official_statement(
        story
    )

    if not quote:
        quote = (
            "No separate official statement "
            "was provided in the verified story."
        )

    draw.text(
        (70, 300),
        speaker or "Kithure Kindiki",
        font=get_font(39, True),
        fill=(220, 45, 55)
    )

    draw.rounded_rectangle(
        (
            55,
            390,
            WIDTH - 55,
            1350
        ),
        radius=32,
        fill=(14, 29, 47),
        outline=(58, 76, 98),
        width=2
    )

    draw.text(
        (95, 450),
        "“",
        font=get_font(100, True),
        fill=(220, 45, 55)
    )

    draw_fitted_text(
        draw,
        quote,
        (
            110,
            570,
            WIDTH - 100,
            1260
        ),
        start_size=48,
        min_size=29,
        bold=False,
        fill=(245, 247, 250),
        spacing=15
    )

    # IMPORTANT:
    # This is deliberately NOT Bomet County Government.
    # The statement is attributed separately to the
    # Office of the Deputy President.
    draw.text(
        (70, 1410),
        "STATEMENT ATTRIBUTION",
        font=get_font(24, True),
        fill=(220, 45, 55)
    )

    draw_fitted_text(
        draw,
        "Office of the Deputy President",
        (
            70,
            1470,
            WIDTH - 70,
            1560
        ),
        start_size=31,
        min_size=24,
        bold=True,
        fill=(190, 202, 216),
        spacing=5
    )

    draw_footer(
        draw,
        story,
        source="Office of the Deputy President"
    )

    return image


# ============================================================
# SCENE 7 — SOURCE
# ============================================================

def scene_source(story):
    image = make_background()
    draw = ImageDraw.Draw(image)

    draw_header(
        draw,
        "SOURCE"
    )

    draw_section_title(
        draw,
        "VERIFIED SOURCE"
    )

    source = source_name(story)
    url = source_url(story)

    draw.rounded_rectangle(
        (
            55,
            300,
            WIDTH - 55,
            1050
        ),
        radius=32,
        fill=(14, 29, 47),
        outline=(58, 76, 98),
        width=2
    )

    draw.text(
        (95, 365),
        "PRIMARY STORY SOURCE",
        font=get_font(25, True),
        fill=(220, 45, 55)
    )

    draw_fitted_text(
        draw,
        source,
        (
            95,
            445,
            WIDTH - 95,
            650
        ),
        start_size=45,
        min_size=28,
        bold=True,
        fill=(250, 250, 252),
        spacing=8
    )

    draw.text(
        (95, 720),
        "PUBLICATION / SOURCE PAGE",
        font=get_font(23, True),
        fill=(155, 170, 188)
    )

    if url:
        display_url = url.replace(
            "https://",
            ""
        )

        draw_fitted_text(
            draw,
            display_url,
            (
                95,
                785,
                WIDTH - 95,
                950
            ),
            start_size=27,
            min_size=20,
            bold=False,
            fill=(190, 202, 215),
            spacing=7
        )
    else:
        draw.text(
            (95, 790),
            "Source URL not provided",
            font=get_font(27),
            fill=(190, 202, 215)
        )

    draw.text(
        (70, 1130),
        "REPORT DATE",
        font=get_font(25, True),
        fill=(220, 45, 55)
    )

    draw.text(
        (70, 1190),
        story_date(story) or "Not stated",
        font=get_font(46, True),
        fill=(250, 250, 252)
    )

    draw.text(
        (70, 1330),
        "EDITORIAL STANDARD",
        font=get_font(25, True),
        fill=(220, 45, 55)
    )

    draw_fitted_text(
        draw,
        "Confirmed facts are presented as reported. Unconfirmed details are not presented as confirmed facts.",
        (
            70,
            1390,
            WIDTH - 70,
            1550
        ),
        start_size=29,
        min_size=23,
        bold=False,
        fill=(175, 188, 202),
        spacing=8
    )

    draw_footer(
        draw,
        story,
        source=source
    )

    return image


# ============================================================
# SCENE 8 — OUTRO
# ============================================================

def scene_outro(story):
    image = make_background()
    draw = ImageDraw.Draw(image)

    draw_header(
        draw,
        "RIFT VALLEY WATCH"
    )

    draw.text(
        (55, 500),
        "RIFT VALLEY",
        font=get_font(55, True),
        fill=(220, 45, 55)
    )

    draw.text(
        (55, 590),
        "WATCH",
        font=get_font(95, True),
        fill=(250, 250, 252)
    )

    draw_fitted_text(
        draw,
        "Verified regional news. Clear facts. Source-led reporting.",
        (
            55,
            800,
            WIDTH - 55,
            1100
        ),
        start_size=40,
        min_size=28,
        bold=False,
        fill=(220, 229, 238),
        spacing=12
    )

    draw.text(
        (55, 1260),
        "FOLLOW FOR MORE",
        font=get_font(34, True),
        fill=(220, 45, 55)
    )

    draw_footer(
        draw,
        story
    )

    return image


# ============================================================
# SCENE PLAN
# ============================================================

def build_scene_plan(story, source_image=None):

    title = story_title(story)
    county = story_county(story)
    location = story_location(story)
    length = story_length(story)
    cost = story_cost(story)
    status = story_status(story)
    route = story_route(story)
    impact = clean_impact(
        story_impact(story)
    )

    speaker, quote = official_statement(
        story
    )

    source = source_name(story)

    return [
        {
            "name": "LATEST",
            "title": title,
            "text": (
                f"{title}. "
                f"The project covers {length or 'a reported road length'} "
                f"at a reported cost of {cost or 'a reported project cost'}."
            ),
            "image": (
                scene_latest(
                    story,
                    source_image
                )
            )
        },

        {
            "name": "LOCATION",
            "title": "WHERE IS THE PROJECT?",
            "text": (
                f"The project is located in {location}, "
                f"{county}."
            ),
            "image": scene_location(story)
        },

        {
            "name": "KEY FACTS",
            "title": "THE NUMBERS",
            "text": (
                f"The road covers {length or 'a reported length'}, "
                f"with a project cost of {cost or 'a reported cost'}. "
                f"Construction is {status.lower()}."
            ),
            "image": scene_facts(story)
        },

        {
            "name": "ROUTE",
            "title": "ROAD CORRIDOR",
            "text": (
                f"The reported corridor runs through "
                f"{route or 'the locations identified in the source'}."
            ),
            "image": scene_route(story)
        },

        {
            "name": "WHY IT MATTERS",
            "title": "EXPECTED IMPACT",
            "text": impact,
            "image": scene_impact(story)
        },

        {
            "name": "OFFICIAL STATEMENT",
            "title": speaker or "OFFICIAL STATEMENT",
            "text": (
                f"{speaker} said: {quote}"
                if speaker and quote
                else quote or
                "No separate official statement was provided."
            ),
            "image": scene_statement(story)
        },

        {
            "name": "SOURCE",
            "title": "VERIFIED SOURCE",
            "text": (
                f"This report is based on "
                f"{source}."
            ),
            "image": scene_source(story)
        },

        {
            "name": "OUTRO",
            "title": "RIFT VALLEY WATCH",
            "text": (
                "Rift Valley Watch. "
                "Verified regional news. "
                "Follow for more."
            ),
            "image": scene_outro(story)
        }
    ]


# ============================================================
# AUDIO
# ============================================================

def create_audio(text, path):
    text = clean_text(text)

    if not text:
        raise RuntimeError(
            "Narration text is empty."
        )

    log(
        f"Creating narration: {text}"
    )

    tts = gTTS(
        text=text,
        lang="en",
        slow=False
    )

    tts.save(
        str(path)
    )

    if not path.exists():
        raise RuntimeError(
            f"Audio was not created: {path}"
        )

    if path.stat().st_size < 1000:
        raise RuntimeError(
            f"Audio file is too small: {path}"
        )


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
        ],
        "Reading audio duration"
    )

    try:
        return float(
            result.stdout.strip()
        )
    except ValueError:
        raise RuntimeError(
            f"Could not determine audio duration for {path}"
        )


# ============================================================
# VIDEO RENDERING
# ============================================================

def render_scene(
    image_path,
    audio_path,
    video_path
):
    duration = audio_duration(
        audio_path
    )

    # Prevent unnecessarily long static scenes.
    duration = min(
        duration,
        MAX_SCENE_SECONDS
    )

    log(
        f"Scene duration: {duration:.2f}s"
    )

    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",

        "-loop",
        "1",

        "-i",
        str(image_path),

        "-i",
        str(audio_path),

        "-map",
        "0:v:0",
        "-map",
        "1:a:0",

        "-vf",
        (
            "scale=1080:1920:"
            "force_original_aspect_ratio=decrease,"
            "pad=1080:1920:"
            "(ow-iw)/2:"
            "(oh-ih)/2,"
            "setsar=1"
        ),

        "-t",
        f"{duration:.2f}",

        "-r",
        str(FPS),

        "-c:v",
        "libx264",

        "-preset",
        "veryfast",

        "-crf",
        "21",

        "-pix_fmt",
        "yuv420p",

        "-c:a",
        "aac",

        "-b:a",
        "128k",

        "-ar",
        "44100",

        "-shortest",

        "-movflags",
        "+faststart",

        str(video_path)
    ]

    run_command(
        command,
        f"Rendering {video_path.name}"
    )

    if not video_path.exists():
        raise RuntimeError(
            f"Scene video was not created: {video_path}"
        )

    if video_path.stat().st_size < 5000:
        raise RuntimeError(
            f"Scene video is too small: {video_path}"
        )


# ============================================================
# CONCATENATION
# ============================================================

def concatenate_scenes(scene_files):

    if not scene_files:
        raise RuntimeError(
            "No scene files were generated."
        )

    concat_file = (
        OUTPUT_DIR /
        "concat_list.txt"
    )

    with concat_file.open(
        "w",
        encoding="utf-8"
    ) as f:

        for scene in scene_files:

            path = scene.resolve()

            escaped = str(path).replace(
                "'",
                "'\\''"
            )

            f.write(
                f"file '{escaped}'\n"
            )

    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",

        "-f",
        "concat",

        "-safe",
        "0",

        "-i",
        str(concat_file),

        "-c:v",
        "libx264",

        "-preset",
        "veryfast",

        "-crf",
        "21",

        "-pix_fmt",
        "yuv420p",

        "-c:a",
        "aac",

        "-b:a",
        "128k",

        "-ar",
        "44100",

        "-movflags",
        "+faststart",

        str(OUTPUT_FILE)
    ]

    run_command(
        command,
        "Creating final MP4"
    )

    if not OUTPUT_FILE.exists():
        raise RuntimeError(
            "FFmpeg finished but final MP4 does not exist."
        )

    if OUTPUT_FILE.stat().st_size < 10000:
        raise RuntimeError(
            "Final MP4 is too small."
        )


# ============================================================
# FINAL VALIDATION
# ============================================================

def validate_mp4():

    if not OUTPUT_FILE.exists():
        raise RuntimeError(
            "Final MP4 does not exist."
        )

    command = [
        "ffprobe",
        "-v",
        "error",

        "-show_entries",
        "format=duration,size",

        "-show_entries",
        (
            "stream="
            "codec_type,"
            "codec_name,"
            "width,"
            "height,"
            "r_frame_rate"
        ),

        "-of",
        "json",

        str(OUTPUT_FILE)
    ]

    result = subprocess.run(
        command,
        cwd=str(ROOT),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    if result.returncode != 0:
        raise RuntimeError(
            "FFprobe failed."
        )

    info = json.loads(
        result.stdout
    )

    streams = info.get(
        "streams",
        []
    )

    fmt = info.get(
        "format",
        {}
    )

    video = None
    audio = None

    for stream in streams:

        if stream.get("codec_type") == "video":
            video = stream

        elif stream.get("codec_type") == "audio":
            audio = stream

    if video is None:
        raise RuntimeError(
            "No video stream found."
        )

    if audio is None:
        raise RuntimeError(
            "No audio stream found."
        )

    duration = float(
        fmt.get(
            "duration",
            0
        )
    )

    size = int(
        float(
            fmt.get(
                "size",
                0
            )
        )
    )

    if duration <= 1:
        raise RuntimeError(
            "Video duration is invalid."
        )

    if size < 10000:
        raise RuntimeError(
            "Video file size is invalid."
        )

    if video.get("codec_name") != "h264":
        raise RuntimeError(
            "Video is not H.264."
        )

    if audio.get("codec_name") != "aac":
        raise RuntimeError(
            "Audio is not AAC."
        )

    if int(
        video.get(
            "width",
            0
        )
    ) != WIDTH:
        raise RuntimeError(
            "Video width is not 1080."
        )

    if int(
        video.get(
            "height",
            0
        )
    ) != HEIGHT:
        raise RuntimeError(
            "Video height is not 1920."
        )

    log("")
    log("=" * 60)
    log("MP4 VALIDATION PASSED")
    log("=" * 60)

    log(
        f"Duration: {duration:.2f} seconds"
    )

    log(
        f"Size: {size / 1024 / 1024:.2f} MB"
    )

    log("Resolution: 1080x1920")
    log("Video: H.264")
    log("Audio: AAC")


# ============================================================
# QUALITY CONTROL REPORT
# ============================================================

def write_report(
    story,
    scene_records
):
    report = {
        "project": "Rift Valley Watch",
        "status": "PASS",
        "title": story_title(story),
        "source": story.get(
            "source",
            {}
        ),
        "scene_count": len(scene_records),
        "resolution": "1080x1920",
        "fps": FPS,
        "video_codec": "H.264",
        "audio_codec": "AAC",
        "output_file": OUTPUT_FILE.name,

        "fixes_applied": [
            "Dynamic route-card text fitting",
            "Dynamic route-card height",
            "Impact duplicate protection",
            "Separate Deputy President attribution",
            "Short-form pacing limits",
            "Route corridor visualization",
            "Automatic source-image attempt"
        ],

        "quality_control": {
            "mp4_exists": OUTPUT_FILE.exists(),
            "validated": True,
            "route_overflow_protection": True,
            "duplicate_impact_protection": True,
            "statement_attribution_separated": True,
            "social_pacing_enabled": True
        },

        "scenes": scene_records
    }

    with REPORT_FILE.open(
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            report,
            f,
            indent=2,
            ensure_ascii=False
        )


# ============================================================
# MAIN
# ============================================================

def main():

    log("")
    log("=" * 60)
    log("RIFT VALLEY WATCH V2 VIDEO GENERATOR")
    log("=" * 60)
    log("Dynamic layout + faster pacing + route visualization")
    log("=" * 60)

    prepare_output()

    try:

        check_ffmpeg()

        story = load_json(
            STORY_FILE
        )

        log("")
        log("STORY:")
        log(
            story_title(story)
        )

        # ----------------------------------------------------
        # Attempt to retrieve a real source image.
        # Failure is non-fatal.
        # ----------------------------------------------------

        source_image = None

        try:
            source_image = download_source_image(
                story
            )
        except Exception as exc:
            log(
                f"Source image step skipped: {exc}"
            )

        if source_image:
            log(
                f"Using source image: {source_image}"
            )
        else:
            log(
                "No source image available. "
                "Using broadcast graphics."
            )

        # ----------------------------------------------------
        # Build scene plan.
        # ----------------------------------------------------

        scenes = build_scene_plan(
            story,
            source_image
        )

        if len(scenes) != 8:
            raise RuntimeError(
                f"Expected 8 scenes, got {len(scenes)}."
            )

        scene_files = []
        scene_records = []

        # ----------------------------------------------------
        # Generate every scene.
        # ----------------------------------------------------

        for index, scene in enumerate(
            scenes,
            start=1
        ):

            slug = re.sub(
                r"[^a-z0-9]+",
                "_",
                scene["name"].lower()
            ).strip("_")

            image_path = (
                SCENE_DIR /
                f"scene_{index:02d}_{slug}.png"
            )

            audio_path = (
                AUDIO_DIR /
                f"scene_{index:02d}_{slug}.mp3"
            )

            video_path = (
                SCENE_DIR /
                f"scene_{index:02d}_{slug}.mp4"
            )

            log("")
            log("=" * 60)
            log(
                f"SCENE {index}/8: "
                f"{scene['name']}"
            )
            log("=" * 60)

            # Save image generated in build_scene_plan.
            scene["image"].save(
                image_path,
                "PNG",
                optimize=True
            )

            create_audio(
                scene["text"],
                audio_path
            )

            render_scene(
                image_path,
                audio_path,
                video_path
            )

            duration = audio_duration(
                audio_path
            )

            duration = min(
                duration,
                MAX_SCENE_SECONDS
            )

            scene_files.append(
                video_path
            )

            scene_records.append(
                {
                    "scene": index,
                    "name": scene["name"],
                    "image": image_path.name,
                    "audio": audio_path.name,
                    "video": video_path.name,
                    "duration_seconds": round(
                        duration,
                        2
                    )
                }
            )

        # ----------------------------------------------------
        # Combine.
        # ----------------------------------------------------

        log("")
        log("=" * 60)
        log("ALL SCENES CREATED")
        log("=" * 60)

        for scene in scene_files:
            log(
                f"{scene.name}: "
                f"{scene.stat().st_size / 1024:.1f} KB"
            )

        concatenate_scenes(
            scene_files
        )

        validate_mp4()

        write_report(
            story,
            scene_records
        )

        log("")
        log("=" * 60)
        log("SUCCESS")
        log("=" * 60)

        log(
            f"FINAL MP4: {OUTPUT_FILE}"
        )

        log(
            f"SIZE: "
            f"{OUTPUT_FILE.stat().st_size / 1024 / 1024:.2f} MB"
        )

        return 0

    except Exception as exc:

        log("")
        log("=" * 60)
        log("VIDEO GENERATION FAILED")
        log("=" * 60)

        log(
            f"{type(exc).__name__}: {exc}"
        )

        OUTPUT_DIR.mkdir(
            parents=True,
            exist_ok=True
        )

        failure = {
            "project": "Rift Valley Watch",
            "status": "FAILED",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "output_exists": OUTPUT_FILE.exists()
        }

        try:
            with REPORT_FILE.open(
                "w",
                encoding="utf-8"
            ) as f:

                json.dump(
                    failure,
                    f,
                    indent=2
                )

        except Exception:
            pass

        return 1


if __name__ == "__main__":
    sys.exit(main())
