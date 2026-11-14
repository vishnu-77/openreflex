import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Capture, Recall, ReflexState } from '../types'

const PANE = 'openreflex'
const TAG = '[OpenReflex]'
// The events OpenReflex's own hooks.json listens to: what it captures.
const CAPTURED = new Set(['SessionStart', 'UserPromptSubmit', 'PreToolUse', 'PostToolUse', 'PostToolUseFailure', 'PreCompact', 'Stop', 'SessionEnd'])

const recalls = atom({ plugin: 'openreflex', key: 'recalls' } as const, [], { shape: 'recalls-1' })
const captures = atom({ plugin: 'openreflex', key: 'captures' } as const, [], { shape: 'captures-1' })
const state = atom({ plugin: 'openreflex', key: 'state' } as const, null, { shape: 'state-1' })

/** OpenReflex's own lines out of what the hooks added, the tag dropped. */
export function reflexLines(context: readonly string[] | undefined): string[] {
  return (context ?? [])
    .flatMap(text => text.split('\n'))
    .map(line => line.trim())
    .filter(line => line.startsWith(TAG))
    .map(line => line.slice(TAG.length).trim())
    .filter(line => line !== '')
}

/** Of the state files read, the newest one written for this project. */
// shortcut: matches OpenReflex's folder by project name, not by its path hash; two repos with one name show the newer.
export function pickState(files: readonly ReflexState[], names: readonly string[]): ReflexState | null {
  const mine = files.filter(s => s.project !== undefined && names.includes(s.project.toLowerCase()))
  return mine.sort((a, b) => (b.updated_at ?? 0) - (a.updated_at ?? 0))[0] ?? null
}

/** OpenReflex is on for a project once it has learned or mapped anything there. */
export const isOn = (s: ReflexState | null): boolean => s !== null && (s.project_enabled === true || s.phase !== undefined)

const clip = (text: string, max: number): string => (text.length > max ? `${text.slice(0, max - 1)}…` : text)
const ago = (ms: number): string => (ms < 60000 ? `${Math.max(0, Math.round(ms / 1000))} s` : `${Math.floor(ms / 60000)} min`)
const n = (value: number | undefined): string => String(value ?? 0)
const base = (path: string): string => path.replace(/[\\/]+$/, '').split(/[\\/]/).pop()?.toLowerCase() ?? ''

let lastRead = 0
/** Reads OpenReflex's state.json for this project, at most once a second. */
async function refresh($: EngineInterface, force = false): Promise<void> {
  const now = await $.clock.now()
  if (!force && now - lastRead < 1000) return
  lastRead = now
  const home = (await $.env.get('OPENREFLEX_HOME')) ?? `${(await $.env.get('USERPROFILE')) ?? (await $.env.get('HOME')) ?? ''}/.openreflex`
  const repo = await $.session.repo().catch(() => null)
  const names = [base(await $.session.root()), ...(repo === null ? [] : [base(repo.root)])]
  const dirs = await $.fs.list(`${home}/projects`).catch(() => [])
  const files: ReflexState[] = []
  for (const dir of dirs) {
    if (dir.kind !== 'dir') continue
    const text = await $.fs.read(`${home}/projects/${dir.name}/state.json`).catch(() => '')
    try {
      if (text !== '') files.push(JSON.parse(text) as ReflexState)
    } catch {}
  }
  await update($, state, () => pickState(files, names))
}

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({ name: 'openreflex-map', description: 'Show OpenReflex live in a pane' })
    void $.ui.open({ id: PANE, title: 'OpenReflex' })
    const result = await next(e)
    await refresh($, true).catch(() => {})
    return result
  })

  on('command.run', { command: 'openreflex-map' }, async $ => {
    await refresh($, true).catch(() => {})
    await $.ui.open({ id: PANE, title: 'OpenReflex' })
    return { text: 'OpenReflex pane opened.' }
  })

  // Every settings-hook event: OpenReflex speaks at session start, on prompts and around tool calls.
  on('classic.*', async ($, e, next) => {
    const result = await next(e)
    // The pane is a view: a failure here must never change what OpenReflex's hooks gave the model.
    try {
      const event = (e as { hook_event_name?: string }).hook_event_name ?? ''
      if (CAPTURED.has(event)) {
        const at = await $.clock.now()
        const tool = (e as { tool_name?: string; tool?: string }).tool_name ?? (e as { tool?: string }).tool
        if (event !== 'PreToolUse') {
          const one: Capture = { at, event, ...(tool ? { tool } : {}), ...(event === 'PostToolUseFailure' ? { failed: true } : {}) }
          await update($, captures, list => [...list, one].slice(-60))
        }
        const lines = reflexLines((result as { additionalContext?: readonly string[] } | undefined)?.additionalContext)
        if (lines.length > 0) await update($, recalls, list => [...list, { at, when: event, lines }].slice(-50))
        await refresh($)
      }
    } catch {}
    return result
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const s = await read($, state)
    const feed = await read($, captures)
    const said = await read($, recalls)
    const now = await $.clock.now()
    const width = Math.max(24, (e.props as { bodyColumns?: number }).bodyColumns ?? 60)
    const rows = Math.max(8, (e.viewport?.rows ?? 24) - 2)
    const row = (label: string, text: string) => (
      <Text>
        <Text dimColor>{label.padEnd(9)}</Text>
        {clip(text, width - 9)}
      </Text>
    )

    const head: JSX.Element[] = []
    if (!isOn(s)) {
      head.push(
        <Text>
          <Text bold color="green">OpenReflex</Text>
          <Text color="yellow">  ○ off for this project</Text>
        </Text>,
        <Text dimColor>{clip('It sees the hooks but learns nothing here. Turn it on:', width)}</Text>,
        <Text color="yellow">  openreflex approve</Text>,
      )
    } else {
      const st = s as ReflexState
      const live = st.activity?.label ? `${st.activity.label}${st.activity.target ? `  ${st.activity.target}` : ''}  ${st.activity.status ?? ''}` : st.outcome ?? '—'
      head.push(
        <Text>
          <Text bold color="green">OpenReflex</Text>
          <Text color="green">{`  ● ${st.phase ?? 'ready'}`}</Text>
          <Text dimColor>{`${st.task?.mode ? ` · ${st.task.mode}` : ''}${st.plugin_version ? `  v${st.plugin_version}` : ''}`}</Text>
        </Text>,
        row('Memory', `${n(st.experiences)} experiences · ${n(st.lessons)} lessons · ${n(st.facts)} facts`),
        row('Map', `${n(st.map_files)} files · ${n(st.relationships)} links · ${n(st.indexed_files)} indexed`),
        row('Reflexes', `${n(st.reflexes_proven)} proven · ${n(st.reflexes_learning)} learning${st.project_reflex_state ? ` · project ${st.project_reflex_state}` : ''}`),
        row('Verify', `${st.verification ?? '—'} · ${n(st.verified)} verified`),
        row('Now', live),
      )
    }

    const last = said[said.length - 1]
    const recallRows = last === undefined ? [] : [
      <Text dimColor>{`Recalled ${ago(now - last.at)} ago · ${last.when}`}</Text>,
      ...last.lines.slice(0, 3).map(line => <Text color="green">{clip(line, width)}</Text>),
    ]
    const room = Math.max(1, rows - head.length - recallRows.length - 3)
    return (
      <Box flexDirection="column">
        {head}
        <Text> </Text>
        {recallRows}
        {recallRows.length > 0 && <Text> </Text>}
        {feed.length === 0 && <Text dimColor>Nothing captured yet: it shows each prompt and tool call here.</Text>}
        {feed.slice(-room).reverse().map(one => (
          <Text dimColor={!one.failed} color={one.failed ? 'red' : undefined}>
            {clip(`${one.failed ? '✕' : '·'} ${one.event.padEnd(18)} ${one.tool ?? ''}`.trimEnd() + `  ${ago(now - one.at)}`, width)}
          </Text>
        ))}
      </Box>
    )
  })
}
