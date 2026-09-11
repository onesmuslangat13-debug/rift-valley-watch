# ============================================================
# V6 DATA-DRIVEN NEWSROOM SCENES
# ============================================================

def fact_value(story, *labels):
    facts = story.get("verified_facts", [])
    wanted = {str(x).strip().upper() for x in labels}

    for fact in facts:
        if not isinstance(fact, dict):
            continue

        label = clean_text(
            fact.get("label", "")
        ).upper()

        if label in wanted:
            return clean_text(
                fact.get("value", "")
            )

    return ""


def story_category(story):
    value = clean_text(
        story.get("category", "NEWS")
    ).upper()

    return value or "NEWS"


def story_location(story):
    county = clean_text(
        story.get("county", "")
    )

    location = fact_value(
        story,
        "LOCATION",
        "AREA",
        "COUNTY"
    )

    if location:
        return location

    return county or "Rift Valley"


def story_cost(story):
    return fact_value(
        story,
        "COST",
        "PROJECT_COST",
        "VALUE",
        "BUDGET"
    )


def story_status(story):
    return fact_value(
        story,
        "STATUS",
        "PROJECT_STATUS"
    )


def story_length(story):
    return fact_value(
        story,
        "ROAD_LENGTH",
        "LENGTH",
        "DISTANCE",
        "COVERAGE"
    )


def story_route(story):
    return fact_value(
        story,
        "PROJECT",
        "ROUTE",
        "ROAD",
        "CORRIDOR"
    )


def story_impact(story):
    value = fact_value(
        story,
        "IMPACT",
        "SIGNIFICANCE",
        "BENEFIT"
    )

    if value:
        return value

    return clean_text(
        story.get("summary", "")
    )


def scene_latest(story):

    image = create_background()

    draw = ImageDraw.Draw(
        image
    )

    category = story_category(
        story
    )

    length = story_length(
        story
    )

    cost = story_cost(
        story
    )

    location = story_location(
        story
    )

    title = clean_text(
        story.get("title", "")
    )

    top_bar(
        draw,
        "THE LATEST"
    )

    section_label(
        draw,
        category
    )

    # Primary statistic
    if length:

        draw.text(
            (55, 300),
            length.upper(),
            font=get_font(
                105,
                True
            ),
            fill=(255, 255, 255)
        )

    else:

        draw.text(
            (55, 300),
            "LATEST",
            font=get_font(
                82,
                True
            ),
            fill=(255, 255, 255)
        )

    # Secondary identifier
    identifier = (
        "PROJECT"
        if category in {
            "DEVELOPMENT",
            "INFRASTRUCTURE",
            "ROADS"
        }
        else category
    )

    draw.text(
        (58, 440),
        identifier,
        font=get_font(
            48,
            True
        ),
        fill=(225, 35, 42)
    )

    draw_wrapped(
        draw,
        title,
        55,
        565,
        get_font(
            49,
            True
        ),
        (238, 242, 247),
        950,
        14
    )

    # Location
    draw.text(
        (55, 1020),
        "LOCATION",
        font=get_font(
            25,
            True
        ),
        fill=(145, 160, 180)
    )

    draw_wrapped(
        draw,
        location,
        55,
        1070,
        get_font(
            40,
            True
        ),
        (255, 255, 255),
        950,
        10
    )

    # Cost/value card
    if cost:

        draw.rounded_rectangle(
            (
                50,
                1260,
                1030,
                1515
            ),
            radius=25,
            fill=(9, 27, 46),
            outline=(48, 70, 94),
            width=2
        )

        draw.text(
            (85, 1305),
            "REPORTED VALUE",
            font=get_font(
                25,
                True
            ),
            fill=(145, 160, 180)
        )

        draw_wrapped(
            draw,
            cost,
            85,
            1360,
            get_font(
                62,
                True
            ),
            (255, 255, 255),
            890,
            8
        )

    footer(
        draw,
        story
    )

    return image


def scene_photo(story, image_path):

    image = photo_background(
        image_path
    )

    draw = ImageDraw.Draw(
        image
    )

    top_bar(
        draw,
        "VISUAL EVIDENCE"
    )

    section_label(
        draw,
        "OFFICIAL SOURCE"
    )

    title = clean_text(
        story.get(
            "title",
            ""
        )
    )

    draw.rounded_rectangle(
        (
            35,
            1190,
            1045,
            1700
        ),
        radius=30,
        fill=(3, 9, 18)
    )

    draw_wrapped(
        draw,
        title,
        70,
        1245,
        get_font(
            49,
            True
        ),
        (255, 255, 255),
        900,
        14
    )

    source_name = clean_text(
        story.get(
            "source",
            {}
        ).get(
            "name",
            ""
        )
    )

    if source_name:

        draw.text(
            (70, 1575),
            source_name,
            font=get_font(
                27,
                True
            ),
            fill=(225, 35, 42)
        )

    source_badge(
        draw
    )

    footer(
        draw,
        story
    )

    return image


def scene_location(story):

    image = create_background()

    draw = ImageDraw.Draw(
        image
    )

    county = clean_text(
        story.get(
            "county",
            "Rift Valley"
        )
    )

    location = story_location(
        story
    )

    top_bar(
        draw,
        "WHERE IT IS"
    )

    section_label(
        draw,
        "LOCATION"
    )

    draw_wrapped(
        draw,
        county.upper(),
        55,
        315,
        get_font(
            82,
            True
        ),
        (255, 255, 255),
        950,
        8
    )

    draw_wrapped(
        draw,
        location,
        58,
        445,
        get_font(
            39,
            True
        ),
        (225, 35, 42),
        950,
        10
    )

    # Editorial location panel.
    draw.rounded_rectangle(
        (
            70,
            690,
            1010,
            1135
        ),
        radius=32,
        fill=(8, 25, 42),
        outline=(55, 80, 105),
        width=3
    )

    draw.text(
        (110, 750),
        "PROJECT LOCATION",
        font=get_font(
            28,
            True
        ),
        fill=(145, 162, 182)
    )

    draw_wrapped(
        draw,
        location,
        110,
        820,
        get_font(
            51,
            True
        ),
        (255, 255, 255),
        820,
        12
    )

    draw.text(
        (110, 1015),
        county,
        font=get_font(
            30,
            True
        ),
        fill=(225, 35, 42)
    )

    draw_wrapped(
        draw,
        "The verified source places this development within the location identified above.",
        55,
        1225,
        get_font(
            35,
            True
        ),
        (230, 235, 242),
        950,
        13
    )

    footer(
        draw,
        story
    )

    return image


def scene_facts(story):

    image = create_background()

    draw = ImageDraw.Draw(
        image
    )

    top_bar(
        draw,
        "KEY FACTS"
    )

    section_label(
        draw,
        "VERIFIED DATA"
    )

    cards = []

    length = story_length(
        story
    )

    cost = story_cost(
        story
    )

    status = story_status(
        story
    )

    if length:
        cards.append(
            (
                "SCALE / LENGTH",
                length
            )
        )

    if cost:
        cards.append(
            (
                "REPORTED COST",
                cost
            )
        )

    if status:
        cards.append(
            (
                "CURRENT STATUS",
                status
            )
        )

    # Guarantee a useful third card.
    if len(cards) < 3:

        location = story_location(
            story
        )

        if location:
            cards.append(
                (
                    "LOCATION",
                    location
                )
            )

    y = 350

    for label, value in cards[:3]:

        draw.rounded_rectangle(
            (
                50,
                y,
                1030,
                y + 285
            ),
            radius=25,
            fill=(9, 27, 46),
            outline=(48, 70, 94),
            width=2
        )

        draw.text(
            (
                85,
                y + 42
            ),
            label,
            font=get_font(
                26,
                True
            ),
            fill=(145, 162, 182)
        )

        draw_wrapped(
            draw,
            value,
            85,
            y + 105,
            get_font(
                59,
                True
            ),
            (255, 255, 255),
            875,
            8
        )

        y += 345

    footer(
        draw,
        story
    )

    return image


def scene_route(story):

    image = create_background()

    draw = ImageDraw.Draw(
        image
    )

    route = story_route(
        story
    )

    length = story_length(
        story
    )

    top_bar(
        draw,
        "THE ROUTE"
    )

    section_label(
        draw,
        "PROJECT CORRIDOR"
    )

    headline = (
        length.upper()
        if length
        else "PROJECT ROUTE"
    )

    draw_wrapped(
        draw,
        headline,
        55,
        320,
        get_font(
            65,
            True
        ),
        (255, 255, 255),
        950,
        8
    )

    draw.text(
        (55, 430),
        "ROUTE / CONNECTION",
        font=get_font(
            45,
            True
        ),
        fill=(225, 35, 42)
    )

    # Abstract editorial route visualization.
    # It is deliberately not presented as a geographic map.
    points = [
        (120, 720),
        (315, 625),
        (505, 785),
        (700, 650),
        (930, 805)
    ]

    for index in range(
        len(points) - 1
    ):

        x1, y1 = points[index]
        x2, y2 = points[index + 1]

        draw.line(
            (
                x1,
                y1,
                x2,
                y2
            ),
            fill=(225, 35, 42),
            width=12
        )

    # Route nodes.
    for index, point in enumerate(
        points
    ):

        x, y = point

        draw.ellipse(
            (
                x - 20,
                y - 20,
                x + 20,
                y + 20
            ),
            fill=(255, 255, 255),
            outline=(225, 35, 42),
            width=5
        )

        draw.text(
            (
                x - 5,
                y + 38
            ),
            str(index + 1),
            font=get_font(
                24,
                True
            ),
            fill=(230, 235, 242)
        )

    if route:

        draw.rounded_rectangle(
            (
                50,
                1060,
                1030,
                1480
            ),
            radius=28,
            fill=(9, 27, 46),
            outline=(48, 70, 94),
            width=2
        )

        draw.text(
            (85, 1110),
            "VERIFIED PROJECT / ROUTE",
            font=get_font(
                25,
                True
            ),
            fill=(145, 162, 182)
        )

        draw_wrapped(
            draw,
            route,
            85,
            1170,
            get_font(
                39,
                True
            ),
            (255, 255, 255),
            870,
            12
        )

    else:

        draw_wrapped(
            draw,
            "Route details were not supplied in the verified facts.",
            55,
            1120,
            get_font(
                38,
                True
            ),
            (230, 235, 242),
            950,
            13
        )

    footer(
        draw,
        story
    )

    return image
