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

        font = (
            "/usr/share/fonts/truetype/dejavu/"
            "DejaVuSans-Bold.ttf"
        )

        if not Path(font).exists():
            font = (
                "/usr/share/fonts/truetype/liberation2/"
                "LiberationSans-Bold.ttf"
            )

        caption_text = str(
            caption or ""
        )

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

        vf = (
            "scale=1080:1920:"
            "force_original_aspect_ratio=increase,"
            "crop=1080:1920,"
            "setsar=1,"
            "drawbox="
            "x=0:y=0:w=1080:h=150:"
            "color=black@0.72:t=fill,"
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

        log(
            f"Rendering scene: "
            f"{output_path.name}"
        )

        result = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        if result.returncode != 0:

            log("")
            log("FFMPEG SCENE ERROR:")
            log(result.stderr[-5000:])

            raise RuntimeError(
                f"FFmpeg failed creating "
                f"{output_path.name}"
            )

        if not output_path.exists():
            raise RuntimeError(
                f"Scene was not created: "
                f"{output_path}"
            )

        if output_path.stat().st_size < 10000:
            raise RuntimeError(
                f"Scene file is too small: "
                f"{output_path}"
            )

        return str(output_path)

    # IMPORTANT:
    # Always install our own renderer function.
    # Do NOT check whether the old function exists.

    generator.create_scene_video = safe_create_scene_video

    log(
        "Scene video renderer installed."
    )
