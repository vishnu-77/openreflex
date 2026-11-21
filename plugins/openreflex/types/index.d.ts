/** One moment OpenReflex put memory in front of the model. */
export type Recall = { at: number; when: string; lines: string[] }

/** One hook event OpenReflex captured, as the pane saw it. */
export type Capture = { at: number; event: string; tool?: string; failed?: boolean }

/** Whether memory is used and checked (metrics.evidence): observations, not proof of benefit. */
export type Evidence = {
  tasks?: number
  outcomes?: { independently_verified?: number; check_passed?: number; agent_reported?: number; inferred?: number; unknown?: number }
  recall?: { shown?: number; checkable?: number; used?: number; chance?: number | null }
  pointers?: { shown?: number; used?: number; held_out?: number; held_out_used?: number }
  verdict?: { state?: 'early' | 'helping' | 'not_helping'; line?: string }
  first_edit?: { shown?: number; held_out?: number; shown_median?: number | null; held_out_median?: number | null }
  holdout?: { shown?: number; held_out?: number; min_side?: number; tool_call_change?: number | null; low?: number | null; high?: number | null }
}

/** The fields of OpenReflex's own state.json the pane reads: its status-line cache. */
export type ReflexState = {
  project?: string
  phase?: string
  memory?: string
  project_enabled?: boolean
  plugin_version?: string
  experiences?: number
  lessons?: number
  facts?: number
  map_files?: number
  indexed_files?: number
  relationships?: number
  reflexes_proven?: number
  reflexes_learning?: number
  reflexes_learned?: number
  project_reflex_state?: string
  project_reflex_support?: number
  verification?: string
  verified?: number
  outcome?: string
  task?: { active?: boolean; mode?: string }
  activity?: { label?: string; status?: string; target?: string }
  execution?: { calls?: number }
  evidence?: Evidence
  updated_at?: number
}

declare module 'claude-code' {
  interface PluginState {
    'openreflex': { recalls: Shaped<Recall[]>; captures: Shaped<Capture[]>; state: Shaped<ReflexState | null>; details: Shaped<boolean> }
  }
}
