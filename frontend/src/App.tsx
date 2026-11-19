import { useEffect, useMemo, useState } from "react";
import { AgentsPanel, AssetsPanel, ComingSoonPanel, ProductionPanel, ResearchPanel } from "./WorkspacePanels";
import {
  Activity, ArrowUpRight, AudioLines, BookOpen, Check, ChevronDown,
  CircleHelp, Clapperboard, Command, FolderKanban, Gauge, Image, Layers3,
  Plus, Search, Settings2, ShieldCheck, Sparkles, Video, X
} from "lucide-react";

type Project = {
  id: string; slug: string; name: string; description: string | null;
  project_type: string; status: string; version: number; created_at: string;
};
type ProjectPage = { items: Project[]; total: number; limit: number; offset: number };

const nav = [
  { label: "Overview", icon: Gauge },
  { label: "Projects", icon: FolderKanban },
  { label: "Production room", icon: Clapperboard },
  { label: "Research vault", icon: BookOpen },
  { label: "Characters & worlds", icon: Layers3 },
  { label: "Assets", icon: Image },
  { label: "Video & audio", icon: AudioLines },
  { label: "AI agents", icon: Sparkles },
  { label: "Compliance", icon: ShieldCheck },
  { label: "Settings", icon: Settings2 }
];

function App() {
  const [projects, setProjects] = useState<Project[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [active, setActive] = useState("Overview");
  const [query, setQuery] = useState("");
  const [showCreate, setShowCreate] = useState(false);
  const [name, setName] = useState("");
  const [description, setDescription] = useState("");
  const [creating, setCreating] = useState(false);
  const [notice, setNotice] = useState("");

  async function loadProjects() {
    setLoading(true);
    setError("");
    try {
      const response = await fetch("/api/v1/projects?limit=50");
      if (!response.ok) throw new Error(response.status === 404 ? "API route not found" : `API error (${response.status})`);
      const data = await response.json() as ProjectPage;
      setProjects(data.items ?? []);
      setTotal(data.total ?? 0);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not connect to the local API");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void loadProjects(); }, []);

  const filtered = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!needle) return projects;
    return projects.filter(p => p.name.toLowerCase().includes(needle) || p.slug.toLowerCase().includes(needle));
  }, [projects, query]);

  async function createProject(event: React.FormEvent) {
    event.preventDefault();
    if (!name.trim()) return;
    setCreating(true);
    setNotice("");
    try {
      const response = await fetch("/api/v1/projects", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ name: name.trim(), description: description.trim() || null, project_type: "creative" })
      });
      const data = await response.json();
      if (!response.ok) throw new Error(data?.detail?.message ?? data?.detail ?? "Project could not be created");
      setName(""); setDescription(""); setShowCreate(false);
      setNotice("Project created successfully.");
      await loadProjects();
    } catch (err) {
      setNotice(err instanceof Error ? err.message : "Project creation failed.");
    } finally {
      setCreating(false);
    }
  }

  return (
    <div className="app-shell">
      <aside className="sidebar">
        <div className="brand">
          <div className="brand-mark"><Command size={19} /></div>
          <div><strong>MASOUD<span> AI</span></strong><small>CREATIVE STUDIO</small></div>
          <button className="icon-button sidebar-collapse" aria-label="Collapse sidebar"><ChevronDown size={16} /></button>
        </div>
        <button className="workspace-switch"><span className="workspace-avatar">M</span><span><b>Personal workspace</b><small>Local-first · Private</small></span><ChevronDown size={15} /></button>
        <div className="nav-label">WORKSPACE</div>
        <nav>
          {nav.map(item => {
            const Icon = item.icon;
            return <button key={item.label} className={active === item.label ? "nav-item active" : "nav-item"} onClick={() => setActive(item.label)}>
              <Icon size={17} strokeWidth={1.8} /><span>{item.label}</span>{item.label === "AI agents" && <span className="nav-dot" />}
            </button>;
          })}
        </nav>
        <div className="sidebar-bottom">
          <div className="storage-card"><div className="storage-heading"><span>LOCAL STORAGE</span><span>—</span></div><div className="storage-track"><i /></div><small>Usage appears when storage is connected</small></div>
          <div className="profile"><div className="profile-avatar">M</div><div><b>Studio owner</b><small>Administrator</small></div><button className="icon-button" aria-label="Profile menu"><ChevronDown size={15} /></button></div>
        </div>
      </aside>

      <main className="main-area">
        <header className="topbar">
          <div className="breadcrumbs"><span>Workspace</span><span className="slash">/</span><b>{active}</b></div>
          <div className="top-actions">
            <div className="system-status"><i /> LOCAL SYSTEM</div>
            <button className="icon-button help" aria-label="Help"><CircleHelp size={18} /></button>
            <div className="top-avatar">M</div>
          </div>
        </header>

        <div className="page-content">
          <section className="welcome-row">
            <div><div className="eyebrow"><Sparkles size={13} /> YOUR CREATIVE COMMAND CENTER</div><h1>{active === "Overview" ? "Make something meaningful." : active}</h1><p>One workspace for research, stories, visual development and production.</p></div>
            <button className="primary-button" onClick={() => setShowCreate(true)}><Plus size={17} /> New project</button>
          </section>

          {notice && <div className="notice"><Check size={15} />{notice}<button onClick={() => setNotice("")} aria-label="Dismiss"><X size={14} /></button></div>}
          {error && <div className="connection-banner"><Activity size={18} /><div><b>Backend connection unavailable</b><span>{error}. Start the FastAPI service on port 8000, then refresh.</span></div><button onClick={() => void loadProjects()}>Retry</button></div>}

          {(active === "Overview" || active === "Projects") && <>
          <section className="metric-grid">
            <article className="metric-card"><div className="metric-top"><span>ACTIVE PROJECTS</span><FolderKanban size={17} /></div><strong>{loading ? "—" : total}</strong><small>Across your workspace</small></article>
            <article className="metric-card"><div className="metric-top"><span>PRODUCTION RUNS</span><Clapperboard size={17} /></div><strong>—</strong><small>Orchestrator overview coming next</small></article>
            <article className="metric-card"><div className="metric-top"><span>AI AGENTS</span><Sparkles size={17} /></div><strong>—</strong><small>Runtime setup in progress</small></article>
            <article className="metric-card accent-card"><div className="metric-top"><span>STUDIO HEALTH</span><Activity size={17} /></div><strong>{error ? "Offline" : loading ? "Checking" : "Connected"}</strong><small>{error ? "API needs attention" : "Local workspace status"}</small></article>
          </section>

          <section className="section-block">
            <div className="section-heading"><div><span className="eyebrow">YOUR WORK</span><h2>Recent projects</h2></div><div className="project-tools"><label className="search-box"><Search size={15} /><input value={query} onChange={e => setQuery(e.target.value)} placeholder="Search projects..." /></label><button className="secondary-button" onClick={() => void loadProjects()}>Refresh</button></div></div>
            {loading ? <div className="empty-state"><div className="loader" /><b>Loading your workspace</b><span>Connecting to your local project library…</span></div> :
              filtered.length ? <div className="project-grid">{filtered.map(project => <article className="project-card" key={project.id}>
                <div className="project-art"><div className="art-orbit orbit-one" /><div className="art-orbit orbit-two" /><div className="art-core"><Clapperboard size={25} /></div><span className="project-type">{project.project_type}</span></div>
                <div className="project-info"><div className="project-title"><h3>{project.name}</h3><span className="project-status">{project.status}</span></div><p>{project.description || "No description yet. Open the project to add a creative brief."}</p><div className="project-footer"><span>v{project.version} · {new Date(project.created_at).toLocaleDateString()}</span><button aria-label={`Open ${project.name}`}><ArrowUpRight size={16} /></button></div></div>
              </article>)}</div> : <div className="empty-state"><div className="empty-icon"><FolderKanban size={23} /></div><b>{query ? "No matching projects" : "Your studio starts here"}</b><span>{query ? "Try another search term." : "Create your first project and bring your next idea into the studio."}</span>{!query && <button className="secondary-button" onClick={() => setShowCreate(true)}><Plus size={15} /> Create first project</button>}</div>}
          </section>

          <section className="pipeline-strip"><div className="pipeline-intro"><span className="eyebrow">CREATIVE PIPELINE</span><h2>From first thought to final cut.</h2><p>A connected workflow with human review at every important checkpoint.</p></div><div className="pipeline-steps">{[{n:"01",t:"Research",s:"Evidence & insight",i:BookOpen},{n:"02",t:"Story",s:"Script & structure",i:Sparkles},{n:"03",t:"Visuals",s:"Characters & shots",i:Image},{n:"04",t:"Production",s:"Image, video & audio",i:Video},{n:"05",t:"Review",s:"Quality & approval",i:ShieldCheck}].map(step => { const Icon = step.i; return <div className="pipeline-step" key={step.n}><span>{step.n}</span><Icon size={18}/><b>{step.t}</b><small>{step.s}</small></div>; })}</div></section>

          </>}
          {active === "Production room" && <ProductionPanel projects={projects}/>}
          {active === "AI agents" && <AgentsPanel/>}
          {active === "Assets" && <AssetsPanel projects={projects}/>}
          {active === "Research vault" && <ResearchPanel projects={projects}/>}
          {active === "Characters & worlds" && <ComingSoonPanel title="Characters & worlds" description="Character Bible, World Bible, model sheets and continuity tools are planned as a connected creative-development workspace."/>}
          {active === "Video & audio" && <ComingSoonPanel title="Video & audio" description="Media generation, audio, subtitles, editing and compositing will be integrated incrementally through the production pipeline."/>}
          {active === "Compliance" && <ComingSoonPanel title="Compliance" description="Originality, rights, platform policy and publishing-readiness checks will be added as a dedicated review layer."/>}
          {active === "Settings" && <ComingSoonPanel title="Studio settings" description="Local storage, provider configuration, security and workspace preferences will be exposed here as their management interfaces are completed."/>}
          <footer><span>MASOUD AI STUDIO <i>·</i> PRIVATE BY DESIGN</span><span>Full vision. Simplified architecture. Incremental implementation.</span></footer>
        </div>
      </main>

      {showCreate && <div className="modal-backdrop" onMouseDown={e => { if (e.target === e.currentTarget) setShowCreate(false); }}><form className="modal" onSubmit={createProject}>
        <div className="modal-heading"><div><span className="eyebrow">NEW WORKSPACE ITEM</span><h2>Create a project</h2></div><button type="button" className="icon-button" onClick={() => setShowCreate(false)} aria-label="Close"><X size={18}/></button></div>
        <label className="field-label">Project name<input autoFocus value={name} onChange={e => setName(e.target.value)} placeholder="e.g. The forgotten city" maxLength={160} required /></label>
        <label className="field-label">Creative brief <span>OPTIONAL</span><textarea value={description} onChange={e => setDescription(e.target.value)} placeholder="What are you making? What should the audience feel, learn or discover?" rows={4} maxLength={10000}/></label>
        <div className="modal-note"><ShieldCheck size={16}/> Your project is stored in your local studio database.</div>
        <div className="modal-actions"><button type="button" className="secondary-button" onClick={() => setShowCreate(false)}>Cancel</button><button className="primary-button" disabled={creating || !name.trim()}>{creating ? "Creating…" : <><Plus size={16}/> Create project</>}</button></div>
      </form></div>}
    </div>
  );
}

export default App;
