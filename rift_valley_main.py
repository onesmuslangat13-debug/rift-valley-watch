# ============================================================
# RIFT VALLEY WATCH
# MAIN PIPELINE
#
# VERSION: RIFT_VALLEY_WATCH_MAIN_REBUILT_V6
#
# PIPELINE:
#   NEWS ENGINE
#        ↓
#   story.json
#        ↓
#   selected_story.json
#        ↓
#   selected_script.json
#        ↓
#   VIDEO GENERATOR
#        ↓
#   FINAL MP4
#
# IMPORTANT:
# The current video generator requires:
#   data/selected_story.json
#   data/selected_script.json
#
# This main file creates both automatically.
# ============================================================

import json
import os
import re
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
SELECTED_SCRIPT = DATA_DIR / "selected_script.json"

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

    text = str(value)

    text = text.replace(
        "\n",
        " ",
    )

    text = text.replace(
        "\r",
        " ",
    )

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


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

        # Check current level first.
        for key in keys:

            if key in data:

                value = clean_text(
                    data.get(key)
                )

                if value:
                    return value

        # Then inspect nested objects.
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
# IMAGE URL EXTRACTION
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

    images = get_image_urls(
        story
    )

    local_image_valid = (
        LOCAL_IMAGE.exists()
        and LOCAL_IMAGE.stat().st_size > 10_000
    )

    # --------------------------------------------------------
    # Reject Google News boilerplate.
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
        "personalized news",
    ]

    for phrase in forbidden:

        if phrase in combined:

            raise RuntimeError(
                "Google News boilerplate detected."
            )

    # --------------------------------------------------------
    # Real image required.
    # --------------------------------------------------------

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

        existing = (
            SELECTED_STORY.exists()
            or STORY_FILE.exists()
        )

        if existing:

            log(
                "Existing story data will be used."
            )

            return

        raise


# ============================================================
# CREATE SELECTED STORY
# ============================================================

def create_selected_story():

    selected = load_json(
        SELECTED_STORY
    )

    if selected:

        validate_story(
            selected
        )

        log(
            "selected_story.json already exists."
        )

        return selected

    story = load_json(
        STORY_FILE
    )

    if not story:

        raise RuntimeError(
            "No story.json was produced."
        )

    validate_story(
        story
    )

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
        "Created data/selected_story.json."
    )

    confirmed = load_json(
        SELECTED_STORY
    )

    if not confirmed:

        raise RuntimeError(
            "selected_story.json could not "
            "be created."
        )

    validate_story(
        confirmed
    )

    return confirmed


# ============================================================
# BUILD NARRATION
#
# This fixes:
#
# "selected_script.json not found.
#  Using story narration."
#
# The generator will now receive an explicit
# narration field.
# ============================================================

def build_narration(story):

    title = get_title(
        story
    )

    summary = get_summary(
        story
    )

    county = get_county(
        story
    )

    # --------------------------------------------------------
    # Use existing narration if the news engine already
    # supplied one.
    # --------------------------------------------------------

    existing = find_value(
        story,
        [
            "narration",
            "voiceover",
            "voice_over",
            "script",
            "narration_text",
            "narrationText",
        ],
    )

    if existing:

        narration = existing

    else:

        # ----------------------------------------------------
        # Build clean narration from the selected story.
        #
        # Do NOT mention source/publisher.
        # ----------------------------------------------------

        if summary:

            narration = (
                f"{title}. "
                f"Here is what is happening in "
                f"{county if county else 'the Rift Valley'}. "
                f"{summary}"
            )

        else:

            narration = (
                f"{title}. "
                f"This is the latest development "
                f"from "
                f"{county if county else 'the Rift Valley'}."
            )

    # --------------------------------------------------------
    # Remove source/publisher references from narration.
    # --------------------------------------------------------

    publisher_terms = [
        "people daily",
        "citizen tv",
        "citizen digital",
        "the star",
        "standard media",
        "nation media",
        "kenya news agency",
        "kna",
        "facebook",
        "twitter",
        "x.com",
        "google news",
    ]

    for term in publisher_terms:

        narration = re.sub(
            re.escape(term),
            "",
            narration,
            flags=re.IGNORECASE,
        )

    # --------------------------------------------------------
    # Remove URL-like content.
    # --------------------------------------------------------

    narration = re.sub(
        r"https?://\S+",
        "",
        narration,
        flags=re.IGNORECASE,
    )

    # --------------------------------------------------------
    # Clean punctuation/spacing.
    # --------------------------------------------------------

    narration = re.sub(
        r"\s+",
        " ",
        narration,
    ).strip()

    narration = re.sub(
        r"\s+([,.!?])",
        r"\1",
        narration,
    )

    if len(narration) < 20:

        raise RuntimeError(
            "Could not build usable narration."
        )

    return narration


# ============================================================
# CREATE SELECTED SCRIPT
# ============================================================

def create_selected_script(
    story,
):

    # --------------------------------------------------------
    # If an existing selected_script.json is already valid,
    # preserve it.
    # --------------------------------------------------------

    existing = load_json(
        SELECTED_SCRIPT
    )

    if existing:

        existing_narration = find_value(
            existing,
            [
                "narration",
                "voiceover",
                "voice_over",
                "narration_text",
                "narrationText",
                "script",
                "text",
            ],
        )

        if existing_narration:

            log(
                "selected_script.json already exists."
            )

            return existing

    # --------------------------------------------------------
    # Build fresh narration.
    # --------------------------------------------------------

    narration = build_narration(
        story
    )

    title = get_title(
        story
    )

    county = get_county(
        story
    )

    # --------------------------------------------------------
    # Write multiple compatible field names.
    #
    # This makes the script compatible with the
    # current generator regardless of which narration
    # key its get_narration() function reads.
    # --------------------------------------------------------

    script = {
        "title": title,
        "headline": title,
        "county": county,
        "narration": narration,
        "voiceover": narration,
        "voice_over": narration,
        "narration_text": narration,
        "text": narration,
        "script": narration,
    }

    with SELECTED_SCRIPT.open(
        "w",
        encoding="utf-8",
    ) as handle:

        json.dump(
            script,
            handle,
            ensure_ascii=False,
            indent=2,
        )

    log(
        "Created data/selected_script.json."
    )

    log(
        f"NARRATION WORDS: "
        f"{len(narration.split())}"
    )

    # --------------------------------------------------------
    # Confirm.
    # --------------------------------------------------------

    confirmed = load_json(
        SELECTED_SCRIPT
    )

    if not confirmed:

        raise RuntimeError(
            "selected_script.json was not "
            "created successfully."
        )

    confirmed_narration = find_value(
        confirmed,
        [
            "narration",
            "voiceover",
            "voice_over",
            "narration_text",
            "narrationText",
            "text",
            "script",
        ],
    )

    if not confirmed_narration:

        raise RuntimeError(
            "selected_script.json contains "
            "no usable narration."
        )

    return confirmed


# ============================================================
# FIND VIDEO GENERATOR
# ============================================================

def find_video_generator():

    for generator in VIDEO_GENERATORS:

        if generator.exists():

            return generator

    raise RuntimeError(
        "No video generator found."
    )


# ============================================================
# REMOVE OLD MP4
# ============================================================

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


# ============================================================
# RUN VIDEO GENERATOR
# ============================================================

def run_video_generator():

    generator = find_video_generator()

    log(
        f"GENERATOR: {generator.name}"
    )

    if not SELECTED_STORY.exists():

        raise RuntimeError(
            "selected_story.json is missing."
        )

    if not SELECTED_SCRIPT.exists():

        raise RuntimeError(
            "selected_script.json is missing."
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
# FINAL MP4 QC
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
    # STEP 1 — NEWS ENGINE
    # --------------------------------------------------------

    run_news_engine()

    # --------------------------------------------------------
    # STEP 2 — SELECT STORY
    # --------------------------------------------------------

    story = create_selected_story()

    # --------------------------------------------------------
    # STEP 3 — CREATE NARRATION SCRIPT
    # --------------------------------------------------------

    script = create_selected_script(
        story
    )

    # --------------------------------------------------------
    # STEP 4 — DISPLAY STORY
    # --------------------------------------------------------

    title = get_title(
        story
    )

    county = get_county(
        story
    )

    narration = find_value(
        script,
        [
            "narration",
            "voiceover",
            "voice_over",
            "narration_text",
            "text",
            "script",
        ],
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
        f"NARRATION WORDS: "
        f"{len(narration.split())}"
    )

    print(
        "=" * 70
    )

    print("")

    # --------------------------------------------------------
    # STEP 5 — VIDEO
    # --------------------------------------------------------

    run_video_generator()

    # --------------------------------------------------------
    # STEP 6 — FINAL QC
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
