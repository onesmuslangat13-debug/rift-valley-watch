def patch_scene_video(generator):

    def safe_create_scene_video(
        image_path,
        audio_path,
        output_path,
        caption=None,
        *args,
        **kwargs,
    ):

        image_path = Path(image_path)
        audio_path = Path(audio_path)
        output_path = Path(output_path)

        output_path.parent.mkdir(
            parents=True,
            exist_ok=True,
        )

        if not image_path.exists():
            raise RuntimeError(
                f"Scene image missing: {image_path}"
            )

        if not audio_path.exists():
            raise RuntimeError(
                f"Scene audio missing: {audio_path}"
            )

        # --------------------------------------------------
        # FONT
        # --------------------------------------------------

        font = (
            "/usr/share/fonts/truetype/dejavu/"
            "DejaVuSans-Bold.ttf"
        )

        if not Path(font).exists():
            font = (
                "/usr/share/fonts/truetype/liberation2/"
                "LiberationSans-Bold.ttf"
            )

        if not Path(font).exists():
            raise RuntimeError(
                "No usable system font was found."
            )

        # --------------------------------------------------
        # CAPTION
        # --------------------------------------------------

        caption_text = str(
            caption or ""
        ).strip()

        # Escape characters that can break FFmpeg drawtext.
        caption_text = (
            caption_text
            .replace("\\", "\\\\")
            .replace("'", "\\'")
            .replace(":", "\\:")
            .replace(",", "\\,")
            .replace("[", "\\[")
            .replace("]", "\\]")
            .replace("%", "\\%")
        )

        # --------------------------------------------------
        # VIDEO FILTER
        # --------------------------------------------------

        vf = (
            "scale=1080:1920:"
            "force_original_aspect_ratio=increase,"
            "crop=1080:1920,"
            "setsar=1,"
            "drawbox="
            "x=0:"
            "y=0:"
            "w=1080:"
            "h=150:"
            "color=black@0.72:"
            "t=fill,"
            "drawtext="
            f"fontfile='{font}':"
            f"text='{caption_text}':"
            "fontcolor=white:"
            "fontsize=42:"
            "x=(w-text_w)/2:"
            "y=52:"
            "borderw=2:"
            "bordercolor=black"
        )

        # --------------------------------------------------
        # FFMPEG COMMAND
        # --------------------------------------------------

        cmd = [
            "ffmpeg",
            "-y",

            # Still image
            "-loop",
            "1",
            "-i",
            str(image_path),

            # Narration
            "-i",
            str(audio_path),

            # Video filter
            "-vf",
            vf,

            # Video
            "-c:v",
            "libx264",

            "-preset",
            "veryfast",

            "-crf",
            "21",

            "-pix_fmt",
            "yuv420p",

            # Audio
            "-c:a",
            "aac",

            "-b:a",
            "128k",

            # Stop when narration ends
            "-shortest",

            # Frame rate
            "-r",
            str(FPS),

            # Web-compatible MP4
            "-movflags",
            "+faststart",

            # Output
            str(output_path),
        ]

        log(
            "Rendering scene: "
            f"{output_path.name}"
        )

        # --------------------------------------------------
        # RUN FFMPEG
        # --------------------------------------------------

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        # --------------------------------------------------
        # ERROR HANDLING
        # --------------------------------------------------

        if result.returncode != 0:

            log("")
            log(
                "============================================================"
            )
            log("FFMPEG SCENE ERROR")
            log(
                "============================================================"
            )
            log(result.stderr[-10000:])

            raise RuntimeError(
                "FFmpeg failed creating "
                f"{output_path.name}"
            )

        # --------------------------------------------------
        # VERIFY OUTPUT
        # --------------------------------------------------

        if not output_path.exists():

            raise RuntimeError(
                "Scene was not created: "
                f"{output_path}"
            )

        file_size = output_path.stat().st_size

        if file_size < 10000:

            raise RuntimeError(
                "Scene file is too small: "
                f"{output_path} "
                f"({file_size} bytes)"
            )

        log(
            "Scene created successfully: "
            f"{output_path.name} "
            f"({file_size:,} bytes)"
        )

        return str(output_path)

    # ==========================================================
    # IMPORTANT
    # ALWAYS INSTALL OUR OWN SCENE RENDERER
    # ==========================================================

    generator.create_scene_video = (
        safe_create_scene_video
    )

    log(
        "Scene video renderer installed."
    )
