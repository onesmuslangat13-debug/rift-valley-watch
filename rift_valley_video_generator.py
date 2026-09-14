from pathlib import Path
import hashlib
import json
import re
import shutil
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont


BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
SOURCE_DIR = BASE_DIR / "assets" / "source"
WORK_DIR = BASE_DIR / "assets" / "video_work"
AUDIO_DIR = BASE_DIR / "audio"
OUTPUT_DIR = BASE_DIR / "output"

STORY_FILE = DATA_DIR / "selected_story.json"
SCRIPT_FILE = DATA_DIR / "selected_script.json"
AUDIO_FILE = AUDIO_DIR / "narration.mp3"
FINAL_FILE = OUTPUT_DIR / "rift_valley_watch_reel.mp4"

WIDTH = 1080
HEIGHT = 1920
FPS = 30

FORBIDDEN_TERMS = (
    "citizen",
    "ctv",
    "worldcup",
    "world_cup",
    "avatar",
    "placeholder",
    "default_image",
    "default-image",
    "profile_picture",
    "profile-picture",
    "dummy",
    "generic",
    "logo",
    "icon",
)


def run(command, label):
    print()
    print("RUNNING:", label)

    result = subprocess.run(
        command,
        cwd=str(BASE_DIR),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    print(result.stdout)

    if result.returncode != 0:
        raise RuntimeError(
            f"{label} failed with exit code {result.returncode}"
        )


def load_json(path):
    if not path.exists():
        raise RuntimeError(f"Missing JSON file: {path}")

    with path.open("r", encoding="utf-8") as file:
        return json.load(file)


def text(value, fallback=""):
    if value is None:
        return fallback

    if isinstance(value, (dict, list)):
        return fallback

    value = re.sub(r"\s+", " ", str(value)).strip()
    return value or fallback


def get_story(data):
    if isinstance(data, dict) and isinstance(data.get("story"), dict):
        return data["story"]

    if isinstance(data, dict) and isinstance(data.get("stories"), list):
        if not data["stories"]:
            raise RuntimeError("Selected story list is empty")
        return data["stories"][0]

    if isinstance(data, dict):
        return data

    raise RuntimeError("Selected story is not an object")


def font(size, bold=False):
    names = []

    if bold:
        names.extend(
            [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf",
                "C:/Windows/Fonts/arialbd.ttf",
            ]
        )
    else:
        names.extend(
            [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf",
                "C:/Windows/Fonts/arial.ttf",
            ]
        )

    for name in names:
        path = Path(name)

        if path.exists():
            try:
                return ImageFont.truetype(str(path), size)
            except Exception:
                pass

    return ImageFont.load_default()


def wrap(draw, value, selected_font, max_width, maximum=5):
    words = text(value).split()
    lines = []
    current = ""

    for word in words:
        trial = f"{current} {word}".strip()
        box = draw.textbbox((0, 0), trial, font=selected_font)

        if box[2] <= max_width:
            current = trial
        else:
            if current:
                lines.append(current)

            current = word

            if len(lines) >= maximum:
                break

    if current and len(lines) < maximum:
        lines.append(current)

    return lines[:maximum]


def draw_wrapped(draw, value, x, y, max_width, selected_font, fill, gap=10):
    lines = wrap(
        draw,
        value,
        selected_font,
        max_width,
        maximum=5,
    )

    height = selected_font.getbbox("Ag")[3]

    for index, line in enumerate(lines):
        draw.text(
            (x, y + index * (height + gap)),
            line,
            font=selected_font,
            fill=fill,
        )

    return y + len(lines) * (height + gap)


def valid_image(path):
    if not path.exists():
        return False

    if not path.is_file():
        return False

    if path.stat().st_size < 10000:
        return False

    lowered = str(path).lower()

    for term in FORBIDDEN_TERMS:
        if term in lowered:
            return False

    try:
        with Image.open(path) as image:
            image.verify()

        with Image.open(path) as image:
            width, height = image.size

        return width >= 400 and height >= 300

    except Exception:
        return False


def image_signature(path):
    try:
        with Image.open(path) as image:
            image = image.convert("RGB")
            image = image.resize((32, 32))
            return hashlib.sha256(image.tobytes()).hexdigest()
    except Exception:
        return ""


def find_images(story):
    candidates = []

    fields = (
        "image_paths",
        "images",
        "image_path",
        "local_image",
        "photo",
        "photo_path",
        "image",
    )

    for field in fields:
        value = story.get(field)

        if isinstance(value, str):
            candidates.append(Path(value))

        elif isinstance(value, list):
            for item in value:
                if isinstance(item, str):
                    candidates.append(Path(item))

                elif isinstance(item, dict):
                    possible = (
                        item.get("local_path")
                        or item.get("path")
                        or item.get("file")
                        or item.get("image_path")
                    )

                    if possible:
                        candidates.append(Path(str(possible)))

    for pattern in (
        "story_image*",
        "article_image*",
        "photo*",
        "*.jpg",
        "*.jpeg",
        "*.png",
        "*.webp",
    ):
        candidates.extend(SOURCE_DIR.glob(pattern))

    resolved = []
    seen = set()
    signatures = set()

    for candidate in candidates:
        if not candidate.is_absolute():
            options = [
                BASE_DIR / candidate,
                DATA_DIR / candidate,
                SOURCE_DIR / candidate,
            ]
        else:
            options = [candidate]

        for option in options:
            try:
                option = option.resolve()
            except Exception:
                pass

            key = str(option)

            if key in seen:
                continue

            seen.add(key)

            if not valid_image(option):
                continue

            signature = image_signature(option)

            if signature and signature in signatures:
                continue

            if signature:
                signatures.add(signature)

            resolved.append(option)

            if len(resolved) >= 6:
                return resolved

    return resolved


def prepare_image(path):
    with Image.open(path) as original:
        image = original.convert("RGB")

    source_width, source_height = image.size
    target_ratio = WIDTH / HEIGHT
    source_ratio = source_width / source_height

    if source_ratio > target_ratio:
        new_height = HEIGHT
        new_width = int(new_height * source_ratio)
    else:
        new_width = WIDTH
        new_height = int(new_width / source_ratio)

    image = image.resize(
        (new_width, new_height),
        Image.Resampling.LANCZOS,
    )

    left = max(0, (new_width - WIDTH) // 2)
    top = max(0, (new_height - HEIGHT) // 2)

    image = image.crop(
        (
            left,
            top,
            left + WIDTH,
            top + HEIGHT,
        )
    )

    overlay = Image.new("RGBA", image.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)

    for y in range(HEIGHT):
        ratio = y / HEIGHT

        if ratio < 0.4:
            alpha = int(205 * (1 - ratio / 0.4))
        else:
            alpha = int(180 * ((ratio - 0.4) / 0.6))

        alpha = max(0, min(205, alpha))

        draw.line(
            (0, y, WIDTH, y),
            fill=(0, 0, 0, alpha),
        )

    return Image.alpha_composite(
        image.convert("RGBA"),
        overlay,
    ).convert("RGB")


def decorate(image, story):
    draw = ImageDraw.Draw(image)

    white = (255, 255, 255)
    muted = (218, 225, 232)
    yellow = (245, 185, 62)

    brand_font = font(42, True)
    label_font = font(30, True)
    title_font = font(65, True)
    body_font = font(33, False)
    footer_font = font(23, False)

    title = text(
        story.get("title") or story.get("headline"),
        "Rift Valley Regional Update",
    )

    county = text(
        story.get("county") or story.get("location"),
        "Rift Valley",
    )

    category = text(
        story.get("category"),
        "REGIONAL UPDATE",
    ).upper()

    summary = text(
        story.get("summary") or story.get("description"),
        "",
    )

    source_data = story.get("source", "")

    if isinstance(source_data, dict):
        source = text(
            source_data.get("name"),
            "Rift Valley Watch",
        )
    else:
        source = text(source_data, "Rift Valley Watch")

    if "citizen" in source.lower() or source.lower() == "ctv":
        source = "Rift Valley Watch"

    draw.rectangle(
        (0, 0, WIDTH, 126),
        fill=(5, 12, 21),
    )

    draw.rectangle(
        (0, 122, WIDTH, 130),
        fill=yellow,
    )

    draw.text(
        (58, 35),
        "RIFT VALLEY WATCH",
        font=brand_font,
        fill=white,
    )

    draw.text(
        (58, 150),
        f"{county.upper()}  |  {category}",
        font=label_font,
        fill=yellow,
    )

    title_y = draw_wrapped(
        draw,
        title,
        58,
        240,
        WIDTH - 116,
        title_font,
        white,
        gap=12,
    )

    summary_y = max(title_y + 55, 920)

    draw_wrapped(
        draw,
        summary,
        58,
        summary_y,
        WIDTH - 116,
        body_font,
        muted,
        gap=10,
    )

    footer_y = HEIGHT - 110

    draw.rectangle(
        (0, footer_y - 25, WIDTH, HEIGHT),
        fill=(4, 10, 17),
    )

    draw.text(
        (58, footer_y + 10),
        f"SOURCE: {source}",
        font=footer_font,
        fill=muted,
    )

    return image


def create_scene(source_path, story, output_path):
    image = prepare_image(source_path)
    image = decorate(image, story)

    image.save(
        output_path,
        format="JPEG",
        quality=94,
        optimize=True,
    )


def audio_duration():
    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "format=duration",
        "-of",
        "default=noprint_wrappers=1:nokey=1",
        str(AUDIO_FILE),
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    if result.returncode != 0:
        raise RuntimeError("Could not read narration duration")

    value = float(result.stdout.strip())

    if value <= 0:
        raise RuntimeError("Narration duration is invalid")

    return value


def create_video(scene_path, output_path, duration):
    command = [
        "ffmpeg",
        "-y",
        "-loop",
        "1",
        "-i",
        str(scene_path),
        "-t",
        f"{duration:.3f}",
        "-vf",
        (
            f"scale={WIDTH}:{HEIGHT}:"
            "force_original_aspect_ratio=decrease,"
            f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2,"
            "format=yuv420p"
        ),
        "-r",
        str(FPS),
        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "20",
        "-pix_fmt",
        "yuv420p",
        "-an",
        str(output_path),
    ]

    run(command, f"Creating {output_path.name}")


def concatenate(scene_videos, output_path):
    concat_file = WORK_DIR / "concat.txt"

    with concat_file.open("w", encoding="utf-8") as file:
        for video in scene_videos:
            file.write(f"file '{video.resolve()}'\n")

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
        "-an",
        str(output_path),
    ]

    run(command, "Concatenating scenes")


def add_audio(video_path):
    command = [
        "ffmpeg",
        "-y",
        "-i",
        str(video_path),
        "-i",
        str(AUDIO_FILE),
        "-map",
        "0:v:0",
        "-map",
        "1:a:0",
        "-c:v",
        "copy",
        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-shortest",
        "-movflags",
        "+faststart",
        str(FINAL_FILE),
    ]

    run(command, "Adding narration")


def validate():
    if not FINAL_FILE.exists():
        raise RuntimeError("Final MP4 was not created")

    if FINAL_FILE.stat().st_size < 100000:
        raise RuntimeError("Final MP4 is too small")

    command = [
        "ffprobe",
        "-v",
        "error",
        "-show_entries",
        "stream=codec_type,width,height",
        "-of",
        "csv=p=0",
        str(FINAL_FILE),
    ]

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        encoding="utf-8",
        errors="replace",
    )

    output = result.stdout.replace(" ", "")

    if "video" not in output:
        raise RuntimeError("Final MP4 has no video stream")

    if "audio" not in output:
        raise RuntimeError("Final MP4 has no audio stream")

    if "1080,1920" not in output:
        raise RuntimeError("Final MP4 is not 1080x1920")

    print()
    print("FINAL VIDEO VALIDATED")
    print(FINAL_FILE)
    print(FINAL_FILE.stat().st_size, "bytes")


def main():
    print("=" * 72)
    print("RIFT VALLEY WATCH VIDEO GENERATOR")
    print("=" * 72)

    for directory in (
        DATA_DIR,
        SOURCE_DIR,
        WORK_DIR,
        AUDIO_DIR,
        OUTPUT_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)

    if not SCRIPT_FILE.exists():
        raise RuntimeError(f"Missing script file: {SCRIPT_FILE}")

    if not AUDIO_FILE.exists():
        raise RuntimeError(f"Missing narration file: {AUDIO_FILE}")

    story = get_story(load_json(STORY_FILE))
    images = find_images(story)

    if not images:
        raise RuntimeError("No valid real article photographs found")

    duration = audio_duration()
    each_duration = duration / len(images)

    if WORK_DIR.exists():
        for item in WORK_DIR.iterdir():
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                shutil.rmtree(item)

    videos = []

    for index, image_path in enumerate(images, start=1):
        scene_image = WORK_DIR / f"scene_{index:02d}.jpg"
        scene_video = WORK_DIR / f"scene_{index:02d}.mp4"

        create_scene(
            image_path,
            story,
            scene_image,
        )

        create_video(
            scene_image,
            scene_video,
            each_duration,
        )

        videos.append(scene_video)

    silent_video = WORK_DIR / "silent_video.mp4"

    concatenate(
        videos,
        silent_video,
    )

    if FINAL_FILE.exists():
        FINAL_FILE.unlink()

    add_audio(silent_video)
    validate()

    print()
    print("GENERATION COMPLETED")


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print()
        print("RIFT VALLEY WATCH GENERATOR FAILED")
        print("ERROR:", error)
        sys.exit(1)
