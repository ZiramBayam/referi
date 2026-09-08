// Gerbang DEMO_MODE sisi `web/` — nilai mana yang MENYALA dan mana yang MATI.
//
// KENAPA ADA: bug yang ditutup di sini tidak terlihat sebagai galat. Dengan aturan lama
// (`process.env.DEMO_MODE !== "1"`), konfigurasi yang DIANJURKAN `.env.example`
// (`DEMO_MODE=true`) membuat tombol hapus memori tidak dirender sama sekali sementara
// endpoint penghapusnya hidup — §7 langkah 5 hilang tanpa satu pun pesan. Tes ini
// mengunci daftar nilainya ke daftar yang sama dengan `TRUE_FLAGS` di
// `agent/agent/vault_client.py`, dan mengunci juga bahwa daftar itu tidak diperlebar.

import test from "node:test";
import assert from "node:assert/strict";

import { isFlagOn, demoModeEnabled } from "../src/lib/demoMode.js";

// Disalin dari `TRUE_FLAGS` sisi agen. Kalau sisi sana berubah, tes ini yang gagal duluan.
const ON = ["1", "true", "yes", "demo"];

test("nilai yang sama dengan TRUE_FLAGS sisi agen menyalakan gerbang", () => {
  for (const v of ON) assert.equal(isFlagOn(v), true, `nilai ${JSON.stringify(v)}`);
});

test("huruf besar dan spasi di tepi tidak mengubah putusan", () => {
  for (const v of ["TRUE", "True", " true ", "YES", "Demo", "\t1\n"]) {
    assert.equal(isFlagOn(v), true, `nilai ${JSON.stringify(v)}`);
  }
});

test("env hadir tapi kosong = MATI (persis config_flag sisi agen)", () => {
  assert.equal(isFlagOn(""), false);
  assert.equal(isFlagOn("   "), false);
});

test("env tidak diset = MATI", () => {
  assert.equal(isFlagOn(undefined), false);
  assert.equal(isFlagOn(null), false);
});

test("daftarnya tidak diperlebar: nilai lain tetap MATI", () => {
  for (const v of ["0", "false", "no", "off", "on", "2", "y", "t", "enabled", "DEMO_MODE"]) {
    assert.equal(isFlagOn(v), false, `nilai ${JSON.stringify(v)}`);
  }
});

test("demoModeEnabled membaca process.env.DEMO_MODE saat DIPANGGIL, bukan saat impor", () => {
  const saved = process.env.DEMO_MODE;
  try {
    delete process.env.DEMO_MODE;
    assert.equal(demoModeEnabled(), false);
    process.env.DEMO_MODE = "true";
    assert.equal(demoModeEnabled(), true);
    process.env.DEMO_MODE = "false";
    assert.equal(demoModeEnabled(), false);
  } finally {
    if (saved === undefined) delete process.env.DEMO_MODE;
    else process.env.DEMO_MODE = saved;
  }
});
