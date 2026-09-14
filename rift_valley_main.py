# ============================================================
# RIFT VALLEY WATCH
# MAIN ORCHESTRATOR
# VERSION: RVW_MAIN_V32_NEWS_ENGINE_DIAGNOSTIC
#
# PURPOSE
# - Run the real-time news engine
# - Validate generated story/script
# - Select one story for the reel
# - Download/validate real article photos
# - Generate narration
# - Run the video renderer
# - Validate final MP4
#
# IMPORTANT
# - Uses data/ for JSON files
# - Uses assets/source/ for real article photos
# - Uses assets/video_work/ for temporary video work
# - Uses audio/ for narration
# - Uses output/ for final MP4
# - Rejects Gachagua content
# - Rejects Citizen/placeholder/avatar visuals
# - Captures the FULL news-engine error output
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

MAX_IMAGES = 6

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


# ============================================================
# LOGGING
# ============================================================

def banner(text):
    print()
    print("=" * 72)
    print(text)
    print("=" * 72)


def log(text):
    print(f"[RVW] {text}")


# ============================================================
# DIRECTORIES
# ============================================================

def ensure_directories():
    directories = [
        DATA_DIR,
        SOURCE_DIR,
        VIDEO_WORK_DIR,
        AUDIO_DIR,
        OUTPUT_DIR,
        NEWS_ENGINE.parent,
    ]

    for directory in directories:
        directory.mkdir(parents=True, exist_ok=True)

    log("Required directories verified.")


# ============================================================
# CLEAN GENERATED FILES
# ============================================================

def clean_generated_files():
    log("Cleaning generated files...")

    files_to_remove = [
        SELECTED_STORY_FILE,
        SELECTED_SCRIPT_FILE,
        NARRATION_FILE,
        FINAL_VIDEO,
    ]

    for file_path in files_to_remove:
        try:
            if file_path.exists():
                file_path.unlink()
                log(f"Removed: {file_path}")
        except Exception as exc:
            log(f"Could not remove {file_path}: {exc}")

    # Remove temporary video files.
    if VIDEO_WORK_DIR.exists():
        for item in VIDEO_WORK_DIR.iterdir():
            try:
                if item.is_file() or item.is_symlink():
                    item.unlink()
                elif item.is_dir():
                    shutil.rmtree(item)
            except Exception as exc:
                log(f"Could not clean {item}: {exc}")

    log("Generated-file cleanup complete.")


# ============================================================
# JSON HELPERS
# ============================================================

def load_json(path):
    if not path.exists():
        raise FileNotFoundError(f"Missing JSON file: {path}")

    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except json.JSONDecodeError as exc:
        raise RuntimeError(
            f"Invalid JSON in {path}: {exc}"
        ) from exc


def save_json(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)

    temporary = path.with_suffix(path.suffix + ".tmp")

    with temporary.open("w", encoding="utf-8") as handle:
        json.dump(
            data,
            handle,
            ensure_ascii=False,
            indent=2,
        )

    temporary.replace(path)


# ============================================================
# TEXT HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    text = str(value)

    text = text.replace("\r", " ")
    text = text.replace("\n", " ")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def story_text(story):
    if not isinstance(story, dict):
        return ""

    parts = []

    for key in [
        "title",
        "summary",
        "description",
        "content",
        "location",
        "county",
        "category",
    ]:
        value = story.get(key)

        if isinstance(value, str):
            parts.append(value)

    source = story.get("source")

    if isinstance(source, dict):
        parts.append(source.get("name", ""))

    verified_facts = story.get("verified_facts")

    if isinstance(verified_facts, list):
        for fact in verified_facts:
            if isinstance(fact, dict):
                parts.append(fact.get("label", ""))
                parts.append(fact.get("value", ""))

    return clean_text(" ".join(parts))


# ============================================================
# FORBIDDEN CONTENT
# ============================================================

def contains_forbidden_content(value):
    text = clean_text(value).lower()

    for term in FORBIDDEN_TERMS:
        if term in text:
            return True

    return False


def contains_forbidden_visual_text(value):
    text = clean_text(value).lower()

    for term in FORBIDDEN_VISUAL_TERMS:
        if term in text:
            return True

    return False


# ============================================================
# IMAGE PATH RESOLUTION
# ============================================================

def resolve_image_path(value):
    if not value:
        return None

    raw = clean_text(value)

    if not raw:
        return None

    candidate = Path(raw)

    if candidate.is_absolute() and candidate.exists():
        return candidate

    candidates = [
        BASE_DIR / raw,
        DATA_DIR / raw,
        SOURCE_DIR / raw,
    ]

    for path in candidates:
        if path.exists():
            return path

    # Handle paths beginning with assets/
    normalized = raw.replace("\\", "/")

    if normalized.startswith("assets/"):
        path = BASE_DIR / normalized
        if path.exists():
            return path

    # Handle basename lookup in source directory.
    basename = Path(normalized).name

    if basename:
        path = SOURCE_DIR / basename

        if path.exists():
            return path

    return None


# ============================================================
# IMAGE VALIDATION
# ============================================================

def image_is_forbidden(path):
    if not path:
        return True

    text = str(path).lower()

    for term in FORBIDDEN_VISUAL_TERMS:
        if term in text:
            return True

    return False


def image_is_valid(path):
    if not path:
        return False

    try:
        path = Path(path)

        if not path.exists():
            return False

        if path.suffix.lower() not in SUPPORTED_IMAGE_EXTENSIONS:
            return False

        if path.stat().st_size < MIN_IMAGE_BYTES:
            return False

        if image_is_forbidden(path):
            return False

        return True

    except Exception:
        return False


# ============================================================
# COLLECT STORY IMAGES
# ============================================================

def collect_story_images(story):
    images = []

    if not isinstance(story, dict):
        return images

    possible_keys = [
        "image",
        "image_path",
        "image_file",
        "photo",
        "photo_path",
        "thumbnail",
        "thumbnail_path",
        "hero_image",
    ]

    for key in possible_keys:
        value = story.get(key)

        if isinstance(value, str):
            path = resolve_image_path(value)

            if path and image_is_valid(path):
                images.append(path)

        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    path = resolve_image_path(item)

                    if path and image_is_valid(path):
                        images.append(path)

                elif isinstance(item, dict):
                    for item_key in [
                        "path",
                        "file",
                        "file_path",
                        "image",
                        "image_path",
                        "url",
                    ]:
                        item_value = item.get(item_key)

                        if isinstance(item_value, str):
                            path = resolve_image_path(item_value)

                            if path and image_is_valid(path):
                                images.append(path)

    # Check common multi-image field.
    for key in [
        "images",
        "photos",
        "visuals",
        "image_paths",
    ]:
        value = story.get(key)

        if not isinstance(value, list):
            continue

        for item in value:
            if isinstance(item, str):
                path = resolve_image_path(item)

                if path and image_is_valid(path):
                    images.append(path)

            elif isinstance(item, dict):
                for item_key in [
                    "path",
                    "file",
                    "file_path",
                    "image",
                    "image_path",
                    "url",
                ]:
                    item_value = item.get(item_key)

                    if isinstance(item_value, str):
                        path = resolve_image_path(item_value)

                        if path and image_is_valid(path):
                            images.append(path)

    # Search source directory for photos if the JSON itself does
    # not contain enough explicit image references.
    if SOURCE_DIR.exists():
        for path in sorted(SOURCE_DIR.iterdir()):
            if not path.is_file():
                continue

            if not image_is_valid(path):
                continue

            images.append(path)

    # De-duplicate.
    unique = []
    seen = set()

    for path in images:
        try:
            key = str(path.resolve()).lower()
        except Exception:
            key = str(path).lower()

        if key in seen:
            continue

        seen.add(key)
        unique.append(path)

    return unique[:MAX_IMAGES]


# ============================================================
# SYNCHRONIZE STORY IMAGES
# ============================================================

def synchronize_story_images(story):
    images = collect_story_images(story)

    if not images:
        log("No valid real article photographs found.")
        return []

    normalized_images = [
        str(path.relative_to(BASE_DIR))
        if path.is_relative_to(BASE_DIR)
        else str(path)
        for path in images
    ]

    story["images"] = normalized_images

    # Preserve the first image in common compatibility fields.
    first = normalized_images[0]

    story["image"] = first
    story["image_path"] = first

    log(f"Validated {len(images)} real article image(s).")

    return images


# ============================================================
# STORY SELECTION
# ============================================================

def extract_story_candidates(payload):
    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        return []

    for key in [
        "stories",
        "articles",
        "items",
        "results",
        "news",
    ]:
        value = payload.get(key)

        if isinstance(value, list):
            return value

    # Some engines write a single story object.
    if payload.get("title"):
        return [payload]

    return []


def story_score(story):
    score = 0

    if not isinstance(story, dict):
        return -999999

    title = clean_text(story.get("title"))
    summary = clean_text(story.get("summary"))

    category = clean_text(story.get("category")).upper()
    county = clean_text(story.get("county"))

    text = story_text(story).lower()

    if contains_forbidden_content(text):
        return -999999

    # Strong preference for usable stories.
    if title:
        score += 30

    if summary:
        score += 20

    if county:
        score += 10

    if category:
        score += 10

    # Prefer current major categories.
    preferred_categories = {
        "POLITICS": 25,
        "DEVELOPMENT": 24,
        "INFRASTRUCTURE": 23,
        "BUSINESS & ECONOMY": 22,
        "AGRICULTURE": 20,
        "HEALTH": 18,
        "EDUCATION": 17,
        "SECURITY": 16,
    }

    score += preferred_categories.get(category, 0)

    # Prefer stories with real images.
    images = collect_story_images(story)

    if images:
        score += 30

    if len(images) >= 2:
        score += 15

    # Avoid very obviously generic stories.
    if "press release" in text:
        score -= 5

    if len(title) < 15:
        score -= 10

    return score


def select_story(payload):
    candidates = extract_story_candidates(payload)

    if not candidates:
        raise RuntimeError(
            "No usable stories were found in data/story.json."
        )

    ranked = []

    for story in candidates:
        if not isinstance(story, dict):
            continue

        score = story_score(story)

        if score <= -999000:
            continue

        ranked.append((score, story))

    if not ranked:
        raise RuntimeError(
            "All available stories were rejected by content filters."
        )

    ranked.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    selected = ranked[0][1]

    if contains_forbidden_content(story_text(selected)):
        raise RuntimeError(
            "Selected story contains forbidden content."
        )

    log(
        "Selected story: "
        + clean_text(selected.get("title"))
    )

    return selected


# ============================================================
# SCRIPT SELECTION
# ============================================================

def extract_script_candidates(payload):
    if isinstance(payload, list):
        return payload

    if not isinstance(payload, dict):
        return []

    for key in [
        "scripts",
        "items",
        "stories",
        "articles",
    ]:
        value = payload.get(key)

        if isinstance(value, list):
            return value

    if payload.get("title") or payload.get("narration"):
        return [payload]

    return []


def script_matches_story(script, story):
    if not isinstance(script, dict):
        return False

    story_title = clean_text(story.get("title")).lower()

    script_title = clean_text(
        script.get("title")
    ).lower()

    if story_title and script_title:
        if story_title == script_title:
            return True

        # Partial matching.
        words = [
            word
            for word in re.findall(r"[a-z0-9]+", story_title)
            if len(word) > 4
        ]

        if words:
            matches = sum(
                1
                for word in words
                if word in script_title
            )

            if matches >= min(4, len(words)):
                return True

    return False


def select_script(payload, story):
    candidates = extract_script_candidates(payload)

    if not candidates:
        log("No script list detected; building narration from story.")
        return {}

    for script in candidates:
        if script_matches_story(script, story):
            return script

    # If no exact match, use first valid script.
    for script in candidates:
        if isinstance(script, dict):
            return script

    return {}


# ============================================================
# NARRATION
# ============================================================

def build_narration_text(story, script=None):
    if not isinstance(story, dict):
        raise RuntimeError("Selected story is not a dictionary.")

    if isinstance(script, dict):
        for key in [
            "narration",
            "voiceover",
            "script",
            "text",
            "body",
        ]:
            value = script.get(key)

            if isinstance(value, str):
                text = clean_text(value)

                if len(text) >= 40 and not contains_forbidden_content(text):
                    return text

    title = clean_text(story.get("title"))
    summary = clean_text(story.get("summary"))

    verified_facts = story.get("verified_facts")

    fact_text = []

    if isinstance(verified_facts, list):
        for fact in verified_facts:
            if not isinstance(fact, dict):
                continue

            label = clean_text(fact.get("label"))
            value = clean_text(fact.get("value"))

            if value:
                if label:
                    fact_text.append(f"{label}: {value}")
                else:
                    fact_text.append(value)

    parts = []

    if title:
        parts.append(title)

    if summary:
        parts.append(summary)

    if fact_text:
        parts.append(
            " ".join(fact_text[:5])
        )

    text = clean_text(" ".join(parts))

    if not text:
        raise RuntimeError(
            "Unable to build narration text."
        )

    if contains_forbidden_content(text):
        raise RuntimeError(
            "Narration contains forbidden content."
        )

    return text


def generate_narration(text):
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    if NARRATION_FILE.exists():
        try:
            NARRATION_FILE.unlink()
        except Exception:
            pass

    log("Generating narration...")

    try:
        tts = gTTS(
            text=text,
            lang="en",
            slow=False,
        )

        tts.save(str(NARRATION_FILE))

    except Exception as exc:
        raise RuntimeError(
            f"gTTS narration generation failed: {exc}"
        ) from exc

    if not NARRATION_FILE.exists():
        raise RuntimeError(
            "Narration file was not created."
        )

    if NARRATION_FILE.stat().st_size < MIN_AUDIO_BYTES:
        raise RuntimeError(
            "Narration file is too small or empty."
        )

    log(
        f"Narration created: "
        f"{NARRATION_FILE.stat().st_size:,} bytes"
    )


# ============================================================
# NEWS ENGINE
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

    # IMPORTANT:
    # Capture stdout/stderr so GitHub Actions shows the REAL
    # failure instead of only "exit code 1".
    result = subprocess.run(
        command,
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    engine_output = result.stdout or ""

    if engine_output:
        print()
        print("---------- NEWS ENGINE OUTPUT ----------")
        print(engine_output)
        print("-------- END NEWS ENGINE OUTPUT --------")
        print()

    if result.returncode != 0:
        raise RuntimeError(
            "News engine failed with exit code "
            f"{result.returncode}.\n\n"
            "FULL NEWS ENGINE OUTPUT:\n"
            f"{engine_output[-12000:]}"
        )

    log("News engine completed successfully.")

    if not STORY_FILE.exists():
        raise RuntimeError(
            "News engine completed but data/story.json "
            "was not created."
        )

    if not SCRIPT_FILE.exists():
        raise RuntimeError(
            "News engine completed but data/script.json "
            "was not created."
        )


# ============================================================
# CREATE SELECTED FILES
# ============================================================

def create_selected_files():
    banner("SELECTING STORY")

    story_payload = load_json(STORY_FILE)

    selected_story = select_story(story_payload)

    images = synchronize_story_images(
        selected_story
    )

    if not images:
        raise RuntimeError(
            "Selected story has no valid real article photograph."
        )

    # Save the selected story.
    save_json(
        SELECTED_STORY_FILE,
        selected_story,
    )

    script_payload = load_json(SCRIPT_FILE)

    selected_script = select_script(
        script_payload,
        selected_story,
    )

    narration = build_narration_text(
        selected_story,
        selected_script,
    )

    if isinstance(selected_script, dict):
        selected_script["title"] = selected_story.get(
            "title",
            selected_script.get("title", ""),
        )

        selected_script["narration"] = narration

    else:
        selected_script = {
            "title": selected_story.get("title", ""),
            "narration": narration,
        }

    selected_script["images"] = selected_story.get(
        "images",
        [],
    )

    save_json(
        SELECTED_SCRIPT_FILE,
        selected_script,
    )

    log(
        f"Selected story saved: "
        f"{SELECTED_STORY_FILE}"
    )

    log(
        f"Selected script saved: "
        f"{SELECTED_SCRIPT_FILE}"
    )

    return selected_story, selected_script


# ============================================================
# VALIDATE SELECTED DATA
# ============================================================

def validate_selected_data():
    banner("VALIDATING SELECTED DATA")

    if not SELECTED_STORY_FILE.exists():
        raise RuntimeError(
            "selected_story.json is missing."
        )

    if not SELECTED_SCRIPT_FILE.exists():
        raise RuntimeError(
            "selected_script.json is missing."
        )

    story = load_json(
        SELECTED_STORY_FILE
    )

    script = load_json(
        SELECTED_SCRIPT_FILE
    )

    if not isinstance(story, dict):
        raise RuntimeError(
            "selected_story.json does not contain a story object."
        )

    title = clean_text(story.get("title"))

    if not title:
        raise RuntimeError(
            "Selected story has no title."
        )

    full_text = story_text(story)

    if contains_forbidden_content(full_text):
        raise RuntimeError(
            "Selected story contains forbidden content."
        )

    images = collect_story_images(story)

    if not images:
        raise RuntimeError(
            "Selected story contains no valid real article images."
        )

    narration = ""

    if isinstance(script, dict):
        narration = clean_text(
            script.get("narration")
            or script.get("voiceover")
            or script.get("script")
            or script.get("text")
        )

    if not narration:
        narration = build_narration_text(
            story,
            script,
        )

    if contains_forbidden_content(narration):
        raise RuntimeError(
            "Selected narration contains forbidden content."
        )

    log(f"Story title: {title}")
    log(f"Real images: {len(images)}")
    log(f"Narration characters: {len(narration)}")

    return story, script


# ============================================================
# RENDERER
# ============================================================

def run_renderer():
    banner("RUNNING VIDEO RENDERER")

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
        "Executing: "
        + " ".join(command)
    )

    result = subprocess.run(
        command,
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    renderer_output = result.stdout or ""

    if renderer_output:
        print()
        print("---------- VIDEO RENDERER OUTPUT ----------")
        print(renderer_output)
        print("-------- END VIDEO RENDERER OUTPUT --------")
        print()

    if result.returncode != 0:
        raise RuntimeError(
            "Video renderer failed with exit code "
            f"{result.returncode}.\n\n"
            "FULL RENDERER OUTPUT:\n"
            f"{renderer_output[-12000:]}"
        )

    log("Video renderer completed successfully.")


# ============================================================
# FINAL VIDEO VALIDATION
# ============================================================

def validate_final_output():
    banner("VALIDATING FINAL VIDEO")

    if not FINAL_VIDEO.exists():
        raise RuntimeError(
            f"Final MP4 does not exist: {FINAL_VIDEO}"
        )

    size = FINAL_VIDEO.stat().st_size

    if size < MIN_VIDEO_BYTES:
        raise RuntimeError(
            "Final MP4 is too small."
        )

    log(
        f"Final video size: {size:,} bytes"
    )

    # Validate with ffprobe if available.
    ffprobe = shutil.which("ffprobe")

    if not ffprobe:
        log(
            "ffprobe not found; skipping technical stream validation."
        )
        return

    command = [
        ffprobe,
        "-v",
        "error",
        "-show_entries",
        "stream=index,codec_type,codec_name,width,height",
        "-of",
        "json",
        str(FINAL_VIDEO),
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
        check=False,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "ffprobe failed:\n"
            + result.stdout
        )

    try:
        probe = json.loads(result.stdout)
    except Exception as exc:
        raise RuntimeError(
            "Unable to parse ffprobe output."
        ) from exc

    streams = probe.get("streams", [])

    video_streams = [
        stream
        for stream in streams
        if stream.get("codec_type") == "video"
    ]

    audio_streams = [
        stream
        for stream in streams
        if stream.get("codec_type") == "audio"
    ]

    if not video_streams:
        raise RuntimeError(
            "Final MP4 contains no video stream."
        )

    if not audio_streams:
        raise RuntimeError(
            "Final MP4 contains no audio stream."
        )

    video = video_streams[0]

    width = video.get("width")
    height = video.get("height")

    log(
        f"Video dimensions: {width}x{height}"
    )

    if width != 1080 or height != 1920:
        raise RuntimeError(
            "Final video is not 1080x1920 vertical."
        )

    log("Final MP4 passed technical validation.")


# ============================================================
# SUMMARY
# ============================================================

def print_summary():
    banner("RIFT VALLEY WATCH - GENERATION COMPLETE")

    print(f"Story JSON:       {STORY_FILE}")
    print(f"Selected story:   {SELECTED_STORY_FILE}")
    print(f"Selected script:  {SELECTED_SCRIPT_FILE}")
    print(f"Narration:        {NARRATION_FILE}")
    print(f"Final video:      {FINAL_VIDEO}")

    if FINAL_VIDEO.exists():
        print(
            f"Final size:       "
            f"{FINAL_VIDEO.stat().st_size:,} bytes"
        )

    print()
    print("STATUS: SUCCESS")
    print()


# ============================================================
# MAIN
# ============================================================

def main():
    try:
        banner(
            "RIFT VALLEY WATCH - "
            "REAL-TIME NEWS VIDEO PIPELINE"
        )

        ensure_directories()

        clean_generated_files()

        # ----------------------------------------------------
        # STEP 1
        # Fetch fresh news and real article photos.
        # ----------------------------------------------------
        run_news_engine()

        # ----------------------------------------------------
        # STEP 2
        # Select one strong story and its photos.
        # ----------------------------------------------------
        create_selected_files()

        # ----------------------------------------------------
        # STEP 3
        # Validate selected story/script.
        # ----------------------------------------------------
        story, script = validate_selected_data()

        # ----------------------------------------------------
        # STEP 4
        # Build narration.
        # ----------------------------------------------------
        narration = build_narration_text(
            story,
            script,
        )

        # ----------------------------------------------------
        # STEP 5
        # Generate narration MP3.
        # ----------------------------------------------------
        generate_narration(narration)

        # ----------------------------------------------------
        # STEP 6
        # Validate narration.
        # ----------------------------------------------------
        if not NARRATION_FILE.exists():
            raise RuntimeError(
                "Narration MP3 missing after generation."
            )

        if NARRATION_FILE.stat().st_size < MIN_AUDIO_BYTES:
            raise RuntimeError(
                "Narration MP3 is invalid or too small."
            )

        # ----------------------------------------------------
        # STEP 7
        # Render final vertical reel.
        # ----------------------------------------------------
        run_renderer()

        # ----------------------------------------------------
        # STEP 8
        # Validate final MP4.
        # ----------------------------------------------------
        validate_final_output()

        # ----------------------------------------------------
        # STEP 9
        # Print success summary.
        # ----------------------------------------------------
        print_summary()

        return 0

    except KeyboardInterrupt:
        print()
        print("Pipeline interrupted by user.")
        return 130

    except Exception as exc:
        banner("RIFT VALLEY WATCH - PIPELINE FAILED")

        print(f"ERROR: {exc}")
        print()

        print("TRACEBACK:")
        traceback.print_exc()

        print()
        print("STATUS: FAILED")

        return 1


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    sys.exit(main())
