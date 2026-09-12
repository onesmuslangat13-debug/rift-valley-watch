import json
import re
import html
import time
from pathlib import Path
from urllib.parse import urlparse, urljoin

import requests
import xml.etree.ElementTree as ET

from rift_valley_video_generator import generate_video


# ============================================================
# RIFT VALLEY WATCH NEWS ENGINE V3
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
        "RiftValleyWatch/3.0"
    )
}

BLOCKED_DOMAINS = {
    "google.com",
    "news.google.com",
    "facebook.com",
    "m.facebook.com",
    "youtube.com",
    "instagram.com",
    "tiktok.com",
}

BLOCKED_IMAGE_TERMS = [
    "logo",
    "favicon",
    "icon",
    "placeholder",
    "default-image",
    "default_image",
    "avatar",
    "profile",
]


# ============================================================
# CLEAN TEXT
# ============================================================

def clean_text(value):
    value = html.unescape(value or "")

    value = re.sub(
        r"<script.*?</script>",
        " ",
        value,
        flags=re.I | re.S,
    )

    value = re.sub(
        r"<style.*?</style>",
        " ",
        value,
        flags=re.I | re.S,
    )

    value = re.sub(
        r"<[^>]+>",
        " ",
        value,
    )

    value = re.sub(
        r"\s+",
        " ",
        value,
    )

    return value.strip()


# ============================================================
# DOMAIN
# ============================================================

def get_domain(url):
    try:
        domain = urlparse(
            url
        ).netloc.lower()

        return domain.replace(
            "www.",
            "",
        )
    except Exception:
        return ""


def is_blocked_domain(url):
    domain = get_domain(url)

    if not domain:
        return True

    for blocked in BLOCKED_DOMAINS:
        if (
            domain == blocked
            or domain.endswith("." + blocked)
        ):
            return True

    return False


# ============================================================
# RSS
# ============================================================

def fetch_rss(query):
    response = requests.get(
        "https://news.google.com/rss/search",
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

    return ET.fromstring(
        response.text
    )


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

        raw_description = (
            item.findtext("description")
            or ""
        )

        summary = clean_text(
            raw_description
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

        # Try to extract an image directly
        # from the RSS description.
        rss_image = extract_image_from_html(
            raw_description,
            link,
        )

        stories.append(
            {
                "title": title,
                "url": link,
                "summary": summary,
                "raw_description": raw_description,
                "published": published,
                "source": source,
                "rss_image": rss_image,
            }
        )

    return stories


# ============================================================
# IMAGE EXTRACTION FROM HTML
# ============================================================

def extract_image_from_html(
    page,
    base_url,
):
    if not page:
        return None

    # og:image
    patterns = [
        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',
        r'<meta[^>]+property=["\']og:image:url["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',
        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            page,
            re.I,
        )

        if match:
            image_url = html.unescape(
                match.group(1)
            ).strip()

            return urljoin(
                base_url,
                image_url,
            )

    # Ordinary image tag
    image_matches = re.findall(
        r'<img[^>]+src=["\']([^"\']+)',
        page,
        re.I,
    )

    for image_url in image_matches:

        image_url = html.unescape(
            image_url
        ).strip()

        full_url = urljoin(
            base_url,
            image_url,
        )

        if not is_bad_image_url(
            full_url
        ):
            return full_url

    return None


# ============================================================
# IMAGE QUALITY FILTER
# ============================================================

def is_bad_image_url(url):
    if not url:
        return True

    lower = url.lower()

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

    for term in BLOCKED_IMAGE_TERMS:
        if term in lower:
            return True

    return False


# ============================================================
# VERIFY IMAGE
# ============================================================

def verify_image(image_url):
    if not image_url:
        return False

    if is_bad_image_url(
        image_url
    ):
        return False

    try:
        response = requests.get(
            image_url,
            headers=HEADERS,
            timeout=15,
            stream=True,
        )

        if response.status_code != 200:
            return False

        content_type = (
            response.headers.get(
                "Content-Type",
                "",
            ).lower()
        )

        if (
            "image/" not in content_type
            and not any(
                ext in image_url.lower()
                for ext in [
                    ".jpg",
                    ".jpeg",
                    ".png",
                    ".webp",
                ]
            )
        ):
            return False

        return True

    except Exception:
        return False


# ============================================================
# META EXTRACTION
# ============================================================

def extract_meta(
    page,
    property_name=None,
    name=None,
):
    if property_name:

        patterns = [
            (
                r'<meta[^>]+property=["\']'
                + re.escape(property_name)
                + r'["\'][^>]+content=["\']([^"\']+)'
            ),
            (
                r'<meta[^>]+content=["\']([^"\']+)["\']'
                r'[^>]+property=["\']'
                + re.escape(property_name)
                + r'["\']'
            ),
        ]

        for pattern in patterns:
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

        patterns = [
            (
                r'<meta[^>]+name=["\']'
                + re.escape(name)
                + r'["\'][^>]+content=["\']([^"\']+)'
            ),
            (
                r'<meta[^>]+content=["\']([^"\']+)["\']'
                r'[^>]+name=["\']'
                + re.escape(name)
                + r'["\']'
            ),
        ]

        for pattern in patterns:
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
# GOOGLE DESCRIPTION CHECK
# ============================================================

def is_google_generic_text(text):
    if not text:
        return True

    lower = text.lower()

    bad_phrases = [
        "comprehensive up-to-date news coverage",
        "aggregated from sources all over the world",
        "aggregated from sources",
        "google news",
    ]

    return any(
        phrase in lower
        for phrase in bad_phrases
    )


# ============================================================
# ARTICLE ENRICHMENT
# ============================================================

def enrich_story(story):

    original_url = story["url"]

    # --------------------------------------------------------
    # Reject obvious social media results immediately
    # --------------------------------------------------------

    if is_blocked_domain(
        original_url
    ):
        return None

    try:

        response = requests.get(
            original_url,
            headers=HEADERS,
            timeout=20,
            allow_redirects=True,
        )

        if response.status_code >= 400:
            return None

        resolved_url = response.url

        # ----------------------------------------------------
        # Reject Facebook/Google final URLs
        # ----------------------------------------------------

        if is_blocked_domain(
            resolved_url
        ):
            return None

        story["resolved_url"] = (
            resolved_url
        )

        page = response.text[
            :4_000_000
        ]

        # ----------------------------------------------------
        # Publisher
        # ----------------------------------------------------

        site_name = extract_meta(
            page,
            property_name="og:site_name",
        )

        if site_name:
            story["source"] = clean_text(
                site_name
            )

        # If publisher wasn't found in metadata,
        # retain RSS publisher.
        if not story.get("source"):
            story["source"] = get_domain(
                resolved_url
            )

        # ----------------------------------------------------
        # Real title
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
        # Real summary
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

        description = clean_text(
            description or ""
        )

        if (
            description
            and not is_google_generic_text(
                description
            )
            and len(description) >= 40
        ):
            story["summary"] = (
                description
            )

        # Otherwise use the RSS description.
        if (
            not story.get("summary")
            or is_google_generic_text(
                story["summary"]
            )
        ):
            rss_summary = clean_text(
                story.get(
                    "summary",
                    "",
                )
            )

            if (
                rss_summary
                and not is_google_generic_text(
                    rss_summary
                )
            ):
                story["summary"] = (
                    rss_summary
                )

        # ----------------------------------------------------
        # Image
        # ----------------------------------------------------

        image_url = extract_image_from_html(
            page,
            resolved_url,
        )

        # If article page did not expose image,
        # use RSS image.
        if not image_url:
            image_url = story.get(
                "rss_image"
            )

        if not image_url:
            return None

        image_url = urljoin(
            resolved_url,
            image_url,
        )

        if not verify_image(
            image_url
        ):
            print(
                "Rejected: image could not "
                "be verified."
            )
            return None

        story["image_url"] = (
            image_url
        )

        # ----------------------------------------------------
        # Require usable summary
        # ----------------------------------------------------

        summary = clean_text(
            story.get(
                "summary",
                "",
            )
        )

        if (
            not summary
            or len(summary) < 30
            or is_google_generic_text(
                summary
            )
        ):
            print(
                "Rejected: article summary "
                "is not usable."
            )
            return None

        story["summary"] = summary

        return story

    except Exception as error:

        print(
            f"Enrichment error: {error}"
        )

        return None


# ============================================================
# SCORE STORY
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

    if re.search(
        r"\b\d+(?:\.\d+)?\s?"
        r"(?:billion|million|km|kms)\b",
        text,
        re.I,
    ):
        score += 8

    if re.search(
        r"\b(?:ksh|kes|sh)\s?[\d,.]+",
        text,
        re.I,
    ):
        score += 8

    return score


# ============================================================
# HEADLINE
# ============================================================

def create_short_headline(title):

    title = clean_text(
        title
    )

    # Remove publisher suffixes.
    title = re.sub(
        r"\s*[-|]\s*"
        r"(Citizen Digital|"
        r"The Star|"
        r"Nation|"
        r"Tuko|"
        r"KBC|"
        r"Capital FM|"
        r"People Daily).*$",
        "",
        title,
        flags=re.I,
    )

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
        story.get(
            "summary",
            "",
        )
    )

    source = clean_text(
        story.get(
            "source",
            "the published report",
        )
    )

    if len(summary) > 500:
        summary = (
            summary[:500]
            .rsplit(" ", 1)[0]
            + "."
        )

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
# COLLECT STORIES
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

                story["county"] = (
                    county
                )

                story["score"] = (
                    score_story(story)
                )

                candidates.append(
                    story
                )

        except Exception as error:

            print(
                f"Feed error for "
                f"{county}: {error}"
            )

    candidates.sort(
        key=lambda item: item["score"],
        reverse=True,
    )

    return candidates


# ============================================================
# SELECT STORY
# ============================================================

def select_story():

    candidates = (
        collect_candidates()
    )

    if not candidates:

        raise RuntimeError(
            "No recent Rift Valley stories found."
        )

    print("")
    print(
        f"Found {len(candidates)} candidates."
    )

    checked = 0

    for candidate in candidates[:40]:

        checked += 1

        print("")
        print(
            f"Checking story {checked}: "
            f"{candidate['title']}"
        )

        story = enrich_story(
            candidate
        )

        if not story:

            print(
                "Rejected: no verified "
                "article image/source/summary."
            )

            continue

        story["title"] = (
            create_short_headline(
                story["title"]
            )
        )

        story["narration"] = (
            build_narration(
                story
            )
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
            f"Published: "
            f"{story.get('published')}"
        )
        print(
            f"Image: "
            f"{story.get('image_url')}"
        )
        print(
            f"URL: "
            f"{story.get('resolved_url')}"
        )
        print("=" * 60)

        return story

    raise RuntimeError(
        "No recent story passed the "
        "image and article verification checks."
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
