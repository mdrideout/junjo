export const initialNodes = [
  {
    id: '4347435328',
    data: { label: 'CountNode' },
    position: { x: 0.0, y: 0.0 },
  },
  {
    id: '4347435664',
    data: { label: 'IncrementNode' },
    position: { x: 0.0, y: 0.0 },
  },
  {
    id: '4347436000',
    data: { label: 'SetWarningNode This is more text.' },
    position: { x: 0.0, y: 0.0 },
  },
  {
    id: '4347436336',
    data: { label: 'FinalNode' },
    position: { x: 0.0, y: 0.0 },
  },
]

export const initialEdges = [
  {
    id: '4347435328-4347435664',
    source: '4347435328',
    target: '4347435664',
    label: null,
  },
  {
    id: '4347435664-4347436000',
    source: '4347435664',
    target: '4347436000',
    label: 'count_over_10',
  },
  {
    id: '4347436000-4347436336',
    source: '4347436000',
    target: '4347436336',
    label: null,
  },
  {
    id: '4347435664-4347436336',
    source: '4347435664',
    target: '4347436336',
    label: null,
  },
]
