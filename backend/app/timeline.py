"""Explicit in-world chronology independent from screenplay scene order."""
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .database import Base, get_db
from .models import Story, StoryScene


def _now() -> datetime:
    return datetime.now(timezone.utc)


class TimelineEvent(Base):
    __tablename__ = "timeline_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    story_id: Mapped[str] = mapped_column(ForeignKey("stories.id", ondelete="RESTRICT"), index=True, nullable=False)
    scene_id: Mapped[str | None] = mapped_column(ForeignKey("story_scenes.id", ondelete="RESTRICT"), index=True, nullable=True)
    event_type: Mapped[str] = mapped_column(String(48), default="story_event", nullable=False)
    title: Mapped[str] = mapped_column(String(240), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    in_world_time: Mapped[str | None] = mapped_column(String(180), nullable=True)
    chronology_note: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True, nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class TimelineRelation(Base):
    __tablename__ = "timeline_relations"
    __table_args__ = (
        UniqueConstraint("story_id", "before_event_id", "after_event_id", name="uq_timeline_relation_edge"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    story_id: Mapped[str] = mapped_column(ForeignKey("stories.id", ondelete="RESTRICT"), index=True, nullable=False)
    before_event_id: Mapped[str] = mapped_column(ForeignKey("timeline_events.id", ondelete="RESTRICT"), index=True, nullable=False)
    after_event_id: Mapped[str] = mapped_column(ForeignKey("timeline_events.id", ondelete="RESTRICT"), index=True, nullable=False)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)


class TimelineEventIn(BaseModel):
    scene_id: str | None = Field(default=None, min_length=36, max_length=36)
    event_type: str = Field(default="story_event", min_length=1, max_length=48)
    title: str = Field(min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=8000)
    in_world_time: str | None = Field(default=None, max_length=180)
    chronology_note: str | None = Field(default=None, max_length=4000)


class TimelineEventEdit(BaseModel):
    expected_version: int = Field(ge=1)
    title: str = Field(min_length=1, max_length=240)
    description: str | None = Field(default=None, max_length=8000)
    in_world_time: str | None = Field(default=None, max_length=180)
    chronology_note: str | None = Field(default=None, max_length=4000)
    active: bool = True


class TimelineRelationIn(BaseModel):
    before_event_id: str = Field(min_length=36, max_length=36)
    after_event_id: str = Field(min_length=36, max_length=36)
    note: str | None = Field(default=None, max_length=4000)


router = APIRouter(prefix="/api/v1/stories/{sid}/timeline", tags=["timeline"])


def _story(db: Session, sid: str) -> Story:
    story = db.get(Story, sid)
    if story is None:
        raise HTTPException(404, detail={"code": "story_not_found"})
    return story


def _event_out(event: TimelineEvent) -> dict:
    return {
        "id": event.id,
        "story_id": event.story_id,
        "scene_id": event.scene_id,
        "event_type": event.event_type,
        "title": event.title,
        "description": event.description,
        "in_world_time": event.in_world_time,
        "chronology_note": event.chronology_note,
        "active": event.active,
        "version": event.version,
        "created_at": event.created_at,
        "updated_at": event.updated_at,
    }


def _relation_out(relation: TimelineRelation) -> dict:
    return {
        "id": relation.id,
        "before_event_id": relation.before_event_id,
        "after_event_id": relation.after_event_id,
        "note": relation.note,
        "created_at": relation.created_at,
    }


def _active_edges(db: Session, sid: str) -> list[tuple[str, str]]:
    rows = db.scalars(select(TimelineRelation).where(TimelineRelation.story_id == sid)).all()
    active_ids = {
        event.id
        for event in db.scalars(
            select(TimelineEvent).where(TimelineEvent.story_id == sid, TimelineEvent.active.is_(True))
        ).all()
    }
    return [
        (row.before_event_id, row.after_event_id)
        for row in rows
        if row.before_event_id in active_ids and row.after_event_id in active_ids
    ]


def _path_exists(edges: list[tuple[str, str]], start: str, target: str) -> bool:
    adjacency: dict[str, list[str]] = {}
    for before, after in edges:
        adjacency.setdefault(before, []).append(after)
    pending = [start]
    visited: set[str] = set()
    while pending:
        current = pending.pop()
        if current == target:
            return True
        if current in visited:
            continue
        visited.add(current)
        pending.extend(adjacency.get(current, []))
    return False


def _topological_order(event_ids: list[str], edges: list[tuple[str, str]]) -> tuple[list[str], list[str]]:
    adjacency = {event_id: [] for event_id in event_ids}
    indegree = {event_id: 0 for event_id in event_ids}
    for before, after in edges:
        if before in adjacency and after in adjacency:
            adjacency[before].append(after)
            indegree[after] += 1
    ready = sorted(event_id for event_id, degree in indegree.items() if degree == 0)
    order: list[str] = []
    while ready:
        current = ready.pop(0)
        order.append(current)
        for following in sorted(adjacency[current]):
            indegree[following] -= 1
            if indegree[following] == 0:
                ready.append(following)
                ready.sort()
    return order, sorted(set(event_ids) - set(order))


@router.get("/events")
def list_events(sid: str, db: Session = Depends(get_db)):
    _story(db, sid)
    rows = db.scalars(
        select(TimelineEvent).where(TimelineEvent.story_id == sid).order_by(TimelineEvent.created_at, TimelineEvent.id)
    ).all()
    return {"items": [_event_out(row) for row in rows]}


@router.post("/events", status_code=201)
def create_event(sid: str, payload: TimelineEventIn, db: Session = Depends(get_db)):
    _story(db, sid)
    if payload.scene_id:
        scene = db.get(StoryScene, payload.scene_id)
        if scene is None or scene.story_id != sid:
            raise HTTPException(404, detail={"code": "scene_not_found"})
    event = TimelineEvent(
        story_id=sid,
        scene_id=payload.scene_id,
        event_type=payload.event_type.strip().casefold(),
        title=payload.title.strip(),
        description=payload.description,
        in_world_time=payload.in_world_time,
        chronology_note=payload.chronology_note,
    )
    db.add(event)
    db.commit()
    db.refresh(event)
    return _event_out(event)


@router.patch("/events/{event_id}")
def update_event(sid: str, event_id: str, payload: TimelineEventEdit, db: Session = Depends(get_db)):
    _story(db, sid)
    event = db.get(TimelineEvent, event_id)
    if event is None or event.story_id != sid:
        raise HTTPException(404, detail={"code": "timeline_event_not_found"})
    if event.version != payload.expected_version:
        raise HTTPException(409, detail={"code": "timeline_event_version_conflict", "current_version": event.version})
    event.title = payload.title.strip()
    event.description = payload.description
    event.in_world_time = payload.in_world_time
    event.chronology_note = payload.chronology_note
    event.active = payload.active
    event.version += 1
    event.updated_at = _now()
    db.commit()
    db.refresh(event)
    return _event_out(event)


@router.get("/relations")
def list_relations(sid: str, db: Session = Depends(get_db)):
    _story(db, sid)
    rows = db.scalars(
        select(TimelineRelation).where(TimelineRelation.story_id == sid).order_by(TimelineRelation.created_at)
    ).all()
    return {"items": [_relation_out(row) for row in rows]}


@router.post("/relations", status_code=201)
def create_relation(sid: str, payload: TimelineRelationIn, db: Session = Depends(get_db)):
    _story(db, sid)
    if payload.before_event_id == payload.after_event_id:
        raise HTTPException(422, detail={"code": "timeline_self_relation"})
    before = db.get(TimelineEvent, payload.before_event_id)
    after = db.get(TimelineEvent, payload.after_event_id)
    if not before or before.story_id != sid or not after or after.story_id != sid:
        raise HTTPException(404, detail={"code": "timeline_event_not_found"})
    if not before.active or not after.active:
        raise HTTPException(409, detail={"code": "timeline_event_inactive"})
    edges = _active_edges(db, sid)
    if (payload.before_event_id, payload.after_event_id) in edges:
        existing = db.scalar(
            select(TimelineRelation).where(
                TimelineRelation.story_id == sid,
                TimelineRelation.before_event_id == payload.before_event_id,
                TimelineRelation.after_event_id == payload.after_event_id,
            )
        )
        return _relation_out(existing)
    if _path_exists(edges, payload.after_event_id, payload.before_event_id):
        raise HTTPException(409, detail={"code": "timeline_chronology_cycle"})
    relation = TimelineRelation(
        story_id=sid,
        before_event_id=payload.before_event_id,
        after_event_id=payload.after_event_id,
        note=payload.note,
    )
    db.add(relation)
    db.commit()
    db.refresh(relation)
    return _relation_out(relation)


@router.post("/analyze")
def analyze_timeline(sid: str, db: Session = Depends(get_db)):
    _story(db, sid)
    events = db.scalars(
        select(TimelineEvent).where(TimelineEvent.story_id == sid, TimelineEvent.active.is_(True))
    ).all()
    event_ids = [event.id for event in events]
    edges = _active_edges(db, sid)
    ordered, cyclic = _topological_order(event_ids, edges)
    if cyclic:
        return {
            "story_id": sid,
            "is_consistent": False,
            "ordered_event_ids": ordered,
            "cycle_event_ids": cyclic,
            "relations_count": len(edges),
            "note": "Chronology is a partial order. Events without a path between them are intentionally unordered.",
        }
    return {
        "story_id": sid,
        "is_consistent": True,
        "ordered_event_ids": ordered,
        "cycle_event_ids": [],
        "relations_count": len(edges),
        "note": "Chronology is a partial order. Events without a path between them are intentionally unordered.",
    }
