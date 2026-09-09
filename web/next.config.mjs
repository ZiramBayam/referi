// Konfigurasi sengaja minimal: demo dijalankan lokal (`next build` + `next start`),
// tanpa image optimizer, tanpa rewrite, tanpa telemetry tambahan.
/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  // Next menulis AGENTS.md + CLAUDE.md ke web/ setiap kali dev server hidup. Keduanya
  // bukan hasil kerja dan tidak pernah dibaca siapa pun di repo ini; tanpa baris ini
  // mereka terus muncul kembali di `git status`.
  agentRules: false,
};

export default nextConfig;
