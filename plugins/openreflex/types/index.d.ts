/** One moment OpenReflex put memory in front of the model. */
export type Recall = { at: number; when: string; lines: string[] }

/** One hook event OpenReflex captured, as the pane saw it. */
export type Capture = { at: number; event: string; tool?: string; failed?: boolean }

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
  updated_at?: number
}

declare module 'claude-code' {
  interface PluginState {
    'openreflex': { recalls: Shaped<Recall[]>; captures: Shaped<Capture[]>; state: Shaped<ReflexState | null> }
  }
}
