"""Character and World Bible API with versioned profiles and scene links."""
import json
from datetime import datetime, timezone
from uuid import uuid4
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint, select
from sqlalchemy.orm import Mapped, mapped_column, Session
from .database import Base
from .models import Story, StoryScene

def _now(): return datetime.now(timezone.utc)
def _dump(v): return json.dumps(v,ensure_ascii=False,sort_keys=True,separators=(",",":"))
def _load(v):
    try: return json.loads(v or "{}")
    except (ValueError,TypeError): return {}
class Character(Base):
    __tablename__="story_characters"
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4()))
    story_id:Mapped[str]=mapped_column(ForeignKey("stories.id",ondelete="RESTRICT"),index=True,nullable=False)
    name:Mapped[str]=mapped_column(String(180),nullable=False); role:Mapped[str]=mapped_column(String(80),nullable=False)
    age:Mapped[str|None]=mapped_column(String(80)); appearance_json:Mapped[str]=mapped_column(Text,default="{}",nullable=False)
    psychology_json:Mapped[str]=mapped_column(Text,default="{}",nullable=False); backstory:Mapped[str|None]=mapped_column(Text)
    goals:Mapped[str|None]=mapped_column(Text); conflict:Mapped[str|None]=mapped_column(Text); arc:Mapped[str|None]=mapped_column(Text)
    voice_notes:Mapped[str|None]=mapped_column(Text); version:Mapped[int]=mapped_column(Integer,default=1,nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=_now,nullable=False)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=_now,onupdate=_now,nullable=False)
class Relationship(Base):
    __tablename__="character_relationships"
    __table_args__=(UniqueConstraint("story_id","source_id","target_id","kind",name="uq_character_relationship"),)
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4()))
    story_id:Mapped[str]=mapped_column(ForeignKey("stories.id",ondelete="RESTRICT"),index=True,nullable=False)
    source_id:Mapped[str]=mapped_column(ForeignKey("story_characters.id",ondelete="RESTRICT"),nullable=False)
    target_id:Mapped[str]=mapped_column(ForeignKey("story_characters.id",ondelete="RESTRICT"),nullable=False)
    kind:Mapped[str]=mapped_column(String(100),nullable=False); description:Mapped[str|None]=mapped_column(Text)
class Location(Base):
    __tablename__="story_world_locations"
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4()))
    story_id:Mapped[str]=mapped_column(ForeignKey("stories.id",ondelete="RESTRICT"),index=True,nullable=False)
    name:Mapped[str]=mapped_column(String(180),nullable=False); location_type:Mapped[str]=mapped_column(String(80),nullable=False)
    description:Mapped[str|None]=mapped_column(Text); geography_json:Mapped[str]=mapped_column(Text,default="{}",nullable=False)
    culture_json:Mapped[str]=mapped_column(Text,default="{}",nullable=False); version:Mapped[int]=mapped_column(Integer,default=1,nullable=False)
    created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=_now,nullable=False)
    updated_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=_now,onupdate=_now,nullable=False)
class WorldRule(Base):
    __tablename__="story_world_rules"
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4()))
    story_id:Mapped[str]=mapped_column(ForeignKey("stories.id",ondelete="RESTRICT"),index=True,nullable=False)
    category:Mapped[str]=mapped_column(String(80),nullable=False); statement:Mapped[str]=mapped_column(Text,nullable=False)
    rationale:Mapped[str|None]=mapped_column(Text); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=_now,nullable=False)
class SceneCharacter(Base):
    __tablename__="scene_character_links"
    __table_args__=(UniqueConstraint("scene_id","character_id",name="uq_scene_character_link"),)
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4()))
    scene_id:Mapped[str]=mapped_column(ForeignKey("story_scenes.id",ondelete="RESTRICT"),index=True,nullable=False)
    character_id:Mapped[str]=mapped_column(ForeignKey("story_characters.id",ondelete="RESTRICT"),index=True,nullable=False)
    presence_type:Mapped[str]=mapped_column(String(40),default="present",nullable=False); note:Mapped[str|None]=mapped_column(Text)
class SceneLocation(Base):
    __tablename__="scene_location_links"
    __table_args__=(UniqueConstraint("scene_id","location_id",name="uq_scene_location_link"),)
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4()))
    scene_id:Mapped[str]=mapped_column(ForeignKey("story_scenes.id",ondelete="RESTRICT"),index=True,nullable=False)
    location_id:Mapped[str]=mapped_column(ForeignKey("story_world_locations.id",ondelete="RESTRICT"),index=True,nullable=False)
    note:Mapped[str|None]=mapped_column(Text)
class BibleRevision(Base):
    __tablename__="story_bible_revisions"
    __table_args__=(UniqueConstraint("story_id","version",name="uq_story_bible_revision"),)
    id:Mapped[str]=mapped_column(String(36),primary_key=True,default=lambda:str(uuid4()))
    story_id:Mapped[str]=mapped_column(ForeignKey("stories.id",ondelete="RESTRICT"),index=True,nullable=False)
    version:Mapped[int]=mapped_column(Integer,nullable=False); snapshot_json:Mapped[str]=mapped_column(Text,nullable=False)
    change_note:Mapped[str|None]=mapped_column(String(500)); created_at:Mapped[datetime]=mapped_column(DateTime(timezone=True),default=_now,nullable=False)
class CharacterIn(BaseModel):
    name:str=Field(min_length=1,max_length=180); role:str=Field(default="supporting",max_length=80); age:str|None=None
    appearance:dict=Field(default_factory=dict); psychology:dict=Field(default_factory=dict); backstory:str|None=None
    goals:str|None=None; conflict:str|None=None; arc:str|None=None; voice_notes:str|None=None
class CharacterEdit(CharacterIn): expected_version:int=Field(ge=1)
class LocationIn(BaseModel):
    name:str=Field(min_length=1,max_length=180); location_type:str=Field(default="place",max_length=80)
    description:str|None=None; geography:dict=Field(default_factory=dict); culture:dict=Field(default_factory=dict)
class LocationEdit(LocationIn): expected_version:int=Field(ge=1)
class RuleIn(BaseModel):
    category:str=Field(min_length=1,max_length=80); statement:str=Field(min_length=1,max_length=12000); rationale:str|None=None
class RelationshipIn(BaseModel):
    source_id:str=Field(min_length=36,max_length=36); target_id:str=Field(min_length=36,max_length=36)
    kind:str=Field(min_length=1,max_length=100); description:str|None=None
class SceneCharacterIn(BaseModel):
    character_id:str=Field(min_length=36,max_length=36); presence_type:str=Field(default="present",max_length=40); note:str|None=None
class SceneLocationIn(BaseModel):
    location_id:str=Field(min_length=36,max_length=36); note:str|None=None
router=APIRouter(prefix="/api/v1",tags=["character-world"])
def _story(db,sid):
    x=db.get(Story,sid)
    if not x: raise HTTPException(404,detail={"code":"story_not_found"})
    return x
def _owned(db,model,i,sid):
    x=db.get(model,i)
    if not x or x.story_id!=sid: raise HTTPException(404,detail={"code":"bible_item_not_found"})
    return x
def _char(x):
    return {"id":x.id,"story_id":x.story_id,"name":x.name,"role":x.role,"age":x.age,"appearance":_load(x.appearance_json),"psychology":_load(x.psychology_json),"backstory":x.backstory,"goals":x.goals,"conflict":x.conflict,"arc":x.arc,"voice_notes":x.voice_notes,"version":x.version}
def _loc(x):
    return {"id":x.id,"story_id":x.story_id,"name":x.name,"location_type":x.location_type,"description":x.description,"geography":_load(x.geography_json),"culture":_load(x.culture_json),"version":x.version}
def _snapshot(db,sid,note):
    cs=db.scalars(select(Character).where(Character.story_id==sid)).all(); rs=db.scalars(select(Relationship).where(Relationship.story_id==sid)).all()
    ls=db.scalars(select(Location).where(Location.story_id==sid)).all(); rules=db.scalars(select(WorldRule).where(WorldRule.story_id==sid)).all()
    scenes=db.scalars(select(StoryScene).where(StoryScene.story_id==sid)).all(); ids=[x.id for x in scenes]
    sc=db.scalars(select(SceneCharacter).where(SceneCharacter.scene_id.in_(ids))).all() if ids else []
    sl=db.scalars(select(SceneLocation).where(SceneLocation.scene_id.in_(ids))).all() if ids else []
    version=(db.scalar(select(BibleRevision.version).where(BibleRevision.story_id==sid).order_by(BibleRevision.version.desc()).limit(1)) or 0)+1
    data={"characters":[_char(x) for x in cs],"relationships":[{"source_id":x.source_id,"target_id":x.target_id,"kind":x.kind,"description":x.description} for x in rs],"locations":[_loc(x) for x in ls],"rules":[{"category":x.category,"statement":x.statement,"rationale":x.rationale} for x in rules],"scene_characters":[{"scene_id":x.scene_id,"character_id":x.character_id,"presence_type":x.presence_type,"note":x.note} for x in sc],"scene_locations":[{"scene_id":x.scene_id,"location_id":x.location_id,"note":x.note} for x in sl]}
    db.add(BibleRevision(story_id=sid,version=version,snapshot_json=_dump(data),change_note=note))
@router.get("/stories/{sid}/bible")
def get_bible(sid:str,db:Session):
    _story(db,sid); cs=db.scalars(select(Character).where(Character.story_id==sid)).all(); rs=db.scalars(select(Relationship).where(Relationship.story_id==sid)).all()
    ls=db.scalars(select(Location).where(Location.story_id==sid)).all(); rules=db.scalars(select(WorldRule).where(WorldRule.story_id==sid)).all()
    rev=db.scalars(select(BibleRevision).where(BibleRevision.story_id==sid).order_by(BibleRevision.version.desc()).limit(50)).all()
    scenes=db.scalars(select(StoryScene).where(StoryScene.story_id==sid)).all(); ids=[x.id for x in scenes]
    sc=db.scalars(select(SceneCharacter).where(SceneCharacter.scene_id.in_(ids))).all() if ids else []; sl=db.scalars(select(SceneLocation).where(SceneLocation.scene_id.in_(ids))).all() if ids else []
    return {"story_id":sid,"characters":[_char(x) for x in cs],"relationships":[{"id":x.id,"source_id":x.source_id,"target_id":x.target_id,"kind":x.kind,"description":x.description} for x in rs],"locations":[_loc(x) for x in ls],"rules":[{"id":x.id,"category":x.category,"statement":x.statement,"rationale":x.rationale} for x in rules],"scene_characters":[{"scene_id":x.scene_id,"character_id":x.character_id,"presence_type":x.presence_type,"note":x.note} for x in sc],"scene_locations":[{"scene_id":x.scene_id,"location_id":x.location_id,"note":x.note} for x in sl],"revisions":[{"version":x.version,"change_note":x.change_note,"created_at":x.created_at} for x in rev]}
@router.post("/stories/{sid}/characters",status_code=201)
def create_character(sid:str,p:CharacterIn,db:Session):
    _story(db,sid); x=Character(story_id=sid,name=p.name.strip(),role=p.role,age=p.age,appearance_json=_dump(p.appearance),psychology_json=_dump(p.psychology),backstory=p.backstory,goals=p.goals,conflict=p.conflict,arc=p.arc,voice_notes=p.voice_notes)
    db.add(x);db.flush();_snapshot(db,sid,"Character created");db.commit();db.refresh(x);return _char(x)
@router.patch("/stories/{sid}/characters/{cid}")
def update_character(sid:str,cid:str,p:CharacterEdit,db:Session):
    x=_owned(db,Character,cid,sid)
    if x.version!=p.expected_version: raise HTTPException(409,detail={"code":"character_version_conflict","current_version":x.version})
    for k,v in p.model_dump(exclude={"expected_version"}).items(): setattr(x,{"appearance":"appearance_json","psychology":"psychology_json"}.get(k,k),_dump(v) if k in ("appearance","psychology") else v.strip() if k=="name" else v)
    x.version+=1;x.updated_at=_now();_snapshot(db,sid,"Character updated");db.commit();db.refresh(x);return _char(x)
@router.post("/stories/{sid}/relationships",status_code=201)
def create_relationship(sid:str,p:RelationshipIn,db:Session):
    _story(db,sid)
    if p.source_id==p.target_id: raise HTTPException(422,detail={"code":"self_relationship_not_allowed"})
    _owned(db,Character,p.source_id,sid);_owned(db,Character,p.target_id,sid)
    x=Relationship(story_id=sid,**p.model_dump());db.add(x)
    try: db.flush();_snapshot(db,sid,"Relationship created");db.commit()
    except Exception: db.rollback();raise HTTPException(409,detail={"code":"relationship_conflict"})
    return {"id":x.id,"source_id":x.source_id,"target_id":x.target_id,"kind":x.kind,"description":x.description}
@router.post("/stories/{sid}/locations",status_code=201)
def create_location(sid:str,p:LocationIn,db:Session):
    _story(db,sid);x=Location(story_id=sid,name=p.name.strip(),location_type=p.location_type,description=p.description,geography_json=_dump(p.geography),culture_json=_dump(p.culture))
    db.add(x);db.flush();_snapshot(db,sid,"World location created");db.commit();db.refresh(x);return _loc(x)
@router.patch("/stories/{sid}/locations/{lid}")
def update_location(sid:str,lid:str,p:LocationEdit,db:Session):
    x=_owned(db,Location,lid,sid)
    if x.version!=p.expected_version: raise HTTPException(409,detail={"code":"location_version_conflict","current_version":x.version})
    for k,v in p.model_dump(exclude={"expected_version"}).items(): setattr(x,{"geography":"geography_json","culture":"culture_json"}.get(k,k),_dump(v) if k in ("geography","culture") else v.strip() if k=="name" else v)
    x.version+=1;x.updated_at=_now();_snapshot(db,sid,"World location updated");db.commit();db.refresh(x);return _loc(x)
@router.post("/stories/{sid}/rules",status_code=201)
def create_rule(sid:str,p:RuleIn,db:Session):
    _story(db,sid);x=WorldRule(story_id=sid,**p.model_dump());db.add(x);db.flush();_snapshot(db,sid,"World rule created");db.commit();return {"id":x.id,"category":x.category,"statement":x.statement,"rationale":x.rationale}
@router.post("/stories/{sid}/scenes/{scene_id}/characters",status_code=201)
def attach_character(sid:str,scene_id:str,p:SceneCharacterIn,db:Session):
    _story(db,sid);scene=db.get(StoryScene,scene_id)
    if not scene or scene.story_id!=sid: raise HTTPException(404,detail={"code":"scene_not_found"})
    _owned(db,Character,p.character_id,sid);x=SceneCharacter(scene_id=scene_id,**p.model_dump());db.add(x)
    try: db.flush();_snapshot(db,sid,"Character linked to scene");db.commit()
    except Exception: db.rollback();raise HTTPException(409,detail={"code":"scene_character_link_conflict"})
    return {"scene_id":scene_id,"character_id":x.character_id,"presence_type":x.presence_type,"note":x.note}
@router.post("/stories/{sid}/scenes/{scene_id}/locations",status_code=201)
def attach_location(sid:str,scene_id:str,p:SceneLocationIn,db:Session):
    _story(db,sid);scene=db.get(StoryScene,scene_id)
    if not scene or scene.story_id!=sid: raise HTTPException(404,detail={"code":"scene_not_found"})
    _owned(db,Location,p.location_id,sid);x=SceneLocation(scene_id=scene_id,**p.model_dump());db.add(x)
    try: db.flush();_snapshot(db,sid,"Location linked to scene");db.commit()
    except Exception: db.rollback();raise HTTPException(409,detail={"code":"scene_location_link_conflict"})
    return {"scene_id":scene_id,"location_id":x.location_id,"note":x.note}
