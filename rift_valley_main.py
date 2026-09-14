from pathlib import Path
import json
import re
import subprocess
import sys
import shutil
import hashlib
import traceback
import time

import requests
from PIL import Image, ImageOps
from gtts import gTTS

# ============================================================

# RIFT VALLEY WATCH

# MAIN ORCHESTRATOR

# VERSION: RVW_MAIN_V38_REAL_IMAGE_BYTE_RECOVERY

#

# PURPOSE

# - Run the news engine

# - Read data/story.json

# - Select ONE valid story

# - Recover REAL photographs belonging to that story

# - Recover generic filenames such as photo_02.jpg

# - Validate actual image bytes

# - Handle JPG files containing PNG/WebP/other image bytes

# - Normalize all valid images to JPEG

# - Create narration

# - Write selected_story.json

# - Write selected_script.json

# - Run video renderer

# - Validate final MP4

#

# IMPORTANT

# - Does NOT search Google for replacement images

# - Does NOT download replacement images

# - Does NOT use generic stock images

# - Does NOT mix unrelated story directories

# - Uses photographs already downloaded by news_engine.py

# - Supports multiple real photos for one story

# ============================================================

BASE_DIR = Path(**file**).resolve().parent

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

NEWS_ENGINE = BASE_DIR / "scripts" / "news_engine.py"

FINAL_VIDEO = OUTPUT_DIR / "rift_valley_watch_reel.mp4"

# ============================================================

# SETTINGS

# ============================================================

MIN_IMAGE_BYTES = 5000

MIN_IMAGE_WIDTH = 200
MIN_IMAGE_HEIGHT = 150

MIN_AUDIO_BYTES = 1000
MIN_VIDEO_BYTES = 100000

MAX_IMAGES = 6

MAX_SOURCE_SCAN_FILES = 5000

SUPPORTED_IMAGE_EXTENSIONS = {
".jpg",
".jpeg",
".png",
".webp",
".avif",
".bmp",
".tif",
".tiff",
}

POSSIBLE_MEDIA_EXTENSIONS = {
".jpg",
".jpeg",
".png",
".webp",
".avif",
".bmp",
".tif",
".tiff",
".jfif",
".bin",
".dat",
".img",
}

# ============================================================

# FORBIDDEN STORY TERMS

# ============================================================

FORBIDDEN_STORY_TERMS = [
"rigathi gachagua",
"gachagua",
]

# ============================================================

# FORBIDDEN VISUAL TERMS

# ============================================================

FORBIDDEN_VISUAL_TERMS = [
"citizen",
"citizen tv",
"ctv",
"k24",
"k24 tv",
"world cup",
"avatar",
"placeholder",
"default image",
"generic avatar",
"profile picture",
"dummy image",
"generic image",
"generic",
"logo",
"icon",
"thumbnail placeholder",
"no image",
"missing image",
]

# ============================================================

# POSSIBLE IMAGE FIELD NAMES

# ============================================================

IMAGE_FIELD_NAMES = {
"image",
"image_url",
"imageurl",
"image_path",
"imagepath",
"photo",
"photo_url",
"photourl",
"photo_path",
"photopath",
"thumbnail",
"thumbnail_url",
"thumbnailurl",
"media",
"media_url",
"mediaurl",
"media_path",
"mediapath",
"picture",
"picture_url",
"pictureurl",
"picture_path",
"picturepath",
"images",
"image_urls",
"image_paths",
"local_images",
"local_image_paths",
"photos",
"photo_urls",
"photo_paths",
"local_photos",
"local_photo_paths",
}

# ============================================================

# BASIC HELPERS

# ============================================================

def log(message=""):
print(message, flush=True)

def ensure_directories():
DATA_DIR.mkdir(parents=True, exist_ok=True)
SOURCE_DIR.mkdir(parents=True, exist_ok=True)
VIDEO_WORK_DIR.mkdir(parents=True, exist_ok=True)
AUDIO_DIR.mkdir(parents=True, exist_ok=True)
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

def safe_read_json(path):
if not path.exists():
return None

```
try:
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)
except Exception as exc:
    log(f"ERROR reading JSON {path}: {exc}")
    return None
```

def safe_write_json(path, payload):
path.parent.mkdir(parents=True, exist_ok=True)

```
temp = path.with_suffix(path.suffix + ".tmp")

with temp.open("w", encoding="utf-8") as f:
    json.dump(payload, f, indent=2, ensure_ascii=False)

temp.replace(path)
```

def clean_video_work_directory():
if VIDEO_WORK_DIR.exists():
for item in VIDEO_WORK_DIR.iterdir():
try:
if item.is_dir():
shutil.rmtree(item)
else:
item.unlink()
except Exception:
pass

```
VIDEO_WORK_DIR.mkdir(parents=True, exist_ok=True)
```

# ============================================================

# SUBPROCESS

# ============================================================

def run_python_script(script_path, label):
if not script_path.exists():
raise RuntimeError(
f"{label} not found: {script_path}"
)

```
log("")
log("=" * 70)
log(label)
log("=" * 70)

command = [
    sys.executable,
    str(script_path),
]

log("Running:")
log(" ".join(command))
log("")

result = subprocess.run(
    command,
    cwd=str(BASE_DIR),
    text=True,
)

if result.returncode != 0:
    raise RuntimeError(
        f"{label} failed with exit code {result.returncode}"
    )

return True
```

# ============================================================

# STORY TEXT

# ============================================================

def story_to_text(story):
if not isinstance(story, dict):
return ""

```
values = []

for key in [
    "title",
    "headline",
    "description",
    "summary",
    "content",
    "body",
    "location",
    "county",
    "source",
    "category",
]:
    value = story.get(key)

    if isinstance(value, str):
        values.append(value)

    elif isinstance(value, list):
        values.extend(
            str(x)
            for x in value
            if isinstance(x, (str, int, float))
        )

return " ".join(values)
```

def normalize_text(value):
if value is None:
return ""

```
text = str(value)

text = text.lower()

text = re.sub(
    r"[^a-z0-9]+",
    " ",
    text,
)

return re.sub(
    r"\s+",
    " ",
    text,
).strip()
```

def story_is_forbidden(story):
text = normalize_text(
story_to_text(story)
)

```
for term in FORBIDDEN_STORY_TERMS:
    if term in text:
        return True

return False
```

# ============================================================

# STORY EXTRACTION

# ============================================================

def extract_story_list(payload):
if payload is None:
return []

```
if isinstance(payload, list):
    return [
        item
        for item in payload
        if isinstance(item, dict)
    ]

if isinstance(payload, dict):

    for key in [
        "stories",
        "articles",
        "items",
        "results",
        "news",
        "data",
    ]:
        value = payload.get(key)

        if isinstance(value, list):
            return [
                item
                for item in value
                if isinstance(item, dict)
            ]

    if any(
        key in payload
        for key in [
            "title",
            "headline",
            "description",
            "summary",
        ]
    ):
        return [payload]

return []
```

# ============================================================

# STORY IDENTIFIERS

# ============================================================

def story_identifiers(story):
identifiers = []

```
if not isinstance(story, dict):
    return identifiers

keys = [
    "id",
    "story_id",
    "storyId",
    "article_id",
    "articleId",
    "news_id",
    "newsId",
    "hash",
    "story_hash",
    "article_hash",
    "uuid",
    "guid",
    "slug",
]

for key in keys:
    value = story.get(key)

    if value is None:
        continue

    if isinstance(value, (str, int, float)):
        value = str(value).strip()

        if value:
            identifiers.append(value)

return identifiers
```

# ============================================================

# IMAGE REFERENCE EXTRACTION

# ============================================================

def looks_like_image_reference(value):
if not isinstance(value, str):
return False

```
value = value.strip()

if not value:
    return False

lower = value.lower()

if lower.startswith("data:image/"):
    return False

if lower.startswith("http://"):
    return True

if lower.startswith("https://"):
    return True

path = Path(
    lower.split("?")[0].split("#")[0]
)

if path.suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS:
    return True

if path.suffix.lower() in POSSIBLE_MEDIA_EXTENSIONS:
    return True

return False
```

def extract_image_references(payload):
found = []

```
def walk(obj, key_hint=None):

    if isinstance(obj, dict):

        for key, value in obj.items():

            key_lower = str(key).lower()

            if key_lower in IMAGE_FIELD_NAMES:

                if isinstance(value, str):
                    if looks_like_image_reference(value):
                        found.append(value)

                elif isinstance(value, list):

                    for item in value:

                        if isinstance(item, str):
                            if looks_like_image_reference(item):
                                found.append(item)

                        elif isinstance(item, dict):
                            walk(item, key_lower)

                        elif isinstance(item, list):
                            walk(item, key_lower)

            else:
                walk(value, key_lower)

    elif isinstance(obj, list):

        for item in obj:
            walk(item, key_hint)

    elif isinstance(obj, str):

        if key_hint in IMAGE_FIELD_NAMES:
            if looks_like_image_reference(obj):
                found.append(obj)

walk(payload)

unique = []

seen = set()

for item in found:

    key = str(item).strip()

    if key and key not in seen:
        seen.add(key)
        unique.append(key)

return unique
```

# ============================================================

# PATH RESOLUTION

# ============================================================

def resolve_local_reference(reference):
if not isinstance(reference, str):
return None

```
reference = reference.strip()

if not reference:
    return None

if reference.startswith("http://"):
    return None

if reference.startswith("https://"):
    return None

cleaned = reference.split("?")[0].split("#")[0]

candidates = []

try:
    direct = Path(cleaned)

    if direct.is_absolute():
        candidates.append(direct)

except Exception:
    pass

candidates.extend([
    BASE_DIR / cleaned,
    SOURCE_DIR / cleaned,
    DATA_DIR / cleaned,
    VIDEO_WORK_DIR / cleaned,
])

normalized = cleaned.replace("\\", "/")

if normalized.startswith("./"):
    normalized = normalized[2:]

candidates.append(
    BASE_DIR / normalized
)

candidates.append(
    SOURCE_DIR / normalized
)

seen = set()

for candidate in candidates:

    try:
        candidate = candidate.resolve()
    except Exception:
        continue

    key = str(candidate)

    if key in seen:
        continue

    seen.add(key)

    if candidate.is_file():
        return candidate

return None
```

# ============================================================

# IMAGE VALIDATION

# ============================================================

def file_is_large_enough(path):
try:
return (
path.is_file()
and path.stat().st_size >= MIN_IMAGE_BYTES
)
except Exception:
return False

def pil_open_image(path):
try:
with Image.open(path) as image:
image.load()

```
        image = ImageOps.exif_transpose(image)

        width, height = image.size

        if width < MIN_IMAGE_WIDTH:
            return None

        if height < MIN_IMAGE_HEIGHT:
            return None

        return image.copy()

except Exception:
    return None
```

def image_is_decodable_by_pil(path):
image = pil_open_image(path)

```
if image is None:
    return False

try:
    image.close()
except Exception:
    pass

return True
```

# ============================================================

# FFMPEG FALLBACK

# ============================================================

def ffmpeg_available():
try:
result = subprocess.run(
[
"ffmpeg",
"-version",
],
stdout=subprocess.DEVNULL,
stderr=subprocess.DEVNULL,
)

```
    return result.returncode == 0

except Exception:
    return False
```

def decode_image_with_ffmpeg(path):
if not ffmpeg_available():
return None

```
try:

    command = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(path),
        "-frames:v",
        "1",
        "-f",
        "image2pipe",
        "-vcodec",
        "png",
        "pipe:1",
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if result.returncode != 0:
        return None

    if not result.stdout:
        return None

    from io import BytesIO

    image = Image.open(
        BytesIO(result.stdout)
    )

    image.load()

    image = ImageOps.exif_transpose(
        image
    )

    width, height = image.size

    if width < MIN_IMAGE_WIDTH:
        return None

    if height < MIN_IMAGE_HEIGHT:
        return None

    return image.copy()

except Exception:
    return None
```

# ============================================================

# VISUAL FILTER

# ============================================================

def visual_reference_is_forbidden(path):
text = normalize_text(
str(path)
)

```
for term in FORBIDDEN_VISUAL_TERMS:

    if term in text:
        return True

return False
```

def image_is_real_and_valid(path):
if not path:
return False

```
path = Path(path)

if not path.exists():
    return False

if not file_is_large_enough(path):
    return False

if visual_reference_is_forbidden(path):
    return False

image = pil_open_image(path)

if image is not None:
    try:
        image.close()
    except Exception:
        pass

    return True

image = decode_image_with_ffmpeg(path)

if image is not None:
    try:
        image.close()
    except Exception:
        pass

    return True

return False
```

# ============================================================

# SOURCE DIRECTORY SCANNING

# ============================================================

def source_files_in_directory(directory):
directory = Path(directory)

```
if not directory.exists():
    return []

if not directory.is_dir():
    return []

results = []

try:

    for path in directory.rglob("*"):

        if len(results) >= MAX_SOURCE_SCAN_FILES:
            break

        if not path.is_file():
            continue

        try:
            size = path.stat().st_size
        except Exception:
            continue

        if size < MIN_IMAGE_BYTES:
            continue

        suffix = path.suffix.lower()

        if suffix:
            if suffix not in POSSIBLE_MEDIA_EXTENSIONS:
                continue

        results.append(path)

except Exception as exc:
    log(
        f"WARNING scanning {directory}: {exc}"
    )

return sorted(
    results,
    key=lambda p: str(p).lower(),
)
```

def populated_source_directories():
directories = []

```
if not SOURCE_DIR.exists():
    return directories

try:

    for child in SOURCE_DIR.iterdir():

        if not child.is_dir():
            continue

        files = source_files_in_directory(
            child
        )

        if files:
            directories.append(
                (child, files)
            )

except Exception as exc:
    log(
        f"WARNING scanning source directories: {exc}"
    )

return directories
```

# ============================================================

# DIRECTORY / STORY MATCHING

# ============================================================

def filename_story_match_score(path, story):
if not isinstance(story, dict):
return 0

```
path_text = normalize_text(
    path.name
)

full_text = normalize_text(
    story_to_text(story)
)

if not path_text:
    return 0

score = 0

identifiers = story_identifiers(story)

for identifier in identifiers:

    token = normalize_text(identifier)

    if token and token in path_text:
        score += 10

words = [
    word
    for word in full_text.split()
    if len(word) >= 5
]

for word in words:

    if word in path_text:
        score += 1

return score
```

def source_directory_matches_story(
directory,
story,
):
directory = Path(directory)

```
dir_text = normalize_text(
    directory.name
)

if not dir_text:
    return False

identifiers = story_identifiers(story)

for identifier in identifiers:

    token = normalize_text(
        identifier
    )

    if token and token in dir_text:
        return True

story_text = normalize_text(
    story_to_text(story)
)

story_words = {
    word
    for word in story_text.split()
    if len(word) >= 6
}

if not story_words:
    return False

matches = 0

for word in story_words:

    if word in dir_text:
        matches += 1

return matches >= 2
```

# ============================================================

# EXPLICIT IMAGE RESOLUTION

# ============================================================

def resolve_explicit_story_images(story):
references = extract_image_references(
story
)

```
resolved = []

for reference in references:

    path = resolve_local_reference(
        reference
    )

    if path is None:
        continue

    if not image_is_real_and_valid(path):
        continue

    resolved.append(path)

unique = []

seen = set()

for path in resolved:

    key = str(
        path.resolve()
    )

    if key in seen:
        continue

    seen.add(key)
    unique.append(path)

return unique
```

# ============================================================

# CONFIRMED STORY DIRECTORIES

# ============================================================

def confirmed_story_directories(
story,
explicit_images,
):
confirmed = []

```
seen = set()

# --------------------------------------------------------
# Directories containing explicit image references
# --------------------------------------------------------

for image in explicit_images:

    try:
        parent = image.parent.resolve()
    except Exception:
        continue

    try:
        parent.relative_to(
            SOURCE_DIR.resolve()
        )
    except Exception:
        continue

    key = str(parent)

    if key not in seen:
        seen.add(key)
        confirmed.append(parent)

# --------------------------------------------------------
# Directories whose name matches story ID
# --------------------------------------------------------

for directory, files in populated_source_directories():

    if source_directory_matches_story(
        directory,
        story,
    ):
        key = str(
            directory.resolve()
        )

        if key not in seen:
            seen.add(key)
            confirmed.append(
                directory.resolve()
            )

return confirmed
```

# ============================================================

# IMAGE NORMALIZATION

# ============================================================

def normalize_with_pil(
source_path,
destination_path,
):
try:

```
    with Image.open(source_path) as image:

        image.load()

        image = ImageOps.exif_transpose(
            image
        )

        if image.mode not in (
            "RGB",
            "RGBA",
        ):
            image = image.convert(
                "RGBA"
            )

        if image.mode == "RGBA":

            background = Image.new(
                "RGB",
                image.size,
                "white",
            )

            background.paste(
                image,
                mask=image.getchannel(
                    "A"
                ),
            )

            image = background

        else:
            image = image.convert(
                "RGB"
            )

        destination_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        image.save(
            destination_path,
            "JPEG",
            quality=94,
            optimize=True,
        )

    return True

except Exception:
    return False
```

def normalize_with_ffmpeg(
source_path,
destination_path,
):
if not ffmpeg_available():
return False

```
try:

    destination_path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    command = [
        "ffmpeg",
        "-y",
        "-loglevel",
        "error",
        "-i",
        str(source_path),
        "-frames:v",
        "1",
        "-q:v",
        "2",
        str(destination_path),
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )

    if result.returncode != 0:
        return False

    if not destination_path.exists():
        return False

    if destination_path.stat().st_size < MIN_IMAGE_BYTES:
        return False

    return image_is_decodable_by_pil(
        destination_path
    )

except Exception:
    return False
```

def normalize_any_real_image(
source_path,
):
source_path = Path(source_path)

```
try:
    relative_key = str(
        source_path.resolve()
    )
except Exception:
    relative_key = str(source_path)

digest = hashlib.sha1(
    relative_key.encode(
        "utf-8",
        errors="ignore",
    )
).hexdigest()[:16]

destination = (
    VIDEO_WORK_DIR
    / "normalized_images"
    / f"story_photo_{digest}.jpg"
)

if destination.exists():

    if image_is_real_and_valid(
        destination
    ):
        return destination

if normalize_with_pil(
    source_path,
    destination,
):
    return destination

try:
    if destination.exists():
        destination.unlink()
except Exception:
    pass

if normalize_with_ffmpeg(
    source_path,
    destination,
):
    return destination

return None
```

# ============================================================

# IMAGE SIGNATURE / DEDUPLICATION

# ============================================================

def image_signature(path):
try:

```
    with Image.open(path) as image:

        image = ImageOps.exif_transpose(
            image
        )

        image = image.convert(
            "RGB"
        )

        image.thumbnail(
            (64, 64)
        )

        data = image.tobytes()

        return hashlib.sha1(
            data
        ).hexdigest()

except Exception:
    return None
```

# ============================================================

# RECOVER STORY IMAGES

# ============================================================

def recover_story_images(story):
log("")
log("=" * 70)
log("RECOVERING REAL STORY PHOTOS")
log("=" * 70)

```
explicit_images = (
    resolve_explicit_story_images(
        story
    )
)

if explicit_images:
    log(
        f"Explicit valid images found: "
        f"{len(explicit_images)}"
    )
else:
    log(
        "Explicit valid images found: 0"
    )

confirmed_dirs = confirmed_story_directories(
    story,
    explicit_images,
)

all_source_dirs = (
    populated_source_directories()
)

selected_dirs = []

seen_dirs = set()

# --------------------------------------------------------
# First priority: confirmed directories
# --------------------------------------------------------

for directory in confirmed_dirs:

    key = str(
        directory.resolve()
    )

    if key not in seen_dirs:
        seen_dirs.add(key)
        selected_dirs.append(
            directory
        )

# --------------------------------------------------------
# Safe fallback:
#
# If exactly ONE populated story source directory exists,
# it is safe to use it because the news engine has produced
# one current selected story.
#
# This is the critical fix for:
# photo_02.jpg
# photo_03.jpg
# photo_04.jpg
# etc.
# --------------------------------------------------------

if not selected_dirs:

    if len(all_source_dirs) == 1:

        directory, files = (
            all_source_dirs[0]
        )

        log(
            "Exactly ONE populated source "
            "directory found."
        )

        log(
            f"Using confirmed current-run "
            f"source directory: {directory}"
        )

        selected_dirs.append(
            directory
        )

    elif len(all_source_dirs) > 1:

        log(
            f"Multiple populated source "
            f"directories found: "
            f"{len(all_source_dirs)}"
        )

        log(
            "Will NOT mix unrelated "
            "directories."
        )

# --------------------------------------------------------
# Collect candidate files
# --------------------------------------------------------

candidates = []

seen = set()

for directory in selected_dirs:

    files = source_files_in_directory(
        directory
    )

    log("")
    log(
        f"SOURCE DIRECTORY: {directory}"
    )

    log(
        f"Candidate files: {len(files)}"
    )

    for path in files:

        key = str(
            path.resolve()
        )

        if key in seen:
            continue

        seen.add(key)

        candidates.append(path)

# --------------------------------------------------------
# Explicit images are also candidates
# --------------------------------------------------------

for path in explicit_images:

    key = str(
        path.resolve()
    )

    if key in seen:
        continue

    seen.add(key)

    candidates.append(path)

# --------------------------------------------------------
# If multiple source directories exist and none was
# confirmed, use title-token matching only.
# --------------------------------------------------------

if (
    not candidates
    and len(all_source_dirs) > 1
):

    scored = []

    for directory, files in all_source_dirs:

        directory_score = 0

        if source_directory_matches_story(
            directory,
            story,
        ):
            directory_score += 100

        for path in files:

            score = (
                directory_score
                + filename_story_match_score(
                    path,
                    story,
                )
            )

            if score > 0:
                scored.append(
                    (
                        score,
                        path,
                    )
                )

    scored.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    for score, path in scored:

        if score <= 0:
            continue

        key = str(
            path.resolve()
        )

        if key in seen:
            continue

        seen.add(key)
        candidates.append(path)

        if len(candidates) >= MAX_IMAGES:
            break

# --------------------------------------------------------
# Detailed source report
# --------------------------------------------------------

log("")
log("CANDIDATE REAL IMAGE FILES:")

if not candidates:
    log("NONE")

for candidate in candidates:
    try:
        size = candidate.stat().st_size
    except Exception:
        size = 0

    log(
        f"  {candidate} "
        f"({size} bytes)"
    )

# --------------------------------------------------------
# Normalize + validate + deduplicate
# --------------------------------------------------------

normalized = []

signatures = set()

for candidate in candidates:

    log("")
    log(
        f"CHECKING IMAGE: {candidate}"
    )

    if visual_reference_is_forbidden(
        candidate
    ):
        log(
            "REJECTED: forbidden visual "
            "reference"
        )
        continue

    if not file_is_large_enough(
        candidate
    ):
        log(
            "REJECTED: file too small"
        )
        continue

    normalized_path = (
        normalize_any_real_image(
            candidate
        )
    )

    if normalized_path is None:

        log(
            "REJECTED: could not decode "
            "actual image bytes"
        )

        continue

    signature = image_signature(
        normalized_path
    )

    if signature is None:

        log(
            "REJECTED: no visual signature"
        )

        continue

    if signature in signatures:

        log(
            "REJECTED: duplicate visual"
        )

        continue

    signatures.add(signature)

    normalized.append(
        normalized_path
    )

    log(
        f"ACCEPTED REAL PHOTO: "
        f"{normalized_path}"
    )

    if len(normalized) >= MAX_IMAGES:
        break

# --------------------------------------------------------
# Final result
# --------------------------------------------------------

log("")
log("=" * 70)
log(
    f"REAL STORY PHOTOS ACCEPTED: "
    f"{len(normalized)}"
)
log("=" * 70)

for index, image in enumerate(
    normalized,
    start=1,
):
    log(
        f"{index}. {image}"
    )

if not normalized:

    log("")
    log(
        "ERROR: No valid real story "
        "images found."
    )

    return []

return normalized
```

# ============================================================

# STORY SELECTION

# ============================================================

def story_priority_score(story):
score = 0

```
if not isinstance(story, dict):
    return -999

text = normalize_text(
    story_to_text(story)
)

if not text:
    return -999

# Prefer current / breaking developments
priority_terms = [
    "today",
    "breaking",
    "latest",
    "president",
    "president william ruto",
    "state house",
    "government",
    "county",
    "governor",
    "minister",
    "ministry",
    "police",
    "dci",
    "kenya red cross",
    "ndma",
    "kmd",
    "ke n ha",
    "kenha",
    "kenya power",
]

for term in priority_terms:
    if term in text:
        score += 2

if story.get("published"):
    score += 1

if story.get("published_at"):
    score += 1

if story.get("source"):
    score += 1

return score
```

def select_best_story(stories):
allowed = [
story
for story in stories
if not story_is_forbidden(story)
]

```
if not allowed:
    return None

scored = []

for story in allowed:

    score = story_priority_score(
        story
    )

    scored.append(
        (
            score,
            story,
        )
    )

scored.sort(
    key=lambda item: item[0],
    reverse=True,
)

return scored[0][1]
```

# ============================================================

# SCRIPT HANDLING

# ============================================================

def extract_script_list(payload):
if payload is None:
return []

```
if isinstance(payload, list):
    return payload

if isinstance(payload, dict):

    for key in [
        "scripts",
        "items",
        "stories",
        "data",
    ]:

        value = payload.get(key)

        if isinstance(value, list):
            return value

    return [payload]

return []
```

def script_matches_story(script, story):
if not isinstance(script, dict):
return False

```
story_id_values = set(
    str(value)
    for value in story_identifiers(
        story
    )
)

for key in [
    "id",
    "story_id",
    "storyId",
    "article_id",
    "articleId",
    "news_id",
    "newsId",
    "hash",
    "story_hash",
    "article_hash",
    "uuid",
    "guid",
    "slug",
]:

    value = script.get(key)

    if value is None:
        continue

    if str(value) in story_id_values:
        return True

story_title = normalize_text(
    story.get("title")
    or story.get("headline")
    or ""
)

script_title = normalize_text(
    script.get("title")
    or script.get("headline")
    or ""
)

if story_title and script_title:

    if (
        story_title == script_title
        or story_title in script_title
        or script_title in story_title
    ):
        return True

return False
```

def find_script_for_story(
script_payload,
story,
):
scripts = extract_script_list(
script_payload
)

```
for script in scripts:

    if script_matches_story(
        script,
        story,
    ):
        return script

if scripts:
    return scripts[0]

return {}
```

# ============================================================

# REPLACE IMAGE REFERENCES

# ============================================================

def replace_image_references(
payload,
normalized_images,
):
if not normalized_images:
return payload

```
counter = {
    "value": 0
}

def next_image():
    index = counter["value"]

    image = normalized_images[
        index % len(normalized_images)
    ]

    counter["value"] += 1

    return str(
        image.relative_to(
            BASE_DIR
        )
    ).replace(
        "\\",
        "/",
    )

def walk(obj):

    if isinstance(obj, dict):

        result = {}

        for key, value in obj.items():

            key_lower = str(key).lower()

            if key_lower in IMAGE_FIELD_NAMES:

                if isinstance(value, str):

                    if looks_like_image_reference(
                        value
                    ):
                        result[key] = (
                            next_image()
                        )
                    else:
                        result[key] = value

                elif isinstance(value, list):

                    new_list = []

                    for item in value:

                        if isinstance(
                            item,
                            str,
                        ) and looks_like_image_reference(
                            item
                        ):
                            new_list.append(
                                next_image()
                            )

                        else:
                            new_list.append(
                                walk(item)
                            )

                    result[key] = new_list

                else:
                    result[key] = walk(value)

            else:
                result[key] = walk(value)

        return result

    if isinstance(obj, list):

        return [
            walk(item)
            for item in obj
        ]

    return obj

return walk(payload)
```

# ============================================================

# ATTACH CANONICAL IMAGE FIELDS

# ============================================================

def attach_canonical_images(
payload,
normalized_images,
):
relative_paths = []

```
for image in normalized_images:

    try:
        relative = image.relative_to(
            BASE_DIR
        )
    except Exception:
        relative = image

    relative_paths.append(
        str(relative).replace(
            "\\",
            "/",
        )
    )

if isinstance(payload, dict):

    payload = dict(payload)

    payload["images"] = list(
        relative_paths
    )

    payload["image_paths"] = list(
        relative_paths
    )

    payload["local_images"] = list(
        relative_paths
    )

    payload["local_image_paths"] = list(
        relative_paths
    )

    payload["photos"] = list(
        relative_paths
    )

    payload["photo_paths"] = list(
        relative_paths
    )

return payload
```

# ============================================================

# NARRATION TEXT

# ============================================================

def narration_text_from_story(
story,
script,
):
parts = []

```
if isinstance(script, dict):

    for key in [
        "narration",
        "voiceover",
        "voice_over",
        "script",
        "text",
        "body",
        "summary",
    ]:

        value = script.get(key)

        if isinstance(value, str):
            value = value.strip()

            if value:
                parts.append(value)

                break

if not parts:

    title = (
        story.get("title")
        or story.get("headline")
        or ""
    )

    summary = (
        story.get("summary")
        or story.get("description")
        or story.get("content")
        or ""
    )

    if title:
        parts.append(
            str(title).strip()
        )

    if summary:
        parts.append(
            str(summary).strip()
        )

text = " ".join(parts)

text = re.sub(
    r"\s+",
    " ",
    text,
).strip()

return text
```

# ============================================================

# NARRATION

# ============================================================

def generate_narration(
story,
script,
):
text = narration_text_from_story(
story,
script,
)

```
if not text:
    raise RuntimeError(
        "Narration text is empty."
    )

log("")
log("=" * 70)
log("GENERATING NARRATION")
log("=" * 70)

log(
    f"Narration characters: "
    f"{len(text)}"
)

try:

    if NARRATION_FILE.exists():
        try:
            NARRATION_FILE.unlink()
        except Exception:
            pass

    tts = gTTS(
        text=text,
        lang="en",
        slow=False,
    )

    tts.save(
        str(NARRATION_FILE)
    )

except Exception as exc:

    raise RuntimeError(
        f"gTTS narration failed: {exc}"
    )

if not NARRATION_FILE.exists():
    raise RuntimeError(
        "Narration file was not created."
    )

if (
    NARRATION_FILE.stat().st_size
    < MIN_AUDIO_BYTES
):
    raise RuntimeError(
        "Narration file is too small."
    )

log(
    f"Narration created: "
    f"{NARRATION_FILE}"
)

return True
```

# ============================================================

# SELECTED STORY PREPARATION

# ============================================================

def prepare_selected_files(
story,
script,
normalized_images,
):
selected_story = dict(story)

```
selected_story = (
    replace_image_references(
        selected_story,
        normalized_images,
    )
)

selected_story = (
    attach_canonical_images(
        selected_story,
        normalized_images,
    )
)

selected_story["selected_for_video"] = True

selected_story["real_image_count"] = (
    len(normalized_images)
)

selected_script = (
    dict(script)
    if isinstance(script, dict)
    else {}
)

selected_script = (
    replace_image_references(
        selected_script,
        normalized_images,
    )
)

selected_script = (
    attach_canonical_images(
        selected_script,
        normalized_images,
    )
)

selected_script["selected_for_video"] = True

selected_script["real_image_count"] = (
    len(normalized_images)
)

safe_write_json(
    SELECTED_STORY_FILE,
    selected_story,
)

safe_write_json(
    SELECTED_SCRIPT_FILE,
    selected_script,
)

log("")
log(
    f"Selected story written: "
    f"{SELECTED_STORY_FILE}"
)

log(
    f"Selected script written: "
    f"{SELECTED_SCRIPT_FILE}"
)

return (
    selected_story,
    selected_script,
)
```

# ============================================================

# VIDEO VALIDATION

# ============================================================

def validate_video(path):
path = Path(path)

```
log("")
log("=" * 70)
log("VALIDATING FINAL MP4")
log("=" * 70)

if not path.exists():

    log(
        f"ERROR: Final video does not exist: "
        f"{path}"
    )

    return False

size = path.stat().st_size

log(
    f"Video size: {size} bytes"
)

if size < MIN_VIDEO_BYTES:

    log(
        "ERROR: Video is too small."
    )

    return False

try:

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration,size",
        "-of",
        "default=noprint_wrappers=1",
        str(path),
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:

        log(
            "ERROR: ffprobe validation failed."
        )

        log(
            result.stderr
        )

        return False

    log(
        result.stdout
    )

except Exception as exc:

    log(
        f"WARNING: ffprobe unavailable: {exc}"
    )

return True
```

# ============================================================

# SOURCE FAILURE REPORT

# ============================================================

def print_source_contents():
log("")
log("=" * 70)
log("ASSETS/SOURCE CONTENT")
log("=" * 70)

```
if not SOURCE_DIR.exists():
    log(
        "Source directory does not exist."
    )
    return

found = False

try:

    for path in SOURCE_DIR.rglob("*"):

        if not path.is_file():
            continue

        found = True

        try:
            size = path.stat().st_size
        except Exception:
            size = 0

        log(
            f"{path} {size} bytes"
        )

except Exception as exc:

    log(
        f"Could not list source content: {exc}"
    )

if not found:
    log(
        "No source files found."
    )
```

# ============================================================

# MAIN

# ============================================================

def main():

```
start_time = time.time()

log("")
log("=" * 70)
log("RIFT VALLEY WATCH")
log("MAIN ORCHESTRATOR")
log("RVW_MAIN_V38_REAL_IMAGE_BYTE_RECOVERY")
log("=" * 70)

ensure_directories()

clean_video_work_directory()

# --------------------------------------------------------
# 1. RUN NEWS ENGINE
# --------------------------------------------------------

try:

    run_python_script(
        NEWS_ENGINE,
        "RUNNING NEWS ENGINE",
    )

except Exception as exc:

    log("")
    log(
        f"ERROR: News engine failed: {exc}"
    )

    traceback.print_exc()

    sys.exit(1)

# --------------------------------------------------------
# 2. LOAD STORY JSON
# --------------------------------------------------------

log("")
log("=" * 70)
log("LOADING STORY DATA")
log("=" * 70)

story_payload = safe_read_json(
    STORY_FILE
)

if story_payload is None:

    log(
        "ERROR: story.json is missing "
        "or invalid."
    )

    sys.exit(1)

stories = extract_story_list(
    story_payload
)

log(
    f"Stories loaded: {len(stories)}"
)

if not stories:

    log(
        "ERROR: No stories found."
    )

    sys.exit(1)

# --------------------------------------------------------
# 3. SELECT ONE STORY
# --------------------------------------------------------

selected_story = select_best_story(
    stories
)

if selected_story is None:

    log(
        "ERROR: No allowed story found."
    )

    sys.exit(1)

title = (
    selected_story.get("title")
    or selected_story.get("headline")
    or "Untitled story"
)

log("")
log("=" * 70)
log("SELECTED STORY")
log("=" * 70)
log(title)

if story_is_forbidden(
    selected_story
):

    log(
        "ERROR: Selected story is forbidden."
    )

    sys.exit(1)

# --------------------------------------------------------
# 4. RECOVER REAL PHOTOS
# --------------------------------------------------------

normalized_images = (
    recover_story_images(
        selected_story
    )
)

if not normalized_images:

    log("")
    print_source_contents()

    log("")
    log(
        "ERROR: No real story images "
        "were recovered."
    )

    sys.exit(1)

# --------------------------------------------------------
# 5. LOAD SCRIPT
# --------------------------------------------------------

script_payload = safe_read_json(
    SCRIPT_FILE
)

selected_script = find_script_for_story(
    script_payload,
    selected_story,
)

# --------------------------------------------------------
# 6. WRITE SELECTED FILES
# --------------------------------------------------------

(
    selected_story,
    selected_script,
) = prepare_selected_files(
    selected_story,
    selected_script,
    normalized_images,
)

# --------------------------------------------------------
# 7. GENERATE NARRATION
# --------------------------------------------------------

try:

    generate_narration(
        selected_story,
        selected_script,
    )

except Exception as exc:

    log("")
    log(
        f"ERROR: Narration generation failed: {exc}"
    )

    traceback.print_exc()

    sys.exit(1)

# --------------------------------------------------------
# 8. RUN VIDEO RENDERER
# --------------------------------------------------------

try:

    run_python_script(
        RENDERER_FILE,
        "RUNNING VIDEO RENDERER",
    )

except Exception as exc:

    log("")
    log(
        f"ERROR: Video renderer failed: {exc}"
    )

    traceback.print_exc()

    sys.exit(1)

# --------------------------------------------------------
# 9. VALIDATE FINAL MP4
# --------------------------------------------------------

if not validate_video(
    FINAL_VIDEO
):

    log("")
    log(
        "ERROR: Final MP4 validation failed."
    )

    sys.exit(1)

# --------------------------------------------------------
# 10. FINAL REPORT
# --------------------------------------------------------

elapsed = (
    time.time()
    - start_time
)

log("")
log("=" * 70)
log("RIFT VALLEY WATCH COMPLETE")
log("=" * 70)

log(
    f"Selected story: {title}"
)

log(
    f"Real photographs used: "
    f"{len(normalized_images)}"
)

log(
    f"Narration: {NARRATION_FILE}"
)

log(
    f"Final MP4: {FINAL_VIDEO}"
)

try:
    size = FINAL_VIDEO.stat().st_size

    log(
        f"Final MP4 size: {size} bytes"
    )

except Exception:
    pass

log(
    f"Elapsed time: {elapsed:.1f} seconds"
)

log("")
log(
    "SUCCESS: REAL PHOTO VIDEO GENERATED."
)
```

# ============================================================

# ENTRY POINT

# ============================================================

if **name** == "**main**":
try:
main()

```
except KeyboardInterrupt:

    log("")
    log(
        "Process interrupted."
    )

    sys.exit(130)

except Exception as exc:

    log("")
    log("=" * 70)
    log("FATAL ERROR")
    log("=" * 70)

    log(
        str(exc)
    )

    traceback.print_exc()

    sys.exit(1)
```
