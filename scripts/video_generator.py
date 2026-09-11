import json
import re
import sys
import html
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parent.parent
STORY_FILE = ROOT / "data" / "story.json"
SCRIPT_FILE = ROOT / "data" / "script.json"

TIMEOUT = 25
MAX_STORIES = 12


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
]


RSS_SOURCES = [
    {
        "name": "Google News",
        "url": (
            "https://news.google.com/rss/search?"
            + urllib.parse.urlencode(
                {
                    "q": (
                        "Kenya Rift Valley county development "
                        "OR roads OR health OR education OR business"
                    ),
                    "hl": "en-KE",
                    "gl": "KE",
                    "ceid": "KE:en",
                }
            )
        ),
    },
    {
        "name": "Google News",
        "url": (
            "https://news.google.com/rss/search?"
            + urllib.parse.urlencode(
                {
                    "q": (
                        "Bomet OR Kericho OR Nakuru OR Narok OR Nandi "
                        "OR Uasin Gishu OR Turkana OR Samburu Kenya"
                    ),
                    "hl": "en-KE",
                    "gl": "KE",
                    "ceid": "KE:en",
                }
            )
        ),
    },
]


def clean_text(value):
    if value is None:
        return ""

    value = html.unescape(str(value))
    value = re.sub(r"<[^>]+>", " ", value)
    value = value.replace("\n", " ")
    value = re.sub(r"\s+", " ", value)

    return value.strip()


def fetch_url(url):
    request = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 "
                "RiftValleyWatch/1.0"
            )
        },
    )

    with urllib.request.urlopen(
        request,
        timeout=TIMEOUT,
    ) as response:
        return response.read()


def parse_date(value):
    value = clean_text(value)

    if not value:
        return datetime.now(timezone.utc).isoformat()

    formats = [
        "%a, %d %b %Y %H:%M:%S %Z",
        "%a, %d %b %Y %H:%M:%S %z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%SZ",
    ]

    for date_format in formats:
        try:
            parsed = datetime.strptime(value, date_format)
            return parsed.astimezone(timezone.utc).isoformat()
        except ValueError:
            continue

    return value


def parse_rss(xml_bytes, source_name):
    stories = []

    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as error:
        print(f"RSS parsing failed: {error}")
        return stories

    for item in root.findall(".//item"):
        title = clean_text(
            item.findtext("title")
        )

        link = clean_text(
            item.findtext("link")
        )

        description = clean_text(
            item.findtext("description")
        )

        published = parse_date(
            item.findtext("pubDate")
            or item.findtext("published")
            or ""
        )

        if not title or not link:
            continue

        stories.append(
            {
                "title": title,
                "url": link,
                "description": description,
                "published": published,
                "source": source_name,
            }
        )

    return stories


def fetch_live_stories():
    all_stories = []

    for source in RSS_SOURCES:
        print(f"Fetching live source: {source['name']}")

        try:
            xml_bytes = fetch_url(source["url"])
            stories = parse_rss(
                xml_bytes,
                source["name"],
            )
            all_stories.extend(stories)
        except Exception as error:
            print(
                f"Could not fetch {source['name']}: {error}"
            )

    return all_stories


def identify_county(text):
    text = clean_text(text).lower()

    for county in COUNTIES:
        if county.lower() in text:
            return county

    return "Rift Valley"


def classify_story(title, description):
    text = f"{title} {description}".lower()

    categories = [
        (
            "INFRASTRUCTURE",
            [
                "road",
                "bridge",
                "construction",
                "water project",
                "dam",
                "electricity",
            ],
        ),
        (
            "HEALTH",
            [
                "hospital",
                "health",
                "clinic",
                "medicine",
                "maternal",
                "disease",
            ],
        ),
        (
            "EDUCATION",
            [
                "school",
                "education",
                "student",
                "teacher",
                "university",
                "classroom",
            ],
        ),
        (
            "AGRICULTURE",
            [
                "farmer",
                "agriculture",
                "maize",
                "tea",
                "coffee",
                "livestock",
                "dairy",
            ],
        ),
        (
            "BUSINESS",
            [
                "business",
                "investment",
                "market",
                "trade",
                "company",
                "jobs",
                "employment",
            ],
        ),
        (
            "GOVERNANCE",
            [
                "county government",
                "governor",
                "deputy president",
                "president",
                "ministry",
                "government",
            ],
        ),
    ]

    for category, keywords in categories:
        if any(keyword in text for keyword in keywords):
            return category

    return "DEVELOPMENT"


def deduplicate_stories(stories):
    result = []
    seen = set()

    for story in stories:
        key = re.sub(
            r"[^a-z0-9]+",
            "",
            story["title"].lower(),
        )

        if not key or key in seen:
            continue

        seen.add(key)
        result.append(story)

    return result


def select_regional_stories(stories):
    stories = deduplicate_stories(stories)

    selected = []
    counties_seen = set()

    # First, prioritize county diversity.
    for story in stories:
        county = identify_county(
            f"{story['title']} {story['description']}"
        )

        if county not in counties_seen:
            story["county"] = county
            story["category"] = classify_story(
                story["title"],
                story["description"],
            )
            selected.append(story)
            counties_seen.add(county)

        if len(selected) >= MAX_STORIES:
            break

    # Fill remaining slots with other fresh stories.
    if len(selected) < MAX_STORIES:
        selected_keys = {
            story["title"]
            for story in selected
        }

        for story in stories:
            if story["title"] in selected_keys:
                continue

            story["county"] = identify_county(
                f"{story['title']} {story['description']}"
            )

            story["category"] = classify_story(
                story["title"],
                story["description"],
            )

            selected.append(story)

            if len(selected) >= MAX_STORIES:
                break

    return selected


def make_fallback_story():
    return {
        "title": (
            "Rift Valley Watch regional update"
        ),
        "county": "Rift Valley",
        "category": "DEVELOPMENT",
        "date": datetime.now(
            timezone.utc
        ).date().isoformat(),
        "source": "Live regional news feed",
        "source_url": "",
        "verified_facts": {
            "LOCATION": "Rift Valley, Kenya",
            "STATUS": "Live feed available",
            "IMPACT": (
                "Regional developments are being monitored "
                "across the Rift Valley."
            ),
        },
        "official_statement": {
            "speaker": "",
            "quote": "",
        },
        "stories": [],
        "summary": (
            "Rift Valley Watch is monitoring fresh developments "
            "across counties in the region."
        ),
    }


def build_story_payload(stories):
    if not stories:
        return make_fallback_story()

    current_date = datetime.now(
        timezone.utc
    ).date().isoformat()

    regional_items = []

    for story in stories:
        regional_items.append(
            {
                "title": story["title"],
                "county": story.get(
                    "county",
                    "Rift Valley",
                ),
                "category": story.get(
                    "category",
                    "DEVELOPMENT",
                ),
                "description": story.get(
                    "description",
                    "",
                ),
                "source": story.get(
                    "source",
                    "Live news feed",
                ),
                "url": story.get(
                    "url",
                    "",
                ),
                "published": story.get(
                    "published",
                    "",
                ),
            }
        )

    first = regional_items[0]

    return {
        "title": (
            "Rift Valley Watch: "
            f"{len(regional_items)} Fresh Regional Updates"
        ),
        "county": "Rift Valley",
        "category": "REGIONAL ROUNDUP",
        "date": current_date,
        "source": "Live RSS news feeds",
        "source_url": "",
        "verified_facts": {
            "LOCATION": "Rift Valley, Kenya",
            "STATUS": "Fresh stories collected automatically",
            "IMPACT": (
                "The roundup tracks current developments "
                "across counties in the Rift Valley."
            ),
        },
        "official_statement": {
            "speaker": "",
            "quote": "",
        },
        "stories": regional_items,
        "lead_story": first,
        "summary": (
            "Fresh regional developments collected from live "
            "news feeds covering the Rift Valley."
        ),
    }


def build_script(story):
    stories = story.get("stories", [])

    if not stories:
        return {
            "title": story["title"],
            "narration": [
                (
                    "This is Rift Valley Watch, tracking "
                    "verified developments across the region."
                )
            ],
            "scenes": [],
        }

    narration = [
        (
            "This is Rift Valley Watch, bringing you fresh "
            "developments from across Kenya's Rift Valley."
        )
    ]

    scenes = []

    for index, item in enumerate(stories, start=1):
        county = clean_text(
            item.get("county", "Rift Valley")
        )

        category = clean_text(
            item.get("category", "DEVELOPMENT")
        )

        title = clean_text(
            item.get("title", "")
        )

        description = clean_text(
            item.get("description", "")
        )

        source = clean_text(
            item.get("source", "Live news feed")
        )

        if description:
            spoken = (
                f"Update {index}, from {county}. "
                f"{title}. {description}. "
                f"Source: {source}."
            )
        else:
            spoken = (
                f"Update {index}, from {county}. "
                f"{title}. "
                f"Source: {source}."
            )

        narration.append(spoken)

        scenes.append(
            {
                "scene": index,
                "county": county,
                "category": category,
                "title": title,
                "description": description,
                "source": source,
                "source_url": item.get("url", ""),
                "narration": spoken,
            }
        )

    narration.append(
        "That is the latest regional roundup from Rift Valley Watch."
    )

    return {
        "title": story["title"],
        "generated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "narration": narration,
        "scenes": scenes,
    }


def save_json(path, payload):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with path.open("w", encoding="utf-8") as file:
        json.dump(
            payload,
            file,
            indent=2,
            ensure_ascii=False,
        )


def main():
    print("=" * 60)
    print("STARTING REAL-TIME RIFT VALLEY NEWS ENGINE")
    print("=" * 60)

    print("[1/4] Fetching live news...")
    live_stories = fetch_live_stories()

    print(
        f"Stories collected: {len(live_stories)}"
    )

    print("[2/4] Selecting regional coverage...")
    selected_stories = select_regional_stories(
        live_stories
    )

    print(
        f"Stories selected: {len(selected_stories)}"
    )

    print("[3/4] Building regional story...")
    story = build_story_payload(
        selected_stories
    )

    print("[4/4] Building narration script...")
    script = build_script(story)

    save_json(
        STORY_FILE,
        story,
    )

    save_json(
        SCRIPT_FILE,
        script,
    )

    print("=" * 60)
    print("REAL-TIME NEWS ENGINE SUCCESSFUL")
    print(f"Story file: {STORY_FILE}")
    print(f"Script file: {SCRIPT_FILE}")
    print(
        "Coverage: "
        + ", ".join(
            sorted(
                {
                    item.get(
                        "county",
                        "Rift Valley",
                    )
                    for item in selected_stories
                }
            )
        )
    )
    print("=" * 60)


if __name__ == "__main__":
    try:
        main()
    except Exception as error:
        print("=" * 60)
        print("NEWS ENGINE FAILED")
        print(str(error))
        print("=" * 60)
        sys.exit(1)
