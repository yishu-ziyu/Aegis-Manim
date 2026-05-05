# Manim Knowledge Layer Task

- [x] Inspect existing prompt and generation flow.
- [x] Verify local Manim runtime version.
- [x] Add a compact Manim syntax and pattern knowledge pack.
- [x] Load the knowledge pack through CLI and Web generation paths.
- [x] Add tests for prompt context injection.
- [x] Run lint, tests, compile checks, and a generation/render smoke test.

## Review

Implemented a prompt-level Manim knowledge layer loaded by both CLI and Web generation paths. Verified with lint, 18 focused tests, compile checks, and a real `codex-cli` Web request that generated and rendered `GeneratedScene`.
