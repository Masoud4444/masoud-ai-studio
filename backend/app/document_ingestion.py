"""Bounded local PDF/DOCX extraction into provenance-aware evidence."""
import json,os,subprocess,sys
from pathlib import Path
from fastapi import HTTPException
from sqlalchemy.orm import Session
from .models import Asset,ResearchSource
from .research_schemas import ResearchEvidenceCreate
from .research_vault import create_evidence
from .storage import blob_path
MAX_BYTES=20*1024*1024
PARSER=Path(__file__).with_name("document_parser.py")
def extract_document(db:Session,source_id:str)->dict:
    source=db.get(ResearchSource,source_id)
    if source is None: raise HTTPException(404,detail={"code":"research_source_not_found"})
    if source.source_type!="document" or not source.asset_id: raise HTTPException(409,detail={"code":"document_source_requires_attached_asset"})
    asset=db.get(Asset,source.asset_id)
    if asset is None: raise HTTPException(404,detail={"code":"research_document_asset_not_found"})
    if asset.size_bytes<=0 or asset.size_bytes>MAX_BYTES: raise HTTPException(413,detail={"code":"document_parse_size_limit","max_bytes":MAX_BYTES})
    path=blob_path(asset.sha256)
    if not path.is_file() or path.stat().st_size!=asset.size_bytes: raise HTTPException(409,detail={"code":"document_blob_unavailable"})
    with path.open("rb") as f: sig=f.read(8)
    if sig.startswith(b"%PDF-") and asset.mime_type=="application/pdf": kind="pdf"
    elif sig.startswith(b"PK\\x03\\x04") and asset.mime_type=="application/zip": kind="docx"
    else: raise HTTPException(415,detail={"code":"unsupported_document_format","supported":["PDF","DOCX"]})
    env={"PATH":os.environ.get("PATH",""),"PYTHONIOENCODING":"utf-8"}
    try:
        run=subprocess.run([sys.executable,"-I",str(PARSER),str(path),kind],stdin=subprocess.DEVNULL,capture_output=True,text=True,encoding="utf-8",errors="replace",timeout=30,check=False,cwd=str(PARSER.parents[2]),env=env)
    except subprocess.TimeoutExpired: raise HTTPException(408,detail={"code":"document_parser_timeout"})
    except OSError: raise HTTPException(503,detail={"code":"document_parser_unavailable"})
    try: result=json.loads(run.stdout or "{}")
    except json.JSONDecodeError: raise HTTPException(422,detail={"code":"document_parser_invalid_output"})
    if run.returncode:
        code=result.get("error","document_parse_failed")
        allowed={"encrypted_pdf_not_supported","document_page_limit_exceeded","document_text_limit_exceeded","docx_archive_limits_exceeded","invalid_docx_container","document_chunk_limit_exceeded","unsupported_document_type"}
        raise HTTPException(422,detail={"code":code if code in allowed else "document_parse_failed"})
    chunks=result.get("chunks")
    if not isinstance(chunks,list) or len(chunks)>250: raise HTTPException(422,detail={"code":"document_parser_invalid_output"})
    created=[]; skipped=0
    for n,chunk in enumerate(chunks,1):
        text=chunk.get("text","")
        if not isinstance(text,str) or not text.strip(): skipped+=1; continue
        parts=[text[i:i+10000] for i in range(0,len(text),10000)]
        for part_no,part in enumerate(parts,1):
            locator=chunk.get("locator") or f"Document segment {n}"
            if len(parts)>1: locator=f"{locator}, segment {part_no}/{len(parts)}"
            item=create_evidence(db,source_id,ResearchEvidenceCreate(evidence_type="quote",excerpt=part,locator=locator[:500],metadata={"extraction_method":"local_text_extraction","parser_version":"0.1","format":kind,"segment":n}))
            if item.get("replayed"): skipped+=1
            else: created.append(item["id"])
    return {"source_id":source_id,"format":kind,"chunks_found":len(chunks),"evidence_created":len(created),"already_present_or_empty":skipped,"evidence_ids":created,"limitations":["No OCR","No embedded media extraction","No page-layout fidelity"]}
