"""The learning thread: one focus at a time, checked weekly, renewed monthly.

Rules, the same ones the rest of Lifey follows:
- Sessions are not stored here. They are the journal entries of the focus's habit (minutes), so a
  corrected entry corrects every number.
- A day with no entries is unknown. A week with none shows "no entries", never a zero.
- Lifey never grades the outcome or the recall answer. The person closes the month.
- Only the topic and outcome ever leave the app (the Claude connector). Notes and recall stay here.
"""
from __future__ import annotations

from datetime import date, timedelta

from . import entries as e
from . import repo

CATEGORIES = ("tech", "life", "sport", "money", "investing", "other")
RESULTS = ("met", "partly", "not_met")
NEXT_STEPS = ("continue", "switch", "pause")

HABIT_TAG = "learning"          # the custom habit sessions are logged under
HABIT_LABEL = "Learning"
HABIT_UNIT = "minutes"

# Research that backs the design, shown on the shelf for every focus. Figures are as reported by the
# sources named; each caveat says where the evidence is thinner than its reputation.
STARTER_SHELF = [
    {"id": "gollwitzer-2006", "citation": "Gollwitzer & Sheeran (2006), Advances in Experimental Social Psychology",
     "url": "https://stafforini.com/works/gollwitzer-2006-implementation-intentions-and/",
     "finding": "If-then plans help goal attainment across 94 tests (d about 0.65).",
     "caveat": "Figure confirmed through secondary sources; later work has revisited the size.",
     "used_for": "The practice slot"},
    {"id": "harkin-2016", "citation": "Harkin et al. (2016), Psychological Bulletin",
     "url": "https://eprints.whiterose.ac.uk/id/eprint/91437/",
     "finding": "Checking progress more often improves goal attainment (d+ 0.40, 138 studies); larger when progress is recorded.",
     "caveat": "Mostly health goals. A moderate effect.",
     "used_for": "The weekly check"},
    {"id": "di-stefano-2014", "citation": "Di Stefano, Gino, Pisano & Staats (2014), HBS working paper 14-093",
     "url": "https://www.library.hbs.edu/working-knowledge/reflecting-on-work-improves-job-performance",
     "finding": "Trainees who reflected for 15 minutes a day scored about 23% higher on the final test.",
     "caveat": "One field setting plus lab studies, and a working paper. Promising, not settled.",
     "used_for": "Writing the recall"},
    {"id": "dunlosky-2013", "citation": "Dunlosky et al. (2013), Psychological Science in the Public Interest",
     "url": "https://stafforini.com/works/dunlosky-2013-improving-students-learning/",
     "finding": "Practice testing and spacing rated highest-utility of ten techniques; rereading and highlighting low.",
     "caveat": "Mostly student samples.",
     "used_for": "Recall before checking"},
    {"id": "cepeda-2006", "citation": "Cepeda et al. (2006), Psychological Bulletin",
     "url": "https://pubmed.ncbi.nlm.nih.gov/16719566/",
     "finding": "Spreading practice over days beats one block; the best gap grows with how long you need to remember.",
     "caveat": "Verbal recall tasks, not complex skills.",
     "used_for": "Spaced practice slots"},
    {"id": "dai-2014", "citation": "Dai, Milkman & Riis (2014), Management Science",
     "url": "https://faculty.wharton.upenn.edu/wp-content/uploads/2014/06/Dai_Fresh_Start_2014_Mgmt_Sci.pdf",
     "finding": "Goal-directed behaviour rises after temporal landmarks such as a new month or a Monday.",
     "caveat": "Archival studies of searches and gym visits, not learning.",
     "used_for": "The monthly renewal"},
    {"id": "locke-latham-2002", "citation": "Locke & Latham (2002), American Psychologist",
     "url": "https://goal-lab.psych.umn.edu/orgpsych/2020/readings/5.%20Motivation/Locke%20&%20Latham%20(2002).pdf",
     "finding": "Specific, difficult goals with feedback beat 'do your best'.",
     "caveat": "Mostly work tasks.",
     "used_for": "One checkable outcome"},
    {"id": "lally-2010", "citation": "Lally et al. (2010), European Journal of Social Psychology",
     "url": "https://openresearch.surrey.ac.uk/esploro/outputs/99783513802346",
     "finding": "Median 66 days for a daily behaviour to plateau in automaticity (range 18 to 254); one missed day did not matter much.",
     "caveat": "96 volunteers, self-report, not replicated. The '21 days' claim has no basis.",
     "used_for": "No streaks"},
]


def month_start(day: date) -> date:
    return day.replace(day=1)


def topic_key(topic: str) -> str:
    return " ".join(topic.lower().split())


def _clean(value, limit: int, name: str, *, required: bool = False) -> str:
    text = " ".join(str(value or "").split())
    if required and not text:
        raise ValueError(f"{name} is required.")
    if len(text) > limit:
        raise ValueError(f"{name} is at most {limit} characters.")
    return text


def validate_focus(body: dict, *, partial: bool = False) -> dict:
    """Clean the fields of a focus or raise ValueError with a message that is safe to show."""
    out: dict = {}
    spec = (("topic", 80, "The topic", True), ("outcome", 240, "The outcome", True),
            ("plan_if", 200, "The 'if'", False), ("plan_then", 200, "The 'then'", False),
            ("why", 200, "The reason", False))
    for key, limit, name, required in spec:
        if partial and key not in body:
            continue
        out[key] = _clean(body.get(key), limit, name, required=required)
    if not partial or "category" in body:
        category = str(body.get("category") or "")
        if category not in CATEGORIES:
            raise ValueError("Pick a category.")
        out["category"] = category
    if "topic" in out:
        out["topic_key"] = topic_key(out["topic"])
    return out


def validate_study(citation: str, url: str, finding: str) -> dict:
    """A study as the owner or the connector supplied it: text as given, link must be http(s)."""
    link = str(url or "").strip()
    if not link.lower().startswith(("http://", "https://")) or len(link) > 500 or any(c.isspace() for c in link):
        raise ValueError("The link must be a web address starting with http:// or https://")
    return {"citation": _clean(citation, 300, "The citation", required=True), "url": link,
            "finding": _clean(finding, 400, "The finding", required=True)}


def ensure_habit() -> str:
    """The habit sessions are logged under, created (or un-archived) on first use."""
    repo.create_habit(HABIT_TAG, HABIT_LABEL, HABIT_UNIT, None, None)
    repo.update_habit(HABIT_TAG, {"archived": False})
    return HABIT_TAG


def renewal(active: dict | None, today: date) -> str:
    """'set' when nothing is being learned, 'close' when the focus belongs to an earlier month, else 'ok'."""
    if active is None:
        return "set"
    return "close" if date.fromisoformat(str(active["month"])[:10]) < month_start(today) else "ok"


def sessions(logs: list[dict], habit_tag: str, days: list[date]) -> dict:
    """Entries, minutes and days practised for one habit over `days`, plus how many of them are known.

    `unknown_days` are days (up to today) on which nothing at all was logged, so a practice that was not
    written down is not read as a missed one."""
    wanted = set(days)
    logged_days = {e._day(l["date"]) for l in logs}
    count, minutes, practised = 0, 0.0, set()
    for log in logs:
        if e.kind(log) != "habit" or e.habit_tag(log) != habit_tag:
            continue
        day = e._day(log["date"])
        if day not in wanted:
            continue
        number = e._number(log.get("value"))
        count += 1
        minutes += number if number is not None else 0.0
        practised.add(day)
    return {"entries": count, "minutes": round(minutes), "days_practised": len(practised),
            "days": len(days), "unknown_days": sum(1 for d in days if d not in logged_days)}


def overview(today: date, logs_month: list[dict]) -> dict:
    """Everything the learning page needs, from the database and this month's journal entries."""
    active = repo.active_focus()
    key = active["topic_key"] if active else None
    month_days = [month_start(today) + timedelta(days=i) for i in range((today - month_start(today)).days + 1)]
    return {
        "today": today.isoformat(),
        "month": month_start(today).isoformat(),
        "renewal": renewal(active, today),
        "active": active,
        "month_sessions": sessions(logs_month, active["habit_tag"], month_days) if active else None,
        "history": repo.closed_focuses(),
        "shelf": repo.list_studies(key) if key else [],
        "starter": STARTER_SHELF,
        "templates": {"categories": list(CATEGORIES), "habit": {"tag": HABIT_TAG, "label": HABIT_LABEL,
                                                                "unit": HABIT_UNIT}},
    }

