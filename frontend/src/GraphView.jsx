import { useEffect, useMemo, useRef, useState } from 'react'
import ForceGraph2D from 'react-force-graph-2d'

const API = 'http://127.0.0.1:8000'
const MAX_NODES = 80 // cap so a big "collective" band can't flood the canvas

// Interactive force graph. Given a set of nodes/links and which ids to
// highlight (the path, or an explored seed); clicking a node pulls in its
// neighbours from the API (bounded).
export default function GraphView({ nodes, links, highlight, neighborsPath, edgeLabel, height = 440, onNodeClick, accent = '#7ad4bd', graphBg = 'rgba(0,0,0,0.2)', ink = '255,255,255' }) {
  // Canvas foreground palette, derived from the theme `ink` (an "r,g,b" triplet).
  // On a light graph this is a dark ink; on dark themes it's white.
  const cLabel = `rgb(${ink})`
  const cLabelDim = `rgba(${ink},0.7)`
  const cLine = `rgba(${ink},0.18)`
  const cLineStrong = `rgba(${ink},0.4)`
  const cNodeDim = `rgba(${ink},0.5)`
  const cBorder = `rgba(${ink},0.15)`
  const wrapRef = useRef(null)
  const fgRef = useRef(null)
  const [width, setWidth] = useState(600)
  // The "active" node whose connections popup is pinned open. Set when you hover
  // a node; it STAYS (does not clear on mouse-leave) until you close it (✕) or
  // hover a different node. Highlight + popup both use it.
  const [activeNode, setActiveNode] = useState(null)
  const hi = useMemo(() => new Set(highlight || []), [highlight])
  const endId = (v) => (v && typeof v === 'object' ? v.id : v)
  const neighbourLabel = edgeLabel === 'member' ? 'Band' : 'Musician'

  const [data, setData] = useState({ nodes: [], links: [] })
  // Reset the graph (and any pinned popup) when the source data changes.
  useEffect(() => {
    setData({ nodes: nodes.map((n) => ({ ...n })), links: links.map((l) => ({ ...l })) })
    setActiveNode(null)
  }, [nodes, links])

  // The active node's connections: each neighbour + the shared member/band.
  const connections = useMemo(() => {
    if (!activeNode) return []
    const out = []
    for (const l of data.links) {
      const s = endId(l.source), t = endId(l.target)
      if (s !== activeNode.id && t !== activeNode.id) continue
      const other = s === activeNode.id ? l.target : l.source
      const name = typeof other === 'object' ? other.name : (data.nodes.find((n) => n.id === other)?.name ?? '?')
      out.push({ name, via: l.label })
    }
    return out.sort((a, b) => a.name.localeCompare(b.name))
  }, [activeNode, data])

  // Keep the canvas as wide as its container.
  useEffect(() => {
    if (!wrapRef.current) return
    const ro = new ResizeObserver(([e]) => setWidth(e.contentRect.width))
    ro.observe(wrapRef.current)
    return () => ro.disconnect()
  }, [])

  // Spread nodes much further apart (default forces bunch them into an unreadable
  // clump): stronger repulsion + longer links, then reheat.
  useEffect(() => {
    const fg = fgRef.current
    if (!fg) return
    fg.d3Force('charge')?.strength(-320)
    fg.d3Force('link')?.distance(90)
    fg.d3ReheatSimulation?.()
  }, [data])

  const expand = (node) => {
    fetch(`${API}${neighborsPath}?id=${node.id}`)
      .then((r) => r.json())
      .then((sub) => {
        setData((cur) => {
          if (cur.nodes.length >= MAX_NODES) return cur
          const byId = new Map(cur.nodes.map((n) => [n.id, n]))
          for (const n of sub.nodes) {
            if (!byId.has(n.id) && byId.size < MAX_NODES) byId.set(n.id, { id: n.id, name: n.name })
          }
          const nextNodes = [...byId.values()]
          const key = new Set(cur.links.map((l) => `${l.source.id ?? l.source}-${l.target.id ?? l.target}`))
          const nextLinks = [...cur.links]
          for (const l of sub.links) {
            const k = `${l.source}-${l.target}`
            if (!key.has(k) && byId.has(l.source) && byId.has(l.target)) {
              nextLinks.push({ source: l.source, target: l.target, label: l[edgeLabel] })
              key.add(k)
            }
          }
          return { nodes: nextNodes, links: nextLinks }
        })
      })
      .catch(() => {})
  }

  const activeId = activeNode?.id

  return (
    <div ref={wrapRef} className="relative h-full overflow-hidden rounded-2xl border"
         style={{ background: graphBg, borderColor: cBorder }}>
      <ForceGraph2D
        ref={fgRef}
        graphData={data}
        width={width}
        height={height}
        backgroundColor="rgba(0,0,0,0)"
        cooldownTicks={140}
        warmupTicks={40}
        nodeRelSize={5}
        enableNodeDrag={false}
        onEngineStop={() => fgRef.current?.zoomToFit(400, 50)}
        onNodeClick={onNodeClick || expand}
        onNodeHover={(node) => { if (node) setActiveNode(node) }}
        nodePointerAreaPaint={(node, color, ctx) => {
          // Generous invisible hit target so small nodes are easy to click/hover.
          ctx.fillStyle = color
          ctx.beginPath()
          ctx.arc(node.x, node.y, 12, 0, 2 * Math.PI)
          ctx.fill()
        }}
        linkColor={(l) => {
          const s = endId(l.source), t = endId(l.target)
          if (activeId != null && (s === activeId || t === activeId)) return accent
          return hi.has(s) && hi.has(t) ? cLineStrong : cLine
        }}
        linkWidth={(l) => {
          const s = endId(l.source), t = endId(l.target)
          if (activeId != null && (s === activeId || t === activeId)) return 2
          return hi.has(s) && hi.has(t) ? 2.5 : 1
        }}
        nodeCanvasObject={(node, ctx, scale) => {
          const on = hi.has(node.id)
          const hov = node.id === activeId
          const r = on || hov ? 6 : 4
          ctx.beginPath()
          ctx.arc(node.x, node.y, r, 0, 2 * Math.PI)
          ctx.fillStyle = on || hov ? accent : cNodeDim
          ctx.fill()
          if (on || hov) { ctx.strokeStyle = cLabel; ctx.lineWidth = 1.5; ctx.stroke() }
          const fs = 12 / scale
          ctx.font = `${on || hov ? 600 : 400} ${fs}px sans-serif`
          ctx.fillStyle = on || hov ? cLabel : cLabelDim
          ctx.textAlign = 'center'
          ctx.fillText(node.name, node.x, node.y + r + fs)
        }}
      />

      {/* pinned popup: a table of the node's connections. Stays until closed. */}
      {activeNode && connections.length > 0 && (
        <div className="absolute right-3 top-3 z-10 flex max-h-[88%] w-60 flex-col
                        border border-[var(--surface-border)] bg-[var(--menu)] text-[var(--menu-text)] shadow-2xl">
          <div className="flex items-center justify-between gap-2 border-b border-[var(--surface-border)] px-3 py-2">
            <p className="truncate text-sm font-semibold text-[var(--accent)]">{activeNode.name}</p>
            <button
              onClick={() => setActiveNode(null)}
              className="shrink-0 px-1.5 opacity-50 transition hover:opacity-100"
              aria-label="Close"
            >
              ✕
            </button>
          </div>
          <div className="overflow-auto">
            <table className="w-full text-xs">
              <thead className="sticky top-0 bg-[var(--menu)]">
                <tr className="uppercase tracking-wider opacity-40">
                  <th className="px-3 py-1.5 text-left font-normal">{neighbourLabel}</th>
                  <th className="px-3 py-1.5 text-left font-normal">via {edgeLabel}</th>
                </tr>
              </thead>
              <tbody>
                {connections.map((c, i) => (
                  <tr key={i} className="border-t border-[var(--surface-border)]">
                    <td className="px-3 py-1 opacity-90">{c.name}</td>
                    <td className="px-3 py-1 text-[var(--accent)]">{c.via || '—'}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      <p className="px-4 py-2 text-center text-xs uppercase tracking-wider" style={{ color: `rgba(${ink},0.35)` }}>
        Hover a node to pin its connections (✕ to close) · {onNodeClick ? 'click to centre' : 'click to explore'}
      </p>
    </div>
  )
}
