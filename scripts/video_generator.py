import json
import shutil
import subprocess
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from gtts import gTTS


ROOT = Path(__file__).resolve().parents[1]

STORY_FILE = ROOT / "data" / "story.json"
OUTPUT_DIR = ROOT / "output"
SCENE_DIR = OUTPUT_DIR / "scenes"
AUDIO_DIR = OUTPUT_DIR / "audio"

OUTPUT_FILE = OUTPUT_DIR / "rift_valley_watch.mp4"
REPORT_FILE = OUTPUT_DIR / "visual_report.json"

WIDTH = 1080
HEIGHT = 1920
FPS = 30


def log(message):
    print(message, flush=True)


def run_command(command, description):
    log("")
    log("=" * 60)
    log(description)
    log("=" * 60)
    log(" ".join(str(x) for x in command))

    result = subprocess.run(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    if result.stdout:
        print(result.stdout, flush=True)

    if result.returncode != 0:
        raise RuntimeError(
            f"{description} failed with exit code {result.returncode}"
        )

    return result


def check_ffmpeg():
    if shutil.which("ffmpeg") is None:
        raise RuntimeError("FFmpeg was not found.")

    if shutil.which("ffprobe") is None:
        raise RuntimeError("FFprobe was not found.")

    log("FFmpeg found.")
    log("FFprobe found.")


def load_json(path):
    if not path.exists():
        raise RuntimeError(f"Missing file: {path}")

    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)
    except Exception as exc:
        raise RuntimeError(f"Could not read {path}: {exc}")


def prepare_output():
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    SCENE_DIR.mkdir(parents=True, exist_ok=True)
    AUDIO_DIR.mkdir(parents=True, exist_ok=True)

    if OUTPUT_FILE.exists():
        OUTPUT_FILE.unlink()

    if REPORT_FILE.exists():
        REPORT_FILE.unlink()

    for folder in [SCENE_DIR, AUDIO_DIR]:
        for item in folder.iterdir():
            if item.is_file():
                item.unlink()

    log(f"Output directory: {OUTPUT_DIR}")
    log(f"Scene directory: {SCENE_DIR}")
    log(f"Audio directory: {AUDIO_DIR}")


def get_font(size, bold=False):
    candidates = []

    if bold:
        candidates.extend([
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Bold.ttf"
        ])
    else:
        candidates.extend([
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/liberation2/LiberationSans-Regular.ttf"
        ])

    for path in candidates:
        if Path(path).exists():
            return ImageFont.truetype(path, size)

    return ImageFont.load_default()


def wrap_text(draw, text, font, max_width):
    words = str(text).split()
    lines = []
    current = ""

    for word in words:
        candidate = word if not current else current + " " + word

        bbox = draw.textbbox(
            (0, 0),
            candidate,
            font=font
        )

        if bbox[2] - bbox[0] <= max_width:
            current = candidate
        else:
            if current:
                lines.append(current)
            current = word

    if current:
        lines.append(current)

    return lines


def draw_wrapped(
    draw,
    text,
    x,
    y,
    font,
    max_width,
    fill=(235, 240, 245),
    spacing=14
):
    lines = wrap_text(
        draw,
        text,
        font,
        max_width
    )

    for line in lines:
        draw.text(
            (x, y),
            line,
            font=font,
            fill=fill
        )

        bbox = draw.textbbox(
            (x, y),
            line,
            font=font
        )

        y += (bbox[3] - bbox[1]) + spacing

    return y


def make_background():
    image = Image.new(
        "RGB",
        (WIDTH, HEIGHT),
        (9, 15, 23)
    )

    draw = ImageDraw.Draw(image)

    for y in range(HEIGHT):
        value = int(
            9 + (y / HEIGHT) * 14
        )

        draw.line(
            [(0, y), (WIDTH, y)],
            fill=(value, value + 5, value + 12)
        )

    for x in range(0, WIDTH, 90):
        draw.line(
            [(x, 0), (x, HEIGHT)],
            fill=(24, 32, 43),
            width=1
        )

    for y in range(0, HEIGHT, 90):
        draw.line(
            [(0, y), (WIDTH, y)],
            fill=(24, 32, 43),
            width=1
        )

    return image


def draw_header(draw, section):
    draw.rectangle(
        [0, 0, WIDTH, 120],
        fill=(17, 24, 34)
    )

    draw.rectangle(
        [0, 0, 16, 120],
        fill=(220, 35, 45)
    )

    logo_font = get_font(35, True)
    section_font = get_font(23, True)

    draw.text(
        (45, 23),
        "RIFT VALLEY WATCH",
        font=logo_font,
        fill=(255, 255, 255)
    )

    draw.text(
        (45, 72),
        section.upper(),
        font=section_font,
        fill=(190, 201, 213)
    )

    draw.text(
        (WIDTH - 170, 40),
        "NEWS",
        font=section_font,
        fill=(220, 35, 45)
    )


def draw_footer(draw, source):
    y = HEIGHT - 105

    draw.rectangle(
        [0, y, WIDTH, HEIGHT],
        fill=(13, 19, 27)
    )

    font = get_font(21)

    draw.text(
        (40, y + 30),
        f"SOURCE: {source}",
        font=font,
        fill=(195, 205, 216)
    )


def create_scene_image(
    path,
    section,
    title,
    body,
    cards=None,
    source="Bomet County Government"
):
    image = make_background()
    draw = ImageDraw.Draw(image)

    draw_header(draw, section)

    title_font = get_font(57, True)
    body_font = get_font(37)
    label_font = get_font(23, True)
    value_font = get_font(52, True)

    y = 220

    y = draw_wrapped(
        draw,
        title,
        55,
        y,
        title_font,
        WIDTH - 110,
        fill=(255, 255, 255),
        spacing=12
    )

    y += 60

    if cards:
        for label, value in cards:
            card_height = 180

            draw.rounded_rectangle(
                [55, y, WIDTH - 55, y + card_height],
                radius=18,
                fill=(20, 29, 40),
                outline=(58, 70, 85),
                width=2
            )

            draw.text(
                (85, y + 25),
                str(label).upper(),
                font=label_font,
                fill=(220, 35, 45)
            )

            draw_wrapped(
                draw,
                value,
                85,
                y + 72,
                value_font,
                WIDTH - 170,
                fill=(255, 255, 255),
                spacing=8
            )

            y += card_height + 28

    y = max(y, 500)

    draw_wrapped(
        draw,
        body,
        55,
        y,
        body_font,
        WIDTH - 110,
        fill=(224, 231, 238),
        spacing=16
    )

    draw_footer(draw, source)

    image.save(
        path,
        "PNG",
        optimize=True
    )


def fact_value(story, label, default=""):
    for fact in story.get("verified_facts", []):
        if str(fact.get("label", "")).upper() == label.upper():
            return str(fact.get("value", default))

    return default


def build_sections(story):
    title = story.get(
        "title",
        "Rift Valley Watch"
    )

    county = story.get(
        "county",
        "Bomet County"
    )

    summary = story.get(
        "summary",
        ""
    )

    source = story.get(
        "source",
        {}
    )

    source_name = source.get(
        "name",
        "Official source"
    )

    project = fact_value(
        story,
        "PROJECT",
        ""
    )

    road_length = fact_value(
        story,
        "ROAD_LENGTH",
        ""
    )

    cost = fact_value(
        story,
        "COST",
        ""
    )

    location = fact_value(
        story,
        "LOCATION",
        county
    )

    status = fact_value(
        story,
        "STATUS",
        ""
    )

    impact = fact_value(
        story,
        "IMPACT",
        ""
    )

    statement = story.get(
        "official_statement",
        {}
    )

    speaker = statement.get(
        "speaker",
        ""
    )

    quote = statement.get(
        "quote",
        ""
    )

    return [
        {
            "name": "LATEST",
            "title": title,
            "text": (
                f"{title}. "
                f"According to {source_name}, {summary}"
            ),
            "cards": None
        },
        {
            "name": "LOCATION",
            "title": "WHERE IS THE PROJECT?",
            "text": (
                f"The project is located in {location}. "
                f"The reported road corridor covers "
                f"{project}."
            ),
            "cards": [
                ("COUNTY", county),
                ("LOCATION", location)
            ]
        },
        {
            "name": "KEY FACTS",
            "title": "THE NUMBERS",
            "text": (
                f"The project covers {road_length} "
                f"and has a reported cost of {cost}. "
                f"Construction status: {status}."
            ),
            "cards": [
                ("ROAD LENGTH", road_length),
                ("PROJECT COST", cost)
            ]
        },
        {
            "name": "ROUTE",
            "title": "ROAD CORRIDOR",
            "text": (
                f"The reported route is "
                f"{project}. "
                f"The project is being undertaken "
                f"in Bomet County."
            ),
            "cards": [
                ("ROUTE", project)
            ]
        },
        {
            "name": "WHY IT MATTERS",
            "title": "EXPECTED IMPACT",
            "text": (
                f"{impact}. "
                f"The county government says the project "
                f"is expected to unlock economic potential "
                f"in the area and wider Bomet County."
            ),
            "cards": None
        },
        {
            "name": "OFFICIAL STATEMENT",
            "title": speaker or "OFFICIAL STATEMENT",
            "text": quote or (
                "The official source says construction "
                "works are ongoing."
            ),
            "cards": None
        },
        {
            "name": "SOURCE",
            "title": "VERIFIED SOURCE",
            "text": (
                f"This report is based on information "
                f"published by {source_name}. "
                f"Unconfirmed details are not presented "
                f"as confirmed facts."
            ),
            "cards": [
                ("SOURCE", source_name)
            ]
        },
        {
            "name": "OUTRO",
            "title": "RIFT VALLEY WATCH",
            "text": (
                "Tracking verified developments across "
                "the region. Follow for more verified "
                "local news."
            ),
            "cards": None
        }
    ]


def create_audio(text, path):
    if not text.strip():
        raise RuntimeError(
            "Narration text is empty."
        )

    log(f"Creating audio: {path.name}")

    tts = gTTS(
        text=text,
        lang="en",
        slow=False
    )

    tts.save(str(path))

    if not path.exists():
        raise RuntimeError(
            f"Audio was not created: {path}"
        )

    if path.stat().st_size < 1000:
        raise RuntimeError(
            f"Audio file is too small: {path}"
        )


def render_scene(image_path, audio_path, video_path):
    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",

        "-loop",
        "1",
        "-i",
        str(image_path),

        "-i",
        str(audio_path),

        "-map",
        "0:v:0",
        "-map",
        "1:a:0",

        "-vf",
        (
            "scale=1080:1920:"
            "force_original_aspect_ratio=decrease,"
            "pad=1080:1920:(ow-iw)/2:(oh-ih)/2,"
            "setsar=1"
        ),

        "-r",
        str(FPS),

        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "21",

        "-pix_fmt",
        "yuv420p",

        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ar",
        "44100",

        "-shortest",
        "-movflags",
        "+faststart",

        str(video_path)
    ]

    run_command(
        command,
        f"Rendering {video_path.name}"
    )

    if not video_path.exists():
        raise RuntimeError(
            f"Scene video was not created: {video_path}"
        )

    if video_path.stat().st_size < 5000:
        raise RuntimeError(
            f"Scene video is too small: {video_path}"
        )


def concatenate_scenes(scene_files):
    if not scene_files:
        raise RuntimeError(
            "No scene files were generated."
        )

    concat_file = OUTPUT_DIR / "concat_list.txt"

    with concat_file.open(
        "w",
        encoding="utf-8"
    ) as f:
        for scene in scene_files:
            path = scene.resolve()

            escaped = str(path).replace(
                "'",
                "'\\''"
            )

            f.write(
                f"file '{escaped}'\n"
            )

    log("")
    log("CONCAT LIST:")
    print(
        concat_file.read_text(
            encoding="utf-8"
        ),
        flush=True
    )

    command = [
        "ffmpeg",
        "-y",
        "-hide_banner",
        "-loglevel",
        "error",

        "-f",
        "concat",
        "-safe",
        "0",
        "-i",
        str(concat_file),

        "-c:v",
        "libx264",
        "-preset",
        "veryfast",
        "-crf",
        "21",

        "-pix_fmt",
        "yuv420p",

        "-c:a",
        "aac",
        "-b:a",
        "128k",
        "-ar",
        "44100",

        "-movflags",
        "+faststart",

        str(OUTPUT_FILE)
    ]

    run_command(
        command,
        "Creating final MP4"
    )

    if not OUTPUT_FILE.exists():
        raise RuntimeError(
            "FFmpeg finished but final MP4 does not exist."
        )

    if OUTPUT_FILE.stat().st_size < 10000:
        raise RuntimeError(
            "Final MP4 is too small."
        )


def validate_mp4():
    if not OUTPUT_FILE.exists():
        raise RuntimeError(
            "Final MP4 does not exist."
        )

    command = [
        "ffprobe",
        "-v",
        "error",

        "-show_entries",
        "format=duration,size",

        "-show_entries",
        "stream="
        "codec_type,"
        "codec_name,"
        "width,"
        "height,"
        "r_frame_rate",

        "-of",
        "json",

        str(OUTPUT_FILE)
    ]

    result = subprocess.run(
        command,
        cwd=ROOT,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    print(
        result.stdout,
        flush=True
    )

    if result.returncode != 0:
        raise RuntimeError(
            "FFprobe failed."
        )

    info = json.loads(
        result.stdout
    )

    streams = info.get(
        "streams",
        []
    )

    fmt = info.get(
        "format",
        {}
    )

    video = None
    audio = None

    for stream in streams:
        if stream.get(
            "codec_type"
        ) == "video":
            video = stream

        if stream.get(
            "codec_type"
        ) == "audio":
            audio = stream

    if video is None:
        raise RuntimeError(
            "No video stream found."
        )

    if audio is None:
        raise RuntimeError(
            "No audio stream found."
        )

    duration = float(
        fmt.get(
            "duration",
            0
        )
    )

    size = int(
        float(
            fmt.get(
                "size",
                0
            )
        )
    )

    if duration <= 1:
        raise RuntimeError(
            "Video duration is invalid."
        )

    if size < 10000:
        raise RuntimeError(
            "Video file size is invalid."
        )

    if video.get(
        "codec_name"
    ) != "h264":
        raise RuntimeError(
            "Video is not H.264."
        )

    if audio.get(
        "codec_name"
    ) != "aac":
        raise RuntimeError(
            "Audio is not AAC."
        )

    if int(
        video.get(
            "width",
            0
        )
    ) != WIDTH:
        raise RuntimeError(
            "Video width is not 1080."
        )

    if int(
        video.get(
            "height",
            0
        )
    ) != HEIGHT:
        raise RuntimeError(
            "Video height is not 1920."
        )

    log("")
    log("MP4 VALIDATION PASSED")
    log(f"Duration: {duration:.2f} seconds")
    log(
        f"Size: {size / 1024 / 1024:.2f} MB"
    )
    log("Resolution: 1080x1920")
    log("Video: H.264")
    log("Audio: AAC")


def write_report(story, sections, scene_files):
    report = {
        "project": "Rift Valley Watch",
        "status": "PASS",
        "title": story.get("title", ""),
        "source": story.get("source", {}),
        "scene_count": len(scene_files),
        "resolution": "1080x1920",
        "fps": FPS,
        "video_codec": "H.264",
        "audio_codec": "AAC",
        "output_file": OUTPUT_FILE.name,
        "scenes": [
            {
                "scene": i + 1,
                "name": sections[i]["name"],
                "file": scene_files[i].name
            }
            for i in range(len(scene_files))
        ],
        "quality_control": {
            "mp4_exists": OUTPUT_FILE.exists(),
            "validated": True
        }
    }

    with REPORT_FILE.open(
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            report,
            f,
            indent=2,
            ensure_ascii=False
        )


def main():
    log("")
    log("=" * 60)
    log("RIFT VALLEY WATCH VIDEO GENERATOR")
    log("=" * 60)

    # Create output BEFORE anything else.
    prepare_output()

    try:
        check_ffmpeg()

        story = load_json(
            STORY_FILE
        )

        log("")
        log("STORY:")
        log(
            story.get(
                "title",
                ""
            )
        )

        sections = build_sections(
            story
        )

        if len(sections) != 8:
            raise RuntimeError(
                f"Expected 8 scenes, got {len(sections)}."
            )

        scene_files = []

        for index, section in enumerate(
            sections,
            start=1
        ):
            slug = (
                section["name"]
                .lower()
                .replace(" ", "_")
            )

            image_path = (
                SCENE_DIR /
                f"scene_{index:02d}_{slug}.png"
            )

            audio_path = (
                AUDIO_DIR /
                f"scene_{index:02d}_{slug}.mp3"
            )

            video_path = (
                SCENE_DIR /
                f"scene_{index:02d}_{slug}.mp4"
            )

            log("")
            log(
                f"SCENE {index}/8: "
                f"{section['name']}"
            )

            create_scene_image(
                image_path,
                section["name"],
                section["title"],
                section["text"],
                section.get("cards"),
                story.get(
                    "source",
                    {}
                ).get(
                    "name",
                    "Bomet County Government"
                )
            )

            create_audio(
                section["text"],
                audio_path
            )

            render_scene(
                image_path,
                audio_path,
                video_path
            )

            scene_files.append(
                video_path
            )

        log("")
        log("=" * 60)
        log("ALL SCENES CREATED")
        log("=" * 60)

        for scene in scene_files:
            log(
                f"{scene.name}: "
                f"{scene.stat().st_size / 1024:.1f} KB"
            )

        concatenate_scenes(
            scene_files
        )

        validate_mp4()

        write_report(
            story,
            sections,
            scene_files
        )

        log("")
        log("=" * 60)
        log("SUCCESS")
        log("=" * 60)
        log(
            f"FINAL MP4: {OUTPUT_FILE}"
        )
        log(
            f"SIZE: "
            f"{OUTPUT_FILE.stat().st_size / 1024 / 1024:.2f} MB"
        )

        return 0

    except Exception as exc:
        log("")
        log("=" * 60)
        log("VIDEO GENERATION FAILED")
        log("=" * 60)
        log(
            f"{type(exc).__name__}: {exc}"
        )

        OUTPUT_DIR.mkdir(
            parents=True,
            exist_ok=True
        )

        failure = {
            "project": "Rift Valley Watch",
            "status": "FAILED",
            "error_type": type(exc).__name__,
            "error": str(exc),
            "output_exists": OUTPUT_FILE.exists()
        }

        try:
            with REPORT_FILE.open(
                "w",
                encoding="utf-8"
            ) as f:
                json.dump(
                    failure,
                    f,
                    indent=2
                )
        except Exception:
            pass

        return 1


if __name__ == "__main__":
    sys.exit(main())
