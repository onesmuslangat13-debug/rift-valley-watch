import os
import sys
import json
import shutil
import subprocess
import urllib.request
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH
# SELF-CONTAINED VIDEO BUILDER
# ============================================================

ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"
ASSET_DIR = ROOT / "assets"
SOURCE_DIR = ASSET_DIR / "source"
AUDIO_DIR = ASSET_DIR / "audio"
OUTPUT_DIR = ROOT / "output"
SCENE_DIR = OUTPUT_DIR / "scenes"

STORY_FILE = DATA_DIR / "story.json"
SCRIPT_FILE = DATA_DIR / "script.json"

SOURCE_IMAGE = SOURCE_DIR / "story_image.jpg"

FINAL_OUTPUT = OUTPUT_DIR / "rift_valley_watch_reel.mp4"

WIDTH = 1080
HEIGHT = 1920
FPS = 30

# ============================================================
# REAL IMAGE FALLBACKS
# ============================================================

REAL_IMAGE_URLS = [
    "https://peopledaily.digital/wp-content/uploads/2026/03/image-300-500x333.png",
    "https://topnews.ke/wp-content/uploads/2026/03/WhatsApp-Image-2026-03-18-at-12.13.35-rr-1024x683.jpeg",
    "https://topnews.ke/wp-content/uploads/2026/03/WhatsApp-Image-2026-03-18-at-12.13.36-66-1024x683.jpeg",
]

# ============================================================
# VERIFIED TEST STORY
# ============================================================

VERIFIED_STORY = {
    "title": "65-KM Road Project Worth KSh 2.1 Billion Underway in Bomet",
    "county": "Bomet County",
    "category": "DEVELOPMENT",
    "date": "2026-03-18",
    "source": {
        "name": "Bomet County Government",
        "url": (
            "https://bomet.go.ke/"
            "dp-kindiki-visits-bomet-to-inspect-development-projects"
        ),
        "type": "OFFICIAL_SOURCE",
    },
    "verified_facts": [
        {
            "label": "PROJECT",
            "value": (
                "Kyogong-Kapkesosio-Sigor-Chebunyo / "
                "Sigor-Lelaitich-Kipreres-Longisa road"
            ),
        },
        {
            "label": "ROAD LENGTH",
            "value": "65 kilometres",
        },
        {
            "label": "COST",
            "value": "KSh 2.1 billion",
        },
        {
            "label": "LOCATION",
            "value": "Chepalungu Constituency, Bomet County",
        },
        {
            "label": "STATUS",
            "value": "Ongoing construction works",
        },
        {
            "label": "IMPACT",
            "value": (
                "Expected to unlock economic potential "
                "in the area and wider Bomet County"
            ),
        },
    ],
    "official_statement": {
        "available": True,
        "speaker": "Deputy President Kithure Kindiki",
        "quote": (
            "The Roads and Transport Ministry has been instructed "
            "to closely monitor road construction to ensure speedy "
            "completion and quality works."
        ),
    },
    "summary": (
        "Construction is ongoing on a 65-kilometre road project "
        "linking Kyogong, Kapkesosio, Sigor and Chebunyo, with "
        "another section running through Sigor, Lelaitich, "
        "Kipreres and Longisa in Bomet County. The Bomet County "
        "Government says the project is being constructed at a "
        "cost of KSh 2.1 billion in Chepalungu Constituency and "
        "is expected to unlock the economic potential of the "
        "area and wider county."
    ),
}


# ============================================================
# LOGGING
# ============================================================

def log(message=""):
    print(message, flush=True)


# ============================================================
# DIRECTORIES
# ============================================================

def prepare_directories():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SCENE_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# STORY
# ============================================================

def write_story():
    with open(
        STORY_FILE,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            VERIFIED_STORY,
            f,
            indent=2,
            ensure_ascii=False,
        )

    log(f"Story written: {STORY_FILE}")


# ============================================================
# NARRATION
# ============================================================

def build_narration():

    return [
        (
            "A major road project is underway in Bomet County. "
            "The development covers sixty-five kilometres of road "
            "in Chepalungu Constituency."
        ),
        (
            "The project links Kyogong, Kapkesosio, Sigor and "
            "Chebunyo, with another section connecting Sigor, "
            "Lelaitich, Kipreres and Longisa."
        ),
        (
            "The reported project cost is two point one billion "
            "Kenya shillings."
        ),
        (
            "Construction works are currently ongoing, according "
            "to the Bomet County Government."
        ),
        (
            "The county government says the project is expected "
            "to unlock economic potential in the area and across "
            "the wider county."
        ),
        (
            "Deputy President Kithure Kindiki said the Roads and "
            "Transport Ministry had been instructed to closely "
            "monitor construction to ensure speedy completion "
            "and quality works."
        ),
        (
            "The official source for this report is the Bomet "
            "County Government."
        ),
        (
            "Rift Valley Watch. Verified county news and "
            "developments."
        ),
    ]


def write_script(narration):
    script = {
        "segments": [
            {
                "scene": index + 1,
                "text": text,
            }
            for index, text in enumerate(narration)
        ]
    }

    with open(
        SCRIPT_FILE,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            script,
            f,
            indent=2,
            ensure_ascii=False,
        )


# ============================================================
# IMAGE
# ============================================================

def valid_image(path):
    try:
        path = Path(path)

        if not path.exists():
            return False

        if path.stat().st_size < 5000:
            return False

        with Image.open(path) as image:
            image.verify()

        return True

    except Exception:
        return False


def download_image():
    prepare_directories()

    if valid_image(SOURCE_IMAGE):
        log(
            f"Using existing real image: "
            f"{SOURCE_IMAGE}"
        )
        return SOURCE_IMAGE

    log("")
    log("============================================================")
    log("DOWNLOADING REAL ARTICLE IMAGE")
    log("============================================================")

    for index, url in enumerate(REAL_IMAGE_URLS, 1):

        temp = SOURCE_DIR / f"image_{index}.tmp"

        try:
            log(f"Trying image source {index}...")

            request = urllib.request.Request(
                url,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 "
                        "(X11; Linux x86_64) "
                        "AppleWebKit/537.36 "
                        "Chrome/131 Safari/537.36"
                    )
                },
            )

            with urllib.request.urlopen(
                request,
                timeout=30,
            ) as response:

                data = response.read()

            with open(temp, "wb") as f:
                f.write(data)

            if valid_image(temp):

                image = Image.open(temp).convert("RGB")
                image.save(
                    SOURCE_IMAGE,
                    "JPEG",
                    quality=94,
                )

                temp.unlink(missing_ok=True)

                log(
                    f"REAL IMAGE FOUND: {url}"
                )

                log(
                    f"Saved: {SOURCE_IMAGE}"
                )

                return SOURCE_IMAGE

            temp.unlink(missing_ok=True)

        except Exception as exc:

            temp.unlink(missing_ok=True)

            log(
                f"Image source {index} failed: "
                f"{exc}"
            )

    raise RuntimeError(
        "No usable real article image could be downloaded."
    )


# ============================================================
# FONTS
# ============================================================

def get_font(size, bold=True):

    candidates = []

    if bold:
        candidates.extend(
            [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
            ]
        )
    else:
        candidates.extend(
            [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
            ]
        )

    for path in candidates:

        if Path(path).exists():
            return ImageFont.truetype(
                path,
                size,
            )

    return ImageFont.load_default()


# ============================================================
# TEXT WRAPPING
# ============================================================

def wrap_text(
    draw,
    text,
    font,
    max_width,
):

    words = str(text).split()

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

    return lines


# ============================================================
# IMAGE PREPARATION
# ============================================================

def crop_cover(image):

    image = image.convert("RGB")

    ratio = max(
        WIDTH / image.width,
        HEIGHT / image.height,
    )

    new_width = int(
        image.width * ratio
    )

    new_height = int(
        image.height * ratio
    )

    image = image.resize(
        (new_width, new_height),
        Image.Resampling.LANCZOS,
    )

    left = (
        new_width - WIDTH
    ) // 2

    top = (
        new_height - HEIGHT
    ) // 2

    return image.crop(
        (
            left,
            top,
            left + WIDTH,
            top + HEIGHT,
        )
    )


def load_background(image_path):

    image = Image.open(
        image_path
    )

    return crop_cover(image)


# ============================================================
# BASE SCENE
# ============================================================

def create_base_scene(
    image_path,
    scene_number,
    section,
):

    image = load_background(
        image_path
    )

    draw = ImageDraw.Draw(
        image,
        "RGBA",
    )

    # Dark lower gradient approximation.
    draw.rectangle(
        (0, 0, WIDTH, 165),
        fill=(0, 0, 0, 190),
    )

    draw.rectangle(
        (0, 1500, WIDTH, HEIGHT),
        fill=(0, 0, 0, 205),
    )

    # Top branding.
    small_font = get_font(
        34,
        True,
    )

    draw.text(
        (48, 42),
        "RIFT VALLEY WATCH",
        font=small_font,
        fill=(255, 255, 255, 255),
    )

    # Scene indicator.
    scene_font = get_font(
        30,
        True,
    )

    scene_label = (
        f"{scene_number:02d}  |  {section.upper()}"
    )

    bbox = draw.textbbox(
        (0, 0),
        scene_label,
        font=scene_font,
    )

    draw.text(
        (
            WIDTH - 48 - (bbox[2] - bbox[0]),
            45,
        ),
        scene_label,
        font=scene_font,
        fill=(255, 255, 255, 220),
    )

    return image, draw


# ============================================================
# SAVE SCENE IMAGE
# ============================================================

def save_scene_image(
    image,
    index,
):

    path = (
        SCENE_DIR /
        f"scene_{index:02d}.jpg"
    )

    image.save(
        path,
        "JPEG",
        quality=94,
        optimize=True,
    )

    if not valid_image(path):
        raise RuntimeError(
            f"Scene image invalid: {path}"
        )

    return path


# ============================================================
# SCENE 1
# ============================================================

def scene_1(image_path):

    image, draw = create_base_scene(
        image_path,
        1,
        "Breaking Development",
    )

    title_font = get_font(
        72,
        True,
    )

    lines = wrap_text(
        draw,
        VERIFIED_STORY["title"],
        title_font,
        930,
    )

    y = 650

    for line in lines:

        draw.text(
            (60, y),
            line,
            font=title_font,
            fill="white",
            stroke_width=3,
            stroke_fill="black",
        )

        y += 90

    return save_scene_image(
        image,
        1,
    )


# ============================================================
# SCENE 2
# ============================================================

def scene_2(image_path):

    image, draw = create_base_scene(
        image_path,
        2,
        "Where It Is",
    )

    label_font = get_font(
        42,
        True,
    )

    title_font = get_font(
        78,
        True,
    )

    body_font = get_font(
        46,
        True,
    )

    draw.text(
        (60, 560),
        "LOCATION",
        font=label_font,
        fill="white",
    )

    draw.text(
        (60, 630),
        "BOMET COUNTY",
        font=title_font,
        fill="white",
    )

    lines = wrap_text(
        draw,
        "Chepalungu Constituency",
        body_font,
        900,
    )

    y = 780

    for line in lines:

        draw.text(
            (60, y),
            line,
            font=body_font,
            fill="white",
        )

        y += 65

    return save_scene_image(
        image,
        2,
    )


# ============================================================
# SCENE 3
# ============================================================

def scene_3(image_path):

    image, draw = create_base_scene(
        image_path,
        3,
        "Key Facts",
    )

    title_font = get_font(
        64,
        True,
    )

    value_font = get_font(
        78,
        True,
    )

    draw.text(
        (60, 500),
        "65 KILOMETRES",
        font=value_font,
        fill="white",
    )

    draw.text(
        (60, 650),
        "KSh 2.1 BILLION",
        font=value_font,
        fill="white",
    )

    draw.text(
        (60, 820),
        "ONGOING CONSTRUCTION",
        font=title_font,
        fill="white",
    )

    return save_scene_image(
        image,
        3,
    )


# ============================================================
# SCENE 4
# ============================================================

def scene_4(image_path):

    image, draw = create_base_scene(
        image_path,
        4,
        "The Route",
    )

    title_font = get_font(
        56,
        True,
    )

    body_font = get_font(
        45,
        True,
    )

    draw.text(
        (60, 450),
        "ROAD CONNECTIONS",
        font=title_font,
        fill="white",
    )

    route = (
        "Kyogong → Kapkesosio → Sigor → "
        "Chebunyo"
    )

    lines = wrap_text(
        draw,
        route,
        body_font,
        930,
    )

    y = 600

    for line in lines:

        draw.text(
            (60, y),
            line,
            font=body_font,
            fill="white",
        )

        y += 75

    route2 = (
        "Sigor → Lelaitich → Kipreres → Longisa"
    )

    lines = wrap_text(
        draw,
        route2,
        body_font,
        930,
    )

    y += 80

    for line in lines:

        draw.text(
            (60, y),
            line,
            font=body_font,
            fill="white",
        )

        y += 75

    return save_scene_image(
        image,
        4,
    )


# ============================================================
# SCENE 5
# ============================================================

def scene_5(image_path):

    image, draw = create_base_scene(
        image_path,
        5,
        "Why It Matters",
    )

    title_font = get_font(
        68,
        True,
    )

    body_font = get_font(
        50,
        True,
    )

    draw.text(
        (60, 480),
        "EXPECTED IMPACT",
        font=title_font,
        fill="white",
    )

    text = (
        "The Bomet County Government says "
        "the project is expected to unlock "
        "economic potential in the area "
        "and wider county."
    )

    lines = wrap_text(
        draw,
        text,
        body_font,
        920,
    )

    y = 700

    for line in lines:

        draw.text(
            (60, y),
            line,
            font=body_font,
            fill="white",
        )

        y += 72

    return save_scene_image(
        image,
        5,
    )


# ============================================================
# SCENE 6
# ============================================================

def scene_6(image_path):

    image, draw = create_base_scene(
        image_path,
        6,
        "Official Statement",
    )

    title_font = get_font(
        55,
        True,
    )

    body_font = get_font(
        43,
        True,
    )

    draw.text(
        (60, 440),
        "KITHURE KINDIKI",
        font=title_font,
        fill="white",
    )

    quote = (
        "The Roads and Transport Ministry "
        "has been instructed to closely "
        "monitor road construction to ensure "
        "speedy completion and quality works."
    )

    lines = wrap_text(
        draw,
        quote,
        body_font,
        900,
    )

    y = 600

    for line in lines:

        draw.text(
            (60, y),
            line,
            font=body_font,
            fill="white",
        )

        y += 65

    return save_scene_image(
        image,
        6,
    )


# ============================================================
# SCENE 7
# ============================================================

def scene_7(image_path):

    image, draw = create_base_scene(
        image_path,
        7,
        "Verified Source",
    )

    title_font = get_font(
        65,
        True,
    )

    body_font = get_font(
        48,
        True,
    )

    draw.text(
        (60, 520),
        "OFFICIAL SOURCE",
        font=title_font,
        fill="white",
    )

    draw.text(
        (60, 670),
        "Bomet County",
        font=title_font,
        fill="white",
    )

    draw.text(
        (60, 750),
        "Government",
        font=title_font,
        fill="white",
    )

    source_url = (
        "bomet.go.ke"
    )

    draw.text(
        (60, 940),
        source_url,
        font=body_font,
        fill="white",
    )

    return save_scene_image(
        image,
        7,
    )


# ============================================================
# SCENE 8
# ============================================================

def scene_8(image_path):

    image, draw = create_base_scene(
        image_path,
        8,
        "Rift Valley Watch",
    )

    title_font = get_font(
        76,
        True,
    )

    body_font = get_font(
        45,
        True,
    )

    draw.text(
        (60, 620),
        "RIFT VALLEY",
        font=title_font,
        fill="white",
    )

    draw.text(
        (60, 720),
        "WATCH",
        font=title_font,
        fill="white",
    )

    draw.text(
        (60, 900),
        "Verified county news.",
        font=body_font,
        fill="white",
    )

    return save_scene_image(
        image,
        8,
    )


# ============================================================
# AUDIO
# ============================================================

def create_audio(
    text,
    index,
):

    output = (
        AUDIO_DIR /
        f"scene_{index:02d}.mp3"
    )

    if output.exists():
        output.unlink()

    log(
        f"Creating narration: "
        f"{output.name}"
    )

    tts = gTTS(
        text=text,
        lang="en",
        slow=False,
    )

    tts.save(
        str(output)
    )

    if not output.exists():
        raise RuntimeError(
            f"Narration was not created: {output}"
        )

    if output.stat().st_size < 1000:
        raise RuntimeError(
            f"Narration file is too small: {output}"
        )

    return output


# ============================================================
# SCENE VIDEO
# ============================================================

def render_scene(
    image_path,
    audio_path,
    output_path,
):

    font = (
        "/usr/share/fonts/truetype/dejavu/"
        "DejaVuSans-Bold.ttf"
    )

    if not Path(font).exists():
        font = (
            "/usr/share/fonts/truetype/liberation2/"
            "LiberationSans-Bold.ttf"
        )

    if output_path.exists():
        output_path.unlink()

    cmd = [
        "ffmpeg",
        "-y",

        "-loop",
        "1",

        "-i",
        str(image_path),

        "-i",
        str(audio_path),

        "-vf",
        (
            "scale=1080:1920:"
            "force_original_aspect_ratio=increase,"
            "crop=1080:1920,"
            "setsar=1"
        ),

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

        "-shortest",

        "-r",
        str(FPS),

        "-movflags",
        "+faststart",

        str(output_path),
    ]

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:

        log("")
        log("FFMPEG SCENE ERROR")
        log(result.stderr[-10000:])

        raise RuntimeError(
            f"Scene render failed: "
            f"{output_path.name}"
        )

    if not output_path.exists():
        raise RuntimeError(
            f"Scene MP4 missing: "
            f"{output_path}"
        )

    if output_path.stat().st_size < 10000:
        raise RuntimeError(
            f"Scene MP4 is too small: "
            f"{output_path}"
        )

    log(
        f"Scene MP4 created: "
        f"{output_path.name}"
    )


# ============================================================
# CONCATENATE
# ============================================================

def concatenate_scenes(
    scene_files,
):

    if not scene_files:
        raise RuntimeError(
            "No scene MP4 files were created."
        )

    concat_file = (
        OUTPUT_DIR /
        "concat_list.txt"
    )

    with open(
        concat_file,
        "w",
        encoding="utf-8",
    ) as f:

        for scene in scene_files:

            absolute = Path(
                scene
            ).resolve()

            escaped = (
                str(absolute)
                .replace("'", "'\\''")
            )

            f.write(
                f"file '{escaped}'\n"
            )

    temp_output = (
        OUTPUT_DIR /
        "rift_valley_watch_reel_temp.mp4"
    )

    if temp_output.exists():
        temp_output.unlink()

    log("")
    log("============================================================")
    log("CONCATENATING SCENES")
    log("============================================================")

    # First attempt: stream copy.
    cmd_copy = [
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
        str(temp_output),
    ]

    result = subprocess.run(
        cmd_copy,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    # If stream-copy fails, re-encode.
    if (
        result.returncode != 0
        or not temp_output.exists()
        or temp_output.stat().st_size < 10000
    ):

        if temp_output.exists():
            temp_output.unlink()

        log(
            "Stream-copy concat failed. "
            "Using safe re-encode."
        )

        cmd_reencode = [
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
            "21",
            "-pix_fmt",
            "yuv420p",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-movflags",
            "+faststart",
            str(temp_output),
        ]

        result = subprocess.run(
            cmd_reencode,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if result.returncode != 0:

            log("")
            log("FINAL CONCAT FFMPEG ERROR")
            log(result.stderr[-15000:])

            raise RuntimeError(
                "Could not concatenate scene MP4 files."
            )

    if not temp_output.exists():
        raise RuntimeError(
            "Temporary final MP4 was not created."
        )

    if temp_output.stat().st_size < 10000:
        raise RuntimeError(
            "Temporary final MP4 is too small."
        )

    shutil.move(
        str(temp_output),
        str(FINAL_OUTPUT),
    )

    log(
        f"FINAL MP4 CREATED: "
        f"{FINAL_OUTPUT}"
    )


# ============================================================
# MP4 VERIFICATION
# ============================================================

def verify_mp4():

    log("")
    log("============================================================")
    log("VERIFYING FINAL MP4")
    log("============================================================")

    if not FINAL_OUTPUT.exists():

        log("ERROR: Final MP4 does not exist.")

        raise RuntimeError(
            "Rift Valley Watch MP4 was NOT generated."
        )

    if FINAL_OUTPUT.stat().st_size < 50000:

        raise RuntimeError(
            "Final MP4 is suspiciously small."
        )

    cmd = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration,size",
        "-of",
        "default=noprint_wrappers=1",
        str(FINAL_OUTPUT),
    ]

    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:

        log(result.stderr)

        raise RuntimeError(
            "Final MP4 failed ffprobe verification."
        )

    log(
        "FINAL MP4 VERIFIED"
    )

    log(
        result.stdout.strip()
    )

    log(
        f"FILE: {FINAL_OUTPUT}"
    )

    log(
        f"SIZE: {FINAL_OUTPUT.stat().st_size:,} bytes"
    )


# ============================================================
# CLEAN OLD OUTPUT
# ============================================================

def clean_output():

    if SCENE_DIR.exists():

        for file in SCENE_DIR.iterdir():

            if file.is_file():
                file.unlink()

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    if FINAL_OUTPUT.exists():
        FINAL_OUTPUT.unlink()

    temp = (
        OUTPUT_DIR /
        "rift_valley_watch_reel_temp.mp4"
    )

    if temp.exists():
        temp.unlink()

    concat = (
        OUTPUT_DIR /
        "concat_list.txt"
    )

    if concat.exists():
        concat.unlink()


# ============================================================
# MAIN BUILD
# ============================================================

def build_video():

    prepare_directories()
    clean_output()

    image_path = download_image()

    narration = build_narration()

    write_script(
        narration
    )

    scene_images = [
        scene_1(image_path),
        scene_2(image_path),
        scene_3(image_path),
        scene_4(image_path),
        scene_5(image_path),
        scene_6(image_path),
        scene_7(image_path),
        scene_8(image_path),
    ]

    if len(scene_images) != 8:
        raise RuntimeError(
            "Expected 8 scene images."
        )

    scene_files = []

    for index, (
        scene_image,
        narration_text,
    ) in enumerate(
        zip(
            scene_images,
            narration,
        ),
        1,
    ):

        audio_path = create_audio(
            narration_text,
            index,
        )

        scene_output = (
            SCENE_DIR /
            f"scene_{index:02d}.mp4"
        )

        render_scene(
            scene_image,
            audio_path,
            scene_output,
        )

        scene_files.append(
            scene_output
        )

    log("")
    log(
        f"TOTAL SCENE MP4 FILES: "
        f"{len(scene_files)}"
    )

    for scene in scene_files:

        log(
            f"  {scene.name}: "
            f"{scene.stat().st_size:,} bytes"
        )

    concatenate_scenes(
        scene_files
    )

    verify_mp4()


# ============================================================
# MAIN
# ============================================================

def main():

    log("")
    log("============================================================")
    log("RIFT VALLEY WATCH")
    log("SELF-CONTAINED VIDEO BUILD")
    log("============================================================")

    log(
        f"ROOT: {ROOT}"
    )

    log(
        f"OUTPUT: {FINAL_OUTPUT}"
    )

    try:

        prepare_directories()

        write_story()

        build_video()

        log("")
        log("============================================================")
        log("BUILD SUCCESSFUL")
        log("============================================================")

        log(
            f"FINAL FILE: {FINAL_OUTPUT}"
        )

    except Exception as exc:

        log("")
        log("============================================================")
        log("RIFT VALLEY WATCH FAILED")
        log("============================================================")

        log(
            f"{type(exc).__name__}: {exc}"
        )

        log("")
        log("Output directory:")

        if OUTPUT_DIR.exists():

            for item in OUTPUT_DIR.iterdir():

                try:
                    size = item.stat().st_size
                except Exception:
                    size = 0

                log(
                    f"  {item.name} "
                    f"{size:,} bytes"
                )

        log("")
        log("Scene directory:")

        if SCENE_DIR.exists():

            for item in SCENE_DIR.iterdir():

                try:
                    size = item.stat().st_size
                except Exception:
                    size = 0

                log(
                    f"  {item.name} "
                    f"{size:,} bytes"
                )

        sys.exit(1)


if __name__ == "__main__":
    main()
