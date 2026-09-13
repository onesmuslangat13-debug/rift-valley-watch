def validate(article, script):
    if not article.get("title"):
        raise RuntimeError(
            "Story title is missing."
        )

    if not article.get("url"):
        raise RuntimeError(
            "Story URL is missing."
        )

    if not article.get("story_type"):
        raise RuntimeError(
            "Story type is missing."
        )

    if word_count(script) < 45:
        raise RuntimeError(
            "Narration contains fewer than 45 words."
        )

    if not FINAL_IMAGE.exists():
        raise RuntimeError(
            "Final article image does not exist."
        )

    try:
        image = Image.open(
            FINAL_IMAGE
        )

        image.verify()

    except Exception as exc:
        raise RuntimeError(
            f"Final image is invalid: {exc}"
        )

    # ========================================================
    # PUBLISHER ATTRIBUTION CHECK
    #
    # Do NOT block ordinary words such as:
    # "nation", "citizen", "star", or "standard".
    #
    # Only reject obvious publisher attribution.
    # ========================================================

    script_lower = script.lower()

    forbidden_attribution_patterns = [
        r"\baccording to nation africa\b",
        r"\baccording to daily nation\b",
        r"\bnation africa reports\b",
        r"\bdaily nation reports\b",
        r"\breported by nation africa\b",
        r"\breported by daily nation\b",

        r"\baccording to citizen digital\b",
        r"\bcitizen digital reports\b",
        r"\breported by citizen digital\b",

        r"\baccording to the star\b",
        r"\bthe star reports\b",
        r"\breported by the star\b",

        r"\baccording to kbc\b",
        r"\bkbc reports\b",
        r"\breported by kbc\b",

        r"\baccording to people daily\b",
        r"\bpeople daily reports\b",
        r"\breported by people daily\b",

        r"\baccording to standard media\b",
        r"\bstandard media reports\b",
        r"\breported by standard media\b",

        r"\baccording to capital news\b",
        r"\bcapital news reports\b",
        r"\breported by capital news\b",

        r"\baccording to ntv\b",
        r"\bntv reports\b",
        r"\breported by ntv\b",

        r"\baccording to tv47\b",
        r"\btv47 reports\b",
        r"\breported by tv47\b",
    ]

    for pattern in forbidden_attribution_patterns:
        if re.search(
            pattern,
            script_lower,
            flags=re.IGNORECASE,
        ):
            raise RuntimeError(
                "Publisher attribution detected "
                "in narration."
            )

    # ========================================================
    # REPEATED SENTENCE CHECK
    # ========================================================

    sentences = split_sentences(
        script
    )

    seen = set()

    for sentence in sentences:
        key = sentence_key(
            sentence
        )

        if not key:
            continue

        if key in seen:
            raise RuntimeError(
                "Repeated sentence detected."
            )

        seen.add(key)

    print(
        "[VALIDATION] Story and narration passed."
    )
