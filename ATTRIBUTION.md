# Attribution and licenses

Minesweeper Thinking Lab was extracted from
[imom39a/jev-playground](https://github.com/imom39a/jev-playground) on
September 22, 2026. The extraction includes the three experiment variants,
tests, research and recorded results. [EXTRACTION.json](EXTRACTION.json) records
the source commit and hashes of the actual files, including the research work
that was uncommitted in the source workspace. The original playground remains
available separately.

The Minesweeper playground was extracted from an internal Minesweeper
prototype. Its game rules, bounded candidate state,
provider adapters, server lifecycle, and browser views remain attributable to
that source project and its author.

The playground calls these external services at runtime:

- [TypeSafe System One / JEV](https://docs.typesafe.ai/) for structured cell
  choices.
- [OpenRouter](https://openrouter.ai/docs) for the conventional LLM lane.

Those services and their SDKs/API terms apply to their use. This repository's
original source is released under the Apache License, Version 2.0; see
[LICENSE](LICENSE).

The included `.agents/skills/typesafe-ai/SKILL.md` declares its own MIT license.
Linked research and external services retain their respective ownership; the
research documents cite sources rather than redistributing their full text.
