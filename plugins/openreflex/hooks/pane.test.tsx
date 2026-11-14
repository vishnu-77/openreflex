import { expect, test } from 'claude-code/testing'

import { reflexLines } from './pane'

const PANE = {
  plugin: 'openreflex',
  component: 'Pane',
  requestId: 'openreflex',
  props: { title: 'OpenReflex', isFocused: false, bodyColumns: 60, placement: 'dock', scroll: { offset: 0, bodyRows: 20 }, view: {} },
} as const

test('only OpenReflex lines are kept, without the tag', () => {
  expect(reflexLines(['other hook', '[OpenReflex] Reflex: run tests · active.\n  [OpenReflex] Project memory: app.'])).toEqual([
    'Reflex: run tests · active.',
    'Project memory: app.',
  ])
  expect(reflexLines(['[#12] some memory', '[OpenReflex]'])).toEqual([])
  expect(reflexLines(undefined)).toEqual([])
})

test('what OpenReflex adds to a prompt shows in the pane', async ($, on) => {
  on('clock.now', () => ({ value: 1000 }))
  on('classic.UserPromptSubmit', () => ({ additionalContext: ['[OpenReflex] Reflex: run tests · active.'] }))

  const empty = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect((await empty.find({ type: 'Text', text: /Nothing recalled/ }))?.text).toBeDefined()
  await empty.unmount()

  await $.classic.UserPromptSubmit({ prompt: 'hi' } as never)

  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: /run tests/ }))?.text).toBe('Reflex: run tests · active.')
  expect((await ui.find({ type: 'Text', text: /UserPromptSubmit/ }))?.text).toBe('Now · UserPromptSubmit')
  await ui.unmount()
})
