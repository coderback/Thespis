# client/

The browser client: map, play UI, inspector, autoplay. Owned by @AhmedBokaniUsman.

- The client holds no game logic. It sends verbs, renders state and animates moves (`docs/api.md`).
- Plain JavaScript modules and a `<canvas>`, built with Vite. No framework and no image files: the pixel art is drawn in code.
- Production build output (`dist/`) is served by the engine as static files, so the game and API share one URL.

## Run it

```bash
npm install
npm run dev        # http://localhost:5173, proxies the API to the engine on :8000 (ENGINE_URL to change)
npm test           # node --test: why-chain, fog, bursts and the fixture backend, against fixtures/
npm run lint
npm run build      # dist/, which uvicorn games.crypt_road.app:app serves at /
```

Start the engine first (`uvicorn games.crypt_road.app:app --reload` from the repo root), or open
`http://localhost:5173/?fixtures=1` to play the demo route from `fixtures/` with no engine at all.

URL parameters: `?s=<session>` resumes a run (set automatically, so a reload resumes), `?seed=7` starts new sessions on
another seed, `?api=<origin>` points at another engine, `?fixtures=1` uses the fixture backend.

## What's where

| File | What it does |
| --- | --- |
| `src/api.js` | The only module that talks to the engine. `HttpApi` (real engine, `X-Session` header) and `FixtureApi` (replays `fixtures/` along the demo route) share one interface |
| `src/model.js` | Pure helpers: names and text, fog (`mapFigures`), mind icons, belief bursts, the why-chain, reply ordering. Unit-tested |
| `src/map.js` | The 18 x 12 tile map at 3x: tweens with bob, shadow and arrival squash; fog of war with last-seen ghosts; phase tint with lit windows and the guard's torch at night; typed speech bubbles; icons; gossip lines; duel dice |
| `src/world.js`, `src/sprites.js` | The map and the five characters, painted in code |
| `src/bar.js` | Bottom bar: dialogue log with model/cache/fallback badges, buttons from `GET /allowed` (free actions outlined, phase-ending ones accented, disabled ones explain why on hover), the Talk box and the Tell... claim builder |
| `src/inspector.js` | Minds, Beliefs, Ledger and Why tabs, and the why-chain: line, decision, cited beliefs and events, and the ledger root marked true or false |
| `src/main.js` | The controller: sessions, the act flow (dice, reactions, offscreen lines, moves, greetings, digest), the epilogue, landing, end card, credits and dev panel |
| `src/autoplay.js` | "Watch the 60-second story": the frame-Kael route on seed 1 with captions. About 55 s on the fallback brain |

## Things to know

- **Click any spoken line** (in the log or the Why tab) to open its why-chain. Clicking an id chip jumps to that belief or event.
- **Fog:** only your stop is lit. NPCs fade out as they leave it, and a dashed ghost marks where you last saw them (`npcs[].last_seen`). The inspector always shows everything.
- **Phase-ending verbs:** reactions play first, then lines from tick decisions you could hear, then the walk, then greetings in the new phase. `GET /digest` is fetched while the moves animate.
- **Race end:** the fog lifts and the two epilogue ticks play out, then the end card shows the narrator's epilogue and what the world remembers.
- **Dev panel:** press <kbd>`</kbd>. Reload from disk, brain on or off (`/dev/brain`), cache hits seen, and a new session on any seed.
- `window.game` is the running controller, handy for recording (`game.act({verb: "wait"})`).
