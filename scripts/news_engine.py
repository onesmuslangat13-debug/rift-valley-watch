import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

STORY_FILE = ROOT / "data" / "story.json"
SCRIPT_FILE = ROOT / "data" / "script.json"

MIN_WORDS = 70
MAX_WORDS = 170


def clean_text(value):
    if value is None:
        return ""

    text = str(value)
    text = text.replace("\xa0", " ")
    text = re.sub(r"\s+", " ", text)

    return text.strip()


def word_count(text):
    return len(clean_text(text).split())


def split_sentences(text):
    text = clean_text(text)

    if not text:
        return []

    return [
        clean_text(x)
        for x in re.split(r"(?<=[.!?])\s+", text)
        if clean_text(x)
    ]


def load_story():
    if not STORY_FILE.exists():
        print("[ERROR] data/story.json not found.")
        return None

    try:
        with open(STORY_FILE, "r", encoding="utf-8") as file:
            story = json.load(file)

        if not isinstance(story, dict):
            print("[ERROR] story.json must contain an object.")
            return None

        return story

    except Exception as error:
        print(f"[ERROR] Could not load story.json: {error}")
        return None


def get_county(story):
    county = clean_text(story.get("county"))

    if county:
        return county

    return "the Rift Valley region"


def get_category(story):
    category = clean_text(story.get("category")).upper()

    if category:
        return category

    return "REGIONAL NEWS"


def get_title(story):
    title = clean_text(story.get("title"))

    if title:
        return title

    return "A new development is drawing attention in the Rift Valley"


def get_source(story):
    source = clean_text(story.get("source"))

    if source:
        return source

    return "the reported source"


def clean_summary(summary, title):
    summary = clean_text(summary)
    title = clean_text(title)

    if not summary:
        return ""

    if title and summary.lower().startswith(title.lower()):
        summary = summary[len(title):].strip(" .:-")

    unwanted = [
        r"^read more\s*",
        r"^share this\s*",
        r"^subscribe\s*",
        r"^home\s*",
    ]

    for pattern in unwanted:
        summary = re.sub(
            pattern,
            "",
            summary,
            flags=re.IGNORECASE
        )

    return clean_text(summary)


def extract_facts(summary):
    facts = []

    blocked = [
        "read more",
        "click here",
        "subscribe",
        "cookie policy",
        "privacy policy",
        "terms and conditions",
    ]

    for sentence in split_sentences(summary):

        if word_count(sentence) < 6:
            continue

        lowered = sentence.lower()

        if any(word in lowered for word in blocked):
            continue

        if sentence not in facts:
            facts.append(sentence)

        if len(facts) == 4:
            break

    return facts


def make_hook(story):
    title = get_title(story)
    county = get_county(story)
    category = get_category(story)

    if category == "BREAKING NEWS":
        return f"Breaking news from {county}: {title}."

    if category == "DEVELOPMENT":
        return (
            f"A major development is taking shape in "
            f"{county}: {title}."
        )

    if category == "AGRICULTURE":
        return (
            f"Farmers in {county} are watching a new "
            f"development: {title}."
        )

    if category == "HEALTH":
        return (
            f"A health development in {county} is "
            f"drawing attention: {title}."
        )

    if category == "EDUCATION":
        return (
            f"Education is taking centre stage in "
            f"{county}: {title}."
        )

    if category == "BUSINESS":
        return (
            f"Business activity in {county} is getting "
            f"attention: {title}."
        )

    if category == "SECURITY":
        return (
            f"A security development in {county} is "
            f"drawing attention: {title}."
        )

    if category == "POLITICS":
        return (
            f"Political developments in {county} are "
            f"drawing attention after {title.lower()}."
        )

    if category == "ACCOUNTABILITY":
        return (
            f"An accountability issue in {county} is "
            f"drawing attention: {title}."
        )

    return f"Here is the latest development from {county}: {title}."


def make_what_happened(story, facts):
    title = get_title(story)
    source = get_source(story)

    if not facts:
        return (
            f"{title}. The development was reported by "
            f"{source}."
        )

    fact = facts[0]

    if fact.lower() == title.lower() and len(facts) > 1:
        fact = facts[1]

    return (
        f"{title}. According to {source}, {fact}"
    )


def make_key_facts(facts):
    if not facts:
        return (
            "Available information remains limited, and "
            "additional details will be confirmed as they emerge."
        )

    selected = []

    for fact in facts:
        if fact not in selected:
            selected.append(fact)

        if len(selected) == 2:
            break

    return " ".join(selected)


def make_why_it_matters(story):
    county = get_county(story)
    category = get_category(story)

    if category == "DEVELOPMENT":
        return (
            f"The development matters because projects in "
            f"{county} can affect infrastructure, public "
            f"services, jobs and economic activity."
        )

    if category == "AGRICULTURE":
        return (
            f"The issue matters because agriculture supports "
            f"livelihoods, food security and local markets "
            f"across {county}."
        )

    if category == "HEALTH":
        return (
            f"The development matters because health services "
            f"directly affect residents across {county}."
        )

    if category == "EDUCATION":
        return (
            f"The development matters because education "
            f"investment can affect students, teachers and "
            f"future opportunities across {county}."
        )

    if category == "BUSINESS":
        return (
            f"The issue matters because business activity can "
            f"affect jobs, investment, incomes and local revenue."
        )

    if category == "ACCOUNTABILITY":
        return (
            "The issue matters because public resources require "
            "transparency, proper oversight and accountability."
        )

    if category == "SECURITY":
        return (
            f"The development matters because security conditions "
            f"can directly affect residents and businesses in {county}."
        )

    if category == "POLITICS":
        return (
            "The issue matters because political decisions can "
            "influence public policy, priorities and public resources."
        )

    return (
        f"The development matters because it could affect "
        f"residents and communities across {county}."
    )


def make_impact(story):
    county = get_county(story)
    category = get_category(story)

    if category == "DEVELOPMENT":
        return (
            f"For residents of {county}, the real test will be "
            "whether the project is completed as planned and "
            "delivers practical benefits."
        )

    if category == "AGRICULTURE":
        return (
            f"For farmers and households in {county}, the key "
            "question is whether the development produces "
            "measurable benefits over time."
        )

    if category == "BUSINESS":
        return (
            "For businesses and workers, the key question is "
            "whether the development creates sustainable "
            "economic opportunities."
        )

    if category == "ACCOUNTABILITY":
        return (
            "For taxpayers, the focus should remain on the "
            "available evidence and how public resources are managed."
        )

    return (
        f"For residents of {county}, the significance will "
        "depend on what happens next and whether the reported "
        "development produces tangible results."
    )


def make_close(story):
    county = get_county(story)

    return (
        f"Rift Valley Watch will continue tracking developments "
        f"across {county} and the wider Rift Valley. Follow for "
        "verified regional news, accountability and development."
    )


def build_script(story):

    title = get_title(story)

    summary = clean_summary(
        story.get("summary", ""),
        title
    )

    facts = extract_facts(summary)

    sections = {
        "hook": make_hook(story),
        "what_happened": make_what_happened(story, facts),
        "key_facts": make_key_facts(facts),
        "why_it_matters": make_why_it_matters(story),
        "impact": make_impact(story),
        "close": make_close(story),
    }

    narration = " ".join(sections.values())
    narration = clean_text(narration)

    sentences = split_sentences(narration)

    unique = []
    seen = set()

    for sentence in sentences:
        key = sentence.lower()

        if key not in seen:
            seen.add(key)
            unique.append(sentence)

    narration = " ".join(unique)

    return sections, narration


def trim_script(text, maximum):
    sentences = split_sentences(text)

    result = []
    count = 0

    for sentence in sentences:
        words = word_count(sentence)

        if count + words > maximum:
            break

        result.append(sentence)
        count += words

    return " ".join(result)


def quality_check(story, sections, narration):

    words = word_count(narration)

    print(f"      Word count: {words}")

    if words < MIN_WORDS:
        print(f"[ERROR] Script too short: minimum {MIN_WORDS} words.")
        return False

    if words > MAX_WORDS:
        print(f"[ERROR] Script too long: maximum {MAX_WORDS} words.")
        return False

    required = [
        "hook",
        "what_happened",
        "key_facts",
        "why_it_matters",
        "impact",
        "close",
    ]

    for name in required:
        if not clean_text(sections.get(name)):
            print(f"[ERROR] Missing section: {name}")
            return False

    if not clean_text(story.get("source")):
        print("[ERROR] Story source is missing.")
        return False

    if narration.rstrip()[-1:] not in ".!?":
        print("[ERROR] Narration has incomplete ending.")
        return False

    forbidden = [
        "click here",
        "read more",
        "cookie policy",
        "privacy policy",
        "terms and conditions",
    ]

    lowered = narration.lower()

    for phrase in forbidden:
        if phrase in lowered:
            print(f"[ERROR] Webpage noise detected: {phrase}")
            return False

    print("      QC PASSED")
    return True


def save_script(story, sections, narration):

    SCRIPT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    output = {
        "page": "Rift Valley Watch",
        "status": "ready",

        "story": {
            "title": clean_text(story.get("title")),
            "county": clean_text(story.get("county")),
            "category": get_category(story),
            "source": clean_text(story.get("source")),
            "url": clean_text(story.get("url")),
            "date": clean_text(story.get("date")),
        },

        "sections": sections,

        "narration": narration,

        "word_count": word_count(narration),
    }

    with open(
        SCRIPT_FILE,
        "w",
        encoding="utf-8"
    ) as file:

        json.dump(
            output,
            file,
            indent=2,
            ensure_ascii=False
        )


def main():

    print()
    print("=" * 60)
    print("RIFT VALLEY WATCH")
    print("NEWS SCRIPT ENGINE V1.0")
    print("=" * 60)

    print()
    print("[1/4] Loading story...")

    story = load_story()

    if not story:
        return

    print(
        f"      Story: {get_title(story)}"
    )

    print(
        f"      County: {get_county(story)}"
    )

    print(
        f"      Category: {get_category(story)}"
    )

    print()
    print("[2/4] Building script...")

    sections, narration = build_script(story)

    if word_count(narration) > MAX_WORDS:
        narration = trim_script(
            narration,
            MAX_WORDS
        )

    print()
    print("[3/4] Quality control...")

    if not quality_check(
        story,
        sections,
        narration
    ):
        print()
        print("SCRIPT ENGINE STOPPED.")
        return

    print()
    print("[4/4] Saving script...")

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
    print("RIFT VALLEY WATCH SCRIPT ENGINE COMPLETE.")


if __name__ == "__main__":
    main()
