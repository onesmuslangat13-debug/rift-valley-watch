# ============================================================
# RIFT VALLEY WATCH V1.0
# PROFESSIONAL SCRIPT ENGINE
#
# STORY
#   ↓
# PROFESSIONAL NEWS SCRIPT
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


def clean_text(text):
    if not text:
        return ""

    text = re.sub(r"\s+", " ", str(text))
    return text.strip()


def word_count(text):
    return len(text.split())


def trim_words(text, maximum):
    words = text.split()

    if len(words) <= maximum:
        return text

    return " ".join(words[:maximum]).rstrip(" ,.;:") + "."


def load_story():

    if not STORY_FILE.exists():
        print("[ERROR] data/story.json was not found.")
        return None

    try:
        with open(
            STORY_FILE,
            "r",
            encoding="utf-8"
        ) as f:
            return json.load(f)

    except Exception as e:
        print(f"[ERROR] Could not read story.json: {e}")
        return None


def generate_hook(story):

    title = clean_text(
        story.get("title", "")
    )

    county = clean_text(
        story.get("county", "")
    )

    category = clean_text(
        story.get("category", "")
    )

    if category == "BREAKING NEWS":
        return (
            f"Breaking news from {county}: "
            f"{title}."
        )

    if category == "POLITICS":

        location = county if county else "the region"

        return (
            f"Political developments in {location} are drawing "
            f"attention after {title.lower()}."
        )

    if category == "ACCOUNTABILITY":
        location = county if county else "the region"

        return (
            f"A major accountability question is emerging "
            f"in {location}: {title.lower()}."
        )

    if category == "AGRICULTURE":
        location = county if county else "the region"

        return (
            f"Farmers in {location} are at the centre of "
            f"a new development: {title.lower()}."
        )

    if category == "HEALTH":
        location = county if county else "the region"

        return (
            f"A new health development in {location} "
            f"could affect local residents: "
            f"{title.lower()}."
        )

    if category == "EDUCATION":
        location = county if county else "the region"

        return (
            f"Education is taking centre stage in {location} "
            f"after {title.lower()}."
        )

    if category == "BUSINESS":
        location = county if county else "the region"

        return (
            f"Business activity in {location} is getting "
            f"attention after {title.lower()}."
        )

    if category == "DEVELOPMENT":
        location = county if county else "the region"

        return (
            f"A major development story is emerging "
            f"from {location}: {title.lower()}."
        )

    if category == "SECURITY":
        location = county if county else "the region"

        return (
            f"A security development in {location} "
            f"is drawing attention after "
            f"{title.lower()}."
        )

    if category == "COMMUNITY":
        location = county if county else "the region"

        return (
            f"A community story from {location} "
            f"is drawing attention: {title.lower()}."
        )

    if category == "TOURISM":
        location = county if county else "the region"

        return (
            f"Tourism is getting attention in {location} "
            f"after {title.lower()}."
        )

    location = county if county else "the region"

    return (
        f"Here is the latest development from {location}: "
        f"{title}."
    )


def generate_what_happened(story):

    title = clean_text(
        story.get("title", "")
    )

    summary = clean_text(
        story.get("summary", "")
    )

    county = clean_text(
        story.get("county", "")
    )

    source = clean_text(
        story.get("source", "")
    )

    if summary:
        return (
            f"{title}. "
            f"The {source} reports that "
            f"{summary}"
        )

    return (
        f"{title}. "
        f"The development was reported by "
        f"{source} in {county} County."
    )


def generate_key_facts(story):

    summary = clean_text(
        story.get("summary", "")
    )

    if not summary:
        return (
            "The available official-source information "
            "is currently limited, so further details "
            "should be confirmed before publication."
        )

    sentences = re.split(
        r"(?<=[.!?])\s+",
        summary
    )

    facts = []

    for sentence in sentences:

        sentence = clean_text(sentence)

        if len(sentence) < 20:
            continue

        facts.append(sentence)

        if len(facts) >= 2:
            break

    if not facts:
        return summary

    return " ".join(facts)


def generate_why_it_matters(story):

    category = clean_text(
        story.get("category", "")
    )

    county = clean_text(
        story.get("county", "")
    )

    location = county if county else "the region"

    if category == "AGRICULTURE":
        return (
            f"The development matters because agriculture "
            f"is an important part of livelihoods in "
            f"{location}, and changes in farming practices "
            f"can affect household incomes, food security "
            f"and local markets."
        )

    if category == "HEALTH":
        return (
            f"The development matters because health "
            f"services directly affect residents across "
            f"{location}, particularly access, quality and "
            f"availability of care."
        )

    if category == "EDUCATION":
        return (
            f"The development matters because education "
            f"investment can affect students, teachers "
            f"and long-term opportunities across "
            f"{location}."
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
            f"projects can affect services, infrastructure "
            f"and economic activity across {location}."
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
        f"The development matters because it could have "
        f"an impact on residents and communities in "
        f"{location}."
    )


def generate_impact(story):

    category = clean_text(
        story.get("category", "")
    )

    county = clean_text(
        story.get("county", "")
    )

    location = county if county else "the region"

    if category == "AGRICULTURE":
        return (
            f"For farmers and households in {location}, "
            f"the key question will be whether the "
            f"development produces measurable benefits "
            f"over time."
        )

    if category == "DEVELOPMENT":
        return (
            f"For residents of {location}, the real test "
            f"will be whether the project translates "
            f"into reliable services and practical benefits."
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
            f"For residents of {location}, the impact will "
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
        f"For residents of {location}, the significance "
        f"will depend on what happens next and whether "
        f"the reported development produces tangible results."
    )


def generate_close(story):

    county = clean_text(
        story.get("county", "")
    )

    location = county if county else "the region"

    return (
        f"Rift Valley Watch will continue tracking "
        f"developments across {location} and the wider "
        f"Rift Valley. Follow for verified regional news, "
        f"accountability and developments."
    )


def build_script(story):

    hook = generate_hook(story)

    what_happened = generate_what_happened(
        story
    )

    key_facts = generate_key_facts(
        story
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
        "close": close,
    }

    narration = " ".join(
        sections.values()
    )

    narration = clean_text(narration)

    narration = trim_words(
        narration,
        MAX_WORDS
    )

    return sections, narration


def save_script(story, sections, narration):

    SCRIPT_FILE.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    output = {
        "page": "Rift Valley Watch",

        "status": "ready",

        "story": {
            "title": story.get("title", ""),
            "county": story.get("county", ""),
            "category": story.get("category", ""),
            "source": story.get("source", ""),
            "url": story.get("url", ""),
        },

        "sections": sections,

        "narration": narration,

        "word_count": word_count(
            narration
        ),
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


def main():

    print()
    print("=" * 60)
    print("RIFT VALLEY WATCH V1.0")
    print("PROFESSIONAL SCRIPT ENGINE")
    print("=" * 60)

    print()
    print("[1/4] Loading selected story...")

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
        f"      Category: "
        f"{story.get('category', '')}"
    )

    print()
    print("[2/4] Building professional script...")

    sections, narration = build_script(
        story
    )

    print(
        f"      Word count: "
        f"{word_count(narration)}"
    )

    print()
    print("[3/4] Quality check...")

    words = word_count(narration)

    if words < 40:
        print(
            "[ERROR] Script is too short."
        )
        return

    if words > MAX_WORDS:
        print(
            "[ERROR] Script exceeds maximum "
            f"of {MAX_WORDS} words."
        )
        return

    if not sections["hook"]:
        print("[ERROR] Missing hook.")
        return

    if not sections["what_happened"]:
        print("[ERROR] Missing main story.")
        return

    if not sections["close"]:
        print("[ERROR] Missing close.")
        return

    print("      QC PASSED")

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
