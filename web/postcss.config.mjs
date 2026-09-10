// Tailwind v4 dipasang lewat plugin PostCSS resminya. Tidak ada `tailwind.config.js`:
// di v4 seluruh token hidup di `@theme inline` dalam `src/app/globals.css`, jadi hanya
// ada SATU tempat yang memegang sistem desain.
const config = {
  plugins: {
    "@tailwindcss/postcss": {},
  },
};

export default config;
