"""Versioned Story Engine foundation: dossiers, immutable snapshots and ordered scenes."""
import json
from datetime import datetime, timezone
from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from .models import Project, Story, StoryRevision, StoryScene
from .story_schemas import StoryCreate, StoryUpdate, StorySceneCreate, StorySceneUpdate

def _now(): return datetime.now(timezone.utc)
def _dump(value): return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
def _beats(raw):
    try: value = json.loads(raw or "[]")
    except (TypeError, ValueError): value = []
    return value if isinstance(value, list) else []
def _scene_data(scene):
    return {"id":scene.id,"position":scene.position,"title":scene.title,"slugline":scene.slugline,"summary":scene.summary,
            "dramatic_purpose":scene.dramatic_purpose,"location":scene.location,"time_of_day":scene.time_of_day,
            "beats":_beats(scene.beats_json),"body":scene.body,"version":scene.version,
            "created_at":scene.created_at,"updated_at":scene.updated_at}
def _story_fields(story):
    return {"id":story.id,"project_id":story.project_id,"title":story.title,"format":story.format,"genre":story.genre,
            "target_audience":story.target_audience,"premise":story.premise,"logline":story.logline,"synopsis":story.synopsis,
            "creative_intent":story.creative_intent,"status":story.status,"version":story.version,
            "created_at":story.created_at,"updated_at":story.updated_at}
def _snapshot(db, story, note=None):
    scenes=db.scalars(select(StoryScene).where(StoryScene.story_id==story.id).order_by(StoryScene.position)).all()
    db.add(StoryRevision(story_id=story.id,version=story.version,snapshot_json=_dump({"story":_story_fields(story),"scenes":[_scene_data(s) for s in scenes]}),change_note=note))
def _payload(db, story, revisions=False):
    scenes=db.scalars(select(StoryScene).where(StoryScene.story_id==story.id).order_by(StoryScene.position)).all()
    result={**_story_fields(story),"scenes":[_scene_data(s) for s in scenes],"scene_count":len(scenes)}
    if revisions:
        rows=db.scalars(select(StoryRevision).where(StoryRevision.story_id==story.id).order_by(StoryRevision.version.desc()).limit(100)).all()
        result["revisions"]=[{"id":r.id,"version":r.version,"change_note":r.change_note,"created_at":r.created_at} for r in rows]
    return result
def _get(db, story_id):
    story=db.get(Story,story_id)
    if story is None: raise HTTPException(status_code=404,detail={"code":"story_not_found"})
    return story
def _bump(db, story, note):
    story.version+=1; story.updated_at=_now(); _snapshot(db,story,note)

def create_story(db:Session,payload:StoryCreate):
    project=db.get(Project,payload.project_id)
    if project is None: raise HTTPException(status_code=404,detail={"code":"project_not_found"})
    if project.status!="active": raise HTTPException(status_code=409,detail={"code":"project_archived"})
    title=payload.title.strip()
    if not title: raise HTTPException(status_code=422,detail={"code":"story_title_required"})
    story=Story(project_id=project.id,title=title,format=payload.format,genre=payload.genre,target_audience=payload.target_audience,
        premise=payload.premise,logline=payload.logline,synopsis=payload.synopsis,creative_intent=payload.creative_intent)
    db.add(story);db.flush();_snapshot(db,story,"Initial story dossier");db.commit();db.refresh(story)
    return _payload(db,story,True)
def list_stories(db:Session,project_id=None,limit=50,offset=0):
    query=select(Story);count=select(func.count()).select_from(Story)
    if project_id: query=query.where(Story.project_id==project_id);count=count.where(Story.project_id==project_id)
    total=db.scalar(count) or 0;items=db.scalars(query.order_by(Story.updated_at.desc()).limit(limit).offset(offset)).all()
    return {"items":[_payload(db,x) for x in items],"total":total,"limit":limit,"offset":offset}
def get_story(db:Session,story_id:str): return _payload(db,_get(db,story_id),True)
def update_story(db:Session,story_id:str,payload:StoryUpdate):
    story=_get(db,story_id)
    if story.version!=payload.expected_version: raise HTTPException(status_code=409,detail={"code":"story_version_conflict","current_version":story.version})
    values=payload.model_dump(exclude_unset=True,exclude={"expected_version","change_note"})
    for key,value in values.items(): setattr(story,key,value.strip() if key=="title" and isinstance(value,str) else value)
    if not story.title.strip(): raise HTTPException(status_code=422,detail={"code":"story_title_required"})
    _bump(db,story,payload.change_note or "Story dossier updated");db.commit();db.refresh(story)
    return _payload(db,story,True)
def create_scene(db:Session,story_id:str,payload:StorySceneCreate):
    story=_get(db,story_id);position=(db.scalar(select(func.max(StoryScene.position)).where(StoryScene.story_id==story_id)) or 0)+1
    scene=StoryScene(story_id=story_id,position=position,title=payload.title.strip(),slugline=payload.slugline,summary=payload.summary,
        dramatic_purpose=payload.dramatic_purpose,location=payload.location,time_of_day=payload.time_of_day,beats_json=_dump(payload.beats),body=payload.body)
    db.add(scene);db.flush();_bump(db,story,f"Scene {position} created");db.commit();db.refresh(scene)
    return {"scene":_scene_data(scene),"story_version":story.version}
def update_scene(db:Session,story_id:str,scene_id:str,payload:StorySceneUpdate):
    story=_get(db,story_id);scene=db.scalar(select(StoryScene).where(StoryScene.id==scene_id,StoryScene.story_id==story_id))
    if scene is None: raise HTTPException(status_code=404,detail={"code":"story_scene_not_found"})
    if scene.version!=payload.expected_version: raise HTTPException(status_code=409,detail={"code":"scene_version_conflict","current_version":scene.version})
    values=payload.model_dump(exclude_unset=True,exclude={"expected_version","change_note"})
    for key,value in values.items():
        if key=="beats": scene.beats_json=_dump(value)
        else: setattr(scene,key,value.strip() if key=="title" and isinstance(value,str) else value)
    if not scene.title.strip(): raise HTTPException(status_code=422,detail={"code":"scene_title_required"})
    scene.version+=1;scene.updated_at=_now();_bump(db,story,payload.change_note or f"Scene {scene.position} updated")
    db.commit();db.refresh(scene);return {"scene":_scene_data(scene),"story_version":story.version}
def delete_scene(db:Session,story_id:str,scene_id:str):
    story=_get(db,story_id);scene=db.scalar(select(StoryScene).where(StoryScene.id==scene_id,StoryScene.story_id==story_id))
    if scene is None: raise HTTPException(status_code=404,detail={"code":"story_scene_not_found"})
    deleted_position=scene.position;db.delete(scene);db.flush()
    remaining=db.scalars(select(StoryScene).where(StoryScene.story_id==story_id).order_by(StoryScene.position)).all()
    for i,item in enumerate(remaining,1): item.position=-i
    db.flush()
    for i,item in enumerate(remaining,1): item.position=i
    _bump(db,story,f"Scene {deleted_position} deleted");db.commit()
    return _payload(db,story,True)


def reorder_scenes(db: Session, story_id: str, expected_story_version: int, scene_ids: list[str]):
    story = _get(db, story_id)
    if story.version != expected_story_version:
        raise HTTPException(status_code=409, detail={"code": "story_version_conflict", "current_version": story.version})
    scenes = db.scalars(select(StoryScene).where(StoryScene.story_id == story_id).order_by(StoryScene.position)).all()
    current_ids = {scene.id for scene in scenes}
    requested_ids = set(scene_ids)
    if len(scene_ids) != len(requested_ids) or requested_ids != current_ids:
        raise HTTPException(status_code=422, detail={"code": "scene_order_must_contain_each_scene_once"})
    by_id = {scene.id: scene for scene in scenes}
    # Move through unique negative positions to avoid transient unique-index collisions.
    for index, scene_id in enumerate(scene_ids, 1):
        by_id[scene_id].position = -index
    db.flush()
    for index, scene_id in enumerate(scene_ids, 1):
        by_id[scene_id].position = index
    _bump(db, story, "Scene order changed")
    db.commit()
    db.refresh(story)
    return _payload(db, story, True)



def apply_outline_proposal(db: Session, story_id: str, expected_version: int, proposal: dict, commit: bool = True):
    """Append a reviewed AI outline as scenes in one versioned story revision."""
    story = _get(db, story_id)
    if story.version != expected_version:
        raise HTTPException(status_code=409, detail={
            "code": "story_version_conflict", "current_version": story.version
        })
    project = db.get(Project, story.project_id)
    if project is None or project.status != "active" or story.status in {"archived", "locked"}:
        raise HTTPException(status_code=409, detail={"code": "story_not_active"})

    existing_count = db.scalar(
        select(func.count()).select_from(StoryScene).where(StoryScene.story_id == story_id)
    ) or 0
    if existing_count + len(proposal["scenes"]) > 500:
        raise HTTPException(status_code=409, detail={"code": "story_scene_limit_exceeded"})

    story.logline = proposal["logline"]
    story.synopsis = proposal["synopsis"]
    if story.status == "development":
        story.status = "outlined"

    for offset, item in enumerate(proposal["scenes"], 1):
        db.add(StoryScene(
            story_id=story.id,
            position=existing_count + offset,
            title=item["title"].strip(),
            slugline=item.get("slugline"),
            summary=item["summary"],
            dramatic_purpose=item.get("dramatic_purpose"),
            beats_json=_dump(item.get("beats", [])),
        ))

    _bump(db, story, f"AI outline proposal applied · {len(proposal['scenes'])} scenes appended")
    if commit:
        db.commit()
        db.refresh(story)
    else:
        db.flush()
    return _payload(db, story, True)
