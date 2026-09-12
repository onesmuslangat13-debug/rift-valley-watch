import json
import re
import html
from pathlib import Path
from urllib.parse import urlparse, urljoin

import requests
import xml.etree.ElementTree as ET

from rift_valley_video_generator import generate_video


# ============================================================
# RIFT VALLEY WATCH NEWS ENGINE V5
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
        "RiftValleyWatch/5.0"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,image/webp,"
        "*/*;q=0.8"
    ),
    "Accept-Language": "en-KE,en;q=0.9",
}

# These domains are NEVER acceptable as the final article.
BLOCKED_FINAL_DOMAINS = {
    "facebook.com",
    "m.facebook.com",
    "instagram.com",
    "youtube.com",
    "youtu.be",
    "tiktok.com",
}

# Google News is allowed as an intermediary.
GOOGLE_NEWS_DOMAINS = {
    "news.google.com",
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
    "sprite",
    "loading",
    "blank",
    "transparent",
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
        domain = urlparse(url).netloc.lower()

        return domain.replace(
            "www.",
            "",
        )

    except Exception:
        return ""


def is_social_domain(url):
    domain = get_domain(url)

    if not domain:
        return True

    for blocked in BLOCKED_FINAL_DOMAINS:
        if (
            domain == blocked
            or domain.endswith(
                "." + blocked
            )
        ):
            return True

    return False


def is_google_news_url(url):
    domain = get_domain(url)

    for google_domain in GOOGLE_NEWS_DOMAINS:
        if (
            domain == google_domain
            or domain.endswith(
                "." + google_domain
            )
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
        response.content
    )


# ============================================================
# RSS IMAGE EXTRACTION
# ============================================================

def get_rss_media_image(item):
    namespaces = [
        "http://search.yahoo.com/mrss/",
        "http://search.yahoo.com/mrss",
    ]

    for namespace in namespaces:

        for tag_name in [
            "content",
            "thumbnail",
        ]:

            element = item.find(
                f"{{{namespace}}}{tag_name}"
            )

            if element is not None:

                image_url = (
                    element.attrib.get(
                        "url"
                    )
                    or element.attrib.get(
                        "href"
                    )
                )

                if image_url:

                    image_url = html.unescape(
                        image_url
                    ).strip()

                    if not is_bad_image_url(
                        image_url
                    ):
                        return image_url

    # RSS enclosure
    enclosure = item.find(
        "enclosure"
    )

    if enclosure is not None:

        enclosure_url = (
            enclosure.attrib.get(
                "url",
                "",
            )
            or ""
        ).strip()

        enclosure_type = (
            enclosure.attrib.get(
                "type",
                "",
            )
            or ""
        ).lower()

        if (
            enclosure_url
            and (
                "image/" in enclosure_type
                or re.search(
                    r"\.(jpg|jpeg|png|webp|avif)(?:\?|$)",
                    enclosure_url,
                    re.I,
                )
            )
        ):

            if not is_bad_image_url(
                enclosure_url
            ):
                return enclosure_url

    return None


# ============================================================
# RSS PARSER
# ============================================================

def parse_feed(root):
    stories = []

    for item in root.findall(
        ".//item"
    ):

        title = clean_text(
            item.findtext(
                "title"
            )
        )

        link = (
            item.findtext(
                "link"
            )
            or ""
        ).strip()

        raw_description = (
            item.findtext(
                "description"
            )
            or ""
        )

        summary = clean_text(
            raw_description
        )

        published = (
            item.findtext(
                "pubDate"
            )
            or ""
        ).strip()

        source_element = item.find(
            "source"
        )

        source = ""

        if source_element is not None:

            source = clean_text(
                source_element.text
                or ""
            )

        # Try RSS media fields first.
        rss_image = (
            get_rss_media_image(
                item
            )
        )

        # Then try image embedded in description.
        description_image = (
            extract_image_from_html(
                raw_description,
                link,
            )
        )

        if not rss_image:
            rss_image = (
                description_image
            )

        if not title or not link:
            continue

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

    # --------------------------------------------------------
    # OpenGraph / Twitter
    # --------------------------------------------------------

    patterns = [

        r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)',

        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image["\']',

        r'<meta[^>]+property=["\']og:image:url["\'][^>]+content=["\']([^"\']+)',

        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+property=["\']og:image:url["\']',

        r'<meta[^>]+name=["\']twitter:image["\'][^>]+content=["\']([^"\']+)',

        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image["\']',

        r'<meta[^>]+name=["\']twitter:image:src["\'][^>]+content=["\']([^"\']+)',

        r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+name=["\']twitter:image:src["\']',
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

            image_url = urljoin(
                base_url,
                image_url,
            )

            if not is_bad_image_url(
                image_url
            ):
                return image_url

    # --------------------------------------------------------
    # JSON-LD image
    # --------------------------------------------------------

    matches = re.findall(
        r'"image"\s*:\s*"([^"]+)"',
        page,
        re.I,
    )

    for image_url in matches:

        image_url = html.unescape(
            image_url
        ).strip()

        image_url = urljoin(
            base_url,
            image_url,
        )

        if not is_bad_image_url(
            image_url
        ):
            return image_url

    # --------------------------------------------------------
    # JSON-LD image array
    # --------------------------------------------------------

    array_matches = re.findall(
        r'"image"\s*:\s*\[\s*"([^"]+)"',
        page,
        re.I,
    )

    for image_url in array_matches:

        image_url = html.unescape(
            image_url
        ).strip()

        image_url = urljoin(
            base_url,
            image_url,
        )

        if not is_bad_image_url(
            image_url
        ):
            return image_url

    # --------------------------------------------------------
    # Normal / lazy images
    # --------------------------------------------------------

    image_patterns = [
        r'<img[^>]+src=["\']([^"\']+)',
        r'<img[^>]+data-src=["\']([^"\']+)',
        r'<img[^>]+data-lazy-src=["\']([^"\']+)',
        r'<img[^>]+data-original=["\']([^"\']+)',
    ]

    for pattern in image_patterns:

        matches = re.findall(
            pattern,
            page,
            re.I,
        )

        for image_url in matches:

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
        "facebook.com",
        "fbcdn.net",
        "instagram.com",
        "cdninstagram.com",
        "tiktok.com",
    ]

    for domain in blocked_domains:

        if domain in lower:
            return True

    for term in BLOCKED_IMAGE_TERMS:

        if term in lower:
            return True

    if lower.endswith(
        ".svg"
    ):
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
            timeout=20,
            stream=True,
            allow_redirects=True,
        )

        if response.status_code != 200:
            return False

        final_url = response.url

        if is_bad_image_url(
            final_url
        ):
            return False

        content_type = (
            response.headers.get(
                "Content-Type",
                "",
            ).lower()
        )

        # Normal image response.
        if content_type.startswith(
            "image/"
        ):
            return True

        # Some publishers incorrectly label
        # their image content type.
        extensions = [
            ".jpg",
            ".jpeg",
            ".png",
            ".webp",
            ".avif",
        ]

        if any(
            ext in final_url.lower()
            for ext in extensions
        ):
            return True

        if any(
            ext in image_url.lower()
            for ext in extensions
        ):
            return True

        return False

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
                + re.escape(
                    property_name
                )
                + r'["\'][^>]+content=["\']([^"\']+)'
            ),
            (
                r'<meta[^>]+content=["\']([^"\']+)["\']'
                r'[^>]+property=["\']'
                + re.escape(
                    property_name
                )
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
                + re.escape(
                    name
                )
                + r'["\'][^>]+content=["\']([^"\']+)'
            ),
            (
                r'<meta[^>]+content=["\']([^"\']+)["\']'
                r'[^>]+name=["\']'
                + re.escape(
                    name
                )
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
# JSON-LD DESCRIPTION
# ============================================================

def extract_jsonld_description(
    page
):

    patterns = [
        r'"description"\s*:\s*"([^"]+)"',
        r'"articleBody"\s*:\s*"([^"]+)"',
    ]

    for pattern in patterns:

        matches = re.findall(
            pattern,
            page,
            re.I,
        )

        for value in matches:

            value = clean_text(
                value
            )

            if len(value) >= 40:

                return value

    return None


# ============================================================
# GOOGLE GENERIC TEXT CHECK
# ============================================================

def is_google_generic_text(
    text
):

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
# SUMMARY VALIDATION
# ============================================================

def usable_summary(
    text
):

    text = clean_text(
        text
    )

    if not text:
        return False

    if is_google_generic_text(
        text
    ):
        return False

    if len(text) < 30:
        return False

    return True


# ============================================================
# ARTICLE ENRICHMENT
# ============================================================

def enrich_story(
    story
):

    original_url = story.get(
        "url",
        "",
    )

    if not original_url:

        print(
            "Rejected: missing article URL."
        )

        return None

    # --------------------------------------------------------
    # IMPORTANT:
    #
    # Google News URLs ARE allowed here.
    #
    # We must follow them to the real publisher.
    # --------------------------------------------------------

    if is_social_domain(
        original_url
    ):

        print(
            "Rejected: blocked social URL."
        )

        return None

    try:

        print(
            f"Opening: {original_url}"
        )

        response = requests.get(
            original_url,
            headers=HEADERS,
            timeout=30,
            allow_redirects=True,
        )

        if response.status_code >= 400:

            print(
                f"Rejected: HTTP "
                f"{response.status_code}"
            )

            return None

        resolved_url = (
            response.url
        )

        print(
            f"Resolved URL: {resolved_url}"
        )

        # ----------------------------------------------------
        # Only the FINAL destination is checked.
        # ----------------------------------------------------

        if is_social_domain(
            resolved_url
        ):

            print(
                "Rejected: final URL is "
                "social media."
            )

            return None

        # If Google News did not redirect
        # to a publisher, reject it.
        if is_google_news_url(
            resolved_url
        ):

            print(
                "Rejected: Google News "
                "did not resolve to publisher."
            )

            return None

        story["resolved_url"] = (
            resolved_url
        )

        page = response.text[
            :6_000_000
        ]

        # ----------------------------------------------------
        # SOURCE
        # ----------------------------------------------------

        site_name = extract_meta(
            page,
            property_name="og:site_name",
        )

        if site_name:

            story["source"] = clean_text(
                site_name
            )

        if not story.get(
            "source"
        ):

            story["source"] = get_domain(
                resolved_url
            )

        if not story.get(
            "source"
        ):

            print(
                "Rejected: no source."
            )

            return None

        # ----------------------------------------------------
        # REAL TITLE
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
        # SUMMARY
        #
        # Priority:
        # 1. og:description
        # 2. meta description
        # 3. JSON-LD
        # 4. RSS description
        # ----------------------------------------------------

        description = extract_meta(
            page,
            property_name="og:description",
        )

        if not usable_summary(
            description
        ):

            description = extract_meta(
                page,
                name="description",
            )

        if not usable_summary(
            description
        ):

            description = (
                extract_jsonld_description(
                    page
                )
            )

        if usable_summary(
            description
        ):

            story["summary"] = clean_text(
                description
            )

        if not usable_summary(
            story.get(
                "summary",
                "",
            )
        ):

            rss_summary = clean_text(
                story.get(
                    "summary",
                    "",
                )
            )

            if usable_summary(
                rss_summary
            ):

                story["summary"] = (
                    rss_summary
                )

        # ----------------------------------------------------
        # IMAGE
        #
        # Priority:
        # 1. article metadata
        # 2. JSON-LD
        # 3. article img
        # 4. RSS media
        # ----------------------------------------------------

        image_url = extract_image_from_html(
            page,
            resolved_url,
        )

        if not image_url:

            image_url = story.get(
                "rss_image"
            )

        if not image_url:

            print(
                "Rejected: no image found."
            )

            return None

        image_url = urljoin(
            resolved_url,
            image_url,
        )

        print(
            f"Image candidate: {image_url}"
        )

        if not verify_image(
            image_url
        ):

            print(
                "Rejected: image failed "
                "verification."
            )

            return None

        story["image_url"] = (
            image_url
        )

        # ----------------------------------------------------
        # FINAL SUMMARY CHECK
        # ----------------------------------------------------

        summary = clean_text(
            story.get(
                "summary",
                "",
            )
        )

        if not usable_summary(
            summary
        ):

            print(
                "Rejected: no usable summary."
            )

            return None

        story["summary"] = (
            summary
        )

        print(
            "VERIFICATION PASSED"
        )

        print(
            f"Publisher: "
            f"{story.get('source')}"
        )

        print(
            f"Image: "
            f"{story.get('image_url')}"
        )

        print(
            f"Summary length: "
            f"{len(summary)} characters"
        )

        return story

    except requests.exceptions.Timeout:

        print(
            "Rejected: request timed out."
        )

        return None

    except requests.exceptions.RequestException as error:

        print(
            f"Rejected: request error: "
            f"{error}"
        )

        return None

    except Exception as error:

        print(
            f"Enrichment error: "
            f"{error}"
        )

        return None


# ============================================================
# SCORE STORY
# ============================================================

def score_story(
    story
):

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

def create_short_headline(
    title
):

    title = clean_text(
        title
    )

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

def build_narration(
    story
):

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
            .rsplit(
                " ",
                1
            )[0]
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
# COLLECT CANDIDATES
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
                    story[
                        "title"
                    ].lower(),
                ).strip()

                if not key:
                    continue

                if key in seen:
                    continue

                seen.add(
                    key
                )

                story["county"] = (
                    county
                )

                story["score"] = (
                    score_story(
                        story
                    )
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
            "No recent Rift Valley "
            "stories found."
        )

    print("")
    print(
        f"Found {len(candidates)} candidates."
    )

    maximum_checks = min(
        len(candidates),
        80,
    )

    for index, candidate in enumerate(
        candidates[
            :maximum_checks
        ],
        start=1,
    ):

        print("")
        print(
            f"Checking story {index}: "
            f"{candidate['title']} - "
            f"{candidate.get('source', '')}"
        )

        story = enrich_story(
            candidate
        )

        if not story:

            print(
                "Rejected: article did not "
                "pass verification."
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
            f"Title: "
            f"{story['title']}"
        )

        print(
            f"County: "
            f"{story.get('county')}"
        )

        print(
            f"Source: "
            f"{story.get('source')}"
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

        print(
            f"Summary: "
            f"{story.get('summary', '')[:300]}"
        )

        print("=" * 60)

        return story

    raise RuntimeError(
        "No recent story passed "
        "article verification."
    )


# ============================================================
# SAVE STORY
# ============================================================

def save_story(
    story
):

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
    print(
        "RIFT VALLEY WATCH NEWS ENGINE V5"
    )
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
    print(
        "RIFT VALLEY WATCH COMPLETE"
    )
    print("=" * 60)


if __name__ == "__main__":
    main()
