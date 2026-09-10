# ============================================================
# RIFT VALLEY WATCH
# NEWS ENGINE — STEP 2E
#
# NEWS SOURCES
#      ↓
# COUNTY DETECTION
#      ↓
# REGIONAL FILTER
#      ↓
# STORY SCORING
#      ↓
# STRONGEST STORY
#
# This file handles news discovery and story selection only.
# ============================================================

import json
import re
from datetime import datetime, timezone
from pathlib import Path

import feedparser
import requests


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
# RIFT VALLEY COVERAGE
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
    ],
    "Nakuru": [
        "nakuru",
        "naivasha",
        "gilgil",
        "molo",
        "njoro",
        "rongai",
    ],
    "Nandi": [
        "nandi",
        "kapsabet",
        "mosop",
        "aldai",
        "emgwen",
        "tinderet",
    ],
    "Uasin Gishu": [
        "uasin gishu",
        "eldoret",
        "turbo",
        "kesses",
        "soy",
        "moiben",
    ],
    "Elgeyo-Marakwet": [
        "elgeyo-marakwet",
        "elgeyo marakwet",
        "iten",
        "marakwet",
        "keiyo",
        "keiyo south",
        "keiyo north",
    ],
    "West Pokot": [
        "west pokot",
        "kapenguria",
        "kacheliba",
        "sigor",
        "pokot",
    ],
    "Narok": [
        "narok",
        "kilgoris",
        "trans mara",
        "suswa",
        "maasai mara",
        "ololulunga",
    ],
}


# ============================================================
# NEWS SOURCES
# ============================================================

RSS_SOURCES = [
    {
        "name": "The Star",
        "url": "https://www.the-star.co.ke/rss",
    },
    {
        "name": "The Standard",
        "url": "https://www.standardmedia.co.ke/rss",
    },
    {
        "name": "Citizen Digital",
        "url": "https://www.citizen.digital/rss",
    },
]


# ============================================================
# STORY PRIORITY
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
    "president",
    "deputy president",
    "cabinet",
    "government",
    "election",
    "elections",
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
]


MEDIUM_PRIORITY_TERMS = [
    "county",
    "assembly",
    "senator",
    "mp",
    "woman representative",
    "business",
    "investment",
    "jobs",
    "employment",
    "market",
    "prices",
    "education",
    "water",
    "electricity",
    "housing",
    "infrastructure",
    "tourism",
    "livestock",
    "maize",
    "dairy",
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
        "politician",
        "election",
        "elections",
        "party",
        "campaign",
        "president",
        "deputy president",
        "cabinet",
        "government",
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
    ],
    "HEALTH": [
        "hospital",
        "health",
        "doctor",
        "patient",
        "disease",
        "clinic",
        "medical",
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
    ],
}


# ============================================================
# CONFIG
# ============================================================

def load_config():
    """Load application configuration."""

    if not CONFIG_FILE.exists():
        return {
            "page_name": "Rift Valley Watch",
            "region": "Rift Valley, Kenya",
            "language": "en",
            "max_articles": 50,
            "max_script_words": 180,
        }

    try:
        with open(CONFIG_FILE, "r", encoding="utf-8") as file:
            return json.load(file)
    except Exception:
        return {
            "page_name": "Rift Valley Watch",
            "region": "Rift Valley, Kenya",
            "language": "en",
            "max_articles": 50,
            "max_script_words": 180,
        }


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_text(text):
    """Clean article text."""

    if not text:
        return ""

    text = re.sub(r"<[^>]+>", " ", str(text))
    text = re.sub(r"\s+", " ", text)

    return text.strip()


# ============================================================
# COUNTY DETECTION
# ============================================================

def detect_county(title, summary):
    """Identify the strongest matching covered county."""

    text = f"{title} {summary}".lower()

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

    return max(matches, key=matches.get)


# ============================================================
# CATEGORY DETECTION
# ============================================================

def detect_category(title, summary):
    """Identify the most relevant story category."""

    text = f"{title} {summary}".lower()

    scores = {}

    for category, keywords in CATEGORY_TERMS.items():
        score = 0

        for keyword in keywords:
            if keyword.lower() in text:
                score += 1

        scores[category] = score

    best_category = max(scores, key=scores.get)

    if scores[best_category] == 0:
        return "COMMUNITY"

    return best_category


# ============================================================
# STORY SCORING
# ============================================================

def score_story(title, summary, county):
    """Calculate a relevance and importance score."""

    text = f"{title} {summary}".lower()

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
    # Strong headline indicators
    # --------------------------------------------------------

    if "breaking" in title.lower():
        score += 10

    if re.search(r"\b\d+\b", title):
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
    # Weak / low-value formats
    # --------------------------------------------------------

    weak_terms = [
        "opinion",
        "podcast",
        "newsletter",
        "weekly roundup",
        "daily roundup",
        "best",
        "top",
    ]

    for term in weak_terms:
        if term in title.lower():
            score -= 5

    if len(title.split()) < 4:
        score -= 5

    if len(summary) < 80:
        score -= 5

    return score


# ============================================================
# FETCH RSS SOURCE
# ============================================================

def fetch_rss_source(source):
    """Fetch one RSS source safely."""

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
            timeout=20,
        )

        response.raise_for_status()

        feed = feedparser.parse(response.content)

        articles = []

        for entry in feed.entries:
            title = clean_text(
                entry.get("title", "")
            )

            summary = clean_text(
                entry.get("summary", "")
            )

            link = entry.get("link", "")

            if not title or not link:
                continue

            articles.append(
                {
                    "title": title,
                    "summary": summary,
                    "url": link,
                    "source": source["name"],
                }
            )

        return articles

    except Exception as error:
        print(
            f"[WARNING] Could not fetch "
            f"{source['name']}: {error}"
        )

        return []


# ============================================================
# REGIONAL FILTER
# ============================================================

def filter_regional_stories(articles):
    """Keep only stories relevant to our covered counties."""

    regional = []

    for article in articles:

        county = detect_county(
            article["title"],
            article["summary"],
        )

        if not county:
            continue

        article["county"] = county

        article["category"] = detect_category(
            article["title"],
            article["summary"],
        )

        article["score"] = score_story(
            article["title"],
            article["summary"],
            county,
        )

        regional.append(article)

    return regional


# ============================================================
# REMOVE DUPLICATES
# ============================================================

def remove_duplicates(articles):
    """Remove duplicate or near-duplicate headlines."""

    unique = []
    seen = set()

    for article in articles:

        normalized = re.sub(
            r"[^a-z0-9 ]",
            "",
            article["title"].lower(),
        )

        normalized = re.sub(
            r"\s+",
            " ",
            normalized,
        ).strip()

        if not normalized:
            continue

        if normalized in seen:
            continue

        seen.add(normalized)
        unique.append(article)

    return unique


# ============================================================
# SELECT STRONGEST STORY
# ============================================================

def select_story(articles):
    """Select one strongest regional story."""

    if not articles:
        return None

    articles = remove_duplicates(articles)

    articles.sort(
        key=lambda article: (
            article.get("score", 0),
            len(article.get("summary", "")),
        ),
        reverse=True,
    )

    selected = articles[0]

    selected["selected_at"] = (
        datetime.now(timezone.utc).isoformat()
    )

    return selected


# ============================================================
# SAVE STORY
# ============================================================

def save_story(story):
    """Save selected story to data/story.json."""

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
# MAIN NEWS ENGINE
# ============================================================

def run_news_engine():
    """Run the complete regional news selection process."""

    config = load_config()

    max_articles = int(
        config.get("max_articles", 50)
    )

    print("=" * 60)
    print("RIFT VALLEY WATCH — NEWS ENGINE")
    print("=" * 60)

    print("\n[1/5] Loading news sources...")

    all_articles = []

    for source in RSS_SOURCES:

        print(
            f"      Fetching: {source['name']}"
        )

        articles = fetch_rss_source(source)

        all_articles.extend(articles)

    print(
        f"      Total articles fetched: "
        f"{len(all_articles)}"
    )

    print("\n[2/5] Limiting article pool...")

    all_articles = all_articles[:max_articles]

    print(
        f"      Articles considered: "
        f"{len(all_articles)}"
    )

    print("\n[3/5] Filtering for covered counties...")

    regional_articles = filter_regional_stories(
        all_articles
    )

    print(
        f"      Regional stories found: "
        f"{len(regional_articles)}"
    )

    print("\n[4/5] Ranking stories...")

    story = select_story(
        regional_articles
    )

    if not story:

        print(
            "\n[ERROR] No relevant Rift Valley story found."
        )

        return None

    print("\n[5/5] Strongest story selected")

    print("-" * 60)
    print(f"TITLE    : {story['title']}")
    print(f"COUNTY   : {story['county']}")
    print(f"CATEGORY : {story['category']}")
    print(f"SOURCE   : {story['source']}")
    print(f"SCORE    : {story['score']}")
    print(f"URL      : {story['url']}")
    print("-" * 60)

    save_story(story)

    print(
        f"\n[SAVED] {STORY_FILE}"
    )

    return story


# ============================================================
# DIRECT EXECUTION
# ============================================================

if __name__ == "__main__":
    run_news_engine()
