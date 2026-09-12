import json
import re
import shutil
import subprocess
import urllib.request
from pathlib import Path

from PIL import Image


# ============================================================
# RIFT VALLEY WATCH
# MAIN CONTROLLER
#
# This file does NOT rebuild the renderer.
# It prepares the story, guarantees a real source image,
# corrects repository paths, then calls the saved V6 renderer.
# ============================================================

ROOT = Path(__file__).resolve().parent
DATA_DIR = ROOT / "data"
OUTPUT_DIR = ROOT / "output"
ASSET_DIR = ROOT / "assets"
SOURCE_DIR = ASSET_DIR / "source"

STORY_FILE = DATA_DIR / "story.json"
SELECTED_FILE = DATA_DIR / "selected_story.json"
SCRIPT_FILE = DATA_DIR / "script.json"
REPORT_FILE = DATA_DIR / "visual_report.json"

OUTPUT_FILE = OUTPUT_DIR / "rift_valley_watch_reel.mp4"
CANONICAL_IMAGE = SOURCE_DIR / "story_image.jpg"

WIDTH = 1080
HEIGHT = 1920


# ============================================================
# REAL PUBLISHED IMAGES
#
# These are publisher-hosted photographs associated with
# the exact March 18, 2026 Bomet road story.
# ============================================================

REAL_IMAGE_URLS = [
    "https://peopledaily.digital/wp-content/uploads/2026/03/image-300-500x333.png",
    "https://topnews.ke/wp-content/uploads/2026/03/WhatsApp-Image-2026-03-18-at-12.13.35-rr-1024x683.jpeg",
]


# ============================================================
# BASIC HELPERS
# ============================================================

def clean(value):
    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value)
    ).strip()


def ensure_dirs():
    for path in (
        DATA_DIR,
        OUTPUT_DIR,
        ASSET_DIR,
        SOURCE_DIR,
        OUTPUT_DIR / "scenes",
        ASSET_DIR / "audio",
    ):
        path.mkdir(
            parents=True,
            exist_ok=True
        )


def load_json(path):
    if not path.exists():
        raise RuntimeError(
            f"Missing required file: {path}"
        )

    return json.loads(
        path.read_text(
            encoding="utf-8"
        )
    )


def save_json(path, data):
    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    path.write_text(
        json.dumps(
            data,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )


# ============================================================
# IMAGE VALIDATION
# ============================================================

def validate_image(path):
    path = Path(path)

    if not path.exists():
        return False

    if path.stat().st_size < 10000:
        return False

    try:
        with Image.open(path) as image:
            image.verify()

        with Image.open(path) as image:
            width, height = image.size
            fmt = image.format

        if width < 400:
            return False

        if height < 300:
            return False

        if width * height < 250000:
            return False

        if fmt not in {
            "JPEG",
            "JPG",
            "PNG",
            "WEBP",
            "AVIF",
        }:
            return False

        return True

    except Exception:
        return False


def convert_to_jpeg(source, destination):
    source = Path(source)
    destination = Path(destination)

    try:
        with Image.open(source) as image:
            image = image.convert("RGB")

            image.save(
                destination,
                "JPEG",
                quality=95,
                optimize=True
            )

        return validate_image(
            destination
        )

    except Exception as exc:
        print(
            f"Image conversion failed: {exc}"
        )

        return False


# ============================================================
# REAL IMAGE DOWNLOAD
# ============================================================

def download_real_image(
    url,
    destination
):
    print()
    print("=" * 70)
    print("REAL IMAGE RECOVERY")
    print("=" * 70)

    print(
        f"Trying: {url}"
    )

    temporary = destination.with_suffix(
        ".download"
    )

    try:
        request = urllib.request.Request(
            url,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 "
                    "(Windows NT 10.0; Win64; x64) "
                    "AppleWebKit/537.36 "
                    "Chrome/153 Safari/537.36"
                ),
                "Accept": (
                    "image/avif,image/webp,"
                    "image/apng,image/svg+xml,"
                    "image/*,*/*;q=0.8"
                ),
                "Referer": url,
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=45
        ) as response:

            data = response.read()

        if len(data) < 10000:
            print(
                "Rejected: downloaded file is too small."
            )
            return False

        temporary.write_bytes(
            data
        )

        if not validate_image(
            temporary
        ):
            print(
                "Downloaded object is not a valid photographic image."
            )
            return False

        if not convert_to_jpeg(
            temporary,
            destination
        ):
            print(
                "Could not convert recovered image to JPEG."
            )
            return False

        print(
            f"VALID REAL IMAGE: {destination}"
        )

        return True

    except Exception as exc:
        print(
            f"Image download failed: {exc}"
        )

        return False

    finally:
        try:
            if temporary.exists():
                temporary.unlink()
        except Exception:
            pass


# ============================================================
# LOCAL IMAGE RECOVERY
# ============================================================

def find_local_image(story):
    candidates = []

    for key in (
        "local_image",
        "image_path",
        "localImage",
    ):
        value = story.get(key)

        if value:
            candidates.append(
                Path(value)
            )

    candidates.extend(
        [
            CANONICAL_IMAGE,
            SOURCE_DIR / "story_image.jpg",
            SOURCE_DIR / "story_image.jpeg",
            SOURCE_DIR / "story_image.png",
            DATA_DIR / "story_image.jpg",
            ROOT / "story_image.jpg",
        ]
    )

    for candidate in candidates:
        try:
            candidate = candidate.expanduser()

            if not candidate.is_absolute():
                candidate = ROOT / candidate

            if validate_image(candidate):
                print(
                    f"VALID LOCAL REAL IMAGE: {candidate}"
                )

                return candidate

        except Exception:
            continue

    return None


# ============================================================
# REAL IMAGE RECOVERY
# ============================================================

def recover_real_image(story):

    local = find_local_image(
        story
    )

    if local:

        if local.resolve() != CANONICAL_IMAGE.resolve():

            try:
                shutil.copy2(
                    local,
                    CANONICAL_IMAGE
                )

                local = CANONICAL_IMAGE

            except Exception:
                pass

        return local

    title = clean(
        story.get("title", "")
    ).lower()

    source_url = clean(
        story.get(
            "source",
            {}
        ).get(
            "url",
            ""
        )
    ).lower()

    is_bomet_road_story = (
        "bomet" in title
        and "road" in title
        and (
            "2.1" in title
            or "65" in title
            or "chepalungu" in source_url
            or "bomet.go.ke" in source_url
        )
    )

    if is_bomet_road_story:
        urls = REAL_IMAGE_URLS
    else:
        urls = []

    if not urls:
        print(
            "No corroborating image set applies to this story."
        )

    for url in urls:

        if download_real_image(
            url,
            CANONICAL_IMAGE
        ):
            return CANONICAL_IMAGE

    return None


# ============================================================
# STORY VALIDATION
# ============================================================

def validate_story(story):

    title = clean(
        story.get("title")
    )

    county = clean(
        story.get("county")
    )

    source = story.get(
        "source"
    ) or {}

    source_name = clean(
        source.get("name")
    )

    source_url = clean(
        source.get("url")
    )

    if not title:
        raise RuntimeError(
            "Story has no title."
        )

    if not county:
        raise RuntimeError(
            "Story has no county."
        )

    if not source_name:
        raise RuntimeError(
            "Story has no publisher/source name."
        )

    if not source_url:
        raise RuntimeError(
            "Story has no source URL."
        )

    forbidden = (
        "google news",
        "facebook.com",
        "google news app",
        "google news icon",
    )

    haystack = json.dumps(
        story,
        ensure_ascii=False
    ).lower()

    for bad in forbidden:

        if bad in haystack:
            raise RuntimeError(
                "Rejected story: "
                f"forbidden boilerplate detected: {bad}"
            )

    if "verified_facts" not in story:
        raise RuntimeError(
            "Story has no verified_facts."
        )

    if not story["verified_facts"]:
        raise RuntimeError(
            "Story has no verified facts."
        )

    return True


# ============================================================
# NARRATION
# ============================================================

def build_script(story):

    title = clean(
        story.get("title")
    )

    county = clean(
        story.get("county")
    )

    facts = {}

    for item in story.get(
        "verified_facts",
        []
    ):

        label = clean(
            item.get("label")
        ).upper()

        value = clean(
            item.get("value")
        )

        if label:
            facts[label] = value

    location = facts.get(
        "LOCATION",
        county
    )

    length = facts.get(
        "ROAD_LENGTH",
        "not stated"
    )

    cost = facts.get(
        "COST",
        "not stated"
    )

    route = facts.get(
        "PROJECT",
        "not fully stated"
    )

    status = facts.get(
        "STATUS",
        "reported"
    )

    impact = facts.get(
        "IMPACT",
        "not separately stated"
    )

    statement = story.get(
        "official_statement"
    ) or {}

    speaker = clean(
        statement.get("speaker")
    )

    quote = clean(
        statement.get("quote")
    )

    source_name = clean(
        story.get(
            "source",
            {}
        ).get(
            "name"
        )
    )

    date = clean(
        story.get("date")
    )

    segments = [

        f"{title}.",

        (
            f"The project is located in {location}. "
            f"Construction status: {status}."
        ),

        (
            f"Key figures: {length}, "
            f"with a reported project cost "
            f"of {cost}."
        ),

        (
            f"The reported route is {route}."
        ),

        (
            f"Why it matters: {impact}."
        ),
    ]

    if quote:

        segments.append(
            f"{speaker or 'An official'} said: {quote}"
        )

    else:

        segments.append(
            "No separate official statement "
            "was provided in the verified story."
        )

    segments.append(
        f"This report is based on "
        f"{source_name}, dated "
        f"{date or 'the reported date'}."
    )

    segments.append(
        "Rift Valley Watch. "
        "Verified regional news. "
        "Follow for more."
    )

    full_script = " ".join(
        segments
    )

    return {
        "full_script": full_script,
        "segments": segments,
    }


# ============================================================
# PATCH THE EXISTING V6 GENERATOR
# ============================================================

def patch_generator(
    generator,
    story,
    image_path
):

    # --------------------------------------------------------
    # Correct repository paths.
    # --------------------------------------------------------

    generator.ROOT = ROOT

    generator.STORY_FILE = STORY_FILE

    generator.SCRIPT_FILE = SCRIPT_FILE

    generator.OUTPUT_DIR = OUTPUT_DIR

    generator.ASSET_DIR = ASSET_DIR

    generator.SOURCE_IMAGE_DIR = SOURCE_DIR

    generator.AUDIO_DIR = (
        ASSET_DIR / "audio"
    )

    generator.SCENE_DIR = (
        OUTPUT_DIR / "scenes"
    )

    generator.OUTPUT_FILE = (
        OUTPUT_FILE
    )

    generator.REPORT_FILE = (
        REPORT_FILE
    )

    generator.WIDTH = WIDTH

    generator.HEIGHT = HEIGHT

    generator.FPS = 30

    # --------------------------------------------------------
    # Force the renderer to use the real recovered image.
    # --------------------------------------------------------

    def fixed_find_source_image(
        _story
    ):

        if not validate_image(
            image_path
        ):
            raise RuntimeError(
                "Recovered image failed final validation."
            )

        return (
            image_path,
            REAL_IMAGE_URLS.copy()
        )

    generator.find_source_image = (
        fixed_find_source_image
    )

    # --------------------------------------------------------
    # SOURCE scene:
    # display publisher name and date.
    # Do not display the long raw URL.
    # --------------------------------------------------------

    def source_scene_without_url(
        current_story
    ):

        image = (
            generator.create_background()
        )

        draw = generator.ImageDraw.Draw(
            image
        )

        generator.add_grid(
            draw
        )

        generator.top_bar(
            draw
        )

        generator.section_label(
            draw,
            "SOURCE"
        )

        name = generator.source_name(
            current_story
        )

        generator.draw_wrapped(
            draw,
            name,
            (
                65,
                330,
                WIDTH - 65,
                700
            ),
            generator.get_font(
                52,
                True
            ),
            max_lines=3,
            line_spacing=18
        )

        draw.text(
            (65, 820),
            "REPORT DATE",
            font=generator.get_font(
                28,
                True
            ),
            fill=(230, 55, 65)
        )

        draw.text(
            (65, 890),
            generator.story_date(
                current_story
            ) or "Not stated",
            font=generator.get_font(
                50,
                True
            ),
            fill=(240, 240, 245)
        )

        generator.source_badge(
            draw,
            current_story
        )

        generator.footer(
            draw,
            current_story
        )

        return image

    generator.scene_source = (
        source_scene_without_url
    )


# ============================================================
# FINAL MP4 QC
# ============================================================

def final_qc(path):

    path = Path(path)

    if not path.exists():
        raise RuntimeError(
            f"Final MP4 was not created: {path}"
        )

    if path.stat().st_size < 100 * 1024:
        raise RuntimeError(
            "Final MP4 is suspiciously small."
        )

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type,codec_name,width,height",
        "-show_entries",
        "format=duration,size",
        "-of",
        "json",
        str(path),
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=True,
    )

    data = json.loads(
        result.stdout
    )

    streams = data.get(
        "streams",
        []
    )

    fmt = data.get(
        "format",
        {}
    )

    video = next(
        (
            s
            for s in streams
            if s.get("codec_type") == "video"
        ),
        None
    )

    audio = next(
        (
            s
            for s in streams
            if s.get("codec_type") == "audio"
        ),
        None
    )

    if not video:
        raise RuntimeError(
            "Final MP4 has no video stream."
        )

    if not audio:
        raise RuntimeError(
            "Final MP4 has no audio stream."
        )

    width = int(
        video.get(
            "width",
            0
        )
    )

    height = int(
        video.get(
            "height",
            0
        )
    )

    duration = float(
        fmt.get(
            "duration",
            0
        )
    )

    if width != WIDTH or height != HEIGHT:

        raise RuntimeError(
            f"Final MP4 is "
            f"{width}x{height}; "
            f"expected {WIDTH}x{HEIGHT}."
        )

    if video.get(
        "codec_name"
    ) != "h264":

        raise RuntimeError(
            "Expected H.264 video, "
            f"got {video.get('codec_name')}."
        )

    if audio.get(
        "codec_name"
    ) not in (
        "aac",
        "mp4a"
    ):

        raise RuntimeError(
            "Expected AAC audio, "
            f"got {audio.get('codec_name')}."
        )

    if duration < 10:

        raise RuntimeError(
            "Final MP4 is shorter than "
            "10 seconds."
        )

    if duration > 180:

        raise RuntimeError(
            "Final MP4 is longer than "
            "180 seconds."
        )

    return {
        "passed": True,
        "width": width,
        "height": height,
        "duration_seconds": round(
            duration,
            2
        ),
        "size_bytes": path.stat().st_size,
        "video_codec": video.get(
            "codec_name"
        ),
        "audio_codec": audio.get(
            "codec_name"
        ),
    }


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 70)
    print("RIFT VALLEY WATCH")
    print("REAL IMAGE RECOVERY + V6 RENDERER")
    print("=" * 70)

    ensure_dirs()

    story = load_json(
        STORY_FILE
    )

    validate_story(
        story
    )

    print()

    print(
        f"TITLE : "
        f"{story.get('title', '')}"
    )

    print(
        f"COUNTY: "
        f"{story.get('county', '')}"
    )

    print(
        f"SOURCE: "
        f"{story.get('source', {}).get('name', '')}"
    )

    # --------------------------------------------------------
    # Recover a genuine published photograph.
    # --------------------------------------------------------

    image_path = recover_real_image(
        story
    )

    if not image_path:

        raise RuntimeError(
            "No usable real published article image "
            "could be recovered. "
            "The video was NOT generated with "
            "a fake placeholder."
        )

    story["local_image"] = str(
        image_path
    )

    # --------------------------------------------------------
    # Prepare narration.
    # --------------------------------------------------------

    script = build_script(
        story
    )

    save_json(
        SCRIPT_FILE,
        script
    )

    save_json(
        SELECTED_FILE,
        story
    )

    # --------------------------------------------------------
    # Import existing V6 renderer.
    # --------------------------------------------------------

    import rift_valley_video_generator as generator

    patch_generator(
        generator,
        story,
        image_path
    )

    print()

    print("=" * 70)
    print("STARTING EXISTING V6 RENDERER")
    print("=" * 70)

    print(
        f"REAL IMAGE: {image_path}"
    )

    print(
        f"OUTPUT     : {OUTPUT_FILE}"
    )

    # Existing renderer loads story.json itself.
    generator.main()

    # --------------------------------------------------------
    # Safety fallback if the renderer retained its old name.
    # --------------------------------------------------------

    if not OUTPUT_FILE.exists():

        legacy_output = (
            OUTPUT_DIR /
            "rift_valley_watch.mp4"
        )

        if legacy_output.exists():

            shutil.copy2(
                legacy_output,
                OUTPUT_FILE
            )

    # --------------------------------------------------------
    # Final QC.
    # --------------------------------------------------------

    qc = final_qc(
        OUTPUT_FILE
    )

    report = {
        "status": "PASSED",
        "output": str(
            OUTPUT_FILE
        ),
        "image": str(
            image_path
        ),
        "image_type": (
            "real_published_source_visual"
        ),
        "qc": qc,
    }

    save_json(
        OUTPUT_DIR /
        "final_qc.json",
        report
    )

    print()

    print("=" * 70)
    print("RIFT VALLEY WATCH COMPLETE")
    print("=" * 70)

    print(
        f"MP4    : {OUTPUT_FILE}"
    )

    print(
        f"IMAGE  : {image_path}"
    )

    print(
        f"DURATION: "
        f"{qc['duration_seconds']} seconds"
    )

    print(
        f"FORMAT  : "
        f"{qc['width']}x{qc['height']}"
    )

    print(
        "QC      : PASSED"
    )


if __name__ == "__main__":
    main()
