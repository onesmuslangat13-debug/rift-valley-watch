# RIFT VALLEY WATCH
# REAL-TIME REGIONAL NEWS ENGINE
# Politics + Development + Business + Agriculture + Infrastructure
# Health + Education + Security + Community
#
# EXCLUSION:
# Rigathi Gachagua and stories primarily about him are excluded.

import json
import re
import time
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parent.parent

DATA_DIR = ROOT / "data"
STORY_FILE = DATA_DIR / "story.json"
SCRIPT_FILE = DATA_DIR / "script.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# SETTINGS
# ============================================================

MAX_STORIES = 12
MAX_STORIES_PER_COUNTY = 2
REQUEST_TIMEOUT = 20

COUNTIES = [
    "Bomet",
    "Kericho",
    "Nakuru",
    "Narok",
    "Nandi",
    "Uasin Gishu",
    "Elgeyo-Marakwet",
    "West Pokot",
    "Trans Nzoia",
    "Samburu",
    "Turkana",
    "Laikipia",
    "Kajiado",
]

# Gachagua exclusion requested by user.
EXCLUDED_TERMS = [
    "rigathi gachagua",
    "gachagua",
    "former deputy president gachagua",
    "former deputy president rigathi",
]


# ============================================================
# TOPIC DEFINITIONS
# ============================================================

TOPICS = {
    "POLITICS": [
        "politics",
        "political",
        "president",
        "william ruto",
        "ruto",
        "uda",
        "government",
        "governor",
        "governor's",
        "governors",
        "mp ",
        "mp,",
        "senator",
        "senate",
        "parliament",
        "assembly",
        "election",
        "2027",
        "party",
        "campaign",
        "rally",
        "political party",
        "politician",
        "cabinet",
        "deputy president",
    ],

    "INFRASTRUCTURE": [
        "road",
        "roads",
        "highway",
        "bridge",
        "bridges",
        "airport",
        "railway",
        "construction",
        "water project",
        "water supply",
        "dam",
        "housing",
        "infrastructure",
        "electricity",
        "power",
        "sewer",
        "drainage",
        "market construction",
    ],

    "AGRICULTURE": [
        "agriculture",
        "farmer",
        "farmers",
        "farming",
        "tea",
        "coffee",
        "maize",
        "wheat",
        "potato",
        "dairy",
        "livestock",
        "cattle",
        "milk",
        "horticulture",
        "irrigation",
        "fertilizer",
        "fertiliser",
        "crop",
        "crops",
        "food production",
        "food security",
    ],

    "BUSINESS": [
        "business",
        "economy",
        "economic",
        "investment",
        "investor",
        "company",
        "companies",
        "industry",
        "industrial",
        "factory",
        "manufacturing",
        "trade",
        "market",
        "markets",
        "jobs",
        "employment",
        "enterprise",
        "tourism",
        "hotel",
        "property",
        "real estate",
    ],

    "HEALTH": [
        "health",
        "hospital",
        "hospitals",
        "clinic",
        "medical",
        "doctor",
        "doctors",
        "nurse",
        "nurses",
        "medicine",
        "disease",
        "healthcare",
        "maternal",
        "vaccination",
        "ambulance",
    ],

    "EDUCATION": [
        "education",
        "school",
        "schools",
        "university",
        "universities",
        "college",
        "tvet",
        "students",
        "teachers",
        "teacher",
        "classroom",
        "scholarship",
        "learning",
        "education centre",
    ],

    "SECURITY": [
        "security",
        "police",
        "crime",
        "arrest",
        "robbery",
        "accident",
        "fire",
        "flood",
        "disaster",
        "rescue",
        "missing",
        "death",
        "killed",
        "injured",
        "terror",
        "bandit",
        "banditry",
    ],

    "COMMUNITY": [
        "community",
        "residents",
        "locals",
        "local residents",
        "county",
        "youth",
        "women",
        "cooperative",
        "co-operatives",
        "church",
        "community project",
        "public participation",
    ],
}


# ============================================================
# SEARCH QUERIES
# ============================================================

SEARCH_QUERIES = [
    "Rift Valley Kenya politics Ruto UDA 2027",
    "Rift Valley Kenya government development projects",
    "Rift Valley Kenya roads infrastructure projects",
    "Rift Valley Kenya agriculture farmers tea coffee maize dairy",
    "Rift Valley Kenya business economy investment jobs",
    "Rift Valley Kenya hospitals health",
    "Rift Valley Kenya schools education universities",
    "Rift Valley Kenya security accident flood fire",
    "Bomet Kenya latest news",
    "Kericho Kenya latest news",
    "Nakuru Kenya latest news",
    "Narok Kenya latest news",
    "Nandi Kenya latest news",
    "Uasin Gishu Kenya latest news",
    "Elgeyo Marakwet Kenya latest news",
    "West Pokot Kenya latest news",
    "Trans Nzoia Kenya latest news",
    "Samburu Kenya latest news",
    "Turkana Kenya latest news",
    "Laikipia Kenya latest news",
    "Kajiado Kenya latest news",
]


# ============================================================
# HELPERS
# ============================================================

def clean_text(value):
    if value is None:
        return ""

    value = str(value)

    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("&amp;", "&")
    value = value.replace("&quot;", '"')
    value = value.replace("&#39;", "'")
    value = value.replace("&apos;", "'")
    value = value.replace("&lt;", "<")
    value = value.replace("&gt;", ">")

    value = re.sub(r"\s+", " ", value)

    return value.strip()


def normalize(value):
    return re.sub(r"\s+", " ", clean_text(value)).strip().lower()


def contains_excluded_term(text):
    text = normalize(text)

    for term in EXCLUDED_TERMS:
        if term in text:
            return True

    return False


def detect_county(text):
    text_lower = normalize(text)

    # Long names first.
    counties_sorted = sorted(
        COUNTIES,
        key=len,
        reverse=True,
    )

    for county in counties_sorted:
        if normalize(county) in text_lower:
            return county

    # Common regional references.
    aliases = {
        "uasingishu": "Uasin Gishu",
        "uasin gishu": "Uasin Gishu",
        "elgeyo marakwet": "Elgeyo-Marakwet",
        "elgeyo-marakwet": "Elgeyo-Marakwet",
        "west pokot": "West Pokot",
        "trans nzoia": "Trans Nzoia",
    }

    for alias, county in aliases.items():
        if alias in text_lower:
            return county

    return ""


def detect_topic(text):
    text_lower = normalize(text)

    scores = {}

    for topic, keywords in TOPICS.items():
        score = 0

        for keyword in keywords:
            if keyword in text_lower:
                score += 1

        scores[topic] = score

    best_topic = max(
        scores,
        key=scores.get,
    )

    if scores[best_topic] == 0:
        return "COMMUNITY"

    return best_topic


def parse_date(value):
    if not value:
        return ""

    value = clean_text(value)

    try:
        parsed = time.strptime(
            value,
            "%a, %d %b %Y %H:%M:%S %z",
        )

        return time.strftime(
            "%Y-%m-%dT%H:%M:%SZ",
            parsed,
        )

    except Exception:
        pass

    return value


def request_url(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "RiftValleyWatch/2.0"
            )
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=REQUEST_TIMEOUT,
    ) as response:

        return response.read()


# ============================================================
# GOOGLE NEWS RSS
# ============================================================

def google_news_url(query):
    encoded = urllib.parse.quote(query)

    return (
        "https://news.google.com/rss/search"
        f"?q={encoded}"
        "&hl=en-KE"
        "&gl=KE"
        "&ceid=KE:en"
    )


def parse_rss(xml_data):
    stories = []

    try:
        root = ET.fromstring(xml_data)
    except Exception as exc:
        print(
            f"RSS parse error: {exc}"
        )
        return stories

    for item in root.findall(".//item"):

        title = clean_text(
            item.findtext("title", "")
        )

        description = clean_text(
            item.findtext("description", "")
        )

        link = clean_text(
            item.findtext("link", "")
        )

        source_node = item.find("source")

        source = ""

        if source_node is not None:
            source = clean_text(
                source_node.text
            )

        published = parse_date(
            item.findtext("pubDate", "")
        )

        combined = (
            f"{title} "
            f"{description}"
        )

        if not title:
            continue

        # Hard exclusion.
        if contains_excluded_term(combined):
            continue

        county = detect_county(combined)

        if not county:
            continue

        topic = detect_topic(combined)

        stories.append(
            {
                "title": title,
                "county": county,
                "category": topic,
                "description": description,
                "source": source or "Google News",
                "url": link,
                "published": published,
            }
        )

    return stories


# ============================================================
# STORY QUALITY
# ============================================================

def score_story(story):
    title = normalize(
        story.get("title", "")
    )

    description = normalize(
        story.get("description", "")
    )

    text = f"{title} {description}"

    score = 0

    # Political stories are important.
    if story["category"] == "POLITICS":
        score += 9

    # Development and infrastructure.
    if story["category"] in [
        "INFRASTRUCTURE",
        "BUSINESS",
        "AGRICULTURE",
    ]:
        score += 7

    if story["category"] in [
        "HEALTH",
        "EDUCATION",
        "SECURITY",
    ]:
        score += 6

    # Strong breaking-news language.
    urgent_words = [
        "breaking",
        "latest",
        "announces",
        "launches",
        "approves",
        "reveals",
        "unveils",
        "new",
        "major",
        "billions",
        "million",
        "project",
        "agreement",
        "investment",
    ]

    for word in urgent_words:
        if word in text:
            score += 2

    # Stories with a proper source URL are preferred.
    if story.get("url"):
        score += 3

    if story.get("source"):
        score += 2

    # Specific county is already required.
    if story.get("county"):
        score += 2

    return score


def deduplicate(stories):
    seen = set()
    result = []

    for story in stories:

        key = normalize(
            story.get("title", "")
        )

        # Remove common punctuation.
        key = re.sub(
            r"[^a-z0-9]+",
            " ",
            key,
        ).strip()

        if not key:
            continue

        if key in seen:
            continue

        seen.add(key)
        result.append(story)

    return result


# ============================================================
# REGIONAL SELECTION
# ============================================================

def select_stories(stories):
    stories = deduplicate(stories)

    for story in stories:
        story["_score"] = score_story(
            story
        )

    stories.sort(
        key=lambda x: x["_score"],
        reverse=True,
    )

    selected = []
    county_counts = {}

    # First pass:
    # maximize county diversity.
    for story in stories:

        county = story["county"]

        if county_counts.get(
            county,
            0,
        ) >= 1:
            continue

        selected.append(story)

        county_counts[county] = (
            county_counts.get(
                county,
                0,
            ) + 1
        )

        if len(selected) >= MAX_STORIES:
            return selected

    # Second pass:
    # add stronger additional stories.
    for story in stories:

        if story in selected:
            continue

        county = story["county"]

        if county_counts.get(
            county,
            0,
        ) >= MAX_STORIES_PER_COUNTY:
            continue

        selected.append(story)

        county_counts[county] = (
            county_counts.get(
                county,
                0,
            ) + 1
        )

        if len(selected) >= MAX_STORIES:
            break

    return selected


# ============================================================
# NARRATION
# ============================================================

def make_story_narration(story):
    title = clean_text(
        story.get("title", "")
    )

    county = clean_text(
        story.get("county", "")
    )

    category = clean_text(
        story.get("category", "")
    )

    description = clean_text(
        story.get("description", "")
    )

    if len(description) > 280:
        description = (
            description[:277].rstrip()
            + "..."
        )

    if description:
        return (
            f"{county}. "
            f"{title}. "
            f"{description}"
        )

    return (
        f"{county}. "
        f"{title}."
    )


def build_script(stories, generated_at):
    counties = []

    for story in stories:
        county = story["county"]

        if county not in counties:
            counties.append(county)

    narration = []

    narration.append(
        "Rift Valley Watch. "
        "Here are the latest major developments "
        "across Kenya's Rift Valley."
    )

    for story in stories:
        narration.append(
            make_story_narration(story)
        )

    narration.append(
        "That is the latest regional roundup "
        "from Rift Valley Watch."
    )

    scenes = []

    scenes.append(
        {
            "type": "opener",
            "text": (
                "RIFT VALLEY WATCH\n"
                "LIVE REGIONAL ROUNDUP"
            ),
            "narration": narration[0],
        }
    )

    scenes.append(
        {
            "type": "coverage",
            "text": (
                "REGIONAL COVERAGE\n"
                + " • ".join(counties)
            ),
            "narration": (
                "Today's bulletin brings together "
                "fresh developments from across "
                "the Rift Valley."
            ),
        }
    )

    for index, story in enumerate(
        stories,
        start=1,
    ):

        scenes.append(
            {
                "type": "story",
                "index": index,
                "county": story["county"],
                "category": story["category"],
                "title": story["title"],
                "description": story[
                    "description"
                ],
                "source": story["source"],
                "url": story["url"],
                "published": story[
                    "published"
                ],
                "narration": make_story_narration(
                    story
                ),
            }
        )

    scenes.append(
        {
            "type": "outro",
            "text": "RIFT VALLEY WATCH",
            "narration": narration[-1],
        }
    )

    return {
        "title": (
            "Rift Valley Watch: "
            f"{len(stories)} Fresh Regional Updates"
        ),
        "generated_at": generated_at,
        "counties": counties,
        "story_count": len(stories),
        "narration": narration,
        "scenes": scenes,
    }


# ============================================================
# OUTPUT
# ============================================================

def build_story_json(
    stories,
    generated_at,
):
    counties = []

    for story in stories:
        if story["county"] not in counties:
            counties.append(
                story["county"]
            )

    lead = stories[0] if stories else None

    story_data = {
        "title": (
            "Rift Valley Watch: "
            f"{len(stories)} Fresh Regional Updates"
        ),
        "county": "Rift Valley",
        "category": "REGIONAL ROUNDUP",
        "date": generated_at,
        "source": "Live RSS news feeds",
        "source_url": "",
        "verified_facts": {
            "LOCATION": (
                "Rift Valley, Kenya"
            ),
            "COUNTIES": ", ".join(
                counties
            ),
            "STATUS": (
                "Fresh stories collected "
                "automatically from live feeds"
            ),
            "STORY_COUNT": len(stories),
        },
        "official_statement": {
            "speaker": "",
            "quote": "",
        },
        "stories": stories,
        "lead_story": lead,
        "summary": (
            "Automated regional news roundup "
            "covering fresh developments across "
            "the Rift Valley."
        ),
    }

    # Never expose internal scoring.
    for story in story_data["stories"]:
        story.pop(
            "_score",
            None,
        )

    if story_data["lead_story"]:
        story_data[
            "lead_story"
        ].pop(
            "_score",
            None,
        )

    return story_data


def save_json(path, data):
    with open(
        path,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            data,
            file,
            indent=2,
            ensure_ascii=False,
        )


# ============================================================
# FALLBACK
# ============================================================

def build_empty_story(generated_at):
    return {
        "title": (
            "Rift Valley Watch: "
            "Live Regional Update"
        ),
        "county": "Rift Valley",
        "category": "REGIONAL ROUNDUP",
        "date": generated_at,
        "source": "Live RSS news feeds",
        "source_url": "",
        "verified_facts": {
            "LOCATION": (
                "Rift Valley, Kenya"
            ),
            "STATUS": (
                "No qualifying fresh stories "
                "were retrieved during this run"
            ),
            "STORY_COUNT": 0,
        },
        "official_statement": {
            "speaker": "",
            "quote": "",
        },
        "stories": [],
        "lead_story": None,
        "summary": (
            "No qualifying fresh regional stories "
            "were retrieved during this run."
        ),
    }


# ============================================================
# MAIN
# ============================================================

def main():

    print("=" * 50)
    print("RIFT VALLEY WATCH REAL-TIME NEWS ENGINE")
    print("=" * 50)

    generated_at = datetime.now(
        timezone.utc
    ).strftime(
        "%Y-%m-%dT%H:%M:%SZ"
    )

    print(
        f"Generated: {generated_at}"
    )

    all_stories = []

    print()
    print(
        f"Searching {len(SEARCH_QUERIES)} "
        "live news feeds..."
    )

    for index, query in enumerate(
        SEARCH_QUERIES,
        start=1,
    ):

        print(
            f"[{index}/{len(SEARCH_QUERIES)}] "
            f"{query}"
        )

        try:
            url = google_news_url(
                query
            )

            xml_data = request_url(
                url
            )

            found = parse_rss(
                xml_data
            )

            print(
                f"    Found {len(found)} "
                "qualifying items"
            )

            all_stories.extend(found)

        except Exception as exc:

            print(
                f"    Feed unavailable: {exc}"
            )

    print()
    print(
        f"Collected: {len(all_stories)} "
        "candidate stories"
    )

    # Final hard exclusion.
    all_stories = [
        story
        for story in all_stories
        if not contains_excluded_term(
            (
                story.get("title", "")
                + " "
                + story.get(
                    "description",
                    "",
                )
            )
        )
    ]

    selected = select_stories(
        all_stories
    )

    print(
        f"Selected: {len(selected)} "
        "regional stories"
    )

    if selected:

        print()
        print("SELECTED STORIES")
        print("-" * 50)

        for index, story in enumerate(
            selected,
            start=1,
        ):

            print(
                f"{index}. "
                f"[{story['county']}] "
                f"[{story['category']}]"
            )

            print(
                f"   {story['title']}"
            )

            print(
                f"   Source: "
                f"{story['source']}"
            )

    else:
        print()
        print(
            "No qualifying stories found."
        )

    # --------------------------------------------------------
    # STORY JSON
    # --------------------------------------------------------

    story_data = (
        build_story_json(
            selected,
            generated_at,
        )
        if selected
        else build_empty_story(
            generated_at
        )
    )

    save_json(
        STORY_FILE,
        story_data,
    )

    # --------------------------------------------------------
    # SCRIPT JSON
    # --------------------------------------------------------

    script_data = build_script(
        selected,
        generated_at,
    )

    save_json(
        SCRIPT_FILE,
        script_data,
    )

    print()
    print(
        f"Saved: {STORY_FILE}"
    )

    print(
        f"Saved: {SCRIPT_FILE}"
    )

    print()
    print("=" * 50)
    print("NEWS ENGINE COMPLETED SUCCESSFULLY")
    print("=" * 50)


if __name__ == "__main__":
    main()
