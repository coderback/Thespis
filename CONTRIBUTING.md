# Contributing

Two people, one weekend, no broken `main`. These rules keep us out of each other's way.

## The rules

1. **Nobody pushes to `main`.** GitHub enforces it: every change goes through a pull request.
2. **CI must pass before merging.** The `ci` check runs lint and tests for the engine and the client.
3. **Your branch must be up to date with `main` before it merges.** Use GitHub's "Update branch" button,
   or `git pull --rebase origin main` locally.
4. **Squash merge only.** One commit per PR keeps history readable and easy to revert.
5. **Stay in your folders.** See the ownership map below. Touching someone else's folder is fine when needed,
   but ask them to review.
6. **The contract changes together.** If you change an API shape, update `docs/api.md` and `fixtures/` in
   the same PR and request the other person's review.
7. **No secrets in git.** Keys live in `.env`, which is ignored.

## Ownership

| Path | Owner |
| --- | --- |
| `thespis/`, `games/`, `tests/`, `tools/`, `.github/` | Tobi (@coderback) |
| `client/` | Ahmed (@AhmedBokaniUsman) |
| `docs/api.md`, `fixtures/` | Both: changes need the other's review |

`CODEOWNERS` requests the right reviewer automatically.

## Day-to-day flow

```bash
git checkout main
git pull
git checkout -b ahmed/13-play-ui        # <name>/<issue number>-<short-slug>

# ...work, commit small and often...
git push -u origin ahmed/13-play-ui
gh pr create --fill                     # or open the PR on GitHub
```

- Put `Closes #13` in the PR description so the issue closes when it merges.
- Keep PRs small: one issue per PR where possible. Merge your own PR once CI is green,
  unless it touches the contract or the other person's folder.
- Use draft PRs for work in progress you want the other person to see early.
- Commit messages: short imperative subject, e.g. `Add gate check to tick`.

## Where work is tracked

- **Issues** are the to-do list. Each has an owner label, an area, a milestone and a "Done when" check.
- **Milestones** follow the build plan:

| Milestone | Due (UK time) |
| --- | --- |
| M0 Kickoff | Sat 12:00 |
| M1 Fallback playable | Sat 18:00 (Integration 1) |
| M2 Live model on host | Sat 22:00 (Integration 2) |
| M3 Feature freeze | Sun 09:30 |
| M4 Submitted | Sun 12:30 |
| Stretch | Only after M2; switch off anything not working by Sun 08:30 |

- **Labels:** `owner:*`, `area:*`, `type:*`, priority `P0` to `P2`, and `stretch`.
  `P0` items are the ones the demo cannot ship without.

## If main breaks anyway

Revert the offending squash commit with a PR (`git revert <sha>`), get CI green, merge, then fix forward on a branch.
