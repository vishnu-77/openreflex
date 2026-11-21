import { expect, test } from 'claude-code/testing'

import { evidenceRows, flowLines, isOn, pickState, reflexLines, reflexText, verdictOf } from './pane'

const PANE = {
  plugin: 'openreflex',
  component: 'Pane',
  requestId: 'openreflex',
  props: { title: 'OpenReflex', isFocused: false, bodyColumns: 70, placement: 'dock', scroll: { offset: 0, bodyRows: 30 }, view: {} },
} as const

const ON = { project: 'opentrajectory', phase: 'ready', project_enabled: true, experiences: 15, lessons: 16, map_files: 115, updated_at: 20,
  // verified here is the unfiltered store count; the pane must show only evidence.outcomes.verified.
  reflexes_proven: 0, reflexes_learned: 22, reflexes_learning: 90, verification: 'test', verified: 1,
  evidence: { tasks: 17, outcomes: { independently_verified: 0, check_passed: 2, agent_reported: 1, inferred: 5, unknown: 7 }, recall: { shown: 9, checkable: 3, used: 2, chance: 0.556 }, verdict: { state: 'early' as const, line: 'Too early to tell: 3 hints shown, 2 used' }, holdout: { shown: 14, held_out: 0, min_side: 30, tool_call_change: null, low: null, high: null } } }

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

test('the pane leads with the verdict and the last hint; numbers wait behind Details', async ($, on) => {
  engine(on, 'opentrajectory')
  on('classic.UserPromptSubmit', () => ({ additionalContext: ['[OpenReflex] Reflex: run tests · active.'] }))
  on('classic.PostToolUse', () => ({}))
  on('classic.PostToolUseFailure', () => ({}))

  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  await $.classic.UserPromptSubmit({ hook_event_name: 'UserPromptSubmit', prompt: 'hi' } as never)
  await $.classic.PostToolUse({ hook_event_name: 'PostToolUse', tool_name: 'Read' } as never)
  await $.classic.PostToolUseFailure({ hook_event_name: 'PostToolUseFailure', tool_name: 'Bash' } as never)

  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: /● ready/ }))?.text).toBeDefined()
  expect((await ui.find({ type: 'Text', text: /^Too early to tell: 3 hints shown, 2 used$/ }))?.text).toBeDefined()
  expect((await ui.find({ type: 'Text', text: /^Last hint/ }))?.text).toBeDefined()
  expect((await ui.find({ type: 'Text', text: /run tests/ }))?.text).toBe('Reflex: run tests · active.')
  // The feed keeps failures and hints only, not every tool call.
  expect((await ui.find({ type: 'Text', text: /✕ PostToolUseFailure Bash/ }))?.text).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /PostToolUse Read/ })).toBeUndefined()
  // Details are hidden until asked for.
  expect(await ui.find({ type: 'Text', text: /15 stored experiences/ })).toBeUndefined()

  await ui.press({ key: 'details' })
  expect((await ui.find({ type: 'Text', text: /15 stored experiences/ }))?.text).toBeDefined()
  expect((await ui.find({ type: 'Text', text: /2 check passed · 1 agent said · 5 inferred · 7 unknown$/ }))?.text).toBeDefined()
  expect((await ui.find({ type: 'Text', text: /used 2 \(67%\) · chance 56%/ }))?.text).toBeDefined()
  expect((await ui.find({ type: 'Text', text: /22 reflexes · 90 learning/ }))?.text).toBeDefined()
  expect(await ui.find({ type: 'Text', text: /proven/ })).toBeUndefined()
  expect((await ui.find({ type: 'Text', text: /last check: test/ }))?.text).toBeDefined()
  // No bare "verified" on screen: the old store count (verified: 1) must not reappear, and a passing check is not
  // called verified. Only independently verified outcomes would say so, and there are none here.
  expect(await ui.find({ type: 'Text', text: /verified/ })).toBeUndefined()

  await ui.press({ key: 'details' })
  expect(await ui.find({ type: 'Text', text: /15 stored experiences/ })).toBeUndefined()
  await ui.unmount()
})

test('the verdict is coloured by its state, and an older state file says when it will appear', () => {
  expect(verdictOf({ verdict: { state: 'helping', line: 'Hints are used' } })).toEqual({ color: 'green', line: 'Hints are used' })
  expect(verdictOf({ verdict: { state: 'not_helping', line: 'x' } }).color).toBe('red')
  expect(verdictOf({ verdict: { state: 'early', line: 'x' } }).color).toBe('yellow')
  expect(verdictOf(undefined).line).toBe('Evidence updates at the next session start')
  expect(verdictOf({}).line).toBe('Evidence updates at the next session start')
})

test('the flow shows the newest recaps first, here instead of in the session', async ($, on) => {
  const flow = [{ at: 40, text: '↺ OpenReflex · 41\n2 experiences · test-first 94% · ~16 calls · +80 context tokens\nOpenReflex context → likely src/auth/session.py · test-first recommended' },
    { at: 70, text: '↺ OpenReflex · COMPLETE\nsuccess · inspect-first · 4 calls · regret 0.00 vs test-first' }]
  expect(flowLines(flow, 100000).map(l => l.text)).toEqual([
    '↺ OpenReflex · COMPLETE  · 30 s ago', '  success · inspect-first · 4 calls · regret 0.00 vs test-first',
    '↺ OpenReflex · 41  · 1 min ago', '  2 experiences · test-first 94% · ~16 calls · +80 context tokens',
    '  OpenReflex context → likely src/auth/session.py · test-first recommended'])
  expect(flowLines(undefined, 0)).toEqual([])
  engine(on, 'opentrajectory', JSON.stringify({ ...ON, flow }))
  await $.session.start({ cwd: '/', surface: 'terminal', isInteractive: true })
  const ui = await $.ui.mount({ ...PANE, surface: 'terminal' })
  expect((await ui.find({ type: 'Text', text: /likely src\/auth\/session\.py/ }))?.text).toBeDefined()
  expect((await ui.find({ type: 'Text', text: /^↺ OpenReflex · COMPLETE/ }))?.text).toBeDefined()
  await ui.unmount()
})

test('first edit compares medians only when both sides have them', () => {
  const rows = (first_edit: object) => Object.fromEntries(evidenceRows({ first_edit }))
  expect(rows({ shown: 12, held_out: 9, shown_median: 4, held_out_median: 7 })['First edit'])
    .toBe('median 4 calls with hint (n=12) · 7 without (n=9)')
  expect(rows({ shown: 2, held_out: 0, shown_median: 3, held_out_median: null })['First edit'])
    .toBe('needs more tasks (2 with hint · 0 without)')
  expect(rows({})['First edit']).toBe('needs more tasks (0 with hint · 0 without)')
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
    outcomes: { independently_verified: 0, check_passed: 0, agent_reported: 0, inferred: 31, unknown: 84 },
    recall: { shown: 18, checkable: 4, used: 1, chance: 0.088 },
    holdout: { shown: 115, held_out: 0, min_side: 30, tool_call_change: null, low: null, high: null },
  }))
  expect(rows.Checked).toBe('0 check passed · 0 agent said · 31 inferred · 84 unknown')
  // Independently verified outcomes are named only when there are some: no source produces them yet.
  const external = Object.fromEntries(evidenceRows({ tasks: 3, outcomes: { independently_verified: 1, check_passed: 2 } }))
  expect(external.Checked).toBe('1 independently verified · 2 check passed · 0 agent said · 0 inferred · 0 unknown')
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

test('pointers say how often they were used, against held-out tasks touching the files anyway', () => {
  const rows = (pointers: object) => Object.fromEntries(evidenceRows({ pointers }))
  expect(rows({}).Pointers).toBe('none yet: they fire on the first file a task touches')
  expect(rows({ shown: 7, used: 4, held_out: 0, held_out_used: 0 }).Pointers).toBe('7 shown · used 4 (57%)')
  expect(rows({ shown: 7, used: 4, held_out: 2, held_out_used: 1 }).Pointers)
    .toBe('7 shown · used 4 (57%) · held out 2, touched anyway 1')
  expect(Object.values(rows({ shown: 3, used: 3 })).join(' ')).not.toMatch(/help|benefit|saved/i)
})
