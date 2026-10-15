from __future__ import annotations

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

from sqlalchemy import (
    Column,
    Integer,
    MetaData,
    String,
    Table,
    Text,
    UniqueConstraint,
    create_engine,
    delete,
    func,
    insert,
    select,
    update,
)

metadata = MetaData()
records = Table(
    "records",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("project", String(80), nullable=False, index=True),
    Column("session", String(36), nullable=False, default=""),
    Column("kind", String(32), nullable=False),
    Column("content", Text, nullable=False),
    Column("created", String(40), nullable=False),
)

focus_sessions = Table(
    "focus_sessions",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("project", String(80), nullable=False, index=True),
    Column("goal", String(240), nullable=False),
    Column("focus_minutes", Integer, nullable=False),
    Column("break_minutes", Integer, nullable=False),
    Column("status", String(20), nullable=False),
    Column("started", String(40), nullable=False),
    Column("ended", String(40), nullable=False),
    Column("outcome", Text, nullable=False, default=""),
    Column("next_step", Text, nullable=False, default=""),
)

metrics = Table(
    "metrics",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("project", String(80), nullable=False, index=True),
    Column("event", String(40), nullable=False),
    Column("value", String(200), nullable=False, default=""),
    Column("created", String(40), nullable=False),
)

focus_plans = Table(
    "focus_plans",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("project", String(80), nullable=False, index=True),
    Column("goal", String(240), nullable=False),
    Column("steps", Text, nullable=False),
    Column("updated", String(40), nullable=False),
    UniqueConstraint("project", "goal", name="uq_focus_plans_project_goal"),
)

exercises = Table(
    "exercises",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("project", String(80), nullable=False, index=True),
    Column("prompt", Text, nullable=False),
    Column("answer", Text, nullable=False, default=""),
    Column("topic", String(120), nullable=False, default=""),
    Column("created", String(40), nullable=False),
    Column("updated", String(40), nullable=False),
    Column("next_review", String(40), nullable=False),
    Column("interval_days", Integer, nullable=False, default=0),
    Column("ease", String(20), nullable=False, default="2.5"),
    Column("repetitions", Integer, nullable=False, default=0),
    Column("last_rating", Integer, nullable=True),
)


class MemoryStore:
    def __init__(self, path: Path, retention: bool):
        self.retention = retention
        path.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
        self.engine = create_engine(f"sqlite:///{path}", connect_args={"check_same_thread": False})
        # Schema is managed by Alembic. Tests also use the real migration.

    def add(self, project: str, kind: str, content: str, session: str = "") -> int | None:
        if not self.retention:
            return None
        with self.engine.begin() as conn:
            result = conn.execute(
                insert(records).values(
                    project=project,
                    kind=kind,
                    content=content,
                    session=session,
                    created=datetime.now(UTC).isoformat(),
                )
            )
            return result.inserted_primary_key[0]

    def record_metric(self, project: str, event: str, value: str = "") -> None:
        if not self.retention:
            return
        with self.engine.begin() as conn:
            conn.execute(insert(metrics).values(
                project=project, event=event, value=value[:200],
                created=datetime.now(UTC).isoformat(),
            ))

    def metric_summary(self, project: str, days: int = 14) -> dict:
        if not self.retention:
            return {"days": days, "events": {}, "daily": []}
        cutoff = (datetime.now(UTC) - timedelta(days=max(1, min(days, 90)))).isoformat()
        with self.engine.connect() as conn:
            rows = [dict(row) for row in conn.execute(
                select(metrics).where(metrics.c.project == project, metrics.c.created >= cutoff)
                .order_by(metrics.c.id)
            ).mappings()]
        events: dict[str, int] = {}
        latency_values: list[float] = []
        first_token_values: list[float] = []
        daily: dict[str, dict[str, int]] = {}
        for row in rows:
            event = row["event"]
            events[event] = events.get(event, 0) + 1
            if event == "chat_completed":
                try:
                    latency_values.append(float(row["value"]))
                except (TypeError, ValueError):
                    pass
            elif event == "chat_first_token":
                try:
                    first_token_values.append(float(row["value"]))
                except (TypeError, ValueError):
                    pass
            day = row["created"][:10]
            daily.setdefault(day, {})[event] = daily.setdefault(day, {}).get(event, 0) + 1
        summary = {"days": days, "events": events, "daily": [
            {"date": day, **values} for day, values in sorted(daily.items())
        ]}
        if latency_values:
            summary["chat_latency_ms"] = {
                "count": len(latency_values),
                "average": round(sum(latency_values) / len(latency_values)),
                "last": round(latency_values[-1]),
            }
        if first_token_values:
            summary["first_token_latency_ms"] = {
                "count": len(first_token_values),
                "average": round(sum(first_token_values) / len(first_token_values)),
                "last": round(first_token_values[-1]),
            }
        return summary

    def add_turn(self, project: str, session: str, prompt: str, answer: str) -> None:
        if not self.retention:
            return
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as conn:
            conn.execute(
                insert(records),
                [
                    {
                        "project": project,
                        "session": session,
                        "kind": role,
                        "content": content,
                        "created": now,
                    }
                    for role, content in (("user", prompt), ("assistant", answer))
                ],
            )

    def notes(self, project: str) -> list[dict]:
        if not self.retention:
            return []
        with self.engine.connect() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    select(records)
                    .where(
                        records.c.project == project,
                        records.c.kind.in_(["preference", "difficulty", "topic", "result", "decision", "lesson", "focus_outcome"]),
                    )
                    .order_by(records.c.id.desc())
                    .limit(100)
                ).mappings()
            ]

    def list(self, project: str, limit: int = 200, session: str | None = None) -> list[dict]:
        if not self.retention:
            return []
        statement = select(records).where(records.c.project == project)
        if session is not None:
            statement = statement.where(records.c.session == session)
        with self.engine.connect() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    statement.order_by(records.c.id.desc()).limit(limit)
                ).mappings()
            ]

    def search(self, project: str, query: str, limit: int = 20) -> list[dict]:
        if not self.retention:
            return []
        terms = [term.casefold() for term in query.split() if term.strip()]
        if not terms:
            return []
        with self.engine.connect() as conn:
            rows = [
                dict(row)
                for row in conn.execute(
                    select(records).where(
                        records.c.project == project,
                        records.c.kind.in_(["preference", "difficulty", "topic", "result", "decision", "lesson", "focus_outcome"]),
                    )
                ).mappings()
            ]
        ranked = []
        for row in rows:
            content = row["content"].casefold()
            score = sum(content.count(term) for term in terms)
            if score:
                ranked.append((score, row))
        ranked.sort(key=lambda item: (item[0], item[1]["id"]), reverse=True)
        return [row for _, row in ranked[: max(1, min(limit, 100))]]

    def edit(self, project: str, identity: int, kind: str, content: str) -> bool:
        if not self.retention:
            return False
        with self.engine.begin() as conn:
            return bool(
                conn.execute(
                    update(records)
                    .where(records.c.project == project, records.c.id == identity)
                    .values(kind=kind, content=content)
                ).rowcount
            )

    def remove(self, project: str, identity: int | None = None) -> int:
        query = delete(records).where(records.c.project == project)
        if identity is not None:
            query = query.where(records.c.id == identity)
        with self.engine.begin() as conn:
            return conn.execute(query).rowcount

    def export(self, project: str) -> list[dict]:
        if not self.retention:
            return []
        with self.engine.connect() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    select(records).where(records.c.project == project).order_by(records.c.id)
                ).mappings()
            ]

    def record_focus(self, project: str, session: dict) -> int | None:
        if not self.retention:
            return None
        with self.engine.begin() as conn:
            result = conn.execute(
                insert(focus_sessions).values(
                    project=project,
                    goal=session["goal"],
                    focus_minutes=session["focus_minutes"],
                    break_minutes=session["break_minutes"],
                    status="completed",
                    started=session.get("started_at_wall", datetime.now(UTC).isoformat()),
                    ended=datetime.now(UTC).isoformat(),
                    outcome=session.get("outcome", ""),
                    next_step=session.get("next_step", ""),
                )
            )
            return result.inserted_primary_key[0]

    def focus_stats(self, project: str) -> dict:
        if not self.retention:
            return {"sessions": 0, "minutes": 0, "last_goal": None}
        with self.engine.connect() as conn:
            total = conn.execute(
                select(
                    func.count(focus_sessions.c.id),
                    func.coalesce(func.sum(focus_sessions.c.focus_minutes), 0),
                ).where(focus_sessions.c.project == project)
            ).one()
            last = conn.execute(
                select(focus_sessions.c.goal)
                .where(focus_sessions.c.project == project)
                .order_by(focus_sessions.c.id.desc())
                .limit(1)
            ).scalar_one_or_none()
        today = datetime.now(UTC).date().isoformat()
        with self.engine.connect() as conn:
            today_count = conn.execute(select(func.count(focus_sessions.c.id)).where(
                focus_sessions.c.project == project, focus_sessions.c.started >= today,
            )).scalar_one()
        return {"sessions": int(total[0]), "minutes": int(total[1]), "last_goal": last,
                "today_sessions": int(today_count)}

    def review_focus(self, project: str, goal: str, outcome: str, next_step: str) -> bool:
        if not self.retention:
            return False
        with self.engine.begin() as conn:
            row = conn.execute(select(focus_sessions.c.id).where(
                focus_sessions.c.project == project, focus_sessions.c.goal == goal,
            ).order_by(focus_sessions.c.id.desc()).limit(1)).scalar_one_or_none()
            if row is None:
                return False
            conn.execute(update(focus_sessions).where(focus_sessions.c.id == row).values(
                outcome=outcome, next_step=next_step,
            ))
        return True

    def focus_history(self, project: str, limit: int = 30) -> list[dict]:
        if not self.retention:
            return []
        with self.engine.connect() as conn:
            return [dict(row) for row in conn.execute(
                select(focus_sessions).where(focus_sessions.c.project == project)
                .order_by(focus_sessions.c.id.desc()).limit(max(1, min(limit, 100)))
            ).mappings()]

    def save_focus_steps(self, project: str, goal: str, steps: list[dict]) -> list[dict]:
        if not self.retention:
            return steps
        now = datetime.now(UTC).isoformat()
        serialized = json.dumps(steps, ensure_ascii=False)
        with self.engine.begin() as conn:
            existing = conn.execute(select(focus_plans.c.id).where(
                focus_plans.c.project == project, focus_plans.c.goal == goal
            )).scalar_one_or_none()
            if existing:
                conn.execute(update(focus_plans).where(focus_plans.c.id == existing).values(steps=serialized, updated=now))
            else:
                conn.execute(insert(focus_plans).values(project=project, goal=goal, steps=serialized, updated=now))
        return steps

    def get_focus_steps(self, project: str, goal: str) -> list[str]:
        if not self.retention:
            return []
        with self.engine.connect() as conn:
            value = conn.execute(select(focus_plans.c.steps).where(
                focus_plans.c.project == project, focus_plans.c.goal == goal
            )).scalar_one_or_none()
        if not value:
            return []
        stored = json.loads(value)
        return [
            {"text": step, "done": False} if isinstance(step, str) else step
            for step in stored
        ]

    def add_exercise(self, project: str, prompt: str, answer: str, topic: str) -> int | None:
        if not self.retention:
            return None
        now = datetime.now(UTC).isoformat()
        with self.engine.begin() as conn:
            result = conn.execute(
                insert(exercises).values(
                    project=project,
                    prompt=prompt,
                    answer=answer,
                    topic=topic,
                    created=now,
                    updated=now,
                    next_review=now,
                    interval_days=0,
                    ease="2.5",
                    repetitions=0,
                )
            )
            return result.inserted_primary_key[0]

    def list_exercises(self, project: str, due_only: bool = False, limit: int = 100) -> list[dict]:
        if not self.retention:
            return []
        statement = select(exercises).where(exercises.c.project == project)
        if due_only:
            statement = statement.where(exercises.c.next_review <= datetime.now(UTC).isoformat())
        with self.engine.connect() as conn:
            return [
                dict(row)
                for row in conn.execute(
                    statement.order_by(exercises.c.next_review, exercises.c.id).limit(limit)
                ).mappings()
            ]

    def review_exercise(self, project: str, identity: int, rating: int) -> bool:
        if not self.retention:
            return False
        with self.engine.begin() as conn:
            row = conn.execute(
                select(exercises)
                .where(exercises.c.project == project, exercises.c.id == identity)
            ).mappings().first()
            if row is None:
                return False
            ease = max(1.3, float(row["ease"]) + 0.1 - (5 - rating) * 0.08)
            repetitions = 0 if rating < 3 else row["repetitions"] + 1
            if rating < 3:
                interval = 1
            elif repetitions == 1:
                interval = 1
            elif repetitions == 2:
                interval = 3
            else:
                interval = max(1, round(max(1, row["interval_days"]) * ease))
            next_review = datetime.now(UTC).replace(microsecond=0) + timedelta(days=interval)
            conn.execute(
                update(exercises)
                .where(exercises.c.project == project, exercises.c.id == identity)
                .values(
                    updated=datetime.now(UTC).isoformat(),
                    next_review=next_review.isoformat(),
                    interval_days=interval,
                    ease=f"{ease:.4f}",
                    repetitions=repetitions,
                    last_rating=rating,
                )
            )
            return True

    def remove_exercise(self, project: str, identity: int) -> bool:
        with self.engine.begin() as conn:
            return bool(
                conn.execute(
                    delete(exercises).where(
                        exercises.c.project == project, exercises.c.id == identity
                    )
                ).rowcount
            )

    def close(self) -> None:
        self.engine.dispose()
