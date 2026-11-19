import { useEffect, useState } from "react";
import type { FormEvent } from "react";
import { Clock, GitBranch, Plus, RefreshCw, ShieldCheck } from "lucide-react";

type Project = { id: string; name: string };
type Scene = { id: string; title: string; position: number };
type Story = { id: string; title: string; scenes: Scene[] };
type EventItem = {
  id: string; scene_id: string | null; event_type: string; title: string;
  description: string | null; in_world_time: string | null;
  chronology_note: string | null; active: boolean; version: number;
};
type Relation = { id: string; before_event_id: string; after_event_id: string; note: string | null };
type Analysis = { is_consistent: boolean; ordered_event_ids: string[]; cycle_event_ids: string[]; relations_count: number; note: string };

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  const data = await response.json().catch(() => null);
  if (!response.ok) {
    const detail = data?.detail;
    throw new Error(typeof detail === "object" ? (detail.code ?? "Request failed") : String(detail ?? "Request failed"));
  }
  return data as T;
}

export function TimelinePanel({ projects }: { projects: Project[] }) {
  const [projectId, setProjectId] = useState(projects[0]?.id ?? "");
  const [stories, setStories] = useState<Story[]>([]);
  const [storyId, setStoryId] = useState("");
  const [story, setStory] = useState<Story | null>(null);
  const [events, setEvents] = useState<EventItem[]>([]);
  const [relations, setRelations] = useState<Relation[]>([]);
  const [title, setTitle] = useState("");
  const [eventType, setEventType] = useState("story_event");
  const [inWorldTime, setInWorldTime] = useState("");
  const [sceneId, setSceneId] = useState("");
  const [description, setDescription] = useState("");
  const [chronologyNote, setChronologyNote] = useState("");
  const [beforeId, setBeforeId] = useState("");
  const [afterId, setAfterId] = useState("");
  const [relationNote, setRelationNote] = useState("");
  const [analysis, setAnalysis] = useState<Analysis | null>(null);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function loadStories() {
    if (!projectId) { setStories([]); setStoryId(""); return; }
    const data = await request<{ items: Story[] }>("/api/v1/stories?project_id=" + encodeURIComponent(projectId) + "&limit=100");
    setStories(data.items ?? []);
    if (!data.items?.some(item => item.id === storyId)) setStoryId(data.items?.[0]?.id ?? "");
  }

  async function loadTimeline() {
    if (!storyId) { setStory(null); setEvents([]); setRelations([]); setAnalysis(null); return; }
    setLoading(true);
    setError("");
    try {
      const [s, e, r] = await Promise.all([
        request<Story>("/api/v1/stories/" + storyId),
        request<{ items: EventItem[] }>("/api/v1/stories/" + storyId + "/timeline/events"),
        request<{ items: Relation[] }>("/api/v1/stories/" + storyId + "/timeline/relations")
      ]);
      setStory(s);
      setEvents(e.items ?? []);
      setRelations(r.items ?? []);
      setAnalysis(null);
      if (!s.scenes?.some(scene => scene.id === sceneId)) setSceneId("");
      if (!e.items?.some(item => item.id === beforeId)) setBeforeId("");
      if (!e.items?.some(item => item.id === afterId)) setAfterId("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not load timeline");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => { void loadStories().catch(err => setError(err.message)); }, [projectId]);
  useEffect(() => { void loadTimeline(); }, [storyId]);

  async function submit(event: FormEvent, path: string, payload: unknown, success: string) {
    event.preventDefault();
    if (!storyId) return;
    setBusy(true); setError(""); setNotice("");
    try {
      await request(path, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      setNotice(success);
      await loadTimeline();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Could not save timeline data");
    } finally {
      setBusy(false);
    }
  }

  async function analyze() {
    if (!storyId) return;
    setBusy(true); setError(""); setNotice("");
    try {
      const result = await request<Analysis & { story_id: string }>("/api/v1/stories/" + storyId + "/timeline/analyze", { method: "POST" });
      setAnalysis(result);
      setNotice(result.is_consistent ? "Chronology constraints are consistent." : "A chronology cycle was detected.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Timeline analysis failed");
    } finally {
      setBusy(false);
    }
  }

  const eventName = (id: string) => events.find(item => item.id === id)?.title ?? "Unknown event";
  const orderedNames = analysis?.ordered_event_ids.map(eventName) ?? [];

  return <section className="workspace-panel">
    <div className="panel-header"><div><span className="eyebrow">IN-WORLD CHRONOLOGY</span><h2>Timeline & Event Continuity</h2><p>Define what happened before what, independently from screenplay scene order. Unrelated events remain unordered until you connect them.</p></div><button className="secondary-button" onClick={() => void loadTimeline()}><RefreshCw size={14}/> Refresh</button></div>
    {projects.length === 0 ? <div className="empty-state">Create a project before defining its timeline.</div> : <>
      <div className="asset-toolbar">
        <label className="field-label">Project<select value={projectId} onChange={e => setProjectId(e.target.value)}>{projects.map(project => <option key={project.id} value={project.id}>{project.name}</option>)}</select></label>
        <label className="field-label">Story<select value={storyId} onChange={e => setStoryId(e.target.value)}><option value="">Select a story</option>{stories.map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>
      </div>
      {error && <div className="connection-banner">{error}</div>}
      {notice && <div className="notice">{notice}</div>}
      {!storyId ? <div className="empty-state"><Clock size={22}/><b>Select a story</b><span>Create a story in Story Engine before adding timeline events.</span></div> : loading ? <div className="empty-state">Loading timeline…</div> : <>
        <div className="story-meta-grid"><div><small>EVENTS</small><b>{events.filter(item => item.active).length}</b></div><div><small>ORDERING RULES</small><b>{relations.length}</b></div><div><small>SCENES</small><b>{story?.scenes?.length ?? 0}</b></div><div><small>MODEL</small><b>Partial order</b></div></div>
        <div className="story-bible-grid">
          <form className="research-create" onSubmit={event => void submit(event, "/api/v1/stories/" + storyId + "/timeline/events", { title, event_type: eventType, in_world_time: inWorldTime || null, scene_id: sceneId || null, description: description || null, chronology_note: chronologyNote || null }, "Timeline event created.")}>
            <div className="form-title"><Plus size={15}/> New event</div>
            <label className="field-label">Event title<input value={title} onChange={e => setTitle(e.target.value)} maxLength={240} required/></label>
            <label className="field-label">Event type<input value={eventType} onChange={e => setEventType(e.target.value)} maxLength={48}/></label>
            <label className="field-label">In-world time marker<input value={inWorldTime} onChange={e => setInWorldTime(e.target.value)} placeholder="e.g. Year 14, winter / three days before the coronation"/></label>
            <label className="field-label">Related screenplay scene<select value={sceneId} onChange={e => setSceneId(e.target.value)}><option value="">Not tied to a scene</option>{story?.scenes?.map(scene => <option key={scene.id} value={scene.id}>{scene.position}. {scene.title}</option>)}</select></label>
            <label className="field-label">Description<textarea rows={3} value={description} onChange={e => setDescription(e.target.value)}/></label>
            <label className="field-label">Chronology note<textarea rows={2} value={chronologyNote} onChange={e => setChronologyNote(e.target.value)} placeholder="Uncertainty, flashback context or source note"/></label>
            <button className="primary-button" disabled={busy || !title.trim()}><Plus size={14}/> Add event</button>
          </form>
          <form className="research-create" onSubmit={event => void submit(event, "/api/v1/stories/" + storyId + "/timeline/relations", { before_event_id: beforeId, after_event_id: afterId, note: relationNote || null }, "Chronology constraint saved.")}>
            <div className="form-title"><GitBranch size={15}/> Set event order</div>
            <p className="research-muted">The first event must happen before the second. Cycles are rejected automatically.</p>
            <label className="field-label">Earlier event<select value={beforeId} onChange={e => setBeforeId(e.target.value)}><option value="">Choose event</option>{events.filter(item => item.active).map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>
            <label className="field-label">Later event<select value={afterId} onChange={e => setAfterId(e.target.value)}><option value="">Choose event</option>{events.filter(item => item.active).map(item => <option key={item.id} value={item.id}>{item.title}</option>)}</select></label>
            <label className="field-label">Reason / evidence note<textarea rows={3} value={relationNote} onChange={e => setRelationNote(e.target.value)}/></label>
            <button className="primary-button" disabled={busy || !beforeId || !afterId || beforeId === afterId}><GitBranch size={14}/> Add ordering rule</button>
          </form>
        </div>
        <section className="bible-list"><div className="section-heading"><div><h3>Recorded events</h3><p className="research-muted">Scene position is displayed only as a reference, never used as chronology.</p></div><button className="primary-button" onClick={() => void analyze()} disabled={busy || events.length === 0}><ShieldCheck size={14}/> Analyze chronology</button></div>
          {events.map(item => <article className="bible-entry" key={item.id}><div><b>{item.title}</b><small>{item.event_type} · {item.in_world_time || "No in-world time marker"} · {item.scene_id ? story?.scenes.find(scene => scene.id === item.scene_id)?.title ?? "Scene linked" : "No scene link"} · v{item.version}</small><p>{item.description || item.chronology_note || "No further detail."}</p></div><span className={item.active ? "project-status" : "project-type"}>{item.active ? "active" : "inactive"}</span></article>)}
          {!events.length && <p className="research-muted">No timeline events yet.</p>}
        </section>
        <section className="bible-list"><h3>Ordering constraints</h3>
          {relations.map(item => <article className="bible-entry" key={item.id}><div><b>{eventName(item.before_event_id)} <span aria-hidden="true">→</span> {eventName(item.after_event_id)}</b>{item.note && <p>{item.note}</p>}</div><small>BEFORE</small></article>)}
          {!relations.length && <p className="research-muted">No explicit chronology constraints. Events remain unordered.</p>}
        </section>
        {analysis && <section className="bible-list"><h3>Chronology analysis</h3><div className={analysis.is_consistent ? "notice" : "connection-banner"}>{analysis.is_consistent ? "No chronology cycles found." : "Cycle detected in the event-order graph."}</div>{analysis.ordered_event_ids.length > 0 && <ol>{orderedNames.map((name, index) => <li key={analysis.ordered_event_ids[index]}>{name}</li>)}</ol>}{analysis.cycle_event_ids.length > 0 && <p>{analysis.cycle_event_ids.map(eventName).join(" · ")}</p>}<p className="research-muted">{analysis.note}</p></section>}
      </>}
    </>}
  </section>;
}
