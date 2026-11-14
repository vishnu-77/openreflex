import { atom, read, update } from 'claude-code'
import type { Register } from 'claude-code'

import type { Recall } from '../types'

const PANE = 'openreflex'
const TAG = '[OpenReflex]'
const recalls = atom({ plugin: 'openreflex', key: 'recalls' } as const, [], { shape: 'recalls-1' })

/** OpenReflex's own lines out of what the hooks added, the tag dropped. */
export function reflexLines(context: readonly string[] | undefined): string[] {
  return (context ?? [])
    .flatMap(text => text.split('\n'))
    .map(line => line.trim())
    .filter(line => line.startsWith(TAG))
    .map(line => line.slice(TAG.length).trim())
    .filter(line => line !== '')
}

const clip = (text: string, max: number): string => (text.length > max ? `${text.slice(0, max - 1)}…` : text)
const ago = (ms: number): string => (ms < 60000 ? `${Math.max(0, Math.round(ms / 1000))} s` : `${Math.floor(ms / 60000)} min`)

export const register: Register = on => {
  on('session.start', async ($, e, next) => {
    await $.command.register({ name: 'openreflex-map', description: 'Show what OpenReflex recalls in a pane' })
    void $.ui.open({ id: PANE, title: 'OpenReflex' })
    return next(e)
  })

  on('command.run', { command: 'openreflex-map' }, async $ => {
    await $.ui.open({ id: PANE, title: 'OpenReflex' })
    return { text: 'OpenReflex pane opened.' }
  })

  // Every settings-hook event: OpenReflex speaks at session start, on prompts and around tool calls.
  on('classic.*', async ($, e, next) => {
    const result = await next(e)
    const context = (result as { additionalContext?: readonly string[] } | undefined)?.additionalContext
    // The pane is a view: a failure here must never change what OpenReflex's hooks gave the model.
    try {
      const lines = reflexLines(context)
      if (lines.length > 0) {
        const at = await $.clock.now()
        const when = (e as { hook_event_name?: string }).hook_event_name ?? 'hook'
        await update($, recalls, list => [...list, { at, when, lines }].slice(-100))
      }
    } catch {}
    return result
  })

  on('ui.render', { component: 'Pane', requestId: PANE }, async ($, e) => {
    const { Box, Text } = $.ui.resolve(e)
    const list = await read($, recalls)
    const now = await $.clock.now()
    const width = Math.max(20, (e.props as { bodyColumns?: number }).bodyColumns ?? 60)
    const rows = Math.max(6, (e.viewport?.rows ?? 24) - 4)
    const last = list[list.length - 1]

    if (last === undefined) {
      return (
        <Box flexDirection="column">
          <Text bold color="green">OpenReflex</Text>
          <Text dimColor>Nothing recalled yet. Reflexes show here when OpenReflex brings them in.</Text>
        </Box>
      )
    }
    const latest = last.lines.slice(0, Math.max(2, Math.floor(rows / 2)))
    const room = Math.max(1, rows - latest.length - 4)
    return (
      <Box flexDirection="column">
        <Text>
          <Text bold color="green">OpenReflex</Text>
          <Text dimColor>{`  ${list.length} recall${list.length === 1 ? '' : 's'} · last ${ago(now - last.at)} ago`}</Text>
        </Text>
        <Text dimColor>{`Now · ${last.when}`}</Text>
        {latest.map(line => <Text color="green">{clip(line, width)}</Text>)}
        <Text> </Text>
        {list.slice(-room - 1, -1).reverse().map(one => (
          <Text dimColor>{clip(`· ${one.when.padEnd(16)} ${one.lines[0] ?? ''}`, width)}</Text>
        ))}
      </Box>
    )
  })
}
