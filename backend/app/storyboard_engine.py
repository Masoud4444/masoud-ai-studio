"""Scene-linked storyboard, immutable media references and human-reviewed takes."""
import json
from datetime import datetime, timezone
from uuid import uuid4
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from .models import Story, StoryScene, ProjectAsset, Asset, StoryboardShot, StoryboardTake
from .storyboard_schemas import StoryboardShotCreate, StoryboardShotUpdate, StoryboardTakeCreate

def _now(): return datetime.now(timezone.utc)
def _json(value): return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
def _decode(raw, fallback):
    try: return json.loads(raw or "")
    except (TypeError, ValueError): return fallback

def _story(db, story_id):
    story=db.get(Story,story_id)
    if story is None: raise HTTPException(404,detail={"code":"story_not_found"})
    return story

def _scene(db, story_id, scene_id):
    scene=db.scalar(select(StoryScene).where(StoryScene.id==scene_id,StoryScene.story_id==story_id))
    if scene is None: raise HTTPException(404,detail={"code":"story_scene_not_found"})
    return scene

def _shot_data(db, shot):
    takes=db.scalars(select(StoryboardTake).where(StoryboardTake.shot_id==shot.id).order_by(StoryboardTake.take_number)).all()
    return {"id":shot.id,"story_id":shot.story_id,"scene_id":shot.scene_id,"position":shot.position,
      "title":shot.title,"description":shot.description,"shot_size":shot.shot_size,"camera_angle":shot.camera_angle,
      "camera_movement":shot.camera_movement,"lens":shot.lens,"composition":shot.composition,"action":shot.action,
      "dialogue":shot.dialogue,"duration_seconds":float(shot.duration_seconds),"transition":shot.transition,"prompt":shot.prompt,
      "source_excerpt":shot.source_excerpt,"source_start":shot.source_start,"source_end":shot.source_end,
      "continuity_notes":shot.continuity_notes,"entity_refs":_decode(shot.entity_refs_json,[]),
      "approved_take_id":shot.approved_take_id,"version":shot.version,
      "takes":[{"id":t.id,"take_number":t.take_number,"asset_id":t.asset_id,"asset_sha256":t.asset_sha256,
        "status":t.status,"engine_key":t.engine_key,"engine_job_id":t.engine_job_id,"prompt_snapshot":t.prompt_snapshot,
        "generation_metadata":_decode(t.generation_metadata_json,{}),"review_note":t.review_note,"created_at":t.created_at} for t in takes],
      "created_at":shot.created_at,"updated_at":shot.updated_at}

def list_shots(db:Session,story_id:str,scene_id:str):
    _story(db,story_id);_scene(db,story_id,scene_id)
    rows=db.scalars(select(StoryboardShot).where(StoryboardShot.story_id==story_id,StoryboardShot.scene_id==scene_id).order_by(StoryboardShot.position)).all()
    return {"items":[_shot_data(db,row) for row in rows]}

def create_shot(db:Session,story_id:str,payload:StoryboardShotCreate):
    _story(db,story_id);_scene(db,story_id,payload.scene_id)
    position=(db.scalar(select(func.max(StoryboardShot.position)).where(StoryboardShot.story_id==story_id,StoryboardShot.scene_id==payload.scene_id)) or 0)+1
    data=payload.model_dump();refs=data.pop("entity_refs")
    shot=StoryboardShot(id=str(uuid4()),story_id=story_id,position=position,entity_refs_json=_json(refs),**data)
    db.add(shot);db.commit();db.refresh(shot);return _shot_data(db,shot)

def update_shot(db:Session,story_id:str,shot_id:str,payload:StoryboardShotUpdate):
    _story(db,story_id)
    shot=db.scalar(select(StoryboardShot).where(StoryboardShot.id==shot_id,StoryboardShot.story_id==story_id))
    if shot is None: raise HTTPException(404,detail={"code":"storyboard_shot_not_found"})
    if shot.version!=payload.expected_version: raise HTTPException(409,detail={"code":"storyboard_shot_version_conflict","current_version":shot.version})
    values=payload.model_dump(exclude_unset=True,exclude={"expected_version"})
    if "entity_refs" in values: shot.entity_refs_json=_json(values.pop("entity_refs"))
    for key,value in values.items(): setattr(shot,key,value)
    shot.version+=1;shot.updated_at=_now()
    # An edit invalidates approval so approval always applies to the current shot version.
    shot.approved_take_id=None
    db.commit();db.refresh(shot);return _shot_data(db,shot)

def reorder_shots(db:Session,story_id:str,scene_id:str,expected_story_version:int,shot_ids:list[str]):
    story=_story(db,story_id);_scene(db,story_id,scene_id)
    if story.version!=expected_story_version: raise HTTPException(409,detail={"code":"story_version_conflict","current_version":story.version})
    rows=db.scalars(select(StoryboardShot).where(StoryboardShot.story_id==story_id,StoryboardShot.scene_id==scene_id).order_by(StoryboardShot.position)).all()
    current={row.id for row in rows}
    if len(shot_ids)!=len(set(shot_ids)) or set(shot_ids)!=current: raise HTTPException(422,detail={"code":"invalid_storyboard_order"})
    for row in rows: row.position+=len(rows)+1
    db.flush();by_id={row.id:row for row in rows}
    for index,shot_id in enumerate(shot_ids,1): by_id[shot_id].position=index
    db.commit();return {"items":[_shot_data(db,by_id[sid]) for sid in shot_ids]}

def create_take(db:Session,story_id:str,shot_id:str,payload:StoryboardTakeCreate):
    _story(db,story_id)
    shot=db.scalar(select(StoryboardShot).where(StoryboardShot.id==shot_id,StoryboardShot.story_id==story_id))
    if shot is None: raise HTTPException(404,detail={"code":"storyboard_shot_not_found"})
    asset=db.get(Asset,payload.asset_id)
    if asset is None: raise HTTPException(404,detail={"code":"asset_not_found"})
    linked=db.scalar(select(ProjectAsset.id).join(Story,Story.project_id==ProjectAsset.project_id).where(Story.id==story_id,ProjectAsset.asset_id==asset.id))
    if linked is None: raise HTTPException(422,detail={"code":"asset_not_attached_to_story_project"})
    number=(db.scalar(select(func.max(StoryboardTake.take_number)).where(StoryboardTake.shot_id==shot_id)) or 0)+1
    take=StoryboardTake(id=str(uuid4()),shot_id=shot_id,take_number=number,asset_id=asset.id,asset_sha256=asset.sha256,
      prompt_snapshot=payload.prompt_snapshot,engine_key=payload.engine_key,engine_job_id=payload.engine_job_id,
      generation_metadata_json=_json(payload.generation_metadata),status="generated")
    db.add(take);db.commit();db.refresh(take);return _shot_data(db,shot)

def review_take(db:Session,story_id:str,shot_id:str,take_id:str,status:str,review_note:str|None):
    _story(db,story_id)
    shot=db.scalar(select(StoryboardShot).where(StoryboardShot.id==shot_id,StoryboardShot.story_id==story_id))
    if shot is None: raise HTTPException(404,detail={"code":"storyboard_shot_not_found"})
    take=db.scalar(select(StoryboardTake).where(StoryboardTake.id==take_id,StoryboardTake.shot_id==shot_id))
    if take is None: raise HTTPException(404,detail={"code":"storyboard_take_not_found"})
    if status=="approved":
        if take.status not in ("selected","approved"): raise HTTPException(409,detail={"code":"take_must_be_selected_before_approval"})
        shot.approved_take_id=take.id;take.status="approved"
    elif status=="selected":
        if shot.approved_take_id: shot.approved_take_id=None
        db.query(StoryboardTake).filter(StoryboardTake.shot_id==shot_id,StoryboardTake.id!=take_id,StoryboardTake.status=="selected").update({"status":"generated"},synchronize_session=False)
        take.status="selected"
    else:
        if shot.approved_take_id==take.id: shot.approved_take_id=None
        take.status="rejected"
    take.review_note=review_note;shot.version+=1;shot.updated_at=_now()
    db.commit();db.refresh(shot);return _shot_data(db,shot)
