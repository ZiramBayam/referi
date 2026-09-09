# Fonts vendored into this repository

Three typefaces ship in this folder as `.woff2` files. All three are licensed under the
**SIL Open Font License 1.1**, which permits redistribution inside this MIT-licensed
repository provided the fonts themselves stay under the OFL and are not sold on their own.

| File | Family | Copyright | Licence |
|---|---|---|---|
| `Fraunces-Variable.woff2` | Fraunces | Copyright 2020 The Fraunces Project Authors | OFL 1.1 |
| `SpaceGrotesk-Variable.woff2` | Space Grotesk | Copyright 2020 The Space Grotesk Project Authors | OFL 1.1 |
| `JetBrainsMono-Variable.woff2` | JetBrains Mono | Copyright 2020 The JetBrains Mono Project Authors | OFL 1.1 |

Full licence text: <https://openfontlicense.org/open-font-license-official-text/>

**Why vendored rather than loaded from a CDN.** Judges run this demo locally, and the
evidence pages must render identically with the network off. Fetching the fonts from
`fonts.gstatic.com` at build or run time would make the page depend on a third-party host
that is not part of the submission. Each file is the latin subset only (`U+0000-00FF`),
so the three together add roughly 120 KB.
