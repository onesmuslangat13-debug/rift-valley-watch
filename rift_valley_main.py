# ============================================================
# RIFT VALLEY WATCH
# MAIN PIPELINE
#
# VERSION: RIFT_VALLEY_WATCH_MAIN_REBUILT_V3
#
# PIPELINE:
#   1. Run news engine
#   2. Load selected story
#   3. Validate story
#   4. Run video generator
#   5. Verify final MP4
#
# OUTPUT:
#   output/rift_valley_watch_reel.mp4
#
# RULES:
#   - ONE REAL STORY
#   - ONE COUNTY PER REEL
#   - REAL ARTICLE IMAGE REQUIRED
#   - 1080x1920
#   - NO SOURCE/PUBLISHER DISPLAY
#   - NO SOURCE/PUBLISHER IN NARRATION
#   - NO GOOGLE NEWS BOILERPLATE
# ============================================================

import json
import os
import subprocess
import sys
from pathlib import Path


# ============================================================
# PATH CONFIGURATION
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
ASSETS_DIR = BASE_DIR / "assets"
SOURCE_DIR = ASSETS_DIR / "source"
OUTPUT_DIR = BASE_DIR / "output"
AUDIO_DIR = BASE_DIR / "audio"

NEWS_ENGINE = BASE_DIR / "scripts" / "news_engine.py"

VIDEO_GENERATOR_OPTIONS = [
    BASE_DIR / "rift_valley_video_generator.py",
    BASE_DIR / "video_generator.py",
]

SELECTED_STORY = DATA_DIR / "selected_story.json"
STORY_FILE = DATA_DIR / "story.json"

FINAL_MP4 = OUTPUT_DIR / "rift_valley_watch_reel.mp4"

LOCAL_IMAGE = SOURCE_DIR / "story_image.jpg"


# ============================================================
# TARGET COUNTIES
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


# ============================================================
# LOGGING
# ============================================================

def log(message):
    print(
        f"[RIFT VALLEY WATCH] {message}",
        flush=True,
    )


# ============================================================
# DIRECTORY PREPARATION
# ============================================================

def prepare_directories():

    directories = [
        DATA_DIR,
        ASSETS_DIR,
        SOURCE_DIR,
        OUTPUT_DIR,
        AUDIO_DIR,
    ]

    for directory in directories:
        directory.mkdir(
            parents=True,
            exist_ok=True,
        )


# ============================================================
# JSON READER
# ============================================================

def load_json(path):

    path = Path(path)

    if not path.exists():
        return {}

    try:

        with path.open(
            "r",
            encoding="utf-8",
        ) as handle:

            value = json.load(handle)

        if isinstance(value, dict):
            return value

        return {}

    except Exception as exc:

        log(
            f"JSON read warning: {path} -> {exc}"
        )

        return {}


# ============================================================
# STORY LOADING
# ============================================================

def load_story():

    selected = load_json(
        SELECTED_STORY
    )

    if selected:

        log(
            "Story file: data/selected_story.json"
        )

        return selected

    fallback = load_json(
        STORY_FILE
    )

    if fallback:

        log(
            "Story file: data/story.json"
        )

        return fallback

    return {}


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(value):

    if value is None:
        return ""

    text = str(value)

    text = text.replace(
        "\n",
        " ",
    )

    text = text.replace(
        "\r",
        " ",
    )

    return " ".join(
        text.split()
    ).strip()


def get_title(story):

    for key in [
        "title",
        "headline",
        "name",
    ]:

        value = clean_text(
            story.get(key)
        )

        if value:
            return value

    return ""


def get_summary(story):

    for key in [
        "summary",
        "description",
        "content",
        "body",
        "text",
    ]:

        value = clean_text(
            story.get(key)
        )

        if value:
            return value

    return ""


def get_county(story):

    county = clean_text(
        story.get("county")
    )

    if county:
        return county

    combined = (
        get_title(story)
        + " "
        + get_summary(story)
    ).lower()

    for name in COUNTIES:

        if name.lower() in combined:
            return name

    return ""


# ============================================================
# IMAGE DISCOVERY
# ============================================================

def get_image_urls(story):

    urls = []

    direct_keys = [
        "image",
        "image_url",
        "imageUrl",
        "thumbnail",
        "thumbnail_url",
        "photo",
        "photo_url",
        "article_image",
        "article_image_url",
        "featured_image",
        "featured_image_url",
        "og_image",
        "og_image_url",
        "image_src",
        "imageSource",
    ]

    for key in direct_keys:

        value = story.get(key)

        if isinstance(
            value,
            str,
        ):

            value = value.strip()

            if value:
                urls.append(value)

        elif isinstance(
            value,
            dict,
        ):

            for nested_key in [
                "url",
                "src",
                "image",
                "href",
            ]:

                nested = value.get(
                    nested_key
                )

                if isinstance(
                    nested,
                    str,
                ):

                    nested = nested.strip()

                    if nested:
                        urls.append(
                            nested
                        )

    list_keys = [
        "images",
        "image_urls",
        "article_images",
        "photos",
        "gallery",
        "media",
    ]

    for key in list_keys:

        value = story.get(key)

        if not isinstance(
            value,
            list,
        ):
            continue

        for item in value:

            if isinstance(
                item,
                str,
            ):

                item = item.strip()

                if item:
                    urls.append(item)

            elif isinstance(
                item,
                dict,
            ):

                for nested_key in [
                    "url",
                    "src",
                    "image",
                    "href",
                ]:

                    nested = item.get(
                        nested_key
                    )

                    if isinstance(
                        nested,
                        str,
                    ):

                        nested = nested.strip()

                        if nested:
                            urls.append(
                                nested
                            )

    # Remove duplicates.
    result = []
    seen = set()

    for url in urls:

        if url in seen:
            continue

        seen.add(url)
        result.append(url)

    return result


# ============================================================
# STORY VALIDATION
# ============================================================

def validate_story(story):

    if not story:

        raise RuntimeError(
            "No story data was found."
        )

    title = get_title(
        story
    )

    if not title:

        raise RuntimeError(
            "Selected story has no headline."
        )

    summary = get_summary(
        story
    )

    county = get_county(
        story
    )

    image_urls = get_image_urls(
        story
    )

    local_image_valid = (
        LOCAL_IMAGE.exists()
        and LOCAL_IMAGE.stat().st_size > 10_000
    )

    # --------------------------------------------------------
    # Reject obvious Google News boilerplate.
    # --------------------------------------------------------

    combined = (
        title
        + " "
        + summary
    ).lower()

    forbidden_phrases = [
        "google news",
        "get the latest news",
        "sign in to google",
        "google news app",
        "personalized news",
    ]

    for phrase in forbidden_phrases:

        if phrase in combined:

            raise RuntimeError(
                "Invalid Google News boilerplate "
                "detected in story."
            )

    # --------------------------------------------------------
    # Require real image information.
    # --------------------------------------------------------

    if not image_urls and not local_image_valid:

        raise RuntimeError(
            "No usable article image was found."
        )

    # --------------------------------------------------------
    # Print selected story.
    # --------------------------------------------------------

    log(
        f"HEADLINE: {title}"
    )

    log(
        "COUNTY: "
        + (
            county
            if county
            else "Unknown"
        )
    )

    log(
        f"IMAGE URLS: {len(image_urls)}"
    )

    if local_image_valid:

        log(
            "LOCAL ARTICLE IMAGE: AVAILABLE"
        )

    return True


# ============================================================
# COMMAND EXECUTION
# ============================================================

def run_command(
    command,
    label,
):

    command = [
        str(item)
        for item in command
    ]

    log(
        f"STARTING {label}"
    )

    log(
        "COMMAND: "
        + " ".join(command)
    )

    result = subprocess.run(
        command,
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        env=os.environ.copy(),
    )

    if result.stdout:

        print(
            result.stdout,
            flush=True,
        )

    if result.returncode != 0:

        raise RuntimeError(
            f"{label} failed with exit code "
            f"{result.returncode}"
        )

    log(
        f"{label} COMPLETED"
    )

    return result


# ============================================================
# RUN NEWS ENGINE
# ============================================================

def run_news_engine():

    if not NEWS_ENGINE.exists():

        log(
            "scripts/news_engine.py not found."
        )

        log(
            "Using existing story data."
        )

        return

    try:

        run_command(
            [
                sys.executable,
                "-u",
                str(NEWS_ENGINE),
            ],
            "NEWS ENGINE",
        )

    except Exception as exc:

        log(
            f"NEWS ENGINE WARNING: {exc}"
        )

        # Existing valid story can still be used.
        if SELECTED_STORY.exists():

            log(
                "Existing selected_story.json "
                "will be used."
            )

            return

        if STORY_FILE.exists():

            log(
                "Existing story.json "
                "will be used."
            )

            return

        raise


# ============================================================
# FIND VIDEO GENERATOR
# ============================================================

def find_video_generator():

    for candidate in VIDEO_GENERATOR_OPTIONS:

        if candidate.exists():

            return candidate

    raise RuntimeError(
        "No video generator was found. "
        "Expected rift_valley_video_generator.py "
        "or video_generator.py."
    )


# ============================================================
# REMOVE PREVIOUS MP4
# ============================================================

def remove_previous_mp4():

    if not FINAL_MP4.exists():
        return

    try:

        FINAL_MP4.unlink()

        log(
            "Removed previous final MP4."
        )

    except Exception as exc:

        raise RuntimeError(
            "Could not remove previous final MP4: "
            f"{exc}"
        )


# ============================================================
# RUN VIDEO GENERATOR
# ============================================================

def run_video_generator():

    generator = find_video_generator()

    log(
        f"VIDEO GENERATOR: {generator.name}"
    )

    remove_previous_mp4()

    run_command(
        [
            sys.executable,
            "-u",
            str(generator),
        ],
        "VIDEO GENERATOR",
    )


# ============================================================
# FFMPEG / FFPROBE
# ============================================================

def probe_final_video():

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type,codec_name,width,height,duration",
        "-show_entries",
        "format=duration,size",
        "-of",
        "json",
        str(FINAL_MP4),
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:

        raise RuntimeError(
            "FFprobe failed with exit code "
            f"{result.returncode}"
        )

    try:

        return json.loads(
            result.stdout
        )

    except Exception as exc:

        raise RuntimeError(
            "Could not parse FFprobe output: "
            f"{exc}"
        )


# ============================================================
# FINAL MP4 VERIFICATION
# ============================================================

def verify_final_mp4():

    log(
        "VERIFYING FINAL MP4"
    )

    if not FINAL_MP4.exists():

        raise RuntimeError(
            "Rift Valley Watch MP4 was NOT generated."
        )

    file_size = FINAL_MP4.stat().st_size

    if file_size < 100_000:

        raise RuntimeError(
            "Final MP4 is suspiciously small."
        )

    probe = probe_final_video()

    streams = probe.get(
        "streams",
        [],
    )

    video_stream = None
    audio_stream = None

    for stream in streams:

        stream_type = stream.get(
            "codec_type"
        )

        if stream_type == "video":

            video_stream = stream

        elif stream_type == "audio":

            audio_stream = stream

    if video_stream is None:

        raise RuntimeError(
            "Final MP4 contains no video stream."
        )

    if audio_stream is None:

        raise RuntimeError(
            "Final MP4 contains no audio stream."
        )

    # --------------------------------------------------------
    # Resolution
    # --------------------------------------------------------

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

    if width != 1080 or height != 1920:

        raise RuntimeError(
            "Wrong video resolution: "
            f"{width}x{height}. "
            "Expected 1080x1920."
        )

    # --------------------------------------------------------
    # Durations
    # --------------------------------------------------------

    try:

        video_duration = float(
            video_stream.get(
                "duration"
            )
            or 0
        )

    except Exception:

        video_duration = 0.0

    try:

        audio_duration = float(
            audio_stream.get(
                "duration"
            )
            or 0
        )

    except Exception:

        audio_duration = 0.0

    format_data = probe.get(
        "format",
        {},
    )

    try:

        format_duration = float(
            format_data.get(
                "duration"
            )
            or 0
        )

    except Exception:

        format_duration = 0.0

    total_duration = max(
        video_duration,
        audio_duration,
        format_duration,
    )

    if total_duration <= 0:

        raise RuntimeError(
            "Final MP4 has no valid duration."
        )

    # --------------------------------------------------------
    # Audio/video synchronization
    # --------------------------------------------------------

    if (
        video_duration > 0
        and audio_duration > 0
    ):

        difference = abs(
            video_duration
            - audio_duration
        )

        if difference > 1.5:

            raise RuntimeError(
                "Video/audio duration mismatch: "
                f"{video_duration:.2f}s vs "
                f"{audio_duration:.2f}s."
            )

    # --------------------------------------------------------
    # Final report
    # --------------------------------------------------------

    size_mb = (
        file_size
        / (1024 * 1024)
    )

    log(
        "FINAL MP4 EXISTS"
    )

    log(
        f"FILE: {FINAL_MP4}"
    )

    log(
        f"SIZE: {size_mb:.2f} MB"
    )

    log(
        f"RESOLUTION: {width}x{height}"
    )

    log(
        f"VIDEO DURATION: "
        f"{video_duration:.2f}s"
    )

    log(
        f"AUDIO DURATION: "
        f"{audio_duration:.2f}s"
    )

    log(
        f"TOTAL DURATION: "
        f"{total_duration:.2f}s"
    )

    log(
        "VIDEO STREAM: PASS"
    )

    log(
        "AUDIO STREAM: PASS"
    )

    log(
        "RESOLUTION: PASS"
    )

    log(
        "FINAL QC: PASS"
    )

    return True


# ============================================================
# MAIN
# ============================================================

def main():

    print("")

    print(
        "=" * 70
    )

    print(
        "RIFT VALLEY WATCH"
    )

    print(
        "MAIN PIPELINE"
    )

    print(
        "=" * 70
    )

    # --------------------------------------------------------
    # Prepare directories.
    # --------------------------------------------------------

    prepare_directories()

    # --------------------------------------------------------
    # Run news engine.
    # --------------------------------------------------------

    run_news_engine()

    # --------------------------------------------------------
    # Load story.
    # --------------------------------------------------------

    story = load_story()

    if not story:

        raise RuntimeError(
            "No story was available after "
            "the news-engine step."
        )

    # --------------------------------------------------------
    # Validate story.
    # --------------------------------------------------------

    validate_story(
        story
    )

    title = get_title(
        story
    )

    county = get_county(
        story
    )

    print("")

    print(
        "=" * 70
    )

    print(
        "SELECTED STORY"
    )

    print(
        "=" * 70
    )

    print(
        f"HEADLINE: {title}"
    )

    print(
        "COUNTY: "
        + (
            county
            if county
            else "Unknown"
        )
    )

    print(
        "=" * 70
    )

    print("")

    # --------------------------------------------------------
    # Generate video.
    # --------------------------------------------------------

    run_video_generator()

    # --------------------------------------------------------
    # Verify MP4.
    # --------------------------------------------------------

    verify_final_mp4()

    # --------------------------------------------------------
    # SUCCESS.
    # --------------------------------------------------------

    print("")

    print(
        "=" * 70
    )

    print(
        "RIFT VALLEY WATCH SUCCESS"
    )

    print(
        "=" * 70
    )

    print(
        f"FINAL MP4: {FINAL_MP4}"
    )

    print(
        "1080x1920: PASS"
    )

    print(
        "VIDEO STREAM: PASS"
    )

    print(
        "AUDIO STREAM: PASS"
    )

    print(
        "FINAL QC: PASS"
    )

    print(
        "=" * 70
    )

    return 0


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        raise SystemExit(
            main()
        )

    except KeyboardInterrupt:

        print("")

        print(
            "RIFT VALLEY WATCH CANCELLED."
        )

        raise SystemExit(130)

    except Exception as exc:

        print("")

        print(
            "=" * 70
        )

        print(
            "RIFT VALLEY WATCH FAILED"
        )

        print(
            "=" * 70
        )

        print(
            f"{type(exc).__name__}: {exc}"
        )

        print(
            "=" * 70
        )

        raise SystemExit(1)
