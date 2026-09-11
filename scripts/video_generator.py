import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH
# REAL-TIME REGIONAL BULLETIN VIDEO GENERATOR
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

STORY_FILE = ROOT / "data" / "story.json"
SCRIPT_FILE = ROOT / "data" / "script.json"

OUTPUT_DIR = ROOT / "output"
SCENE_DIR = OUTPUT_DIR / "scenes"
AUDIO_DIR = OUTPUT_DIR / "audio"

ASSET_DIR = ROOT / "assets"
MUSIC_FILE = ASSET_DIR / "music" / "news_bed.mp3"

OUTPUT_FILE = OUTPUT_DIR / "rift_valley_watch.mp4"
REPORT_FILE = ROOT / "data" / "visual_report.json"

WIDTH = 1080
HEIGHT = 1920
FPS = 30

BG = (8, 13, 23)
PANEL = (19, 29, 45)
WHITE = (245, 247, 250)
MUTED = (170, 181, 196)
RED = (218, 38, 52)
BLUE = (42, 100, 205)


# ============================================================
# BASIC HELPERS
# ============================================================

def clean(value):
    if value is None:
        return ""

    return " ".join(
        str(value)
        .replace("&amp;", "&")
        .replace("&quot;", '"')
        .replace("&#39;", "'")
        .replace("&apos;", "'")
        .split()
    )


def run(cmd, allow_failure=False):
    print("")
    print("RUNNING:")
    print(" ".join(str(x) for x in cmd))
    print("")

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    print(result.stdout)

    if result.returncode != 0 and not allow_failure:
        raise RuntimeError(
            "Command failed with exit code "
            + str(result.returncode)
        )

    return result


def load_json(path):
    if not path.exists():
        return {}

    try:
        with open(
            path,
            "r",
            encoding="utf-8",
        ) as f:
            return json.load(f)
    except Exception as exc:
        print("WARNING: Could not read", path)
        print(exc)
        return {}


def get_font(size, bold=False):
    if bold:
        candidates = [
            ROOT / "fonts" / "Inter-Bold.ttf",
            ROOT / "fonts" / "Montserrat-Bold.ttf",
            Path(
                "/usr/share/fonts/truetype/dejavu/"
                "DejaVuSans-Bold.ttf"
            ),
        ]
    else:
        candidates = [
            ROOT / "fonts" / "Inter-Regular.ttf",
            ROOT / "fonts" / "Montserrat-Regular.ttf",
            Path(
                "/usr/share/fonts/truetype/dejavu/"
                "DejaVuSans.ttf"
            ),
        ]

    for candidate in candidates:
        if candidate.exists():
            try:
                return ImageFont.truetype(
                    str(candidate),
                    size,
                )
            except Exception:
                pass

    return ImageFont.load_default()


def text_width(draw, text, fnt):
    box = draw.textbbox(
        (0, 0),
        text,
        font=fnt,
    )
    return box[2] - box[0]


def wrap_text(draw, text, fnt, width):
    text = clean(text)

    if not text:
        return []

    words = text.split()
    lines = []
    current = ""

    for word in words:
        candidate = word

        if current:
            candidate = current + " " + word

        if text_width(
            draw,
            candidate,
            fnt,
        ) <= width:
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
    x,
    y,
    fnt,
    fill,
    width,
    spacing=12,
):
    lines = wrap_text(
        draw,
        text,
        fnt,
        width,
    )

    bbox = fnt.getbbox("Ag")

    line_height = (
        bbox[3]
        - bbox[1]
        + spacing
    )

    for line in lines:
        draw.text(
            (x, y),
            line,
            font=fnt,
            fill=fill,
        )

        y += line_height

    return y


# ============================================================
# DIRECTORIES
# ============================================================

def prepare():
    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    SCENE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    AUDIO_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    (ASSET_DIR / "music").mkdir(
        parents=True,
        exist_ok=True,
    )

    for folder in [
        SCENE_DIR,
        AUDIO_DIR,
    ]:
        for item in folder.glob("*"):
            if item.is_file():
                try:
                    item.unlink()
                except Exception:
                    pass

    if OUTPUT_FILE.exists():
        OUTPUT_FILE.unlink()

    print("Output directories prepared.")


# ============================================================
# STORY LOADING
# ============================================================

def get_stories(data):
    stories = data.get(
        "stories",
        [],
    )

    if isinstance(stories, list):
        valid = []

        for story in stories:
            if not isinstance(story, dict):
                continue

            title = clean(
                story.get(
                    "title",
                    "",
                )
            )

            if title:
                valid.append(story)

        if valid:
            return valid[:10]

    title = clean(
        data.get(
            "title",
            "",
        )
    )

    if title:
        return [
            {
                "title": title,
                "county": clean(
                    data.get(
                        "county",
                        "Rift Valley",
                    )
                ),
                "category": clean(
                    data.get(
                        "category",
                        "NEWS",
                    )
                ),
                "description": clean(
                    data.get(
                        "description",
                        "",
                    )
                ),
                "source": clean(
                    data.get(
                        "source",
                        "",
                    )
                ),
            }
        ]

    return []


# ============================================================
# VISUAL FOUNDATION
# ============================================================

def make_background():
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        BG,
    )

    draw = ImageDraw.Draw(image)

    for y in range(HEIGHT):
        ratio = y / HEIGHT

        r = int(
            8 + 12 * ratio
        )

        g = int(
            13 + 13 * ratio
        )

        b = int(
            23 + 20 * ratio
        )

        draw.line(
            (0, y, WIDTH, y),
            fill=(r, g, b),
        )

    return image


def draw_header(draw, label):
    draw.rectangle(
        (0, 0, WIDTH, 16),
        fill=RED,
    )

    logo = get_font(
        46,
        True,
    )

    small = get_font(
        23,
        True,
    )

    draw.text(
        (55, 48),
        "RIFT VALLEY",
        font=logo,
        fill=WHITE,
    )

    draw.text(
        (55, 105),
        "WATCH",
        font=logo,
        fill=RED,
    )

    draw.text(
        (55, 172),
        clean(label).upper(),
        font=small,
        fill=MUTED,
    )

    draw.ellipse(
        (875, 65, 902, 92),
        fill=RED,
    )

    draw.text(
        (918, 58),
        "LIVE",
        font=small,
        fill=WHITE,
    )


def draw_footer(draw, source=""):
    y = HEIGHT - 145

    draw.rectangle(
        (45, y, WIDTH - 45, HEIGHT - 45),
        fill=(12, 19, 31),
    )

    fnt = get_font(
        21,
        False,
    )

    draw.text(
        (70, y + 17),
        "RIFT VALLEY WATCH",
        font=fnt,
        fill=WHITE,
    )

    if source:
        draw.text(
            (70, y + 53),
            "Source: " + clean(source)[:72],
            font=fnt,
            fill=MUTED,
        )


# ============================================================
# SCENE IMAGES
# ============================================================

def opener():
    image = make_background()
    draw = ImageDraw.Draw(image)

    draw_header(
        draw,
        "LIVE REGIONAL BULLETIN",
    )

    draw.rounded_rectangle(
        (50, 470, WIDTH - 50, 1170),
        radius=32,
        fill=PANEL,
    )

    draw.text(
        (90, 545),
        "LATEST",
        font=get_font(
            30,
            True,
        ),
        fill=RED,
    )

    draw_wrapped(
        draw,
        "RIFT VALLEY WATCH",
        90,
        625,
        get_font(
            76,
            True,
        ),
        WHITE,
        850,
        15,
    )

    draw_wrapped(
        draw,
        "Fresh developments from across "
        "Kenya's Rift Valley.",
        90,
        850,
        get_font(
            34,
            False,
        ),
        MUTED,
        820,
        16,
    )

    draw.rectangle(
        (0, 1300, WIDTH, 1385),
        fill=RED,
    )

    draw.text(
        (55, 1322),
        "POLITICS  •  BUSINESS  •  DEVELOPMENT",
        font=get_font(
            27,
            True,
        ),
        fill=WHITE,
    )

    draw_footer(
        draw,
        "Live regional news feeds",
    )

    return image


def coverage(counties, date):
    image = make_background()
    draw = ImageDraw.Draw(image)

    draw_header(
        draw,
        "REGIONAL COVERAGE",
    )

    draw.text(
        (60, 310),
        "TODAY'S RIFT VALLEY",
        font=get_font(
            52,
            True,
        ),
        fill=WHITE,
    )

    draw.text(
        (60, 385),
        clean(date),
        font=get_font(
            29,
            False,
        ),
        fill=MUTED,
    )

    for i, county in enumerate(
        counties[:12]
    ):
        row = i // 2
        col = i % 2

        x = 55 + col * 490
        y = 490 + row * 165

        draw.rounded_rectangle(
            (
                x,
                y,
                x + 455,
                y + 125,
            ),
            radius=18,
            fill=PANEL,
        )

        draw.ellipse(
            (
                x + 25,
                y + 43,
                x + 58,
                y + 76,
            ),
            fill=RED,
        )

        draw.text(
            (x + 78, y + 27),
            clean(county).upper(),
            font=get_font(
                26,
                True,
            ),
            fill=WHITE,
        )

        draw.text(
            (x + 78, y + 70),
            "FRESH UPDATE",
            font=get_font(
                20,
                False,
            ),
            fill=MUTED,
        )

    draw_footer(
        draw,
        "Regional coverage",
    )

    return image


def story_card(story, index, total):
    image = make_background()
    draw = ImageDraw.Draw(image)

    county = clean(
        story.get(
            "county",
            "Rift Valley",
        )
    )

    category = clean(
        story.get(
            "category",
            "NEWS",
        )
    )

    title = clean(
        story.get(
            "title",
            "Regional Update",
        )
    )

    description = clean(
        story.get(
            "description",
            "",
        )
    )

    source = clean(
        story.get(
            "source",
            "",
        )
    )

    draw_header(
        draw,
        category,
    )

    draw.text(
        (870, 180),
        f"{index:02d}/{total:02d}",
        font=get_font(
            23,
            True,
        ),
        fill=MUTED,
    )

    # DATA/VISUAL PANEL
    draw.rounded_rectangle(
        (45, 300, WIDTH - 45, 700),
        radius=28,
        fill=(22, 34, 53),
    )

    # grid
    for x in range(80, 1030, 120):
        draw.line(
            (x, 325, x, 675),
            fill=(40, 57, 80),
            width=1,
        )

    for y in range(350, 680, 75):
        draw.line(
            (65, y, 1015, y),
            fill=(40, 57, 80),
            width=1,
        )

    draw.text(
        (85, 365),
        "REGIONAL UPDATE",
        font=get_font(
            24,
            True,
        ),
        fill=RED,
    )

    draw.text(
        (85, 425),
        county.upper(),
        font=get_font(
            46,
            True,
        ),
        fill=WHITE,
    )

    draw.text(
        (85, 500),
        category.upper(),
        font=get_font(
            27,
            True,
        ),
        fill=MUTED,
    )

    draw.text(
        (870, 410),
        "LIVE",
        font=get_font(
            29,
            True,
        ),
        fill=RED,
    )

    # HEADLINE PANEL
    draw.rounded_rectangle(
        (45, 755, WIDTH - 45, HEIGHT - 205),
        radius=30,
        fill=PANEL,
    )

    draw.text(
        (85, 815),
        "HEADLINE",
        font=get_font(
            24,
            True,
        ),
        fill=RED,
    )

    title_y = draw_wrapped(
        draw,
        title,
        85,
        875,
        get_font(
            51,
            True,
        ),
        WHITE,
        850,
        14,
    )

    body_y = max(
        title_y + 45,
        1190,
    )

    if description:
        draw_wrapped(
            draw,
            description[:480],
            85,
            body_y,
            get_font(
                29,
                False,
            ),
            MUTED,
            850,
            14,
        )

    draw_footer(
        draw,
        source,
    )

    return image


def empty_card():
    image = make_background()
    draw = ImageDraw.Draw(image)

    draw_header(
        draw,
        "LIVE REGIONAL UPDATE",
    )

    draw.text(
        (70, 620),
        "NO FRESH UPDATE",
        font=get_font(
            58,
            True,
        ),
        fill=WHITE,
    )

    draw_wrapped(
        draw,
        "No qualifying regional stories "
        "were retrieved during this automated run.",
        70,
        750,
        get_font(
            32,
            False,
        ),
        MUTED,
        850,
        15,
    )

    draw_footer(
        draw,
        "Live news feeds",
    )

    return image


def outro():
    image = make_background()
    draw = ImageDraw.Draw(image)

    draw_header(
        draw,
        "END OF BULLETIN",
    )

    draw.text(
        (70, 650),
        "RIFT VALLEY",
        font=get_font(
            64,
            True,
        ),
        fill=WHITE,
    )

    draw.text(
        (70, 735),
        "WATCH",
        font=get_font(
            64,
            True,
        ),
        fill=RED,
    )

    draw_wrapped(
        draw,
        "Fresh regional developments. "
        "Follow Rift Valley Watch.",
        70,
        900,
        get_font(
            34,
            False,
        ),
        MUTED,
        830,
        15,
    )

    draw.rectangle(
        (70, 1090, 850, 1098),
        fill=RED,
    )

    draw_footer(
        draw,
        "Rift Valley Watch",
    )

    return image


# ============================================================
# AUDIO
# ============================================================

def create_voice(text, path):
    text = clean(text)

    if not text:
        return False

    try:
        print("Creating narration...")

        tts = gTTS(
            text=text,
            lang="en",
            slow=False,
        )

        tts.save(
            str(path)
        )

        if path.exists() and path.stat().st_size > 1000:
            print(
                "Narration created:",
                path,
            )
            return True

    except Exception as exc:
        print(
            "WARNING: Narration unavailable:"
        )
        print(exc)

    return False


def get_duration(path):
    result = run(
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
        allow_failure=True,
    )

    try:
        return float(
            result.stdout.strip()
        )
    except Exception:
        return 5.0


# ============================================================
# RENDER ONE SCENE
# ============================================================

def render_scene(image, narration, number):
    png = (
        SCENE_DIR
        / f"scene_{number:02d}.png"
    )

    silent = (
        SCENE_DIR
        / f"scene_{number:02d}_silent.mp4"
    )

    final = (
        SCENE_DIR
        / f"scene_{number:02d}.mp4"
    )

    audio = (
        AUDIO_DIR
        / f"scene_{number:02d}.mp3"
    )

    print("")
    print("=" * 50)
    print(
        f"RENDERING SCENE {number}"
    )
    print("=" * 50)

    image.save(
        str(png),
        format="PNG",
    )

    # --------------------------------------------------------
    # Try narration.
    # Failure MUST NOT stop video creation.
    # --------------------------------------------------------

    has_audio = create_voice(
        narration,
        audio,
    )

    length = 5.0

    if has_audio:
        length = get_duration(
            audio
        ) + 0.7

        length = max(
            4.0,
            min(
                length,
                12.0,
            ),
        )

    print(
        "Scene duration:",
        length,
    )

    # --------------------------------------------------------
    # Create video-only scene
    # --------------------------------------------------------

    run(
        [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(png),
            "-t",
            f"{length:.2f}",
            "-r",
            str(FPS),
            "-vf",
            (
                f"scale={WIDTH}:{HEIGHT}:"
                "force_original_aspect_ratio=decrease,"
                f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2"
            ),
            "-c:v",
            "libx264",
            "-preset",
            "ultrafast",
            "-crf",
            "23",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(silent),
        ]
    )

    if not silent.exists():
        raise RuntimeError(
            f"Scene {number} video was not created."
        )

    # --------------------------------------------------------
    # Add narration
    # --------------------------------------------------------

    if has_audio:

        run(
            [
                "ffmpeg",
                "-y",
                "-i",
                str(silent),
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
                "-shortest",
                "-movflags",
                "+faststart",
                str(final),
            ],
            allow_failure=True,
        )

    # --------------------------------------------------------
    # If audio rendering failed, use silent scene.
    # --------------------------------------------------------

    if not final.exists():
        shutil.copy2(
            silent,
            final,
        )

        print(
            "Narration unavailable; "
            "using video-only scene."
        )

    if not final.exists():
        raise RuntimeError(
            f"Scene {number} final MP4 was not created."
        )

    print(
        "SCENE CREATED:",
        final,
    )

    print(
        "SIZE:",
        final.stat().st_size,
        "bytes",
    )

    return final


# ============================================================
# CONCATENATION
# ============================================================

def concatenate(scene_files):
    print("")
    print("=" * 50)
    print("ASSEMBLING FINAL MP4")
    print("=" * 50)

    if not scene_files:
        raise RuntimeError(
            "No scene MP4 files exist."
        )

    concat_file = (
        OUTPUT_DIR
        / "concat.txt"
    )

    with open(
        concat_file,
        "w",
        encoding="utf-8",
    ) as f:

        for scene in scene_files:
            f.write(
                "file '"
                + str(
                    scene.resolve()
                )
                .replace(
                    "'",
                    "'\\''",
                )
                + "'\n"
            )

    print(
        "Scenes to concatenate:",
        len(scene_files),
    )

    for scene in scene_files:
        print(
            scene,
            scene.stat().st_size,
            "bytes",
        )

    # --------------------------------------------------------
    # First attempt: stream copy
    # --------------------------------------------------------

    temp = (
        OUTPUT_DIR
        / "final_temp.mp4"
    )

    result = run(
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
            "-movflags",
            "+faststart",
            str(temp),
        ],
        allow_failure=True,
    )

    # --------------------------------------------------------
    # Second attempt: re-encode if stream copy fails.
    # --------------------------------------------------------

    if not temp.exists() or temp.stat().st_size < 10000:

        print(
            "Stream-copy concatenation failed."
        )

        if temp.exists():
            temp.unlink()

        run(
            [
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
                    f"scale={WIDTH}:{HEIGHT}"
                ),
                "-r",
                str(FPS),
                "-c:v",
                "libx264",
                "-preset",
                "veryfast",
                "-crf",
                "22",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "128k",
                "-movflags",
                "+faststart",
                str(temp),
            ]
        )

    if not temp.exists():
        raise RuntimeError(
            "FFmpeg failed to create final_temp.mp4."
        )

    if temp.stat().st_size < 10000:
        raise RuntimeError(
            "final_temp.mp4 is invalid or too small."
        )

    if OUTPUT_FILE.exists():
        OUTPUT_FILE.unlink()

    temp.replace(
        OUTPUT_FILE
    )

    print(
        "FINAL MP4 CREATED:",
        OUTPUT_FILE,
    )

    print(
        "FINAL SIZE:",
        OUTPUT_FILE.stat().st_size,
        "bytes",
    )


# ============================================================
# VALIDATION
# ============================================================

def validate():
    print("")
    print("=" * 50)
    print("VALIDATING FINAL MP4")
    print("=" * 50)

    if not OUTPUT_FILE.exists():
        raise RuntimeError(
            "Final MP4 does not exist."
        )

    if OUTPUT_FILE.stat().st_size < 10000:
        raise RuntimeError(
            "Final MP4 is too small."
        )

    result = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size",
            "-show_entries",
            "stream=codec_type,codec_name,width,height",
            "-of",
            "json",
            str(OUTPUT_FILE),
        ],
        allow_failure=False,
    )

    info = json.loads(
        result.stdout
    )

    streams = info.get(
        "streams",
        [],
    )

    video = None
    audio = None

    for stream in streams:
        if stream.get(
            "codec_type"
        ) == "video":
            video = stream

        if stream.get(
            "codec_type"
        ) == "audio":
            audio = stream

    if video is None:
        raise RuntimeError(
            "Final MP4 contains no video stream."
        )

    print(
        "Video:",
        video.get("width"),
        "x",
        video.get("height"),
    )

    print(
        "Video codec:",
        video.get("codec_name"),
    )

    if audio:
        print(
            "Audio codec:",
            audio.get("codec_name"),
        )
    else:
        print(
            "WARNING: Final video has no audio."
        )

    if video.get("width") != WIDTH:
        raise RuntimeError(
            "Final video width is not 1080."
        )

    if video.get("height") != HEIGHT:
        raise RuntimeError(
            "Final video height is not 1920."
        )

    print("")
    print(
        "FINAL MP4 VALIDATION PASSED"
    )
    print(
        "FILE:",
        OUTPUT_FILE,
    )
    print(
        "SIZE:",
        f"{OUTPUT_FILE.stat().st_size / 1024 / 1024:.2f} MB",
    )


# ============================================================
# REPORT
# ============================================================

def save_report(stories, scenes):
    counties = []

    for story in stories:
        county = clean(
            story.get(
                "county",
                "",
            )
        )

        if county and county not in counties:
            counties.append(county)

    report = {
        "generator": "Rift Valley Watch V3",
        "output": "output/rift_valley_watch.mp4",
        "resolution": "1080x1920",
        "fps": FPS,
        "stories": len(stories),
        "scenes": len(scenes),
        "counties": counties,
        "music_file_available": MUSIC_FILE.exists(),
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
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print("")
    print("=" * 60)
    print("RIFT VALLEY WATCH")
    print("REAL-TIME REGIONAL VIDEO GENERATOR")
    print("=" * 60)

    if shutil.which("ffmpeg") is None:
        raise RuntimeError(
            "FFmpeg is not installed."
        )

    if shutil.which("ffprobe") is None:
        raise RuntimeError(
            "FFprobe is not installed."
        )

    prepare()

    story_data = load_json(
        STORY_FILE
    )

    # script.json is not required for rendering,
    # but load it if available.
    script_data = load_json(
        SCRIPT_FILE
    )

    stories = get_stories(
        story_data
    )

    print("")
    print(
        "STORIES LOADED:",
        len(stories),
    )

    for i, story in enumerate(
        stories,
        1,
    ):
        print(
            f"{i}. "
            f"[{clean(story.get('county', 'Rift Valley'))}] "
            f"{clean(story.get('title', ''))}"
        )

    scenes = []

    # --------------------------------------------------------
    # SCENE 1
    # --------------------------------------------------------

    scene_number = 1

    scenes.append(
        render_scene(
            opener(),
            (
                "Rift Valley Watch. "
                "Here are the latest major developments "
                "from across Kenya's Rift Valley."
            ),
            scene_number,
        )
    )

    scene_number += 1

    # --------------------------------------------------------
    # COVERAGE SCENE
    # --------------------------------------------------------

    counties = []

    for story in stories:
        county = clean(
            story.get(
                "county",
                "",
            )
        )

        if county and county not in counties:
            counties.append(county)

    if counties:

        date = clean(
            story_data.get(
                "date",
                "",
            )
        )

        scenes.append(
            render_scene(
                coverage(
                    counties,
                    date,
                ),
                (
                    "Today's bulletin brings "
                    "fresh developments from across "
                    "the Rift Valley."
                ),
                scene_number,
            )
        )

        scene_number += 1

    # --------------------------------------------------------
    # STORY SCENES
    # --------------------------------------------------------

    if stories:

        total = len(stories)

        for index, story in enumerate(
            stories,
            1,
        ):

            county = clean(
                story.get(
                    "county",
                    "Rift Valley",
                )
            )

            title = clean(
                story.get(
                    "title",
                    "Regional update",
                )
            )

            description = clean(
                story.get(
                    "description",
                    "",
                )
            )

            narration = (
                county
                + ". "
                + title
                + ". "
                + description[:320]
            )

            scenes.append(
                render_scene(
                    story_card(
                        story,
                        index,
                        total,
                    ),
                    narration,
                    scene_number,
                )
            )

            scene_number += 1

    else:

        scenes.append(
            render_scene(
                empty_card(),
                (
                    "Rift Valley Watch. "
                    "No qualifying fresh regional "
                    "story was retrieved during this run."
                ),
                scene_number,
            )
        )

        scene_number += 1

    # --------------------------------------------------------
    # OUTRO
    # --------------------------------------------------------

    scenes.append(
        render_scene(
            outro(),
            (
                "That is the latest regional "
                "roundup from Rift Valley Watch."
            ),
            scene_number,
        )
    )

    # --------------------------------------------------------
    # VERIFY SCENES
    # --------------------------------------------------------

    print("")
    print("=" * 60)
    print("SCENE VERIFICATION")
    print("=" * 60)

    valid_scenes = []

    for scene in scenes:

        if scene.exists() and scene.stat().st_size > 10000:

            print(
                "VALID:",
                scene.name,
                f"{scene.stat().st_size / 1024:.1f} KB",
            )

            valid_scenes.append(scene)

        else:

            print(
                "INVALID:",
                scene,
            )

    if not valid_scenes:
        raise RuntimeError(
            "ZERO VALID SCENE MP4 FILES WERE CREATED."
        )

    # --------------------------------------------------------
    # FINAL ASSEMBLY
    # --------------------------------------------------------

    concatenate(
        valid_scenes
    )

    validate()

    save_report(
        stories,
        valid_scenes,
    )

    print("")
    print("=" * 60)
    print("VIDEO GENERATION SUCCESSFUL")
    print("=" * 60)

    print(
        "OUTPUT:",
        OUTPUT_FILE,
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except Exception as exc:

        print("")
        print("=" * 60)
        print("VIDEO GENERATOR FAILED")
        print("=" * 60)

        print(
            "ERROR:",
            str(exc),
        )

        print("")
        print("OUTPUT DIRECTORY:")

        if OUTPUT_DIR.exists():

            for item in OUTPUT_DIR.rglob("*"):

                if item.is_file():

                    print(
                        item,
                        item.stat().st_size,
                        "bytes",
                    )

        print("")
        print(
            "END OF VIDEO GENERATOR ERROR"
        )

        sys.exit(1)
