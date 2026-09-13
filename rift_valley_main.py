# ============================================================
# FINAL QC
# ============================================================

def verify_final_video(path):
    path = Path(path)

    if not path.exists():
        raise RuntimeError(
            "Final MP4 does not exist."
        )

    size = path.stat().st_size

    if size < 100_000:
        raise RuntimeError(
            "Final MP4 is suspiciously small."
        )

    command = [
        "ffprobe",
        "-v",
        "error",

        "-show_entries",
        "stream="
        "codec_type,"
        "codec_name,"
        "width,"
        "height,"
        "duration,"
        "r_frame_rate",

        "-show_entries",
        "format="
        "duration,"
        "size",

        "-of",
        "json",

        str(path),
    ]

    result = subprocess.run(
        command,
        capture_output=True,
        text=True,
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"FFprobe failed with exit code {result.returncode}"
        )

    try:
        probe = json.loads(result.stdout)
    except Exception as exc:
        raise RuntimeError(
            f"FFprobe returned invalid JSON: {exc}"
        )

    streams = probe.get("streams", [])

    video_stream = next(
        (
            stream
            for stream in streams
            if stream.get("codec_type") == "video"
        ),
        None,
    )

    audio_stream = next(
        (
            stream
            for stream in streams
            if stream.get("codec_type") == "audio"
        ),
        None,
    )

    if video_stream is None:
        raise RuntimeError(
            "Final MP4 contains no video stream."
        )

    if audio_stream is None:
        raise RuntimeError(
            "Final MP4 contains no audio stream."
        )

    width = int(
        video_stream.get("width") or 0
    )

    height = int(
        video_stream.get("height") or 0
    )

    if width != VIDEO_WIDTH or height != VIDEO_HEIGHT:
        raise RuntimeError(
            f"Final video resolution is "
            f"{width}x{height}; expected "
            f"{VIDEO_WIDTH}x{VIDEO_HEIGHT}."
        )

    try:
        video_duration = float(
            video_stream.get("duration") or 0
        )
    except Exception:
        video_duration = 0

    try:
        audio_duration = float(
            audio_stream.get("duration") or 0
        )
    except Exception:
        audio_duration = 0

    try:
        format_duration = float(
            probe.get("format", {}).get(
                "duration"
            ) or 0
        )
    except Exception:
        format_duration = 0

    duration = max(
        video_duration,
        audio_duration,
        format_duration,
    )

    if duration <= 0:
        raise RuntimeError(
            "Final MP4 has no valid duration."
        )

    if video_duration > 0 and audio_duration > 0:
        difference = abs(
            video_duration - audio_duration
        )

        if difference > 1.5:
            raise RuntimeError(
                "Video/audio duration mismatch: "
                f"{video_duration:.2f}s vs "
                f"{audio_duration:.2f}s."
            )

    log(
        "FINAL QC PASSED"
    )

    log(
        f"Resolution: {width}x{height}"
    )

    log(
        f"Video duration: "
        f"{video_duration:.2f}s"
    )

    log(
        f"Audio duration: "
        f"{audio_duration:.2f}s"
    )

    log(
        f"File size: "
        f"{size / (1024 * 1024):.2f} MB"
    )

    return True


# ============================================================
# MAIN
# ============================================================

def main():
    log("=" * 70)
    log("RIFT VALLEY WATCH")
    log("VIDEO GENERATOR")
    log(f"VERSION: {GENERATOR_VERSION}")
    log("=" * 70)

    # --------------------------------------------------------
    # CLEAN TEMP DIRECTORY
    # --------------------------------------------------------

    TEMP_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    for item in TEMP_DIR.iterdir():
        try:
            if item.is_file():
                item.unlink()
            elif item.is_dir():
                import shutil
                shutil.rmtree(item)
        except Exception as exc:
            log(
                f"Could not remove temp item "
                f"{item}: {exc}"
            )

    # --------------------------------------------------------
    # ENSURE DIRECTORIES
    # --------------------------------------------------------

    DATA_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    SOURCE_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    AUDIO_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    OUTPUT_DIR.mkdir(
        parents=True,
        exist_ok=True,
    )

    # --------------------------------------------------------
    # REMOVE STALE OUTPUT
    # --------------------------------------------------------

    if OUTPUT_FILE.exists():
        try:
            OUTPUT_FILE.unlink()
            log(
                "Removed previous final MP4."
            )
        except Exception as exc:
            raise RuntimeError(
                "Could not remove previous "
                f"MP4: {exc}"
            )

    # --------------------------------------------------------
    # LOAD STORY
    # --------------------------------------------------------

    story = get_story()

    title = extract_title(story)
    county = extract_county(story)

    if not title:
        raise RuntimeError(
            "Story title/headline is missing."
        )

    log(
        f"TITLE: {title}"
    )

    log(
        f"COUNTY: "
        f"{county if county else 'Unknown'}"
    )

    # --------------------------------------------------------
    # BUILD NARRATION
    # --------------------------------------------------------

    narration = build_narration(
        story
    )

    if not narration:
        raise RuntimeError(
            "No narration was generated."
        )

    log(
        f"NARRATION: {narration}"
    )

    log(
        f"NARRATION WORDS: "
        f"{len(narration.split())}"
    )

    # --------------------------------------------------------
    # RESOLVE REAL IMAGES
    # --------------------------------------------------------

    images = resolve_images(
        story
    )

    if not images:
        raise RuntimeError(
            "No usable article images found."
        )

    # --------------------------------------------------------
    # IMPORTANT:
    # ONE IMAGE = ONE SCENE.
    # MULTIPLE IMAGES = REAL SLIDESHOW.
    #
    # There is NO fake counter.
    # --------------------------------------------------------

    log(
        f"USABLE DISTINCT IMAGES: "
        f"{len(images)}"
    )

    prepared_images = []

    for index, image_path in enumerate(
        images,
        start=1,
    ):
        prepared_path = (
            TEMP_DIR /
            f"prepared_{index}.jpg"
        )

        log(
            f"Preparing image "
            f"{index}/{len(images)}: "
            f"{image_path}"
        )

        prepare_image_for_vertical(
            image_path,
            prepared_path,
        )

        prepared_images.append(
            prepared_path
        )

    # --------------------------------------------------------
    # CREATE OVERLAYS
    # --------------------------------------------------------

    overlays = []

    if len(prepared_images) == 1:

        overlay_path = (
            TEMP_DIR /
            "overlay_1.png"
        )

        create_overlay(
            overlay_path,
            county,
            title,
            image_number=None,
            image_total=None,
            show_counter=False,
        )

        overlays.append(
            overlay_path
        )

        log(
            "Single real image detected."
        )

        log(
            "Using ONE continuous "
            "Ken Burns scene."
        )

    else:

        total_images = len(
            prepared_images
        )

        log(
            f"REAL PHOTO SLIDESHOW: "
            f"{total_images} distinct images."
        )

        for index in range(
            1,
            total_images + 1,
        ):
            overlay_path = (
                TEMP_DIR /
                f"overlay_{index}.png"
            )

            create_overlay(
                overlay_path,
                county,
                title,
                image_number=index,
                image_total=total_images,
                show_counter=True,
            )

            overlays.append(
                overlay_path
            )

    # --------------------------------------------------------
    # GENERATE NARRATION AUDIO
    # --------------------------------------------------------

    audio_path = generate_audio(
        narration
    )

    audio_duration = get_media_duration(
        audio_path
    )

    if audio_duration <= 0:
        raise RuntimeError(
            "Narration duration is invalid."
        )

    log(
        f"AUDIO DURATION: "
        f"{audio_duration:.2f}s"
    )

    # --------------------------------------------------------
    # CREATE SILENT VIDEO
    # --------------------------------------------------------

    silent_video = (
        TEMP_DIR /
        "silent_video.mp4"
    )

    if len(prepared_images) == 1:

        create_single_image_video(
            prepared_images[0],
            overlays[0],
            audio_duration,
            silent_video,
        )

    else:

        create_multi_image_video(
            prepared_images,
            overlays,
            audio_duration,
            silent_video,
        )

    if not silent_video.exists():
        raise RuntimeError(
            "Silent video was not created."
        )

    # --------------------------------------------------------
    # ATTACH NARRATION
    # --------------------------------------------------------

    final_path = attach_audio(
        silent_video,
        audio_path,
    )

    # --------------------------------------------------------
    # FINAL QC
    # --------------------------------------------------------

    verify_final_video(
        final_path
    )

    # --------------------------------------------------------
    # FINAL SUCCESS
    # --------------------------------------------------------

    log("=" * 70)
    log(
        "RIFT VALLEY WATCH "
        "GENERATION COMPLETE"
    )
    log("=" * 70)

    log(
        f"FINAL MP4: {final_path}"
    )

    log(
        f"SIZE: "
        f"{final_path.stat().st_size / "
        f"(1024 * 1024):.2f} MB"
    )

    log(
        "No source/publisher displayed."
    )

    log(
        "No source/publisher narrated."
    )

    log(
        "No fake photo counter."
    )

    log(
        "No [PHOTOS] artifact."
    )

    log(
        "No / PCS artifact."
    )

    log(
        "No VERIFIED REPORT label."
    )

    return final_path


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":
    main()
