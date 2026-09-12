import json
import subprocess
import tempfile
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS


# ============================================================
# RIFT VALLEY WATCH VIDEO SETTINGS
# ============================================================

WIDTH = 1080
HEIGHT = 1920
FPS = 30

OUTPUT = Path("output/rift_valley_watch_reel.mp4")

SOURCE_DIR = Path("assets/source")
AUDIO_DIR = Path("assets/audio")


# ============================================================
# FONTS
# ============================================================

def get_font(size, bold=False):
    if bold:
        candidates = [
            "fonts/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
        ]
    else:
        candidates = [
            "fonts/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]

    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)

    return ImageFont.load_default()


# ============================================================
# TEXT WRAPPING
# ============================================================

def wrap_text(draw, text, font, max_width):
    words = str(text or "").split()

    lines = []
    current = ""

    for word in words:
        test = f"{current} {word}".strip()

        bbox = draw.textbbox(
            (0, 0),
            test,
            font=font,
        )

        text_width = bbox[2] - bbox[0]

        if text_width <= max_width:
            current = test
        else:
            if current:
                lines.append(current)

            current = word

    if current:
        lines.append(current)

    return lines


# ============================================================
# IMAGE DOWNLOAD
# ============================================================

def download_image(url):
    if not url:
        raise RuntimeError("No story image URL was provided.")

    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = SOURCE_DIR / "story_image.jpg"

    response = requests.get(
        url,
        headers={
            "User-Agent": "Mozilla/5.0 RiftValleyWatch/1.0"
        },
        timeout=30,
    )

    response.raise_for_status()

    path.write_bytes(response.content)

    try:
        image = Image.open(path).convert("RGB")
    except Exception as error:
        raise RuntimeError(
            f"Downloaded file is not a valid image: {error}"
        )

    image.save(
        path,
        "JPEG",
        quality=92,
    )

    return path


# ============================================================
# CREATE NEWS SCENE
# ============================================================

def create_scene(
    image_path,
    title,
    body,
    label,
):
    image = Image.open(
        image_path
    ).convert("RGB")

    # --------------------------------------------------------
    # Fill the vertical frame while maintaining aspect ratio
    # --------------------------------------------------------

    image_ratio = image.width / image.height
    target_ratio = WIDTH / HEIGHT

    if image_ratio > target_ratio:
        new_height = HEIGHT
        new_width = int(new_height * image_ratio)
    else:
        new_width = WIDTH
        new_height = int(new_width / image_ratio)

    image = image.resize(
        (new_width, new_height),
        Image.Resampling.LANCZOS,
    )

    left = max(
        0,
        (image.width - WIDTH) // 2,
    )

    top = max(
        0,
        (image.height - HEIGHT) // 2,
    )

    image = image.crop(
        (
            left,
            top,
            left + WIDTH,
            top + HEIGHT,
        )
    )

    canvas = image.convert("RGBA")

    # --------------------------------------------------------
    # Overlay
    # --------------------------------------------------------

    overlay = Image.new(
        "RGBA",
        (WIDTH, HEIGHT),
        (0, 0, 0, 0),
    )

    draw = ImageDraw.Draw(overlay)

    # Top newsroom bar
    draw.rectangle(
        (0, 0, WIDTH, 220),
        fill=(5, 8, 12, 225),
    )

    # Bottom information panel
    draw.rectangle(
        (0, HEIGHT - 760, WIDTH, HEIGHT),
        fill=(5, 8, 12, 235),
    )

    # Breaking indicator
    draw.rectangle(
        (0, 0, 300, 70),
        fill=(190, 20, 30, 255),
    )

    draw.text(
        (35, 14),
        "RIFT VALLEY",
        font=get_font(34, True),
        fill="white",
    )

    draw.text(
        (35, 88),
        "WATCH",
        font=get_font(54, True),
        fill="white",
    )

    # Section label
    draw.text(
        (WIDTH - 500, 35),
        str(label).upper(),
        font=get_font(28, True),
        fill="white",
    )

    # --------------------------------------------------------
    # Headline
    # --------------------------------------------------------

    title_font = get_font(
        58,
        True,
    )

    body_font = get_font(
        34,
        False,
    )

    title_lines = wrap_text(
        draw,
        title,
        title_font,
        WIDTH - 110,
    )

    y = HEIGHT - 700

    for line in title_lines[:5]:
        draw.text(
            (55, y),
            line,
            font=title_font,
            fill="white",
        )

        y += 72

    # --------------------------------------------------------
    # Body
    # --------------------------------------------------------

    y += 20

    body_lines = wrap_text(
        draw,
        body,
        body_font,
        WIDTH - 110,
    )

    for line in body_lines[:9]:
        draw.text(
            (55, y),
            line,
            font=body_font,
            fill="white",
        )

        y += 47

    # --------------------------------------------------------
    # Footer
    # --------------------------------------------------------

    draw.rectangle(
        (0, HEIGHT - 80, WIDTH, HEIGHT),
        fill=(0, 0, 0, 220),
    )

    draw.text(
        (55, HEIGHT - 62),
        "RIFT VALLEY WATCH  •  CURRENT AFFAIRS",
        font=get_font(25, True),
        fill="white",
    )

    return Image.alpha_composite(
        canvas,
        overlay,
    ).convert("RGB")


# ============================================================
# CREATE SCENES
# ============================================================

def create_scenes(story, image_path, temp_dir):
    title = story.get(
        "title",
        "Rift Valley regional update",
    )

    summary = story.get(
        "summary",
        "A regional current affairs story is being reported.",
    )

    source = story.get(
        "source",
        "Published report",
    )

    resolved_url = story.get(
        "resolved_url",
        story.get("url", ""),
    )

    scenes = [
        (
            "BREAKING UPDATE",
            title,
            summary,
        ),

        (
            "WHAT WE KNOW",
            title,
            summary,
        ),

        (
            "WHY IT MATTERS",
            "Regional impact",
            (
                "The development is being followed "
                "for its potential impact on communities, "
                "services, business and development "
                "across the Rift Valley."
            ),
        ),

        (
            "SOURCE",
            source,
            resolved_url,
        ),
    ]

    scene_paths = []

    for index, scene in enumerate(scenes):
        label, scene_title, body = scene

        scene_path = (
            temp_dir /
            f"scene_{index}.png"
        )

        frame = create_scene(
            image_path,
            scene_title,
            body,
            label,
        )

        frame.save(
            scene_path,
            "PNG",
        )

        scene_paths.append(scene_path)

    return scene_paths


# ============================================================
# CREATE SILENT VIDEO
# ============================================================

def create_silent_video(scene_paths, temp_dir):
    concat_file = temp_dir / "concat.txt"

    duration = 4.5

    lines = []

    for scene_path in scene_paths:
        escaped_path = str(
            scene_path.resolve()
        ).replace("'", "'\\''")

        lines.append(
            f"file '{escaped_path}'"
        )

        lines.append(
            f"duration {duration}"
        )

    # Required by FFmpeg concat demuxer
    final_path = str(
        scene_paths[-1].resolve()
    ).replace("'", "'\\''")

    lines.append(
        f"file '{final_path}'"
    )

    concat_file.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )

    silent_video = (
        temp_dir /
        "silent.mp4"
    )

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "concat",
            "-safe",
            "0",
            "-i",
            str(concat_file),
            "-vf",
            (
                f"scale={WIDTH}:{HEIGHT}:"
                "force_original_aspect_ratio=decrease,"
                f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2"
            ),
            "-r",
            str(FPS),
            "-c:v",
            "libx264",
            "-preset",
            "medium",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(silent_video),
        ],
        check=True,
    )

    return silent_video


# ============================================================
# CREATE NARRATION
# ============================================================

def create_audio(story):
    AUDIO_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    narration = story.get(
        "narration",
        "",
    )

    if not narration:
        raise RuntimeError(
            "No narration was provided."
        )

    audio_path = (
        AUDIO_DIR /
        "narration.mp3"
    )

    print("Generating narration...")

    gTTS(
        text=narration,
        lang="en",
        slow=False,
    ).save(
        audio_path
    )

    if not audio_path.exists():
        raise RuntimeError(
            "Narration audio was not created."
        )

    return audio_path


# ============================================================
# COMBINE VIDEO + AUDIO
# ============================================================

def combine_video_audio(
    silent_video,
    audio_path,
):
    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    print("Combining video and narration...")

    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(silent_video),
            "-i",
            str(audio_path),

            "-map",
            "0:v:0",
            "-map",
            "1:a:0",

            "-c:v",
            "libx264",
            "-preset",
            "medium",

            "-c:a",
            "aac",
            "-b:a",
            "128k",

            "-pix_fmt",
            "yuv420p",

            "-shortest",

            "-movflags",
            "+faststart",

            str(OUTPUT),
        ],
        check=True,
    )


# ============================================================
# VIDEO QC
# ============================================================

def validate_video():
    if not OUTPUT.exists():
        raise RuntimeError(
            "Video QC failed: MP4 file does not exist."
        )

    if OUTPUT.stat().st_size < 100_000:
        raise RuntimeError(
            "Video QC failed: MP4 file is unusually small."
        )

    # --------------------------------------------------------
    # Video stream
    # --------------------------------------------------------

    video_result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,width,height,duration",
            "-of",
            "json",
            str(OUTPUT),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    video_data = json.loads(
        video_result.stdout
    )

    if not video_data.get("streams"):
        raise RuntimeError(
            "Video QC failed: no video stream found."
        )

    video_stream = video_data["streams"][0]

    if video_stream.get("codec_name") != "h264":
        raise RuntimeError(
            "Video QC failed: video codec is not H.264."
        )

    if int(video_stream.get("width", 0)) != WIDTH:
        raise RuntimeError(
            "Video QC failed: incorrect width."
        )

    if int(video_stream.get("height", 0)) != HEIGHT:
        raise RuntimeError(
            "Video QC failed: incorrect height."
        )

    # --------------------------------------------------------
    # Audio stream
    # --------------------------------------------------------

    audio_result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "a:0",
            "-show_entries",
            "stream=codec_name,sample_rate,channels,duration",
            "-of",
            "json",
            str(OUTPUT),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    audio_data = json.loads(
        audio_result.stdout
    )

    if not audio_data.get("streams"):
        raise RuntimeError(
            "Video QC failed: no audio stream found."
        )

    audio_stream = audio_data["streams"][0]

    if audio_stream.get("codec_name") != "aac":
        raise RuntimeError(
            "Video QC failed: audio codec is not AAC."
        )

    print("")
    print("=" * 60)
    print("VIDEO QC PASSED")
    print("=" * 60)
    print(f"File: {OUTPUT}")
    print(f"Resolution: {WIDTH}x{HEIGHT}")
    print(f"Video codec: {video_stream.get('codec_name')}")
    print(f"Audio codec: {audio_stream.get('codec_name')}")
    print("=" * 60)


# ============================================================
# MAIN VIDEO GENERATION FUNCTION
# ============================================================

def generate_video(story):
    print("")
    print("=" * 60)
    print("RIFT VALLEY WATCH VIDEO GENERATOR")
    print("=" * 60)

    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    AUDIO_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Download article image
    # --------------------------------------------------------

    print("Downloading source image...")

    image_path = download_image(
        story.get("image_url")
    )

    print(
        f"Source image: {image_path}"
    )

    # --------------------------------------------------------
    # Generate narration
    # --------------------------------------------------------

    audio_path = create_audio(
        story
    )

    # --------------------------------------------------------
    # Generate scenes and video
    # --------------------------------------------------------

    with tempfile.TemporaryDirectory() as temp:
        temp_dir = Path(temp)

        print("Creating scenes...")

        scene_paths = create_scenes(
            story,
            image_path,
            temp_dir,
        )

        print(
            f"Created {len(scene_paths)} scenes."
        )

        print("Creating silent video...")

        silent_video = create_silent_video(
            scene_paths,
            temp_dir,
        )

        combine_video_audio(
            silent_video,
            audio_path,
        )

    # --------------------------------------------------------
    # QC
    # --------------------------------------------------------

    validate_video()

    # --------------------------------------------------------
    # Save metadata
    # --------------------------------------------------------

    metadata = {
        "brand": "Rift Valley Watch",
        "title": story.get("title"),
        "county": story.get("county"),
        "source": story.get("source"),
        "source_image": str(image_path),
        "source_url": (
            story.get("resolved_url")
            or story.get("url")
        ),
        "output": str(OUTPUT),
        "resolution": f"{WIDTH}x{HEIGHT}",
        "fps": FPS,
        "video_codec": "H.264",
        "audio_codec": "AAC",
    }

    Path(
        "data/visual_metadata.json"
    ).write_text(
        json.dumps(
            metadata,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print("")
    print("=" * 60)
    print("RIFT VALLEY WATCH VIDEO SUCCESSFUL")
    print("=" * 60)
    print(f"Created: {OUTPUT}")
    print("=" * 60)


# ============================================================
# LOCAL EXECUTION SUPPORT
# ============================================================

if __name__ == "__main__":
    story_file = Path(
        "data/story.json"
    )

    if not story_file.exists():
        raise RuntimeError(
            "data/story.json was not found."
        )

    story = json.loads(
        story_file.read_text(
            encoding="utf-8"
        )
    )

    generate_video(story)
