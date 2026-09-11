import os
import sys
import json
import math
import shutil
import subprocess
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageFilter
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH — VIDEO GENERATOR V2
# Real photos + broadcast graphics + narration
# 1080x1920 vertical
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

STORY_FILE = ROOT / "data" / "story.json"
SCRIPT_FILE = ROOT / "data" / "script.json"

SOURCE_DIR = ROOT / "assets" / "source"
OUTPUT_DIR = ROOT / "output"
SCENES_DIR = OUTPUT_DIR / "scenes"
AUDIO_DIR = OUTPUT_DIR / "audio"

FINAL_VIDEO = OUTPUT_DIR / "rift_valley_watch.mp4"
VISUAL_REPORT = ROOT / "data" / "visual_report.json"

WIDTH = 1080
HEIGHT = 1920
FPS = 30

SCENE_SECONDS = 7
OPENER_SECONDS = 4
OUTRO_SECONDS = 4

FONT_DIRS = [
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/usr/share/fonts/truetype/liberation2"),
    Path("/usr/share/fonts/truetype/noto"),
    ROOT / "fonts",
]


# ============================================================
# BASIC UTILITIES
# ============================================================

def log(message=""):
    print(message, flush=True)


def run_command(command, check=True):
    log("")
    log("RUNNING:")
    log(" ".join(str(x) for x in command))

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    if result.stdout:
        print(result.stdout, flush=True)

    if check and result.returncode != 0:
        raise RuntimeError(
            f"Command failed with exit code {result.returncode}"
        )

    return result


def ensure_directories():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SCENES_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)


def load_json(path):
    if not path.exists():
        raise FileNotFoundError(f"Missing file: {path}")

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def get_font(size, bold=False):
    candidates = []

    if bold:
        names = [
            "DejaVuSans-Bold.ttf",
            "LiberationSans-Bold.ttf",
            "NotoSans-Bold.ttf",
        ]
    else:
        names = [
            "DejaVuSans.ttf",
            "LiberationSans-Regular.ttf",
            "NotoSans-Regular.ttf",
        ]

    for directory in FONT_DIRS:
        for name in names:
            candidates.append(directory / name)

    for path in candidates:
        if path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except Exception:
                pass

    return ImageFont.load_default()


def text_width(draw, text, font):
    box = draw.textbbox((0, 0), text, font=font)
    return box[2] - box[0]


def wrap_text(draw, text, font, max_width):
    words = str(text or "").split()

    if not words:
        return []

    lines = []
    current = words[0]

    for word in words[1:]:
        candidate = current + " " + word

        if text_width(draw, candidate, font) <= max_width:
            current = candidate
        else:
            lines.append(current)
            current = word

    lines.append(current)

    return lines


def draw_wrapped_text(
    draw,
    xy,
    text,
    font,
    fill,
    max_width,
    line_spacing=10,
    max_lines=None,
):
    x, y = xy

    lines = wrap_text(draw, text, font, max_width)

    if max_lines:
        if len(lines) > max_lines:
            lines = lines[:max_lines]

            if not lines[-1].endswith("..."):
                lines[-1] = lines[-1].rstrip(".") + "..."

    bbox = font.getbbox("Ag")
    line_height = bbox[3] - bbox[1]

    for line in lines:
        draw.text(
            (x, y),
            line,
            font=font,
            fill=fill,
        )
        y += line_height + line_spacing

    return y


# ============================================================
# PHOTO HANDLING
# ============================================================

def find_photo(story):
    image_path = story.get("image_path")

    if image_path:
        candidate = ROOT / image_path

        if candidate.exists() and candidate.is_file():
            return candidate

    candidates = [
        story.get("image"),
        story.get("photo"),
        story.get("photo_path"),
        story.get("image_file"),
    ]

    for value in candidates:
        if not value:
            continue

        candidate = ROOT / str(value)

        if candidate.exists() and candidate.is_file():
            return candidate

    return None


def load_photo(path):
    if not path:
        return None

    try:
        image = Image.open(path)
        image = image.convert("RGB")
        return image
    except Exception as exc:
        log(f"PHOTO WARNING: Could not open {path}: {exc}")
        return None


def crop_photo(image, width, height, zoom=1.0):
    if image is None:
        return None

    image = image.copy()

    target_ratio = width / height
    image_ratio = image.width / image.height

    if image_ratio > target_ratio:
        new_height = image.height
        new_width = int(new_height * target_ratio)
    else:
        new_width = image.width
        new_height = int(new_width / target_ratio)

    left = max(0, (image.width - new_width) // 2)
    top = max(0, (image.height - new_height) // 2)

    image = image.crop(
        (
            left,
            top,
            left + new_width,
            top + new_height,
        )
    )

    if zoom != 1.0:
        crop_w = max(1, int(image.width / zoom))
        crop_h = max(1, int(image.height / zoom))

        left = max(0, (image.width - crop_w) // 2)
        top = max(0, (image.height - crop_h) // 2)

        image = image.crop(
            (
                left,
                top,
                left + crop_w,
                top + crop_h,
            )
        )

    image = image.resize(
        (width, height),
        Image.Resampling.LANCZOS,
    )

    return image


def make_photo_background(image):
    """
    Creates a full-screen blurred version of the real photo.
    Used behind the main crop to avoid fake graphics.
    """

    if image is None:
        return Image.new("RGB", (WIDTH, HEIGHT), (15, 18, 24))

    bg = crop_photo(image, WIDTH, HEIGHT)

    if bg is None:
        return Image.new("RGB", (WIDTH, HEIGHT), (15, 18, 24))

    bg = bg.filter(ImageFilter.GaussianBlur(20))

    return bg


def paste_photo_panel(canvas, image, box):
    if image is None:
        return

    x1, y1, x2, y2 = box

    width = x2 - x1
    height = y2 - y1

    photo = crop_photo(image, width, height)

    if photo is not None:
        canvas.paste(photo, (x1, y1))


# ============================================================
# GRAPHICS
# ============================================================

def add_top_bar(draw, section="RIFT VALLEY WATCH"):
    draw.rectangle(
        (0, 0, WIDTH, 92),
        fill=(9, 12, 18),
    )

    draw.rectangle(
        (0, 0, 15, 92),
        fill=(220, 35, 45),
    )

    logo_font = get_font(34, bold=True)

    draw.text(
        (40, 25),
        section.upper(),
        font=logo_font,
        fill=(255, 255, 255),
    )

    live_font = get_font(25, bold=True)

    live_text = "LIVE • REGIONAL NEWS"

    draw.text(
        (WIDTH - text_width(draw, live_text, live_font) - 40, 30),
        live_text,
        font=live_font,
        fill=(235, 235, 235),
    )


def add_bottom_brand(draw):
    y = HEIGHT - 70

    draw.rectangle(
        (0, y, WIDTH, HEIGHT),
        fill=(8, 10, 15),
    )

    font = get_font(24, bold=True)

    draw.text(
        (40, y + 22),
        "RIFT VALLEY WATCH",
        font=font,
        fill=(235, 235, 235),
    )


def add_photo_overlay(canvas, y_start, y_end):
    overlay = Image.new(
        "RGBA",
        (WIDTH, y_end - y_start),
        (0, 0, 0, 0),
    )

    draw = ImageDraw.Draw(overlay)

    for i in range(overlay.height):
        alpha = int(
            190 * (i / max(1, overlay.height))
        )

        draw.line(
            (0, i, WIDTH, i),
            fill=(0, 0, 0, alpha),
        )

    canvas.alpha_composite(
        overlay,
        (0, y_start),
    )


def county_label(draw, county):
    if not county:
        return

    font = get_font(28, bold=True)

    text = str(county).upper()

    padding_x = 24
    padding_y = 12

    box = draw.textbbox(
        (0, 0),
        text,
        font=font,
    )

    tw = box[2] - box[0]
    th = box[3] - box[1]

    x = 40
    y = 115

    draw.rounded_rectangle(
        (
            x,
            y,
            x + tw + padding_x * 2,
            y + th + padding_y * 2,
        ),
        radius=10,
        fill=(220, 35, 45),
    )

    draw.text(
        (
            x + padding_x,
            y + padding_y - 2,
        ),
        text,
        font=font,
        fill=(255, 255, 255),
    )


# ============================================================
# SCENE CREATION
# ============================================================

def create_opener():
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        (10, 13, 19),
    )

    draw = ImageDraw.Draw(image)

    # Broadcast-style background
    for y in range(HEIGHT):
        shade = int(12 + (y / HEIGHT) * 20)

        draw.line(
            (0, y, WIDTH, y),
            fill=(shade, shade + 2, shade + 5),
        )

    draw.rectangle(
        (0, 0, 18, HEIGHT),
        fill=(220, 35, 45),
    )

    small_font = get_font(32, bold=True)
    main_font = get_font(92, bold=True)
    sub_font = get_font(38, bold=True)

    draw.text(
        (70, 550),
        "RIFT VALLEY",
        font=small_font,
        fill=(235, 235, 235),
    )

    draw.text(
        (65, 610),
        "WATCH",
        font=main_font,
        fill=(255, 255, 255),
    )

    draw.rectangle(
        (70, 740, 400, 752),
        fill=(220, 35, 45),
    )

    draw.text(
        (70, 795),
        "REGIONAL NEWS BULLETIN",
        font=sub_font,
        fill=(225, 225, 225),
    )

    draw.text(
        (70, 870),
        "POLITICS • BUSINESS • DEVELOPMENT",
        font=get_font(27, bold=True),
        fill=(165, 170, 180),
    )

    add_bottom_brand(draw)

    path = SCENES_DIR / "scene_00_opener.png"
    image.save(path, "PNG")

    return path


def create_story_scene(story, index):
    image = Image.new(
        "RGBA",
        (WIDTH, HEIGHT),
        (8, 11, 16, 255),
    )

    photo_path = find_photo(story)
    photo = load_photo(photo_path)

    if photo is not None:
        background = make_photo_background(photo)
        image = background.convert("RGBA")

        # Darken the background slightly
        dark = Image.new(
            "RGBA",
            (WIDTH, HEIGHT),
            (0, 0, 0, 85),
        )
        image.alpha_composite(dark)

        # Main real-photo panel
        photo_top = 105
        photo_bottom = 1030

        panel = crop_photo(
            photo,
            WIDTH - 80,
            photo_bottom - photo_top,
            zoom=1.02,
        )

        if panel is not None:
            image.paste(
                panel.convert("RGBA"),
                (40, photo_top),
            )

        # Photo edge
        draw = ImageDraw.Draw(image)

        draw.rectangle(
            (
                40,
                photo_top,
                WIDTH - 40,
                photo_bottom,
            ),
            outline=(255, 255, 255, 45),
            width=2,
        )

    else:
        draw = ImageDraw.Draw(image)

        draw.rectangle(
            (0, 0, WIDTH, HEIGHT),
            fill=(15, 18, 25, 255),
        )

        # Fallback visual
        draw.rectangle(
            (0, 100, WIDTH, 1100),
            fill=(25, 30, 40, 255),
        )

    draw = ImageDraw.Draw(image)

    # Top broadcast bar
    add_top_bar(draw)

    county = story.get("county", "Rift Valley")
    category = story.get("category", "NEWS")

    county_label(draw, county)

    # Lower information panel
    panel_top = 980

    panel = Image.new(
        "RGBA",
        (WIDTH, HEIGHT - panel_top),
        (7, 10, 15, 238),
    )

    image.alpha_composite(
        panel,
        (0, panel_top),
    )

    draw = ImageDraw.Draw(image)

    # Red breaking line
    draw.rectangle(
        (
            40,
            panel_top + 30,
            300,
            panel_top + 38,
        ),
        fill=(220, 35, 45),
    )

    category_font = get_font(25, bold=True)

    draw.text(
        (40, panel_top + 60),
        str(category).upper(),
        font=category_font,
        fill=(220, 35, 45),
    )

    title = (
        story.get("title")
        or story.get("headline")
        or "Rift Valley News Update"
    )

    title_font = get_font(51, bold=True)

    draw_wrapped_text(
        draw,
        (40, panel_top + 105),
        title,
        title_font,
        (255, 255, 255),
        WIDTH - 80,
        line_spacing=8,
        max_lines=4,
    )

    # Source
    source = story.get("source") or "News source"

    source_font = get_font(23, bold=False)

    source_text = f"Source: {source}"

    draw.text(
        (40, HEIGHT - 150),
        source_text,
        font=source_font,
        fill=(175, 180, 188),
    )

    # Story number
    number_font = get_font(30, bold=True)

    number_text = f"{index:02d}"

    draw.text(
        (
            WIDTH - text_width(draw, number_text, number_font) - 45,
            HEIGHT - 150,
        ),
        number_text,
        font=number_font,
        fill=(175, 180, 188),
    )

    # Photo indicator
    if photo is not None:
        photo_font = get_font(20, bold=True)

        draw.text(
            (40, HEIGHT - 105),
            "PHOTO • SOURCE ARTICLE",
            font=photo_font,
            fill=(140, 145, 155),
        )

    add_bottom_brand(draw)

    # Restore bottom text after brand strip
    draw = ImageDraw.Draw(image)

    draw.text(
        (40, HEIGHT - 48),
        "RIFT VALLEY WATCH",
        font=get_font(21, bold=True),
        fill=(205, 208, 215),
    )

    path = SCENES_DIR / f"scene_{index:02d}.png"

    image.convert("RGB").save(
        path,
        "PNG",
        optimize=True,
    )

    return path, photo_path


def create_outro():
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        (10, 13, 19),
    )

    draw = ImageDraw.Draw(image)

    draw.rectangle(
        (0, 0, 18, HEIGHT),
        fill=(220, 35, 45),
    )

    title_font = get_font(70, bold=True)
    sub_font = get_font(32, bold=True)

    title = "RIFT VALLEY WATCH"

    draw.text(
        (
            (WIDTH - text_width(draw, title, title_font)) // 2,
            720,
        ),
        title,
        font=title_font,
        fill=(255, 255, 255),
    )

    subtitle = "MORE REGIONAL NEWS • MORE UPDATES"

    draw.text(
        (
            (WIDTH - text_width(draw, subtitle, sub_font)) // 2,
            830,
        ),
        subtitle,
        font=sub_font,
        fill=(190, 195, 202),
    )

    draw.rectangle(
        (340, 910, 740, 918),
        fill=(220, 35, 45),
    )

    add_bottom_brand(draw)

    path = SCENES_DIR / "scene_99_outro.png"

    image.save(
        path,
        "PNG",
        optimize=True,
    )

    return path


# ============================================================
# NARRATION
# ============================================================

def make_narration_text(story):
    narration = story.get("narration")

    if narration:
        return str(narration).strip()

    county = story.get("county", "the Rift Valley")
    category = story.get("category", "news")
    title = story.get("title") or story.get("headline", "")

    description = story.get("description", "")

    parts = [
        f"Rift Valley Watch. {county}. {category}.",
        title,
    ]

    if description:
        parts.append(description)

    return " ".join(
        str(x).strip()
        for x in parts
        if x
    )


def create_audio(text, index):
    if not text.strip():
        return None

    path = AUDIO_DIR / f"story_{index:02d}.mp3"

    try:
        log(f"Generating narration for story {index}")

        tts = gTTS(
            text=text,
            lang="en",
            slow=False,
        )

        tts.save(str(path))

        if path.exists() and path.stat().st_size > 1000:
            return path

    except Exception as exc:
        log(f"TTS WARNING: {exc}")

    return None


# ============================================================
# FFMPEG SCENE RENDERING
# ============================================================

def render_png_to_mp4(png_path, output_path, duration, audio_path=None):
    command = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(png_path),
    ]

    if audio_path and audio_path.exists():
        command += [
            "-i",
            str(audio_path),
        ]

    command += [
        "-t",
        str(duration),
        "-r",
        str(FPS),
        "-vf",
        "scale=1080:1920:force_original_aspect_ratio=decrease,"
        "pad=1080:1920:(ow-iw)/2:(oh-ih)/2",
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
    ]

    if audio_path and audio_path.exists():
        command += [
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-ar",
            "44100",
            "-ac",
            "2",
            "-shortest",
        ]
    else:
        command += [
            "-an",
        ]

    command += [
        "-movflags",
        "+faststart",
        str(output_path),
    ]

    result = run_command(
        command,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"FFmpeg failed creating {output_path}"
        )

    if not output_path.exists():
        raise RuntimeError(
            f"Scene was not created: {output_path}"
        )

    if output_path.stat().st_size < 5000:
        raise RuntimeError(
            f"Scene is suspiciously small: {output_path}"
        )

    return output_path


# ============================================================
# CONCATENATION
# ============================================================

def create_concat_file(scene_files):
    concat_path = OUTPUT_DIR / "concat.txt"

    with open(
        concat_path,
        "w",
        encoding="utf-8",
    ) as f:

        for path in scene_files:
            safe_path = str(path.resolve()).replace(
                "'",
                "'\\''",
            )

            f.write(
                f"file '{safe_path}'\n"
            )

    return concat_path


def concatenate_scenes(scene_files):
    concat_file = create_concat_file(scene_files)

    # First attempt: stream copy
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
        str(FINAL_VIDEO),
    ]

    result = run_command(
        command,
        check=False,
    )

    if (
        result.returncode == 0
        and FINAL_VIDEO.exists()
        and FINAL_VIDEO.stat().st_size > 100000
    ):
        return FINAL_VIDEO

    log("Concat copy failed. Trying re-encode.")

    if FINAL_VIDEO.exists():
        FINAL_VIDEO.unlink()

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
        "veryfast",
        "-crf",
        "23",
        "-pix_fmt",
        "yuv420p",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ar",
        "44100",
        "-ac",
        "2",
        "-movflags",
        "+faststart",
        str(FINAL_VIDEO),
    ]

    result = run_command(
        command,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "FFmpeg failed to assemble the final MP4."
        )

    if not FINAL_VIDEO.exists():
        raise RuntimeError(
            "Final MP4 was not created."
        )

    return FINAL_VIDEO


# ============================================================
# VALIDATION
# ============================================================

def validate_video():
    if not FINAL_VIDEO.exists():
        raise RuntimeError(
            "Final video does not exist."
        )

    if FINAL_VIDEO.stat().st_size < 100000:
        raise RuntimeError(
            "Final video is suspiciously small."
        )

    command = [
        "ffprobe",
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=codec_name,width,height,pix_fmt",
        "-show_entries",
        "format=duration,size",
        "-of",
        "json",
        str(FINAL_VIDEO),
    ]

    result = run_command(
        command,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "ffprobe could not read the final MP4."
        )

    try:
        info = json.loads(result.stdout)

        streams = info.get("streams", [])

        if not streams:
            raise RuntimeError(
                "No video stream found."
            )

        stream = streams[0]

        width = int(stream.get("width", 0))
        height = int(stream.get("height", 0))

        log("")
        log("FINAL VIDEO:")
        log(f"Width: {width}")
        log(f"Height: {height}")
        log(f"Codec: {stream.get('codec_name')}")
        log(f"Pixel format: {stream.get('pix_fmt')}")

        if width != WIDTH or height != HEIGHT:
            raise RuntimeError(
                f"Wrong dimensions: {width}x{height}"
            )

    except json.JSONDecodeError:
        raise RuntimeError(
            "Could not parse ffprobe output."
        )


# ============================================================
# VISUAL REPORT
# ============================================================

def write_visual_report(stories, rendered_scenes):
    report = {
        "project": "Rift Valley Watch",
        "version": "V2",
        "resolution": f"{WIDTH}x{HEIGHT}",
        "fps": FPS,
        "real_photos_enabled": True,
        "stories": [],
    }

    for item in rendered_scenes:
        report["stories"].append(item)

    with open(
        VISUAL_REPORT,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            report,
            f,
            indent=2,
            ensure_ascii=False,
        )


# ============================================================
# MAIN
# ============================================================

def main():
    log("=" * 70)
    log("RIFT VALLEY WATCH V2 VIDEO GENERATOR")
    log("=" * 70)

    ensure_directories()

    # --------------------------------------------------------
    # Load news
    # --------------------------------------------------------

    try:
        data = load_json(STORY_FILE)
    except Exception as exc:
        log(f"ERROR loading story.json: {exc}")
        return 1

    if isinstance(data, dict):
        stories = (
            data.get("stories")
            or data.get("articles")
            or data.get("items")
            or []
        )
    elif isinstance(data, list):
        stories = data
    else:
        stories = []

    if not stories:
        log("ERROR: No stories found in story.json.")
        return 1

    log("")
    log(f"Stories loaded: {len(stories)}")

    # --------------------------------------------------------
    # Clean old scenes
    # --------------------------------------------------------

    for path in SCENES_DIR.glob("*"):
        try:
            if path.is_file():
                path.unlink()
        except Exception:
            pass

    for path in AUDIO_DIR.glob("*"):
        try:
            if path.is_file():
                path.unlink()
        except Exception:
            pass

    if FINAL_VIDEO.exists():
        try:
            FINAL_VIDEO.unlink()
        except Exception:
            pass

    # --------------------------------------------------------
    # Opener
    # --------------------------------------------------------

    rendered_scenes = []

    opener_png = create_opener()
    opener_mp4 = SCENES_DIR / "scene_00_opener.mp4"

    try:
        render_png_to_mp4(
            opener_png,
            opener_mp4,
            OPENER_SECONDS,
        )

        rendered_scenes.append(
            {
                "scene": "opener",
                "photo": False,
                "file": str(opener_mp4.relative_to(ROOT)),
            }
        )

    except Exception as exc:
        log(f"OPENER WARNING: {exc}")

    # --------------------------------------------------------
    # Stories
    # --------------------------------------------------------

    usable_stories = stories[:10]

    for index, story in enumerate(
        usable_stories,
        start=1,
    ):
        log("")
        log("=" * 60)
        log(f"STORY {index}")
        log("=" * 60)

        try:
            title = (
                story.get("title")
                or story.get("headline")
                or "Untitled story"
            )

            county = story.get(
                "county",
                "Rift Valley",
            )

            log(f"County: {county}")
            log(f"Title: {title}")

            png_path, photo_path = create_story_scene(
                story,
                index,
            )

            audio_text = make_narration_text(
                story
            )

            audio_path = create_audio(
                audio_text,
                index,
            )

            mp4_path = (
                SCENES_DIR /
                f"scene_{index:02d}.mp4"
            )

            render_png_to_mp4(
                png_path,
                mp4_path,
                SCENE_SECONDS,
                audio_path,
            )

            rendered_scenes.append(
                {
                    "scene": index,
                    "county": county,
                    "category": story.get(
                        "category",
                        "NEWS",
                    ),
                    "title": title,
                    "photo": bool(photo_path),
                    "photo_path": (
                        str(
                            photo_path.relative_to(ROOT)
                        )
                        if photo_path
                        else None
                    ),
                    "audio": bool(audio_path),
                    "file": str(
                        mp4_path.relative_to(ROOT)
                    ),
                }
            )

            log(
                f"Story {index} completed successfully."
            )

        except Exception as exc:
            log("")
            log(
                f"STORY {index} WARNING: {exc}"
            )

            # Continue with remaining stories.
            continue

    # --------------------------------------------------------
    # Outro
    # --------------------------------------------------------

    try:
        outro_png = create_outro()

        outro_mp4 = (
            SCENES_DIR /
            "scene_99_outro.mp4"
        )

        render_png_to_mp4(
            outro_png,
            outro_mp4,
            OUTRO_SECONDS,
        )

        rendered_scenes.append(
            {
                "scene": "outro",
                "photo": False,
                "file": str(
                    outro_mp4.relative_to(ROOT)
                ),
            }
        )

    except Exception as exc:
        log(f"OUTRO WARNING: {exc}")

    # --------------------------------------------------------
    # Find MP4 scenes
    # --------------------------------------------------------

    scene_files = []

    for path in sorted(
        SCENES_DIR.glob("scene_*.mp4")
    ):
        if path.stat().st_size > 5000:
            scene_files.append(path)

    log("")
    log("=" * 70)
    log("SCENES READY")
    log("=" * 70)

    for path in scene_files:
        log(
            f"{path.name}: "
            f"{path.stat().st_size:,} bytes"
        )

    if not scene_files:
        log("ERROR: No usable MP4 scenes were created.")
        return 1

    # --------------------------------------------------------
    # Assemble final MP4
    # --------------------------------------------------------

    try:
        log("")
        log("=" * 70)
        log("ASSEMBLING FINAL MP4")
        log("=" * 70)

        concatenate_scenes(scene_files)

    except Exception as exc:
        log("")
        log(f"FINAL ASSEMBLY ERROR: {exc}")
        return 1

    # --------------------------------------------------------
    # Validate
    # --------------------------------------------------------

    try:
        validate_video()
    except Exception as exc:
        log("")
        log(f"VIDEO VALIDATION ERROR: {exc}")
        return 1

    # --------------------------------------------------------
    # Visual report
    # --------------------------------------------------------

    try:
        write_visual_report(
            usable_stories,
            rendered_scenes,
        )
    except Exception as exc:
        log(
            f"REPORT WARNING: {exc}"
        )

    # --------------------------------------------------------
    # Final success
    # --------------------------------------------------------

    log("")
    log("=" * 70)
    log("VIDEO GENERATION SUCCESSFUL")
    log("=" * 70)

    log(
        f"Created: {FINAL_VIDEO}"
    )

    log(
        f"Size: {FINAL_VIDEO.stat().st_size:,} bytes"
    )

    photo_count = sum(
        1
        for item in rendered_scenes
        if item.get("photo") is True
    )

    log(
        f"Real photos used: {photo_count}"
    )

    log(
        f"Scenes: {len(scene_files)}"
    )

    log("=" * 70)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("Interrupted.")
        sys.exit(1)
    except Exception as exc:
        log("")
        log("=" * 70)
        log("FATAL VIDEO GENERATOR ERROR")
        log("=" * 70)
        log(str(exc))
        log("=" * 70)
        sys.exit(1)
