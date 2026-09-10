# ============================================================
# RIFT VALLEY WATCH V1.2
# OFFICIAL-SOURCE REGIONAL NEWS ENGINE
#
# COVERAGE:
# Bomet | Kericho | Nakuru | Nandi
# Uasin Gishu | Elgeyo-Marakwet | West Pokot | Narok
#
# SOURCES:
# Official county/government websites only
#
# PIPELINE:
# OFFICIAL SOURCES
#       ↓
# STORY EXTRACTION
#       ↓
# COUNTY DETECTION
#       ↓
# CATEGORY DETECTION
#       ↓
# POLITICAL / ACCOUNTABILITY SCORING
#       ↓
# STORY RANKING
#       ↓
# ONE STORY
#       ↓
# data/story.json
# ============================================================

import json
import os
import re
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


# ============================================================
# PATHS
# ============================================================

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

CONFIG_FILE = os.path.join(BASE_DIR, "config", "settings.json")
STORY_FILE = os.path.join(BASE_DIR, "data", "story.json")


# ============================================================
# OFFICIAL SOURCES ONLY
# ============================================================

OFFICIAL_SOURCES = {
    "Bomet": {
        "name": "Bomet County Government",
        "url": "https://bomet.go.ke/news/"
    },
    "Kericho": {
        "name": "Kericho County Government",
        "url": "https://www.kericho.go.ke/"
    },
    "Nakuru": {
        "name": "Nakuru County Government",
        "url": "https://www.nakuru.go.ke/"
    },
    "Nandi": {
        "name": "Nandi County Government",
        "url": "https://nandi.go.ke/news/"
    },
    "Uasin Gishu": {
        "name": "Uasin Gishu County Government",
        "url": "https://uasingishu.go.ke/"
    },
    "Elgeyo-Marakwet": {
        "name": "Elgeyo-Marakwet County Government",
        "url": "https://elgeyomarakwet.go.ke/news/"
    },
    "West Pokot": {
        "name": "West Pokot County Government",
        "url": "https://www.westpokot.go.ke/"
    },
    "Narok": {
        "name": "Narok County Government",
        "url": "https://www.narok.go.ke/"
    }
}


# ============================================================
# COUNTY KEYWORDS
# ============================================================

COUNTY_KEYWORDS = {
    "Bomet": [
        "bomet",
        "bomet county"
    ],

    "Kericho": [
        "kericho",
        "kericho county"
    ],

    "Nakuru": [
        "nakuru",
        "nakuru county"
    ],

    "Nandi": [
        "nandi",
        "nandi county"
    ],

    "Uasin Gishu": [
        "uasin gishu",
        "eldoret",
        "uasin gishu county"
    ],

    "Elgeyo-Marakwet": [
        "elgeyo",
        "marakwet",
        "elgeyo-marakwet",
        "elgeyo marakwet"
    ],

    "West Pokot": [
        "west pokot",
        "pokot",
        "kapenguria",
        "west pokot county"
    ],

    "Narok": [
        "narok",
        "narok county",
        "maasai mara"
    ]
}


# ============================================================
# CATEGORIES
# ============================================================

CATEGORIES = {
    "BREAKING NEWS": [
        "breaking",
        "urgent",
        "alert",
        "rescue",
        "incident",
        "crash",
        "accident",
        "fire",
        "missing",
        "killed",
        "death",
        "fatal",
        "arrested"
    ],

    "POLITICS": [
        "governor",
        "senator",
        "mca",
        "mp ",
        "member of parliament",
        "politician",
        "political",
        "election",
        "elections",
        "campaign",
        "party",
        "ward",
        "assembly",
        "county assembly",
        "deputy governor",
        "president",
        "government"
    ],

    "ACCOUNTABILITY": [
        "audit",
        "auditor",
        "auditor-general",
        "procurement",
        "tender",
        "tenders",
        "contract",
        "contracts",
        "budget",
        "budgets",
        "funds",
        "money",
        "expenditure",
        "spending",
        "irregular",
        "misuse",
        "mismanagement",
        "corruption",
        "investigation",
        "accountability",
        "oversight",
        "pending bills",
        "unpaid bills",
        "revenue",
        "loss",
        "losses"
    ],

    "DEVELOPMENT": [
        "project",
        "projects",
        "road",
        "roads",
        "bridge",
        "bridges",
        "water",
        "infrastructure",
        "construction",
        "constructed",
        "development",
        "stadium",
        "market",
        "markets",
        "housing",
        "electricity",
        "street lighting"
    ],

    "SECURITY": [
        "police",
        "security",
        "crime",
        "robbery",
        "theft",
        "suspect",
        "arrest",
        "arrested",
        "dci",
        "investigation",
        "bandit",
        "bandits",
        "attack",
        "attacked",
        "terror",
        "terrorism"
    ],

    "AGRICULTURE": [
        "agriculture",
        "farmer",
        "farmers",
        "farming",
        "coffee",
        "tea",
        "maize",
        "fertilizer",
        "livestock",
        "dairy",
        "crops",
        "harvest",
        "irrigation",
        "seedlings",
        "seeds"
    ],

    "HEALTH": [
        "health",
        "hospital",
        "hospitals",
        "doctor",
        "doctors",
        "nurse",
        "nurses",
        "clinic",
        "medical",
        "medicine",
        "disease",
        "vaccination",
        "immunization",
        "maternal",
        "healthcare"
    ],

    "EDUCATION": [
        "education",
        "school",
        "schools",
        "student",
        "students",
        "teacher",
        "teachers",
        "university",
        "college",
        "bursary",
        "scholarship",
        "scholars",
        "training"
    ],

    "BUSINESS": [
        "business",
        "businesses",
        "trade",
        "traders",
        "market",
        "markets",
        "investment",
        "investor",
        "investors",
        "industry",
        "industrial",
        "enterprise",
        "employment",
        "jobs",
        "economy"
    ],

    "COMMUNITY": [
        "community",
        "residents",
        "youth",
        "women",
        "groups",
        "leaders",
        "families",
        "social",
        "empowerment",
        "donation",
        "charity"
    ],

    "TOURISM": [
        "tourism",
        "tourist",
        "tourists",
        "hotel",
        "hotels",
        "wildlife",
        "park",
        "parks",
        "mara",
        "attraction",
        "tour"
    ]
}


# ============================================================
# GENERIC / NON-STORY TITLES
# ============================================================

GENERIC_TITLES = {
    "recent news",
    "recent news events",
    "recent news & events",
    "news & events",
    "news and events",
    "latest news",
    "latest updates",
    "latest update",
    "news",
    "events",
    "news updates",
    "latest news and events",
    "recent updates",
    "our news",
    "county news",
    "featured news",
    "news headlines",
    "latest stories",
    "recent stories",
    "our latest news",
    "latest developments",
    "updates",
    "announcements",
    "notice",
    "notices",
    "press releases",
    "press release",
    "news and events",
    "news events"
}


# ============================================================
# WEAK / NON-NEWS TERMS
# ============================================================

WEAK_TERMS = [
    "photo gallery",
    "gallery",
    "advertisement",
    "advert",
    "vacancy",
    "job vacancy",
    "careers",
    "career opportunity",
    "tender notice",
    "download",
    "login",
    "register",
    "contact us",
    "privacy policy",
    "terms and conditions"
]


# ============================================================
# REQUEST SETTINGS
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 Chrome/131.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    )
}

TIMEOUT = 20


# ============================================================
# HELPERS
# ============================================================

def normalize_text(text):
    """Normalize whitespace and common HTML spacing."""

    if not text:
        return ""

    text = str(text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def normalize_title(title):
    """Normalize title for comparison."""

    title = normalize_text(title).lower()

    title = title.replace("–", "-")
    title = title.replace("—", "-")

    title = re.sub(r"[^\w\s&-]", "", title)
    title = re.sub(r"\s+", " ", title)

    return title.strip()


def is_generic_title(title):
    """Reject page headings that are not actual stories."""

    normalized = normalize_title(title)

    if not normalized:
        return True

    if normalized in GENERIC_TITLES:
        return True

    # Catch variations such as:
    # "Recent News & Events 2026"
    # "Latest News and Events"
    if normalized.startswith("recent news"):
        return True

    if normalized.startswith("latest news"):
        return True

    if normalized.startswith("news & events"):
        return True

    if normalized.startswith("news and events"):
        return True

    if normalized.startswith("recent updates"):
        return True

    return False


def is_weak_title(title):
    """Reject obvious non-news content."""

    normalized = normalize_title(title)

    for term in WEAK_TERMS:
        if term in normalized:
            return True

    return False


def word_count(text):
    return len(normalize_text(text).split())


def title_is_reasonable(title):
    """
    A genuine news title normally has enough information
    to stand on its own.
    """

    title = normalize_text(title)

    if not title:
        return False

    if is_generic_title(title):
        return False

    if is_weak_title(title):
        return False

    words = word_count(title)

    if words < 4:
        return False

    if len(title) < 25:
        return False

    return True


def normalize_url(url):
    if not url:
        return ""

    url = url.strip()

    if url.startswith("//"):
        url = "https:" + url

    return url


def url_is_bad(url, source_url):
    """
    Reject navigation, category, template and section links.
    """

    if not url:
        return True

    url = normalize_url(url)

    if url.startswith("#"):
        return True

    if url.lower().startswith("javascript:"):
        return True

    if url.lower().startswith("mailto:"):
        return True

    absolute_url = urljoin(source_url, url)

    source_parsed = urlparse(source_url)
    candidate_parsed = urlparse(absolute_url)

    source_path = source_parsed.path.rstrip("/").lower()
    candidate_path = candidate_parsed.path.rstrip("/").lower()

    # Same page as source
    if absolute_url.rstrip("/") == source_url.rstrip("/"):
        return True

    if candidate_path == source_path:
        return True

    # Common section/navigation paths
    bad_path_parts = [
        "/templates/",
        "/category/",
        "/categories/",
        "/tag/",
        "/tags/",
        "/page/",
        "/author/",
        "/search",
        "/events",
        "/gallery",
        "/contact",
        "/about",
        "/login",
        "/register"
    ]

    for bad_part in bad_path_parts:
        if bad_part in candidate_path:
            return True

    # Specific known generic page from Kericho
    if "news_and_events" in candidate_path:
        return True

    # Generic news index itself
    if candidate_path.endswith("/news"):
        return True

    # Generic events index
    if candidate_path.endswith("/events"):
        return True

    return False


def likely_story_link(title, href, source_url):
    """
    Determine whether an <a> element is probably a real
    individual story rather than navigation.
    """

    if not title_is_reasonable(title):
        return False

    if url_is_bad(href, source_url):
        return False

    # A useful story title usually contains several words.
    if word_count(title) < 5:
        return False

    return True


# ============================================================
# COUNTY DETECTION
# ============================================================

def detect_county(text):
    text = normalize_text(text).lower()

    scores = {}

    for county, keywords in COUNTY_KEYWORDS.items():
        score = 0

        for keyword in keywords:
            if keyword in text:
                score += 1

        if score:
            scores[county] = score

    if not scores:
        return None

    return max(scores, key=scores.get)


# ============================================================
# CATEGORY DETECTION
# ============================================================

def detect_category(text):

    text = normalize_text(text).lower()

    scores = {}

    for category, keywords in CATEGORIES.items():

        score = 0

        for keyword in keywords:

            if keyword in text:
                score += 1

        if score:
            scores[category] = score

    if not scores:
        return "COMMUNITY"

    return max(scores, key=scores.get)


# ============================================================
# POLITICAL SCORE
# ============================================================

def political_score(text):

    text = normalize_text(text).lower()

    terms = CATEGORIES["POLITICS"]

    score = 0

    for term in terms:
        if term in text:
            score += 4

    return score


# ============================================================
# ACCOUNTABILITY SCORE
# ============================================================

def accountability_score(text):

    text = normalize_text(text).lower()

    terms = CATEGORIES["ACCOUNTABILITY"]

    score = 0

    for term in terms:
        if term in text:
            score += 5

    return score


# ============================================================
# STORY SCORE
# ============================================================

def score_story(story):

    title = normalize_text(story.get("title", ""))
    summary = normalize_text(story.get("summary", ""))

    combined = f"{title} {summary}".lower()

    score = 0

    # County relevance
    if story.get("county"):
        score += 20

    # Political importance
    score += story.get("political_score", 0)

    # Accountability importance
    score += story.get("accountability_score", 0)

    # Title quality
    title_words = word_count(title)

    if title_words >= 7:
        score += 10

    elif title_words >= 5:
        score += 5

    # Summary depth
    summary_words = word_count(summary)

    if summary_words >= 60:
        score += 10

    elif summary_words >= 30:
        score += 5

    # Strong news terms
    high_priority_terms = [
        "launches",
        "launched",
        "approves",
        "approved",
        "allocates",
        "allocated",
        "investigation",
        "audit",
        "auditor",
        "budget",
        "project",
        "hospital",
        "road",
        "water",
        "security",
        "arrested",
        "governor",
        "county assembly"
    ]

    for term in high_priority_terms:

        if term in combined:
            score += 3

    # Weak content penalties
    for term in WEAK_TERMS:

        if term in combined:
            score -= 15

    return score


# ============================================================
# FETCH SOURCE
# ============================================================

def fetch_source(county, source):

    print(f"      Fetching: {source['name']}")

    try:

        response = requests.get(
            source["url"],
            headers=HEADERS,
            timeout=TIMEOUT
        )

        response.raise_for_status()

        return response.text

    except Exception as exc:

        print(
            f"      [WARNING] Could not fetch "
            f"{source['name']}: {exc}"
        )

        return None


# ============================================================
# EXTRACT SUMMARY FROM CONTAINER
# ============================================================

def extract_summary(container, title):

    if container is None:
        return ""

    paragraphs = []

    # First look for actual paragraphs
    for p in container.find_all("p"):

        text = normalize_text(p.get_text(" ", strip=True))

        if not text:
            continue

        if text.lower() == title.lower():
            continue

        if len(text) < 40:
            continue

        paragraphs.append(text)

    # Remove duplicates
    unique = []

    for text in paragraphs:

        if text not in unique:
            unique.append(text)

    summary = " ".join(unique)

    # Limit size
    if len(summary) > 1000:
        summary = summary[:1000].rsplit(" ", 1)[0] + "..."

    return summary


# ============================================================
# FIND STORY CONTAINER
# ============================================================

def find_story_container(anchor):

    """
    Move upward from the story link and find a reasonable
    article/list/div container without swallowing the entire
    webpage.
    """

    # Best case: actual article
    article = anchor.find_parent("article")

    if article is not None:
        return article

    # Next best: list item
    li = anchor.find_parent("li")

    if li is not None:

        text = normalize_text(li.get_text(" ", strip=True))

        if len(text) <= 2500:
            return li

    # Try limited div ancestors
    current = anchor.parent

    for _ in range(4):

        if current is None:
            break

        if current.name == "div":

            text = normalize_text(
                current.get_text(" ", strip=True)
            )

            if 50 <= len(text) <= 2500:
                return current

        current = current.parent

    return anchor.parent


# ============================================================
# EXTRACT STORIES — LINK CENTRIC
# ============================================================

def extract_stories(html, county, source):

    soup = BeautifulSoup(html, "html.parser")

    # Remove elements that cannot contain useful stories
    for tag in soup([
        "script",
        "style",
        "noscript",
        "footer",
        "header",
        "nav",
        "form",
        "svg"
    ]):

        tag.decompose()

    stories = []

    seen_urls = set()
    seen_titles = set()

    # --------------------------------------------------------
    # PRIMARY METHOD:
    # Look for real links to individual stories.
    # --------------------------------------------------------

    for anchor in soup.find_all("a", href=True):

        title = normalize_text(
            anchor.get_text(" ", strip=True)
        )

        href = normalize_url(
            anchor.get("href", "")
        )

        if not likely_story_link(
            title,
            href,
            source["url"]
        ):
            continue

        absolute_url = urljoin(
            source["url"],
            href
        )

        normalized_candidate_url = (
            absolute_url.rstrip("/")
        )

        normalized_candidate_title = (
            normalize_title(title)
        )

        if normalized_candidate_url in seen_urls:
            continue

        if normalized_candidate_title in seen_titles:
            continue

        container = find_story_container(anchor)

        summary = extract_summary(
            container,
            title
        )

        # If the container gives no summary, inspect nearby text
        if not summary:

            nearby = normalize_text(
                container.get_text(" ", strip=True)
                if container
                else ""
            )

            if nearby.lower() != title.lower():

                nearby = nearby.replace(
                    title,
                    ""
                ).strip()

                if len(nearby) >= 40:
                    summary = nearby[:1000]

        combined = f"{title} {summary}"

        detected_county = detect_county(
            combined
        )

        # Prefer the source county when the article is
        # clearly from that county's official website.
        if not detected_county:
            detected_county = county

        category = detect_category(
            combined
        )

        political = political_score(
            combined
        )

        accountability = accountability_score(
            combined
        )

        story = {
            "title": title,
            "summary": summary,
            "url": absolute_url,
            "source": source["name"],
            "county": detected_county,
            "category": category,
            "political_score": political,
            "accountability_score": accountability
        }

        story["score"] = score_story(story)

        stories.append(story)

        seen_urls.add(
            normalized_candidate_url
        )

        seen_titles.add(
            normalized_candidate_title
        )

    # --------------------------------------------------------
    # SECONDARY METHOD:
    # Some county websites use article blocks where the
    # heading itself contains the link.
    # --------------------------------------------------------

    if not stories:

        for heading in soup.find_all(
            ["h2", "h3", "h4", "h5"]
        ):

            title = normalize_text(
                heading.get_text(" ", strip=True)
            )

            if not title_is_reasonable(title):
                continue

            anchor = heading.find("a", href=True)

            if anchor is None:
                anchor = heading.find_parent(
                    "a",
                    href=True
                )

            if anchor is None:
                continue

            href = normalize_url(
                anchor.get("href", "")
            )

            if url_is_bad(
                href,
                source["url"]
            ):
                continue

            absolute_url = urljoin(
                source["url"],
                href
            )

            if absolute_url.rstrip("/") in seen_urls:
                continue

            container = find_story_container(
                anchor
            )

            summary = extract_summary(
                container,
                title
            )

            combined = f"{title} {summary}"

            detected_county = (
                detect_county(combined)
                or county
            )

            category = detect_category(
                combined
            )

            political = political_score(
                combined
            )

            accountability = accountability_score(
                combined
            )

            story = {
                "title": title,
                "summary": summary,
                "url": absolute_url,
                "source": source["name"],
                "county": detected_county,
                "category": category,
                "political_score": political,
                "accountability_score": accountability
            }

            story["score"] = score_story(
                story
            )

            stories.append(story)

            seen_urls.add(
                absolute_url.rstrip("/")
            )

    return stories


# ============================================================
# ENRICH STORIES
# ============================================================

def enrich_stories(stories):

    enriched = []

    for story in stories:

        title = normalize_text(
            story.get("title", "")
        )

        if is_generic_title(title):
            continue

        if is_weak_title(title):
            continue

        text = (
            f"{title} "
            f"{story.get('summary', '')}"
        )

        story["county"] = (
            detect_county(text)
            or story.get("county")
        )

        story["category"] = detect_category(
            text
        )

        story["political_score"] = (
            political_score(text)
        )

        story["accountability_score"] = (
            accountability_score(text)
        )

        story["score"] = score_story(
            story
        )

        enriched.append(story)

    return enriched


# ============================================================
# RANK STORIES
# ============================================================

def rank_stories(stories):

    return sorted(
        stories,
        key=lambda story: (
            story.get("score", 0),
            story.get("accountability_score", 0),
            story.get("political_score", 0),
            word_count(
                story.get("summary", "")
            )
        ),
        reverse=True
    )


# ============================================================
# SELECT STORY
# ============================================================

def select_story(stories):

    ranked = rank_stories(
        stories
    )

    for story in ranked:

        title = normalize_text(
            story.get("title", "")
        )

        if is_generic_title(title):
            continue

        if is_weak_title(title):
            continue

        if not story.get("url"):
            continue

        return story

    return None


# ============================================================
# SAVE STORY
# ============================================================

def save_story(story):

    os.makedirs(
        os.path.dirname(STORY_FILE),
        exist_ok=True
    )

    with open(
        STORY_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            story,
            file,
            indent=2,
            ensure_ascii=False
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 60)
    print("RIFT VALLEY WATCH V1.2")
    print("OFFICIAL-SOURCE NEWS ENGINE")
    print("=" * 60)
    print()

    # --------------------------------------------------------
    # LOAD SETTINGS
    # --------------------------------------------------------

    try:

        with open(
            CONFIG_FILE,
            "r",
            encoding="utf-8"
        ) as file:

            settings = json.load(file)

    except Exception as exc:

        print(
            f"[ERROR] Could not load settings: {exc}"
        )

        return

    max_articles = int(
        settings.get(
            "max_articles",
            50
        )
    )

    # --------------------------------------------------------
    # STEP 1
    # --------------------------------------------------------

    print("[1/5] Loading official county sources...")

    all_stories = []

    for county, source in OFFICIAL_SOURCES.items():

        html = fetch_source(
            county,
            source
        )

        if not html:
            continue

        stories = extract_stories(
            html,
            county,
            source
        )

        print(
            f"      Stories found: {len(stories)}"
        )

        all_stories.extend(
            stories
        )

    print()
    print(
        f"      Total stories found: "
        f"{len(all_stories)}"
    )

    # --------------------------------------------------------
    # STEP 2
    # --------------------------------------------------------

    print()
    print("[2/5] Limiting story pool...")

    # Remove duplicate URLs first
    unique_stories = []
    seen = set()

    for story in all_stories:

        url = story.get("url", "").rstrip("/")

        if not url:
            continue

        if url in seen:
            continue

        seen.add(url)
        unique_stories.append(story)

    # Keep a reasonable working pool
    stories = unique_stories[:max_articles]

    print(
        f"      Stories considered: "
        f"{len(stories)}"
    )

    # --------------------------------------------------------
    # STEP 3
    # --------------------------------------------------------

    print()
    print(
        "[3/5] Detecting counties and categories..."
    )

    stories = enrich_stories(
        stories
    )

    print(
        f"      Stories enriched: "
        f"{len(stories)}"
    )

    # --------------------------------------------------------
    # STEP 4
    # --------------------------------------------------------

    print()
    print("[4/5] Ranking stories...")

    selected = select_story(
        stories
    )

    # --------------------------------------------------------
    # STEP 5
    # --------------------------------------------------------

    if not selected:

        print()
        print(
            "[ERROR] No valid Rift Valley story found."
        )
        print(
            "        The engine rejected page headings "
            "and non-story links."
        )

        return

    print()
    print(
        "[5/5] Strongest story selected"
    )

    print("-" * 60)
    print(
        f"TITLE        : "
        f"{selected['title']}"
    )
    print(
        f"COUNTY       : "
        f"{selected['county']}"
    )
    print(
        f"CATEGORY     : "
        f"{selected['category']}"
    )
    print(
        f"SOURCE       : "
        f"{selected['source']}"
    )
    print(
        f"SCORE        : "
        f"{selected['score']}"
    )
    print(
        f"POLITICAL    : "
        f"{selected['political_score']}"
    )
    print(
        f"ACCOUNTABILITY: "
        f"{selected['accountability_score']}"
    )
    print(
        f"URL          : "
        f"{selected['url']}"
    )
    print("-" * 60)

    save_story(
        selected
    )

    print()
    print(
        f"[SAVED] {STORY_FILE}"
    )
    print()


if __name__ == "__main__":
    main()
