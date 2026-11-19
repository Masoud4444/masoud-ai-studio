import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Activity, BookOpen, Check, CirclePause, CirclePlay, FileText, FolderOpen, Link2, Plus, RefreshCw, ShieldCheck, Sparkles, Upload, X } from "lucide-react";
type Project={id:string;name:string;slug:string};
type Workflow={workflow_key:string;version:number;description:string;steps:Array<{key:string;approval_required:boolean}>};
type Run={id:string;workflow_key:string;status:string;project_id:string|null;created_at:string;steps:Array<{step_key:string;status:string;approval_required:boolean;task_id:string;error_code:string|null}>};
type Agent={id:string;slug:string;name:string;purpose:string;status:string;version:number;provider_id:string|null;model_id:string|null;tools:Array<{tool_name:string;permission:string;approval_required:boolean;is_enabled:boolean}>};
type Asset={id:string;asset_id:string;filename:string;mime_type:string;size_bytes:number;created_at:string};
type ResearchSearchResult={id:string;kind:"source"|"evidence"|"claim";title:string;excerpt:string;source_type?:string;claim_type?:string;status?:string;locator?:string;source_id?:string;project_id?:string;project_ids?:string[]};
type ResearchSearchResponse={query:string;totals:{sources:number;evidence:number;claims:number};sources:ResearchSearchResult[];evidence:ResearchSearchResult[];claims:ResearchSearchResult[]};
async function api<T>(path:string,init?:RequestInit):Promise<T>{const response=await fetch(path,init);const body=await response.json().catch(()=>null);if(!response.ok)throw new Error(body?.detail?.code??body?.detail??`Request failed (${response.status})`);return body as T;}
function PanelHeader({eyebrow,title,description,onRefresh}:{eyebrow:string;title:string;description:string;onRefresh:()=>void}){return <div className="panel-header"><div><span className="eyebrow">{eyebrow}</span><h2>{title}</h2><p>{description}</p></div><button className="secondary-button" onClick={onRefresh}><RefreshCw size={14}/> Refresh</button></div>}
function Status({value}:{value:string}){return <span className={`status-pill status-${value.replaceAll("_","-")}`}>{value.replaceAll("_"," ")}</span>}
export function ProductionPanel({projects}:{projects:Project[]}) {
 const [workflows,setWorkflows]=useState<Workflow[]>([]),[runs,setRuns]=useState<Run[]>([]),[workflowKey,setWorkflowKey]=useState(""),[projectId,setProjectId]=useState(""),[brief,setBrief]=useState(""),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState(""),[notice,setNotice]=useState("");
 async function load(){setLoading(true);setError("");try{const [w,r]=await Promise.all([api<Workflow[]>("/api/v1/production/workflows"),api<{items:Run[]}>("/api/v1/production/runs?limit=50")]);setWorkflows(w);setRuns(r.items??[]);if(!workflowKey&&w.length)setWorkflowKey(w[0].workflow_key);}catch(e){setError(e instanceof Error?e.message:"Could not load production data");}finally{setLoading(false);}}
 useEffect(()=>{void load();},[]);
 async function create(e:FormEvent){e.preventDefault();if(!workflowKey||!brief.trim())return;setBusy(true);setError("");setNotice("");try{await api("/api/v1/production/runs",{method:"POST",headers:{"Content-Type":"application/json","Idempotency-Key":crypto.randomUUID()},body:JSON.stringify({workflow_key:workflowKey,project_id:projectId||null,inputs:{brief:brief.trim()}})});setBrief("");setNotice("Production run created. Approval gates remain active.");await load();}catch(e){setError(e instanceof Error?e.message:"Could not create run");}finally{setBusy(false);}}
 async function control(id:string,action:"pause"|"resume"|"cancel"){setBusy(true);setError("");try{await api(`/api/v1/production/runs/${id}/${action}`,{method:"POST"});setNotice(`Run ${action} request completed.`);await load();}catch(e){setError(e instanceof Error?e.message:"Run action failed");}finally{setBusy(false);}}
 return <section className="workspace-panel"><PanelHeader eyebrow="PRODUCTION ORCHESTRATOR" title="Production room" description="Create and monitor preproduction workflows with explicit human approval gates." onRefresh={()=>void load()}/><form className="create-strip" onSubmit={create}><label className="field-label">Workflow<select value={workflowKey} onChange={e=>setWorkflowKey(e.target.value)}>{workflows.map(w=><option key={w.workflow_key} value={w.workflow_key}>{w.workflow_key} · v{w.version}</option>)}</select></label><label className="field-label">Project<select value={projectId} onChange={e=>setProjectId(e.target.value)}><option value="">No project selected</option>{projects.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label><label className="field-label brief-field">Creative brief<textarea rows={2} value={brief} onChange={e=>setBrief(e.target.value)} placeholder="Describe the idea, audience, intent and desired outcome…" required/></label><button className="primary-button" disabled={busy||!brief.trim()||!workflowKey}><Plus size={15}/> Create run</button></form>{error&&<div className="connection-banner">{error}</div>}{notice&&<div className="notice"><Check size={14}/>{notice}<button onClick={()=>setNotice("")}><X size={13}/></button></div>}<div className="panel-list-heading"><b>Production runs</b><span>{runs.length} records</span></div>{loading?<div className="empty-state">Loading production runs…</div>:runs.length===0?<div className="empty-state"><div className="empty-icon"><Activity size={22}/></div><b>No production runs yet</b><span>Create a run above to start the preproduction pipeline.</span></div>:<div className="run-list">{runs.map(run=><article className="run-card" key={run.id}><div className="run-top"><div><b>{run.workflow_key}</b><small>{new Date(run.created_at).toLocaleString()}</small></div><Status value={run.status}/></div><div className="run-steps">{run.steps.map(step=><div className="run-step" key={step.task_id}><span className={`step-indicator step-${step.status}`}/><span>{step.step_key.replaceAll("_"," ")}</span>{step.approval_required&&<small>HUMAN APPROVAL</small>}<Status value={step.status}/></div>)}</div><div className="run-actions">{["running","queued","waiting_approval"].includes(run.status)&&<button className="secondary-button" disabled={busy} onClick={()=>void control(run.id,"pause")}><CirclePause size={14}/> Pause</button>}{["paused","pausing"].includes(run.status)&&<button className="secondary-button" disabled={busy} onClick={()=>void control(run.id,"resume")}><CirclePlay size={14}/> Resume</button>}{!["succeeded","failed","cancelled"].includes(run.status)&&<button className="danger-button" disabled={busy||run.steps.some(step=>step.status==="running")} onClick={()=>void control(run.id,"cancel")}>{run.steps.some(step=>step.status==="running")?"Wait for active step":"Cancel run"}</button>}</div></article>)}</div>}</section>;
}
export function AgentsPanel(){
 const [agents,setAgents]=useState<Agent[]>([]),[name,setName]=useState(""),[purpose,setPurpose]=useState(""),[prompt,setPrompt]=useState(""),[loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState(""),[notice,setNotice]=useState("");
 async function load(){setLoading(true);try{const d=await api<{items:Agent[]}>("/api/v1/agents?limit=100");setAgents(d.items??[]);setError("");}catch(e){setError(e instanceof Error?e.message:"Could not load agents");}finally{setLoading(false);}}
 useEffect(()=>{void load();},[]);
 async function create(e:FormEvent){e.preventDefault();setBusy(true);setError("");try{const slug=name.toLowerCase().trim().replace(/[^a-z0-9]+/g,"-").replace(/^-|-$/g,"").slice(0,100)+"-"+Math.random().toString(36).slice(2,7);await api("/api/v1/agents",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({slug,name:name.trim(),purpose:purpose.trim(),system_prompt:prompt,permissions:["ai.generate"],max_cost_per_run_usd:0.25,monthly_budget_usd:5})});setName("");setPurpose("");setPrompt("");setNotice("Draft agent created. Configure a provider and model before enabling it.");await load();}catch(e){setError(e instanceof Error?e.message:"Could not create agent");}finally{setBusy(false);}}
 async function toggle(agent:Agent){setBusy(true);try{await api(`/api/v1/agents/${agent.id}/${agent.status==="enabled"?"disable":"enable"}`,{method:"POST"});await load();}catch(e){setError(e instanceof Error?e.message:"Agent action failed");}finally{setBusy(false);}}
 return <section className="workspace-panel"><PanelHeader eyebrow="AGENT MANAGER" title="AI agents" description="Create controlled agent profiles. Runtime execution remains gated by provider setup, pricing and budgets." onRefresh={()=>void load()}/><form className="agent-create" onSubmit={create}><div className="form-title"><Sparkles size={16}/> Create an agent profile</div><div className="form-grid"><label className="field-label">Agent name<input value={name} onChange={e=>setName(e.target.value)} placeholder="Research analyst" minLength={2} required/></label><label className="field-label">Purpose<input value={purpose} onChange={e=>setPurpose(e.target.value)} placeholder="Research and synthesize evidence" minLength={5} required/></label></div><label className="field-label">System prompt<textarea rows={3} value={prompt} onChange={e=>setPrompt(e.target.value)} placeholder="Define role, boundaries, expected output and source discipline…"/></label><div className="form-foot"><span><ShieldCheck size={14}/> Starts as draft · no provider call</span><button className="primary-button" disabled={busy||!name.trim()||!purpose.trim()}><Plus size={15}/> Create draft</button></div></form>{error&&<div className="connection-banner">{error}</div>}{notice&&<div className="notice"><Check size={14}/>{notice}<button onClick={()=>setNotice("")}><X size={13}/></button></div>}<div className="panel-list-heading"><b>Agent registry</b><span>{agents.length} agents</span></div>{loading?<div className="empty-state">Loading agents…</div>:agents.length===0?<div className="empty-state"><div className="empty-icon"><Sparkles size={22}/></div><b>No agents configured</b><span>Create a draft profile to begin.</span></div>:<div className="agent-grid">{agents.map(agent=><article className="agent-card" key={agent.id}><div className="agent-card-top"><div className="agent-symbol"><Sparkles size={18}/></div><Status value={agent.status}/></div><h3>{agent.name}</h3><p>{agent.purpose}</p><div className="agent-meta"><span>v{agent.version}</span><span>{agent.provider_id?"Provider configured":"No provider"}</span><span>{agent.tools.length} tool grants</span></div><button className="secondary-button" disabled={busy||(!agent.provider_id||!agent.model_id)&&agent.status!=="enabled"} onClick={()=>void toggle(agent)}>{agent.status==="enabled"?"Disable agent":"Enable agent"}</button></article>)}</div>}</section>;
}
export function AssetsPanel({projects}:{projects:Project[]}){
 const [projectId,setProjectId]=useState(projects[0]?.id??""),[assets,setAssets]=useState<Asset[]>([]),[loading,setLoading]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(""),[notice,setNotice]=useState("");
 useEffect(()=>{if(!projectId&&projects.length)setProjectId(projects[0].id);},[projects,projectId]);
 async function load(id=projectId){if(!id){setAssets([]);return;}setLoading(true);try{setAssets(await api<Asset[]>(`/api/v1/projects/${id}/assets`));setError("");}catch(e){setError(e instanceof Error?e.message:"Could not load assets");}finally{setLoading(false);}}
 useEffect(()=>{void load(projectId);},[projectId]);
 async function upload(e:FormEvent<HTMLFormElement>){e.preventDefault();const form=e.currentTarget;const file=(form.elements.namedItem("asset") as HTMLInputElement).files?.[0];if(!file||!projectId)return;const data=new FormData();data.append("file",file);setBusy(true);try{await api(`/api/v1/projects/${projectId}/assets`,{method:"POST",body:data});form.reset();setNotice("Asset uploaded and attached to project.");await load();}catch(e){setError(e instanceof Error?e.message:"Upload failed");}finally{setBusy(false);}}
 async function detach(linkId:string){if(!projectId)return;setBusy(true);try{await api(`/api/v1/projects/${projectId}/assets/${linkId}`,{method:"DELETE"});await load();}catch(e){setError(e instanceof Error?e.message:"Could not detach asset");}finally{setBusy(false);}}
 return <section className="workspace-panel"><PanelHeader eyebrow="ASSET LIBRARY" title="Assets" description="Upload and organize project files in the local content-addressed storage layer." onRefresh={()=>void load()}/>{projects.length===0?<div className="empty-state">Create a project before adding assets.</div>:<><div className="asset-toolbar"><label className="field-label">Project<select value={projectId} onChange={e=>setProjectId(e.target.value)}>{projects.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label><form className="upload-form" onSubmit={upload}><input type="file" name="asset" required/><button className="primary-button" disabled={busy}><Upload size={14}/> Upload asset</button></form></div>{error&&<div className="connection-banner">{error}</div>}{notice&&<div className="notice">{notice}</div>}<div className="asset-list">{loading?"Loading assets…":assets.length?assets.map(asset=><div className="asset-row" key={asset.id}><div className="asset-icon"><FolderOpen size={17}/></div><div className="asset-main"><b>{asset.filename}</b><small>{asset.mime_type} · {(asset.size_bytes/1024).toFixed(1)} KB</small></div><button className="danger-button" disabled={busy} onClick={()=>void detach(asset.id)}>Detach</button></div>):<div className="empty-state">No assets attached to this project yet.</div>}</div></>}</section>;
}
export function ComingSoonPanel({title,description}:{title:string;description:string}){return <section className="workspace-panel"><div className="coming-soon"><div className="empty-icon"><Sparkles size={24}/></div><span className="eyebrow">STUDIO MODULE</span><h2>{title}</h2><p>{description}</p><span className="module-state">Planned module · implementation staged</span></div></section>}

type ResearchSource={id:string;source_type:string;title:string;asset_id?:string|null;canonical_url:string|null;author:string|null;publisher:string|null;summary:string|null;project_ids:string[];created_at:string};
type ResearchEvidence={id:string;source_id:string;evidence_type:string;excerpt:string;locator:string|null;relationship?:string;note?:string};
type ResearchClaim={id:string;project_id:string;statement:string;claim_type:string;status:string;evidence:ResearchEvidence[]};

export function ResearchPanel({projects}:{projects:Project[]}) {
 const [projectId,setProjectId]=useState(projects[0]?.id??"");
 const [availableAssets,setAvailableAssets]=useState<Asset[]>([]);
 const [selectedAssetId,setSelectedAssetId]=useState("");
 const [sources,setSources]=useState<ResearchSource[]>([]);
 const [claims,setClaims]=useState<ResearchClaim[]>([]);
 const [sourceType,setSourceType]=useState("url");
 const [title,setTitle]=useState(""),[url,setUrl]=useState(""),[author,setAuthor]=useState(""),[summary,setSummary]=useState("");
 const [claimText,setClaimText]=useState(""),[claimType,setClaimType]=useState("factual");
 const [expanded,setExpanded]=useState("");
 const [evidenceBySource,setEvidenceBySource]=useState<Record<string,ResearchEvidence[]>>({});
 const [excerpt,setExcerpt]=useState(""),[locator,setLocator]=useState(""),[evidenceType,setEvidenceType]=useState("quote");
 const [selectedClaim,setSelectedClaim]=useState(""),[relationship,setRelationship]=useState("supports");
 const [searchText,setSearchText]=useState(""),[searchResults,setSearchResults]=useState<ResearchSearchResponse|null>(null),[searchBusy,setSearchBusy]=useState(false);
 const [loading,setLoading]=useState(true),[busy,setBusy]=useState(false),[error,setError]=useState(""),[notice,setNotice]=useState("");

 async function load(){
  setLoading(true);setError("");
  try{
   const sourceQuery=projectId?"?limit=100&project_id="+encodeURIComponent(projectId):"?limit=100";
   const sourcePage=await api<{items:ResearchSource[]}>("/api/v1/research/sources"+sourceQuery);
   const claimPage=projectId?await api<{items:ResearchClaim[]}>("/api/v1/research/claims?project_id="+encodeURIComponent(projectId)+"&limit=100"):{items:[] as ResearchClaim[]};
   setSources(sourcePage.items??[]);setClaims(claimPage.items??[]);
   if(selectedClaim&&!claimPage.items.some(c=>c.id===selectedClaim))setSelectedClaim("");
  }catch(e){setError(e instanceof Error?e.message:"Could not load Research Vault");}
  finally{setLoading(false);}
 }
 useEffect(()=>{if(!projectId&&projects.length)setProjectId(projects[0].id);},[projects,projectId]);
 useEffect(()=>{
  setSelectedAssetId("");
  if(!projectId){setAvailableAssets([]);return;}
  let active=true;
  api<Asset[]>("/api/v1/projects/"+projectId+"/assets").then(items=>{if(active)setAvailableAssets(items??[]);}).catch(()=>{if(active)setAvailableAssets([]);});
  return ()=>{active=false;};
 },[projectId]);
 useEffect(()=>{void load();},[projectId]);

 async function searchVault(e:FormEvent){
  e.preventDefault();if(searchText.trim().length<2)return;
  setSearchBusy(true);setError("");
  try{
   const params=new URLSearchParams({q:searchText.trim(),limit:"20"});
   if(projectId)params.set("project_id",projectId);
   setSearchResults(await api<ResearchSearchResponse>("/api/v1/research/search?"+params.toString()));
  }catch(e){setError(e instanceof Error?e.message:"Research search failed");}
  finally{setSearchBusy(false);}
 }
 function clearSearch(){setSearchText("");setSearchResults(null);}
 async function createSource(e:FormEvent){
  e.preventDefault();if(!title.trim())return;
  if(sourceType==="url"&&!url.trim()){setError("A URL is required for this source type.");return;}
  setBusy(true);setError("");setNotice("");
  try{
   await api("/api/v1/research/sources",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({
    source_type:sourceType,title:title.trim(),canonical_url:sourceType==="url"?url.trim():null,
    author:author.trim()||null,summary:summary.trim()||null,project_id:projectId||null,
    asset_id:selectedAssetId||null
   })});
   setTitle("");setUrl("");setAuthor("");setSummary("");setNotice("Source saved with its provenance metadata.");await load();
  }catch(e){setError(e instanceof Error?e.message:"Could not save source");}
  finally{setBusy(false);}
 }
 async function extractDocument(sourceId:string){
  setBusy(true);setError("");setNotice("");
  try{
   const result=await api<{evidence_created:number;already_present_or_empty:number;format:string}>("/api/v1/research/sources/"+sourceId+"/extract",{method:"POST"});
   setNotice(result.evidence_created+" evidence segments extracted from "+result.format.toUpperCase()+". "+result.already_present_or_empty+" were empty or already present.");
   const page=await api<{items:ResearchEvidence[]}>("/api/v1/research/sources/"+sourceId+"/evidence?limit=100");
   setEvidenceBySource(prev=>({...prev,[sourceId]:page.items??[]}));setExpanded(sourceId);
  }catch(e){setError(e instanceof Error?e.message:"Document extraction failed");}
  finally{setBusy(false);}
 }
 async function toggleEvidence(sourceId:string){
  if(expanded===sourceId){setExpanded("");return;}
  setExpanded(sourceId);setError("");
  try{
   const page=await api<{items:ResearchEvidence[]}>("/api/v1/research/sources/"+sourceId+"/evidence?limit=100");
   setEvidenceBySource(prev=>({...prev,[sourceId]:page.items??[]}));
  }catch(e){setError(e instanceof Error?e.message:"Could not load evidence");}
 }
 async function addEvidence(e:FormEvent,sourceId:string){
  e.preventDefault();if(!excerpt.trim())return;
  setBusy(true);setError("");
  try{
   await api("/api/v1/research/sources/"+sourceId+"/evidence",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({
    evidence_type:evidenceType,excerpt:excerpt.trim(),locator:locator.trim()||null
   })});
   setExcerpt("");setLocator("");
   const page=await api<{items:ResearchEvidence[]}>("/api/v1/research/sources/"+sourceId+"/evidence?limit=100");
   setEvidenceBySource(prev=>({...prev,[sourceId]:page.items??[]}));
   setNotice("Evidence recorded. Its source and locator are preserved.");
  }catch(e){setError(e instanceof Error?e.message:"Could not record evidence");}
  finally{setBusy(false);}
 }
 async function createClaim(e:FormEvent){
  e.preventDefault();if(!projectId||!claimText.trim())return;
  setBusy(true);setError("");
  try{
   await api("/api/v1/research/claims",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({
    project_id:projectId,statement:claimText.trim(),claim_type:claimType
   })});
   setClaimText("");setNotice("Draft claim created. Attach evidence before accepting it.");await load();
  }catch(e){setError(e instanceof Error?e.message:"Could not create claim");}
  finally{setBusy(false);}
 }
 async function attachEvidence(item:ResearchEvidence){
  if(!selectedClaim)return;
  setBusy(true);setError("");
  try{
   await api("/api/v1/research/claims/"+selectedClaim+"/evidence/"+item.id,{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({relationship})});
   setNotice("Evidence linked to the selected claim.");await load();
  }catch(e){setError(e instanceof Error?e.message:"Could not link evidence");}
  finally{setBusy(false);}
 }
 async function reviewClaim(claim:ResearchClaim,status:"accepted"|"rejected"|"reviewed"){
  setBusy(true);setError("");
  try{
   await api("/api/v1/research/claims/"+claim.id,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({status})});
   setNotice(status==="accepted"?"Claim accepted with supporting evidence.":status==="rejected"?"Claim rejected with contradicting evidence.":"Claim marked as reviewed.");
   await load();
  }catch(e){setError(e instanceof Error?e.message:"Claim review failed");}
  finally{setBusy(false);}
 }
 return <section className="workspace-panel">
  <PanelHeader eyebrow="PROVENANCE & EVIDENCE" title="Research Vault" description="Curate sources, preserve exact evidence locations and connect claims to what supports or contradicts them." onRefresh={()=>void load()}/>
  <div className="research-toolbar">
   <label className="field-label">Project scope
    <select value={projectId} onChange={e=>setProjectId(e.target.value)}>
     <option value="">Universal vault · all sources</option>
     {projects.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}
    </select>
   </label>
   <span className="research-count"><BookOpen size={14}/>{sources.length} sources <i>·</i> {claims.length} claims</span>
  </div>
  <form className="research-search" onSubmit={searchVault}>
   <div><b>Search the knowledge vault</b><small>Search source metadata, exact excerpts, locators and project claims.</small></div>
   <input value={searchText} onChange={e=>setSearchText(e.target.value)} placeholder="Search a phrase, name, evidence or claim…" maxLength={200}/>
   <button className="primary-button" disabled={searchBusy||searchText.trim().length<2}><BookOpen size={14}/>{searchBusy?"Searching…":"Search"}</button>
   {searchResults&&<button type="button" className="secondary-button" onClick={clearSearch}>Clear</button>}
  </form>
  {searchResults&&<div className="research-search-results">
   <div className="panel-list-heading"><b>Search results for “{searchResults.query}”</b><span>{searchResults.totals.sources+searchResults.totals.evidence+searchResults.totals.claims} matches</span></div>
   {searchResults.totals.sources+searchResults.totals.evidence+searchResults.totals.claims===0?<div className="research-muted">No matching records in this scope.</div>:<>
    {[...searchResults.sources,...searchResults.evidence,...searchResults.claims].map(item=><article className="research-search-hit" key={item.kind+item.id}>
     <div><Status value={item.kind}/><b>{item.title}</b></div>
     {item.excerpt&&<p>{item.excerpt}</p>}
     <small>{item.kind==="evidence"?(item.locator||"Evidence excerpt"):item.kind==="claim"?(item.claim_type+" · "+item.status):(item.source_type||"Source record")}</small>
    </article>)}
   </>}
  </div>}
  <div className="research-layout">
   <div className="research-main">
    <form className="research-create" onSubmit={createSource}>
     <div className="form-title"><Plus size={16}/> Register a source</div>
     <div className="form-grid">
      <label className="field-label">Source type
       <select value={sourceType} onChange={e=>setSourceType(e.target.value)}>
        <option value="url">Web URL</option><option value="document">Document</option><option value="note">Research note</option><option value="transcript">Transcript</option><option value="dataset">Dataset</option><option value="other">Other</option>
       </select>
      </label>
      <label className="field-label">Title<input value={title} onChange={e=>setTitle(e.target.value)} placeholder="Source title" maxLength={300} required/></label>
     </div>
     {sourceType==="url"&&<label className="field-label">Canonical URL<input type="url" value={url} onChange={e=>setUrl(e.target.value)} placeholder="https://…" required/></label>}
     <div className="form-grid">
      <label className="field-label">Author / creator<input value={author} onChange={e=>setAuthor(e.target.value)} placeholder="Optional"/></label>
      <label className="field-label">Short summary<input value={summary} onChange={e=>setSummary(e.target.value)} placeholder="Optional context"/></label>
     </div>
     {projectId&&<label className="field-label">Attach a stored file · upload files first in Assets
      <select value={selectedAssetId} onChange={e=>setSelectedAssetId(e.target.value)}>
       <option value="">No file attached</option>
       {availableAssets.map(asset=><option key={asset.asset_id} value={asset.asset_id}>{asset.filename} · {asset.mime_type}</option>)}
      </select>
     </label>}
     <div className="form-foot"><span><ShieldCheck size={14}/> Metadata only · no background URL fetching</span><button className="primary-button" disabled={busy||!title.trim()}><Plus size={14}/> Save source</button></div>
    </form>
    {error&&<div className="connection-banner">{error}</div>}
    {notice&&<div className="notice"><Check size={14}/>{notice}<button onClick={()=>setNotice("")}><X size={13}/></button></div>}
    <div className="panel-list-heading"><b>Source library</b><span>{sources.length} records</span></div>
    {loading?<div className="empty-state">Loading sources…</div>:sources.length===0?<div className="empty-state"><div className="empty-icon"><BookOpen size={22}/></div><b>No sources in this view</b><span>Register a URL, document or research note to begin building the evidence base.</span></div>:
     <div className="research-source-list">{sources.map(source=><article className="research-source-card" key={source.id}>
      <div className="research-source-top"><div className="research-source-icon"><FileText size={17}/></div><div className="research-source-title"><div><b>{source.title}</b><Status value={source.source_type}/></div><small>{source.author||source.publisher||"Creator not recorded"} · {new Date(source.created_at).toLocaleDateString()}</small></div></div>
      {source.canonical_url&&<a className="research-source-url" href={source.canonical_url} target="_blank" rel="noreferrer">{source.canonical_url}</a>}
      {source.summary&&<p>{source.summary}</p>}
      <div className="research-source-actions">{source.source_type==="document"&&source.asset_id&&<button className="secondary-button" disabled={busy} onClick={()=>void extractDocument(source.id)}><FileText size={14}/> Extract text</button>}<button className="secondary-button" onClick={()=>void toggleEvidence(source.id)}><BookOpen size={14}/>{expanded===source.id?"Hide evidence":"Evidence & excerpts"}</button><span>{source.project_ids.length} project links</span></div>
      {expanded===source.id&&<div className="research-evidence-area">
       <form className="research-evidence-form" onSubmit={e=>void addEvidence(e,source.id)}>
        <label className="field-label">Evidence type<select value={evidenceType} onChange={e=>setEvidenceType(e.target.value)}><option value="quote">Direct quote</option><option value="data">Data point</option><option value="observation">Observation</option><option value="transcript">Transcript excerpt</option><option value="other">Other</option></select></label>
        <label className="field-label">Exact excerpt<textarea rows={3} value={excerpt} onChange={e=>setExcerpt(e.target.value)} placeholder="Paste the exact passage or data point…" required/></label>
        <div className="form-foot"><label className="field-label locator-field">Locator<input value={locator} onChange={e=>setLocator(e.target.value)} placeholder="Page 4 · 00:32 · Table 2"/></label><button className="primary-button" disabled={busy||!excerpt.trim()}><Plus size={14}/> Add evidence</button></div>
       </form>
       {(evidenceBySource[source.id]??[]).map(item=><div className="research-evidence-item" key={item.id}><div><span>{item.evidence_type}</span>{item.locator&&<small>{item.locator}</small>}</div><p>{item.excerpt}</p><div className="research-evidence-link"><select value={selectedClaim} onChange={e=>setSelectedClaim(e.target.value)} disabled={!claims.length}><option value="">Select project claim…</option>{claims.map(claim=><option key={claim.id} value={claim.id}>{claim.statement.slice(0,80)}</option>)}</select><select value={relationship} onChange={e=>setRelationship(e.target.value)}><option value="supports">Supports</option><option value="contradicts">Contradicts</option><option value="contextualizes">Context</option></select><button className="secondary-button" disabled={busy||!selectedClaim} onClick={()=>void attachEvidence(item)}><Link2 size={13}/> Link</button></div></div>)}
       {(evidenceBySource[source.id]??[]).length===0&&<small className="research-muted">No evidence excerpts recorded for this source yet.</small>}
      </div>}
     </article>)}</div>}
   </div>
   <aside className="research-claims">
    <form className="research-create" onSubmit={createClaim}>
     <div className="form-title"><Check size={16}/> Capture a research claim</div>
     <label className="field-label">Claim statement<textarea rows={3} value={claimText} onChange={e=>setClaimText(e.target.value)} placeholder="State one testable or interpretable claim…" required disabled={!projectId}/></label>
     <label className="field-label">Claim type<select value={claimType} onChange={e=>setClaimType(e.target.value)}><option value="factual">Factual</option><option value="interpretive">Interpretive</option><option value="forecast">Forecast</option><option value="creative">Creative premise</option><option value="other">Other</option></select></label>
     <button className="primary-button" disabled={busy||!projectId||!claimText.trim()}><Plus size={14}/> Create draft claim</button>
     {!projectId&&<small className="research-muted">Select a project to create claims.</small>}
    </form>
    <div className="panel-list-heading"><b>Claims & review</b><span>{claims.length}</span></div>
    {claims.length===0?<div className="empty-state compact-empty">Claims are organized within a project.</div>:claims.map(claim=><article className="research-claim-card" key={claim.id}>
     <div className="research-claim-top"><Status value={claim.status}/><span>{claim.claim_type}</span></div>
     <p>{claim.statement}</p><small>{claim.evidence.length} linked evidence items</small>
     {claim.evidence.length>0&&<div className="claim-evidence-summary">{claim.evidence.map(ev=><span key={ev.id}>{ev.relationship}</span>)}</div>}
     <div className="claim-review-actions">
      {claim.status!=="accepted"&&claim.evidence.some(ev=>ev.relationship==="supports")&&<button className="secondary-button" disabled={busy} onClick={()=>void reviewClaim(claim,"accepted")}>Accept</button>}
      {claim.status!=="rejected"&&claim.evidence.some(ev=>ev.relationship==="contradicts")&&<button className="secondary-button" disabled={busy} onClick={()=>void reviewClaim(claim,"rejected")}>Reject</button>}
      {claim.status==="draft"&&claim.evidence.length>0&&<button className="secondary-button" disabled={busy} onClick={()=>void reviewClaim(claim,"reviewed")}>Mark reviewed</button>}
     </div>
    </article>)}
   </aside>
  </div>
 </section>;
}


type StoryRecord={id:string;project_id:string;title:string;format:string;genre:string|null;target_audience:string|null;premise:string|null;logline:string|null;synopsis:string|null;creative_intent:string|null;status:string;version:number;scene_count:number;scenes:StoryScene[];revisions?:Array<{id:string;version:number;change_note:string|null;created_at:string}>};
type StoryScene={id:string;position:number;title:string;slugline:string|null;summary:string|null;dramatic_purpose:string|null;location:string|null;time_of_day:string|null;beats:string[];body:string|null;version:number};
export function StoryPanel({projects}:{projects:Project[]}){
 const [projectId,setProjectId]=useState(projects[0]?.id??""),[stories,setStories]=useState<StoryRecord[]>([]),[selected,setSelected]=useState<StoryRecord|null>(null),[title,setTitle]=useState(""),[format,setFormat]=useState("short_film"),[logline,setLogline]=useState(""),[premise,setPremise]=useState(""),[sceneTitle,setSceneTitle]=useState(""),[sceneSummary,setSceneSummary]=useState(""),[loading,setLoading]=useState(false),[busy,setBusy]=useState(false),[error,setError]=useState(""),[notice,setNotice]=useState("");
 async function load(id=projectId){if(!id){setStories([]);setSelected(null);return;}setLoading(true);try{const d=await api<{items:StoryRecord[]}>("/api/v1/stories?project_id="+id+"&limit=100");setStories(d.items??[]);if(selected){const fresh=(d.items??[]).find(x=>x.id===selected.id);setSelected(fresh??null);}setError("");}catch(e){setError(e instanceof Error?e.message:"Could not load stories");}finally{setLoading(false);}}
 useEffect(()=>{if(!projectId&&projects.length)setProjectId(projects[0].id);},[projects,projectId]);useEffect(()=>{void load(projectId);},[projectId]);
 async function refreshSelected(id:string){const fresh=await api<StoryRecord>("/api/v1/stories/"+id);setSelected(fresh);const d=await api<{items:StoryRecord[]}>("/api/v1/stories?project_id="+projectId+"&limit=100");setStories(d.items??[]);}
 async function create(e:FormEvent){e.preventDefault();if(!projectId||!title.trim())return;setBusy(true);setError("");try{const s=await api<StoryRecord>("/api/v1/stories",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({project_id:projectId,title:title.trim(),format,logline:logline.trim()||null,premise:premise.trim()||null})});setTitle("");setLogline("");setPremise("");setSelected(s);setNotice("Story dossier created with its first immutable revision.");const d=await api<{items:StoryRecord[]}>("/api/v1/stories?project_id="+projectId+"&limit=100");setStories(d.items??[]);}catch(e){setError(e instanceof Error?e.message:"Story creation failed");}finally{setBusy(false);}}
 async function addScene(e:FormEvent){e.preventDefault();if(!selected||!sceneTitle.trim())return;setBusy(true);setError("");try{await api("/api/v1/stories/"+selected.id+"/scenes",{method:"POST",headers:{"Content-Type":"application/json"},body:JSON.stringify({title:sceneTitle.trim(),summary:sceneSummary.trim()||null})});setSceneTitle("");setSceneSummary("");await refreshSelected(selected.id);}catch(e){setError(e instanceof Error?e.message:"Could not add scene");}finally{setBusy(false);}}
 async function removeScene(scene:StoryScene){if(!selected)return;setBusy(true);try{const fresh=await api<StoryRecord>("/api/v1/stories/"+selected.id+"/scenes/"+scene.id,{method:"DELETE"});setSelected(fresh);const d=await api<{items:StoryRecord[]}>("/api/v1/stories?project_id="+projectId+"&limit=100");setStories(d.items??[]);}catch(e){setError(e instanceof Error?e.message:"Could not remove scene");}finally{setBusy(false);}}
 async function updateStatus(status:string){if(!selected)return;setBusy(true);try{const fresh=await api<StoryRecord>("/api/v1/stories/"+selected.id,{method:"PATCH",headers:{"Content-Type":"application/json"},body:JSON.stringify({expected_version:selected.version,status,change_note:"Story status changed"})});setSelected(fresh);const d=await api<{items:StoryRecord[]}>("/api/v1/stories?project_id="+projectId+"&limit=100");setStories(d.items??[]);}catch(e){setError(e instanceof Error?e.message:"Could not update story");}finally{setBusy(false);}}
 return <section className="workspace-panel"><div className="panel-header"><div><span className="eyebrow">STORY DEVELOPMENT</span><h2>Story Engine</h2><p>Develop a story dossier and build its scene outline. Every change creates a recoverable immutable revision.</p></div><button className="secondary-button" onClick={()=>void load()}><RefreshCw size={14}/> Refresh</button></div>
 {projects.length===0?<div className="empty-state">Create a project before starting a story.</div>:<><div className="asset-toolbar"><label className="field-label">Project<select value={projectId} onChange={e=>setProjectId(e.target.value)}>{projects.map(p=><option key={p.id} value={p.id}>{p.name}</option>)}</select></label><span className="research-muted">Story records: {stories.length}</span></div>
 <div className="story-layout"><div className="story-sidebar"><form className="research-create" onSubmit={create}><div className="form-title"><Sparkles size={15}/> New story dossier</div><label className="field-label">Title<input value={title} onChange={e=>setTitle(e.target.value)} maxLength={240} required placeholder="Working title"/></label><label className="field-label">Format<select value={format} onChange={e=>setFormat(e.target.value)}><option value="short_film">Short film</option><option value="feature_film">Feature film</option><option value="series">Series</option><option value="documentary">Documentary</option><option value="animation">Animation</option><option value="novel">Novel</option><option value="short_story">Short story</option><option value="advertisement">Advertisement</option><option value="other">Other</option></select></label><label className="field-label">Logline<input value={logline} onChange={e=>setLogline(e.target.value)} maxLength={1000} placeholder="The story in one compelling sentence"/></label><label className="field-label">Premise<textarea rows={3} value={premise} onChange={e=>setPremise(e.target.value)} maxLength={12000} placeholder="Core dramatic idea and central conflict"/></label><button className="primary-button" disabled={busy||!title.trim()}><Plus size={14}/> Create story</button></form><div className="story-list">{loading?"Loading stories…":stories.length?stories.map(s=><button key={s.id} className={selected?.id===s.id?"story-list-item selected":"story-list-item"} onClick={()=>{setSelected(s);void api<StoryRecord>("/api/v1/stories/"+s.id).then(setSelected).catch(e=>setError(e.message));}}><b>{s.title}</b><small>{s.format.replaceAll("_"," ")} · v{s.version} · {s.scene_count} scenes</small></button>):<div className="empty-state compact-empty">No stories in this project yet.</div>}</div></div>
 <div className="story-editor">{error&&<div className="connection-banner">{error}</div>}{notice&&<div className="notice"><Check size={14}/>{notice}<button onClick={()=>setNotice("")}><X size={13}/></button></div>}{!selected?<div className="empty-state"><div className="empty-icon"><BookOpen size={22}/></div><b>Select or create a story</b><span>Your story dossier, outline and revision history will appear here.</span></div>:<><div className="story-editor-head"><div><span className="eyebrow">STORY DOSSIER · VERSION {selected.version}</span><h3>{selected.title}</h3><p>{selected.logline||"No logline recorded yet."}</p></div><select value={selected.status} disabled={busy} onChange={e=>void updateStatus(e.target.value)}>{["development","outlined","drafting","review","locked","archived"].map(s=><option key={s} value={s}>{s.replaceAll("_"," ")}</option>)}</select></div><div className="story-meta-grid"><div><small>FORMAT</small><b>{selected.format.replaceAll("_"," ")}</b></div><div><small>GENRE</small><b>{selected.genre||"Not set"}</b></div><div><small>TARGET AUDIENCE</small><b>{selected.target_audience||"Not set"}</b></div><div><small>SCENES</small><b>{selected.scene_count}</b></div></div>{selected.premise&&<div className="story-premise"><small>PREMISE</small><p>{selected.premise}</p></div>}<div className="panel-list-heading"><b>Scene outline</b><span>{selected.scenes.length} scenes · ordered</span></div><div className="story-scenes">{selected.scenes.map(scene=><article className="story-scene" key={scene.id}><div className="story-scene-number">{String(scene.position).padStart(2,"0")}</div><div className="story-scene-main"><b>{scene.title}</b><small>{scene.slugline||"Slugline not set"} · v{scene.version}</small>{scene.summary&&<p>{scene.summary}</p>}</div><button className="danger-button" disabled={busy} onClick={()=>void removeScene(scene)}>Remove</button></article>)}{!selected.scenes.length&&<div className="empty-state compact-empty">No scenes yet. Add the opening scene to begin the outline.</div>}</div><form className="story-add-scene" onSubmit={addScene}><label className="field-label">Scene title<input value={sceneTitle} onChange={e=>setSceneTitle(e.target.value)} maxLength={240} required placeholder="e.g. The signal arrives"/></label><label className="field-label">Scene summary<textarea rows={2} value={sceneSummary} onChange={e=>setSceneSummary(e.target.value)} maxLength={12000} placeholder="What changes in this scene?"/></label><button className="primary-button" disabled={busy||!sceneTitle.trim()}><Plus size={14}/> Add scene</button></form><div className="story-revisions"><b>Revision history</b>{(selected.revisions??[]).map(r=><span key={r.id}>v{r.version} · {r.change_note||"Saved revision"} · {new Date(r.created_at).toLocaleString()}</span>)}</div></>}</div></div></> }</section>;
}
