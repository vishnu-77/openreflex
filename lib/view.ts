export type View = "builder" | "research";

export const VIEW_EVENT = "openreflex:view";
export const VIEW_STORAGE_KEY = "openreflex-view";
export const BUILDER_ANCHORS = ["how", "quickstart", "privacy", "shipped"];
export const RESEARCH_ANCHORS = ["idea", "graph", "prior-work"];

export function currentView(): View {
  return document.documentElement.dataset.view === "research" ? "research" : "builder";
}

export function setView(view: View, scroll = true) {
  document.documentElement.dataset.view = view;
  try {
    localStorage.setItem(VIEW_STORAGE_KEY, view);
  } catch {
    // Storage can be unavailable (private mode); the switch still works for this visit.
  }
  const url = new URL(window.location.href);
  if (view === "research") url.searchParams.set("view", "research");
  else url.searchParams.delete("view");
  history.replaceState(null, "", url.pathname + url.search);
  window.dispatchEvent(new CustomEvent<View>(VIEW_EVENT, { detail: view }));
  // When the reader is already past the hero, bring them to the top of the newly shown view.
  const first = document.getElementById(view === "research" ? RESEARCH_ANCHORS[0] : BUILDER_ANCHORS[0]);
  if (scroll && first && window.scrollY > first.offsetTop - 120) first.scrollIntoView({ block: "start" });
}

// Runs before first paint (inlined in the document head) so a shared link never flashes the other view.
export const viewScript = `(function(){try{var d=document.documentElement,v="builder",q=new URLSearchParams(location.search).get("view"),h=location.hash.slice(1);if(q==="research"||q==="builder"){v=q}else if(${JSON.stringify(RESEARCH_ANCHORS)}.indexOf(h)>-1){v="research"}else if(${JSON.stringify(BUILDER_ANCHORS)}.indexOf(h)>-1){v="builder"}else if(localStorage.getItem("${VIEW_STORAGE_KEY}")==="research"){v="research"}d.dataset.view=v}catch(e){}})();`;
