import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import { COLORS, NOTE_TYPES, RECORD_FIELDS, groupsFromNotes, shownType } from './data.js'

async function call(method, path, body) {
  const res = await fetch(path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) throw new Error((await res.text()) || res.statusText)
  return res.json()
}
const get = (path) => call('GET', path)
const post = (path, body) => call('POST', path, body ?? {})
const patch = (path, body) => call('PATCH', path, body)

function fitPhone() {
  const scale = Math.min(
    (window.innerWidth - 48) / 390,
    (window.innerHeight - 48) / 800
  )
  document.documentElement.style.setProperty('--phone-scale', String(scale))
}

// Web pages cannot start the OS dictation themselves, so the mic button puts the cursor in the
// text field (which opens the phone keyboard with its mic key) and says how to start dictation here.
function dictationHint() {
  const ua = navigator.userAgent
  if (/iPhone|iPad|iPod|Android/i.test(ua)) return 'Tap the mic on your keyboard'
  if (/Windows/i.test(ua)) return 'Press Win + H to dictate'
  if (/Mac/i.test(ua)) return 'Press the dictation key (mic or Fn twice)'
  return "Use your device's dictation"
}

function MicButton() {
  const [hint, setHint] = useState(false)
  useEffect(() => {
    if (!hint) return undefined
    const timer = window.setTimeout(() => setHint(false), 5000)
    return () => window.clearTimeout(timer)
  }, [hint])

  return (
    <span className="mic-wrap">
      {hint ? <span className="mic-hint">{dictationHint()}</span> : null}
      <button
        className={hint ? 'mic-btn mic-on' : 'mic-btn'}
        type="button"
        aria-label="Dictate"
        onMouseDown={(event) => event.preventDefault()}
        onClick={(event) => {
          event.currentTarget.closest('.field-row')?.querySelector('textarea')?.focus()
          setHint(true)
        }}
      >
        <svg width="18" height="18" viewBox="0 0 24 24" aria-hidden="true">
          <rect x="9" y="3" width="6" height="11" rx="3" />
          <path d="M5 11a7 7 0 0 0 14 0M12 18v3" fill="none" strokeWidth="2" strokeLinecap="round" />
        </svg>
      </button>
    </span>
  )
}

function NoteRow({ note, fresh, onOpen, onAction }) {
  const type = shownType(note)
  const log = note.log || []
  const response = [...log].reverse().find((entry) => entry.kind === 'response')
  const checking = note.source === 'line' && !note.ai_line && note.status !== 'closed'
  return (
    <article
      id={`note-${note.id}`}
      className={fresh ? 'note note-in' : 'note'}
      style={{ '--bar': COLORS[type] }}
    >
      <button
        className="note-hit"
        type="button"
        disabled={!onOpen}
        onClick={() => onOpen?.(note)}
      >
        <p className="note-text">{note.text}</p>
        {checking ? <p className="quiet">Checking the systems…</p> : null}
        {note.ai_line ? <p className="quiet">{note.ai_line}</p> : null}
        {type === 'method' ? <p className="quiet">Not the official method.</p> : null}
        {log
          .filter((entry) => entry.kind === 'action')
          .map((entry) => (
            <p className="quiet log-line" key={entry.id}>
              {entry.ts.slice(11, 16)} · {entry.text}
            </p>
          ))}
        {response ? (
          <p className="quiet log-line">
            Done: {response.data.record.action_taken} · {response.data.record.status}
          </p>
        ) : null}
      </button>
      {onAction && note.status !== 'closed' && note.suggestions?.length ? (
        <div className="chips mini">
          {note.suggestions.map((action) => (
            <button
              key={action}
              className="chip"
              type="button"
              onClick={() => onAction(note, action)}
            >
              {action}
            </button>
          ))}
        </div>
      ) : null}
    </article>
  )
}

function Groups({ groups, freshId, onOpen, onAction }) {
  return groups.map((group) => (
    <section className="group" key={group.label}>
      <h2 className="group-label">{group.label}</h2>
      <div className="card">
        {group.notes.map((note) => (
          <NoteRow
            key={note.id}
            note={note}
            fresh={note.id === freshId}
            onOpen={onOpen}
            onAction={onAction}
          />
        ))}
      </div>
    </section>
  ))
}

function Stations({ stations, onCover }) {
  return (
    <section className="group">
      <h2 className="group-label">This shift</h2>
      <div className="card">
        {stations.map((station) => {
          const person = station.employee
          if (station.id === '12' || person) {
            return (
              <button
                key={station.id}
                className="note station-btn"
                type="button"
                style={{ '--bar': COLORS.closed }}
                onClick={() => onCover(station.id)}
              >
                <p className="note-text">
                  Station {station.id} · {person ? person.name.split(' ')[0] : 'empty'}
                </p>
                <p className="quiet">{person?.notes || 'Trained'}</p>
              </button>
            )
          }
          return (
            <button
              key={station.id}
              className="note station-btn"
              type="button"
              style={{ '--bar': COLORS.method }}
              onClick={() => onCover(station.id)}
            >
              <p className="note-text">Station {station.id} · empty</p>
              <p className="prompt">Choose who covers this</p>
              <p className="quiet">Sam is absent.</p>
            </button>
          )
        })}
      </div>
    </section>
  )
}

function HandoffCard({ label, handoff, onConfirm }) {
  return (
    <section className="group">
      <h2 className="group-label">{label}</h2>
      <div className="card">
        <article className="note" style={{ '--bar': COLORS.method }}>
          <p className="note-text">{handoff.paragraph}</p>
          <a className="quiet file-link" href={handoff.pdf_url} target="_blank" rel="noreferrer">
            Handoff · PDF
          </a>
          {onConfirm && !handoff.confirmed ? (
            <div className="chips mini">
              <button className="chip" type="button" onClick={onConfirm}>
                Confirm I read it
              </button>
            </div>
          ) : handoff.confirmed ? (
            <p className="quiet">Confirmed {handoff.confirmed.slice(11, 16)}</p>
          ) : null}
        </article>
      </div>
    </section>
  )
}

function ShiftStrip({ shifts, selectedId, onSelect }) {
  const stripRef = useRef(null)
  useEffect(() => {
    stripRef.current
      ?.querySelector('[aria-pressed="true"]')
      ?.scrollIntoView({ inline: 'center', block: 'nearest' })
  }, [selectedId, shifts.length])
  return (
    <div className="strip" ref={stripRef} aria-label="Shifts">
      {shifts.map((shift) => (
        <button
          key={shift.id}
          className={shift.status === 'active' ? 'shift shift-now' : 'shift'}
          type="button"
          aria-pressed={shift.id === selectedId}
          onClick={() => onSelect(shift.id)}
        >
          {shift.status === 'active' ? <span className="now-tag">Today</span> : null}
          {shift.label}
        </button>
      ))}
    </div>
  )
}

function Mast({ title = 'Teslog', when, shifts, selectedId, onSelect, back, onSystems }) {
  const active = shifts?.find((shift) => shift.status === 'active')
  const away = onSelect && active && selectedId !== active.id
  return (
    <header className={onSelect ? 'mast' : 'mast mast-plain'}>
      {back}
      <div className="mast-actions">
        {away ? (
          <button className="today-btn" type="button" onClick={() => onSelect(active.id)}>
            Today
          </button>
        ) : null}
        {onSystems ? (
          <button className="hub-btn" type="button" onClick={onSystems}>
            <svg width="14" height="14" viewBox="0 0 14 14" aria-hidden="true">
              <circle cx="3" cy="3" r="2" />
              <circle cx="11" cy="3" r="2" />
              <circle cx="3" cy="11" r="2" />
              <circle cx="11" cy="11" r="2" />
            </svg>
            Giga Hub
          </button>
        ) : null}
      </div>
      <h1 className="title">{title}</h1>
      <hr className="rust" />
      {when ? <p className="when">{when}</p> : null}
      {onSelect ? <ShiftStrip shifts={shifts} selectedId={selectedId} onSelect={onSelect} /> : null}
    </header>
  )
}

function BackButton({ onClick }) {
  return (
    <button className="back" type="button" onClick={onClick} aria-label="Back">
      <svg width="12" height="20" viewBox="0 0 12 20" aria-hidden="true">
        <path d="M10 2 L2 10 L10 18" fill="none" stroke="currentColor" strokeWidth="1.5" />
      </svg>
    </button>
  )
}

function Systems({ onBack }) {
  const [systems, setSystems] = useState([])
  const [turns, setTurns] = useState([])
  const [text, setText] = useState('')
  const [busy, setBusy] = useState(false)
  const endRef = useRef(null)

  useEffect(() => {
    get('/api/systems').then(setSystems).catch(() => setSystems([]))
  }, [])

  // Each connected system has its own color; new systems without one get a spare color.
  const spare = ['#F26B1D', '#3E6AE1', '#7B61FF', '#1FA463', '#C9A227']
  const colorOf = (name) => {
    const i = systems.findIndex((system) => system.name === name)
    return i < 0 ? 'var(--secondary)' : systems[i].color || spare[i % spare.length]
  }

  useEffect(() => {
    endRef.current?.scrollIntoView({ block: 'end' })
  }, [turns, busy])

  async function ask(question) {
    const q = question.trim()
    if (!q || busy) return
    setText('')
    setBusy(true)
    const history = turns.flatMap((turn) => [
      { role: 'user', content: turn.q },
      ...(turn.a ? [{ role: 'assistant', content: turn.a.answer }] : []),
    ])
    setTurns((current) => [...current, { q }])
    let answer
    try {
      answer = await post('/api/ask', { text: q, history })
    } catch (error) {
      answer = { answer: `Could not reach the assistant. ${error.message}`, chips: [], sources: [] }
    }
    setTurns((current) => current.map((turn, i) => (i === current.length - 1 ? { q, a: answer } : turn)))
    setBusy(false)
  }

  return (
    <>
      <div className="scroll">
        <Mast title="Giga Hub" back={<BackButton onClick={onBack} />} />
        <section className="group">
          <div className="card">
            {systems.map((system) => (
              <article key={system.name} className="note" style={{ '--bar': colorOf(system.name) }}>
                <p className="note-text system-name">
                  <span className="dot" style={{ background: colorOf(system.name) }} />
                  {system.name}
                </p>
                <p className="quiet">
                  {system.about} · connected · {system.tools.length} tools
                </p>
                <div className="chips mini">
                  {system.examples.map((example) => (
                    <button key={example} className="chip" type="button" onClick={() => ask(example)}>
                      {example}
                    </button>
                  ))}
                </div>
              </article>
            ))}
          </div>
        </section>
        {turns.map((turn, i) => (
          <section className="group" key={i}>
            <h2 className="group-label">{turn.q}</h2>
            <div className="card">
              <article
                className="note"
                style={{ '--bar': turn.a?.sources?.length ? colorOf(turn.a.sources[0]) : 'var(--line)' }}
              >
                {turn.a ? (
                  <>
                    <p className="note-text">{turn.a.answer}</p>
                    {turn.a.sources?.length ? (
                      <p className="quiet sources">
                        From
                        {turn.a.sources.map((source) => (
                          <span key={source} className="source">
                            <span className="dot" style={{ background: colorOf(source) }} />
                            {source}
                          </span>
                        ))}
                      </p>
                    ) : null}
                    {i === turns.length - 1 && turn.a.chips?.length ? (
                      <div className="chips mini">
                        {turn.a.chips.slice(0, 3).map((chip) => (
                          <button key={chip} className="chip" type="button" onClick={() => ask(chip)}>
                            {chip}
                          </button>
                        ))}
                      </div>
                    ) : null}
                  </>
                ) : (
                  <p className="quiet">Checking the systems…</p>
                )}
              </article>
            </div>
          </section>
        ))}
        <div ref={endRef} />
      </div>
      <form
        className="footer ask-bar"
        onSubmit={(event) => {
          event.preventDefault()
          ask(text)
        }}
      >
        <div className="field-row">
          <textarea
            className="line-field"
            rows={1}
            value={text}
            placeholder="Ask anything · or tap the mic"
            onChange={(event) => setText(event.target.value)}
            aria-label="Ask"
          />
          <MicButton />
        </div>
        <button className="primary" type="submit" disabled={!text.trim() || busy}>
          Ask
        </button>
      </form>
    </>
  )
}

export default function App() {
  const [shifts, setShifts] = useState([])
  const [selectedId, setSelectedId] = useState(null)
  const [screen, setScreen] = useState('home')
  const [day, setDay] = useState({ shift: null, today: [], carried: [], received: null })
  const [past, setPast] = useState(null)
  const [stations, setStations] = useState([])
  const [freshId, setFreshId] = useState(null)
  const [offline, setOffline] = useState(false)
  // sheet: { kind: 'note' | 'issue' | 'confirm' | 'respond' | 'cover', ... }
  const [sheet, setSheet] = useState(null)
  const [draftType, setDraftType] = useState(null)
  const [draftText, setDraftText] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [record, setRecord] = useState(null)
  const [result, setResult] = useState('')
  const [candidates, setCandidates] = useState([])
  const [paragraph, setParagraph] = useState('')
  const known = useRef(null)

  const load = useCallback(async () => {
    try {
      const [calendar, shift, staffing] = await Promise.all([
        get('/data/shifts'),
        get('/data/shift/current'),
        get('/data/stations'),
      ])
      const ids = [...shift.today, ...shift.carried].map((note) => note.id)
      if (known.current) {
        const added = ids.filter((id) => !known.current.includes(id))
        if (added.length) setFreshId(added[added.length - 1])
      }
      known.current = ids
      setShifts(calendar)
      setDay(shift)
      setSelectedId((current) =>
        calendar.some((item) => item.id === current) ? current : shift.shift.id
      )
      setStations(staffing)
      setOffline(false)
    } catch {
      setOffline(true)
    }
  }, [])

  useEffect(() => {
    fitPhone()
    window.addEventListener('resize', fitPhone)
    load()
    const events = new EventSource('/api/stream')
    events.onmessage = () => load()
    return () => {
      window.removeEventListener('resize', fitPhone)
      events.close()
    }
  }, [load])

  useEffect(() => {
    if (!freshId) return
    document.getElementById(`note-${freshId}`)?.scrollIntoView({ block: 'nearest' })
  }, [freshId, day])

  useEffect(() => {
    if (!sheet) return undefined
    function onKey(event) {
      if (event.key === 'Escape') closeSheet()
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [sheet])

  const allNotes = [...day.carried, ...day.today]
  const openNote = sheet?.noteId ? allNotes.find((note) => note.id === sheet.noteId) : null
  const activeId = day.shift?.id
  const shift = shifts.find((item) => item.id === selectedId)
  const nextKind = day.shift?.next_kind ?? 'next'
  const prevKind = day.shift?.prev_kind ?? 'previous'

  function openSheet(next) {
    setError('')
    setBusy(false)
    setResult('')
    setSheet(next)
  }

  function closeSheet() {
    setSheet(null)
    setRecord(null)
  }

  async function run(task) {
    setBusy(true)
    setError('')
    try {
      await task()
    } catch (error) {
      setError(error.message.slice(0, 200))
    }
    setBusy(false)
  }

  async function selectShift(id) {
    closeSheet()
    setSelectedId(id)
    setScreen('home')
    if (shifts.find((item) => item.id === id)?.status === 'passed') {
      setPast(null)
      get(`/data/shift/${id}`).then(setPast).catch(() => setPast({ handoff: null }))
    }
  }

  async function openCover(stationId) {
    openSheet({ kind: 'cover', stationId })
    const people = await get(`/data/hr/employees?station=${stationId}`).catch(() => [])
    setCandidates(people)
  }

  const assign = (employee) =>
    run(async () => {
      await post(`/data/stations/${sheet.stationId}/assign`, { employee: employee.id })
      closeSheet()
      load()
    })

  const saveNote = () =>
    run(async () => {
      const text = draftText.trim()
      const sorted = draftType ? { type: draftType } : await post('/api/classify', { text })
      await post('/data/notes', { text, type: sorted.type, station: sorted.station || null })
      closeSheet()
      load()
    })

  const confirmAction = () =>
    run(async () => {
      const done = await post(`/api/notes/${sheet.noteId}/act`, { action: sheet.action })
      setResult(done.result)
      load()
    })

  const makeRecord = () =>
    run(async () => {
      setRecord(await post(`/api/notes/${sheet.noteId}/structure`, { text: draftText }))
    })

  const saveRecord = () =>
    run(async () => {
      await post(`/data/notes/${sheet.noteId}/log`, {
        kind: 'response',
        text: record.action_taken,
        data: { record, original: draftText },
      })
      if (record.status === 'resolved') {
        await patch(`/data/notes/${sheet.noteId}`, { status: 'closed' })
      }
      closeSheet()
      load()
    })

  const setStatus = (status) =>
    run(async () => {
      await patch(`/data/notes/${sheet.noteId}`, { status })
      closeSheet()
      load()
    })

  const setLabel = (type) =>
    run(async () => {
      await patch(`/data/notes/${sheet.noteId}`, { type })
      load()
    })

  async function openReview() {
    setScreen('review')
    setParagraph('')
    try {
      setParagraph((await post('/api/handoff')).paragraph)
    } catch (error) {
      setParagraph(`Could not draft the handoff. ${error.message.slice(0, 120)}`)
    }
  }

  const passShift = () =>
    run(async () => {
      const passed = await post('/data/handoffs', { paragraph })
      setSelectedId(passed.active)
      setScreen('home')
      await load()
    })

  const confirmReceived = () =>
    run(async () => {
      await post(`/data/handoffs/${day.received.id}/confirm`)
      load()
    })

  const onOpen = (note) => openSheet({ kind: 'issue', noteId: note.id })
  const onAction = (note, action) => openSheet({ kind: 'confirm', noteId: note.id, action })

  let body
  if (screen === 'systems') {
    body = <Systems onBack={() => setScreen('home')} />
  } else if (screen === 'review') {
    body = (
      <>
        <div className="scroll">
          <Mast
            title={`Handoff to ${nextKind} shift`}
            when={`Doors line · ${day.shift?.when ?? ''}`}
            back={<BackButton onClick={() => setScreen('home')} />}
          />
          <section className="group">
            <h2 className="group-label">For the {nextKind} shift</h2>
            <div className="card">
              <article className="note" style={{ '--bar': COLORS.method }}>
                {paragraph ? (
                  <textarea
                    className="line-field bare"
                    rows={8}
                    value={paragraph}
                    onChange={(event) => setParagraph(event.target.value)}
                    aria-label="Handoff"
                  />
                ) : (
                  <p className="quiet">Writing it from the shift log…</p>
                )}
              </article>
            </div>
          </section>
          <Groups groups={groupsFromNotes(allNotes)} />
        </div>
        <div className="footer">
          {error ? <p className="quiet">{error}</p> : null}
          <button
            className="primary"
            type="button"
            disabled={!paragraph || busy}
            onClick={passShift}
          >
            {busy ? 'Passing…' : 'Pass to next shift'}
          </button>
        </div>
      </>
    )
  } else if (!shift) {
    body = (
      <div className="scroll">
        <Mast />
        <p className="empty">{offline ? 'Cannot reach the plant systems.' : 'Loading…'}</p>
      </div>
    )
  } else if (shift.status === 'next') {
    body = (
      <div className="scroll">
        <Mast
          when={shift.when}
          shifts={shifts}
          selectedId={selectedId}
          onSelect={selectShift}
          onSystems={() => setScreen('systems')}
        />
        <p className="empty">Nothing passed yet.</p>
      </div>
    )
  } else if (selectedId === activeId) {
    const today = day.today.length ? [{ label: 'Today', notes: day.today }] : []
    body = (
      <>
        <div className="scroll">
          <Mast
            when={shift.when}
            shifts={shifts}
            selectedId={selectedId}
            onSelect={selectShift}
            onSystems={() => setScreen('systems')}
          />
          {offline ? <p className="empty">Cannot reach the plant systems.</p> : null}
          {day.received ? (
            <HandoffCard
              label={`From the ${prevKind} shift`}
              handoff={day.received}
              onConfirm={confirmReceived}
            />
          ) : null}
          <Stations stations={stations} onCover={openCover} />
          {day.carried.length ? <p className="kicker">From earlier shifts</p> : null}
          <Groups
            groups={groupsFromNotes(day.carried)}
            freshId={freshId}
            onOpen={onOpen}
            onAction={onAction}
          />
          {today.map((group) => (
            <section className="group" key={group.label}>
              <h2 className="group-label">{group.label}</h2>
              <div className="card">
                {group.notes.map((note) => (
                  <NoteRow
                    key={note.id}
                    note={note}
                    fresh={note.id === freshId}
                    onOpen={onOpen}
                    onAction={onAction}
                  />
                ))}
              </div>
            </section>
          ))}
        </div>
        <div className="footer">
          <button className="text-btn" type="button" onClick={openReview}>
            Review handoff
          </button>
          <button
            className="primary"
            type="button"
            onClick={() => {
              setDraftType(null)
              setDraftText('')
              openSheet({ kind: 'note' })
            }}
          >
            Add a note
          </button>
        </div>
      </>
    )
  } else {
    body = (
      <div className="scroll">
        <Mast
          when={shift.when}
          shifts={shifts}
          selectedId={selectedId}
          onSelect={selectShift}
          onSystems={() => setScreen('systems')}
        />
        {past?.handoff ? (
          <>
            <HandoffCard label="Passed on" handoff={past.handoff} />
            <p className="kicker">Handoff</p>
            <Groups groups={past.handoff.groups} />
          </>
        ) : (
          <p className="empty">{past ? 'No handoff saved.' : 'Loading…'}</p>
        )}
      </div>
    )
  }

  let sheetBody = null
  if (sheet?.kind === 'cover') {
    const station = stations.find((item) => item.id === sheet.stationId)
    sheetBody = (
      <div className="sheet" role="dialog" aria-label={`Cover station ${sheet.stationId}`}>
        <h2 className="sheet-title">Cover station {sheet.stationId}</h2>
        <p className="sheet-lead">
          {station?.employee ? `Now: ${station.employee.name}.` : 'Sam is absent.'} Certified people from SAP HR.
        </p>
        {candidates.map((person) => (
          <button
            key={person.id}
            className={person.present ? 'cover-choice' : 'cover-choice needs'}
            type="button"
            disabled={!person.present || busy}
            onClick={() => assign(person)}
          >
            <span className="cover-name">
              {person.name}
              {person.present ? '' : ' · absent'}
            </span>
            <span className="quiet">{person.notes || person.role}</span>
          </button>
        ))}
        {error ? <p className="quiet">{error}</p> : null}
      </div>
    )
  } else if (sheet?.kind === 'issue' && openNote) {
    sheetBody = (
      <div className="sheet" role="dialog" aria-label="Issue">
        <h2 className="sheet-title">{openNote.text}</h2>
        {openNote.ai_line ? <p className="quiet">{openNote.ai_line}</p> : null}
        {(openNote.log || []).map((entry) =>
          entry.kind === 'response' ? (
            <div key={entry.id} className="record">
              <p className="quiet">{entry.ts.slice(11, 16)} · Response · {entry.by}</p>
              {RECORD_FIELDS.map(([key, label]) => (
                <p className="record-row" key={key}>
                  <span>{label}</span>
                  {entry.data.record[key]}
                </p>
              ))}
            </div>
          ) : (
            <p key={entry.id} className="quiet log-line">
              {entry.ts.slice(11, 16)} · {entry.text}
              {entry.data?.system ? ` · ${entry.data.system}` : ''}
            </p>
          )
        )}
        {openNote.status !== 'closed' && openNote.suggestions?.length ? (
          <div className="chips">
            {openNote.suggestions.map((action) => (
              <button key={action} className="chip" type="button" onClick={() => onAction(openNote, action)}>
                {action}
              </button>
            ))}
          </div>
        ) : null}
        <div className="chips">
          {NOTE_TYPES.map((type) => (
            <button
              key={type.id}
              className="chip small"
              type="button"
              aria-pressed={openNote.type === type.id}
              onClick={() => setLabel(type.id)}
            >
              {type.label}
            </button>
          ))}
        </div>
        {error ? <p className="quiet">{error}</p> : null}
        <button
          className="primary"
          type="button"
          onClick={() => {
            setDraftText('')
            setRecord(null)
            openSheet({ kind: 'respond', noteId: openNote.id })
          }}
        >
          What was done?
        </button>
        <button
          className="text-btn center"
          type="button"
          disabled={busy}
          onClick={() => setStatus(openNote.status === 'closed' ? 'open' : 'closed')}
        >
          {openNote.status === 'closed' ? 'Reopen' : 'Mark resolved'}
        </button>
      </div>
    )
  } else if (sheet?.kind === 'confirm') {
    const note = allNotes.find((item) => item.id === sheet.noteId)
    sheetBody = (
      <div className="sheet" role="dialog" aria-label="Confirm action">
        <h2 className="sheet-title">{result ? 'Done' : `${sheet.action}?`}</h2>
        <p className="sheet-lead">{result || note?.text}</p>
        {!result ? <p className="quiet">This changes the plant systems and is added to the log.</p> : null}
        {error ? <p className="quiet">{error}</p> : null}
        {result ? (
          <button className="primary" type="button" onClick={closeSheet}>
            Close
          </button>
        ) : (
          <button className="primary" type="button" disabled={busy} onClick={confirmAction}>
            {busy ? 'Working…' : 'Confirm'}
          </button>
        )}
      </div>
    )
  } else if (sheet?.kind === 'respond') {
    const note = allNotes.find((item) => item.id === sheet.noteId)
    sheetBody = (
      <div className="sheet" role="dialog" aria-label="What was done">
        <h2 className="sheet-title">What was done?</h2>
        <p className="quiet">{note?.text}</p>
        {record ? (
          <>
            <div className="record">
              {RECORD_FIELDS.map(([key, label]) => (
                <label className="record-row" key={key}>
                  <span>{label}</span>
                  <input
                    value={record[key] || ''}
                    onChange={(event) => setRecord({ ...record, [key]: event.target.value })}
                  />
                </label>
              ))}
            </div>
            <p className="quiet">
              Only from your words. {record.status === 'resolved' ? 'Resolved · moves to Closed today.' : ''}
            </p>
            {error ? <p className="quiet">{error}</p> : null}
            <button className="primary" type="button" disabled={busy} onClick={saveRecord}>
              Confirm
            </button>
            <button className="text-btn center" type="button" onClick={() => setRecord(null)}>
              Change my words
            </button>
          </>
        ) : (
          <>
            <div className="field-row">
              <textarea
                className="line-field"
                rows={4}
                value={draftText}
                placeholder="Say it in your own words · tap the mic"
                onChange={(event) => setDraftText(event.target.value)}
                aria-label="What was done"
              />
              <MicButton />
            </div>
            {error ? <p className="quiet">{error}</p> : null}
            <button className="primary" type="button" disabled={!draftText.trim() || busy} onClick={makeRecord}>
              {busy ? 'Writing the record…' : 'Make the record'}
            </button>
          </>
        )}
      </div>
    )
  } else if (sheet?.kind === 'note') {
    sheetBody = (
      <form
        className="sheet"
        role="dialog"
        aria-label="Add a note"
        onSubmit={(event) => {
          event.preventDefault()
          saveNote()
        }}
      >
        <h2 className="sheet-title">Add a note</h2>
        <div className="field-row">
          <textarea
            className="line-field"
            value={draftText}
            rows={3}
            placeholder="Type, or tap the mic"
            onChange={(event) => setDraftText(event.target.value)}
            aria-label="Note"
            maxLength={160}
          />
          <MicButton />
        </div>
        <div className="chips">
          {NOTE_TYPES.map((type) => (
            <button
              key={type.id}
              className="chip"
              type="button"
              aria-pressed={draftType === type.id}
              onClick={() => setDraftType(draftType === type.id ? null : type.id)}
            >
              {type.label}
            </button>
          ))}
        </div>
        <p className="quiet">{draftType ? '' : 'No label picked · it will be sorted for you.'}</p>
        {error ? <p className="quiet">{error}</p> : null}
        <button className="primary" type="submit" disabled={!draftText.trim() || busy}>
          {busy ? 'Saving…' : 'Save'}
        </button>
      </form>
    )
  }

  return (
    <main className="stage">
      <div className="scaler">
        <div className="phone">
          <div className="screen">
            <Fragment key={`${screen}-${selectedId}`}>{body}</Fragment>
            {sheetBody ? (
              <>
                <button className="scrim" type="button" aria-label="Close" onClick={closeSheet} />
                {sheetBody}
              </>
            ) : null}
          </div>
        </div>
      </div>
    </main>
  )
}
