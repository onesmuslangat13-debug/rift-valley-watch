# ============================================================
# RIFT VALLEY WATCH
# MAIN ORCHESTRATOR
#
# VERSION: RVW_MAIN_V31_STABLE_PIPELINE
#
# FLOW:
#
# scripts/news_engine.py
#       ↓
# data/story.json
# data/script.json
#       ↓
# select ONE story
#       ↓
# data/selected_story.json
# data/selected_script.json
#       ↓
# audio/narration.mp3
#       ↓
# rift_valley_video_generator.py
#       ↓
# output/rift_valley_watch_reel.mp4
# ============================================================

from pathlib import Path
import json
import re
import subprocess
import sys
import shutil
import traceback

from gtts import gTTS


# ============================================================
# PATHS
# ============================================================

BASE_DIR = Path(__file__).resolve().parent

DATA_DIR = BASE_DIR / "data"
SOURCE_DIR = BASE_DIR / "assets" / "source"
VIDEO_WORK_DIR = BASE_DIR / "assets" / "video_work"
AUDIO_DIR = BASE_DIR / "audio"
OUTPUT_DIR = BASE_DIR / "output"

STORY_FILE = DATA_DIR / "story.json"
SCRIPT_FILE = DATA_DIR / "script.json"

SELECTED_STORY_FILE = DATA_DIR / "selected_story.json"
SELECTED_SCRIPT_FILE = DATA_DIR / "selected_script.json"

NARRATION_FILE = AUDIO_DIR / "narration.mp3"

RENDERER_FILE = BASE_DIR / "rift_valley_video_generator.py"

FINAL_VIDEO = OUTPUT_DIR / "rift_valley_watch_reel.mp4"

NEWS_ENGINE = BASE_DIR / "scripts" / "news_engine.py"


# ============================================================
# SETTINGS
# ============================================================

MIN_AUDIO_BYTES = 1000
MIN_IMAGE_BYTES = 10000
MIN_VIDEO_BYTES = 100000

FORBIDDEN_TERMS = [
    "rigathi gachagua",
    "gachagua",
]

FORBIDDEN_VISUAL_TERMS = [
    "citizen",
    "citizen digital",
    "citizen tv",
    "world cup",
    "avatar",
    "placeholder",
    "default image",
    "generic avatar",
    "profile picture",
]

SUPPORTED_IMAGE_EXTENSIONS = {
    ".jpg",
    ".jpeg",
    ".png",
    ".webp",
}

MAX_IMAGES = 6


# ============================================================
# LOGGING
# ============================================================

def banner(title):
    print()
    print("=" * 70)
    print(title)
    print("=" * 70)
    print()


def log(message):
    print(
        "[RIFT VALLEY WATCH]",
        message,
        flush=True,
    )


# ============================================================
# DIRECTORY SETUP
# ============================================================

def ensure_directories():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    SOURCE_DIR.mkdir(parents=True, exist_ok=True)
    VIDEO_WORK_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# CLEAN GENERATED OUTPUT
# ============================================================

def clean_generated_files():
    banner("CLEANING PREVIOUS GENERATED FILES")

    files_to_remove = [
        FINAL_VIDEO,
        NARRATION_FILE,
        AUDIO_DIR / "narration_temp.mp3",
        VIDEO_WORK_DIR / "narration.mp3",
        SELECTED_STORY_FILE,
        SELECTED_SCRIPT_FILE,
    ]

    for file in files_to_remove:
        try:
            if file.exists():
                file.unlink()
                log(f"Removed: {file}")
        except Exception as exc:
            log(f"Could not remove {file}: {exc}")

    # Do not delete story.json or script.json here.
    # The news engine owns those files.

    # Remove previously downloaded story images.
    for pattern in [
        "story_image*",
        "story_*.jpg",
        "story_*.jpeg",
        "story_*.png",
        "story_*.webp",
    ]:
        for file in SOURCE_DIR.glob(pattern):
            if not file.is_file():
                continue

            try:
                file.unlink()
                log(f"Removed old image: {file.name}")
            except Exception:
                pass


# ============================================================
# JSON HELPERS
# ============================================================

def load_json(path):
    if not path.exists():
        raise RuntimeError(
            f"Required JSON file does not exist: {path}"
        )

    try:
        with open(
            path,
            "r",
            encoding="utf-8",
        ) as f:
            return json.load(f)

    except Exception as exc:
        raise RuntimeError(
            f"Could not load JSON {path}: {exc}"
        )


def save_json(path, payload):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            payload,
            f,
            indent=2,
            ensure_ascii=False,
        )


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    text = str(value)

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def story_text(story):
    source = story.get("source", "")

    if isinstance(source, dict):
        source_text = " ".join(
            [
                str(source.get("name", "")),
                str(source.get("url", "")),
                str(source.get("type", "")),
            ]
        )
    else:
        source_text = str(source)

    pieces = [
        story.get("title", ""),
        story.get("description", ""),
        story.get("summary", ""),
        story.get("county", ""),
        story.get("category", ""),
        source_text,
    ]

    return clean_text(
        " ".join(
            str(x)
            for x in pieces
            if x
        )
    ).lower()


# ============================================================
# FORBIDDEN STORY CHECK
# ============================================================

def contains_forbidden_content(story):
    text = story_text(story)

    for term in FORBIDDEN_TERMS:
        if term in text:
            return True

    return False


# ============================================================
# IMAGE PATH HELPERS
# ============================================================

def resolve_image_path(value):
    if not value:
        return None

    value = str(value).strip()

    if not value:
        return None

    path = Path(value)

    if path.is_absolute():
        candidate = path
    else:
        candidate = BASE_DIR / value

    try:
        candidate = candidate.resolve()
    except Exception:
        return None

    if not candidate.exists():
        return None

    if not candidate.is_file():
        return None

    if candidate.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
        return None

    return candidate


def image_is_forbidden(path):
    name = path.name.lower()

    for term in FORBIDDEN_VISUAL_TERMS:
        if term in name:
            return True

    return False


def image_is_valid(path):
    if not path:
        return False

    if not path.exists():
        return False

    if not path.is_file():
        return False

    if path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
        return False

    if image_is_forbidden(path):
        return False

    try:
        if path.stat().st_size < MIN_IMAGE_BYTES:
            return False
    except Exception:
        return False

    return True


# ============================================================
# COLLECT STORY IMAGES
# ============================================================

def collect_story_images(story):
    candidates = []

    # --------------------------------------------------------
    # New multi-photo field
    # --------------------------------------------------------

    image_paths = story.get(
        "image_paths",
        [],
    )

    if isinstance(image_paths, str):
        image_paths = [image_paths]

    if isinstance(image_paths, list):
        for value in image_paths:
            path = resolve_image_path(value)

            if path:
                candidates.append(path)

    # --------------------------------------------------------
    # Legacy single-image fields
    # --------------------------------------------------------

    for key in [
        "image_path",
        "local_image",
        "image",
        "photo",
        "photo_path",
    ]:
        value = story.get(key, "")

        if isinstance(value, list):
            for item in value:
                path = resolve_image_path(item)

                if path:
                    candidates.append(path)
        else:
            path = resolve_image_path(value)

            if path:
                candidates.append(path)

    # --------------------------------------------------------
    # Search source directory
    # --------------------------------------------------------

    for path in sorted(
        SOURCE_DIR.iterdir(),
        key=lambda p: p.name.lower(),
    ):
        if not path.is_file():
            continue

        if path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
            continue

        if not path.name.lower().startswith("story_image"):
            continue

        candidates.append(path)

    # --------------------------------------------------------
    # Remove duplicates
    # --------------------------------------------------------

    unique = []
    seen = set()

    for path in candidates:
        try:
            resolved = str(path.resolve())
        except Exception:
            continue

        if resolved in seen:
            continue

        seen.add(resolved)

        if not image_is_valid(path):
            continue

        unique.append(path)

    return unique[:MAX_IMAGES]


# ============================================================
# SYNCHRONIZE IMAGE PATHS
# ============================================================

def synchronize_story_images(story, image_paths):
    relative_paths = []

    for path in image_paths:
        try:
            relative = path.resolve().relative_to(
                BASE_DIR.resolve()
            )
            relative_paths.append(
                relative.as_posix()
            )
        except Exception:
            relative_paths.append(
                str(path).replace(
                    "\\",
                    "/",
                )
            )

    story["image_paths"] = relative_paths

    if relative_paths:
        story["image_path"] = relative_paths[0]

    return story


# ============================================================
# SELECT ONE STORY
# ============================================================

def select_story(story_payload):
    if isinstance(story_payload, dict):
        if isinstance(
            story_payload.get("stories"),
            list,
        ):
            stories = story_payload["stories"]

        elif isinstance(
            story_payload.get("items"),
            list,
        ):
            stories = story_payload["items"]

        elif isinstance(
            story_payload.get("articles"),
            list,
        ):
            stories = story_payload["articles"]

        else:
            stories = [story_payload]

    elif isinstance(story_payload, list):
        stories = story_payload

    else:
        raise RuntimeError(
            "story.json contains an unsupported structure."
        )

    valid = []

    for story in stories:
        if not isinstance(story, dict):
            continue

        if contains_forbidden_content(story):
            log(
                "Rejected forbidden story: "
                + clean_text(
                    story.get("title", "")
                )
            )
            continue

        title = clean_text(
            story.get("title", "")
        )

        if not title:
            continue

        valid.append(story)

    if not valid:
        raise RuntimeError(
            "No valid Rift Valley story was available."
        )

    # Prefer the first story because news_engine.py
    # already ranks stories by freshness/relevance.
    selected = valid[0]

    log(
        "Selected story: "
        + clean_text(
            selected.get("title", "")
        )
    )

    return selected


# ============================================================
# SELECT CORRESPONDING SCRIPT
# ============================================================

def select_script(script_payload, selected_story):
    selected_title = clean_text(
        selected_story.get(
            "title",
            "",
        )
    ).lower()

    if isinstance(script_payload, dict):
        if isinstance(
            script_payload.get("scripts"),
            list,
        ):
            scripts = script_payload["scripts"]

        elif isinstance(
            script_payload.get("items"),
            list,
        ):
            scripts = script_payload["items"]

        elif isinstance(
            script_payload.get("scripts"),
            dict,
        ):
            scripts = [
                script_payload["scripts"]
            ]

        else:
            scripts = [script_payload]

    elif isinstance(script_payload, list):
        scripts = script_payload

    else:
        scripts = []

    # --------------------------------------------------------
    # Try exact/partial title match.
    # --------------------------------------------------------

    for script in scripts:
        if not isinstance(script, dict):
            continue

        candidates = [
            script.get("title", ""),
            script.get("story_title", ""),
            script.get("headline", ""),
        ]

        for candidate in candidates:
            candidate_text = clean_text(
                candidate
            ).lower()

            if (
                candidate_text
                and (
                    candidate_text == selected_title
                    or selected_title in candidate_text
                    or candidate_text in selected_title
                )
            ):
                return script

    # --------------------------------------------------------
    # Otherwise use first valid script.
    # --------------------------------------------------------

    for script in scripts:
        if isinstance(script, dict):
            return script

    # --------------------------------------------------------
    # Build fallback script.
    # --------------------------------------------------------

    title = clean_text(
        selected_story.get(
            "title",
            "",
        )
    )

    summary = clean_text(
        selected_story.get(
            "summary",
            selected_story.get(
                "description",
                "",
            ),
        )
    )

    county = clean_text(
        selected_story.get(
            "county",
            "",
        )
    )

    source = selected_story.get(
        "source",
        "",
    )

    if isinstance(source, dict):
        source_name = clean_text(
            source.get(
                "name",
                "",
            )
        )
    else:
        source_name = clean_text(source)

    parts = []

    if title:
        parts.append(title + ".")

    if county:
        parts.append(
            f"The development is reported in {county}."
        )

    if summary:
        parts.append(summary)

    if source_name:
        parts.append(
            f"The report is from {source_name}."
        )

    narration = " ".join(parts)

    return {
        "title": title,
        "story_title": title,
        "narration": narration,
        "script": narration,
        "text": narration,
    }


# ============================================================
# BUILD NARRATION TEXT
# ============================================================

def build_narration_text(
    selected_story,
    selected_script,
):
    # --------------------------------------------------------
    # Prefer explicit narration fields from script.
    # --------------------------------------------------------

    for key in [
        "narration",
        "narration_text",
        "voiceover",
        "voice_over",
        "script",
        "text",
    ]:
        value = selected_script.get(
            key,
            "",
        )

        if isinstance(value, str):
            value = clean_text(value)

            if len(value) >= 40:
                return value

    # --------------------------------------------------------
    # Story fallback.
    # --------------------------------------------------------

    title = clean_text(
        selected_story.get(
            "title",
            "",
        )
    )

    county = clean_text(
        selected_story.get(
            "county",
            "",
        )
    )

    category = clean_text(
        selected_story.get(
            "category",
            "",
        )
    )

    summary = clean_text(
        selected_story.get(
            "summary",
            selected_story.get(
                "description",
                "",
            ),
        )
    )

    source = selected_story.get(
        "source",
        "",
    )

    if isinstance(source, dict):
        source_name = clean_text(
            source.get(
                "name",
                "",
            )
        )
    else:
        source_name = clean_text(source)

    paragraphs = []

    if title:
        paragraphs.append(title + ".")

    if county and category:
        paragraphs.append(
            f"This is a {category.lower()} development "
            f"reported in {county}."
        )
    elif county:
        paragraphs.append(
            f"The development is in {county}."
        )

    if summary:
        paragraphs.append(summary)

    if source_name:
        paragraphs.append(
            f"The report comes from {source_name}."
        )

    narration = " ".join(
        paragraphs
    )

    if len(narration) < 40:
        narration = (
            title
            or "Rift Valley Watch brings you the latest regional update."
        )

    return clean_text(narration)


# ============================================================
# GENERATE NARRATION
# ============================================================

def generate_narration(text):
    banner("GENERATING NARRATION")

    text = clean_text(text)

    if not text:
        raise RuntimeError(
            "Narration text is empty."
        )

    log(
        f"Narration characters: {len(text)}"
    )

    temp_file = AUDIO_DIR / "narration_temp.mp3"

    for file in [
        NARRATION_FILE,
        temp_file,
        VIDEO_WORK_DIR / "narration.mp3",
    ]:
        try:
            if file.exists():
                file.unlink()
        except Exception:
            pass

    try:
        tts = gTTS(
            text=text,
            lang="en",
            slow=False,
        )

        tts.save(
            str(temp_file)
        )

    except Exception as exc:
        raise RuntimeError(
            f"gTTS narration generation failed: {exc}"
        )

    if not temp_file.exists():
        raise RuntimeError(
            "gTTS did not create narration_temp.mp3."
        )

    if temp_file.stat().st_size < MIN_AUDIO_BYTES:
        raise RuntimeError(
            "Generated narration is too small."
        )

    shutil.move(
        str(temp_file),
        str(NARRATION_FILE),
    )

    # Renderer uses audio/narration.mp3.
    # Keep a synchronized copy in video_work for compatibility.
    try:
        shutil.copy2(
            NARRATION_FILE,
            VIDEO_WORK_DIR / "narration.mp3",
        )
    except Exception as exc:
        log(
            f"Could not copy narration to video_work: {exc}"
        )

    log(
        f"Narration created: {NARRATION_FILE}"
    )

    log(
        f"Narration size: {NARRATION_FILE.stat().st_size} bytes"
    )


# ============================================================
# RUN NEWS ENGINE
# ============================================================

def run_news_engine():
    banner("RUNNING REAL-TIME NEWS ENGINE")

    if not NEWS_ENGINE.exists():
        raise RuntimeError(
            f"News engine not found: {NEWS_ENGINE}"
        )

    command = [
        sys.executable,
        "-u",
        str(NEWS_ENGINE),
    ]

    log(
        "Executing: "
        + " ".join(command)
    )

    result = subprocess.run(
        command,
        cwd=str(BASE_DIR),
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"News engine failed with exit code {result.returncode}."
        )

    if not STORY_FILE.exists():
        raise RuntimeError(
            "News engine completed but data/story.json was not created."
        )

    if not SCRIPT_FILE.exists():
        raise RuntimeError(
            "News engine completed but data/script.json was not created."
        )

    log(
        "News engine completed successfully."
    )


# ============================================================
# CREATE SELECTED FILES
# ============================================================

def create_selected_files():
    banner("SELECTING ONE STORY")

    story_payload = load_json(
        STORY_FILE
    )

    script_payload = load_json(
        SCRIPT_FILE
    )

    selected_story = select_story(
        story_payload
    )

    # --------------------------------------------------------
    # Validate/downloaded images.
    # --------------------------------------------------------

    image_paths = collect_story_images(
        selected_story
    )

    if not image_paths:
        raise RuntimeError(
            "Selected story has no valid real article images."
        )

    log(
        f"Valid story images found: {len(image_paths)}"
    )

    for index, path in enumerate(
        image_paths,
        start=1,
    ):
        log(
            f"Image {index}: {path}"
        )

    selected_story = synchronize_story_images(
        selected_story,
        image_paths,
    )

    # --------------------------------------------------------
    # Remove forbidden visual references from metadata.
    # --------------------------------------------------------

    if contains_forbidden_content(
        selected_story
    ):
        raise RuntimeError(
            "Selected story contains forbidden content."
        )

    selected_script = select_script(
        script_payload,
        selected_story,
    )

    # --------------------------------------------------------
    # Save selected story/script.
    # --------------------------------------------------------

    save_json(
        SELECTED_STORY_FILE,
        selected_story,
    )

    save_json(
        SELECTED_SCRIPT_FILE,
        selected_script,
    )

    if not SELECTED_STORY_FILE.exists():
        raise RuntimeError(
            "selected_story.json was not created."
        )

    if not SELECTED_SCRIPT_FILE.exists():
        raise RuntimeError(
            "selected_script.json was not created."
        )

    log(
        f"Created: {SELECTED_STORY_FILE}"
    )

    log(
        f"Created: {SELECTED_SCRIPT_FILE}"
    )

    return selected_story, selected_script


# ============================================================
# VALIDATE SELECTED DATA
# ============================================================

def validate_selected_data(
    story,
    script,
):
    banner("VALIDATING SELECTED STORY")

    if not isinstance(
        story,
        dict,
    ):
        raise RuntimeError(
            "Selected story is not a JSON object."
        )

    title = clean_text(
        story.get(
            "title",
            "",
        )
    )

    if not title:
        raise RuntimeError(
            "Selected story has no title."
        )

    if contains_forbidden_content(
        story
    ):
        raise RuntimeError(
            "Selected story contains forbidden Gachagua content."
        )

    images = collect_story_images(
        story
    )

    if not images:
        raise RuntimeError(
            "Selected story has no valid images."
        )

    log(
        f"Title: {title}"
    )

    log(
        f"County: "
        + clean_text(
            story.get(
                "county",
                "",
            )
        )
    )

    log(
        f"Category: "
        + clean_text(
            story.get(
                "category",
                "",
            )
        )
    )

    log(
        f"Valid images: {len(images)}"
    )

    if not isinstance(
        script,
        dict,
    ):
        raise RuntimeError(
            "Selected script is not a JSON object."
        )


# ============================================================
# RUN VIDEO RENDERER
# ============================================================

def run_renderer():
    banner("RUNNING VIDEO GENERATOR")

    if not RENDERER_FILE.exists():
        raise RuntimeError(
            f"Renderer not found: {RENDERER_FILE}"
        )

    command = [
        sys.executable,
        "-u",
        str(RENDERER_FILE),
    ]

    log(
        "Executing renderer..."
    )

    result = subprocess.run(
        command,
        cwd=str(BASE_DIR),
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"Video renderer failed with exit code {result.returncode}."
        )

    if not FINAL_VIDEO.exists():
        raise RuntimeError(
            "Renderer completed but final MP4 was not created."
        )

    if FINAL_VIDEO.stat().st_size < MIN_VIDEO_BYTES:
        raise RuntimeError(
            "Final MP4 is too small."
        )

    log(
        f"Final MP4 created: {FINAL_VIDEO}"
    )

    log(
        f"Final MP4 size: {FINAL_VIDEO.stat().st_size} bytes"
    )


# ============================================================
# FINAL FILE VALIDATION
# ============================================================

def validate_final_output():
    banner("FINAL OUTPUT VALIDATION")

    if not FINAL_VIDEO.exists():
        raise RuntimeError(
            "Final MP4 does not exist."
        )

    if FINAL_VIDEO.stat().st_size < MIN_VIDEO_BYTES:
        raise RuntimeError(
            "Final MP4 is below minimum size."
        )

    if not NARRATION_FILE.exists():
        raise RuntimeError(
            "Narration MP3 does not exist."
        )

    if NARRATION_FILE.stat().st_size < MIN_AUDIO_BYTES:
        raise RuntimeError(
            "Narration MP3 is too small."
        )

    log(
        f"MP4: {FINAL_VIDEO}"
    )

    log(
        f"MP4 size: {FINAL_VIDEO.stat().st_size} bytes"
    )

    log(
        f"Narration: {NARRATION_FILE}"
    )

    log(
        f"Narration size: {NARRATION_FILE.stat().st_size} bytes"
    )

    # --------------------------------------------------------
    # Use ffprobe when available.
    # --------------------------------------------------------

    ffprobe = shutil.which(
        "ffprobe"
    )

    if not ffprobe:
        log(
            "ffprobe not found; basic file validation completed."
        )
        return

    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "stream=index,codec_type,codec_name,width,height",
        "-show_entries",
        "format=duration,size",
        "-of",
        "default=noprint_wrappers=1",
        str(FINAL_VIDEO),
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "ffprobe could not validate the final MP4."
        )

    probe_output = result.stdout.strip()

    print()
    print("FFPROBE FINAL VIDEO")
    print("-" * 70)
    print(probe_output)
    print("-" * 70)
    print()

    if "codec_type=video" not in probe_output:
        raise RuntimeError(
            "Final MP4 does not contain a video stream."
        )

    if "codec_type=audio" not in probe_output:
        raise RuntimeError(
            "Final MP4 does not contain an audio stream."
        )

    if "width=1080" not in probe_output:
        raise RuntimeError(
            "Final video width is not 1080."
        )

    if "height=1920" not in probe_output:
        raise RuntimeError(
            "Final video height is not 1920."
        )

    log(
        "Final MP4 validation passed."
    )


# ============================================================
# PRINT SUMMARY
# ============================================================

def print_summary(
    story,
    image_paths,
):
    banner(
        "RIFT VALLEY WATCH GENERATION SUCCESSFUL"
    )

    print(
        "TITLE:"
    )
    print(
        clean_text(
            story.get(
                "title",
                "",
            )
        )
    )

    print()
    print(
        "COUNTY:"
    )
    print(
        clean_text(
            story.get(
                "county",
                "",
            )
        )
    )

    print()
    print(
        "CATEGORY:"
    )
    print(
        clean_text(
            story.get(
                "category",
                "",
            )
        )
    )

    print()
    print(
        "REAL ARTICLE IMAGES:"
    )

    for index, path in enumerate(
        image_paths,
        start=1,
    ):
        print(
            f"{index}. {path}"
        )

    print()
    print(
        "NARRATION:"
    )
    print(
        NARRATION_FILE
    )

    print()
    print(
        "FINAL MP4:"
    )
    print(
        FINAL_VIDEO
    )

    print()
    print("=" * 70)
    print(
        "RIFT VALLEY WATCH COMPLETE"
    )
    print("=" * 70)
    print()


# ============================================================
# MAIN
# ============================================================

def main():
    try:
        banner(
            "RIFT VALLEY WATCH - V31 STABLE PIPELINE"
        )

        log(
            f"Base directory: {BASE_DIR}"
        )

        ensure_directories()

        clean_generated_files()

        # ----------------------------------------------------
        # STEP 1
        # Run the real-time news engine.
        # ----------------------------------------------------

        run_news_engine()

        # ----------------------------------------------------
        # STEP 2
        # Create selected_story.json and
        # selected_script.json.
        # ----------------------------------------------------

        selected_story, selected_script = (
            create_selected_files()
        )

        # ----------------------------------------------------
        # STEP 3
        # Validate selected files.
        # ----------------------------------------------------

        validate_selected_data(
            selected_story,
            selected_script,
        )

        # ----------------------------------------------------
        # STEP 4
        # Build narration.
        # ----------------------------------------------------

        narration_text = build_narration_text(
            selected_story,
            selected_script,
        )

        if not narration_text:
            raise RuntimeError(
                "Could not build narration text."
            )

        log(
            "Narration text prepared."
        )

        # ----------------------------------------------------
        # STEP 5
        # Generate MP3.
        # ----------------------------------------------------

        generate_narration(
            narration_text
        )

        # ----------------------------------------------------
        # STEP 6
        # Run V29/V30/V31 renderer.
        # ----------------------------------------------------

        run_renderer()

        # ----------------------------------------------------
        # STEP 7
        # Final validation.
        # ----------------------------------------------------

        validate_final_output()

        # ----------------------------------------------------
        # STEP 8
        # Summary.
        # ----------------------------------------------------

        image_paths = collect_story_images(
            selected_story
        )

        print_summary(
            selected_story,
            image_paths,
        )

        return 0

    except Exception as exc:
        banner(
            "RIFT VALLEY WATCH GENERATION FAILED"
        )

        print(
            f"ERROR: {exc}"
        )

        print()
        print(
            "TRACEBACK:"
        )

        traceback.print_exc()

        return 1


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    sys.exit(
        main()
    )
