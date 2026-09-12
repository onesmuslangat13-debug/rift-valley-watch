import json
import re
import html
import time
from pathlib import Path
from urllib.parse import urlparse

import requests
import xml.etree.ElementTree as ET

from rift_valley_video_generator import generate_video


# ============================================================
# RIFT VALLEY WATCH — NEWS ENGINE
# ============================================================

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
    "million",
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
    "construction",
    "economy",
    "business",
]

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(X11; Linux x86_64) "
        "AppleWebKit/537.36 "
        "Chrome/120.0 Safari/537.36 "
        "RiftValleyWatch/2.0"
    )
}


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_text(value):
    value = html.unescape(value or "")
    value = re.sub(r"<script.*?</script>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<style.*?</style>", " ", value, flags=re.I | re.S)
    value = re.sub(r"<[^>]+>", " ", value)
    value = re.sub(r"\s+", " ", value)

    return value.strip()


# ============================================================
# GOOGLE NEWS RSS
# ============================================================

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
        timeout=25,
    )

    response.raise_for_status()

    return ET.fromstring(response.text)


# ============================================================
# RSS PARSER
# ============================================================

def parse_feed(root):
    stories = []

    for item in root.findall(".//item"):
        title = clean_text(
            item.findtext("title")
        )

        link = (
            item.findtext("link")
            or ""
        ).strip()

        description = clean_text(
            item.findtext("description")
        )

        published = (
            item.findtext("pubDate")
            or ""
        ).strip()

        source = clean_text(
            item.findtext("source")
        )

        if not title or not link:
            continue

        stories.append(
            {
                "title": title,
                "url": link,
                "summary": description,
                "published": published,
                "source": source,
            }
        )

    return stories


# ============================================================
# STORY SCORING
# ============================================================

def score_story(story):
    text = (
        f"{story.get('title', '')} "
        f"{story.get('summary', '')} "
        f"{story.get('source', '')}"
    ).lower()

    county_hits = sum(
        1
        for county in COUNTIES
        if county.lower() in text
    )

    keyword_hits = sum(
        1
        for keyword in KEYWORDS
        if keyword.lower() in text
    )

    score = (
        county_hits * 30
        + keyword_hits * 4
    )

    # Prefer stories that mention concrete numbers.
    if re.search(
        r"\b(?:ksh|kes|sh)\s?[\d,.]+",
        text,
        re.I,
    ):
        score += 8

    if re.search(
        r"\b\d+(?:\.\d+)?\s?(?:billion|million|km|kms)\b",
        text,
        re.I,
    ):
        score += 8

    return score


# ============================================================
# META TAG EXTRACTION
# ============================================================

def extract_meta(page, property_name=None, name=None):
    if property_name:
        pattern = (
            r'<meta[^>]+'
            r'property=["\']'
            + re.escape(property_name)
            + r'["\'][^>]+'
            r'content=["\']([^"\']+)'
        )

        match = re.search(
            pattern,
            page,
            re.I,
        )

        if match:
            return html.unescape(
                match.group(1)
            ).strip()

        # Reverse attribute order
        pattern = (
            r'<meta[^>]+'
            r'content=["\']([^"\']+)["\'][^>]+'
            r'property=["\']'
            + re.escape(property_name)
            + r'["\']'
        )

        match = re.search(
            pattern,
            page,
            re.I,
        )

        if match:
            return html.unescape(
                match.group(1)
            ).strip()

    if name:
        pattern = (
            r'<meta[^>]+'
            r'name=["\']'
            + re.escape(name)
            + r'["\'][^>]+'
            r'content=["\']([^"\']+)'
        )

        match = re.search(
            pattern,
            page,
            re.I,
        )

        if match:
            return html.unescape(
                match.group(1)
            ).strip()

        pattern = (
            r'<meta[^>]+'
            r'content=["\']([^"\']+)["\'][^>]+'
            r'name=["\']'
            + re.escape(name)
            + r'["\']'
        )

        match = re.search(
            pattern,
            page,
            re.I,
        )

        if match:
            return html.unescape(
                match.group(1)
            ).strip()

    return None


# ============================================================
# IMAGE VALIDATION
# ============================================================

def is_bad_image_url(image_url):
    if not image_url:
        return True

    lower = image_url.lower()

    blocked_domains = [
        "google.com",
        "googleusercontent.com",
        "gstatic.com",
        "googleapis.com",
        "news.google.com",
    ]

    for domain in blocked_domains:
        if domain in lower:
            return True

    blocked_terms = [
        "logo",
        "favicon",
        "icon",
        "placeholder",
        "default-image",
        "default_image",
        "avatar",
        "profile",
    ]

    for term in blocked_terms:
        if term in lower:
            return True

    return False


# ============================================================
# ARTICLE ENRICHMENT
# ============================================================

def enrich_story(story):
    try:
        response = requests.get(
            story["url"],
            headers=HEADERS,
            timeout=20,
            allow_redirects=True,
        )

        response.raise_for_status()

        resolved_url = response.url

        story["resolved_url"] = resolved_url

        page = response.text[:4_000_000]

        # ----------------------------------------------------
        # Real publisher
        # ----------------------------------------------------

        site_name = extract_meta(
            page,
            property_name="og:site_name",
        )

        if site_name:
            story["source"] = clean_text(
                site_name
            )

        # ----------------------------------------------------
        # Real headline
        # ----------------------------------------------------

        real_title = extract_meta(
            page,
            property_name="og:title",
        )

        if real_title:
            story["title"] = clean_text(
                real_title
            )

        # ----------------------------------------------------
        # Real article description
        # ----------------------------------------------------

        description = extract_meta(
            page,
            property_name="og:description",
        )

        if not description:
            description = extract_meta(
                page,
                name="description",
            )

        if description:
            description = clean_text(
                description
            )

            # Reject obvious Google metadata.
            google_phrases = [
                "comprehensive up-to-date news coverage",
                "aggregated from sources",
                "google news",
            ]

            if not any(
                phrase in description.lower()
                for phrase in google_phrases
            ):
                story["summary"] = description

        # ----------------------------------------------------
        # Real article image
        # ----------------------------------------------------

        image_url = extract_meta(
            page,
            property_name="og:image",
        )

        if image_url and not is_bad_image_url(
            image_url
        ):
            story["image_url"] = image_url
        else:
            story["image_url"] = None

        # ----------------------------------------------------
        # Reject Google as final publisher
        # ----------------------------------------------------

        parsed = urlparse(
            resolved_url
        )

        final_domain = (
            parsed.netloc
            .lower()
            .replace("www.", "")
        )

        blocked_final_domains = [
            "google.com",
            "news.google.com",
            "googleusercontent.com",
        ]

        if final_domain in blocked_final_domains:
            return None

        # ----------------------------------------------------
        # Require a genuine article image
        # ----------------------------------------------------

        if not story.get("image_url"):
            return None

        # ----------------------------------------------------
        # Require meaningful article summary
        # ----------------------------------------------------

        if not story.get("summary"):
            return None

        return story

    except Exception as error:
        story["enrichment_error"] = str(
            error
        )

        return None


# ============================================================
# HEADLINE CLEANING
# ============================================================

def create_short_headline(title):
    title = clean_text(title)

    # Remove common publisher suffixes.
    title = re.sub(
        r"\s*[-|]\s*(Citizen Digital|The Star|Nation|Tuko|KBC|Capital FM).*$",
        "",
        title,
        flags=re.I,
    )

    # Remove excessive punctuation.
    title = re.sub(
        r"\s+",
        " ",
        title,
    ).strip()

    return title


# ============================================================
# NARRATION
# ============================================================

def build_narration(story):
    title = create_short_headline(
        story["title"]
    )

    summary = clean_text(
        story.get("summary")
        or ""
    )

    source = clean_text(
        story.get("source")
        or "the published report"
    )

    if len(summary) > 500:
        summary = summary[:500].rsplit(
            " ",
            1,
        )[0] + "."

    return (
        f"Rift Valley Watch. "
        f"{title}. "
        f"{summary} "
        f"This development is being watched "
        f"for its impact on communities, "
        f"services, business and development "
        f"in the region. "
        f"Source: {source}."
    )


# ============================================================
# FIND STORIES
# ============================================================

def collect_candidates():
    candidates = []
    seen = set()

    for county in COUNTIES:
        query = (
            f'"{county}" Kenya when:1d'
        )

        print(
            f"Searching: {county}"
        )

        try:
            root = fetch_rss(
                query
            )

            stories = parse_feed(
                root
            )

            for story in stories:
                key = re.sub(
                    r"[^a-z0-9]+",
                    " ",
                    story["title"].lower(),
                ).strip()

                if not key:
                    continue

                if key in seen:
                    continue

                seen.add(key)

                story["county"] = county

                story["score"] = score_story(
                    story
                )

                candidates.append(
                    story
                )

        except Exception as error:
            print(
                f"Feed error for {county}: "
                f"{error}"
            )

    candidates.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    return candidates


# ============================================================
# SELECT BEST STORY
# ============================================================

def select_story():
    candidates = collect_candidates()

    if not candidates:
        raise RuntimeError(
            "No recent Rift Valley stories were found."
        )

    print("")
    print(
        f"Found {len(candidates)} candidates."
    )

    checked = 0

    for candidate in candidates[:30]:
        checked += 1

        print(
            f"Checking story {checked}: "
            f"{candidate['title']}"
        )

        story = enrich_story(
            candidate
        )

        if not story:
            print(
                "Rejected: no verified article "
                "image/source/summary."
            )
            continue

        story["title"] = create_short_headline(
            story["title"]
        )

        story["narration"] = build_narration(
            story
        )

        story["brand"] = (
            "Rift Valley Watch"
        )

        print("")
        print("=" * 60)
        print("SELECTED STORY")
        print("=" * 60)
        print(
            f"Title: {story['title']}"
        )
        print(
            f"County: {story.get('county')}"
        )
        print(
            f"Source: {story.get('source')}"
        )
        print(
            f"Image: {story.get('image_url')}"
        )
        print(
            f"URL: {story.get('resolved_url')}"
        )
        print("=" * 60)

        return story

    raise RuntimeError(
        "No candidate passed the article "
        "verification and image checks."
    )


# ============================================================
# SAVE STORY
# ============================================================

def save_story(story):
    Path(
        "data"
    ).mkdir(
        parents=True,
        exist_ok=True,
    )

    Path(
        "data/story.json"
    ).write_text(
        json.dumps(
            story,
            indent=2,
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )

    print(
        "Saved: data/story.json"
    )


# ============================================================
# MAIN
# ============================================================

def main():
    print("")
    print("=" * 60)
    print("RIFT VALLEY WATCH NEWS ENGINE")
    print("=" * 60)

    story = select_story()

    save_story(
        story
    )

    print("")
    print(
        "Starting video generation..."
    )

    generate_video(
        story
    )

    print("")
    print("=" * 60)
    print("RIFT VALLEY WATCH COMPLETE")
    print("=" * 60)


if __name__ == "__main__":
    main()
