        if enriched:
            verified.append(enriched)

            print("")
            print("VERIFIED STORY FOUND")
            print("Title:", enriched.get("title", ""))
            print("County:", enriched.get("county", ""))
            print("Source:", enriched.get("source_name", ""))
            print("URL:", enriched.get("url", ""))
            print("Image:", enriched.get("image", ""))
            print("Domain:", enriched.get("resolved_domain", ""))
            print("Score:", enriched.get("score", 0))

            # ------------------------------------------------
            # IMPORTANT:
            # We only need ONE story for one reel.
            # Stop immediately after the first fully verified
            # story instead of checking additional candidates.
            # ------------------------------------------------
            print("")
            print(
                "ONE VERIFIED STORY IS ENOUGH. "
                "Stopping candidate verification."
            )

            break

        elapsed_candidate = (
            time.time() - candidate_start
        )

        print(
            "Candidate verification time:",
            round(elapsed_candidate, 2),
            "seconds",
        )

    total_elapsed = (
        time.time() - total_start
    )

    if not verified:
        raise RuntimeError(
            "No recent story passed verification "
            "after checking the strongest candidates."
        )

    # --------------------------------------------------------
    # Select strongest verified story
    # --------------------------------------------------------

    verified.sort(
        key=lambda x: x.get("score", 0),
        reverse=True,
    )

    story = verified[0]

    # Remove internal fields before saving.
    story.pop("_pre_score", None)

    # --------------------------------------------------------
    # Final required fields
    # --------------------------------------------------------

    story["title"] = clean_text(
        story.get("title", "")
    )

    story["county"] = clean_text(
        story.get("county", "")
    )

    story["source_name"] = clean_text(
        story.get("source_name", "")
    )

    story["summary"] = clean_text(
        story.get("summary", "")
    )

    story["url"] = story.get(
        "url",
        "",
    )

    story["image"] = story.get(
        "image",
        "",
    )

    story["resolved_domain"] = (
        publisher_domain(
            story["url"]
        )
    )

    story["verification"] = (
        story.get(
            "verification",
            "publisher_article",
        )
    )

    story["selected_at"] = (
        now_utc().isoformat()
    )

    # --------------------------------------------------------
    # Final safety checks
    # --------------------------------------------------------

    if not valid_http_url(
        story["url"]
    ):
        raise RuntimeError(
            "Selected story has an invalid URL."
        )

    if is_google_news_url(
        story["url"]
    ):
        raise RuntimeError(
            "Selected story still points to Google News."
        )

    if not story["image"]:
        raise RuntimeError(
            "Selected story has no image."
        )

    if not valid_http_url(
        story["image"]
    ):
        raise RuntimeError(
            "Selected story image is invalid."
        )

    print("")
    print(
        "============================================================"
    )

    print(
        "FINAL STORY SELECTED"
    )

    print(
        "============================================================"
    )

    print(
        json.dumps(
            {
                "title": story.get("title"),
                "county": story.get("county"),
                "source": story.get("source_name"),
                "url": story.get("url"),
                "image": story.get("image"),
                "score": story.get("score"),
                "verification": story.get("verification"),
            },
            indent=2,
            ensure_ascii=False,
        )
    )

    print("")
    print(
        "Total story-selection time:",
        round(total_elapsed, 2),
        "seconds",
    )

    return story


# ============================================================
# SCRIPT CREATION
# ============================================================

def build_script(story):
    """
    Build the narration structure consumed by the video
    generator.

    One story only.
    """

    title = clean_text(
        story.get("title", "")
    )

    summary = clean_text(
        story.get("summary", "")
    )

    county = clean_text(
        story.get("county", "")
    )

    source = clean_text(
        story.get("source_name", "")
    )

    if not summary:
        summary = title

    # --------------------------------------------------------
    # Keep narration reasonably short.
    # --------------------------------------------------------

    summary = summary[:700]

    hook = (
        f"Here's the latest development from "
        f"{county} County."
    )

    narration = (
        f"{hook} "
        f"{title}. "
        f"{summary} "
        f"The development is being reported by "
        f"{source}."
    )

    # --------------------------------------------------------
    # Remove problematic whitespace.
    # --------------------------------------------------------

    narration = re.sub(
        r"\s+",
        " ",
        narration,
    ).strip()

    # --------------------------------------------------------
    # Screen text
    # --------------------------------------------------------

    key_facts = [
        title,
        f"County: {county}",
        f"Source: {source}",
    ]

    script = {
        "title": title,
        "hook": hook,
        "narration": narration,
        "summary": summary,
        "county": county,
        "source": source,
        "source_name": source,
        "source_url": story.get("url", ""),
        "image": story.get("image", ""),
        "key_facts": key_facts,
        "verification": story.get(
            "verification",
            "",
        ),
        "duration_target": 45,
    }

    return script


# ============================================================
# SAFE JSON WRITER
# ============================================================

def write_json(
    path,
    data,
):
    """
    Atomically write JSON so a partially written file is not
    left behind if the runner fails.
    """

    os.makedirs(
        os.path.dirname(path) or ".",
        exist_ok=True,
    )

    temporary_path = (
        path + ".tmp"
    )

    with open(
        temporary_path,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False,
            default=str,
        )

    os.replace(
        temporary_path,
        path,
    )


# ============================================================
# STORY + SCRIPT SAVE
# ============================================================

def save_story_and_script(
    story,
    script,
):

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True,
    )

    write_json(
        STORY_FILE,
        story,
    )

    write_json(
        SCRIPT_FILE,
        script,
    )

    print("")
    print(
        "Saved:",
        STORY_FILE,
    )

    print(
        "Saved:",
        SCRIPT_FILE,
    )


# ============================================================
# VIDEO GENERATION
# ============================================================

def generate_story_video(
    story,
    script,
):
    """
    Call the video generator.

    The generator is expected to create:

        output/rift_valley_watch_reel.mp4
    """

    print("")
    print(
        "============================================================"
    )

    print(
        "STARTING VIDEO GENERATION"
    )

    print(
        "============================================================"
    )

    print(
        "Story:",
        story.get("title", ""),
    )

    print(
        "Image:",
        story.get("image", ""),
    )

    print(
        "Source:",
        story.get("source_name", ""),
    )

    # --------------------------------------------------------
    # Ensure output directory exists.
    # --------------------------------------------------------

    os.makedirs(
        "output",
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Call generator.
    #
    # The current generator should expose:
    #
    #     generate_video(story, script)
    #
    # --------------------------------------------------------

    result = generate_video(
        story,
        script,
    )

    # --------------------------------------------------------
    # Determine output path.
    # --------------------------------------------------------

    expected_path = os.path.join(
        "output",
        "rift_valley_watch_reel.mp4",
    )

    # Some generator versions return the output path.
    # Support that without depending on it.
    returned_path = None

    if isinstance(
        result,
        str,
    ):
        returned_path = result

    elif isinstance(
        result,
        dict,
    ):
        returned_path = (
            result.get("output")
            or result.get("output_path")
            or result.get("video")
            or result.get("video_path")
        )

    # --------------------------------------------------------
    # Prefer returned path when it exists.
    # --------------------------------------------------------

    if (
        returned_path
        and os.path.isfile(
            returned_path
        )
    ):

        output_path = returned_path

    else:

        output_path = expected_path

    # --------------------------------------------------------
    # If the generator created another MP4, find it.
    # --------------------------------------------------------

    if not os.path.isfile(
        output_path
    ):

        possible_files = []

        if os.path.isdir(
            "output"
        ):

            for filename in os.listdir(
                "output"
            ):

                if filename.lower().endswith(
                    ".mp4"
                ):

                    possible_files.append(
                        os.path.join(
                            "output",
                            filename,
                        )
                    )

        if possible_files:

            possible_files.sort(
                key=os.path.getmtime,
                reverse=True,
            )

            output_path = (
                possible_files[0]
            )

    # --------------------------------------------------------
    # HARD FAILURE if no video exists.
    # --------------------------------------------------------

    if not os.path.isfile(
        output_path
    ):

        print("")
        print(
            "VIDEO GENERATION FAILED."
        )

        print(
            "Expected:",
            expected_path,
        )

        print(
            "Available MP4 files:"
        )

        if os.path.isdir(
            "output"
        ):

            for filename in os.listdir(
                "output"
            ):

                if filename.lower().endswith(
                    ".mp4"
                ):

                    print(
                        " -",
                        filename,
                    )

        raise RuntimeError(
            "Video generator finished without "
            "creating an MP4 file."
        )

    # --------------------------------------------------------
    # Basic file validation.
    # --------------------------------------------------------

    size = os.path.getsize(
        output_path
    )

    if size < 50_000:
        raise RuntimeError(
            "Generated MP4 is suspiciously small: "
            f"{size} bytes."
        )

    print("")
    print(
        "VIDEO GENERATED SUCCESSFULLY"
    )

    print(
        "Output:",
        output_path,
    )

    print(
        "Size:",
        f"{size:,}",
        "bytes",
    )

    return output_path


# ============================================================
# FINAL QC
# ============================================================

def validate_output(
    story,
    script,
    video_path,
):
    """
    Final automatic quality-control checks before the GitHub
    Actions job is allowed to succeed.
    """

    print("")
    print(
        "============================================================"
    )

    print(
        "AUTOMATIC FINAL QC"
    )

    print(
        "============================================================"
    )

    errors = []

    # --------------------------------------------------------
    # Story
    # --------------------------------------------------------

    if not story.get(
        "title"
    ):
        errors.append(
            "Story title missing."
        )

    if not story.get(
        "url"
    ):
        errors.append(
            "Story URL missing."
        )

    if is_google_news_url(
        story.get(
            "url",
            "",
        )
    ):
        errors.append(
            "Story URL is still Google News."
        )

    if not story.get(
        "image"
    ):
        errors.append(
            "Story image missing."
        )

    # --------------------------------------------------------
    # Script
    # --------------------------------------------------------

    if not script.get(
        "narration"
    ):
        errors.append(
            "Narration missing."
        )

    if len(
        script.get(
            "narration",
            "",
        )
    ) < 80:
        errors.append(
            "Narration is too short."
        )

    # --------------------------------------------------------
    # Video
    # --------------------------------------------------------

    if not video_path:
        errors.append(
            "Video path missing."
        )

    elif not os.path.isfile(
        video_path
    ):
        errors.append(
            "Video file does not exist."
        )

    else:

        size = os.path.getsize(
            video_path
        )

        if size < 50_000:
            errors.append(
                "Video file is too small."
            )

    # --------------------------------------------------------
    # Report
    # --------------------------------------------------------

    if errors:

        print("")
        print(
            "QC FAILED"
        )

        for error in errors:

            print(
                " -",
                error,
            )

        raise RuntimeError(
            "Automatic QC failed: "
            + " | ".join(errors)
        )

    print("")
    print(
        "QC PASSED"
    )

    print(
        "Story: PASS"
    )

    print(
        "Script: PASS"
    )

    print(
        "Video file: PASS"
    )

    print(
        "============================================================"
    )


# ============================================================
# MAIN
# ============================================================

def main():

    pipeline_start = time.time()

    print("")
    print(
        "################################################################"
    )

    print(
        "# RIFT VALLEY WATCH"
    )

    print(
        "# FAST + VERIFIED NEWS ENGINE"
    )

    print(
        "################################################################"
    )

    print(
        "Started:",
        now_utc().isoformat(),
    )

    # --------------------------------------------------------
    # Prepare directories
    # --------------------------------------------------------

    os.makedirs(
        OUTPUT_DIR,
        exist_ok=True,
    )

    os.makedirs(
        "output",
        exist_ok=True,
    )

    os.makedirs(
        "audio",
        exist_ok=True,
    )

    # --------------------------------------------------------
    # Step 1:
    # Select ONE verified story
    # --------------------------------------------------------

    story = select_story()

    if not story:

        raise RuntimeError(
            "Story selection returned no story."
        )

    # --------------------------------------------------------
    # Step 2:
    # Build script
    # --------------------------------------------------------

    print("")
    print(
        "============================================================"
    )

    print(
        "BUILDING SCRIPT"
    )

    print(
        "============================================================"
    )

    script = build_script(
        story
    )

    print(
        "Narration length:",
        len(
            script.get(
                "narration",
                "",
            )
        ),
        "characters",
    )

    # --------------------------------------------------------
    # Step 3:
    # Save JSON files BEFORE video generation.
    #
    # This makes it possible to inspect exactly which story
    # was selected even if the video generator fails.
    # --------------------------------------------------------

    save_story_and_script(
        story,
        script,
    )

    # --------------------------------------------------------
    # Step 4:
    # Generate video
    # --------------------------------------------------------

    video_path = generate_story_video(
        story,
        script,
    )

    # --------------------------------------------------------
    # Step 5:
    # Automatic QC
    # --------------------------------------------------------

    validate_output(
        story,
        script,
        video_path,
    )

    # --------------------------------------------------------
    # Complete
    # --------------------------------------------------------

    total_time = (
        time.time()
        - pipeline_start
    )

    print("")
    print(
        "################################################################"
    )

    print(
        "# RIFT VALLEY WATCH COMPLETE"
    )

    print(
        "################################################################"
    )

    print(
        "Story:",
        story.get("title", ""),
    )

    print(
        "County:",
        story.get("county", ""),
    )

    print(
        "Source:",
        story.get("source_name", ""),
    )

    print(
        "Video:",
        video_path,
    )

    print(
        "Total pipeline time:",
        round(total_time, 2),
        "seconds",
    )

    print(
        "################################################################"
    )


# ============================================================
# ENTRY POINT
# ============================================================

if __name__ == "__main__":

    try:

        main()

    except KeyboardInterrupt:

        print("")
        print(
            "Pipeline cancelled by user."
        )

        raise

    except Exception as exc:

        print("")
        print(
            "################################################################"
        )

        print(
            "# RIFT VALLEY WATCH FAILED"
        )

        print(
            "################################################################"
        )

        print(
            "ERROR:",
            exc,
        )

        traceback.print_exc()

        raise
