# ============================================================
# RIFT VALLEY WATCH
# OFFICIAL-SOURCE NEWS ENGINE — V1.1
#
# OFFICIAL COUNTY SOURCES
#          ↓
# STORY EXTRACTION
#          ↓
# GENERIC HEADING FILTER
#          ↓
# COUNTY DETECTION
#          ↓
# CATEGORY DETECTION
#          ↓
# POLITICS / ACCOUNTABILITY SCORING
#          ↓
# STORY QUALITY SCORING
#          ↓
# STRONGEST STORY
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
# PRIMARY SOURCES ONLY
#
# No The Star
# No Standard
# No Citizen Digital
#
# ============================================================

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin

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
# COUNTY COVERAGE
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
# POLITICAL TERMS
# ============================================================

POLITICAL_TERMS = [
    "governor",
    "deputy governor",
    "senator",
    "mp",
    "member of parliament",
    "mca",
    "member of county assembly",
    "county assembly",
    "assembly",
    "politician",
    "political",
    "party",
    "election",
    "elections",
    "campaign",
    "government",
    "cabinet",
    "leader",
    "leaders",
    "minister",
    "cabinet secretary",
]


# ============================================================
# ACCOUNTABILITY TERMS
# ============================================================

ACCOUNTABILITY_TERMS = [
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
    "contract",
    "contractor",
    "project",
    "project monitoring",
    "investigation",
    "investigated",
    "probe",
    "court",
    "petition",
    "complaint",
    "oversight",
    "public participation",
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
]


# ============================================================
# HIGH PRIORITY TERMS
# ============================================================

HIGH_PRIORITY_TERMS = [
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
    "police",
    "court",
    "governor",
    "senator",
    "mp",
    "mca",
    "audit",
    "auditor",
    "investigation",
    "probe",
    "irregularities",
    "mismanagement",
    "corruption",
    "budget",
    "procurement",
    "tender",
]


# ============================================================
# MEDIUM PRIORITY TERMS
# ============================================================

MEDIUM_PRIORITY_TERMS = [
    "county",
    "assembly",
    "development",
    "hospital",
    "health",
    "school",
    "university",
    "road",
    "highway",
    "bridge",
    "agriculture",
    "farmers",
    "tea",
    "coffee",
    "business",
    "investment",
    "jobs",
    "employment",
    "market",
    "prices",
    "water",
    "electricity",
    "tourism",
    "livestock",
]


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
    ],

    "POLITICS": [
        "governor",
        "senator",
        "mp",
        "mca",
        "politician",
        "political",
        "election",
        "elections",
        "party",
        "campaign",
        "president",
        "deputy president",
        "cabinet",
        "government",
    ],

    "ACCOUNTABILITY": [
        "audit",
        "auditor",
        "audit report",
        "accountability",
        "irregularities",
        "mismanagement",
        "misuse",
        "funds",
        "budget",
        "procurement",
        "tender",
        "contract",
        "investigation",
        "probe",
        "court",
        "petition",
        "oversight",
        "performance",
        "promise",
        "pledge",
        "delay",
        "delayed",
        "unfinished",
        "abandoned",
    ],

    "DEVELOPMENT": [
        "road",
        "highway",
        "bridge",
        "project",
        "construction",
        "infrastructure",
        "water",
        "electricity",
        "housing",
    ],

    "SECURITY": [
        "police",
        "arrested",
        "crime",
        "attack",
        "robbery",
        "shooting",
        "court",
        "suspect",
    ],

    "AGRICULTURE": [
        "farmer",
        "farmers",
        "agriculture",
        "tea",
        "coffee",
        "maize",
        "dairy",
        "livestock",
        "crop",
        "harvest",
        "seedlings",
        "fertilizer",
    ],

    "HEALTH": [
        "hospital",
        "health",
        "doctor",
        "patient",
        "disease",
        "clinic",
        "medical",
        "nurse",
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
    ],

    "BUSINESS": [
        "business",
        "investment",
        "company",
        "jobs",
        "employment",
        "market",
        "prices",
        "economy",
        "trade",
        "coffee",
        "tourism",
    ],

    "COMMUNITY": [
        "community",
        "residents",
        "families",
        "youth",
        "women",
        "leaders",
        "initiative",
    ],

    "TOURISM": [
        "tourism",
        "tourist",
        "maasai mara",
        "wildlife",
        "park",
        "hotel",
        "travel",
        "conservation",
    ],
}


# ============================================================
# GENERIC / NON-STORY TITLES
# ============================================================

GENERIC_TITLES = {
    "recent news",
    "recent news & events",
    "recent news and events",
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
}


# ============================================================
# CONFIG
# ============================================================

def load_config():
    """Load application configuration."""

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

        return defaults

    except Exception:
        return defaults


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_text(text):
    """Clean HTML and whitespace from text."""

    if not text:
        return ""

    text = BeautifulSoup(
        str(text),
        "html.parser",
    ).get_text(" ")

    text = re.sub(
        r"\s+",
        " ",
        text,
    )

    return text.strip()


# ============================================================
# NORMALIZE URL
# ============================================================

def normalize_url(base_url, href):
    """Convert relative URLs into absolute URLs."""

    if not href:
        return ""

    href = href.strip()

    if href.startswith("#"):
        return ""

    if href.startswith("mailto:"):
        return ""

    if href.startswith("javascript:"):
        return ""

    return urljoin(
        base_url,
        href,
    )


# ============================================================
# NORMALIZE TITLE
# ============================================================

def normalize_title(title):
    """Normalize a title for comparison."""

    title = clean_text(title)

    title = re.sub(
        r"\s+",
        " ",
        title.lower(),
    )

    title = title.strip(
        " -|:•·"
    )

    return title


# ============================================================
# GENERIC TITLE CHECK
# ============================================================

def is_generic_title(title):
    """Return True when a title is a website heading."""

    normalized = normalize_title(
        title
    )

    if not normalized:
        return True

    if normalized in GENERIC_TITLES:
        return True

    # --------------------------------------------------------
    # Common heading patterns
    # --------------------------------------------------------

    generic_patterns = [
        r"^recent news",
        r"^latest news",
        r"^latest updates",
        r"^recent updates",
        r"^news and events$",
        r"^news & events$",
        r"^news updates$",
        r"^featured news$",
        r"^latest stories$",
        r"^recent stories$",
    ]

    for pattern in generic_patterns:

        if re.search(
            pattern,
            normalized,
        ):
            return True

    return False


# ============================================================
# COUNTY DETECTION
# ============================================================

def detect_county(title, summary):
    """Identify the strongest matching covered county."""

    text = (
        f"{title} {summary}"
        .lower()
    )

    matches = {}

    for county, keywords in COUNTY_KEYWORDS.items():

        count = 0

        for keyword in keywords:

            if keyword.lower() in text:
                count += 1

        if count:
            matches[county] = count

    if not matches:
        return None

    return max(
        matches,
        key=matches.get,
    )


# ============================================================
# CATEGORY DETECTION
# ============================================================

def detect_category(title, summary):
    """Identify the strongest story category."""

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

    best_category = max(
        scores,
        key=scores.get,
    )

    if scores[best_category] == 0:
        return "COMMUNITY"

    return best_category


# ============================================================
# POLITICAL SCORE
# ============================================================

def political_score(title, summary):
    """Score stories involving political leadership."""

    text = (
        f"{title} {summary}"
        .lower()
    )

    score = 0

    for term in POLITICAL_TERMS:

        if term in text:
            score += 4

    return score


# ============================================================
# ACCOUNTABILITY SCORE
# ============================================================

def accountability_score(title, summary):
    """Score stories involving accountability."""

    text = (
        f"{title} {summary}"
        .lower()
    )

    score = 0

    for term in ACCOUNTABILITY_TERMS:

        if term in text:
            score += 5

    return score


# ============================================================
# STORY SCORING
# ============================================================

def score_story(
    title,
    summary,
    county,
):
    """Calculate story importance."""

    text = (
        f"{title} {summary}"
        .lower()
    )

    score = 0

    # --------------------------------------------------------
    # County relevance
    # --------------------------------------------------------

    if county:
        score += 15

    # --------------------------------------------------------
    # High-priority terms
    # --------------------------------------------------------

    for term in HIGH_PRIORITY_TERMS:

        if term in text:
            score += 5

    # --------------------------------------------------------
    # Medium-priority terms
    # --------------------------------------------------------

    for term in MEDIUM_PRIORITY_TERMS:

        if term in text:
            score += 2

    # --------------------------------------------------------
    # Political importance
    # --------------------------------------------------------

    score += political_score(
        title,
        summary,
    )

    # --------------------------------------------------------
    # Accountability importance
    # --------------------------------------------------------

    score += accountability_score(
        title,
        summary,
    )

    # --------------------------------------------------------
    # Strong headline indicators
    # --------------------------------------------------------

    if "breaking" in title.lower():
        score += 10

    if re.search(
        r"\b\d+\b",
        title,
    ):
        score += 2

    if "%" in summary:
        score += 2

    # --------------------------------------------------------
    # Story depth
    # --------------------------------------------------------

    if len(summary) >= 150:
        score += 3

    if len(summary) >= 300:
        score += 3

    if len(summary) >= 500:
        score += 2

    # --------------------------------------------------------
    # Weak formats
    # --------------------------------------------------------

    weak_terms = [
        "opinion",
        "podcast",
        "newsletter",
        "weekly roundup",
        "daily roundup",
        "photo gallery",
        "gallery",
        "advertisement",
        "vacancy",
        "job vacancy",
    ]

    for term in weak_terms:

        if term in title.lower():
            score -= 5

    # --------------------------------------------------------
    # Weak headline
    # --------------------------------------------------------

    if len(title.split()) < 4:
        score -= 5

    # --------------------------------------------------------
    # Weak summary
    # --------------------------------------------------------

    if len(summary) < 80:
        score -= 5

    if len(summary) < 30:
        score -= 10

    return score


# ============================================================
# FETCH OFFICIAL PAGE
# ============================================================

def fetch_source(source):
    """Fetch an official county website."""

    try:

        headers = {
            "User-Agent": (
                "Mozilla/5.0 "
                "(Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 "
                "Chrome/120 Safari/537.36"
            )
        }

        response = requests.get(
            source["url"],
            headers=headers,
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


# ============================================================
# EXTRACT STORIES FROM HTML
# ============================================================

def extract_stories(
    html,
    source,
):
    """Extract likely news stories from an official page."""

    if not html:
        return []

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    stories = []

    # --------------------------------------------------------
    # Remove obvious non-content areas
    # --------------------------------------------------------

    for element in soup.find_all(
        [
            "nav",
            "footer",
            "header",
            "script",
            "style",
            "noscript",
        ]
    ):

        element.decompose()

    # --------------------------------------------------------
    # Look for article/post structures first
    # --------------------------------------------------------

    containers = soup.find_all(
        [
            "article",
            "li",
            "div",
        ]
    )

    for container in containers:

        heading = container.find(
            [
                "h1",
                "h2",
                "h3",
                "h4",
                "h5",
            ]
        )

        if not heading:
            continue

        title = clean_text(
            heading.get_text(" ")
        )

        if not title:
            continue

        # ----------------------------------------------------
        # Generic website heading filter
        # ----------------------------------------------------

        if is_generic_title(title):
            continue

        # ----------------------------------------------------
        # Minimum title quality
        # ----------------------------------------------------

        if len(title) < 20:
            continue

        if len(title.split()) < 4:
            continue

        # ----------------------------------------------------
        # Ignore obvious interface text
        # ----------------------------------------------------

        ignored_terms = [
            "home",
            "contact us",
            "about us",
            "read more",
            "learn more",
            "login",
            "subscribe",
            "search",
            "menu",
            "services",
            "privacy policy",
            "terms and conditions",
            "quick links",
        ]

        normalized_title = normalize_title(
            title
        )

        if normalized_title in ignored_terms:
            continue

        # ----------------------------------------------------
        # Find link
        # ----------------------------------------------------

        link = heading.find("a")

        if not link:
            link = container.find("a")

        href = ""

        if link:

            href = normalize_url(
                source["url"],
                link.get(
                    "href",
                    "",
                ),
            )

        if not href:
            href = source["url"]

        # ----------------------------------------------------
        # Summary
        # ----------------------------------------------------

        paragraphs = container.find_all(
            "p"
        )

        summary_parts = []

        for paragraph in paragraphs:

            text = clean_text(
                paragraph.get_text(" ")
            )

            if not text:
                continue

            # Avoid tiny UI fragments
            if len(text) < 25:
                continue

            summary_parts.append(
                text
            )

        summary = " ".join(
            summary_parts
        )

        # ----------------------------------------------------
        # Avoid containers with no meaningful summary
        # ----------------------------------------------------

        if len(summary) < 20:

            # Try nearby text from the container
            container_text = clean_text(
                container.get_text(" ")
            )

            if container_text:
                summary = container_text

        # ----------------------------------------------------
        # Remove title duplication from summary
        # ----------------------------------------------------

        if summary:

            summary_normalized = normalize_title(
                summary
            )

            title_normalized = normalize_title(
                title
            )

            if summary_normalized == title_normalized:
                summary = ""

        # ----------------------------------------------------
        # Build story
        # ----------------------------------------------------

        story = {
            "title": title,
            "summary": summary,
            "url": href,
            "source": source["name"],
            "county": source["county"],
        }

        stories.append(
            story
        )

    # --------------------------------------------------------
    # Remove duplicate titles
    # --------------------------------------------------------

    unique = []

    seen = set()

    for story in stories:

        key = normalize_title(
            story["title"]
        )

        if not key:
            continue

        if key in seen:
            continue

        seen.add(key)

        unique.append(
            story
        )

    return unique


# ============================================================
# ENRICH STORIES
# ============================================================

def enrich_stories(stories):
    """Detect category and calculate score."""

    enriched = []

    for story in stories:

        title = story.get(
            "title",
            "",
        )

        summary = story.get(
            "summary",
            "",
        )

        county = story.get(
            "county"
        )

        # ----------------------------------------------------
        # Final generic-title protection
        # ----------------------------------------------------

        if is_generic_title(title):
            continue

        detected_county = detect_county(
            title,
            summary,
        )

        # ----------------------------------------------------
        # Keep source county if article text doesn't mention
        # the county directly.
        # ----------------------------------------------------

        if detected_county:
            county = detected_county

        category = detect_category(
            title,
            summary,
        )

        score = score_story(
            title,
            summary,
            county,
        )

        story["county"] = county

        story["category"] = category

        story["score"] = score

        story["political_score"] = (
            political_score(
                title,
                summary,
            )
        )

        story["accountability_score"] = (
            accountability_score(
                title,
                summary,
            )
        )

        enriched.append(
            story
        )

    return enriched


# ============================================================
# REMOVE DUPLICATES
# ============================================================

def remove_duplicates(stories):
    """Remove duplicate headlines."""

    unique = []

    seen = set()

    for story in stories:

        normalized = normalize_title(
            story["title"]
        )

        if not normalized:
            continue

        if normalized in seen:
            continue

        seen.add(
            normalized
        )

        unique.append(
            story
        )

    return unique


# ============================================================
# SELECT STRONGEST STORY
# ============================================================

def select_story(stories):
    """Select the strongest regional story."""

    if not stories:
        return None

    stories = remove_duplicates(
        stories
    )

    # --------------------------------------------------------
    # Final safety filter
    # --------------------------------------------------------

    stories = [
        story
        for story in stories
        if not is_generic_title(
            story.get(
                "title",
                "",
            )
        )
    ]

    if not stories:
        return None

    # --------------------------------------------------------
    # Ranking
    # --------------------------------------------------------

    stories.sort(
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

    selected = stories[0]

    selected["selected_at"] = (
        datetime.now(
            timezone.utc
        ).isoformat()
    )

    return selected


# ============================================================
# SAVE STORY
# ============================================================

def save_story(story):
    """Save selected story."""

    if not story:
        return

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
# MAIN ENGINE
# ============================================================

def run_news_engine():
    """Run the complete official-source engine."""

    config = load_config()

    max_articles = int(
        config.get(
            "max_articles",
            100,
        )
    )

    print("=" * 60)

    print(
        "RIFT VALLEY WATCH — "
        "OFFICIAL-SOURCE NEWS ENGINE V1.1"
    )

    print("=" * 60)

    print(
        "\nPrimary sources only."
    )

    print(
        "Political and accountability stories are included."
    )

    # --------------------------------------------------------
    # STEP 1
    # --------------------------------------------------------

    print(
        "\n[1/5] Loading official county sources..."
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

    print(
        f"\n      Total stories found: "
        f"{len(all_stories)}"
    )

    # --------------------------------------------------------
    # STEP 2
    # --------------------------------------------------------

    print(
        "\n[2/5] Limiting story pool..."
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

    print(
        "\n[3/5] Detecting counties and categories..."
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

    print(
        "\n[4/5] Ranking stories..."
    )

    story = select_story(
        enriched
    )

    if not story:

        print(
            "\n[ERROR] "
            "No suitable regional story found."
        )

        return None

    # --------------------------------------------------------
    # STEP 5
    # --------------------------------------------------------

    print(
        "\n[5/5] Strongest story selected"
    )

    print(
        "-" * 60
    )

    print(
        f"TITLE        : "
        f"{story['title']}"
    )

    print(
        f"COUNTY       : "
        f"{story['county']}"
    )

    print(
        f"CATEGORY     : "
        f"{story['category']}"
    )

    print(
        f"SOURCE       : "
        f"{story['source']}"
    )

    print(
        f"SCORE        : "
        f"{story['score']}"
    )

    print(
        f"POLITICAL    : "
        f"{story['political_score']}"
    )

    print(
        f"ACCOUNTABILITY: "
        f"{story['accountability_score']}"
    )

    print(
        f"URL          : "
        f"{story['url']}"
    )

    print(
        "-" * 60
    )

    save_story(
        story
    )

    print(
        f"\n[SAVED] "
        f"{STORY_FILE}"
    )

    return story


# ============================================================
# DIRECT EXECUTION
# ============================================================

if __name__ == "__main__":
    run_news_engine()
