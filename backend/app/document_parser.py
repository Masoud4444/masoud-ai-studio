"""Read-only PDF/DOCX parser subprocess."""
import json,sys,zipfile
from pathlib import Path
MAX_PAGES=250
MAX_CHARS=2_000_000
def parse(path,kind):
    if kind=="pdf":
        from pypdf import PdfReader
        reader=PdfReader(str(path),strict=False)
        if reader.is_encrypted: raise ValueError("encrypted_pdf_not_supported")
        if len(reader.pages)>MAX_PAGES: raise ValueError("document_page_limit_exceeded")
        out=[]; total=0
        for n,page in enumerate(reader.pages,1):
            text=(page.extract_text() or "").replace("\x00","").strip()
            total+=len(text)
            if total>MAX_CHARS: raise ValueError("document_text_limit_exceeded")
            if text: out.append({"text":text,"locator":f"PDF page {n}"})
        return out
    if kind=="docx":
        from docx import Document
        with zipfile.ZipFile(path) as z:
            infos=z.infolist()
            if len(infos)>2000 or sum(x.file_size for x in infos)>80*1024*1024: raise ValueError("docx_archive_limits_exceeded")
            names=set(z.namelist())
            if "[Content_Types].xml" not in names or "word/document.xml" not in names: raise ValueError("invalid_docx_container")
        doc=Document(str(path)); out=[]; buf=[]; start=1; total=0
        for n,p in enumerate(doc.paragraphs,1):
            s=(p.text or "").replace("\x00","").strip()
            if not s: continue
            total+=len(s)
            if total>MAX_CHARS: raise ValueError("document_text_limit_exceeded")
            buf.append(s)
            if sum(map(len,buf))>=8000:
                out.append({"text":"\n".join(buf),"locator":f"DOCX paragraphs {start}-{n}"})
                buf=[]; start=n+1
                if len(out)>=MAX_PAGES: raise ValueError("document_chunk_limit_exceeded")
        if buf: out.append({"text":"\n".join(buf),"locator":f"DOCX paragraphs {start}-{len(doc.paragraphs)}"})
        return out
    raise ValueError("unsupported_document_type")
if __name__=="__main__":
    try:
        if len(sys.argv)!=3: raise ValueError("invalid_parser_arguments")
        print(json.dumps({"chunks":parse(Path(sys.argv[1]),sys.argv[2])},ensure_ascii=False,separators=(",",":")))
    except Exception as exc:
        code=str(exc) if isinstance(exc,ValueError) else "document_parse_failed"
        print(json.dumps({"error":code},separators=(",",":"))); sys.exit(2)
