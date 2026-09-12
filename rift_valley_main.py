def build_video(generator, story, source_image, candidates):

    log("")
    log("=" * 70)
    log("BUILDING RIFT VALLEY WATCH")
    log("=" * 70)

    # --------------------------------------------------------
    # BUILD NARRATION LOCALLY
    # Do not depend on a renderer function that may not exist.
    # --------------------------------------------------------

    narration_segments = [
        "The Bomet County Government says construction is ongoing on a 65-kilometre road project in Chepalungu Constituency.",

        "The project covers the Kyogong, Kapkesosio, Sigor and Chebunyo route, as well as the Sigor, Lelaitich, Kipreres and Longisa section.",

        "The reported project cost is two point one billion Kenya shillings.",

        "According to the county government, the project is expected to unlock the economic potential of the area and the wider Bomet County.",

        "Deputy President Kithure Kindiki said the Roads and Transport Ministry had been instructed to closely monitor construction to ensure speedy completion and quality works.",

        "This report is based on information from the Bomet County Government and is dated March 18, 2026.",

        "Rift Valley Watch. Verified regional news. Follow for more."
    ]

    if not narration_segments:
        raise RuntimeError(
            "No narration segments were created."
        )

    log("")
    log("=" * 70)
    log("CREATING NARRATION")
    log("=" * 70)

    audio_files = []

    for index, text in enumerate(narration_segments):
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
            "Narration pipeline returned fewer than 7 audio segments."
        )

    # --------------------------------------------------------
    # EXACT 8-SCENE PLAN
    # --------------------------------------------------------

    scene_plan = [
        ("VISUAL EVIDENCE", source_image, 0),
        ("WHERE IT IS", None, 1),
        ("KEY FACTS", None, 2),
        ("THE ROUTE", None, 3),
        ("WHY IT MATTERS", None, 4),
        ("OFFICIAL STATEMENT", None, 5),
        ("SOURCE", None, 6),
        ("OUTRO", None, 7)
    ]

    # IMPORTANT:
    # The current narration has 7 segments but the scene plan
    # requires 8 scenes.
    #
    # Therefore the final OUTRO reuses the final narration segment.
    scene_plan[-1] = ("OUTRO", None, 6)

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
    ) in enumerate(scene_plan, start=1):

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
            image = generator.scene_location(story)

        elif name == "KEY FACTS":
            image = generator.scene_facts(story)

        elif name == "THE ROUTE":
            image = generator.scene_route(story)

        elif name == "WHY IT MATTERS":
            image = generator.scene_impact(story)

        elif name == "OFFICIAL STATEMENT":
            image = generator.scene_statement(story)

        elif name == "SOURCE":
            image = generator.scene_source(story)

        elif name == "OUTRO":
            image = generator.scene_outro(story)

        else:
            raise RuntimeError(
                f"Unknown scene: {name}"
            )

        image_path = generator.save_scene(
            image,
            scene_number
        )

        audio_path = audio_files[narration_index]

        caption_text = narration_segments[narration_index]

        scene_video, duration, srt_path = (
            generator.create_scene_video(
                image_path,
                audio_path,
                caption_text,
                scene_number
            )
        )

        scene_files.append(scene_video)

        scene_records.append({
            "scene": scene_number,
            "name": name,
            "image": str(image_path),
            "video": str(scene_video),
            "audio": str(audio_path),
            "caption_file": str(srt_path),
            "duration_seconds": round(duration, 2)
        })

        log(
            f"SCENE COMPLETE: {scene_video}"
        )

    # Continue with your existing FINAL ASSEMBLY section...
