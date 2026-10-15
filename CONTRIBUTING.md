# Contributing

Thanks for your interest in Six Degrees of Rock. This is primarily a showcase
and learning project, but issues and pull requests are welcome.

## Reporting a wrong connection

If a chain looks wrong (two bands linked by someone who was never a member),
open an issue with the two endpoints and the chain the app returned. Most data
problems trace back to MusicBrainz itself; if so, the best fix is to
[edit MusicBrainz](https://musicbrainz.org/doc/How_to_Contribute) so everyone
benefits.

## Development

Follow [Getting started](README.md#getting-started) to run the database, API and
UI locally. Before opening a pull request:

```bash
# backend smoke test (from backend/)
python graph.py

# frontend (from frontend/)
npm run lint
npm run build
```

## Guidelines

- Keep changes focused; one concern per pull request.
- Record any modeling or scope decision in [docs/PROJECT_STATE.md](docs/PROJECT_STATE.md)
  together with its reasoning, the same way the existing decisions are written.
- Be gentle with MusicBrainz: keep the 1 request/second rate limit and the
  response cache, and set `MB_CONTACT` to your own contact when crawling.
