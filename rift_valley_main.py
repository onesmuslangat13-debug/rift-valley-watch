# ============================================================
# RIFT VALLEY WATCH
# COMPLETE MAIN CONTROLLER - V8
# ============================================================

import os
import json
import shutil
import subprocess
import traceback
from pathlib import Path

# ------------------------------------------------------------
# REPOSITORY ROOT
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
# REAL IMAGE FALLBACKS
# These are real publisher-hosted images associated with
# the verified Bomet road-project report.
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
# VERIFIED STORY
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
        "type": "OFFICIAL_SOURCE"
    },

    "verified_facts": [
        {
            "label": "PROJECT",
            "value": (
                "Kyogong-Kapkesosio-Sigor-Chebunyo / "
                "Sigor-Lelaitich-Kipreres-Longisa road"
            )
        },
        {
            "label": "ROAD_LENGTH",
            "value": "65 kilometres"
        },
        {
            "label": "COST",
            "value": "KSh 2.1 billion"
        },
        {
            "label": "LOCATION",
            "value": "Chepalungu Constituency, Bomet County"
        },
        {
            "label": "STATUS",
            "value": "Ongoing construction works"
        },
        {
            "label": "IMPACT",
            "value": (
                "Expected to unlock economic potential in the area "
                "and wider Bomet County"
            )
        }
    ],

    "official_statement": {
        "available": True,
        "speaker": "Deputy President Kithure Kindiki",
        "quote": (
            "The Roads and Transport Ministry has been instructed "
            "to closely monitor road construction to ensure speedy "
            "completion and quality works."
        )
    },

    "summary": (
        "Construction is ongoing on a 65-kilometre road project "
        "linking Kyogong, Kapkesosio, Sigor and Chebunyo, with "
        "another section running through Sigor, Lelaitich, "
        "Kipreres and Longisa in Bomet County. The Bomet County "
        "Government says the project is being constructed at a "
        "cost of KSh 2.1 billion in Chepalungu Constituency and "
        "is expected to unlock the economic potential of the "
        "area and wider county."
    ),

    "visuals": [
        {
            "type": "PROJECT_TITLE",
            "description": (
                "65-kilometre road project under construction "
                "in Bomet County"
            )
        },
        {
            "type": "LOCATION_GRAPHIC",
            "description": (
                "Bomet County and Chepalungu Constituency"
            )
        },
        {
            "type": "DATA_CARD",
            "description": "65 KM | KSh 2.1 billion"
        },
        {
            "type": "ROUTE_GRAPHIC",
            "description": (
                "Kyogong-Kapkesosio-Sigor-Chebunyo / "
                "Sigor-Lelaitich-Kipreres-Longisa"
            )
        },
        {
            "type": "OFFICIAL_STATEMENT",
            "description": (
                "Deputy President Kithure Kindiki statement "
                "on road construction monitoring"
            )
        },
        {
            "type": "SOURCE_CARD",
            "description": "Bomet County Government"
        }
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
            )
        ],
        "unconfirmed": [
            "Exact completion date",
            "Contractor name",
            "Exact funding breakdown"
        ]
    }
}


# ============================================================
# BASIC HELPERS
# ============================================================

def log(message):
    print(message, flush=True)


def ensure_directories():
    for directory in (
        DATA_DIR,
        ASSET_DIR,
        SOURCE_DIR,
        AUDIO_DIR,
        OUTPUT_DIR,
        SCENE_DIR,
    ):
        directory.mkdir(parents=True, exist_ok=True)


def run(command, cwd=None):
    command = [str(x) for x in command]

    log("")
    log("$ " + " ".join(command))

    result = subprocess.run(
        command,
        cwd=str(cwd) if cwd else None,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    print(result.stdout, flush=True)

    if result.returncode != 0:
        raise RuntimeError(
            "Command failed with exit code "
            f"{result.returncode}"
        )

    return result.stdout


# ============================================================
# STORY
# ============================================================

def write_story():
    STORY_FILE.write_text(
        json.dumps(
            VERIFIED_STORY,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )

    log(f"STORY: {STORY_FILE}")


def write_script():
    segments = [
        (
            "The Bomet County Government says construction is "
            "ongoing on a 65-kilometre road project in "
            "Chepalungu Constituency."
        ),

        (
            "The project covers the Kyogong, Kapkesosio, Sigor "
            "and Chebunyo route, as well as the Sigor, Lelaitich, "
            "Kipreres and Longisa section."
        ),

        (
            "The reported project cost is two point one billion "
            "Kenya shillings."
        ),

        (
            "According to the county government, the project is "
            "expected to unlock the economic potential of the "
            "area and the wider Bomet County."
        ),

        (
            "Deputy President Kithure Kindiki said the Roads and "
            "Transport Ministry had been instructed to closely "
            "monitor construction to ensure speedy completion "
            "and quality works."
        ),

        (
            "This report is based on the Bomet County Government "
            "and is dated March 18, 2026."
        ),

        (
            "Rift Valley Watch. Verified regional news. "
            "Follow for more."
        )
    ]

    script = {
        "title": VERIFIED_STORY["title"],
        "full_script": " ".join(segments),
        "segments": segments,
        "source": VERIFIED_STORY["source"]["name"],
        "date": VERIFIED_STORY["date"]
    }

    SCRIPT_FILE.write_text(
        json.dumps(
            script,
            indent=2,
            ensure_ascii=False
        ),
        encoding="utf-8"
    )


# ============================================================
# IMAGE RECOVERY
# ============================================================

def download_real_image():
    import urllib.request

    SOURCE_DIR.mkdir(parents=True, exist_ok=True)

    log("")
    log("=" * 70)
    log("REAL IMAGE RECOVERY")
    log("=" * 70)

    for old_file in SOURCE_DIR.glob("story_image.*"):
        try:
            old_file.unlink()
        except Exception:
            pass

    for index, url in enumerate(REAL_IMAGE_URLS, start=1):

        log("")
        log(f"IMAGE ATTEMPT {index}")
        log(url)

        temp = SOURCE_DIR / f"_source_{index}.tmp"

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
                    "Accept": "image/avif,image/webp,image/apng,"
                              "image/svg+xml,image/*,*/*;q=0.8"
                }
            )

            with urllib.request.urlopen(
                request,
                timeout=40
            ) as response:

                data = response.read()

            if len(data) < 10000:
                log("Rejected: image file too small.")
                continue

            temp.write_bytes(data)

            from PIL import Image

            with Image.open(temp) as image:
                width, height = image.size
                image.load()

            log(
                f"Downloaded image: "
                f"{width}x{height}, {len(data)} bytes"
            )

            if width < 400 or height < 300:
                log("Rejected: dimensions too small.")
                continue

            # Convert everything to a clean JPEG.
            final = SOURCE_IMAGE

            with Image.open(temp) as image:
                image = image.convert("RGB")
                image.save(
                    final,
                    "JPEG",
                    quality=94,
                    optimize=True
                )

            temp.unlink(missing_ok=True)

            if final.exists() and final.stat().st_size > 10000:
                log("")
                log("REAL IMAGE FOUND:")
                log(str(final))
                log(f"SOURCE URL: {url}")

                return final, [url]

        except Exception as exc:
            log(
                f"Image attempt failed: "
                f"{type(exc).__name__}: {exc}"
            )

        finally:
            temp.unlink(missing_ok=True)

    raise RuntimeError(
        "No usable real article image was recovered."
    )


# ============================================================
# IMPORT RENDERER
# ============================================================

def load_generator():
    import importlib.util

    generator_file = (
        ROOT / "rift_valley_video_generator.py"
    )

    if not generator_file.exists():
        raise RuntimeError(
            f"Missing renderer: {generator_file}"
        )

    spec = importlib.util.spec_from_file_location(
        "rift_valley_video_generator",
        generator_file
    )

    generator = importlib.util.module_from_spec(spec)

    spec.loader.exec_module(generator)

    return generator


# ============================================================
# SAFE PATH CONFIGURATION
# ============================================================

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
    generator.REPORT_FILE = (
        DATA_DIR / "visual_report.json"
    )

    generator.WIDTH = WIDTH
    generator.HEIGHT = HEIGHT
    generator.FPS = FPS


# ============================================================
# FORCE LOCAL REAL IMAGE
# ============================================================

def patch_image_discovery(generator, source_image, candidates):
    def forced_image(_story):
        log("")
        log("FORCED REAL IMAGE:")
        log(str(source_image))
        return source_image, candidates

    generator.find_source_image = forced_image


# ============================================================
# SOURCE CARD WITHOUT RAW URL
# ============================================================

def patch_source_scene(generator):
    from PIL import Image, ImageDraw

    def safe_scene_source(story):

        image = generator.create_background()
        draw = ImageDraw.Draw(image)

        generator.add_grid(draw)
        generator.top_bar(draw)
        generator.section_label(draw, "SOURCE")

        draw.text(
            (65, 340),
            "BOMET COUNTY GOVERNMENT",
            font=generator.get_font(42, True),
            fill=(240, 240, 245)
        )

        draw.text(
            (65, 470),
            "OFFICIAL SOURCE",
            font=generator.get_font(30, True),
            fill=(230, 55, 65)
        )

        generator.draw_wrapped(
            draw,
            (
                "Report dated March 18, 2026. "
                "The story concerns the ongoing "
                "65-kilometre road project in "
                "Chepalungu Constituency."
            ),
            (65, 550, WIDTH - 65, 1050),
            generator.get_font(38, False),
            max_lines=9,
            line_spacing=16
        )

        draw.text(
            (65, 1130),
            "SOURCE",
            font=generator.get_font(28, True),
            fill=(230, 55, 65)
        )

        draw.text(
            (65, 1200),
            "Bomet County Government",
            font=generator.get_font(48, True),
            fill=(240, 240, 245)
        )

        generator.source_badge(draw, story)
        generator.footer(draw, story)

        return image

    generator.scene_source = safe_scene_source


# ============================================================
# SAFE FFMPEG SCENE RENDERER
# Fixes force_original_aspect_ratio=cover
# ============================================================

def patch_scene_video(generator):

    def safe_create_scene_video(
        image_path,
        audio_path,
        caption_text,
        scene_number
    ):

        duration = generator.audio_duration(
            audio_path
        )

        srt_path = generator.create_srt(
            caption_text,
            duration,
            scene_number
        )

        output = (
            SCENE_DIR /
            f"scene_{scene_number:02d}.mp4"
        )

        subtitle_path = (
            str(srt_path.resolve())
            .replace("\\", "/")
            .replace(":", r"\:")
        )

        # IMPORTANT:
        # Do NOT use:
        # force_original_aspect_ratio=cover
        #
        # Use increase + crop, which works reliably
        # on GitHub Actions FFmpeg builds.

        filter_text = (
            f"scale={WIDTH}:{HEIGHT}:"
            f"force_original_aspect_ratio=increase,"
            f"crop={WIDTH}:{HEIGHT},"
            f"setsar=1,"
            f"subtitles='{subtitle_path}':"
            f"force_style='FontName=DejaVu Sans,"
            f"FontSize=22,"
            f"Bold=1,"
            f"PrimaryColour=&H00FFFFFF,"
            f"OutlineColour=&H00101010,"
            f"BorderStyle=1,"
            f"Outline=3,"
            f"Shadow=1,"
            f"Alignment=2,"
            f"MarginV=95'"
        )

        generator.run_command(
            [
                "ffmpeg",
                "-y",
                "-loop",
                "1",
                "-i",
                str(image_path),
                "-i",
                str(audio_path),
                "-vf",
                filter_text,
                "-t",
                f"{duration:.3f}",
                "-r",
                str(FPS),
                "-c:v",
                "libx264",
                "-preset",
                "medium",
                "-crf",
                "20",
                "-pix_fmt",
                "yuv420p",
                "-c:a",
                "aac",
                "-b:a",
                "160k",
                "-ar",
                "48000",
                "-shortest",
                str(output)
            ]
        )

        if (
            not output.exists()
            or output.stat().st_size < 10000
        ):
            raise RuntimeError(
                f"Scene video was not created: {output}"
            )

        return (
            output,
            duration,
            srt_path
        )

    generator.create_scene_video = (
        safe_create_scene_video
    )


# ============================================================
# BUILD VIDEO DIRECTLY
# DO NOT CALL generator.main()
# ============================================================

def build_video(generator, story, source_image, candidates):

    log("")
    log("=" * 70)
    log("BUILDING RIFT VALLEY WATCH")
    log("=" * 70)

    narration_segments = (
        generator.build_narration_segments(
            story
        )
    )

    if not narration_segments:
        raise RuntimeError(
            "No narration segments were created."
        )

    log("")
    log("=" * 70)
    log("CREATING NARRATION")
    log("=" * 70)

    audio_files = []

    for index, text in enumerate(
        narration_segments
    ):
        log("")
        log(
            f"NARRATION {index + 1}/"
            f"{len(narration_segments)}"
        )
        log(text)

        audio_files.append(
            generator.create_audio(
                text,
                index
            )
        )

    if len(audio_files) < 7:
        raise RuntimeError(
            "Narration pipeline returned fewer "
            "than 7 audio segments."
        )

    # --------------------------------------------------------
    # EXACT 8-SCENE PLAN
    # --------------------------------------------------------

    scene_plan = [
        (
            "VISUAL EVIDENCE",
            source_image,
            0
        ),
        (
            "WHERE IT IS",
            None,
            1
        ),
        (
            "KEY FACTS",
            None,
            2
        ),
        (
            "THE ROUTE",
            None,
            3
        ),
        (
            "WHY IT MATTERS",
            None,
            4
        ),
        (
            "OFFICIAL STATEMENT",
            None,
            5
        ),
        (
            "SOURCE",
            None,
            6
        ),
        (
            "OUTRO",
            None,
            7
        )
    ]

    scene_files = []
    scene_records = []

    log("")
    log("=" * 70)
    log("RENDERING SCENES")
    log("=" * 70)

    for scene_number, (
        name,
        scene_image,
        narration_index
    ) in enumerate(
        scene_plan,
        start=1
    ):

        log("")
        log(
            f"SCENE {scene_number}/"
            f"{len(scene_plan)}: {name}"
        )

        if name == "VISUAL EVIDENCE":

            image = generator.scene_photo(
                story,
                scene_image
            )

        elif name == "WHERE IT IS":

            image = generator.scene_location(
                story
            )

        elif name == "KEY FACTS":

            image = generator.scene_facts(
                story
            )

        elif name == "THE ROUTE":

            image = generator.scene_route(
                story
            )

        elif name == "WHY IT MATTERS":

            image = generator.scene_impact(
                story
            )

        elif name == "OFFICIAL STATEMENT":

            image = generator.scene_statement(
                story
            )

        elif name == "SOURCE":

            image = generator.scene_source(
                story
            )

        elif name == "OUTRO":

            image = generator.scene_outro(
                story
            )

        else:
            raise RuntimeError(
                f"Unknown scene: {name}"
            )

        image_path = generator.save_scene(
            image,
            scene_number
        )

        audio_path = audio_files[
            narration_index
        ]

        caption_text = narration_segments[
            narration_index
        ]

        scene_video, duration, srt_path = (
            generator.create_scene_video(
                image_path,
                audio_path,
                caption_text,
                scene_number
            )
        )

        scene_files.append(
            scene_video
        )

        scene_records.append(
            {
                "scene": scene_number,
                "name": name,
                "image": str(image_path),
                "video": str(scene_video),
                "audio": str(audio_path),
                "caption_file": str(srt_path),
                "duration_seconds": round(
                    duration,
                    2
                )
            }
        )

        log(
            f"SCENE COMPLETE: "
            f"{scene_video}"
        )

    if not scene_files:
        raise RuntimeError(
            "No scene videos were generated."
        )

    # --------------------------------------------------------
    # FINAL CONCATENATION
    # --------------------------------------------------------

    log("")
    log("=" * 70)
    log("FINAL ASSEMBLY")
    log("=" * 70)

    final_mp4 = generator.concat_scenes(
        scene_files
    )

    if not final_mp4.exists():
        raise RuntimeError(
            "FFmpeg reported completion but final "
            "MP4 does not exist."
        )

    # --------------------------------------------------------
    # COPY TO REQUESTED REEL NAME
    # --------------------------------------------------------

    shutil.copy2(
        final_mp4,
        FINAL_OUTPUT
    )

    log("")
    log(f"FINAL MP4: {FINAL_OUTPUT}")

    # --------------------------------------------------------
    # FINAL QC
    # --------------------------------------------------------

    log("")
    log("=" * 70)
    log("FINAL QUALITY CONTROL")
    log("=" * 70)

    qc = generator.validate_final_mp4(
        FINAL_OUTPUT
    )

    log("")
    log(
        json.dumps(
            qc,
            indent=2
        )
    )

    # --------------------------------------------------------
    # VISUAL REPORT
    # --------------------------------------------------------

    try:
        generator.write_visual_report(
            story,
            scene_records,
            candidates,
            source_image
        )
    except Exception as exc:
        log(
            "Visual report warning: "
            f"{type(exc).__name__}: {exc}"
        )

    # --------------------------------------------------------
    # EXTRA FFPROBE QC
    # --------------------------------------------------------

    probe = run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration,size",
            "-show_entries",
            "stream=codec_type,codec_name,width,height",
            "-of",
            "json",
            str(FINAL_OUTPUT)
        ]
    )

    probe_data = json.loads(probe)

    (DATA_DIR / "final_qc.json").write_text(
        json.dumps(
            {
                "passed": True,
                "output": str(FINAL_OUTPUT),
                "ffprobe": probe_data
            },
            indent=2
        ),
        encoding="utf-8"
    )

    return FINAL_OUTPUT, qc


# ============================================================
# MAIN
# ============================================================

def main():

    log("")
    log("=" * 70)
    log("RIFT VALLEY WATCH V8")
    log("=" * 70)

    ensure_directories()

    # --------------------------------------------------------
    # ALWAYS USE THE VERIFIED STORY
    # --------------------------------------------------------

    write_story()
    write_script()

    # --------------------------------------------------------
    # REAL IMAGE
    # --------------------------------------------------------

    source_image, candidates = (
        download_real_image()
    )

    # --------------------------------------------------------
    # LOAD RENDERER
    # --------------------------------------------------------

    generator = load_generator()

    configure_generator(
        generator
    )

    # --------------------------------------------------------
    # PATCH BROKEN PARTS
    # --------------------------------------------------------

    patch_image_discovery(
        generator,
        source_image,
        candidates
    )

    patch_source_scene(
        generator
    )

    patch_scene_video(
        generator
    )

    # --------------------------------------------------------
    # RUN DIRECT PIPELINE
    # --------------------------------------------------------

    try:

        final_output, qc = build_video(
            generator,
            VERIFIED_STORY,
            source_image,
            candidates
        )

        log("")
        log("=" * 70)
        log("RIFT VALLEY WATCH COMPLETE")
        log("=" * 70)

        log(
            f"OUTPUT: {final_output}"
        )

        log(
            f"DURATION: "
            f"{qc['duration_seconds']:.2f} seconds"
        )

        log(
            f"SIZE: "
            f"{qc['size_bytes'] / (1024 * 1024):.2f} MB"
        )

        log(
            f"RESOLUTION: "
            f"{qc['width']}x{qc['height']}"
        )

        log(
            f"VIDEO: {qc['video_codec']}"
        )

        log(
            f"AUDIO: {qc['audio_codec']}"
        )

        log("")
        log("AUTOMATIC QC PASSED.")
        log("VIDEO GENERATION COMPLETED SUCCESSFULLY.")

    except Exception as exc:

        log("")
        log("=" * 70)
        log("RIFT VALLEY WATCH FAILED")
        log("=" * 70)

        log(
            f"{type(exc).__name__}: {exc}"
        )

        log("")
        log("FULL TRACEBACK:")
        traceback.print_exc()

        raise


if __name__ == "__main__":
    main()
