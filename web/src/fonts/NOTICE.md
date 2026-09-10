# Fonts used by this site

Three typefaces are loaded through `next/font/google` in `veritas-fonts.js`. All three are
licensed under the **SIL Open Font License 1.1**, which permits redistribution inside this
MIT-licensed repository provided the fonts themselves stay under the OFL and are not sold
on their own.

| Family | Role | Copyright | Licence |
|---|---|---|---|
| Fraunces | display, for headings and the wordmark | Copyright 2020 The Fraunces Project Authors | OFL 1.1 |
| Hanken Grotesk | sans, for prose and interface | Copyright 2020 The Hanken Grotesk Project Authors | OFL 1.1 |
| IBM Plex Mono | mono, for values, hashes, selectors, state labels | Copyright 2017 IBM Corp. | OFL 1.1 |

Full licence text: <https://openfontlicense.org/open-font-license-official-text/>

**No font file is vendored into this folder, and the running site fetches none.**
`next/font/google` downloads each face at **build** time and emits it as a self-hosted asset
under `.next/static/media`, together with the `@font-face` rules and a preload hint. The
served page therefore makes no request to `fonts.gstatic.com`: judges running `next start`
offline see the same typography. What does need the network is `next build`.

Three families were previously vendored here as `.woff2`, two of which (Space Grotesk,
JetBrains Mono) the site stopped rendering when `web/` adopted the Veritas type system
(ADR-032). They were removed rather than left behind with a notice describing faces no page
loads; `git log` still has them.
