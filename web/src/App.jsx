import { Fragment, useCallback, useEffect, useRef, useState } from 'react'
import {
  COLORS,
  CURRENT,
  NOTE_TYPES,
  RECORD_FIELDS,
  SHIFTS,
  groupsFromNotes,
  shownType,
} from './data.js'

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
              <p className="quiet">Sam is absent. Also on Day 25.</p>
            </button>
          )
        })}
      </div>
    </section>
  )
}

function HandoffDraft({ text }) {
  return (
    <section className="group">
      <h2 className="group-label">For the night shift</h2>
      <div className="card">
        <article className="note" style={{ '--bar': COLORS.method }}>
          <p className="note-text">{text}</p>
        </article>
      </div>
    </section>
  )
}

function ShiftStrip({ selectedId, onSelect }) {
  return (
    <div className="strip" aria-label="Shifts">
      {SHIFTS.map((shift) => (
        <button
          key={shift.id}
          className="shift"
          type="button"
          aria-pressed={shift.id === selectedId}
          onClick={() => onSelect(shift.id)}
        >
          {shift.chip}
        </button>
      ))}
    </div>
  )
}

function Mast({ title = 'Doors', when, selectedId, onSelect, back, onSystems }) {
  return (
    <header className="mast">
      {back}
      {onSystems ? (
        <button className="systems-btn" type="button" onClick={onSystems}>
          Systems
        </button>
      ) : null}
      <h1 className="title">{title}</h1>
      <hr className="rust" />
      {when ? <p className="when">{when}</p> : null}
      {onSelect ? <ShiftStrip selectedId={selectedId} onSelect={onSelect} /> : null}
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

function TeamsThread({ handoff, confirmed, onConfirm, onBack }) {
  return (
    <>
      <div className="scroll">
        <header className="mast">
          <BackButton onClick={onBack} />
          <h1 className="title">Teams · Doors</h1>
          <hr className="rust" />
        </header>
        <section className="group">
          <h2 className="group-label">Day shift</h2>
          <div className="card">
            <article className="note" style={{ '--bar': COLORS.method }}>
              <p className="note-text">{handoff.paragraph}</p>
              <a className="quiet file-link" href={handoff.pdf_url} target="_blank" rel="noreferrer">
                Handoff · PDF
              </a>
            </article>
          </div>
        </section>
        {confirmed ? (
          <section className="group thread-message">
            <h2 className="group-label">Night shift</h2>
            <div className="card">
              <article className="note" style={{ '--bar': COLORS.closed }}>
                <p className="note-text">Confirmed</p>
              </article>
            </div>
          </section>
        ) : null}
      </div>
      {confirmed ? null : (
        <div className="footer">
          <button className="primary" type="button" onClick={onConfirm}>
            Confirm
          </button>
        </div>
      )}
    </>
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
        <Mast title="Systems" when="Connected to Passdown" back={<BackButton onClick={onBack} />} />
        <section className="group">
          <div className="card">
            {systems.map((system) => (
              <article key={system.name} className="note" style={{ '--bar': COLORS.closed }}>
                <p className="note-text">{system.name}</p>
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
              <article className="note" style={{ '--bar': COLORS.part }}>
                {turn.a ? (
                  <>
                    <p className="note-text">{turn.a.answer}</p>
                    {turn.a.sources?.length ? (
                      <p className="quiet">From {turn.a.sources.join(', ')}</p>
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
        <textarea
          className="line-field"
          rows={1}
          value={text}
          placeholder="Ask anything · or use the keyboard mic"
          onChange={(event) => setText(event.target.value)}
          aria-label="Ask"
        />
        <button className="primary" type="submit" disabled={!text.trim() || busy}>
          Ask
        </button>
      </form>
    </>
  )
}

export default function App() {
  const [selectedId, setSelectedId] = useState(CURRENT)
  const [screen, setScreen] = useState('home')
  const [day, setDay] = useState({ today: [], carried: [], handoff: null })
  const [past, setPast] = useState(null)
  const [stations, setStations] = useState([])
  const [freshId, setFreshId] = useState(null)
  const [confirmed, setConfirmed] = useState(false)
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
      const [shift, staffing] = await Promise.all([get(`/data/shift/${CURRENT}`), get('/data/stations')])
      const ids = [...shift.today, ...shift.carried].map((note) => note.id)
      if (known.current) {
        const added = ids.filter((id) => !known.current.includes(id))
        if (added.length) setFreshId(added[added.length - 1])
      }
      known.current = ids
      setDay(shift)
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
  const passed = Boolean(day.handoff)
  const shift = SHIFTS.find((item) => item.id === selectedId)

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
    setScreen(id === 'n26' && passed ? 'teams' : 'home')
    if (id !== CURRENT && id !== 'n26') {
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
      await post('/data/handoffs', { paragraph })
      await load()
      setSelectedId('n26')
      setScreen('teams')
    })

  const onOpen = (note) => openSheet({ kind: 'issue', noteId: note.id })
  const onAction = (note, action) => openSheet({ kind: 'confirm', noteId: note.id, action })

  let body
  if (screen === 'systems') {
    body = <Systems onBack={() => setScreen('home')} />
  } else if (screen === 'teams' && day.handoff) {
    body = (
      <TeamsThread
        handoff={day.handoff}
        confirmed={confirmed}
        onConfirm={() => setConfirmed(true)}
        onBack={() => {
          setSelectedId(CURRENT)
          setScreen('home')
        }}
      />
    )
  } else if (screen === 'review') {
    body = (
      <>
        <div className="scroll">
          <Mast
            title="Handoff to night shift"
            when="Doors · Sat 26 Sep"
            back={<BackButton onClick={() => setScreen('home')} />}
          />
          <section className="group">
            <h2 className="group-label">For the night shift</h2>
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
            disabled={!paragraph || busy || passed}
            onClick={passShift}
          >
            {passed ? 'Passed' : busy ? 'Passing…' : 'Pass to next shift'}
          </button>
        </div>
      </>
    )
  } else if (selectedId === 'n26') {
    body = (
      <div className="scroll">
        <Mast when={shift.when} selectedId={selectedId} onSelect={selectShift} />
        <p className="empty">Nothing passed yet.</p>
      </div>
    )
  } else if (selectedId === CURRENT) {
    const today = day.today.length ? [{ label: 'Today', notes: day.today }] : []
    body = (
      <>
        <div className="scroll">
          <Mast
            when={shift.when}
            selectedId={selectedId}
            onSelect={selectShift}
            onSystems={() => setScreen('systems')}
          />
          {offline ? <p className="empty">Cannot reach the plant systems.</p> : null}
          <Stations stations={stations} onCover={openCover} />
          {day.carried.length ? <p className="kicker">From last night</p> : null}
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
        <Mast when={shift.when} selectedId={selectedId} onSelect={selectShift} />
        {past?.handoff ? (
          <>
            <HandoffDraft text={past.handoff.paragraph} />
            <a className="quiet file-link" href={past.handoff.pdf_url} target="_blank" rel="noreferrer">
              Handoff · PDF
            </a>
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
            <textarea
              className="line-field"
              rows={4}
              value={draftText}
              placeholder="Say it in your own words · tap the mic on your keyboard"
              onChange={(event) => setDraftText(event.target.value)}
              aria-label="What was done"
            />
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
        <textarea
          className="line-field"
          value={draftText}
          rows={3}
          placeholder="Type, or tap the mic on your keyboard"
          onChange={(event) => setDraftText(event.target.value)}
          aria-label="Note"
          maxLength={160}
        />
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
