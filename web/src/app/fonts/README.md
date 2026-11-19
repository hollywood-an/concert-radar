# Fonts

Both families are licensed under the [SIL Open Font License 1.1](https://openfontlicense.org)
and are served from this folder, so the build never fetches them from a font host.

| File | Family | Copyright |
|---|---|---|
| `BigShouldersDisplay-latin.woff2` | Big Shoulders Display (variable, weights 100–900) | Google Inc. (the Big Shoulders Project Authors) |
| `SchibstedGrotesk-latin.woff2` | Schibsted Grotesk (variable, weights 400–900) | 2023 The Schibsted-Grotesk Project Authors |

Each file is the Latin subset from the Fontsource packages
(`@fontsource-variable/big-shoulders-display` and `@fontsource-variable/schibsted-grotesk`,
version 5.3.0). Characters outside that subset fall back to the system font.
