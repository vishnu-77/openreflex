/** One moment OpenReflex put memory in front of the model. */
export type Recall = { at: number; when: string; lines: string[] }

declare module 'claude-code' {
  interface PluginState {
    'openreflex': { recalls: Shaped<Recall[]> }
  }
}
