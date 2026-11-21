"""Story-scoped prop registry for stable object identity and state continuity."""
from datetime import datetime, timezone
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, select
from sqlalchemy.orm import Mapped, Session, mapped_column

from .character_world import Character
from .database import Base, get_db
from .models import Story


def _now() -> datetime:
    return datetime.now(timezone.utc)


class StoryProp(Base):
    __tablename__ = "story_props"

    id: Mapped[str] = mapped_column(String(36), primary_key=True, default=lambda: str(uuid4()))
    story_id: Mapped[str] = mapped_column(ForeignKey("stories.id", ondelete="RESTRICT"), index=True, nullable=False)
    name: Mapped[str] = mapped_column(String(180), nullable=False)
    category: Mapped[str] = mapped_column(String(80), default="prop", nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    origin: Mapped[str | None] = mapped_column(Text, nullable=True)
    initial_state: Mapped[str | None] = mapped_column(Text, nullable=True)
    current_holder_id: Mapped[str | None] = mapped_column(ForeignKey("story_characters.id", ondelete="RESTRICT"), index=True, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", nullable=False)
    version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_now, onupdate=_now, nullable=False)


class PropIn(BaseModel):
    name: str = Field(min_length=1, max_length=180)
    category: str = Field(default="prop", min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=8000)
    origin: str | None = Field(default=None, max_length=4000)
    initial_state: str | None = Field(default=None, max_length=4000)
    current_holder_id: str | None = Field(default=None, min_length=36, max_length=36)


class PropEdit(BaseModel):
    expected_version: int = Field(ge=1)
    name: str = Field(min_length=1, max_length=180)
    category: str = Field(min_length=1, max_length=80)
    description: str | None = Field(default=None, max_length=8000)
    origin: str | None = Field(default=None, max_length=4000)
    initial_state: str | None = Field(default=None, max_length=4000)
    current_holder_id: str | None = Field(default=None, min_length=36, max_length=36)
    status: str = Field(default="active", pattern="^(active|lost|destroyed|retired)$")


router = APIRouter(prefix="/api/v1/stories/{sid}/props", tags=["story-props"])


def _story(db: Session, sid: str) -> Story:
    story = db.get(Story, sid)
    if story is None:
        raise HTTPException(404, detail={"code": "story_not_found"})
    return story


def _validate_holder(db: Session, sid: str, holder_id: str | None) -> None:
    if holder_id is None:
        return
    holder = db.get(Character, holder_id)
    if holder is None or holder.story_id != sid:
        raise HTTPException(404, detail={"code": "prop_holder_character_not_found"})


def _out(prop: StoryProp) -> dict:
    return {
        "id": prop.id,
        "story_id": prop.story_id,
        "name": prop.name,
        "category": prop.category,
        "description": prop.description,
        "origin": prop.origin,
        "initial_state": prop.initial_state,
        "current_holder_id": prop.current_holder_id,
        "status": prop.status,
        "version": prop.version,
        "created_at": prop.created_at,
        "updated_at": prop.updated_at,
    }


@router.get("")
def list_props(sid: str, db: Session = Depends(get_db)):
    _story(db, sid)
    rows = db.scalars(select(StoryProp).where(StoryProp.story_id == sid).order_by(StoryProp.name, StoryProp.id)).all()
    return {"items": [_out(row) for row in rows]}


@router.post("", status_code=201)
def create_prop(sid: str, payload: PropIn, db: Session = Depends(get_db)):
    _story(db, sid)
    _validate_holder(db, sid, payload.current_holder_id)
    name = payload.name.strip()
    duplicate = db.scalar(select(StoryProp).where(StoryProp.story_id == sid, StoryProp.name.ilike(name)))
    if duplicate:
        raise HTTPException(409, detail={"code": "story_prop_name_conflict"})
    prop = StoryProp(
        story_id=sid,
        name=name,
        category=payload.category.strip().casefold(),
        description=payload.description,
        origin=payload.origin,
        initial_state=payload.initial_state,
        current_holder_id=payload.current_holder_id,
    )
    db.add(prop)
    db.commit()
    db.refresh(prop)
    return _out(prop)


@router.patch("/{prop_id}")
def update_prop(sid: str, prop_id: str, payload: PropEdit, db: Session = Depends(get_db)):
    _story(db, sid)
    prop = db.get(StoryProp, prop_id)
    if prop is None or prop.story_id != sid:
        raise HTTPException(404, detail={"code": "story_prop_not_found"})
    if prop.version != payload.expected_version:
        raise HTTPException(409, detail={"code": "story_prop_version_conflict", "current_version": prop.version})
    _validate_holder(db, sid, payload.current_holder_id)
    duplicate = db.scalar(
        select(StoryProp).where(
            StoryProp.story_id == sid,
            StoryProp.name.ilike(payload.name.strip()),
            StoryProp.id != prop_id,
        )
    )
    if duplicate:
        raise HTTPException(409, detail={"code": "story_prop_name_conflict"})
    prop.name = payload.name.strip()
    prop.category = payload.category.strip().casefold()
    prop.description = payload.description
    prop.origin = payload.origin
    prop.initial_state = payload.initial_state
    prop.current_holder_id = payload.current_holder_id
    prop.status = payload.status
    prop.version += 1
    prop.updated_at = _now()
    db.commit()
    db.refresh(prop)
    return _out(prop)
