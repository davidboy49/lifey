# Proposal: a learning thread for Lifey

Status: draft for the owner. Nothing here is built. Written 2026-10-15 against `/opt/lifey` at commit `9135c01`.

## 1. The idea in one paragraph

Lifey already answers "how is my body trending and what has helped". It does not yet answer
"what am I getting better at". This proposal adds one small, continuous thread: **at any time there is exactly one thing you are
learning, with one outcome you can check, reviewed weekly and renewed monthly.** The weekly part
costs about three minutes inside the review you already do on Sunday. The monthly part is a
short renew-or-switch decision on the first Monday of the month.

The point is that there is always something to move toward, and Lifey can show, from its own
data, whether the practice is happening and what it sits next to (sleep, training, mood).

## 2. How it works

### Monthly: the focus (first Monday)

One screen, four fields:

| Field | Example | Rule |
|---|---|---|
| Focus | "Time-series cross-validation" | One focus at a time. A second needs the first closed or paused. |
| Outcome | "By 8 Nov I can explain expanding-window CV and run it on my own sleep data." | Must be checkable by you. Lifey does not grade it. |
| Practice slot | "If it is 20:00 on Tue/Thu, then I open the notebook for 30 minutes." | Same if-then shape the review already uses. |
| Why now | One sentence. | Optional. |

At month end: **met / partly / not met**, then one of **continue / switch / pause**. A
"not met" is information, not a failure state. The month is closed either way.

### Weekly: three questions in the Sunday review

The review already has "what went well / what got in the way / what did you learn about
yourself". The learning block sits under it, separate from the self-insight box (the old
`learned` field stays as it is):

1. **Practised:** sessions and minutes. Taken from the journal, not typed again (see 3).
2. **Recall, without looking:** "Explain the one idea from this week in two sentences." Written
   first, checked afterwards. This is the retrieval step.
3. **Next week's slot:** keep or change the practice if-then.

A week with no learning entries is shown as unknown, not zero, matching the rest of Lifey.

### Evidence shelf (the "find me studies" part)

Each focus gets an optional shelf of 2 to 5 studies on how to learn that kind of thing better.
Each card has: citation, DOI or link, the one finding in a sentence, the date it was
retrieved, and a label "research, not advice". Details and the privacy rule are in section 5.

## 3. Fit with what exists (no rewrite)

| Need | Reuse | New |
|---|---|---|
| Log a study session | Custom habit with a minutes unit (`journal/habits.py`) | Nothing. Create a "Study" habit. |
| Weekly questions | `journal.weekly_reviews` + `ReviewReflection.tsx` | Two columns: `recall`, `learn_note` (migration 0013) |
| Monthly focus | None | `journal.learning_focus` (month, topic, outcome, if/then, status, closed_at) |
| "Did the week meet it" | Weekly quests (`journal/quests.py`) | One new kind `learning_sessions`, scored on read like the others |
| Sleep association | `review.pattern_candidates` | Reuse as is, with the same 8-nights-per-group threshold |
| Nudge | Sunday 19:00 review nudge | One extra line in that message. No new reminder. |
| Ask Claude about it | Claude connector tools (`connector/tools.py`) | One read tool: `lifey_learning` |

Migration number is 0013 (latest applied is 0012).

## 4. The evidence

I looked each of these up. For several I could read only the abstract or secondary summaries,
not the full paper, so treat the numbers as "reported", and check before quoting them anywhere
public. Where the research is weaker than its reputation, I say so.

| Design choice | Supporting study | What it found | Caveat |
|---|---|---|---|
| If-then practice slot | [Gollwitzer & Sheeran 2006](https://stafforini.com/works/gollwitzer-2006-implementation-intentions-and/) meta-analysis, 94 tests | Implementation intentions help goal attainment, d ≈ 0.65 | Figure confirmed only through secondary sources. Later work has revisited the size. |
| Weekly progress check | [Harkin et al. 2016](https://eprints.whiterose.ac.uk/id/eprint/91437/), *Psychological Bulletin*, 138 studies, N = 19,951 | Interventions that raise how often people monitor progress improve attainment, d+ = 0.40. Larger when progress is physically recorded. | Mostly health goals, not study goals. Effect is moderate, not large. |
| Written reflection / recall at the end | [Di Stefano, Gino, Pisano & Staats 2014](https://www.library.hbs.edu/working-knowledge/reflecting-on-work-improves-job-performance), HBS working paper | Call-centre trainees who spent 15 minutes reflecting scored about 23% higher on the final test | One field setting plus lab studies; a working paper. Promising, not settled. |
| Recall before checking | [Dunlosky et al. 2013](https://stafforini.com/works/dunlosky-2013-improving-students-learning/), review of 10 techniques | Practice testing and distributed practice rated highest utility; rereading and highlighting low | Review of mostly student samples. |
| Spread practice over days, not one block | [Cepeda et al. 2006](https://pubmed.ncbi.nlm.nih.gov/16719566/), 317 experiments | Spacing helps recall; the best gap grows with how long you need to remember | Verbal recall tasks, not complex skills. |
| Monthly renew on a landmark | [Dai, Milkman & Riis 2014](https://faculty.wharton.upenn.edu/wp-content/uploads/2014/06/Dai_Fresh_Start_2014_Mgmt_Sci.pdf), *Management Science* | Goal-directed behaviour rises after temporal landmarks (new month, Monday) | Archival studies of searches and gym visits, not learning. |
| One specific outcome with feedback | [Locke & Latham 2002](https://goal-lab.psych.umn.edu/orgpsych/2020/readings/5.%20Motivation/Locke%20&%20Latham%20(2002).pdf), 35-year review | Specific, difficult goals with feedback beat "do your best" | Mostly work tasks. I confirmed the framing, not the exact statistics. |
| Do not promise a 21-day habit | [Lally et al. 2010](https://openresearch.surrey.ac.uk/esploro/outputs/99783513802346) | Median 66 days to plateau in automaticity, range 18 to 254. One missed day did not materially matter. | 96 volunteers, 39 good fits, self-report. Not replicated. The "21 days" claim is unfounded. |
| Look at sleep next to learning | [Diekelmann & Born 2010](https://www.nature.com/articles/nrn2762), *Nature Reviews Neuroscience* | Sleep supports memory consolidation | I could not retrieve the contents, only the citation. Used for plausibility only. |

**What this does and does not claim.** The studies support the structure (one specific goal,
an if-then slot, regular monitoring, recall, a monthly restart). They do not show this app
will make you learn faster. For one person, Lifey can only report associations, with the
same 8-nights rule as the existing patterns.

## 5. "Find me studies": three options

| Option | How | Cost / risk |
|---|---|---|
| **A. On demand through the Claude connector (recommended)** | You ask Claude about the current focus. It reads `lifey_learning` (topic and outcome only), searches the web, and returns citations. You decide which to pin to the shelf. | No new job, no new outbound traffic from the VPS. Fits the owner-in-the-loop style of CLAUDE.md. |
| B. Monthly job on the VPS | A one-shot container queries a scholarly API for the focus topic and stores links. | New outbound call and a new thing to keep alive on 2 GB RAM. Search quality for niche topics is poor without a model. |
| C. Curated starter shelf | The table in section 4, shown once, never updated. | Zero cost, goes stale. |

Recommendation: **A, with C as the first shelf.** A study is only stored with a link and a
retrieved date, and Lifey never writes a finding from model memory (same rule as numbers in
messages).

**Privacy.** Only the focus name and outcome leave the app via the connector. Recall text,
journal notes and anything health-related are never included. DeepSeek is not involved.

## 6. What it should not do

- No streaks, points or badges. A missed week is unknown or "not practised", not a reset.
- No second reminder. The Sunday nudge gains one line.
- No generic study tips in the morning briefing. Studies sit on the shelf, labelled as
  research, and the briefing keeps its "<= 3 lines + one action" rule.
- No grading of the recall answer by an LLM.
- No claim that learning caused any sleep or HRV change.

## 7. Success check after 8 weeks

These are for you to judge, not for Lifey to optimise:

- The learning block was filled in on at least 6 of 8 Sundays.
- At least one monthly outcome was closed as met or partly met.
- You can name what you can do now that you could not 8 weeks ago.
- The review still takes under 10 minutes. If it grew, remove the recall question first.

## 8. Decisions needed from you

1. **Timing.** CLAUDE.md says no new features until the current version has run 30 consecutive
   days. The last merge was the quests/comeback/"on this day" feature (2026-10-13). Options:
   wait for the window, or log an explicit override in the decisions log.
2. **Scope of "learning".** Skills and topics (this proposal), or only life lessons (the
   existing `learned` box covers that already).
3. **Shelf source.** A, B or C above.
4. **Cadence.** Weekly check with monthly renew (proposed), or monthly only.
5. **Evidence in the briefing.** The no-generic-advice rule is about the coach voice. Confirm
   that a research shelf, labelled as such and kept out of the briefing, is acceptable.

## 9. Build order if approved (one step at a time, confirm between)

1. Migration 0013 and API: focus CRUD, review columns, `learning_sessions` quest kind. Tests
   against real Postgres, including "no entries is unknown".
2. Web: monthly focus screen and the learning block in the review.
3. Connector tool `lifey_learning` (read-only) and the shelf.
4. Eight-week check.
