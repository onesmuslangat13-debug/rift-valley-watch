# ============================================================
# RIFT VALLEY WATCH
# MAIN PIPELINE
#
# VERSION: RIFT_VALLEY_WATCH_MAIN_REBUILT_V4
# ============================================================

import json
import os
import subprocess
import sys
from pathlib import Path


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
ASSETS_DIR = BASE_DIR / "assets"
SOURCE_DIR = ASSETS_DIR / "source"
OUTPUT_DIR = BASE_DIR / "output"
AUDIO_DIR = BASE_DIR / "audio"

NEWS_ENGINE = BASE_DIR / "scripts" / "news_engine.py"

VIDEO_GENERATORS = [
    BASE_DIR / "rift_valley_video_generator.py",
    BASE_DIR / "video_generator.py",
]

SELECTED_STORY = DATA_DIR / "selected_story.json"
STORY_FILE = DATA_DIR / "story.json"

FINAL_MP4 = OUTPUT_DIR / "rift_valley_watch_reel.mp4"

LOCAL_IMAGE = SOURCE_DIR / "story_image.jpg"


# ============================================================
# COUNTIES
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
# DIRECTORIES
# ============================================================

def prepare_directories():

    for directory in [
        DATA_DIR,
        ASSETS_DIR,
        SOURCE_DIR,
        OUTPUT_DIR,
        AUDIO_DIR,
    ]:

        directory.mkdir(
            parents=True,
            exist_ok=True,
        )


# ============================================================
# JSON
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

            data = json.load(handle)

        return data

    except Exception as exc:

        log(
            f"Could not read {path}: {exc}"
        )

        return {}


# ============================================================
# TEXT
# ============================================================

def clean_text(value):

    if value is None:
        return ""

    if isinstance(value, (dict, list)):
        return ""

    return " ".join(
        str(value)
        .replace("\n", " ")
        .replace("\r", " ")
        .split()
    ).strip()


# ============================================================
# RECURSIVE SEARCH
# ============================================================

def recursive_find(
    data,
    keys,
):

    if isinstance(data, dict):

        for key in keys:

            if key in data:

                value = clean_text(
                    data.get(key)
                )

                if value:
                    return value

        for value in data.values():

            found = recursive_find(
                value,
                keys,
            )

            if found:
                return found

    elif isinstance(data, list):

        for item in data:

            found = recursive_find(
                item,
                keys,
            )

            if found:
                return found

    return ""


# ============================================================
# TITLE
# ============================================================

def get_title(story):

    keys = [
        "title",
        "headline",
        "article_title",
        "articleTitle",
        "story_title",
        "storyTitle",
        "news_title",
        "newsTitle",
        "heading",
        "subject",
        "name",
    ]

    return recursive_find(
        story,
        keys,
    )


# ============================================================
# SUMMARY
# ============================================================

def get_summary(story):

    keys = [
        "summary",
        "description",
        "content",
        "body",
        "text",
        "article_text",
        "articleText",
        "story",
        "details",
    ]

    return recursive_find(
        story,
        keys,
    )


# ============================================================
# COUNTY
# ============================================================

def get_county(story):

    keys = [
        "county",
        "county_name",
        "countyName",
        "location",
        "region",
    ]

    county = recursive_find(
        story,
        keys,
    )

    if county:

        for allowed in COUNTIES:

            if allowed.lower() in county.lower():

                return allowed

    combined = json.dumps(
        story,
        ensure_ascii=False,
    ).lower()

    for allowed in COUNTIES:

        if allowed.lower() in combined:

            return allowed

    return ""


# ============================================================
# IMAGE URLS
# ============================================================

def get_image_urls(story):

    keys = [
        "image",
        "image_url",
        "imageUrl",
        "thumbnail",
        "thumbnail_url",
        "thumbnailUrl",
        "photo",
        "photo_url",
        "photoUrl",
        "article_image",
        "article_image_url",
        "articleImage",
        "articleImageUrl",
        "featured_image",
        "featured_image_url",
        "featuredImage",
        "featuredImageUrl",
        "og_image",
        "og_image_url",
        "image_src",
        "imageSource",
    ]

    urls = []

    def scan(data):

        if isinstance(data, dict):

            for key in keys:

                if key not in data:
                    continue

                value = data[key]

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

            for value in data.values():

                scan(value)

        elif isinstance(data, list):

            for item in data:
                scan(item)

        elif isinstance(data, str):

            value = data.strip()

            if (
                value.startswith("http://")
                or value.startswith("https://")
            ):

                lower = value.lower()

                image_extensions = [
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".webp",
                    ".gif",
                ]

                if any(
                    ext in lower
                    for ext in image_extensions
                ):

                    urls.append(value)

    scan(story)

    result = []
    seen = set()

    for url in urls:

        if url in seen:
            continue

        seen.add(url)
        result.append(url)

    return result


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

    story = load_json(
        STORY_FILE
    )

    if story:

        log(
            "Story file: data/story.json"
        )

        return story

    return {}


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

    summary = get_summary(
        story
    )

    county = get_county(
        story
    )

    images = get_image_urls(
        story
    )

    local_image = (
        LOCAL_IMAGE.exists()
        and LOCAL_IMAGE.stat().st_size > 10_000
    )

    # --------------------------------------------------------
    # Google News protection
    # --------------------------------------------------------

    combined = (
        title
        + " "
        + summary
    ).lower()

    forbidden = [
        "google news app",
        "sign in to google",
        "get the latest news",
        "google news",
    ]

    for phrase in forbidden:

        if phrase in combined:

            raise RuntimeError(
                "Google News boilerplate detected "
                "instead of a real story."
            )

    # --------------------------------------------------------
    # Headline
    # --------------------------------------------------------

    if not title:

        # Print structure so the next failure is
        # actually useful instead of another mystery.

        log(
            "STORY JSON DOES NOT CONTAIN A RECOGNIZED HEADLINE."
        )

        if isinstance(
            story,
            dict,
        ):

            log(
                "Available top-level fields: "
                + ", ".join(
                    str(key)
                    for key in story.keys()
                )
            )

        raise RuntimeError(
            "Selected story has no headline."
        )

    # --------------------------------------------------------
    # Image
    # --------------------------------------------------------

    if not images and not local_image:

        raise RuntimeError(
            "Selected story has no usable article image."
        )

    # --------------------------------------------------------
    # Log
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
        f"IMAGE URLS: {len(images)}"
    )

    if local_image:

        log(
            "LOCAL ARTICLE IMAGE: AVAILABLE"
        )

    return True


# ============================================================
# COMMAND RUNNER
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
# NEWS ENGINE
# ============================================================

def run_news_engine():

    if not NEWS_ENGINE.exists():

        log(
            "News engine not found."
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

        existing = load_story()

        if existing:

            log(
                "Existing story data will be used."
            )

            return

        raise


# ============================================================
# VIDEO GENERATOR
# ============================================================

def find_video_generator():

    for generator in VIDEO_GENERATORS:

        if generator.exists():

            return generator

    raise RuntimeError(
        "No video generator found."
    )


def remove_old_video():

    if not FINAL_MP4.exists():
        return

    try:

        FINAL_MP4.unlink()

        log(
            "Removed previous MP4."
        )

    except Exception as exc:

        raise RuntimeError(
            "Could not remove previous MP4: "
            f"{exc}"
        )


def run_video_generator():

    generator = find_video_generator()

    log(
        f"VIDEO GENERATOR: {generator.name}"
    )

    remove_old_video()

    run_command(
        [
            sys.executable,
            "-u",
            str(generator),
        ],
        "VIDEO GENERATOR",
    )


# ============================================================
# FFPROBE
# ============================================================

def probe_video():

    result = subprocess.run(
        [
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
        ],
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
# FINAL QC
# ============================================================

def verify_final_mp4():

    log(
        "VERIFYING FINAL MP4"
    )

    if not FINAL_MP4.exists():

        raise RuntimeError(
            "Rift Valley Watch MP4 was NOT generated."
        )

    size = FINAL_MP4.stat().st_size

    if size < 100_000:

        raise RuntimeError(
            "Final MP4 is suspiciously small."
        )

    probe = probe_video()

    streams = probe.get(
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

        elif stream.get(
            "codec_type"
        ) == "audio":

            audio = stream

    if video is None:

        raise RuntimeError(
            "Final MP4 contains no video stream."
        )

    if audio is None:

        raise RuntimeError(
            "Final MP4 contains no audio stream."
        )

    width = int(
        video.get(
            "width"
        )
        or 0
    )

    height = int(
        video.get(
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

    try:

        video_duration = float(
            video.get(
                "duration"
            )
            or 0
        )

    except Exception:

        video_duration = 0.0

    try:

        audio_duration = float(
            audio.get(
                "duration"
            )
            or 0
        )

    except Exception:

        audio_duration = 0.0

    difference = abs(
        video_duration
        - audio_duration
    )

    if (
        video_duration > 0
        and audio_duration > 0
        and difference > 1.5
    ):

        raise RuntimeError(
            "Video/audio duration mismatch: "
            f"{video_duration:.2f}s vs "
            f"{audio_duration:.2f}s."
        )

    size_mb = (
        size
        / (1024 * 1024)
    )

    log(
        "FINAL QC PASSED"
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

    return True


# ============================================================
# MAIN
# ============================================================

def main():

    print("")
    print("=" * 70)
    print("RIFT VALLEY WATCH")
    print("MAIN PIPELINE")
    print("=" * 70)

    prepare_directories()

    # --------------------------------------------------------
    # 1. NEWS
    # --------------------------------------------------------

    run_news_engine()

    # --------------------------------------------------------
    # 2. LOAD STORY
    # --------------------------------------------------------

    story = load_story()

    if not story:

        raise RuntimeError(
            "No story JSON was available."
        )

    # --------------------------------------------------------
    # 3. VALIDATE
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
    print("=" * 70)
    print("SELECTED STORY")
    print("=" * 70)
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
    print("=" * 70)
    print("")

    # --------------------------------------------------------
    # 4. VIDEO
    # --------------------------------------------------------

    run_video_generator()

    # --------------------------------------------------------
    # 5. FINAL QC
    # --------------------------------------------------------

    verify_final_mp4()

    print("")
    print("=" * 70)
    print("RIFT VALLEY WATCH SUCCESS")
    print("=" * 70)
    print(
        f"FINAL MP4: {FINAL_MP4}"
    )
    print(
        "1080x1920: PASS"
    )
    print(
        "VIDEO: PASS"
    )
    print(
        "AUDIO: PASS"
    )
    print(
        "FINAL QC: PASS"
    )
    print("=" * 70)

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
        print("=" * 70)
        print("RIFT VALLEY WATCH FAILED")
        print("=" * 70)
        print(
            f"{type(exc).__name__}: {exc}"
        )
        print("=" * 70)

        raise SystemExit(1)
