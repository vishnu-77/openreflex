import { expect, test } from 'claude-code/testing'

import { isOn, pickState, reflexLines } from './pane'

const PANE = {
  plugin: 'openreflex',
  component: 'Pane',
  requestId: 'openreflex',
  props: { title: 'OpenReflex', isFocused: false, bodyColumns: 70, placement: 'dock', scroll: { offset: 0, bodyRows: 30 }, view: {} },
} as const

const ON = { project: 'opentrajectory', phase: 'ready', project_enabled: true, experiences: 15, lessons: 16, map_files: 115, updated_at: 20 }

test('only OpenReflex lines are kept, without the tag', () => {
  expect(reflexLines(['other hook', '[OpenReflex] Reflex: run tests · active.\n  [OpenReflex] Project memory: app.'])).toEqual([
    'Reflex: run tests · active.',
    'Project memory: app.',
  ])
  expect(reflexLines(['[#12] some memory', '[OpenReflex]'])).toEqual([])
  expect(reflexLines(undefined)).toEqual([])
})

test('the newest state of this project is picked, and a bare one reads as off', () => {
  const older = { ...ON, experiences: 1, updated_at: 10 }
  expect(pickState([older, ON, { project: 'other', updated_at: 99 }], ['opentrajectory'])?.experiences).toBe(15)
  expect(pickState([ON], ['paper-videos'])).toBe(null)
  expect(isOn(null)).toBe(false)
  expect(isOn({ project: 'paper-videos', updated_at: 5 })).toBe(false)
  expect(isOn(ON)).toBe(true)
})

function engine(on: Parameters<Parameters<typeof test>[1]>[1], root: string, stateText = JSON.stringify(ON), listFails = false) {
  on('clock.now', () => ({ value: 100000 }))
  on('env.get', () => ({ value: 'C:/home' }))
  on('session.root', () => ({ value: `D:/work/${root}` }))
  on('session.repo', () => ({ value: null }))
  on('fs.list', () => {
    if (listFails) throw new Error('EACCES: no such folder')
    return { value: [{ name: 'abc', type: 'dir' }] }
  })
  on('fs.read', () => ({ value: stateText }))
  on('command.register', () => ({ value: { command: 'openreflex-map' } }))
  on('ui.open', () => ({ value: { isPlaced: true } }))
  on('session.start', (_, e) => ({ cwd: e.cwd }))
}

test('the pane shows OpenReflex live: state, recall and each capture', async ($, on) => {
  engine(on, 'opentrajectory')
  on('classic.UserPromptSubmit', () => ({ additionalContext: ['[OpenReflex] Reflex: run tests · active.'] }))
  on('classic.PostToolUse', () => ({}))

  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.classic.UserPromptSubmit({ hook_event_name: 'UserPromptSubmit', prompt: 'hi' } as never)
  await $.classic.PostToolUse({ hook_event_name: 'PostToolUse', tool_name: 'Bash' } as never)

  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: /● ready/ }))?.text).toBeDefined()
  expect((await ui.find({ type: 'Text', text: /15 experiences/ }))?.text).toBeDefined()
  expect((await ui.find({ type: 'Text', text: /run tests/ }))?.text).toBe('Reflex: run tests · active.')
  expect((await ui.find({ type: 'Text', text: /PostToolUse\s+Bash/ }))?.text).toBeDefined()
  await ui.unmount()
})

test('in a project OpenReflex is not on for, the pane says how to turn it on', async ($, on) => {
  engine(on, 'paper-videos')
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })

  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: /off for this project/ }))?.text).toBeDefined()
  expect((await ui.find({ type: 'Text', text: /openreflex approve/ }))?.text).toBeDefined()
  await ui.unmount()
})

// The pane is a view: whatever goes wrong in it, OpenReflex's hooks must reach the model unchanged.
const SAID = { additionalContext: ['[OpenReflex] Reflex: run tests · active.'], sessionTitle: 'kept' }

for (const [name, stateText, listFails] of [
  ['a state file that is not JSON', '{ half written', false],
  ['a state file of the wrong shape', '[1, 2, 3]', false],
  ['a projects folder that cannot be listed', '', true],
] as const) {
  test(`with ${name}, OpenReflex's hook output passes through unchanged`, async ($, on) => {
    engine(on, 'opentrajectory', stateText, listFails)
    on('classic.UserPromptSubmit', () => SAID)
    await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })

    const result = await $.classic.UserPromptSubmit({ hook_event_name: 'UserPromptSubmit', prompt: 'hi' } as never)
    expect(result).toEqual(SAID)

    const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
    expect((await ui.find({ type: 'Text', text: /run tests/ }))?.text).toBe('Reflex: run tests · active.')
    await ui.unmount()
  })
}

test('when the pane itself fails, the hook result still passes through', async ($, on) => {
  engine(on, 'opentrajectory')
  on('classic.PostToolUse', () => SAID)
  on('state.set', () => {
    throw new Error('state store unavailable')
  })

  const result = await $.classic.PostToolUse({ hook_event_name: 'PostToolUse', tool_name: 'Bash' } as never)
  expect(result).toEqual(SAID)
})

test('events OpenReflex does not capture leave no row', async ($, on) => {
  engine(on, 'opentrajectory')
  on('classic.Notification', () => ({}))
  await $.classic.Notification({ hook_event_name: 'Notification', message: 'x' } as never)

  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: /Nothing captured yet/ }))?.text).toBeDefined()
  await ui.unmount()
})
