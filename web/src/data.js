// Static labels only. Shifts and all shift data come from the backend (/data) and the AI (/api).
export const COLORS = {
  open: '#9E2B23',
  part: '#1F4E79',
  quality: '#6B3FA0',
  machine: '#8A3B12',
  method: '#8A5A00',
  closed: '#2C6B4A',
  check: '#1F4E79',
}

export const NOTE_TYPES = [
  { id: 'open', label: 'Still open' },
  { id: 'part', label: 'Missing part' },
  { id: 'quality', label: 'Quality' },
  { id: 'machine', label: 'Machine down' },
  { id: 'method', label: 'Not in the instruction' },
]

export const shownType = (note) => (note.status === 'closed' ? 'closed' : note.type)

export function groupsFromNotes(notes) {
  const order = [
    ['open', 'Still open'],
    ['part', 'Missing part'],
    ['quality', 'Quality'],
    ['machine', 'Machine down'],
    ['method', 'Not in the instruction'],
    ['check', 'Look at this first'],
    ['closed', 'Closed today'],
  ]
  return order
    .map(([type, label]) => ({
      label,
      notes: notes.filter((note) => shownType(note) === type),
    }))
    .filter((group) => group.notes.length > 0)
}

export const RECORD_FIELDS = [
  ['action_taken', 'Action taken'],
  ['done_by', 'Done by'],
  ['status', 'Status'],
  ['follow_up', 'Follow-up'],
]
