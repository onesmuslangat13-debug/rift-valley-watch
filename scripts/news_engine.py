```python
# ============================================================
# RIFT VALLEY WATCH V2.0
# PROFESSIONAL NEWS SCRIPT ENGINE
#
# STORY
#   ↓
# FACT EXTRACTION
#   ↓
# PROFESSIONAL NEWS SCRIPT
#   ↓
# QUALITY CONTROL
#
# Structure:
# HOOK
# WHAT HAPPENED
# KEY FACTS
# WHY IT MATTERS
# IMPACT
# CLOSE
#
# Primary-source newsroom approach.
# ============================================================

import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

STORY_FILE = ROOT / "data" / "story.json"
SCRIPT_FILE = ROOT / "data" / "script.json"

MAX_WORDS = 180
TARGET_WORDS = 155
MIN_WORDS = 60


# ============================================================
# TEXT CLEANING
# ============================================================

def clean_text(text):

    if not text:
        return ""

    text = str(text)

    text = text.replace(
        "\xa0",
        " "
    )

    text = re.sub(
        r"\s+",
        " ",
        text
    )

    return text.strip()


def word_count(text):

    return len(
        clean_text(text).split()
    )


def sentence_split(text):

    text = clean_text(text)

    if not text:
        return []

    sentences = re.split(
        r"(?<=[.!?])\s+",
        text
    )

    cleaned = []

    for sentence in sentences:

        sentence = clean_text(
            sentence
        )

        if sentence:
            cleaned.append(
                sentence
            )

    return cleaned


# ============================================================
# SAFE WORD TRIMMING
# ============================================================

def trim_to_complete_sentences(
    text,
    maximum
):

    sentences = sentence_split(
        text
    )

    if not sentences:
        return ""

    selected = []
    total = 0

    for sentence in sentences:

        words = word_count(
            sentence
        )

        if total + words > maximum:
            break

        selected.append(
            sentence
        )

        total += words

    if selected:
        return " ".join(
            selected
        )

    # Preserve the first complete sentence
    # if it alone exceeds the limit.
    return sentences[0]


# ============================================================
# LOAD STORY
# ============================================================

def load_story():

    if not STORY_FILE.exists():

        print(
            "[ERROR] data/story.json was not found."
        )

        return None

    try:

        with open(
            STORY_FILE,
            "r",
            encoding="utf-8"
        ) as f:

            data = json.load(f)

        if not isinstance(data, dict):

            print(
                "[ERROR] story.json must contain "
                "a JSON object."
            )

            return None

        return data

    except json.JSONDecodeError as e:

        print(
            f"[ERROR] Invalid JSON in story.json: {e}"
        )

        return None

    except Exception as e:

        print(
            f"[ERROR] Could not read story.json: {e}"
        )

        return None


# ============================================================
# CLEAN ARTICLE SUMMARY
# ============================================================

def clean_summary(
    summary,
    title
):

    summary = clean_text(
        summary
    )

    title = clean_text(
        title
    )

    if not summary:
        return ""

    # --------------------------------------------------------
    # Remove exact duplicated headline from beginning.
    # --------------------------------------------------------

    if title:

        title_lower = title.lower()
        summary_lower = summary.lower()

        if summary_lower.startswith(
            title_lower
        ):

            summary = summary[
                len(title):
            ].strip(
                " .:-"
            )

    # --------------------------------------------------------
    # Remove common scraped website phrases.
    # --------------------------------------------------------

    unwanted_patterns = [
        r"^the greatest good for the greatest number\s*",
        r"^read more\s*",
        r"^share this\s*",
        r"^home\s*",
    ]

    for pattern in unwanted_patterns:

        summary = re.sub(
            pattern,
            "",
            summary,
            flags=re.IGNORECASE
        )

    # --------------------------------------------------------
    # Remove repeated title if it appears immediately.
    # --------------------------------------------------------

    if title:

        pattern = (
            r"^"
            + re.escape(title)
            + r"\.?\s*"
        )

        summary = re.sub(
            pattern,
            "",
            summary,
            flags=re.IGNORECASE
        )

    return clean_text(
        summary
    )


# ============================================================
# EXTRACT USEFUL FACTS
# ============================================================

def extract_facts(
    summary,
    maximum=4
):

    sentences = sentence_split(
        summary
    )

    facts = []

    noise = [
        "click here",
        "read more",
        "follow us",
        "subscribe",
        "share this",
        "cookie policy",
        "privacy policy",
        "terms and conditions"
    ]

    for sentence in sentences:

        if word_count(sentence) < 6:
            continue

        lowered = sentence.lower()

        if any(
            item in lowered
            for item in noise
        ):
            continue

        facts.append(
            sentence
        )

        if len(facts) >= maximum:
            break

    return facts


# ============================================================
# LOCATION HELPER
# ============================================================

def get_location(story):

    county = clean_text(
        story.get(
            "county",
            ""
        )
    )

    if county:
        return county

    return "the region"


# ============================================================
# CATEGORY NORMALIZATION
# ============================================================

def get_category(story):

    category = clean_text(
        story.get(
            "category",
            ""
        )
    ).upper()

    if not category:
        category = "REGIONAL NEWS"

    # --------------------------------------------------------
    # Correct common development misclassification.
    # --------------------------------------------------------

    if category == "POLITICS":

        title = clean_text(
            story.get(
                "title",
                ""
            )
        ).lower()

        summary = clean_text(
            story.get(
                "summary",
                ""
            )
        ).lower()

        combined = (
            title + " " + summary
        )

        development_terms = [
            "construction",
            "stadium",
            "road",
            "roads",
            "bridge",
            "water project",
            "hospital",
            "school",
            "market",
            "infrastructure",
            "facility",
            "project",
            "development",
            "irrigation",
            "housing"
        ]

        accountability_terms = [
            "audit",
            "auditor",
            "fraud",
            "corruption",
            "irregular",
            "irregularities",
            "misuse",
            "procurement",
            "tender",
            "investigation",
            "oversight",
            "unaccounted",
            "public funds",
            "pending bills"
        ]

        political_terms = [
            "election",
            "campaign",
            "party",
            "political dispute",
            "political battle",
            "political rivalry",
            "vote",
            "votes",
            "governor fight",
            "senator fight",
            "mca fight",
            "leadership dispute"
        ]

        development_hits = sum(
            1
            for term in development_terms
            if term in combined
        )

        accountability_hits = sum(
            1
            for term in accountability_terms
            if term in combined
        )

        political_hits = sum(
            1
            for term in political_terms
            if term in combined
        )

        if (
            development_hits >= 2
            and accountability_hits == 0
            and political_hits == 0
        ):
            return "DEVELOPMENT"

    return category


# ============================================================
# HOOK
# ============================================================

def generate_hook(story):

    title = clean_text(
        story.get(
            "title",
            ""
        )
    )

    county = get_location(
        story
    )

    category = get_category(
        story
    )

    if not title:
        title = "a new regional development"

    if category == "BREAKING NEWS":

        return (
            f"Breaking news from {county}: "
            f"{title}."
        )

    if category == "POLITICS":

        return (
            f"Political developments in {county} "
            f"are drawing attention after "
            f"{title.lower()}."
        )

    if category == "ACCOUNTABILITY":

        return (
            f"A major accountability issue is "
            f"drawing attention in {county}: "
            f"{title.lower()}."
        )

    if category == "DEVELOPMENT":

        return (
            f"A major development is taking shape "
            f"in {county} after {title.lower()}."
        )

    if category == "AGRICULTURE":

        return (
            f"Farmers in {county} are at the centre "
            f"of a new development: "
            f"{title.lower()}."
        )

    if category == "HEALTH":

        return (
            f"A new health development in {county} "
            f"could affect local residents: "
            f"{title.lower()}."
        )

    if category == "EDUCATION":

        return (
            f"Education is taking centre stage in "
            f"{county} after {title.lower()}."
        )

    if category == "BUSINESS":

        return (
            f"Business activity in {county} is getting "
            f"attention after {title.lower()}."
        )

    if category == "SECURITY":

        return (
            f"A security development in {county} "
            f"is drawing attention after "
            f"{title.lower()}."
        )

    if category == "COMMUNITY":

        return (
            f"A community development in {county} "
            f"is drawing attention after "
            f"{title.lower()}."
        )

    if category == "TOURISM":

        return (
            f"Tourism is getting attention in {county} "
            f"after {title.lower()}."
        )

    return (
        f"Here is the latest development from "
        f"{county}: {title}."
    )


# ============================================================
# WHAT HAPPENED
# ============================================================

def generate_what_happened(
    story,
    facts
):

    title = clean_text(
        story.get(
            "title",
            ""
        )
    )

    source = clean_text(
        story.get(
            "source",
            ""
        )
    )

    if not source:
        source = "the official source"

    if not title:
        title = "The latest development"

    if not facts:

        return (
            f"{title}. "
            f"The development was reported by "
            f"{source}."
        )

    first_fact = facts[0]

    # Avoid repeating the title as a second sentence.
    if first_fact.lower() == title.lower():

        if len(facts) > 1:
            first_fact = facts[1]

        else:

            return (
                f"{title}. "
                f"The development was reported by "
                f"{source}."
            )

    return (
        f"{title}. "
        f"The {source} reports that "
        f"{first_fact}"
    )


# ============================================================
# KEY FACTS
# ============================================================

def generate_key_facts(
    facts
):

    if not facts:

        return (
            "The official source does not currently "
            "provide enough detail for additional "
            "facts to be stated confidently."
        )

    selected = []

    for fact in facts:

        if fact not in selected:

            selected.append(
                fact
            )

        if len(selected) >= 2:
            break

    return " ".join(
        selected
    )


# ============================================================
# WHY IT MATTERS
# ============================================================

def generate_why_it_matters(
    story
):

    category = get_category(
        story
    )

    county = get_location(
        story
    )

    if category == "AGRICULTURE":

        return (
            f"The development matters because agriculture "
            f"is an important part of livelihoods in "
            f"{county}, and changes in farming practices "
            f"can affect household incomes, food security "
            f"and local markets."
        )

    if category == "HEALTH":

        return (
            f"The development matters because health "
            f"services directly affect residents across "
            f"{county}, particularly access, quality and "
            f"availability of care."
        )

    if category == "EDUCATION":

        return (
            f"The development matters because education "
            f"investment can affect students, teachers "
            f"and long-term opportunities across "
            f"{county}."
        )

    if category == "BUSINESS":

        return (
            f"The development matters because business "
            f"activity can influence jobs, investment, "
            f"household income and county revenue."
        )

    if category == "DEVELOPMENT":

        return (
            f"The development matters because public "
            f"projects can affect services, infrastructure, "
            f"jobs and economic activity across {county}."
        )

    if category == "POLITICS":

        return (
            f"The development matters because political "
            f"decisions can directly affect public policy, "
            f"county priorities and the use of public resources."
        )

    if category == "ACCOUNTABILITY":

        return (
            f"The issue matters because public resources "
            f"require transparency, proper oversight and "
            f"clear evidence of how money is being used."
        )

    if category == "SECURITY":

        return (
            f"The development matters because security "
            f"conditions can directly affect residents, "
            f"businesses and movement across the region."
        )

    if category == "COMMUNITY":

        return (
            f"The development matters because community "
            f"issues can directly affect residents, "
            f"local services and quality of life."
        )

    if category == "TOURISM":

        return (
            f"The development matters because tourism "
            f"can support jobs, local businesses, "
            f"investment and community income."
        )

    return (
        f"The development matters because it could "
        f"affect residents and communities in "
        f"{county}."
    )


# ============================================================
# IMPACT
# ============================================================

def generate_impact(
    story
):

    category = get_category(
        story
    )

    county = get_location(
        story
    )

    if category == "AGRICULTURE":

        return (
            f"For farmers and households in {county}, "
            f"the key question will be whether the "
            f"development produces measurable benefits "
            f"over time."
        )

    if category == "DEVELOPMENT":

        return (
            f"For residents of {county}, the real test "
            f"will be whether the project is completed "
            f"as planned and delivers practical benefits."
        )

    if category == "POLITICS":

        return (
            f"For residents, the focus should remain on "
            f"what the decision means in practice and "
            f"whether promised outcomes are delivered."
        )

    if category == "ACCOUNTABILITY":

        return (
            f"For taxpayers, the important issue is whether "
            f"the available evidence supports the decisions "
            f"and whether public funds are being managed "
            f"properly."
        )

    if category == "HEALTH":

        return (
            f"For residents, the key measure will be whether "
            f"the development improves access to effective "
            f"health services."
        )

    if category == "EDUCATION":

        return (
            f"For families and students, the impact will "
            f"ultimately depend on whether the development "
            f"improves access and learning outcomes."
        )

    if category == "BUSINESS":

        return (
            f"For businesses and workers, the key question "
            f"is whether the development creates sustainable "
            f"economic opportunities."
        )

    if category == "SECURITY":

        return (
            f"For residents and businesses, the key question "
            f"is whether the development improves safety "
            f"and security in the affected area."
        )

    if category == "COMMUNITY":

        return (
            f"For residents of {county}, the impact will "
            f"depend on whether the reported development "
            f"produces practical benefits for the community."
        )

    if category == "TOURISM":

        return (
            f"For local communities and businesses, the key "
            f"question is whether the development strengthens "
            f"tourism activity and creates sustainable income."
        )

    return (
        f"For residents of {county}, the significance "
        f"will depend on what happens next and whether "
        f"the reported development produces tangible results."
    )


# ============================================================
# CLOSE
# ============================================================

def generate_close(
    story
):

    county = get_location(
        story
    )

    return (
        f"Rift Valley Watch will continue tracking "
        f"developments across {county} and the wider "
        f"Rift Valley. Follow for verified regional "
        f"news, accountability and developments."
    )


# ============================================================
# BUILD SCRIPT
# ============================================================

def build_script(
    story
):

    title = clean_text(
        story.get(
            "title",
            ""
        )
    )

    raw_summary = clean_text(
        story.get(
            "summary",
            ""
        )
    )

    summary = clean_summary(
        raw_summary,
        title
    )

    facts = extract_facts(
        summary,
        maximum=4
    )

    hook = generate_hook(
        story
    )

    what_happened = generate_what_happened(
        story,
        facts
    )

    key_facts = generate_key_facts(
        facts
    )

    why_it_matters = generate_why_it_matters(
        story
    )

    impact = generate_impact(
        story
    )

    close = generate_close(
        story
    )

    sections = {
        "hook": hook,
        "what_happened": what_happened,
        "key_facts": key_facts,
        "why_it_matters": why_it_matters,
        "impact": impact,
        "close": close
    }

    # --------------------------------------------------------
    # Build narration.
    # --------------------------------------------------------

    narration = " ".join(
        [
            hook,
            what_happened,
            key_facts,
            why_it_matters,
            impact,
            close
        ]
    )

    narration = clean_text(
        narration
    )

    # --------------------------------------------------------
    # Remove accidental duplicated sentences.
    # --------------------------------------------------------

    sentences = sentence_split(
        narration
    )

    unique_sentences = []
    seen = set()

    for sentence in sentences:

        normalized = (
            sentence
            .lower()
            .strip()
        )

        if normalized in seen:
            continue

        seen.add(
            normalized
        )

        unique_sentences.append(
            sentence
        )

    narration = " ".join(
        unique_sentences
    )

    # --------------------------------------------------------
    # Never cut narration in the middle of a sentence.
    # --------------------------------------------------------

    if word_count(narration) > TARGET_WORDS:

        narration = trim_to_complete_sentences(
            narration,
            TARGET_WORDS
        )

    # --------------------------------------------------------
    # Absolute safety limit.
    # --------------------------------------------------------

    if word_count(narration) > MAX_WORDS:

        narration = trim_to_complete_sentences(
            narration,
            MAX_WORDS
        )

    return sections, narration


# ============================================================
# SAVE SCRIPT
# ============================================================

def save_script(
    story,
    sections,
    narration
):

    SCRIPT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    output = {

        "page": "Rift Valley Watch",

        "status": "ready",

        "story": {
            "title": story.get(
                "title",
                ""
            ),

            "county": story.get(
                "county",
                ""
            ),

            "category": get_category(
                story
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
            )
        },

        "sections": sections,

        "narration": narration,

        "word_count": word_count(
            narration
        )
    }

    with open(
        SCRIPT_FILE,
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
# QUALITY CONTROL
# ============================================================

def quality_check(
    story,
    sections,
    narration
):

    words = word_count(
        narration
    )

    print(
        f"      Word count: {words}"
    )

    # --------------------------------------------------------
    # Length.
    # --------------------------------------------------------

    if words < MIN_WORDS:

        print(
            f"[ERROR] Script is too short. "
            f"Minimum is {MIN_WORDS} words."
        )

        return False

    if words > MAX_WORDS:

        print(
            f"[ERROR] Script exceeds maximum "
            f"of {MAX_WORDS} words."
        )

        return False

    # --------------------------------------------------------
    # Required sections.
    # --------------------------------------------------------

    required = [
        "hook",
        "what_happened",
        "key_facts",
        "why_it_matters",
        "impact",
        "close"
    ]

    for section in required:

        if not clean_text(
            sections.get(
                section,
                ""
            )
        ):

            print(
                f"[ERROR] Missing section: {section}"
            )

            return False

    # --------------------------------------------------------
    # No obvious broken ending.
    # --------------------------------------------------------

    stripped = narration.rstrip()

    if stripped and stripped[-1] not in ".!?":

        print(
            "[ERROR] Narration does not end "
            "with complete punctuation."
        )

        return False

    # --------------------------------------------------------
    # No obvious scraped webpage noise.
    # --------------------------------------------------------

    forbidden_phrases = [
        "click here",
        "read more",
        "cookie policy",
        "privacy policy",
        "subscribe now",
        "terms and conditions"
    ]

    lowered = narration.lower()

    for phrase in forbidden_phrases:

        if phrase in lowered:

            print(
                f"[ERROR] Webpage noise detected: "
                f"{phrase}"
            )

            return False

    # --------------------------------------------------------
    # No empty source.
    # --------------------------------------------------------

    if not clean_text(
        story.get(
            "source",
            ""
        )
    ):

        print(
            "[ERROR] Source is missing."
        )

        return False

    print(
        "      QC PASSED"
    )

    return True


# ============================================================
# MAIN
# ============================================================

def main():

    print()
    print("=" * 60)
    print("RIFT VALLEY WATCH V2.0")
    print("PROFESSIONAL SCRIPT ENGINE")
    print("=" * 60)

    print()
    print(
        "Primary-source newsroom script generation."
    )

    print(
        "Complete-sentence protection enabled."
    )

    print(
        "Development-story correction enabled."
    )

    # --------------------------------------------------------
    # STEP 1
    # --------------------------------------------------------

    print()
    print(
        "[1/4] Loading selected story..."
    )

    story = load_story()

    if not story:
        return

    print(
        f"      Story: "
        f"{story.get('title', '')}"
    )

    print(
        f"      County: "
        f"{story.get('county', '')}"
    )

    print(
        f"      Original category: "
        f"{story.get('category', '')}"
    )

    print(
        f"      Final category: "
        f"{get_category(story)}"
    )

    # --------------------------------------------------------
    # STEP 2
    # --------------------------------------------------------

    print()
    print(
        "[2/4] Building professional script..."
    )

    sections, narration = build_script(
        story
    )

    # --------------------------------------------------------
    # STEP 3
    # --------------------------------------------------------

    print()
    print(
        "[3/4] Quality check..."
    )

    passed = quality_check(
        story,
        sections,
        narration
    )

    if not passed:

        print()
        print(
            "SCRIPT ENGINE STOPPED."
        )

        return

    # --------------------------------------------------------
    # STEP 4
    # --------------------------------------------------------

    print()
    print(
        "[4/4] Saving script..."
    )

    save_script(
        story,
        sections,
        narration
    )

    print()
    print("-" * 60)
    print("SCRIPT PREVIEW")
    print("-" * 60)
    print()
    print(narration)
    print()
    print("-" * 60)

    print(
        f"[SAVED] {SCRIPT_FILE}"
    )

    print()
    print(
        "RIFT VALLEY WATCH SCRIPT ENGINE COMPLETE."
    )


if __name__ == "__main__":
    main()
```
