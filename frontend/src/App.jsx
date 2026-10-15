import { useEffect, useMemo, useRef, useState } from 'react'
import GraphView from './GraphView'

const API = 'http://127.0.0.1:8000'

// The band view is the mirror projection of the people view. Bands is default.
const MODES = {
  bands: { list: '/bands', path: '/band-path', neighbors: '/band-neighbors',
           label: 'Bands', unit: 'band', link: 'member_to_next', edge: 'member' },
  people: { list: '/musicians', path: '/path', neighbors: '/neighbors',
            label: 'People', unit: 'musician', link: 'band_to_next', edge: 'band' },
}

// Selectable themes. Each is a set of design tokens applied as CSS variables on
// the root, so switching is instant. page/card can be gradients (inline bg).
const THEMES = {
  nightfade: {
    name: 'Nightfade',
    page: '#e9ebeb', card: 'linear-gradient(135deg,#a3a1a0,#6f747c,#3b424b)', cardBorder: 'transparent',
    radius: '2rem', pill: '9999px',
    text: '#ffffff', muted: 'rgba(255,255,255,0.7)', accent: '#c4b5fd', accentText: '#1a1130',
    // the original multicolour: iridescent pink -> violet -> cyan
    accentImage: 'linear-gradient(90deg,#f9a8d4,#c4b5fd,#a5f3fc)',
    surface: 'rgba(255,255,255,0.12)', surfaceBorder: 'rgba(255,255,255,0.25)',
    menu: 'rgba(255,255,255,0.96)', menuText: '#1f2937', uppercase: true, glass: true,
    graphBg: 'rgba(0,0,0,0.2)', ink: '255,255,255',
    glassBg: 'rgba(255,255,255,0.1)', glassStrong: 'rgba(255,255,255,0.15)',
    glassBorder: 'rgba(255,255,255,0.2)', glassHover: 'rgba(255,255,255,0.2)',
  },
  light: {
    name: 'Light',
    // light frosted glass: pale teal gradient, dark ink, translucent-white panels.
    page: '#e2e6e4', card: 'linear-gradient(135deg,#d6efe6,#eff6f3,#c4e6db)', cardBorder: 'transparent',
    radius: '2rem', pill: '9999px',
    text: '#0a2f28', muted: 'rgba(10,47,40,0.6)', accent: '#1d9e75', accentText: '#ffffff',
    accentImage: 'linear-gradient(90deg,#1d9e75,#0f6e56,#1d9e75)',
    surface: 'rgba(255,255,255,0.5)', surfaceBorder: 'rgba(255,255,255,0.7)',
    menu: 'rgba(255,255,255,0.96)', menuText: '#0a2f28', uppercase: true, glass: true,
    graphBg: '#ffffff', ink: '10,15,13',
    glassBg: 'rgba(255,255,255,0.5)', glassStrong: 'rgba(255,255,255,0.65)',
    glassBorder: 'rgba(255,255,255,0.7)', glassHover: 'rgba(255,255,255,0.7)',
  },
  dark: {
    name: 'Dark',
    // glass version of Monolith: deep magenta-black gradient, frosted panels,
    // magenta highlight (with a pink->magenta->fuchsia shimmer on the number).
    page: '#0d0d0d', card: 'linear-gradient(135deg,#3a1024,#1c0f18,#0a0a0a)', cardBorder: 'rgba(236,45,122,0.25)',
    radius: '2rem', pill: '9999px',
    text: '#ffffff', muted: 'rgba(255,255,255,0.6)', accent: '#ec2d7a', accentText: '#ffffff',
    accentImage: 'linear-gradient(90deg,#f9a8d4,#ec2d7a,#c026d3)',
    surface: 'rgba(255,255,255,0.1)', surfaceBorder: 'rgba(255,255,255,0.22)',
    menu: 'rgba(15,10,13,0.97)', menuText: '#ffffff', uppercase: true, glass: true,
    graphBg: 'rgba(0,0,0,0.2)', ink: '255,255,255',
    glassBg: 'rgba(255,255,255,0.1)', glassStrong: 'rgba(255,255,255,0.15)',
    glassBorder: 'rgba(255,255,255,0.2)', glassHover: 'rgba(255,255,255,0.2)',
  },
}

// A filterable combobox: shows name (+ hint for homonyms), selects by stable id.
function Combobox({ items, value, onChange, placeholder }) {
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const boxRef = useRef(null)

  const selected = items.find((i) => i.id === value)
  const label = (i) => (i.hint ? `${i.name} — ${i.hint}` : i.name)

  const matches = useMemo(() => {
    const q = query.trim().toLowerCase()
    if (!q) return []
    // Prefix match on the name, but also on the name with a leading article
    // ("the ") stripped -- so "smith" finds "The Smiths", while typing "the"
    // still matches it directly. If nothing starts with the query, fall back
    // to a mid-word (substring) match so "pumpkins" still finds them.
    const noThe = (s) => s.replace(/^the\s+/, '')
    const prefix = items.filter((i) => {
      const name = i.name.toLowerCase()
      return name.startsWith(q) || noThe(name).startsWith(q)
    })
    const result = prefix.length ? prefix : items.filter((i) => i.name.toLowerCase().includes(q))
    return result.slice(0, 50)
  }, [query, items])

  useEffect(() => {
    const close = (e) => { if (boxRef.current && !boxRef.current.contains(e.target)) setOpen(false) }
    document.addEventListener('mousedown', close)
    return () => document.removeEventListener('mousedown', close)
  }, [])

  return (
    <div ref={boxRef} className="relative">
      <input
        className="w-full rounded-[var(--pill)] border border-[var(--surface-border)] bg-[var(--surface)]
                   px-4 py-3 text-sm text-[var(--text)] placeholder-[var(--muted)] outline-none
                   transition focus:border-[var(--accent)]"
        placeholder={placeholder}
        value={open ? query : selected ? label(selected) : ''}
        onFocus={() => { setOpen(true); setQuery('') }}
        onChange={(e) => { setQuery(e.target.value); setOpen(true) }}
      />
      {open && matches.length > 0 && (
        <ul className="absolute z-20 mt-1 max-h-64 w-full overflow-auto rounded-[var(--radius)]
                       border border-[var(--surface-border)] bg-[var(--menu)] text-[var(--menu-text)] shadow-2xl">
          {matches.map((i) => (
            <li key={i.id}>
              <button
                className="block w-full px-4 py-2.5 text-left text-sm transition hover:bg-[var(--accent)] hover:text-[var(--accent-text)]"
                onClick={() => { onChange(i.id); setOpen(false) }}
              >
                {i.name}{i.hint && <span className="opacity-50"> — {i.hint}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

// The result panel has two treatments: the glass panel (soft translucent
// surfaces, iridescent number, ↓ arrows) used by all current themes, vs the
// editorial solid accent block (numbered rows) kept for any non-glass theme.
function ResultPanel({ result, cfg, glass, onRandom, U }) {
  const sep = <>{result.degrees === 1 ? 'degree' : 'degrees'}<br />of separation</>

  if (glass) {
    return (
      <div className="rounded-3xl border border-[var(--glass-border)] bg-[var(--glass-bg)] p-6 backdrop-blur-md">
        <p className="mb-6">
          <span className="bg-[image:var(--accent-image)] bg-clip-text text-5xl font-bold text-transparent">{result.degrees}</span>
          <span className="ml-2 text-sm uppercase tracking-widest text-[var(--muted)]">{sep}</span>
        </p>
        <ol>
          {result.chain.map((step) => (
            <li key={step.id}>
              <div className="rounded-2xl border border-[var(--glass-border)] bg-[var(--glass-strong)] px-4 py-2.5 font-medium text-[var(--text)]">{step.name}</div>
              {step[cfg.link] && (
                <div className="flex items-center gap-2 py-1.5 pl-4 text-sm text-[var(--muted)]">
                  <span className="bg-[image:var(--accent-image)] bg-clip-text text-transparent">↓</span> {step[cfg.link]}
                </div>
              )}
            </li>
          ))}
        </ol>
        <button onClick={onRandom}
          className="mt-6 w-full rounded-full border border-[var(--glass-border)] bg-[var(--glass-bg)] py-2.5 text-sm font-semibold text-[var(--text)] transition hover:bg-[var(--glass-hover)]">
          ↻ Random connection
        </button>
      </div>
    )
  }

  return (
    <div className="flex flex-col rounded-[var(--radius)] bg-[image:var(--accent-image)] p-6 text-[var(--accent-text)]">
      <p className="mb-5 flex items-end gap-2">
        <span className="text-6xl font-bold leading-none">{result.degrees}</span>
        <span className="pb-1 text-xs font-semibold uppercase tracking-widest">{sep}</span>
      </p>
      <ol className="border-t border-black/15">
        {result.chain.map((step, i) => (
          <li key={step.id} className="border-b border-black/15 py-2.5">
            <div className="flex gap-3">
              <span className="font-mono text-xs opacity-50">{String(i + 1).padStart(2, '0')}</span>
              <span className="font-semibold">{step.name}</span>
            </div>
            {step[cfg.link] && <p className="pl-8 text-xs opacity-70">via {step[cfg.link]}</p>}
          </li>
        ))}
      </ol>
      <button onClick={onRandom}
        className={`mt-5 rounded-[var(--pill)] border border-black/30 py-2.5 text-xs font-semibold tracking-wider transition hover:bg-black hover:text-[var(--accent)] ${U}`}>
        ↻ Random connection
      </button>
    </div>
  )
}

export default function App() {
  const [theme, setTheme] = useState(() => localStorage.getItem('theme') || 'nightfade')
  const [mode] = useState('bands') // fixed while the People/Bands toggle is hidden
  const [items, setItems] = useState([])
  const [from, setFrom] = useState(null)
  const [to, setTo] = useState(null)
  const [display, setDisplay] = useState(null) // { nodes, links, highlight, result|null, seedName? }
  const [status, setStatus] = useState('')

  const cfg = MODES[mode]
  const t = THEMES[theme] || THEMES.nightfade
  const U = t.uppercase ? 'uppercase' : ''
  useEffect(() => { localStorage.setItem('theme', theme) }, [theme])

  // Show ONE degree from an entity: the node + its direct neighbours only.
  const seedNode = (id, name) => {
    setStatus('loading')
    fetch(`${API}${cfg.neighbors}?id=${id}`)
      .then((r) => r.json())
      .then((sub) => {
        const CAP = 40 // keep the seed + its first ~39 neighbours for readability
        const nodes = sub.nodes.slice(0, CAP)
        const ids = new Set(nodes.map((n) => n.id))
        const links = sub.links
          .filter((l) => ids.has(l.source) && ids.has(l.target))
          .map((l) => ({ source: l.source, target: l.target, label: l[cfg.edge] }))
        setDisplay({ nodes, links, highlight: [id], result: null, seedName: name })
        setStatus('')
      })
      .catch(() => setStatus('Request failed.'))
  }

  // Pick two random (well-connected) entities and show the path between them.
  // Retries a few times in case a pair happens to be unconnected.
  const randomConnection = (list) => {
    if (!list || !list.length) return
    setStatus('loading')
    const sorted = [...list].sort((a, b) => (b.degree || 0) - (a.degree || 0))
    const pool = sorted.slice(0, Math.max(2, Math.ceil(sorted.length * 0.25))) // top ~25% by degree
    const rnd = () => pool[Math.floor(Math.random() * pool.length)]
    const attempt = (n) => {
      const a = rnd()
      let b = rnd(), guard = 0
      while (b.id === a.id && guard++ < 20) b = rnd()
      fetch(`${API}${cfg.path}?from=${a.id}&to=${b.id}`)
        .then((r) => r.json())
        .then((data) => {
          if (data.connected) {
            setFrom(a.id); setTo(b.id)
            const nodes = data.chain.map((s) => ({ id: s.id, name: s.name }))
            const links = []
            for (let i = 0; i < data.chain.length - 1; i++) {
              links.push({ source: data.chain[i].id, target: data.chain[i + 1].id, label: data.chain[i][cfg.link] })
            }
            setDisplay({ nodes, links, highlight: data.chain.map((s) => s.id), result: data })
            setStatus('')
          } else if (n < 6) {
            attempt(n + 1)
          } else {
            setStatus('Could not find a random connection — try again.')
          }
        })
        .catch(() => setStatus('Request failed.'))
    }
    attempt(0)
  }

  // On mode change (and first load): load the list, then seed a random one.
  useEffect(() => {
    let cancelled = false
    setFrom(null); setTo(null); setDisplay(null); setStatus('loading')
    fetch(API + cfg.list)
      .then((r) => r.json())
      .then((list) => {
        if (cancelled) return
        setItems(list)
        randomConnection(list)
      })
      .catch(() => { if (!cancelled) setStatus('Could not reach the API — is the backend running on :8000?') })
    return () => { cancelled = true }
  }, [mode]) // eslint-disable-line react-hooks/exhaustive-deps

  const find = () => {
    if (!from || !to) return
    setStatus('loading')
    fetch(`${API}${cfg.path}?from=${from}&to=${to}`)
      .then((r) => r.json())
      .then((data) => {
        setStatus('')
        if (data.connected) {
          const nodes = data.chain.map((s) => ({ id: s.id, name: s.name }))
          const links = []
          for (let i = 0; i < data.chain.length - 1; i++) {
            links.push({ source: data.chain[i].id, target: data.chain[i + 1].id, label: data.chain[i][cfg.link] })
          }
          setDisplay({ nodes, links, highlight: data.chain.map((s) => s.id), result: data })
        } else {
          setDisplay({ nodes: [], links: [], highlight: [], result: data })
        }
      })
      .catch(() => setStatus('Request failed.'))
  }

  const connected = display?.result?.connected
  const exploring = display && !display.result

  const rootStyle = {
    background: t.page,
    '--text': t.text, '--muted': t.muted, '--accent': t.accent, '--accent-text': t.accentText,
    '--surface': t.surface, '--surface-border': t.surfaceBorder,
    '--menu': t.menu, '--menu-text': t.menuText, '--radius': t.radius, '--pill': t.pill,
    '--accent-image': t.accentImage,
    '--glass-bg': t.glassBg || 'rgba(255,255,255,0.1)',
    '--glass-strong': t.glassStrong || 'rgba(255,255,255,0.15)',
    '--glass-border': t.glassBorder || 'rgba(255,255,255,0.2)',
    '--glass-hover': t.glassHover || 'rgba(255,255,255,0.2)',
  }

  return (
    <div className="min-h-screen px-4 py-8 text-[var(--text)] sm:px-8 sm:py-12" style={rootStyle}>
      <main className="mx-auto max-w-7xl overflow-hidden border p-8 sm:p-12"
            style={{ background: t.card, borderColor: t.cardBorder, borderRadius: t.radius }}>

        {/* theme switcher */}
        <div className="mb-6 flex items-center justify-end gap-2">
          <span className={`mr-1 text-[10px] tracking-wider text-[var(--muted)] ${U}`}>Theme</span>
          {Object.entries(THEMES).map(([key, th]) => (
            <button
              key={key}
              onClick={() => setTheme(key)}
              title={th.name}
              className={`h-5 w-5 rounded-full border-2 transition ${
                theme === key ? 'scale-110 border-[var(--text)]' : 'border-transparent opacity-50 hover:opacity-100'
              }`}
              style={{ background: th.accent }}
            />
          ))}
        </div>

        <header className="mb-8">
          <p className="w-fit bg-[image:var(--accent-image)] bg-clip-text text-3xl font-semibold uppercase tracking-tight text-transparent sm:text-4xl">Six Degrees</p>
          <h1 className={`text-6xl font-bold leading-none tracking-tight sm:text-7xl ${U}`}>
            of Rock<span className="bg-[image:var(--accent-image)] bg-clip-text text-transparent">*</span>
          </h1>
          <p className="mt-5 max-w-md text-sm leading-relaxed text-[var(--muted)]">
            The shortest chain between any two {cfg.unit}s, through the {mode === 'bands' ? 'members' : 'bands'} they shared.
          </p>
        </header>

        {/* People/Bands toggle hidden for now -- band-centric only. The `people`
            mode + MODES config are kept so it can be re-enabled later. */}
        <div className="mb-4 flex flex-wrap items-center justify-end gap-3">
          <button
            onClick={() => randomConnection(items)}
            className={`rounded-[var(--pill)] px-5 py-2 text-xs font-semibold tracking-wider transition ${U} ${
              t.glass
                ? 'border border-[var(--glass-border)] bg-[var(--glass-bg)] text-[var(--text)] backdrop-blur-md hover:bg-[var(--glass-hover)]'
                : 'border border-[var(--accent)] text-[var(--accent)] hover:bg-[var(--accent)] hover:text-[var(--accent-text)]'
            }`}
          >
            ↻ Random connection
          </button>
        </div>

        {/* selectors + find */}
        <div className="grid gap-2 lg:grid-cols-[minmax(0,1fr)_auto_minmax(0,1fr)_auto] lg:items-center">
          <Combobox items={items} value={from} onChange={setFrom} placeholder={`First ${cfg.unit}…`} />
          <span className="hidden text-center text-[var(--muted)] lg:block">→</span>
          <Combobox items={items} value={to} onChange={setTo} placeholder={`Second ${cfg.unit}…`} />
          <button
            onClick={find}
            disabled={!from || !to || status === 'loading'}
            className={`rounded-[var(--pill)] px-8 py-3 text-sm font-semibold tracking-wider whitespace-nowrap transition ${U}
                        ${!from || !to || status === 'loading'
                          ? 'cursor-not-allowed border border-[var(--surface-border)] text-[var(--muted)]'
                          : 'bg-[image:var(--accent-image)] text-[var(--accent-text)] hover:brightness-110'}`}
          >
            {status === 'loading' ? 'Searching…' : 'Find connection'}
          </button>
        </div>

        {status && status !== 'loading' && (
          <p className="mt-4 rounded-[var(--radius)] border border-[var(--surface-border)] bg-[var(--surface)] px-5 py-3 text-sm text-[var(--muted)]">
            {status}
          </p>
        )}

        {/* explore view */}
        {exploring && (
          <div className="mt-8">
            <p className={`mb-3 text-xs tracking-wider text-[var(--muted)] ${U}`}>
              Exploring <span className="font-semibold text-[var(--accent)]">{display.seedName}</span> — pick two {cfg.unit}s to trace a connection
            </p>
            <GraphView nodes={display.nodes} links={display.links} highlight={display.highlight}
                       neighborsPath={cfg.neighbors} edgeLabel={cfg.edge} height={480} accent={t.accent}
                       graphBg={t.graphBg} ink={t.ink}
                       onNodeClick={(n) => seedNode(n.id, n.name)} />
          </div>
        )}

        {/* path found: chart LEFT, accent result panel RIGHT */}
        {connected && (
          <div className="mt-8 grid gap-4 lg:grid-cols-[1.5fr_1fr] lg:items-stretch">
            <GraphView nodes={display.nodes} links={display.links} highlight={display.highlight}
                       neighborsPath={cfg.neighbors} edgeLabel={cfg.edge} height={480} accent={t.accent}
                       graphBg={t.graphBg} ink={t.ink} />
            <ResultPanel result={display.result} cfg={cfg} glass={t.glass} U={U} onRandom={() => randomConnection(items)} />
          </div>
        )}

        {/* no path */}
        {display?.result && connected === false && (
          <div className="mt-8 rounded-[var(--radius)] border border-[var(--surface-border)] bg-[var(--surface)] p-8 text-center text-sm text-[var(--muted)]">
            No connection found — these two sit in separate parts of the network.
            <button
              onClick={() => randomConnection(items)}
              className={`mt-4 block w-full rounded-[var(--pill)] border border-[var(--accent)] py-2.5 text-xs
                          font-semibold tracking-wider text-[var(--accent)] transition hover:bg-[var(--accent)] hover:text-[var(--accent-text)] ${U}`}
            >
              ↻ Random connection
            </button>
          </div>
        )}
      </main>
    </div>
  )
}
