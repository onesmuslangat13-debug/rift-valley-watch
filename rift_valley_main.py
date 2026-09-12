# ============================================================
# RIFT VALLEY WATCH
# COMPLETE MAIN CONTROLLER - V9
# ============================================================

import os
import json
import shutil
import subprocess
import traceback
import importlib.util
from pathlib import Path

# ------------------------------------------------------------
# PATHS
# ------------------------------------------------------------

ROOT = Path(__file__).resolve().parent

DATA_DIR = ROOT / "data"
ASSET_DIR = ROOT / "assets"
SOURCE_DIR = ASSET_DIR / "source"
AUDIO_DIR = ASSET_DIR / "audio"
OUTPUT_DIR = ROOT / "output"
SCENE_DIR = OUTPUT_DIR / "scenes"

STORY_FILE = DATA_DIR / "story.json"
SCRIPT_FILE = DATA_DIR / "script.json"

SOURCE_IMAGE = SOURCE_DIR / "story_image.jpg"
FINAL_OUTPUT = OUTPUT_DIR / "rift_valley_watch_reel.mp4"
GENERATOR_OUTPUT = OUTPUT_DIR / "rift_valley_watch.mp4"

WIDTH = 1080
HEIGHT = 1920
FPS = 30


# ------------------------------------------------------------
# REAL IMAGE FALLBACKS FOR CURRENT TEST STORY
# ------------------------------------------------------------

REAL_IMAGE_URLS = [
    (
        "https://peopledaily.digital/wp-content/uploads/"
        "2026/03/image-300-500x333.png"
    ),
    (
        "https://topnews.ke/wp-content/uploads/"
        "2026/03/WhatsApp-Image-2026-03-18-at-12.13.35-rr-1024x683.jpeg"
    ),
    (
        "https://topnews.ke/wp-content/uploads/"
        "2026/03/WhatsApp-Image-2026-03-18-at-12.13.36-66-1024x683.jpeg"
    ),
]


# ------------------------------------------------------------
# VERIFIED TEST STORY
# ------------------------------------------------------------

VERIFIED_STORY = {
    "title": "65-KM Road Project Worth KSh 2.1 Billion Underway in Bomet",
    "county": "Bomet County",
    "category": "DEVELOPMENT",
    "date": "2026-03-18",

    "source": {
        "name": "Bomet County Government",
        "url": (
            "https://bomet.go.ke/"
            "dp-kindiki-visits-bomet-to-inspect-development-projects"
        ),
        "type": "OFFICIAL_SOURCE",
    },

    "verified_facts": [
        {
            "label": "PROJECT",
            "value": (
                "Kyogong-Kapkesosio-Sigor-Chebunyo / "
                "Sigor-Lelaitich-Kipreres-Longisa road"
            ),
        },
        {
            "label": "ROAD_LENGTH",
            "value": "65 kilometres",
        },
        {
            "label": "COST",
            "value": "KSh 2.1 billion",
        },
        {
            "label": "LOCATION",
            "value": "Chepalungu Constituency, Bomet County",
        },
        {
            "label": "STATUS",
            "value": "Ongoing construction works",
        },
        {
            "label": "IMPACT",
            "value": (
                "Expected to unlock economic potential in the area "
                "and wider Bomet County"
            ),
        },
    ],

    "official_statement": {
        "available": True,
        "speaker": "Deputy President Kithure Kindiki",
        "quote": (
            "The Roads and Transport Ministry has been instructed "
            "to closely monitor road construction to ensure speedy "
            "completion and quality works."
        ),
    },

    "summary": (
        "Construction is ongoing on a 65-kilometre road project "
        "linking Kyogong, Kapkesosio, Sigor and Chebunyo, with "
        "another section running through Sigor, Lelaitich, "
        "Kipreres and Longisa in Bomet County. The Bomet County "
        "Government says the project is being constructed at a "
        "cost of KSh 2.1 billion in Chepalungu Constituency and "
        "is expected to unlock the economic potential of the area "
        "and wider county."
    ),

    "visuals": [
        {
            "type": "PROJECT_TITLE",
            "description": (
                "65-kilometre road project under construction "
                "in Bomet County"
            ),
        },
        {
            "type": "LOCATION_GRAPHIC",
            "description": (
                "Bomet County and Chepalungu Constituency"
            ),
        },
        {
            "type": "DATA_CARD",
            "description": "65 KM | KSh 2.1 billion",
        },
        {
            "type": "ROUTE_GRAPHIC",
            "description": (
                "Kyogong-Kapkesosio-Sigor-Chebunyo / "
                "Sigor-Lelaitich-Kipreres-Longisa"
            ),
        },
        {
            "type": "OFFICIAL_STATEMENT",
            "description": (
                "Deputy President Kithure Kindiki statement "
                "on road construction monitoring"
            ),
        },
        {
            "type": "SOURCE_CARD",
            "description": "Bomet County Government",
        },
    ],

    "editorial": {
        "confirmed": [
            "Construction works are ongoing.",
            "The road project covers 65 kilometres.",
            "The reported project cost is KSh 2.1 billion.",
            "The project is in Chepalungu Constituency, Bomet County.",
            (
                "The county government says the project is expected "
                "to unlock economic potential."
            ),
        ],
        "unconfirmed": [
            "Exact completion date",
            "Contractor name",
            "Exact funding breakdown",
        ],
    },
}


# ------------------------------------------------------------
# LOGGING
# ------------------------------------------------------------

def log(message=""):
    print(message, flush=True)


# ------------------------------------------------------------
# WRITE STORY
# ------------------------------------------------------------

def write_story():
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    with open(STORY_FILE, "w", encoding="utf-8") as f:
        json.dump(
            VERIFIED_STORY,
            f,
            indent=2,
            ensure_ascii=False,
        )

    log(f"Story written: {STORY_FILE}")


# ------------------------------------------------------------
# DYNAMIC NARRATION
# ------------------------------------------------------------

def build_narration(story):
    county = story.get("county", "the Rift Valley")

    source = story.get("source", {})
    source_name = source.get(
        "name",
        "the verified source"
    )

    date = story.get("date", "")

    facts = {
        item.get("label", "").upper(): item.get("value", "")
        for item in story.get("verified_facts", [])
    }

    project = facts.get("PROJECT", "")
    road_length = facts.get(
        "ROAD_LENGTH",
        "the reported distance"
    )
    cost = facts.get(
        "COST",
        "the reported project cost"
    )
    location = facts.get(
        "LOCATION",
        county
    )
    status = facts.get(
        "STATUS",
        "work is ongoing"
    )
    impact = facts.get(
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

    segments = [
        (
            f"{source_name} says {status.lower()} "
            f"on a {road_length} project in {location}."
        ),

        (
            f"The project covers {project}."
            if project
            else f"The project is located in {location}."
        ),

        (
            f"The reported project cost is {cost}."
        ),

        (
            f"According to {source_name.lower()}, "
            f"{impact.lower()}."
            if impact
            else
            f"The project is expected to support economic "
            f"activity in {county}."
        ),

        (
            f"{speaker} said the authorities had been instructed "
            f"to closely monitor the construction to ensure "
            f"speedy completion and quality works."
            if speaker
            else
            "Authorities have been urged to closely monitor "
            "the construction work."
        ),

        (
            f"This report is based on information from "
            f"{source_name} and is dated {date}."
        ),

        (
            f"{speaker} said: {quote}"
            if speaker and quote
            else
            f"The official source is {source_name}."
        ),

        (
            f"Rift Valley Watch. Verified regional news "
            f"from {county}. Follow for more."
        ),
    ]

    return segments


# ------------------------------------------------------------
# WRITE SCRIPT
# ------------------------------------------------------------

def write_script(story):
    segments = build_narration(story)

    script = {
        "story_title": story.get("title", ""),
        "county": story.get("county", ""),
        "source": story.get("source", {}).get(
            "name",
            ""
        ),
        "segments": [
            {
                "index": i,
                "text": text,
            }
            for i, text in enumerate(segments)
        ],
    }

    with open(SCRIPT_FILE, "w", encoding="utf-8") as f:
        json.dump(
            script,
            f,
            indent=2,
            ensure_ascii=False,
        )

    return segments


# ------------------------------------------------------------
# IMAGE VALIDATION
# ------------------------------------------------------------

def validate_image(path):
    try:
        from PIL import Image

        p = Path(path)

        if not p.exists():
            return False

        if p.stat().st_size < 10000:
            return False

        with Image.open(p) as img:
            width, height = img.size

            if width < 300 or height < 200:
                return False

            img.verify()

        return True

    except Exception:
        return False


# ------------------------------------------------------------
# DOWNLOAD REAL IMAGE
# ------------------------------------------------------------

def download_real_image():
    import requests
    from PIL import Image
    from io import BytesIO

    SOURCE_DIR.mkdir(parents=True, exist_ok=True)

    for old_file in SOURCE_DIR.glob("*"):
        try:
            old_file.unlink()
        except Exception:
            pass

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/153.0 Safari/537.36"
        ),
        "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
    }

    for index, url in enumerate(REAL_IMAGE_URLS, 1):

        log("")
        log(f"IMAGE FALLBACK {index}/{len(REAL_IMAGE_URLS)}")
        log(url)

        try:
            response = requests.get(
                url,
                headers=headers,
                timeout=30,
            )

            response.raise_for_status()

            image = Image.open(
                BytesIO(response.content)
            )

            image.load()

            if image.width < 300 or image.height < 200:
                raise RuntimeError(
                    "Image dimensions too small."
                )

            if image.mode not in ("RGB", "L"):
                image = image.convert("RGB")
            else:
                image = image.convert("RGB")

            image.save(
                SOURCE_IMAGE,
                "JPEG",
                quality=95,
            )

            if validate_image(SOURCE_IMAGE):

                log("")
                log(
                    f"REAL IMAGE FOUND: "
                    f"{SOURCE_IMAGE}"
                )

                return SOURCE_IMAGE

        except Exception as exc:
            log(
                f"Image failed: {type(exc).__name__}: {exc}"
            )

    raise RuntimeError(
        "No usable real article image could be recovered."
    )


# ------------------------------------------------------------
# LOAD VIDEO GENERATOR
# ------------------------------------------------------------

def load_generator():

    generator_path = (
        ROOT / "rift_valley_video_generator.py"
    )

    if not generator_path.exists():
        raise FileNotFoundError(
            f"Missing renderer: {generator_path}"
        )

    spec = importlib.util.spec_from_file_location(
        "rift_valley_video_generator",
        generator_path,
    )

    if spec is None or spec.loader is None:
        raise RuntimeError(
            "Could not load video generator."
        )

    generator = importlib.util.module_from_spec(spec)

    spec.loader.exec_module(generator)

    return generator


# ------------------------------------------------------------
# CONFIGURE GENERATOR
# ------------------------------------------------------------

def configure_generator(generator):

    generator.ROOT = ROOT
    generator.STORY_FILE = STORY_FILE
    generator.SCRIPT_FILE = SCRIPT_FILE

    generator.OUTPUT_DIR = OUTPUT_DIR
    generator.ASSET_DIR = ASSET_DIR
    generator.SOURCE_IMAGE_DIR = SOURCE_DIR
    generator.AUDIO_DIR = AUDIO_DIR
    generator.SCENE_DIR = SCENE_DIR

    generator.OUTPUT_FILE = GENERATOR_OUTPUT

    generator.WIDTH = WIDTH
    generator.HEIGHT = HEIGHT
    generator.FPS = FPS


# ------------------------------------------------------------
# FORCE LOCAL REAL IMAGE
# ------------------------------------------------------------

def patch_image_discovery(generator, source_image):

    def find_source_image(*args, **kwargs):
        return str(source_image)

    generator.find_source_image = find_source_image


# ------------------------------------------------------------
# SAFE SOURCE SCENE
# ------------------------------------------------------------

def patch_source_scene(generator, story):

    if not hasattr(generator, "scene_source"):
        return

    original = generator.scene_source

    def safe_source_scene(*args, **kwargs):

        try:
            return original(
                *args,
                **kwargs,
            )
        except Exception:

            try:
                from PIL import Image, ImageDraw, ImageFont

                image = Image.new(
                    "RGB",
                    (WIDTH, HEIGHT),
                    (12, 18, 28),
                )

                draw = ImageDraw.Draw(image)

                font = ImageFont.truetype(
                    "/usr/share/fonts/truetype/dejavu/"
                    "DejaVuSans-Bold.ttf",
                    58,
                )

                small = ImageFont.truetype(
                    "/usr/share/fonts/truetype/dejavu/"
                    "DejaVuSans.ttf",
                    36,
                )

                source_name = (
                    story.get("source", {})
                    .get(
                        "name",
                        "Verified Source",
                    )
                )

                county = story.get(
                    "county",
                    "",
                )

                draw.text(
                    (70, 650),
                    "SOURCE",
                    font=font,
                    fill="white",
                )

                draw.text(
                    (70, 760),
                    source_name.upper(),
                    font=font,
                    fill="white",
                )

                draw.text(
                    (70, 860),
                    "OFFICIAL SOURCE",
                    font=small,
                    fill="white",
                )

                draw.text(
                    (70, 930),
                    county,
                    font=small,
                    fill="white",
                )

                return image

            except Exception:
                return None

    generator.scene_source = safe_source_scene


# ------------------------------------------------------------
# SAFE SCENE VIDEO CREATOR
# ------------------------------------------------------------

def patch_scene_video(generator):

    if not hasattr(generator, "create_scene_video"):
        return

    def safe_create_scene_video(
        image_path,
        audio_path,
        output_path,
        caption=None,
        *args,
        **kwargs,
    ):

        output_path = Path(output_path)
        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        image_path = Path(image_path)
        audio_path = Path(audio_path)

        if not image_path.exists():
            raise RuntimeError(
                f"Scene image missing: {image_path}"
            )

        if not audio_path.exists():
            raise RuntimeError(
                f"Scene audio missing: {audio_path}"
            )

        subtitle_text = (
            str(caption or "")
            .replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace(":", "\\:")
            .replace(",", "\\,")
            .replace("[", "\\[")
            .replace("]", "\\]")
        )

        vf = (
            "scale=1080:1920:"
            "force_original_aspect_ratio=increase,"
            "crop=1080:1920,"
            "setsar=1"
        )

        if subtitle_text:
            vf += (
                ",subtitles='"
                + str(audio_path)
                + "'"
            )

        cmd = [
            "ffmpeg",
            "-y",
            "-loop",
            "1",
            "-i",
            str(image_path),
            "-i",
            str(audio_path),
            "-vf",
            vf,
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
            "-shortest",
            "-r",
            str(FPS),
            "-movflags",
            "+faststart",
            str(output_path),
        ]

        subprocess.run(
            cmd,
            check=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if not output_path.exists():
            raise RuntimeError(
                f"Scene was not created: {output_path}"
            )

        return str(output_path)

    generator.create_scene_video = safe_create_scene_video


# ------------------------------------------------------------
# AUDIO CREATION
# ------------------------------------------------------------

def create_audio(generator, text, index):

    AUDIO_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    output = (
        AUDIO_DIR /
        f"narration_{index + 1:02d}.mp3"
    )

    if output.exists():
        output.unlink()

    if hasattr(generator, "create_audio"):

        try:
            result = generator.create_audio(
                text,
                str(output),
            )

            if result and Path(result).exists():
                return Path(result)

            if output.exists():
                return output

        except TypeError:
            pass

    from gtts import gTTS

    tts = gTTS(
        text=text,
        lang="en",
        slow=False,
    )

    tts.save(str(output))

    if not output.exists():
        raise RuntimeError(
            f"Audio was not created: {output}"
        )

    return output


# ------------------------------------------------------------
# AUDIO + SCENE BUILD
# ------------------------------------------------------------

def build_video(
    generator,
    story,
    source_image,
):

    log("")
    log("=" * 70)
    log("BUILDING RIFT VALLEY WATCH")
    log("=" * 70)

    narration = build_narration(story)

    if len(narration) != 8:
        raise RuntimeError(
            f"Expected 8 narration segments, "
            f"got {len(narration)}."
        )

    log("")
    log("NARRATION SEGMENTS: 8")

    audio_files = []

    for index, text in enumerate(narration):

        log(
            f"Creating audio {index + 1}/8..."
        )

        audio = create_audio(
            generator,
            text,
            index,
        )

        audio_files.append(audio)

    # --------------------------------------------------------
    # SCENE PLAN
    # --------------------------------------------------------

    scene_plan = [
        (
            "VISUAL EVIDENCE",
            source_image,
            0,
        ),
        (
            "WHERE IT IS",
            None,
            1,
        ),
        (
            "KEY FACTS",
            None,
            2,
        ),
        (
            "THE ROUTE",
            None,
            3,
        ),
        (
            "WHY IT MATTERS",
            None,
            4,
        ),
        (
            "OFFICIAL STATEMENT",
            None,
            5,
        ),
        (
            "SOURCE",
            None,
            6,
        ),
        (
            "OUTRO",
            None,
            7,
        ),
    ]

    SCENE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    scene_files = []

    for index, (
        scene_name,
        scene_image,
        narration_index,
    ) in enumerate(scene_plan):

        log("")
        log(
            f"SCENE {index + 1}/8: "
            f"{scene_name}"
        )

        # ----------------------------------------------------
        # GENERATE VISUAL
        # ----------------------------------------------------

        if scene_image is not None:
            image_path = Path(scene_image)

        else:

            image_path = None

            function_map = {
                "WHERE IT IS": "scene_location",
                "KEY FACTS": "scene_facts",
                "THE ROUTE": "scene_route",
                "WHY IT MATTERS": "scene_impact",
                "OFFICIAL STATEMENT": "scene_statement",
                "SOURCE": "scene_source",
                "OUTRO": "scene_outro",
            }

            function_name = function_map.get(
                scene_name
            )

            if function_name and hasattr(
                generator,
                function_name,
            ):

                function = getattr(
                    generator,
                    function_name,
                )

                try:

                    result = function(
                        story
                    )

                    if result is not None:

                        if isinstance(
                            result,
                            (str, Path),
                        ):
                            image_path = Path(
                                result
                            )

                        else:

                            generated = (
                                SCENE_DIR /
                                f"scene_{index + 1:02d}.png"
                            )

                            if hasattr(
                                result,
                                "save",
                            ):
                                result.save(
                                    generated
                                )
                                image_path = generated

                except Exception as exc:
                    log(
                        f"Visual function warning: "
                        f"{exc}"
                    )

            # ------------------------------------------------
            # FALLBACK TO REAL ARTICLE PHOTO
            # ------------------------------------------------

            if (
                image_path is None
                or not image_path.exists()
            ):
                image_path = Path(
                    source_image
                )

        if not image_path.exists():
            raise RuntimeError(
                f"No image available for "
                f"scene {index + 1}: "
                f"{scene_name}"
            )

        output_scene = (
            SCENE_DIR /
            f"scene_{index + 1:02d}.mp4"
        )

        caption = scene_name

        generator.create_scene_video(
            str(image_path),
            str(
                audio_files[
                    narration_index
                ]
            ),
            str(output_scene),
            caption,
        )

        if not output_scene.exists():
            raise RuntimeError(
                f"Scene video missing: "
                f"{output_scene}"
            )

        scene_files.append(
            output_scene
        )

    # --------------------------------------------------------
    # CONCATENATE
    # --------------------------------------------------------

    log("")
    log("CONCATENATING SCENES...")

    if hasattr(
        generator,
        "concat_scenes",
    ):

        result = generator.concat_scenes(
            [
                str(x)
                for x in scene_files
            ],
            str(GENERATOR_OUTPUT),
        )

        if result:
            generator_output = Path(result)
        else:
            generator_output = Path(
                GENERATOR_OUTPUT
            )

    else:

        concat_file = (
            OUTPUT_DIR /
            "scene_concat.txt"
        )

        with open(
            concat_file,
            "w",
            encoding="utf-8",
        ) as f:

            for scene in scene_files:
                safe = (
                    str(scene)
                    .replace("'", "'\\''")
                )

                f.write(
                    f"file '{safe}'\n"
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
                "-c",
                "copy",
                str(GENERATOR_OUTPUT),
            ],
            check=True,
        )

        generator_output = Path(
            GENERATOR_OUTPUT
        )

    if not generator_output.exists():
        raise RuntimeError(
            "Final generator MP4 was not created."
        )

    # --------------------------------------------------------
    # FINAL COPY
    # --------------------------------------------------------

    shutil.copy2(
        generator_output,
        FINAL_OUTPUT,
    )

    if not FINAL_OUTPUT.exists():
        raise RuntimeError(
            "Final Rift Valley Watch MP4 "
            "was not created."
        )

    # --------------------------------------------------------
    # FFMPEG VALIDATION
    # --------------------------------------------------------

    log("")
    log("RUNNING FINAL VIDEO CHECK...")

    probe = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-show_entries",
            "stream=width,height,codec_name",
            "-of",
            "default=noprint_wrappers=1",
            str(FINAL_OUTPUT),
        ],
        capture_output=True,
        text=True,
    )

    if probe.returncode != 0:
        raise RuntimeError(
            "ffprobe validation failed."
        )

    log(probe.stdout)

    return FINAL_OUTPUT


# ------------------------------------------------------------
# MAIN
# ------------------------------------------------------------

def main():

    try:

        log("")
        log("=" * 70)
        log("RIFT VALLEY WATCH - V9")
        log("=" * 70)

        # ----------------------------------------------------
        # DIRECTORIES
        # ----------------------------------------------------

        for directory in [
            DATA_DIR,
            ASSET_DIR,
            SOURCE_DIR,
            AUDIO_DIR,
            OUTPUT_DIR,
            SCENE_DIR,
        ]:
            directory.mkdir(
                parents=True,
                exist_ok=True,
            )

        # ----------------------------------------------------
        # STORY
        # ----------------------------------------------------

        write_story()

        narration = write_script(
            VERIFIED_STORY
        )

        log("")
        log(
            f"Story: "
            f"{VERIFIED_STORY['title']}"
        )

        log(
            f"County: "
            f"{VERIFIED_STORY['county']}"
        )

        log(
            f"Source: "
            f"{VERIFIED_STORY['source']['name']}"
        )

        log(
            f"Narration segments: "
            f"{len(narration)}"
        )

        # ----------------------------------------------------
        # REAL IMAGE
        # ----------------------------------------------------

        source_image = (
            download_real_image()
        )

        # ----------------------------------------------------
        # GENERATOR
        # ----------------------------------------------------

        log("")
        log("Loading video generator...")

        generator = load_generator()

        configure_generator(
            generator
        )

        patch_image_discovery(
            generator,
            source_image,
        )

        patch_source_scene(
            generator,
            VERIFIED_STORY,
        )

        patch_scene_video(
            generator,
        )

        # ----------------------------------------------------
        # BUILD
        # ----------------------------------------------------

        final_output = build_video(
            generator,
            VERIFIED_STORY,
            source_image,
        )

        log("")
        log("=" * 70)
        log("RIFT VALLEY WATCH BUILD SUCCESSFUL")
        log("=" * 70)

        log(
            f"REAL IMAGE: {source_image}"
        )

        log(
            f"OUTPUT: {final_output}"
        )

        log(
            f"SIZE: "
            f"{final_output.stat().st_size / 1024 / 1024:.2f} MB"
        )

        return 0

    except Exception as exc:

        log("")
        log("=" * 70)
        log("RIFT VALLEY WATCH FAILED")
        log("=" * 70)

        log(
            f"{type(exc).__name__}: {exc}"
        )

        traceback.print_exc()

        return 1


if __name__ == "__main__":
    raise SystemExit(main())
