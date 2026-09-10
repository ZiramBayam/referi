import { Fraunces, Hanken_Grotesk, IBM_Plex_Mono } from "next/font/google";

export const display = Fraunces({
  variable: "--font-display",
  subsets: ["latin"],
  axes: ["opsz", "SOFT", "WONK"],
});

export const sans = Hanken_Grotesk({
  variable: "--font-sans",
  subsets: ["latin"],
});

export const mono = IBM_Plex_Mono({
  variable: "--font-mono",
  subsets: ["latin"],
  weight: ["400", "500", "600"],
});
