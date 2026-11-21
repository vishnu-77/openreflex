import { atom, read, update } from 'claude-code'
import type { EngineInterface, Register } from 'claude-code'

import type { Capture, Evidence, Recall, ReflexState } from '../types'

const PANE = 'openreflex'
const TAG = '[OpenReflex]'
// The events OpenReflex's own hooks.json listens to: what it captures.
const CAPTURED = new Set(['SessionStart', 'UserPromptSubmit', 'PreToolUse', 'PostToolUse', 'PostToolUseFailure', 'PreCompact', 'Stop', 'SessionEnd'])

const recalls = atom({ plugin: 'openreflex', key: 'recalls' } as const, [], { shape: 'recalls-1' })
const captures = atom({ plugin: 'openreflex', key: 'captures' } as const, [], { shape: 'captures-1' })
const state = atom({ plugin: 'openreflex', key: 'state' } as const, null, { shape: 'state-1' })
const details = atom({ plugin: 'openreflex', key: 'details' } as const, false, { shape: 'details-1' })

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

const pct = (part: number, whole: number): string => (whole > 0 ? ` (${Math.round((100 * part) / whole)}%)` : '')
const signed = (value: number): string => `${value > 0 ? '+' : value < 0 ? '−' : ''}${Math.round(Math.abs(value) * 100)}%`

/**
 * Whether memory is used and checked, in words that claim no more than the data: "used" is never "helped",
 * use is set against chance, and the holdout gives a change only with its 95% range once both sides are large.
 */
export function evidenceRows(ev: Evidence | undefined): [string, string][] {
  if (ev === undefined) return [['Evidence', 'updates at the next session start']]
  const o = ev.outcomes ?? {}
  const r = ev.recall ?? {}
  const h = ev.holdout ?? {}
  // Each evidence level by its own name (ADR 0001): a passing check is "check passed", never "verified" or "correct".
  const checked = [
    ...((o.independently_verified ?? 0) > 0 ? [`${n(o.independently_verified)} independently verified`] : []),
    `${n(o.check_passed)} check passed`,
    `${n(o.agent_reported)} agent said`,
    `${n(o.inferred)} inferred`,
    `${n(o.unknown)} unknown`,  // the parts add up to the task count; saying it again overflows a panel line
  ].join(' · ')
  const shown = r.shown ?? 0
  const checkable = r.checkable ?? 0
  const recall = shown === 0
    ? 'no past task recalled yet'
    : checkable === 0
      ? `${shown} shown · none checkable yet (no files on both sides)`
      : `${shown} shown · ${checkable} checkable · used ${n(r.used)}${pct(r.used ?? 0, checkable)}` +
        (r.chance === null || r.chance === undefined ? '' : ` · chance ${Math.round(r.chance * 100)}%`)
  const change = h.tool_call_change
  const holdout = change === null || change === undefined || h.low === null || h.low === undefined ||
    h.high === null || h.high === undefined
    ? `${n(h.held_out)} held out · ${n(h.shown)} shown · needs ${n(h.min_side)} each to compare`
    : `calls ${signed(change)} (95%: ${signed(h.low)} to ${signed(h.high)}) · ${n(h.shown)} vs ${n(h.held_out)} held out`
  // First-file pointers: used when shown, set against how often held-out tasks touched those files anyway.
  const p = ev.pointers ?? {}
  const pointers = (p.shown ?? 0) === 0 && (p.held_out ?? 0) === 0
    ? 'none yet: they fire on the first file a task touches'
    : `${n(p.shown)} shown · used ${n(p.used)}${pct(p.used ?? 0, p.shown ?? 0)}` +
      ((p.held_out ?? 0) > 0 ? ` · held out ${n(p.held_out)}, touched anyway ${n(p.held_out_used)}` : '')
  // Rediscovery cost: calls before the first edit, medians, tasks with a pointer against held-out ones that would have had it.
  const f = ev.first_edit ?? {}
  const firstEdit = f.shown_median === null || f.shown_median === undefined || f.held_out_median === null || f.held_out_median === undefined
    ? `needs more tasks (${n(f.shown)} with hint · ${n(f.held_out)} without)`
    : `median ${f.shown_median} calls with hint (n=${n(f.shown)}) · ${f.held_out_median} without (n=${n(f.held_out)})`
  return [['Checked', checked], ['Recall', recall], ['Pointers', pointers], ['First edit', firstEdit], ['Holdout', holdout]]
}

/** The one plain answer at the top of the pane, written by Python (metrics.evidence verdict). */
/**
 * The flow: OpenReflex's recaps (start, pivot, complete), shown here instead of in the session transcript. Newest
 * first, at most `count`; each recap's first line is its head, the rest its detail.
 */
export function flowLines(flow: ReflexState['flow'], nowMs: number, count = 3): { head: boolean; text: string }[] {
  return (flow ?? []).slice(-count).reverse().flatMap(item => {
    const [first, ...rest] = String(item.text).split('\n')
    return [{ head: true, text: `${first}  · ${ago(nowMs - item.at * 1000)} ago` }, ...rest.map(text => ({ head: false, text: `  ${text}` }))]
  })
}

export function verdictOf(ev: Evidence | undefined): { color: string; line: string } {
  const v = ev?.verdict
  if (v === undefined || !v.line) return { color: 'gray', line: 'Evidence updates at the next session start' }
  return { color: v.state === 'helping' ? 'green' : v.state === 'not_helping' ? 'red' : 'yellow', line: v.line }
}

/** Every Reflex OpenReflex has learned is a Reflex: the proven/learned split stays inside OpenReflex, not on screen. */
export function reflexText(st: ReflexState): string {
  const ready = (st.reflexes_proven ?? 0) + (st.reflexes_learned ?? 0)
  const project = st.project_reflex_state === 'learned' || st.project_reflex_state === 'proven'
    ? 'project reflex ready'
    : st.project_reflex_state === 'stale' ? 'project reflex stale' : st.project_reflex_state ? 'project reflex learning' : ''
  return [`${ready} reflex${ready === 1 ? '' : 'es'}`, `${n(st.reflexes_learning)} learning`, project].filter(Boolean).join(' · ')
}

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
    const { Box, Text, Button } = $.ui.resolve(e)
    const s = await read($, state)
    const feed = await read($, captures)
    const said = await read($, recalls)
    const open = await read($, details)
    const now = await $.clock.now()
    const width = Math.max(24, (e.props as { bodyColumns?: number }).bodyColumns ?? 60)
    const row = (label: string, text: string) => (
      <Text>
        <Text dimColor>{label.padEnd(11)}</Text>
        {clip(text, width - 11)}
      </Text>
    )

    const st = (s ?? {}) as ReflexState
    const enabled = isOn(s)
    const verdict = verdictOf(st.evidence)
    const last = said[said.length - 1]
    const live = st.activity?.label ? `${st.activity.label}${st.activity.target ? `  ${st.activity.target}` : ''}  ${st.activity.status ?? ''}` : st.outcome ?? '—'
    // Only what needs attention: hints OpenReflex gave and calls that failed, newest first.
    const recent = [
      ...said.map(r => ({ at: r.at, failed: false, text: r.lines[0] ?? '' })),
      ...feed.filter(c => c.failed).map(c => ({ at: c.at, failed: true, text: `${c.event} ${c.tool ?? ''}`.trimEnd() })),
    ].sort((a, b) => b.at - a.at).slice(0, 5)
    return (
      <Box flexDirection="column">
        {enabled ? (
          <Text>
            <Text bold color="green">OpenReflex</Text>
            <Text color="green">{`  ● ${st.phase ?? 'ready'}`}</Text>
            <Text dimColor>{`${st.task?.mode ? ` · ${st.task.mode}` : ''}${st.plugin_version ? `  v${st.plugin_version}` : ''}`}</Text>
          </Text>
        ) : (
          <Text>
            <Text bold color="green">OpenReflex</Text>
            <Text color="yellow">  ○ off for this project</Text>
          </Text>
        )}
        {!enabled && <Text dimColor>{clip('It sees the hooks but learns nothing here. Turn it on:', width)}</Text>}
        {!enabled && <Text color="yellow">  openreflex approve</Text>}
        <Text> </Text>
        {enabled && <Text bold color={verdict.color}>{clip(verdict.line, width)}</Text>}
        {enabled && <Text> </Text>}
        {enabled && flowLines(st.flow, now).map(line => line.head
          ? <Text color="cyan">{clip(line.text, width)}</Text>
          : <Text>{clip(line.text, width)}</Text>)}
        {enabled && (st.flow ?? []).length > 0 && <Text> </Text>}
        {last === undefined
          ? <Text dimColor>{clip('No hint yet: OpenReflex speaks when it knows something specific', width)}</Text>
          : <Text dimColor>{`Last hint · ${ago(now - last.at)} ago`}</Text>}
        {last !== undefined && last.lines.slice(0, 3).map(line => <Text color="green">{clip(line, width)}</Text>)}
        <Text> </Text>
        {enabled && <Button key="details" label={open ? 'Hide details' : 'Details'} onPress={() => update($, details, v => !v)} />}
        {enabled && open && row('Memory', `${n(st.experiences)} stored experiences · ${n(st.lessons)} lessons · ${n(st.facts)} facts`)}
        {enabled && open && row('Map', `${n(st.map_files)} files · ${n(st.relationships)} links · ${n(st.indexed_files)} indexed`)}
        {enabled && open && row('Reflexes', reflexText(st))}
        {/* Counts of verified outcomes live under Checked, from the same tasks status counts; this row names the check. */}
        {enabled && open && row('Verify', `last check: ${st.verification ?? '—'}`)}
        {enabled && open && row('Now', live)}
        {enabled && open && evidenceRows(st.evidence).map(([label, text]) => row(label, text))}
        <Text> </Text>
        {feed.length === 0 && <Text dimColor>Nothing captured yet: hints and failed calls show here.</Text>}
        {recent.map(one => (
          <Text dimColor={!one.failed} color={one.failed ? 'red' : undefined}>
            {clip(`${one.failed ? '✕' : '·'} ${one.text}  ${ago(now - one.at)}`, width)}
          </Text>
        ))}
      </Box>
    )
  })
}
