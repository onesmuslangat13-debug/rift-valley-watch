# ============================================================
# RIFT VALLEY WATCH
# MAIN PIPELINE
#
# VERSION: RIFT_VALLEY_WATCH_MAIN_REBUILT_V5
#
# FIX:
# - NEWS ENGINE MAY CREATE story.json
# - GENERATOR REQUIRES selected_story.json
# - MAIN NOW CREATES selected_story.json AUTOMATICALLY
# ============================================================

import json
import os
import shutil
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

STORY_FILE = DATA_DIR / "story.json"
SELECTED_STORY = DATA_DIR / "selected_story.json"

LOCAL_IMAGE = SOURCE_DIR / "story_image.jpg"

FINAL_MP4 = OUTPUT_DIR / "rift_valley_watch_reel.mp4"


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
# LOG
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
# JSON LOADING
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

            return json.load(handle)

    except Exception as exc:

        log(
            f"Could not read {path}: {exc}"
        )

        return {}


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_text(value):

    if value is None:
        return ""

    if isinstance(
        value,
        (dict, list),
    ):
        return ""

    return " ".join(
        str(value)
        .replace(
            "\n",
            " ",
        )
        .replace(
            "\r",
            " ",
        )
        .split()
    ).strip()


# ============================================================
# RECURSIVE VALUE FINDER
# ============================================================

def find_value(
    data,
    keys,
):

    if isinstance(
        data,
        dict,
    ):

        # First check current level.
        for key in keys:

            if key in data:

                value = clean_text(
                    data.get(key)
                )

                if value:
                    return value

        # Then recursively inspect nested data.
        for value in data.values():

            found = find_value(
                value,
                keys,
            )

            if found:
                return found

    elif isinstance(
        data,
        list,
    ):

        for item in data:

            found = find_value(
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

    return find_value(
        story,
        [
            "title",
            "headline",
            "article_title",
            "articleTitle",
            "story_title",
            "storyTitle",
            "news_title",
            "newsTitle",
            "heading",
            "name",
        ],
    )


# ============================================================
# SUMMARY
# ============================================================

def get_summary(story):

    return find_value(
        story,
        [
            "summary",
            "description",
            "content",
            "body",
            "text",
            "article_text",
            "articleText",
            "details",
        ],
    )


# ============================================================
# COUNTY
# ============================================================

def get_county(story):

    county = find_value(
        story,
        [
            "county",
            "county_name",
            "countyName",
        ],
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
# IMAGE EXTRACTION
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

        if isinstance(
            data,
            dict,
        ):

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

        elif isinstance(
            data,
            list,
        ):

            for item in data:
                scan(item)

        elif isinstance(
            data,
            str,
        ):

            value = data.strip()

            if (
                value.startswith(
                    "http://"
                )
                or value.startswith(
                    "https://"
                )
            ):

                lower = value.lower()

                if any(
                    extension in lower
                    for extension in [
                        ".jpg",
                        ".jpeg",
                        ".png",
                        ".webp",
                    ]
                ):

                    urls.append(
                        value
                    )

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
# VALIDATE STORY
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

    images = get_image_urls(
        story
    )

    local_image_valid = (
        LOCAL_IMAGE.exists()
        and LOCAL_IMAGE.stat().st_size > 10_000
    )

    combined = (
        title
        + " "
        + summary
    ).lower()

    forbidden = [
        "google news app",
        "sign in to google",
        "get the latest news",
        "personalized news",
    ]

    for phrase in forbidden:

        if phrase in combined:

            raise RuntimeError(
                "Google News boilerplate detected "
                "instead of a real story."
            )

    if not images and not local_image_valid:

        raise RuntimeError(
            "Selected story has no usable "
            "article image."
        )

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

    if local_image_valid:

        log(
            "LOCAL ARTICLE IMAGE: AVAILABLE"
        )

    return True


# ============================================================
# RUN COMMAND
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
# RUN NEWS ENGINE
# ============================================================

def run_news_engine():

    if not NEWS_ENGINE.exists():

        log(
            "scripts/news_engine.py not found."
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

        if (
            STORY_FILE.exists()
            or SELECTED_STORY.exists()
        ):

            log(
                "Existing story data will be used."
            )

            return

        raise


# ============================================================
# CREATE SELECTED STORY
#
# THIS IS THE IMPORTANT FIX.
#
# The current generator refuses to run unless:
#
# data/selected_story.json
#
# exists.
#
# If the news engine only produces story.json,
# copy that story into selected_story.json.
# ============================================================

def create_selected_story():

    selected = load_json(
        SELECTED_STORY
    )

    if selected:

        log(
            "selected_story.json already exists."
        )

        validate_story(
            selected
        )

        return selected

    story = load_json(
        STORY_FILE
    )

    if not story:

        raise RuntimeError(
            "News engine did not create "
            "data/story.json and "
            "data/selected_story.json "
            "does not exist."
        )

    validate_story(
        story
    )

    # Write the exact story structure
    # expected by the generator.

    with SELECTED_STORY.open(
        "w",
        encoding="utf-8",
    ) as handle:

        json.dump(
            story,
            handle,
            ensure_ascii=False,
            indent=2,
        )

    log(
        "Created data/selected_story.json "
        "from data/story.json."
    )

    # Confirm the file can be read back.

    confirmed = load_json(
        SELECTED_STORY
    )

    if not confirmed:

        raise RuntimeError(
            "Failed to create "
            "data/selected_story.json."
        )

    validate_story(
        confirmed
    )

    return confirmed


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


def remove_old_mp4():

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
        f"GENERATOR: {generator.name}"
    )

    # The generator requires selected_story.json.
    if not SELECTED_STORY.exists():

        raise RuntimeError(
            "selected_story.json is missing "
            "before video generation."
        )

    remove_old_mp4()

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


# ============================================================
# MAIN
# ============================================================

def main():

    print("")

    print(
        "=" * 70
    )

    print(
        "STARTING RIFT VALLEY WATCH"
    )

    print(
        "=" * 70
    )

    prepare_directories()

    # --------------------------------------------------------
    # STEP 1
    # --------------------------------------------------------

    run_news_engine()

    # --------------------------------------------------------
    # STEP 2
    # --------------------------------------------------------

    story = create_selected_story()

    # --------------------------------------------------------
    # STEP 3
    # --------------------------------------------------------

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
    # STEP 4
    # --------------------------------------------------------

    run_video_generator()

    # --------------------------------------------------------
    # STEP 5
    # --------------------------------------------------------

    verify_final_mp4()

    # --------------------------------------------------------
    # SUCCESS
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
        "VIDEO: PASS"
    )

    print(
        "AUDIO: PASS"
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
