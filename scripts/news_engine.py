# ============================================================
# RIFT VALLEY WATCH V2.0
# OFFICIAL-SOURCE NEWS ENGINE
#
# COVERAGE
#   Bomet
#   Kericho
#   Nakuru
#   Nandi
#   Uasin Gishu
#   Elgeyo-Marakwet
#   West Pokot
#   Narok
#
# SOURCES
#   Official county government websites only.
#
# PIPELINE
#   OFFICIAL SOURCES
#        ↓
#   ARTICLE DISCOVERY
#        ↓
#   ARTICLE BODY EXTRACTION
#        ↓
#   COUNTY DETECTION
#        ↓
#   CATEGORY DETECTION
#        ↓
#   POLITICAL / ACCOUNTABILITY SCORING
#        ↓
#   STORY RANKING
#        ↓
#   data/story.json
# ============================================================

import json
import re
import time
from pathlib import Path
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup


ROOT = Path(__file__).resolve().parents[1]

SETTINGS_FILE = ROOT / "config" / "settings.json"
STORY_FILE = ROOT / "data" / "story.json"


# ============================================================
# OFFICIAL COUNTY SOURCES
# ============================================================

OFFICIAL_SOURCES = [
    {
        "county": "Bomet",
        "source": "Bomet County Government",
        "url": "https://bomet.go.ke/news/"
    },
    {
        "county": "Kericho",
        "source": "Kericho County Government",
        "url": "https://www.kericho.go.ke/"
    },
    {
        "county": "Nakuru",
        "source": "Nakuru County Government",
        "url": "https://www.nakuru.go.ke/"
    },
    {
        "county": "Nandi",
        "source": "Nandi County Government",
        "url": "https://nandi.go.ke/news/"
    },
    {
        "county": "Uasin Gishu",
        "source": "Uasin Gishu County Government",
        "url": "https://uasingishu.go.ke/"
    },
    {
        "county": "Elgeyo-Marakwet",
        "source": "Elgeyo-Marakwet County Government",
        "url": "https://elgeyomarakwet.go.ke/news/"
    },
    {
        "county": "West Pokot",
        "source": "West Pokot County Government",
        "url": "https://www.westpokot.go.ke/"
    },
    {
        "county": "Narok",
        "source": "Narok County Government",
        "url": "https://www.narok.go.ke/"
    }
]


# ============================================================
# COUNTY KEYWORDS
# ============================================================

COUNTY_KEYWORDS = {
    "Bomet": [
        "bomet",
        "sotik",
        "chepalungu",
        "konoin",
        "bomet east",
        "bomet central",
        "kipreres"
    ],

    "Kericho": [
        "kericho",
        "bureti",
        "belgut",
        "kipkelion",
        "ainamoi",
        "sigowet",
        "soin",
        "litein",
        "londiani",
        "chepseon"
    ],

    "Nakuru": [
        "nakuru",
        "naivasha",
        "gilgil",
        "bahati",
        "molo",
        "njoro",
        "rongai",
        "subukia",
        "kuresoi",
        "elementaita"
    ],

    "Nandi": [
        "nandi",
        "kapsabet",
        "mosop",
        "emgwen",
        "aldai",
        "chesumei",
        "nandi hills",
        "tinderet"
    ],

    "Uasin Gishu": [
        "uasin gishu",
        "eldoret",
        "ainabkoi",
        "kapseret",
        "kesses",
        "moiben",
        "soy",
        "turbo"
    ],

    "Elgeyo-Marakwet": [
        "elgeyo-marakwet",
        "elgeyo marakwet",
        "itimar",
        "keiyo",
        "marakwet",
        "keiyo north",
        "keiyo south",
        "marakwet east",
        "marakwet west",
        "itens"
    ],

    "West Pokot": [
        "west pokot",
        "pokot",
        "kapenguria",
        "pokot south",
        "pokot central",
        "pokot north",
        "pokot west",
        "sigor"
    ],

    "Narok": [
        "narok",
        "transmara",
        "kilgoris",
        "emurua dikir",
        "narok north",
        "narok south",
        "narok west",
        "narok east"
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
        "emergency",
        "latest",
        "just in"
    ],

    "POLITICS": [
        "governor",
        "senator",
        "mca",
        "mp",
        "politician",
        "political",
        "politics",
        "election",
        "campaign",
        "party",
        "assembly",
        "county assembly",
        "leadership",
        "leader",
        "ward",
        "vote",
        "votes",
        "elected",
        "government"
    ],

    "ACCOUNTABILITY": [
        "auditor",
        "audit",
        "oversight",
        "procurement",
        "tender",
        "contract",
        "budget",
        "expenditure",
        "public funds",
        "public money",
        "misuse",
        "irregular",
        "irregularities",
        "fraud",
        "investigation",
        "investigations",
        "query",
        "queries",
        "accountability",
        "transparency",
        "corruption",
        "pending bills",
        "unaccounted"
    ],

    "DEVELOPMENT": [
        "project",
        "projects",
        "construction",
        "road",
        "roads",
        "bridge",
        "bridges",
        "water",
        "drainage",
        "infrastructure",
        "development",
        "facility",
        "market",
        "stadium",
        "housing",
        "electricity",
        "irrigation"
    ],

    "SECURITY": [
        "security",
        "police",
        "crime",
        "criminal",
        "arrest",
        "arrests",
        "accident",
        "accidents",
        "fire",
        "flood",
        "disaster",
        "rescue",
        "terror",
        "violence",
        "missing",
        "investigation"
    ],

    "AGRICULTURE": [
        "farmer",
        "farmers",
        "agriculture",
        "agricultural",
        "farming",
        "coffee",
        "tea",
        "maize",
        "milk",
        "livestock",
        "dairy",
        "fertilizer",
        "seedlings",
        "crops",
        "crop",
        "food",
        "irrigation",
        "harvest"
    ],

    "HEALTH": [
        "health",
        "hospital",
        "clinic",
        "doctor",
        "doctors",
        "nurse",
        "nurses",
        "patient",
        "patients",
        "medicine",
        "medical",
        "disease",
        "vaccination",
        "immunization",
        "healthcare",
        "maternity"
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
        "scholarships",
        "learning",
        "classroom"
    ],

    "BUSINESS": [
        "business",
        "businesses",
        "investment",
        "investor",
        "trade",
        "market",
        "markets",
        "enterprise",
        "entrepreneur",
        "entrepreneurs",
        "jobs",
        "employment",
        "industry",
        "industrial",
        "revenue",
        "economic"
    ],

    "COMMUNITY": [
        "community",
        "residents",
        "residents",
        "youth",
        "women",
        "group",
        "groups",
        "citizens",
        "public",
        "families",
        "households",
        "volunteers"
    ],

    "TOURISM": [
        "tourism",
        "tourist",
        "tourists",
        "wildlife",
        "park",
        "parks",
        "safari",
        "hotel",
        "hotels",
        "conservation",
        "heritage",
        "attraction",
        "attractions"
    ]
}


# ============================================================
# TERMS USED FOR SCORING
# ============================================================

HIGH_PRIORITY_TERMS = [
    "breaking",
    "urgent",
    "emergency",
    "audit",
    "auditor",
    "investigation",
    "irregularities",
    "fraud",
    "corruption",
    "security",
    "arrest",
    "death",
    "accident",
    "flood",
    "fire",
    "election",
    "governor",
    "senator",
    "county assembly"
]


MEDIUM_PRIORITY_TERMS = [
    "budget",
    "procurement",
    "tender",
    "project",
    "hospital",
    "school",
    "road",
    "water",
    "farmers",
    "coffee",
    "tea",
    "jobs",
    "investment",
    "market"
]


WEAK_TERMS = [
    "welcome",
    "courtesy call",
    "congratulations",
    "birthday",
    "merry christmas",
    "happy new year",
    "condolences",
    "delegation",
    "meeting held",
    "photo",
    "gallery"
]


GENERIC_TITLES = [
    "recent news",
    "recent news & events",
    "news",
    "news and events",
    "latest news",
    "events",
    "home",
    "homepage",
    "welcome",
    "updates",
    "county updates",
    "our news"
]


# ============================================================
# REQUEST SETTINGS
# ============================================================

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/139.0 Safari/537.36"
    )
}

REQUEST_TIMEOUT = 25


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_text(text):

    if not text:
        return ""

    text = re.sub(r"\s+", " ", str(text))

    text = text.replace(
        "\xa0",
        " "
    )

    return text.strip()


def normalize_text(text):

    text = clean_text(text)

    return text.lower()


def sentence_clean(text):

    text = clean_text(text)

    text = re.sub(
        r"\s+([,.!?;:])",
        r"\1",
        text
    )

    return text.strip()


# ============================================================
# URL HELPERS
# ============================================================

def same_domain(base_url, target_url):

    try:
        base_domain = urlparse(base_url).netloc.lower()
        target_domain = urlparse(target_url).netloc.lower()

        base_domain = base_domain.replace(
            "www.",
            ""
        )

        target_domain = target_domain.replace(
            "www.",
            ""
        )

        return (
            target_domain == base_domain
            or target_domain.endswith("." + base_domain)
        )

    except Exception:
        return False


def is_valid_story_url(url):

    if not url:
        return False

    lowered = url.lower()

    blocked = [
        "#",
        "javascript:",
        "mailto:",
        "/contact",
        "/about",
        "/login",
        "/search",
        "/gallery",
        "/category/",
        "/tag/",
        "/author/",
        "/page/"
    ]

    for item in blocked:

        if item in lowered:
            return False

    return True


# ============================================================
# GENERIC TITLE CHECK
# ============================================================

def is_generic_title(title):

    normalized = normalize_text(title)

    if not normalized:
        return True

    if normalized in GENERIC_TITLES:
        return True

    if len(normalized) < 20:
        return True

    return False


# ============================================================
# FETCH PAGE
# ============================================================

def fetch_page(url):

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=REQUEST_TIMEOUT
    )

    response.raise_for_status()

    return response.text


# ============================================================
# EXTRACT ARTICLE BODY
# ============================================================

def extract_article_body(soup):

    # --------------------------------------------------------
    # First try semantic article containers.
    # --------------------------------------------------------

    article_selectors = [
        "article",
        "main article",
        ".entry-content",
        ".post-content",
        ".article-content",
        ".single-post-content",
        ".td-post-content",
        ".blog-content",
        ".news-content",
        ".content-area",
        ".site-main",
        "main"
    ]

    candidates = []

    for selector in article_selectors:

        try:
            elements = soup.select(selector)
        except Exception:
            elements = []

        for element in elements:

            paragraphs = element.find_all(
                "p"
            )

            text_parts = []

            for paragraph in paragraphs:

                text = sentence_clean(
                    paragraph.get_text(
                        " ",
                        strip=True
                    )
                )

                if len(text) < 25:
                    continue

                lowered = normalize_text(text)

                # Ignore obvious navigation.
                if lowered in [
                    "read more",
                    "share this",
                    "follow us",
                    "click here",
                    "contact us"
                ]:
                    continue

                text_parts.append(text)

            if text_parts:

                combined = " ".join(
                    text_parts
                )

                if len(combined) > 100:
                    candidates.append(
                        combined
                    )

    # --------------------------------------------------------
    # Choose the longest useful candidate.
    # --------------------------------------------------------

    if candidates:

        candidates.sort(
            key=len,
            reverse=True
        )

        return clean_text(
            candidates[0]
        )

    # --------------------------------------------------------
    # Fallback: collect useful paragraphs from page.
    # --------------------------------------------------------

    paragraphs = soup.find_all("p")

    fallback = []

    for paragraph in paragraphs:

        text = sentence_clean(
            paragraph.get_text(
                " ",
                strip=True
            )
        )

        if len(text) < 35:
            continue

        lowered = normalize_text(text)

        blocked = [
            "subscribe",
            "newsletter",
            "follow us",
            "privacy policy",
            "terms and conditions",
            "cookie policy",
            "read more",
            "contact us"
        ]

        if any(
            word in lowered
            for word in blocked
        ):
            continue

        fallback.append(text)

    return clean_text(
        " ".join(fallback)
    )


# ============================================================
# EXTRACT TITLE
# ============================================================

def extract_title(soup):

    candidates = []

    # Prefer OpenGraph title.
    og = soup.find(
        "meta",
        property="og:title"
    )

    if og and og.get("content"):
        candidates.append(
            clean_text(
                og.get("content")
            )
        )

    # Then H1.
    for h1 in soup.find_all("h1"):

        text = clean_text(
            h1.get_text(
                " ",
                strip=True
            )
        )

        if text:
            candidates.append(text)

    # Then page title.
    if soup.title:

        text = clean_text(
            soup.title.get_text(
                " ",
                strip=True
            )
        )

        if text:
            candidates.append(text)

    for title in candidates:

        if not is_generic_title(title):

            # Remove common website suffixes.
            title = re.split(
                r"\s+[|–-]\s+(?:Nakuru|Kericho|Bomet|"
                r"Nandi|Narok|County Government).*$",
                title,
                flags=re.IGNORECASE
            )[0]

            return clean_text(title)

    return ""


# ============================================================
# EXTRACT DESCRIPTION
# ============================================================

def extract_description(soup):

    meta_names = [
        ("meta", {"name": "description"}),
        ("meta", {"property": "og:description"}),
    ]

    for tag_name, attrs in meta_names:

        tag = soup.find(
            tag_name,
            attrs=attrs
        )

        if tag and tag.get("content"):

            text = clean_text(
                tag.get("content")
            )

            if len(text) >= 40:
                return text

    return ""


# ============================================================
# EXTRACT DATE
# ============================================================

def extract_date(soup):

    # Standard article published time.
    time_tag = soup.find(
        "time"
    )

    if time_tag:

        value = (
            time_tag.get("datetime")
            or time_tag.get_text(
                " ",
                strip=True
            )
        )

        if value:
            return clean_text(value)

    # Common metadata.
    for attrs in [
        {"property": "article:published_time"},
        {"name": "date"},
        {"name": "publish-date"},
        {"name": "datePublished"}
    ]:

        tag = soup.find(
            "meta",
            attrs=attrs
        )

        if tag and tag.get("content"):

            return clean_text(
                tag.get("content")
            )

    return ""


# ============================================================
# EXTRACT LINKS FROM SOURCE PAGE
# ============================================================

def extract_links(
    soup,
    source_url,
    county
):

    links = []

    seen = set()

    for anchor in soup.find_all("a"):

        href = anchor.get("href")

        if not href:
            continue

        url = urljoin(
            source_url,
            href
        )

        if not same_domain(
            source_url,
            url
        ):
            continue

        if not is_valid_story_url(url):
            continue

        if url.rstrip("/") in seen:
            continue

        text = clean_text(
            anchor.get_text(
                " ",
                strip=True
            )
        )

        if len(text) < 20:
            continue

        if len(text) > 250:
            text = text[:250]

        if is_generic_title(text):
            continue

        # Navigation links are often very short or generic.
        lowered = normalize_text(text)

        navigation = [
            "home",
            "about",
            "contact",
            "services",
            "departments",
            "careers",
            "downloads",
            "tenders",
            "documents",
            "more",
            "read more",
            "view all",
            "next",
            "previous"
        ]

        if lowered in navigation:
            continue

        # A likely story title usually has enough text.
        if len(text.split()) < 4:
            continue

        seen.add(
            url.rstrip("/")
        )

        links.append(
            {
                "title": text,
                "url": url,
                "county": county
            }
        )

    return links


# ============================================================
# COUNTY DETECTION
# ============================================================

def detect_county(text, fallback=""):

    normalized = normalize_text(text)

    scores = {}

    for county, keywords in COUNTY_KEYWORDS.items():

        score = 0

        for keyword in keywords:

            if keyword in normalized:
                score += 1

        scores[county] = score

    best_county = fallback
    best_score = 0

    for county, score in scores.items():

        if score > best_score:

            best_county = county
            best_score = score

    return best_county


# ============================================================
# CATEGORY DETECTION
# ============================================================

def detect_category(title, summary):

    text = normalize_text(
        f"{title} {summary}"
    )

    scores = {}

    for category, terms in CATEGORIES.items():

        score = 0

        for term in terms:

            if term in text:
                score += 1

        scores[category] = score

    best_category = "COMMUNITY"
    best_score = 0

    # Accountability gets priority when strongly indicated.
    accountability_hits = sum(
        1
        for term in CATEGORIES["ACCOUNTABILITY"]
        if term in text
    )

    political_hits = sum(
        1
        for term in CATEGORIES["POLITICS"]
        if term in text
    )

    breaking_hits = sum(
        1
        for term in CATEGORIES["BREAKING NEWS"]
        if term in text
    )

    if breaking_hits >= 2:
        return "BREAKING NEWS"

    if accountability_hits >= 2:
        return "ACCOUNTABILITY"

    if political_hits >= 2:
        return "POLITICS"

    for category, score in scores.items():

        if score > best_score:

            best_category = category
            best_score = score

    return best_category


# ============================================================
# POLITICAL SCORE
# ============================================================

def political_score(title, summary):

    text = normalize_text(
        f"{title} {summary}"
    )

    score = 0

    for term in CATEGORIES["POLITICS"]:

        if term in text:
            score += 4

    return score


# ============================================================
# ACCOUNTABILITY SCORE
# ============================================================

def accountability_score(title, summary):

    text = normalize_text(
        f"{title} {summary}"
    )

    score = 0

    for term in CATEGORIES["ACCOUNTABILITY"]:

        if term in text:
            score += 5

    return score


# ============================================================
# STORY SCORE
# ============================================================

def score_story(story):

    title = normalize_text(
        story.get("title", "")
    )

    summary = normalize_text(
        story.get("summary", "")
    )

    combined = f"{title} {summary}"

    score = 0

    # County relevance.
    if story.get("county"):
        score += 10

    # Strong headline.
    if len(title.split()) >= 7:
        score += 5

    # Useful article body.
    if len(summary) >= 200:
        score += 10

    if len(summary) >= 500:
        score += 5

    if len(summary) >= 1000:
        score += 5

    # High priority terms.
    for term in HIGH_PRIORITY_TERMS:

        if term in combined:
            score += 6

    # Medium priority terms.
    for term in MEDIUM_PRIORITY_TERMS:

        if term in combined:
            score += 3

    # Political scrutiny.
    p_score = political_score(
        title,
        summary
    )

    # Accountability scrutiny.
    a_score = accountability_score(
        title,
        summary
    )

    score += p_score
    score += a_score

    # Category bonus.
    category = story.get(
        "category",
        ""
    )

    if category == "BREAKING NEWS":
        score += 15

    elif category == "ACCOUNTABILITY":
        score += 14

    elif category == "POLITICS":
        score += 10

    elif category == "SECURITY":
        score += 10

    elif category == "DEVELOPMENT":
        score += 7

    elif category == "AGRICULTURE":
        score += 6

    # Penalize weak generic stories.
    for term in WEAK_TERMS:

        if term in combined:
            score -= 3

    # Generic titles should be heavily penalized.
    if is_generic_title(
        story.get("title", "")
    ):
        score -= 30

    return score, p_score, a_score


# ============================================================
# ENRICH STORY
# ============================================================

def enrich_story(story):

    title = clean_text(
        story.get("title", "")
    )

    summary = clean_text(
        story.get("summary", "")
    )

    county = detect_county(
        f"{title} {summary}",
        story.get("county", "")
    )

    category = detect_category(
        title,
        summary
    )

    story["title"] = title
    story["summary"] = summary
    story["county"] = county
    story["category"] = category

    score, p_score, a_score = score_story(
        story
    )

    story["score"] = score
    story["political_score"] = p_score
    story["accountability_score"] = a_score

    return story


# ============================================================
# DISCOVER ARTICLE LINKS
# ============================================================

def discover_articles(source):

    county = source["county"]
    source_name = source["source"]
    source_url = source["url"]

    print(
        f"      Fetching: {source_name}"
    )

    try:

        html = fetch_page(
            source_url
        )

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        links = extract_links(
            soup,
            source_url,
            county
        )

        print(
            f"      Candidate links found: "
            f"{len(links)}"
        )

        return links

    except Exception as e:

        print(
            f"[WARNING] Could not fetch "
            f"{source_name}: {e}"
        )

        return []


# ============================================================
# FETCH INDIVIDUAL ARTICLE
# ============================================================

def fetch_article(
    candidate,
    source
):

    url = candidate["url"]

    try:

        html = fetch_page(
            url
        )

        soup = BeautifulSoup(
            html,
            "html.parser"
        )

        title = extract_title(
            soup
        )

        if not title:

            title = candidate.get(
                "title",
                ""
            )

        if is_generic_title(title):

            return None

        body = extract_article_body(
            soup
        )

        description = extract_description(
            soup
        )

        date = extract_date(
            soup
        )

        # Prefer real article body.
        summary = body

        # If article body is too short,
        # use the official meta description.
        if len(summary) < 100:

            if len(description) > len(summary):

                summary = description

        # If there is still no useful content,
        # don't publish the story.
        if len(summary) < 80:

            return None

        county = detect_county(
            f"{title} {summary}",
            source["county"]
        )

        story = {
            "title": title,
            "summary": summary,
            "county": county,
            "category": "",
            "source": source["source"],
            "url": url,
            "date": date
        }

        return enrich_story(
            story
        )

    except Exception:

        return None


# ============================================================
# DEDUPLICATE STORIES
# ============================================================

def deduplicate(stories):

    unique = {}

    for story in stories:

        title = normalize_text(
            story.get("title", "")
        )

        url = story.get(
            "url",
            ""
        ).rstrip("/")

        key = title or url

        if not key:
            continue

        # Keep highest scoring version.
        if (
            key not in unique
            or story.get("score", 0)
            > unique[key].get("score", 0)
        ):

            unique[key] = story

    return list(
        unique.values()
    )


# ============================================================
# SELECT STRONGEST STORY
# ============================================================

def select_story(stories):

    if not stories:
        return None

    stories = sorted(
        stories,
        key=lambda item: item.get(
            "score",
            0
        ),
        reverse=True
    )

    return stories[0]


# ============================================================
# SAVE STORY
# ============================================================

def save_story(story):

    STORY_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    output = {
        "page": "Rift Valley Watch",

        "status": "ready",

        "title": story.get(
            "title",
            ""
        ),

        "summary": story.get(
            "summary",
            ""
        ),

        "county": story.get(
            "county",
            ""
        ),

        "category": story.get(
            "category",
            ""
        ),

        "source": story.get(
            "source",
            ""
        ),

        "url": story.get(
            "url",
            ""
        ),

        "date": story.get(
            "date",
            ""
        ),

        "score": story.get(
            "score",
            0
        ),

        "political_score": story.get(
            "political_score",
            0
        ),

        "accountability_score": story.get(
            "accountability_score",
            0
        )
    }

    with open(
        STORY_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            output,
            f,
            indent=2,
            ensure_ascii=False
        )


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 60)
    print("RIFT VALLEY WATCH V2.0")
    print("OFFICIAL-SOURCE NEWS ENGINE")
    print("=" * 60)

    print()
    print(
        "Primary county government sources only."
    )

    print(
        "Political and accountability stories included."
    )

    print(
        "Article-body extraction enabled."
    )

    # --------------------------------------------------------
    # STEP 1
    # --------------------------------------------------------

    print()
    print(
        "[1/5] Discovering official county stories..."
    )

    candidates = []

    for source in OFFICIAL_SOURCES:

        found = discover_articles(
            source
        )

        for item in found:

            item["source"] = source[
                "source"
            ]

            candidates.append(
                item
            )

        # Small delay between county requests.
        time.sleep(1)

    print()
    print(
        f"      Total candidate links: "
        f"{len(candidates)}"
    )

    # --------------------------------------------------------
    # STEP 2
    # --------------------------------------------------------

    print()
    print(
        "[2/5] Extracting article content..."
    )

    stories = []

    # Don't hammer the official websites.
    max_articles = 60

    for index, candidate in enumerate(
        candidates[:max_articles],
        start=1
    ):

        source = {
            "county": candidate.get(
                "county",
                ""
            ),
            "source": candidate.get(
                "source",
                ""
            )
        }

        story = fetch_article(
            candidate,
            source
        )

        if story:

            stories.append(
                story
            )

        if index % 10 == 0:

            print(
                f"      Processed: "
                f"{index}/{min(len(candidates), max_articles)}"
            )

        time.sleep(0.25)

    print()
    print(
        f"      Usable articles: "
        f"{len(stories)}"
    )

    # --------------------------------------------------------
    # STEP 3
    # --------------------------------------------------------

    print()
    print(
        "[3/5] Detecting counties and categories..."
    )

    enriched = []

    for story in stories:

        enriched.append(
            enrich_story(
                story
            )
        )

    enriched = deduplicate(
        enriched
    )

    print(
        f"      Unique stories: "
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

    if not selected:

        print()
        print(
            "[ERROR] No usable official-source "
            "story found."
        )

        print()
        print(
            "The county websites may be temporarily "
            "unavailable or may have changed structure."
        )

        return

    # --------------------------------------------------------
    # STEP 5
    # --------------------------------------------------------

    print()
    print(
        "[5/5] Strongest story selected"
    )

    print("-" * 60)

    print(
        f"TITLE        : "
        f"{selected.get('title', '')}"
    )

    print(
        f"COUNTY       : "
        f"{selected.get('county', '')}"
    )

    print(
        f"CATEGORY     : "
        f"{selected.get('category', '')}"
    )

    print(
        f"SOURCE       : "
        f"{selected.get('source', '')}"
    )

    print(
        f"SCORE        : "
        f"{selected.get('score', 0)}"
    )

    print(
        f"POLITICAL    : "
        f"{selected.get('political_score', 0)}"
    )

    print(
        f"ACCOUNTABILITY: "
        f"{selected.get('accountability_score', 0)}"
    )

    print(
        f"SUMMARY WORDS: "
        f"{len(selected.get('summary', '').split())}"
    )

    print(
        f"URL          : "
        f"{selected.get('url', '')}"
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
    print(
        "RIFT VALLEY WATCH NEWS ENGINE COMPLETE."
    )


if __name__ == "__main__":
    main()
