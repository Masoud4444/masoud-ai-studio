"""Deterministic, review-first continuity ledger and analyzer."""
import hashlib
import json
from datetime import datetime, timezone
from typing import Literal
from uuid import uuid4
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, select
from sqlalchemy.orm import Mapped, Session, mapped_column
from .database import Base, get_db
from .models import Story, StoryScene
from .character_world import Character, Location, SceneCharacter, SceneLocation
from .props import StoryProp
from .timeline import TimelineEvent, TimelineRelation

def _now(): return datetime.now(timezone.utc)
def _json(v): return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"))
def _fingerprint(v): return hashlib.sha256(_json(v).encode("utf-8")).hexdigest()

class ContinuityFact(Base):
    __tablename__="continuity_facts"
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4()))
    story_id:Mapped[str]=mapped_column(ForeignKey("stories.id",ondelete="RESTRICT"),index=True,nullable=False)
    scene_id:Mapped[str]=mapped_column(ForeignKey("story_scenes.id",ondelete="RESTRICT"),index=True,nullable=False)
    subject_type:Mapped[str]=mapped_column(String(24),nullable=False)
    subject_ref:Mapped[str|None]=mapped_column(String(36),nullable=True)
    subject_label:Mapped[str]=mapped_column(String(180),nullable=False)
    attribute:Mapped[str]=mapped_column(String(100),nullable=False)
    value:Mapped[str]=mapped_column(Text,nullable=False)
    transition_note:Mapped[str|None]=mapped_column(Text)
    evidence_note:Mapped[str|None]=mapped_column(Text)
    active:Mapped[bool]=mapped_column(default=True,nullable=False)
    version:Mapped[int]=mapped_column(Integer,default=1,nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=_now,nullable=False)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=_now,onupdate=_now,nullable=False)

class ContinuityIssue(Base):
    __tablename__="continuity_issues"
    __table_args__=(UniqueConstraint("story_id","fingerprint",name="uq_continuity_issue_fingerprint"),)
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4()))
    story_id:Mapped[str]=mapped_column(ForeignKey("stories.id",ondelete="RESTRICT"),index=True,nullable=False)
    fingerprint:Mapped[str]=mapped_column(String(64),nullable=False)
    code:Mapped[str]=mapped_column(String(48),nullable=False)
    severity:Mapped[str]=mapped_column(String(16),nullable=False)
    status:Mapped[str]=mapped_column(String(16),default="open",nullable=False)
    title:Mapped[str]=mapped_column(String(240),nullable=False)
    description:Mapped[str]=mapped_column(Text,nullable=False)
    details_json:Mapped[str]=mapped_column(Text,nullable=False)
    occurrences:Mapped[int]=mapped_column(Integer,default=1,nullable=False)
    first_seen:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=_now,nullable=False)
    last_seen:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=_now,nullable=False)
    reviewer_note:Mapped[str|None]=mapped_column(Text)
    reviewed_at:Mapped[datetime|None]=mapped_column(DateTime(timezone=True))

class FactIn(BaseModel):
    scene_id:str=Field(min_length=36,max_length=36)
    subject_type:Literal["character","location","prop"]
    subject_ref:str|None=Field(default=None,min_length=36,max_length=36)
    subject_label:str=Field(min_length=1,max_length=180)
    attribute:str=Field(min_length=1,max_length=100)
    value:str=Field(min_length=1,max_length=4000)
    transition_note:str|None=Field(default=None,max_length=4000)
    evidence_note:str|None=Field(default=None,max_length=4000)
class FactEdit(BaseModel):
    expected_version:int=Field(ge=1)
    value:str=Field(min_length=1,max_length=4000)
    transition_note:str|None=Field(default=None,max_length=4000)
    evidence_note:str|None=Field(default=None,max_length=4000)
    active:bool=True
class IssueReview(BaseModel):
    status:Literal["accepted","dismissed","resolved"]
    reviewer_note:str|None=Field(default=None,max_length=4000)

router=APIRouter(prefix="/api/v1/stories/{sid}/continuity",tags=["continuity"])
def _story(db,sid):
    story=db.get(Story,sid)
    if not story: raise HTTPException(404,detail={"code":"story_not_found"})
    return story
def _fact_out(x):
    return {"id":x.id,"scene_id":x.scene_id,"subject_type":x.subject_type,"subject_ref":x.subject_ref,"subject_label":x.subject_label,"attribute":x.attribute,"value":x.value,"transition_note":x.transition_note,"evidence_note":x.evidence_note,"active":x.active,"version":x.version,"created_at":x.created_at}
def _issue_out(x):
    return {"id":x.id,"code":x.code,"severity":x.severity,"status":x.status,"title":x.title,"description":x.description,"details":json.loads(x.details_json),"occurrences":x.occurrences,"first_seen":x.first_seen,"last_seen":x.last_seen,"reviewer_note":x.reviewer_note}
@router.get("/facts")
def list_facts(sid:str,db:Session=Depends(get_db)):
    _story(db,sid)
    facts=db.scalars(select(ContinuityFact).where(ContinuityFact.story_id==sid).order_by(ContinuityFact.created_at)).all()
    return {"items":[_fact_out(x) for x in facts]}
@router.post("/facts",status_code=201)
def create_fact(sid:str,p:FactIn,db:Session=Depends(get_db)):
    _story(db,sid);scene=db.get(StoryScene,p.scene_id)
    if not scene or scene.story_id!=sid: raise HTTPException(404,detail={"code":"scene_not_found"})
    if p.subject_type=="character":
        item=db.get(Character,p.subject_ref) if p.subject_ref else None
        if not item or item.story_id!=sid: raise HTTPException(404,detail={"code":"character_not_found"})
        label=item.name
    elif p.subject_type=="location":
        item=db.get(Location,p.subject_ref) if p.subject_ref else None
        if not item or item.story_id!=sid: raise HTTPException(404,detail={"code":"location_not_found"})
        label=item.name
    else:
        if p.subject_ref: raise HTTPException(422,detail={"code":"prop_reference_not_supported"})
        label=p.subject_label.strip()
    x=ContinuityFact(story_id=sid,scene_id=p.scene_id,subject_type=p.subject_type,subject_ref=p.subject_ref,subject_label=label,attribute=p.attribute.strip().casefold(),value=p.value.strip(),transition_note=p.transition_note,evidence_note=p.evidence_note)
    db.add(x);db.commit();db.refresh(x);return _fact_out(x)
@router.patch("/facts/{fact_id}")
def update_fact(sid:str,fact_id:str,p:FactEdit,db:Session=Depends(get_db)):
    _story(db,sid);x=db.get(ContinuityFact,fact_id)
    if not x or x.story_id!=sid: raise HTTPException(404,detail={"code":"continuity_fact_not_found"})
    if x.version!=p.expected_version: raise HTTPException(409,detail={"code":"continuity_fact_version_conflict","current_version":x.version})
    x.value=p.value.strip();x.transition_note=p.transition_note;x.evidence_note=p.evidence_note;x.active=p.active;x.version+=1;x.updated_at=_now()
    db.commit();db.refresh(x);return _fact_out(x)
@router.get("/issues")
def list_issues(sid:str,status:Literal["open","accepted","dismissed","resolved"]|None=None,db:Session=Depends(get_db)):
    _story(db,sid);q=select(ContinuityIssue).where(ContinuityIssue.story_id==sid)
    if status:q=q.where(ContinuityIssue.status==status)
    items=db.scalars(q.order_by(ContinuityIssue.last_seen.desc()).limit(500)).all()
    return {"items":[_issue_out(x) for x in items]}
@router.patch("/issues/{issue_id}")
def review_issue(sid:str,issue_id:str,p:IssueReview,db:Session=Depends(get_db)):
    _story(db,sid);x=db.get(ContinuityIssue,issue_id)
    if not x or x.story_id!=sid: raise HTTPException(404,detail={"code":"continuity_issue_not_found"})
    x.status=p.status;x.reviewer_note=p.reviewer_note;x.reviewed_at=_now();db.commit();db.refresh(x);return _issue_out(x)


def _timeline_cycle_details(events, relations):
    """Return deterministic evidence for events inside chronology cycles only."""
    active = {event.id: event for event in events if event.active}
    edges = [
        (relation.before_event_id, relation.after_event_id)
        for relation in relations
        if relation.before_event_id in active and relation.after_event_id in active
    ]
    adjacency = {event_id: [] for event_id in active}
    reverse = {event_id: [] for event_id in active}
    for before, after in edges:
        adjacency[before].append(after)
        reverse[after].append(before)

    visited = set()
    order = []

    def visit(node):
        visited.add(node)
        for neighbor in sorted(adjacency[node]):
            if neighbor not in visited:
                visit(neighbor)
        order.append(node)

    for event_id in sorted(active):
        if event_id not in visited:
            visit(event_id)

    visited.clear()
    cyclic_ids = set()

    def collect(node, component):
        visited.add(node)
        component.append(node)
        for neighbor in sorted(reverse[node]):
            if neighbor not in visited:
                collect(neighbor, component)

    for event_id in reversed(order):
        if event_id in visited:
            continue
        component = []
        collect(event_id, component)
        if len(component) > 1 or any(before == event_id and after == event_id for before, after in edges):
            cyclic_ids.update(component)

    if not cyclic_ids:
        return None
    cycle_events = [active[event_id] for event_id in cyclic_ids]
    cycle_edges = [
        (before, after) for before, after in edges
        if before in cyclic_ids and after in cyclic_ids
    ]
    return {
        "event_ids": sorted(cyclic_ids),
        "scene_ids": sorted({event.scene_id for event in cycle_events if event.scene_id}),
        "events": [
            {"id": event.id, "scene_id": event.scene_id, "title": event.title}
            for event in sorted(cycle_events, key=lambda item: item.id)
        ],
        "relations": [
            {"before_event_id": before, "after_event_id": after}
            for before, after in sorted(cycle_edges)
        ],
    }

@router.post("/analyze")
def analyze_continuity(sid:str,db:Session=Depends(get_db)):
    _story(db,sid)
    scenes=db.scalars(select(StoryScene).where(StoryScene.story_id==sid).order_by(StoryScene.position,StoryScene.id)).all()
    scene_by_id={s.id:s for s in scenes};positions={s.id:s.position for s in scenes}
    facts=db.scalars(select(ContinuityFact).where(ContinuityFact.story_id==sid,ContinuityFact.active.is_(True))).all()
    facts.sort(key=lambda f:(positions.get(f.scene_id,10**9),f.created_at,f.id))
    grouped={}
    for f in facts:
        key=(f.subject_type,f.subject_ref or f.subject_label.casefold(),f.attribute)
        grouped.setdefault(key,[]).append(f)
    detected=[]
    def add(code,severity,title,description,details):
        fp=_fingerprint({"code":code,"details":details})
        detected.append((fp,code,severity,title,description,details))
    for (kind,subject,attribute),items in grouped.items():
        by_scene={}
        for f in items:by_scene.setdefault(f.scene_id,[]).append(f)
        for sid_scene,same in by_scene.items():
            values={f.value.casefold() for f in same}
            if len(values)>1:
                details={"subject_type":kind,"subject":same[0].subject_label,"attribute":attribute,"scene_id":sid_scene,"scene_title":scene_by_id[sid_scene].title,"facts":[{"id":f.id,"value":f.value} for f in same]}
                add("conflicting_same_scene","high","Conflicting facts in one scene",f"{same[0].subject_label}: {attribute} has multiple values in {scene_by_id[sid_scene].title}.",details)
        previous=None
        for f in items:
            if previous and previous.scene_id!=f.scene_id and previous.value.casefold()!=f.value.casefold() and not f.transition_note:
                details={"subject_type":kind,"subject":f.subject_label,"attribute":attribute,"from":{"scene_id":previous.scene_id,"scene_title":scene_by_id[previous.scene_id].title,"value":previous.value},"to":{"scene_id":f.scene_id,"scene_title":scene_by_id[f.scene_id].title,"value":f.value},"fact_id":f.id}
                add("unexplained_state_change","medium","Unexplained state change",f"{f.subject_label}: {attribute} changes between scenes without a recorded transition note.",details)
            previous=f
    character_links={(x.scene_id,x.character_id) for x in db.scalars(select(SceneCharacter).where(SceneCharacter.scene_id.in_(list(scene_by_id)))).all()} if scene_by_id else set()
    location_links={(x.scene_id,x.location_id) for x in db.scalars(select(SceneLocation).where(SceneLocation.scene_id.in_(list(scene_by_id)))).all()} if scene_by_id else set()
    for f in facts:
        if f.subject_type=="character" and (f.scene_id,f.subject_ref) not in character_links:
            details={"fact_id":f.id,"scene_id":f.scene_id,"scene_title":scene_by_id[f.scene_id].title,"character_id":f.subject_ref,"character":f.subject_label}
            add("character_not_linked_to_scene","low","Character missing scene link",f"{f.subject_label} has a continuity fact in {scene_by_id[f.scene_id].title} but is not linked as present in that scene.",details)
        if f.subject_type=="location" and (f.scene_id,f.subject_ref) not in location_links:
            details={"fact_id":f.id,"scene_id":f.scene_id,"scene_title":scene_by_id[f.scene_id].title,"location_id":f.subject_ref,"location":f.subject_label}
            add("location_not_linked_to_scene","low","Location missing scene link",f"{f.subject_label} has a continuity fact in {scene_by_id[f.scene_id].title} but is not linked to that scene.",details)
    timeline_events=db.scalars(select(TimelineEvent).where(TimelineEvent.story_id==sid,TimelineEvent.active.is_(True))).all()
    timeline_relations=db.scalars(select(TimelineRelation).where(TimelineRelation.story_id==sid)).all()
    cycle_details=_timeline_cycle_details(timeline_events,timeline_relations)
    if cycle_details:
        add("timeline_chronology_cycle","high","Contradictory story chronology",
            "The explicit chronology contains a cycle: at least one event is required to happen before itself.",
            cycle_details)
    now=_now();open_ids=[];current_fingerprints={item[0] for item in detected}
    for fp,code,severity,title,description,details in detected:
        issue=db.scalar(select(ContinuityIssue).where(ContinuityIssue.story_id==sid,ContinuityIssue.fingerprint==fp))
        if issue:
            issue.last_seen=now;issue.occurrences+=1
            if issue.status=="open":
                issue.severity=severity;issue.title=title;issue.description=description;issue.details_json=_json(details)
        else:
            issue=ContinuityIssue(story_id=sid,fingerprint=fp,code=code,severity=severity,title=title,description=description,details_json=_json(details),first_seen=now,last_seen=now)
            db.add(issue);db.flush()
        if issue.status=="open":open_ids.append(issue.id)
    # Open findings that no longer reproduce are closed as system-resolved; human-reviewed states are preserved.
    stale=db.scalars(select(ContinuityIssue).where(ContinuityIssue.story_id==sid,ContinuityIssue.status=="open")).all()
    for issue in stale:
        if issue.fingerprint not in current_fingerprints:
            issue.status="resolved";issue.reviewer_note="No longer reproduced by the latest continuity analysis.";issue.reviewed_at=now
    db.commit()
    all_open=db.scalars(select(ContinuityIssue).where(ContinuityIssue.story_id==sid,ContinuityIssue.status=="open")).all()
    return {"story_id":sid,"facts_analyzed":len(facts),"issues_detected":len(detected),"open_issues":len(all_open),"issues":[_issue_out(x) for x in all_open]}
