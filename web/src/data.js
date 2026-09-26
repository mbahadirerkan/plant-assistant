// Static labels only. Shifts and all shift data come from the backend (/data) and the AI (/api).
// Speech-to-text language for the mic buttons, e.g. 'en-US' or 'tr-TR'.
export const MIC_LANG = 'en-US'

export const COLORS = {
  open: '#E82127',
  part: '#3E6AE1',
  quality: '#7B61FF',
  machine: '#F26B1D',
  method: '#C9A227',
  closed: '#1FA463',
  check: '#3E6AE1',
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
