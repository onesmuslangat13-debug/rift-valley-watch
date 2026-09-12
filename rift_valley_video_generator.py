import json
import re
import html
import time
from pathlib import Path
import requests
import xml.etree.ElementTree as ET




COUNTIES = [
    "Bomet",
    "Kericho",
    "Nakuru",
    "Nandi",
    "Uasin Gishu",
    "Elgeyo-Marakwet",
    "West Pokot",
    "Narok",
]

KEYWORDS = [
    "project",
    "road",
    "hospital",
    "school",
    "water",
    "jobs",
    "investment",
    "funding",
    "billion",
    "county",
    "government",
    "governor",
    "president",
    "minister",
    "development",
    "agriculture",
    "tourism",
    "education",
    "health",
    "infrastructure",
    "trade",
    "manufacturing",
    "farmers",
]

HEADERS = {
    "User-Agent": "RiftValleyWatch/1.0"
}


def clean_text(value):
    value = html.unescape(value or "")
    value = re.sub(r"<[^>]+>", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def fetch_rss(query):
    url = "https://news.google.com/rss/search"

    response = requests.get(
        url,
        params={
            "q": query,
            "hl": "en-KE",
            "gl": "KE",
            "ceid": "KE:en",
        },
        headers=HEADERS,
        timeout=20,
    )

    response.raise_for_status()

    return ET.fromstring(response.text)


def parse_feed(root):
    stories = []

    for item in root.findall(".//item"):
        title = clean_text(item.findtext("title"))
        link = item.findtext("link") or ""
        description = clean_text(item.findtext("description"))
        published = item.findtext("pubDate") or ""
        source = clean_text(item.findtext("source"))

        if title and link:
            stories.append({
                "title": title,
                "url": link,
                "summary": description,
                "published": published,
                "source": source,
            })

    return stories


def score_story(story):
    text = (
        f"{story['title']} {story['summary']}"
    ).lower()

    county_hits = sum(
        1
        for county in COUNTIES
        if county.lower() in text
    )

    keyword_hits = sum(
        1
        for keyword in KEYWORDS
        if keyword in text
    )

    return (
        county_hits * 20
        + keyword_hits * 3
    )


def enrich_story(story):

    try:

        response = requests.get(
            story["url"],
            headers=HEADERS,
            timeout=15,
            allow_redirects=True,
        )

        story["resolved_url"] = response.url

        page = response.text[:2_000_000]

        image_match = re.search(
            r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
            page,
            re.I,
        )

        if not image_match:

            image_match = re.search(
                r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image',
                page,
                re.I,
            )

        if image_match:
            story["image_url"] = html.unescape(
                image_match.group(1)
            )
        else:
            story["image_url"] = None

        description_match = re.search(
            r'<meta[^>]+name=["\']description["\'][^>]+content=["\']([^"\']+)',
            page,
            re.I,
        )

        if description_match:
            story["summary"] = clean_text(
                html.unescape(
                    description_match.group(1)
                )
            )

    except Exception as error:

        story["image_url"] = None
        story["error"] = str(error)

    return story


def build_narration(story):

    summary = (
        story.get("summary")
        or
        "A new regional development and current affairs story is being reported."
    )

    return (
        f"Rift Valley Watch. "
        f"{story['title']}. "
        f"{summary} "
        f"The report is being followed for its potential "
        f"impact on communities, services, business and "
        f"development in the Rift Valley. "
        f"Source: {story.get('source') or 'published report'}."
    )


def main():

    candidates = []
    seen = set()

    for county in COUNTIES:

        query = f'"{county}" Kenya when:1d'

        try:

            root = fetch_rss(query)

            stories = parse_feed(root)

            for story in stories:

                key = re.sub(
                    r"[^a-z0-9]+",
                    " ",
                    story["title"].lower(),
                ).strip()

                if key in seen:
                    continue

                seen.add(key)

                story["score"] = score_story(story)
                story["county"] = county

                candidates.append(story)

        except Exception as error:

            print(
                f"Feed error for {county}: {error}"
            )

    candidates.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    selected = None

    for story in candidates[:15]:

        story = enrich_story(story)

        if story.get("image_url"):

            selected = story
            break

        time.sleep(0.2)

    if not selected:

        raise RuntimeError(
            "No recent candidate with a usable article image was found."
        )

    selected["narration"] = build_narration(
        selected
    )

    selected["brand"] = "Rift Valley Watch"

    Path("data").mkdir(
        exist_ok=True
    )

    Path(
        "data/story.json"
    ).write_text(
        json.dumps(
            selected,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    generate_video(selected)


if __name__ == "__main__":
    main()
