import json
import subprocess
import tempfile
from pathlib import Path

import requests
from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS


WIDTH = 1080
HEIGHT = 1920
FPS = 30

OUTPUT = Path(
    "output/rift_valley_watch_reel.mp4"
)

SOURCE_DIR = Path(
    "assets/source"
)

AUDIO_DIR = Path(
    "assets/audio"
)


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

            return ImageFont.truetype(
                path,
                size,
            )

    return ImageFont.load_default()


def wrap_text(
    draw,
    text,
    font,
    max_width,
):

    words = text.split()

    lines = []
    current = ""

    for word in words:

        test = (
            current + " " + word
        ).strip()

        width = draw.textbbox(
            (0, 0),
            test,
            font=font,
        )[2]

        if width <= max_width:

            current = test

        else:

            if current:
                lines.append(current)

            current = word

    if current:
        lines.append(current)

    return lines


def download_image(url):

    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    path = (
        SOURCE_DIR /
        "story_image.jpg"
    )

    response = requests.get(
        url,
        headers={
            "User-Agent":
            "RiftValleyWatch/1.0"
        },
        timeout=30,
    )

    response.raise_for_status()

    path.write_bytes(
        response.content
    )

    image = Image.open(path).convert(
        "RGB"
    )

    image.save(
        path,
        quality=92,
    )

    return path


def create_scene(
    image_path,
    title,
    body,
    label,
):

    image = Image.open(
        image_path
    ).convert("RGB")

    image.thumbnail(
        (WIDTH, HEIGHT)
    )

    canvas = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        (12, 15, 20),
    )

    x = (
        WIDTH - image.width
    ) // 2

    y = (
        HEIGHT - image.height
    ) // 2

    canvas.paste(
        image,
        (x, y),
    )

    overlay = Image.new(
        "RGBA",
        (WIDTH, HEIGHT),
        (0, 0, 0, 0),
    )

    draw = ImageDraw.Draw(
        overlay
    )

    draw.rectangle(
        (0, 0, WIDTH, 210),
        fill=(0, 0, 0, 185),
    )

    draw.rectangle(
        (0, HEIGHT - 700, WIDTH, HEIGHT),
        fill=(0, 0, 0, 215),
    )

    draw.text(
        (55, 55),
        "RIFT VALLEY WATCH",
        font=get_font(54, True),
        fill="white",
    )

    draw.text(
        (55, 130),
        label.upper(),
        font=get_font(30, True),
        fill="white",
    )

    title_font = get_font(
        62,
        True,
    )

    body_font = get_font(
        39
    )

    title_lines = wrap_text(
        draw,
        title,
        title_font,
        WIDTH - 110,
    )

    y_position = HEIGHT - 650

    for line in title_lines[:5]:

        draw.text(
            (55, y_position),
            line,
            font=title_font,
            fill="white",
        )

        y_position += 75

    body_lines = wrap_text(
        draw,
        body,
        body_font,
        WIDTH - 110,
    )

    for line in body_lines[:8]:

        draw.text(
            (55, y_position),
            line,
            font=body_font,
            fill="white",
        )

        y_position += 52

    draw.text(
        (55, HEIGHT - 90),
        "Source: reported article",
        font=get_font(25),
        fill="white",
    )

    return Image.alpha_composite(
        canvas.convert("RGBA"),
        overlay,
    ).convert("RGB")


def generate_video(story):

    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    AUDIO_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    Path("output").mkdir(
        exist_ok=True
    )

    image_path = download_image(
        story["image_url"]
    )

    narration = story[
        "narration"
    ]

    audio_path = (
        AUDIO_DIR /
        "narration.mp3"
    )

    gTTS(
        text=narration,
        lang="en",
        slow=False,
    ).save(
        audio_path
    )

    scenes = [

        (
            "BREAKING / REGIONAL UPDATE",
            story["title"],
            story["summary"],
        ),

        (
            "WHAT WE KNOW",
            story["title"],
            story["summary"],
        ),

        (
            "WHY IT MATTERS",
            "Regional impact",
            (
                "The report is being followed "
                "for its implications for "
                "communities, services, business "
                "and development."
            ),
        ),

        (
            "SOURCE",
            story["source"]
            or "Published report",
            story.get(
                "resolved_url"
            )
            or story["url"],
        ),
    ]

    with tempfile.TemporaryDirectory() as temp:

        temp = Path(temp)

        scene_paths = []

        for index, scene in enumerate(
            scenes
        ):

            label, title, body = scene

            path = (
                temp /
                f"scene_{index}.png"
            )

            create_scene(
                image_path,
                title,
                body,
                label,
            ).save(path)

            scene_paths.append(
                path
            )

        concat_file = (
            temp /
            "concat.txt"
        )

        duration = 4.5

        content = []

        for path in scene_paths:

            content.append(
                f"file '{path.resolve()}'"
            )

            content.append(
                f"duration {duration}"
            )

        content.append(
            f"file '{scene_paths[-1].resolve()}'"
        )

        concat_file.write_text(
            "\n".join(content),
            encoding="utf-8",
        )

        silent_video = (
            temp /
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
                "-pix_fmt",
                "yuv420p",
                "-an",
                str(silent_video),
            ],
            check=True,
        )

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
                "-c:a",
                "aac",
                "-shortest",
                "-movflags",
                "+faststart",
                str(OUTPUT),
            ],
            check=True,
        )

    validate_video()

    Path(
        "data/visual_metadata.json"
    ).write_text(
        json.dumps(
            {
                "brand":
                    "Rift Valley Watch",
                "source_image":
                    str(image_path),
                "source_url":
                    story.get(
                        "resolved_url"
                    )
                    or story["url"],
                "title":
                    story["title"],
            },
            indent=2,
        ),
        encoding="utf-8",
    )


def validate_video():

    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-select_streams",
            "v:0",
            "-show_entries",
            "stream=codec_name,width,height",
            "-of",
            "json",
            str(OUTPUT),
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    info = json.loads(
        result.stdout
    )["streams"][0]

    if (
        info["codec_name"] != "h264"
        or int(info["width"]) != WIDTH
        or int(info["height"]) != HEIGHT
    ):

        raise RuntimeError(
            "Video QC failed."
        )
