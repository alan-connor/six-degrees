# Six Degrees of Rock — frontend

Vite + React 19 + Tailwind CSS v4 single-page app, with the graph drawn by
[react-force-graph-2d](https://github.com/vasturiano/react-force-graph).

```bash
npm install
npm run dev      # http://localhost:5173 (expects the API on http://127.0.0.1:8000)
npm run build    # production build to dist/
npm run lint     # oxlint
```

| File | Purpose |
|---|---|
| `src/App.jsx` | Band comboboxes, path search, random connection, themes |
| `src/GraphView.jsx` | Force-directed graph: path view, hover-to-pin, click-to-explore |

See the [root README](../README.md) for the full project, setup and API reference.
