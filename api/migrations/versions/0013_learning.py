"""Learning thread: monthly focus, evidence shelf, weekly recall

Revision ID: 0013
Revises: 0012
"""
from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None

SQL = """
-- One thing being learned at a time. A month's focus has an outcome the person can check; Lifey
-- never grades it. Sessions are not stored here: they are the journal entries of `habit_tag`.
CREATE TABLE journal.learning_focus (
    id          BIGSERIAL PRIMARY KEY,
    month       DATE NOT NULL CHECK (EXTRACT(DAY FROM month) = 1),
    topic       TEXT NOT NULL CHECK (length(topic) BETWEEN 1 AND 80),
    topic_key   TEXT NOT NULL CHECK (length(topic_key) BETWEEN 1 AND 80),
    category    TEXT NOT NULL CHECK (category IN ('tech', 'life', 'sport', 'money', 'investing', 'other')),
    outcome     TEXT NOT NULL CHECK (length(outcome) BETWEEN 1 AND 240),
    plan_if     TEXT NOT NULL DEFAULT '' CHECK (length(plan_if) <= 200),
    plan_then   TEXT NOT NULL DEFAULT '' CHECK (length(plan_then) <= 200),
    why         TEXT NOT NULL DEFAULT '' CHECK (length(why) <= 200),
    habit_tag   TEXT NOT NULL CHECK (habit_tag ~ '^[a-z0-9_]{1,48}$'),
    status      TEXT NOT NULL DEFAULT 'active' CHECK (status IN ('active', 'closed')),
    result      TEXT CHECK (result IN ('met', 'partly', 'not_met')),
    next_step   TEXT CHECK (next_step IN ('continue', 'switch', 'pause')),
    closed_at   TIMESTAMPTZ,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    updated_at  TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    CHECK ((status = 'active' AND result IS NULL AND closed_at IS NULL)
        OR (status = 'closed' AND result IS NOT NULL AND closed_at IS NOT NULL))
);
-- At most one active focus.
CREATE UNIQUE INDEX learning_one_active ON journal.learning_focus ((TRUE)) WHERE status = 'active';

-- Studies the person chose to keep for a topic. A study is stored with its link and the date it was
-- retrieved; Lifey never writes a finding from memory.
CREATE TABLE journal.learning_studies (
    id            BIGSERIAL PRIMARY KEY,
    topic_key     TEXT NOT NULL CHECK (length(topic_key) BETWEEN 1 AND 80),
    citation      TEXT NOT NULL CHECK (length(citation) BETWEEN 1 AND 300),
    url           TEXT NOT NULL CHECK (url ~ '^https?://' AND length(url) <= 500),
    finding       TEXT NOT NULL CHECK (length(finding) BETWEEN 1 AND 400),
    retrieved_on  DATE NOT NULL,
    created_at    TIMESTAMPTZ NOT NULL DEFAULT NOW(),
    UNIQUE (topic_key, url)
);

-- The weekly learning block of the review: the recall answer and next week's practice slot.
ALTER TABLE journal.weekly_reviews
    ADD COLUMN recall     TEXT NOT NULL DEFAULT '' CHECK (length(recall) <= 4000),
    ADD COLUMN learn_slot TEXT NOT NULL DEFAULT '' CHECK (length(learn_slot) <= 300);

-- A quest can now count learning sessions.
ALTER TABLE journal.quests DROP CONSTRAINT quests_kind_check;
ALTER TABLE journal.quests ADD CONSTRAINT quests_kind_check
    CHECK (kind IN ('habit_free', 'sleep_hours', 'bed_before', 'training', 'learning_sessions'));
"""

DOWN = """
DELETE FROM journal.quests WHERE kind = 'learning_sessions';
ALTER TABLE journal.quests DROP CONSTRAINT quests_kind_check;
ALTER TABLE journal.quests ADD CONSTRAINT quests_kind_check
    CHECK (kind IN ('habit_free', 'sleep_hours', 'bed_before', 'training'));
ALTER TABLE journal.weekly_reviews DROP COLUMN recall, DROP COLUMN learn_slot;
DROP TABLE journal.learning_studies;
DROP TABLE journal.learning_focus;
"""


def upgrade() -> None:
    op.execute(SQL)


def downgrade() -> None:
    op.execute(DOWN)
