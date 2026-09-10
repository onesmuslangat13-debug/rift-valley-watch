# ============================================================
# RIFT VALLEY WATCH V1.2
# OFFICIAL-SOURCE NEWS ENGINE
#
# PRIMARY SOURCES ONLY
#
# COVERAGE:
# Bomet
# Kericho
# Nakuru
# Nandi
# Uasin Gishu
# Elgeyo-Marakwet
# West Pokot
# Narok
#
# PIPELINE:
# OFFICIAL SOURCES
#       ↓
# REAL STORY LINK EXTRACTION
#       ↓
# COUNTY DETECTION
#       ↓
# CATEGORY DETECTION
#       ↓
# POLITICAL SCORING
#       ↓
# ACCOUNTABILITY SCORING
#       ↓
# STORY RANKING
#       ↓
# ONE STRONG STORY
#       ↓
# data/story.json
#
# IMPORTANT:
# This version does NOT treat page headings such as
# "RECENT NEWS & EVENTS" as news stories.
# ============================================================

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


# ============================================================
# PATHS
# ============================================================

ROOT = Path(__file__).resolve().parents[1]

CONFIG_DIR = ROOT / "config"
DATA_DIR = ROOT / "data"

CONFIG_FILE = CONFIG_DIR / "settings.json"
STORY_FILE = DATA_DIR / "story.json"

DATA_DIR.mkdir(parents=True, exist_ok=True)


# ============================================================
# OFFICIAL SOURCES
# ============================================================

OFFICIAL_SOURCES = [
    {
        "name": "Bomet County Government",
        "county": "Bomet",
        "url": "https://bomet.go.ke/news/",
    },
    {
        "name": "Kericho County Government",
        "county": "Kericho",
        "url": "https://www.kericho.go.ke/",
    },
    {
        "name": "Nakuru County Government",
        "county": "Nakuru",
        "url": "https://www.nakuru.go.ke/",
    },
    {
        "name": "Nandi County Government",
        "county": "Nandi",
        "url": "https://nandi.go.ke/news/",
    },
    {
        "name": "Uasin Gishu County Government",
        "county": "Uasin Gishu",
        "url": "https://uasingishu.go.ke/",
    },
    {
        "name": "Elgeyo-Marakwet County Government",
        "county": "Elgeyo-Marakwet",
        "url": "https://elgeyomarakwet.go.ke/news/",
    },
    {
        "name": "West Pokot County Government",
        "county": "West Pokot",
        "url": "https://www.westpokot.go.ke/",
    },
    {
        "name": "Narok County Government",
        "county": "Narok",
        "url": "https://www.narok.go.ke/",
    },
]


# ============================================================
# COUNTY KEYWORDS
# ============================================================

COUNTY_KEYWORDS = {
    "Bomet": [
        "bomet",
        "sotik",
        "konoin",
        "chepalungu",
        "longisa",
        "mulot",
    ],
    "Kericho": [
        "kericho",
        "ainamoi",
        "belgut",
        "kipkelion",
        "litein",
        "londiani",
        "bureti",
        "sigowet",
    ],
    "Nakuru": [
        "nakuru",
        "naivasha",
        "gilgil",
        "molo",
        "njoro",
        "rongai",
        "kuresoi",
    ],
    "Nandi": [
        "nandi",
        "kapsabet",
        "mosop",
        "aldai",
        "emgwen",
        "tinderet",
        "chesumei",
    ],
    "Uasin Gishu": [
        "uasin gishu",
        "eldoret",
        "turbo",
        "kesses",
        "soy",
        "moiben",
        "kapseret",
    ],
    "Elgeyo-Marakwet": [
        "elgeyo-marakwet",
        "elgeyo marakwet",
        "iten",
        "marakwet",
        "keiyo",
        "keiyo south",
        "keiyo north",
        "kapcherop",
        "tambach",
    ],
    "West Pokot": [
        "west pokot",
        "kapenguria",
        "kacheliba",
        "sigor",
        "pokot",
        "chepareria",
        "turkwel",
    ],
    "Narok": [
        "narok",
        "kilgoris",
        "trans mara",
        "suswa",
        "maasai mara",
        "ololulunga",
        "mau",
    ],
}


# ============================================================
# CATEGORIES
# ============================================================

CATEGORY_TERMS = {
    "BREAKING NEWS": [
        "breaking",
        "killed",
        "dead",
        "death",
        "missing",
        "arrested",
        "accident",
        "crash",
        "fire",
        "flood",
        "landslide",
        "attack",
        "shooting",
        "rescue",
        "emergency",
    ],

    "POLITICS": [
        "governor",
        "deputy governor",
        "senator",
        "senators",
        "mp",
        "mps",
        "member of parliament",
        "mca",
        "mcas",
        "member of county assembly",
        "county assembly",
        "assembly",
        "politician",
        "political",
        "party",
        "election",
        "elections",
        "campaign",
        "president",
        "government",
        "cabinet",
        "leader",
        "leaders",
    ],

    "ACCOUNTABILITY": [
        "audit",
        "auditor",
        "auditor-general",
        "audit report",
        "accountability",
        "irregular",
        "irregularities",
        "mismanagement",
        "misuse",
        "funds",
        "budget",
        "budget implementation",
        "expenditure",
        "procurement",
        "tender",
        "tenders",
        "contract",
        "contractor",
        "investigation",
        "investigated",
        "probe",
        "court",
        "petition",
        "complaint",
        "oversight",
        "performance",
        "promise",
        "pledge",
        "commitment",
        "delivery",
        "delay",
        "delayed",
        "unfinished",
        "abandoned",
        "failed",
    ],

    "DEVELOPMENT": [
        "road",
        "roads",
        "highway",
        "bridge",
        "bridges",
        "project",
        "projects",
        "construction",
        "infrastructure",
        "water",
        "electricity",
        "housing",
        "stadium",
        "market",
        "markets",
    ],

    "SECURITY": [
        "police",
        "security",
        "arrested",
        "crime",
        "attack",
        "robbery",
        "shooting",
        "suspect",
        "bandit",
        "bandits",
        "investigation",
        "dci",
    ],

    "AGRICULTURE": [
        "farmer",
        "farmers",
        "agriculture",
        "farming",
        "tea",
        "coffee",
        "maize",
        "dairy",
        "livestock",
        "crop",
        "crops",
        "harvest",
        "seedlings",
        "fertilizer",
        "irrigation",
    ],

    "HEALTH": [
        "hospital",
        "hospitals",
        "health",
        "doctor",
        "doctors",
        "patient",
        "patients",
        "disease",
        "clinic",
        "medical",
        "nurse",
        "nurses",
        "healthcare",
        "vaccination",
        "immunization",
    ],

    "EDUCATION": [
        "school",
        "schools",
        "student",
        "students",
        "teacher",
        "teachers",
        "university",
        "education",
        "college",
        "bursary",
        "scholarship",
        "training",
    ],

    "BUSINESS": [
        "business",
        "businesses",
        "investment",
        "investor",
        "investors",
        "company",
        "companies",
        "jobs",
        "employment",
        "market",
        "prices",
        "economy",
        "trade",
        "industry",
        "industrial",
    ],

    "COMMUNITY": [
        "community",
        "residents",
        "families",
        "youth",
        "women",
        "initiative",
        "empowerment",
        "donation",
        "social",
    ],

    "TOURISM": [
        "tourism",
        "tourist",
        "tourists",
        "maasai mara",
        "wildlife",
        "park",
        "parks",
        "hotel",
        "hotels",
        "travel",
        "conservation",
    ],
}


# ============================================================
# GENERIC TITLES
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
    "press release",
    "press releases",
    "news events",
}


# ============================================================
# BAD LINK / PAGE PATTERNS
# ============================================================

BAD_PATH_PATTERNS = [
    "/templates/",
    "/category/",
    "/categories/",
    "/tag/",
    "/tags/",
    "/author/",
    "/search",
    "/contact",
    "/about",
    "/login",
    "/register",
    "/gallery",
    "/galleries",
    "/events",
]


# ============================================================
# REQUEST SETTINGS
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 "
        "(KHTML, like Gecko) "
        "Chrome/131.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
}


# ============================================================
# LOAD CONFIG
# ============================================================

def load_config():
    defaults = {
        "page_name": "Rift Valley Watch",
        "region": "Rift Valley, Kenya",
        "language": "en",
        "max_articles": 100,
        "max_script_words": 180,
    }

    if not CONFIG_FILE.exists():
        return defaults

    try:
        with open(
            CONFIG_FILE,
            "r",
            encoding="utf-8",
        ) as file:
            config = json.load(file)

        defaults.update(config)

    except Exception:
        pass

    return defaults


# ============================================================
# TEXT NORMALIZATION
# ============================================================

def clean_text(text):
    if not text:
        return ""

    text = BeautifulSoup(
        str(text),
        "html.parser",
    ).get_text(" ")

    text = text.replace("\xa0", " ")

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


def normalize_title(title):
    title = clean_text(title).lower()

    title = title.replace(
        "–",
        "-",
    )

    title = title.replace(
        "—",
        "-",
    )

    title = re.sub(
        r"\s+",
        " ",
        title,
    )

    return title.strip()


def is_generic_title(title):
    normalized = normalize_title(
        title
    )

    if not normalized:
        return True

    if normalized in GENERIC_TITLES:
        return True

    if normalized.startswith(
        "recent news"
    ):
        return True

    if normalized.startswith(
        "latest news"
    ):
        return True

    if normalized.startswith(
        "news & events"
    ):
        return True

    if normalized.startswith(
        "news and events"
    ):
        return True

    if normalized.startswith(
        "recent updates"
    ):
        return True

    return False


# ============================================================
# STORY TITLE VALIDATION
# ============================================================

def is_valid_story_title(title):
    title = clean_text(title)

    if not title:
        return False

    if is_generic_title(title):
        return False

    bad_titles = [
        "home",
        "about us",
        "contact us",
        "read more",
        "learn more",
        "login",
        "register",
        "search",
        "menu",
        "services",
        "projects",
        "departments",
    ]

    if title.lower() in bad_titles:
        return False

    # Real headlines should contain enough information.
    if len(title) < 25:
        return False

    if len(title.split()) < 4:
        return False

    return True


# ============================================================
# URL VALIDATION
# ============================================================

def is_bad_url(
    absolute_url,
    source_url,
):
    if not absolute_url:
        return True

    candidate = absolute_url.rstrip(
        "/"
    ).lower()

    source = source_url.rstrip(
        "/"
    ).lower()

    # Same page
    if candidate == source:
        return True

    parsed = urlparse(
        absolute_url
    )

    path = parsed.path.lower()

    # Known navigation/section pages
    for pattern in BAD_PATH_PATTERNS:

        if pattern in path:
            return True

    # Specific Kericho page that caused the problem
    if "news_and_events" in path:
        return True

    # Generic news page
    if path.rstrip("/").endswith(
        "/news"
    ):
        return True

    # Generic events page
    if path.rstrip("/").endswith(
        "/events"
    ):
        return True

    return False


# ============================================================
# FIND LINKED STORY TITLE
# ============================================================

def get_story_title(anchor):
    """
    Get the strongest title available from an anchor.
    """

    text = clean_text(
        anchor.get_text(
            " ",
            strip=True,
        )
    )

    if is_valid_story_title(text):
        return text

    # Sometimes the anchor has an image with alt text.
    image = anchor.find(
        "img"
    )

    if image:

        alt = clean_text(
            image.get(
                "alt",
                "",
            )
        )

        if is_valid_story_title(alt):
            return alt

    return ""


# ============================================================
# FIND STORY CONTAINER
# ============================================================

def find_story_container(anchor):
    """
    Find a nearby article/card without consuming the
    entire webpage.
    """

    article = anchor.find_parent(
        "article"
    )

    if article is not None:
        return article

    item = anchor.find_parent(
        "li"
    )

    if item is not None:

        text = clean_text(
            item.get_text(
                " ",
                strip=True,
            )
        )

        if len(text) <= 3000:
            return item

    current = anchor.parent

    for _ in range(5):

        if current is None:
            break

        if current.name == "div":

            text = clean_text(
                current.get_text(
                    " ",
                    strip=True,
                )
            )

            if 60 <= len(text) <= 3000:
                return current

        current = current.parent

    return anchor.parent


# ============================================================
# EXTRACT SUMMARY
# ============================================================

def extract_summary(
    container,
    title,
):
    if container is None:
        return ""

    paragraphs = []

    for paragraph in container.find_all(
        "p"
    ):

        text = clean_text(
            paragraph.get_text(
                " ",
                strip=True,
            )
        )

        if not text:
            continue

        if text.lower() == title.lower():
            continue

        if len(text) < 30:
            continue

        paragraphs.append(
            text
        )

    # Remove duplicates
    unique = []

    for paragraph in paragraphs:

        if paragraph not in unique:
            unique.append(
                paragraph
            )

    summary = " ".join(
        unique
    )

    if len(summary) > 1200:
        summary = (
            summary[:1200]
            .rsplit(" ", 1)[0]
            + "..."
        )

    return summary


# ============================================================
# EXTRACT LINKED STORIES
# ============================================================

def extract_linked_stories(
    soup,
    source,
):
    """
    Main extraction method.

    IMPORTANT:
    We start from <a href=""> elements, not arbitrary
    headings/divs. This prevents website section headings
    from becoming stories.
    """

    stories = []

    seen_urls = set()
    seen_titles = set()

    for anchor in soup.find_all(
        "a",
        href=True,
    ):

        title = get_story_title(
            anchor
        )

        if not title:
            continue

        href = anchor.get(
            "href",
            "",
        ).strip()

        absolute_url = urljoin(
            source["url"],
            href,
        )

        if is_bad_url(
            absolute_url,
            source["url"],
        ):
            continue

        url_key = absolute_url.rstrip(
            "/"
        ).lower()

        title_key = normalize_title(
            title
        )

        if url_key in seen_urls:
            continue

        if title_key in seen_titles:
            continue

        container = find_story_container(
            anchor
        )

        summary = extract_summary(
            container,
            title,
        )

        story = {
            "title": title,
            "summary": summary,
            "url": absolute_url,
            "source": source["name"],
            "county": source["county"],
        }

        stories.append(
            story
        )

        seen_urls.add(
            url_key
        )

        seen_titles.add(
            title_key
        )

    return stories


# ============================================================
# EXTRACT STORIES
# ============================================================

def extract_stories(
    html,
    source,
):
    if not html:
        return []

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    # Remove page elements that should never become stories.
    for tag in soup.find_all(
        [
            "script",
            "style",
            "noscript",
            "footer",
            "nav",
            "form",
            "svg",
        ]
    ):
        tag.decompose()

    stories = extract_linked_stories(
        soup,
        source,
    )

    return stories


# ============================================================
# COUNTY DETECTION
# ============================================================

def detect_county(
    title,
    summary,
    default_county,
):
    text = (
        f"{title} {summary}"
        .lower()
    )

    scores = {}

    for county, keywords in COUNTY_KEYWORDS.items():

        score = 0

        for keyword in keywords:

            if keyword.lower() in text:
                score += 1

        if score:
            scores[county] = score

    if not scores:
        return default_county

    return max(
        scores,
        key=scores.get,
    )


# ============================================================
# CATEGORY DETECTION
# ============================================================

def detect_category(
    title,
    summary,
):
    text = (
        f"{title} {summary}"
        .lower()
    )

    scores = {}

    for category, keywords in CATEGORY_TERMS.items():

        score = 0

        for keyword in keywords:

            if keyword.lower() in text:
                score += 1

        scores[category] = score

    best = max(
        scores,
        key=scores.get,
    )

    if scores[best] == 0:
        return "COMMUNITY"

    return best


# ============================================================
# POLITICAL SCORE
# ============================================================

def political_score(
    title,
    summary,
):
    text = (
        f"{title} {summary}"
        .lower()
    )

    score = 0

    for term in CATEGORY_TERMS["POLITICS"]:

        if term.lower() in text:
            score += 4

    return score


# ============================================================
# ACCOUNTABILITY SCORE
# ============================================================

def accountability_score(
    title,
    summary,
):
    text = (
        f"{title} {summary}"
        .lower()
    )

    score = 0

    for term in CATEGORY_TERMS[
        "ACCOUNTABILITY"
    ]:

        if term.lower() in text:
            score += 5

    return score


# ============================================================
# STORY SCORE
# ============================================================

def score_story(
    title,
    summary,
    county,
):
    text = (
        f"{title} {summary}"
        .lower()
    )

    score = 0

    # County relevance
    if county:
        score += 15

    # Breaking/high-impact terms
    for term in CATEGORY_TERMS[
        "BREAKING NEWS"
    ]:

        if term.lower() in text:
            score += 5

    # Political importance
    score += political_score(
        title,
        summary,
    )

    # Accountability importance
    score += accountability_score(
        title,
        summary,
    )

    # Development/business/etc.
    for category in [
        "DEVELOPMENT",
        "SECURITY",
        "AGRICULTURE",
        "HEALTH",
        "EDUCATION",
        "BUSINESS",
        "TOURISM",
    ]:

        for term in CATEGORY_TERMS[
            category
        ]:

            if term.lower() in text:
                score += 2

    # Strong headline
    if len(title.split()) >= 7:
        score += 5

    # Useful article depth
    if len(summary) >= 150:
        score += 5

    if len(summary) >= 300:
        score += 5

    # Very short summary penalty
    if len(summary) < 50:
        score -= 3

    return score


# ============================================================
# ENRICH STORIES
# ============================================================

def enrich_stories(
    stories,
):
    enriched = []

    for story in stories:

        title = clean_text(
            story.get(
                "title",
                "",
            )
        )

        summary = clean_text(
            story.get(
                "summary",
                "",
            )
        )

        if not is_valid_story_title(
            title
        ):
            continue

        if is_generic_title(
            title
        ):
            continue

        county = detect_county(
            title,
            summary,
            story.get(
                "county"
            ),
        )

        category = detect_category(
            title,
            summary,
        )

        political = political_score(
            title,
            summary,
        )

        accountability = (
            accountability_score(
                title,
                summary,
            )
        )

        score = score_story(
            title,
            summary,
            county,
        )

        story["title"] = title
        story["summary"] = summary
        story["county"] = county
        story["category"] = category
        story["political_score"] = political
        story["accountability_score"] = (
            accountability
        )
        story["score"] = score

        enriched.append(
            story
        )

    return enriched


# ============================================================
# REMOVE DUPLICATES
# ============================================================

def remove_duplicates(
    stories,
):
    unique = []

    seen_titles = set()
    seen_urls = set()

    for story in stories:

        title_key = normalize_title(
            story.get(
                "title",
                "",
            )
        )

        url_key = (
            story.get(
                "url",
                "",
            )
            .rstrip("/")
            .lower()
        )

        if not title_key:
            continue

        if title_key in seen_titles:
            continue

        if url_key in seen_urls:
            continue

        seen_titles.add(
            title_key
        )

        seen_urls.add(
            url_key
        )

        unique.append(
            story
        )

    return unique


# ============================================================
# RANK STORIES
# ============================================================

def rank_stories(
    stories,
):
    stories = remove_duplicates(
        stories
    )

    return sorted(
        stories,
        key=lambda story: (
            story.get(
                "score",
                0,
            ),
            story.get(
                "accountability_score",
                0,
            ),
            story.get(
                "political_score",
                0,
            ),
            len(
                story.get(
                    "summary",
                    "",
                )
            ),
        ),
        reverse=True,
    )


# ============================================================
# SELECT STORY
# ============================================================

def select_story(
    stories,
):
    ranked = rank_stories(
        stories
    )

    for story in ranked:

        title = story.get(
            "title",
            "",
        )

        url = story.get(
            "url",
            "",
        )

        if not is_valid_story_title(
            title
        ):
            continue

        if is_generic_title(
            title
        ):
            continue

        if not url:
            continue

        # Final protection against the known bad page.
        if "news_and_events" in url.lower():
            continue

        return story

    return None


# ============================================================
# SAVE STORY
# ============================================================

def save_story(
    story,
):
    with open(
        STORY_FILE,
        "w",
        encoding="utf-8",
    ) as file:

        json.dump(
            story,
            file,
            indent=2,
            ensure_ascii=False,
        )


# ============================================================
# MAIN
# ============================================================

def main():

    config = load_config()

    max_articles = int(
        config.get(
            "max_articles",
            100,
        )
    )

    print(
        "=" * 60
    )

    print(
        "RIFT VALLEY WATCH V1.2"
    )

    print(
        "OFFICIAL-SOURCE NEWS ENGINE"
    )

    print(
        "=" * 60
    )

    print()

    print(
        "Primary sources only."
    )

    print(
        "Political and accountability stories are included."
    )

    print()

    # --------------------------------------------------------
    # STEP 1
    # --------------------------------------------------------

    print(
        "[1/5] Loading official county sources..."
    )

    all_stories = []

    for source in OFFICIAL_SOURCES:

        print(
            f"      Fetching: "
            f"{source['name']}"
        )

        html = fetch_source(
            source
        )

        if not html:
            continue

        stories = extract_stories(
            html,
            source,
        )

        print(
            f"      Stories found: "
            f"{len(stories)}"
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

    print(
        "[2/5] Limiting story pool..."
    )

    all_stories = remove_duplicates(
        all_stories
    )

    all_stories = all_stories[
        :max_articles
    ]

    print(
        f"      Stories considered: "
        f"{len(all_stories)}"
    )

    # --------------------------------------------------------
    # STEP 3
    # --------------------------------------------------------

    print()

    print(
        "[3/5] Detecting counties and categories..."
    )

    enriched = enrich_stories(
        all_stories
    )

    print(
        f"      Stories enriched: "
        f"{len(enriched)}"
    )

    # --------------------------------------------------------
    # STEP 4
    # --------------------------------------------------------

    print()

    print(
        "[4/5] Ranking stories..."
    )

    selected = select_story(
        enriched
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
            "        Generic website headings and "
            "section pages were rejected."
        )

        return

    print()

    print(
        "[5/5] Strongest story selected"
    )

    print(
        "-" * 60
    )

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

    print(
        "-" * 60
    )

    selected["selected_at"] = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    save_story(
        selected
    )

    print()

    print(
        f"[SAVED] "
        f"{STORY_FILE}"
    )

    print()


# ============================================================
# RUN
# ============================================================

def fetch_source(
    source,
):
    try:

        response = requests.get(
            source["url"],
            headers=HEADERS,
            timeout=25,
        )

        response.raise_for_status()

        return response.text

    except Exception as error:

        print(
            f"[WARNING] Could not fetch "
            f"{source['name']}: {error}"
        )

        return ""


if __name__ == "__main__":
    main()
