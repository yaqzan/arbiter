import { useCallback, useEffect, useMemo, useState } from 'react'
import type { ReactElement } from 'react'
import { NavLink, Navigate, Route, Routes, useSearchParams } from 'react-router-dom'
import { api } from './api'
import type { MediaTypeInfo } from './types'
import RankPage from './pages/RankPage'
import LeaderboardPage from './pages/LeaderboardPage'
import LibraryPage from './pages/LibraryPage'
import ReviewPage from './pages/ReviewPage'
import AddPage from './pages/AddPage'
import HistoryPage from './pages/HistoryPage'

export interface ContestContext {
  types: MediaTypeInfo[]
  active: MediaTypeInfo
  setActive: (key: string) => void
  refreshTypes: () => Promise<void>
  /** Whether this visitor can change anything. The server decides (a tailnet
   *  peer, see arbiter/auth.py) and enforces it; this only hides the controls. */
  canEdit: boolean
}

// `owner`: pages that exist only to change things. A visitor never sees them.
const NAV = [
  { to: '/rank', label: 'Rank', owner: true },
  { to: '/leaderboard', label: 'Leaderboard', owner: false },
  { to: '/review', label: 'Review', owner: false },
  { to: '/history', label: 'History', owner: false },
  { to: '/library', label: 'Library', owner: false },
  { to: '/add', label: 'Add', owner: true },
]

export default function App() {
  const [types, setTypes] = useState<MediaTypeInfo[]>([])
  const [error, setError] = useState<string | null>(null)
  const [example, setExample] = useState(false)
  // null until health answers, so the page never draws edit controls it then
  // has to take away. Anything but an explicit `authed: true` is a visitor.
  const [canEdit, setCanEdit] = useState<boolean | null>(null)
  const [params, setParams] = useSearchParams()

  useEffect(() => {
    api.health()
      .then((h) => { setExample(!!h.example); setCanEdit(h.authed === true) })
      .catch(() => setCanEdit(false))
  }, [])

  const refreshTypes = useCallback(async () => {
    try {
      setTypes((await api.types()).types)
      setError(null)
    } catch (err) {
      setError(String(err))
    }
  }, [])

  useEffect(() => { void refreshTypes() }, [refreshTypes])

  const activeKey = params.get('type') ?? types[0]?.key ?? 'movie'
  const active = useMemo(
    () => types.find((t) => t.key === activeKey) ?? types[0],
    [types, activeKey],
  )

  const setActive = useCallback((key: string) => {
    const next = new URLSearchParams(params)
    next.set('type', key)
    setParams(next, { replace: true })
  }, [params, setParams])

  if (error) {
    return (
      <div className="boot-error">
        <h1>Arbiter</h1>
        <p>Can't reach the API.</p>
        <code>{error}</code>
        <p className="muted">Start it with <code>python -m arbiter serve</code>.</p>
      </div>
    )
  }
  if (!active || canEdit === null) return <div className="boot">Loading…</div>

  const context: ContestContext = { types, active, setActive, refreshTypes, canEdit }
  const home = `/${canEdit ? 'rank' : 'leaderboard'}?type=${active.key}`
  const ownerOnly = (element: ReactElement) =>
    canEdit ? element : <Navigate to={home} replace />

  return (
    <div className="app">
      <header className="topbar">
        <div className="brand">
          <span className="brand-mark">◆</span>
          <span className="brand-name">Arbiter</span>
          {!canEdit && <span className="read-only-mark muted">read only</span>}
        </div>

        {/* The contest strip. Two titles in different contests never meet, so
            which tab you are on is the single most load-bearing piece of state
            on the page — it stays visible everywhere. */}
        <nav className="type-strip" aria-label="Media type">
          {types.map((type) => (
            <button
              key={type.key}
              className={`type-tab${type.key === active.key ? ' is-active' : ''}`}
              onClick={() => setActive(type.key)}
              title={`${type.stats.total} titles · ${type.stats.rounds} rounds`}
            >
              <span className="type-icon">{type.icon}</span>
              <span>{type.label}</span>
              <span className="type-count">{type.stats.total}</span>
              {type.stats.contested_confident > 0 && (
                <span className="type-flag" title="contested — score has left its filed tier">
                  {type.stats.contested_confident}
                </span>
              )}
            </button>
          ))}
        </nav>

        <nav className="page-nav" aria-label="Sections">
          {NAV.filter((entry) => canEdit || !entry.owner).map((entry) => (
            <NavLink
              key={entry.to}
              to={`${entry.to}?type=${active.key}`}
              className={({ isActive }) => `page-link${isActive ? ' is-active' : ''}`}
            >
              {entry.label}
            </NavLink>
          ))}
        </nav>
      </header>

      {example && (
        <div className="flash">
          This is the example library, and it is read only. Run{' '}
          <code>python -m arbiter init</code> on the server to start your own.
        </div>
      )}

      <main className="content">
        <Routes>
          <Route path="/" element={<Navigate to={home} replace />} />
          <Route path="/rank" element={ownerOnly(<RankPage ctx={context} />)} />
          <Route path="/leaderboard" element={<LeaderboardPage ctx={context} />} />
          <Route path="/review" element={<ReviewPage ctx={context} />} />
          <Route path="/history" element={<HistoryPage ctx={context} />} />
          <Route path="/library" element={<LibraryPage ctx={context} />} />
          <Route path="/add" element={ownerOnly(<AddPage ctx={context} />)} />
          <Route path="*" element={<Navigate to={home} replace />} />
        </Routes>
      </main>
    </div>
  )
}
