import json
import subprocess
import shutil
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS


ROOT = Path(__file__).resolve().parents[1]

SCRIPT_FILE = ROOT / "data" / "script.json"
OUTPUT_DIR = ROOT / "output"
TEMP_DIR = ROOT / "output" / "temp"

VIDEO_FILE = OUTPUT_DIR / "rift_valley_watch.mp4"
AUDIO_FILE = TEMP_DIR / "narration.mp3"

WIDTH = 1080
HEIGHT = 1920

FPS = 30

BACKGROUND = (18, 22, 30)
PANEL = (27, 33, 43)
WHITE = (245, 247, 250)
LIGHT = (190, 198, 210)
ACCENT = (220, 38, 38)
GREEN = (34, 197, 94)

FONT_DIRS = [
    Path("/usr/share/fonts/truetype/dejavu"),
    Path("/usr/share/fonts/truetype/liberation2"),
]


def find_font(size, bold=False):
    candidates = []

    if bold:
        candidates = [
            "DejaVuSans-Bold.ttf",
            "LiberationSans-Bold.ttf",
        ]
    else:
        candidates = [
            "DejaVuSans.ttf",
            "LiberationSans-Regular.ttf",
        ]

    for directory in FONT_DIRS:
        for filename in candidates:
            path = directory / filename
            if path.exists():
                return ImageFont.truetype(str(path), size)

    return ImageFont.load_default()


def run_command(command):
    print("[RUN]", " ".join(str(x) for x in command))

    result = subprocess.run(
        command,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        print(result.stdout)
        print(result.stderr)

        raise RuntimeError(
            f"Command failed with exit code {result.returncode}"
        )

    return result


def load_script():
    if not SCRIPT_FILE.exists():
        raise RuntimeError(
            "data/script.json was not found."
        )

    with open(
        SCRIPT_FILE,
        "r",
        encoding="utf-8",
    ) as file:
        data = json.load(file)

    if not isinstance(data, dict):
        raise RuntimeError(
            "data/script.json must contain a JSON object."
        )

    return data


def wrap_text(draw, text, font, max_width):
    words = text.split()

    lines = []
    current = ""

    for word in words:
        test = word if not current else current + " " + word

        bbox = draw.textbbox(
            (0, 0),
            test,
            font=font,
        )

        width = bbox[2] - bbox[0]

        if width <= max_width:
            current = test
        else:
            if current:
                lines.append(current)

            current = word

    if current:
        lines.append(current)

    return lines


def draw_centered_text(
    draw,
    text,
    font,
    center_x,
    start_y,
    max_width,
    fill,
    spacing=18,
):
    lines = wrap_text(
        draw,
        text,
        font,
        max_width,
    )

    y = start_y

    for line in lines:
        bbox = draw.textbbox(
            (0, 0),
            line,
            font=font,
        )

        width = bbox[2] - bbox[0]

        x = center_x - (width / 2)

        draw.text(
            (x, y),
            line,
            font=font,
            fill=fill,
        )

        y += (
            bbox[3] - bbox[1]
        ) + spacing

    return y


def create_background():
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        BACKGROUND,
    )

    draw = ImageDraw.Draw(image)

    # Top news bar
    draw.rectangle(
        [0, 0, WIDTH, 145],
        fill=(12, 15, 21),
    )

    # Breaking-news indicator
    draw.rectangle(
        [60, 42, 330, 105],
        fill=ACCENT,
    )

    bold_small = find_font(
        34,
        bold=True,
    )

    draw.text(
        (88, 54),
        "RIFT VALLEY WATCH",
        font=bold_small,
        fill=WHITE,
    )

    # Bottom branding bar
    draw.rectangle(
        [0, HEIGHT - 115, WIDTH, HEIGHT],
        fill=(12, 15, 21),
    )

    small = find_font(
        28,
        bold=True,
    )

    draw.text(
        (60, HEIGHT - 82),
        "REGIONAL NEWS • DEVELOPMENT • ACCOUNTABILITY",
        font=small,
        fill=LIGHT,
    )

    return image


def create_slide(
    title,
    body,
    label,
    output_file,
):
    image = create_background()

    draw = ImageDraw.Draw(image)

    title_font = find_font(
        76,
        bold=True,
    )

    body_font = find_font(
        48,
        bold=False,
    )

    label_font = find_font(
        32,
        bold=True,
    )

    # Section label
    draw.rounded_rectangle(
        [60, 245, 430, 320],
        radius=18,
        fill=PANEL,
    )

    draw.text(
        (88, 263),
        label.upper(),
        font=label_font,
        fill=GREEN,
    )

    # Main title
    title_y = 390

    title_end = draw_centered_text(
        draw,
        title,
        title_font,
        WIDTH // 2,
        title_y,
        WIDTH - 150,
        WHITE,
        spacing=22,
    )

    # Divider
    divider_y = min(
        title_end + 65,
        900,
    )

    draw.rectangle(
        [
            120,
            divider_y,
            WIDTH - 120,
            divider_y + 5,
        ],
        fill=ACCENT,
    )

    # Body
    body_y = divider_y + 75

    draw_centered_text(
        draw,
        body,
        body_font,
        WIDTH // 2,
        body_y,
        WIDTH - 170,
        LIGHT,
        spacing=22,
    )

    image.save(
        output_file,
        quality=95,
    )


def get_sections(data):
    sections = data.get(
        "sections",
        {},
    )

    if not isinstance(sections, dict):
        raise RuntimeError(
            "script.json sections are invalid."
        )

    return [
        (
            "THE LATEST",
            sections.get("hook", ""),
        ),
        (
            "WHAT HAPPENED",
            sections.get("what_happened", ""),
        ),
        (
            "KEY FACTS",
            sections.get("key_facts", ""),
        ),
        (
            "WHY IT MATTERS",
            sections.get("why_it_matters", ""),
        ),
        (
            "THE IMPACT",
            sections.get("impact", ""),
        ),
        (
            "WHAT'S NEXT",
            sections.get("close", ""),
        ),
    ]


def create_audio(narration):
    print("[AUDIO] Generating narration...")

    tts = gTTS(
        text=narration,
        lang="en",
        slow=False,
    )

    tts.save(
        str(AUDIO_FILE)
    )

    if not AUDIO_FILE.exists():
        raise RuntimeError(
            "Narration audio was not created."
        )


def get_audio_duration():
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "default=noprint_wrappers=1:nokey=1",
            str(AUDIO_FILE),
        ],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            "Could not determine audio duration."
        )

    return float(
        result.stdout.strip()
    )


def create_video(data):
    print()
    print("=" * 60)
    print("RIFT VALLEY WATCH VIDEO GENERATOR")
    print("=" * 60)

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    TEMP_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    title = (
        data.get("story", {})
        .get("title", "")
        .strip()
    )

    narration = (
        data.get("narration", "")
        .strip()
    )

    if not title:
        raise RuntimeError(
            "Story title is missing."
        )

    if not narration:
        raise RuntimeError(
            "Narration is missing."
        )

    sections = get_sections(data)

    # Remove previous temporary files
    for file in TEMP_DIR.glob("*"):
        if file.is_file():
            file.unlink()

    print()
    print("[1/5] Creating narration...")

    create_audio(
        narration
    )

    duration = get_audio_duration()

    print(
        f"      Audio duration: {duration:.2f} seconds"
    )

    print()
    print("[2/5] Creating visual slides...")

    slide_files = []

    for index, (label, body) in enumerate(
        sections,
        start=1,
    ):
        slide_file = (
            TEMP_DIR
            / f"slide_{index:02d}.png"
        )

        create_slide(
            title=title,
            body=body,
            label=label,
            output_file=slide_file,
        )

        slide_files.append(
            slide_file
        )

        print(
            f"      Created slide {index}: {label}"
        )

    print()
    print("[3/5] Building visual sequence...")

    seconds_per_slide = max(
        duration / len(slide_files),
        2.5,
    )

    concat_file = (
        TEMP_DIR
        / "slides.txt"
    )

    with open(
        concat_file,
        "w",
        encoding="utf-8",
    ) as file:

        for slide in slide_files:
            file.write(
                f"file '{slide.resolve()}'\n"
            )

            file.write(
                f"duration {seconds_per_slide}\n"
            )

        # ffmpeg concat requires the final frame
        file.write(
            f"file '{slide_files[-1].resolve()}'\n"
        )

    silent_video = (
        TEMP_DIR
        / "silent_video.mp4"
    )

    run_command(
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
            f"scale={WIDTH}:{HEIGHT}:force_original_aspect_ratio=decrease,"
            f"pad={WIDTH}:{HEIGHT}:(ow-iw)/2:(oh-ih)/2",
            "-r",
            str(FPS),
            "-c:v",
            "libx264",
            "-pix_fmt",
            "yuv420p",
            "-an",
            str(silent_video),
        ]
    )

    print()
    print("[4/5] Adding narration...")

    run_command(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(silent_video),
            "-i",
            str(AUDIO_FILE),
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "128k",
            "-shortest",
            "-movflags",
            "+faststart",
            str(VIDEO_FILE),
        ]
    )

    print()
    print("[5/5] Quality control...")

    if not VIDEO_FILE.exists():
        raise RuntimeError(
            "Final MP4 was not created."
        )

    if VIDEO_FILE.stat().st_size < 100000:
        raise RuntimeError(
            "Final MP4 is suspiciously small."
        )

    # Verify the MP4 can be read by ffprobe
    run_command(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size",
            "-of",
            "default=noprint_wrappers=1",
            str(VIDEO_FILE),
        ]
    )

    print()
    print("-" * 60)
    print("VIDEO GENERATION COMPLETE")
    print("-" * 60)

    print(
        f"Title: {title}"
    )

    print(
        f"Output: {VIDEO_FILE}"
    )

    print(
        f"Size: {VIDEO_FILE.stat().st_size / 1024 / 1024:.2f} MB"
    )

    print("-" * 60)


def main():
    try:
        data = load_script()

        create_video(
            data
        )

    except Exception as error:
        print()
        print("=" * 60)
        print("VIDEO GENERATION FAILED")
        print("=" * 60)
        print()
        print(str(error))
        print()

        raise


if __name__ == "__main__":
    main()
