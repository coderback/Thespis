# client/

The browser client: map, play UI, inspector, autoplay. Owned by @AhmedBokaniUsman.

- The client holds no game logic. It sends verbs, renders state and animates moves.
- Build against `fixtures/` until the engine is live, then against the API in `docs/api.md`.
- If you add a `package.json`, CI will run `npm ci`, then `lint`, `test` and `build` scripts if they exist.
- Production build output is served by the engine as static files, so the game and API share one URL.
