import "./globals.css";
import { display, sans, mono } from "../fonts/veritas-fonts.js";
import { ThemeProvider, themeInitScript } from "../components/theme/ThemeProvider.jsx";
import { LandingLens } from "../components/ProofLens.jsx";
import { Nav } from "../components/Nav.jsx";
import { Footer } from "../components/Footer.jsx";

const DIRECTION_CONTRACT = [
  "THESIS: Referi is a proof gate for autonomous value movement; it refuses the category-default dashboard that reports activity without changing permission.",
  "OWN-WORLD: The Veritas instrument system, pinned by the client: a chroma-0 neutral scale in oklch, one brand blue #004eff, three signal colors reserved for proof state, 14px hairline-bordered panels on a quiet surface, Fraunces display over Hanken Grotesk prose and IBM Plex Mono data. True light and dark, never a tinted near-black.",
  "STORY: The overview makes the mechanism legible and hands the visitor one way in. Inside the execution room they propose a bounded treasury rebalance, watch the agent recall stale-oracle memory, see the action block, refresh the fixture, receive a Passport, and test exactly-once enforcement.",
  "FIRST VIEWPORT: Two surfaces, split. The overview opens over the ProofLens field with the product thesis, one primary action into the execution room, and a summary of what is enforced on the right. The execution room itself opens on a sticky stage rail above four numbered steps that follow the real execution order: propose, preflight, passport, execute.",
  "FORM: Client-pinned direction; the Veritas-UHI9 frontend is the visual authority and Referi supplies every fact.",
  "MOTION: Two authored moments. In the execution room, the gate resolving: obligations arrive staggered under a scanline, the decision chip is replaced key-first with no exit, and the passport unseals by clip-path. On the overview, the GateChain diagram running its own chain, each connector drawing itself and each node lighting as the flow reaches it, stopped whenever the figure is offscreen. Everything else is feedback: a sliding nav marker and scroll reveals. Numbers never animate: a stalled count leaves a wrong figure on a claim about state.",
  "FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, DESIGN.md, and every shipping raster carrying its provenance",
].join("\n");

export const metadata = {
  title: "Referi · proof before permission",
  description:
    "An incident-conditioned control plane for agent execution on high-stakes DeFi actions.",
};

/** @param {{ children: unknown }} props */
export default function RootLayout({ children }) {
  return (
    <html
      lang="en"
      data-scroll-behavior="smooth"
      suppressHydrationWarning
      className={`${display.variable} ${sans.variable} ${mono.variable} h-full antialiased`}
    >
      <body className="min-h-full bg-bg text-ink">
        {/* Kontrak arah, sebagai komentar HTML pertama di dalam <body>: ia harus selamat
            dari build produksi supaya keputusan desainnya bisa diaudit dari output. */}
        <div
          className="hidden"
          aria-hidden="true"
          dangerouslySetInnerHTML={{ __html: `<!-- ${DIRECTION_CONTRACT} -->` }}
        />
        <script dangerouslySetInnerHTML={{ __html: themeInitScript }} />
        <a
          href="#content"
          className="sr-only focus:not-sr-only focus:absolute focus:left-4 focus:top-4 focus:z-50 focus:rounded-lg focus:border focus:border-border-strong focus:bg-surface focus:px-4 focus:py-2 focus:text-sm focus:text-ink"
        >
          Skip to content
        </a>
        <ThemeProvider>
          <LandingLens />
          <div className="relative z-10 flex min-h-screen flex-col">
            <Nav />
            <main id="content" className="flex-1">
              {children}
            </main>
            <Footer />
          </div>
        </ThemeProvider>
      </body>
    </html>
  );
}
