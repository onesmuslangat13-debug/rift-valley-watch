# ============================================================
# GENERATE VIDEO
# ============================================================

def generate_video(story):
    validate_story_for_video(story)

    script = build_script(story)

    write_json(
        STORY_FILE,
        story,
    )

    write_json(
        SELECTED_STORY_FILE,
        story,
    )

    write_json(
        SCRIPT_FILE,
        script,
    )

    write_json(
        SELECTED_SCRIPT_FILE,
        script,
    )

    print()
    print("=" * 60)
    print("VIDEO GENERATION")
    print("=" * 60)
    print(
        "Image:",
        story["local_image"],
    )

    try:
        from rift_valley_video_generator import (
            generate_video as video_generator
        )
    except Exception as exc:
        raise RuntimeError(
            "Could not import "
            "rift_valley_video_generator.py: "
            + str(exc)
        )

    # IMPORTANT:
    # Your current video generator accepts ONE argument.
    output = video_generator(
        story
    )

    if output is None:
        output = VIDEO_FILE

    output = Path(output)

    if not output.exists():
        if VIDEO_FILE.exists():
            output = VIDEO_FILE

    if not output.exists():
        raise RuntimeError(
            "Video generator completed but "
            "no final MP4 was created."
        )

    return output
