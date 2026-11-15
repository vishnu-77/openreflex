import { expect, test } from 'claude-code/testing'

import { evidenceRows, isOn, pickState, reflexLines, reflexText } from './pane'

const PANE = {
  plugin: 'openreflex',
  component: 'Pane',
  requestId: 'openreflex',
  props: { title: 'OpenReflex', isFocused: false, bodyColumns: 70, placement: 'dock', scroll: { offset: 0, bodyRows: 30 }, view: {} },
} as const

const ON = { project: 'opentrajectory', phase: 'ready', project_enabled: true, experiences: 15, lessons: 16, map_files: 115, updated_at: 20,
  // verified here is the unfiltered store count; the pane must show only evidence.outcomes.verified.
  reflexes_proven: 0, reflexes_learned: 22, reflexes_learning: 90, verification: 'test', verified: 1,
  evidence: { tasks: 17, outcomes: { verified: 2, inferred: 6, unknown: 7 }, recall: { shown: 9, checkable: 3, used: 2, chance: 0.556 }, holdout: { shown: 14, held_out: 0, min_side: 30, tool_call_change: null, low: null, high: null } } }

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
    // The shape the engine really returns (checked against Claude Code 2.1.325): a file beside the folder must be skipped.
    return { value: [{ name: 'notes.txt', kind: 'file', size: 4, mtimeMs: 0, isLink: false }, { name: 'abc', kind: 'dir', size: 0, mtimeMs: 0, isLink: false }] }
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
  expect((await ui.find({ type: 'Text', text: /15 stored experiences/ }))?.text).toBeDefined()
  expect((await ui.find({ type: 'Text', text: /2 verified · 6 inferred/ }))?.text).toBeDefined()
  expect((await ui.find({ type: 'Text', text: /used 2 \(67%\) · chance 56%/ }))?.text).toBeDefined()
  expect((await ui.find({ type: 'Text', text: /22 reflexes · 90 learning/ }))?.text).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /proven/ })).toBeUndefined()
  expect((await ui.find({ type: 'Text', text: /last check: test/ }))?.text).toBeDefined()
  // One verified count on screen, the filtered one: never a second that disagrees with it.
  const verifiedCounts = (await ui.findAll({ type: 'Text', text: /\d+ verified/ })).map(t => t.text.match(/(\d+) verified/)?.[1])
  expect(new Set(verifiedCounts)).toEqual(new Set(['2']))
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

test('evidence says what was checked and used, never that memory helped', () => {
  const rows = Object.fromEntries(evidenceRows({
    tasks: 115,
    outcomes: { verified: 0, inferred: 31, unknown: 84 },
    recall: { shown: 18, checkable: 4, used: 1, chance: 0.088 },
    holdout: { shown: 115, held_out: 0, min_side: 30, tool_call_change: null, low: null, high: null },
  }))
  expect(rows.Checked).toBe('0 verified · 31 inferred · 84 unknown of 115 tasks')
  // Use is a share of the recalls that can be judged, set against chance: never of every recall.
  expect(rows.Recall).toBe('18 shown · 4 checkable · used 1 (25%) · chance 9%')
  expect(rows.Holdout).toBe('0 held out · 115 shown · needs 30 each to compare')
  expect(Object.values(rows).join(' ')).not.toMatch(/help|benefit|saved/i)
})

test('a recall that cannot be judged is not counted as unused', () => {
  const rows = Object.fromEntries(evidenceRows({ recall: { shown: 1, checkable: 0, used: 0, chance: null } }))
  expect(rows.Recall).toBe('1 shown · none checkable yet (no files on both sides)')
  expect(Object.fromEntries(evidenceRows({ recall: { shown: 0, used: 0 } })).Recall).toBe('no past task recalled yet')
})

test('the holdout gives a change only with its 95% range', () => {
  const full = { shown: 40, held_out: 35, min_side: 30, tool_call_change: -0.357, low: -0.495, high: -0.18 }
  expect(Object.fromEntries(evidenceRows({ holdout: full })).Holdout).toBe('calls −36% (95%: −50% to −18%) · 40 vs 35 held out')
  // A change without its range is never shown on its own.
  const bare = { ...full, low: null, high: null }
  expect(Object.fromEntries(evidenceRows({ holdout: bare })).Holdout).toBe('35 held out · 40 shown · needs 30 each to compare')
})

test('a state file from before evidence existed says when it will appear', () => {
  expect(evidenceRows(undefined)).toEqual([['Evidence', 'updates at the next session start']])
})

test('reflexes are counted as reflexes, without the proven/learned split', () => {
  expect(reflexText({ reflexes_proven: 2, reflexes_learned: 20, reflexes_learning: 90, project_reflex_state: 'learned' }))
    .toBe('22 reflexes · 90 learning · project reflex ready')
  expect(reflexText({ reflexes_learned: 1, reflexes_learning: 2, project_reflex_state: 'candidate' }))
    .toBe('1 reflex · 2 learning · project reflex learning')
  expect(reflexText({})).toBe('0 reflexes · 0 learning')
})
