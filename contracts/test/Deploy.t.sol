// SPDX-License-Identifier: MIT
pragma solidity 0.8.36;

import {Test} from "forge-std/Test.sol";
import {Deploy} from "../script/Deploy.s.sol";
import {EvaluatorVault} from "../src/EvaluatorVault.sol";

/// @dev Membuka helper `internal` skrip deploy untuk diuji.
contract DeployHarness is Deploy {
    function exposedValidate(
        address acp,
        address agent,
        address arbiter,
        address deployer,
        uint256 expectedChainId,
        bool allowArbiterEqAgent
    ) external view {
        _validate(acp, agent, arbiter, deployer, expectedChainId, allowArbiterEqAgent);
    }
}

/// @notice Tes untuk `script/Deploy.s.sol`.
/// @dev Dua fokus:
///      1. Guard konsistensi (`_validate`) — semua argumen konstruktor vault immutable, jadi skrip
///         adalah satu-satunya tempat salah jaringan/ACP/agen/arbiter bisa dicegat.
///      2. SAMBUNGAN env → guard → konstruktor di `run()`. Ini yang dulu tidak diuji sama sekali:
///         satu-satunya tes env lama memakai nilai yang PERSIS SAMA dengan default tiap `vm.envOr`,
///         sehingga mengganti tiap `vm.envOr` dengan defaultnya — bahkan menghapus SELURUH panggilan
///         `_validate` dari `run()` — tetap lolos 137/137. `test_deployFromEnv_everyEnvVarIsWired`
///         di bawah memakai nilai yang BERBEDA dari default untuk setiap variabel, dan menuntut
///         perbedaan itu terlihat di vault atau di revert guard.
///
///      Parser `AGENT_PRIVATE_KEY` beserta seluruh tesnya DIHAPUS (ADR-016 tahap 2): kunci privat
///      sudah keluar dari jalur deploy, digantikan keystore Foundry `--account`.
///
///      CATATAN PARALELISME: `forge test` 1.7.1 menjalankan fungsi tes dalam satu kontrak secara
///      PARALEL, sedangkan `vm.setEnv` mengubah environment PROSES. Karena itu HANYA SATU fungsi di
///      berkas ini yang menulis env; sisanya memanggil guard secara langsung. Versi lama yang menulis
///      env dari banyak fungsi terbukti flaky (5 dari 24 tes gagal acak).
contract DeployTest is Test {
    /// Nilai uji (bukan alamat nyata; ACP nyata ada di docs/versions.md, dibaca dari env).
    address internal constant ACP_TEST = address(0xACADE);
    address internal constant ARBITER_TEST = address(0xA4B17E);
    address internal constant AGENT_TEST = address(0xA6E7);
    uint256 internal constant CHAIN_TEST = 84532;

    DeployHarness internal harness;

    function setUp() public {
        harness = new DeployHarness();
    }

    // ------------------------------------------------------------------
    // Guard konsistensi sebelum konstruktor immutable
    // ------------------------------------------------------------------

    function test_validate_happyPath() public {
        vm.chainId(CHAIN_TEST);
        vm.etch(ACP_TEST, hex"60006000fd"); // kode apa pun; guard hanya melihat `code.length`
        harness.exposedValidate(ACP_TEST, AGENT_TEST, ARBITER_TEST, AGENT_TEST, CHAIN_TEST, false);
    }

    function test_validate_wrongChainReverts() public {
        vm.chainId(31337);
        vm.etch(ACP_TEST, hex"60006000fd");
        vm.expectRevert(Deploy.WrongChain.selector);
        harness.exposedValidate(ACP_TEST, AGENT_TEST, ARBITER_TEST, AGENT_TEST, CHAIN_TEST, false);
    }

    function test_validate_acpWithoutCodeReverts() public {
        vm.chainId(CHAIN_TEST);
        assertEq(ACP_TEST.code.length, 0, "prasyarat: ACP_TEST masih EOA");
        vm.expectRevert(Deploy.AcpNotContract.selector);
        harness.exposedValidate(ACP_TEST, AGENT_TEST, ARBITER_TEST, AGENT_TEST, CHAIN_TEST, false);
    }

    function test_validate_agentMismatchReverts() public {
        vm.chainId(CHAIN_TEST);
        vm.etch(ACP_TEST, hex"60006000fd");
        vm.expectRevert(Deploy.AgentMismatch.selector);
        harness.exposedValidate(ACP_TEST, address(0xBEEF), ARBITER_TEST, AGENT_TEST, CHAIN_TEST, false);
    }

    function test_validate_arbiterEqualsAgentReverts() public {
        vm.chainId(CHAIN_TEST);
        vm.etch(ACP_TEST, hex"60006000fd");
        vm.expectRevert(Deploy.ArbiterEqualsAgent.selector);
        harness.exposedValidate(ACP_TEST, AGENT_TEST, AGENT_TEST, AGENT_TEST, CHAIN_TEST, false);
    }

    /// Escape hatch eksplisit — dipertahankan supaya deploy 84532 lama tetap bisa direproduksi,
    /// walau sesudah task 1.2c-arb arbiter adalah EOA terpisah dan jalur ini tidak dipakai lagi.
    function test_validate_arbiterEqualsAgentAllowedByEscapeHatch() public {
        vm.chainId(CHAIN_TEST);
        vm.etch(ACP_TEST, hex"60006000fd");
        harness.exposedValidate(ACP_TEST, AGENT_TEST, AGENT_TEST, AGENT_TEST, CHAIN_TEST, true);
    }

    /// Escape hatch TIDAK melonggarkan guard lain.
    function test_validate_escapeHatchDoesNotBypassOtherGuards() public {
        vm.chainId(31337);
        vm.etch(ACP_TEST, hex"60006000fd");
        vm.expectRevert(Deploy.WrongChain.selector);
        harness.exposedValidate(ACP_TEST, AGENT_TEST, AGENT_TEST, AGENT_TEST, CHAIN_TEST, true);

        vm.chainId(CHAIN_TEST);
        vm.expectRevert(Deploy.AgentMismatch.selector);
        harness.exposedValidate(ACP_TEST, address(0xBEEF), address(0xBEEF), AGENT_TEST, CHAIN_TEST, true);
    }

    // ------------------------------------------------------------------
    // Sambungan env → guard → konstruktor — SATU-SATUNYA penulis env di berkas ini
    // ------------------------------------------------------------------

    /// @dev Setiap blok di bawah mematikan satu mutan yang HARI INI lolos (utang tes ADR-016):
    ///      D1 `_validate` dihapus dari `run()`            → blok B & C (revert guard hilang).
    ///      D2 `AGENT_ADDRESS`  diganti default `deployer` → blok B (mismatch tidak lagi terdeteksi).
    ///      D3 `MIN_BOND_WEI`   diganti default 0          → blok A (`MIN_BOND` != 7 wei).
    ///      D4 `CHAIN_ID`       diganti default 84532      → blok D (deploy di chain 31337 revert).
    ///      D5 `ALLOW_ARBITER_EQ_AGENT` diganti default false → blok E (deploy sah jadi revert).
    ///      D6 `ACP_ADDRESS`    tidak lagi dari env        → blok A (`vault.acp()` != ACP_TEST).
    ///      D7 `ARBITER_ADDRESS` tidak lagi dari env       → blok A (`vault.arbiter()` != ARBITER_TEST).
    ///      D13 `ARBITER_ADDRESS` jadi ber-default (`vm.envOr`) → blok F (env wajib yang hilang lolos).
    ///      D14 `ACP_ADDRESS` jadi ber-default (`vm.envOr`)     → blok F (idem).
    ///      `deployer` diambil dari `msg.sender`, jadi di sini ia = alamat kontrak tes ini.
    function test_deployFromEnv_everyEnvVarIsWired() public {
        address deployer = address(this);
        vm.etch(ACP_TEST, hex"60006000fd");

        // --- Blok A: nilai NON-DEFAULT untuk tiap variabel benar-benar sampai ke konstruktor.
        vm.chainId(CHAIN_TEST);
        vm.setEnv("ACP_ADDRESS", vm.toString(ACP_TEST));
        vm.setEnv("ARBITER_ADDRESS", vm.toString(ARBITER_TEST));
        vm.setEnv("AGENT_ADDRESS", vm.toString(deployer));
        vm.setEnv("CHAIN_ID", vm.toString(CHAIN_TEST));
        vm.setEnv("MIN_BOND_WEI", "7"); // != default 0
        vm.setEnv("ALLOW_ARBITER_EQ_AGENT", "false");

        EvaluatorVault vault = harness.run();
        assertEq(address(vault.acp()), ACP_TEST, "ACP_ADDRESS harus berasal dari env");
        assertEq(vault.arbiter(), ARBITER_TEST, "ARBITER_ADDRESS harus berasal dari env");
        assertEq(vault.agent(), deployer, "agent = AGENT_ADDRESS = --sender");
        assertEq(vault.MIN_BOND(), 7, "MIN_BOND_WEI harus berasal dari env, bukan default 0");

        // --- Blok B: `AGENT_ADDRESS` yang berbeda dari `--sender` DICEGAT, bukan didiamkan.
        vm.setEnv("AGENT_ADDRESS", vm.toString(address(0xBEEF)));
        vm.expectRevert(Deploy.AgentMismatch.selector);
        harness.run();
        vm.setEnv("AGENT_ADDRESS", vm.toString(deployer));

        // --- Blok C: guard chain dipanggil dari `run()` (bukan hanya ada di `_validate`).
        vm.chainId(31337);
        vm.expectRevert(Deploy.WrongChain.selector);
        harness.run();

        // --- Blok D: `CHAIN_ID` non-default benar-benar dibaca — deploy di 31337 justru harus SAH.
        vm.setEnv("CHAIN_ID", "31337");
        EvaluatorVault onLocal = harness.run();
        assertEq(onLocal.agent(), deployer, "deploy di chain non-default harus berhasil");
        vm.chainId(CHAIN_TEST);
        vm.setEnv("CHAIN_ID", vm.toString(CHAIN_TEST));

        // --- Blok E: `ALLOW_ARBITER_EQ_AGENT` non-default membuka jalur yang default-nya ditolak.
        vm.setEnv("ARBITER_ADDRESS", vm.toString(deployer));
        vm.expectRevert(Deploy.ArbiterEqualsAgent.selector);
        harness.run();

        vm.setEnv("ALLOW_ARBITER_EQ_AGENT", "true");
        EvaluatorVault fused = harness.run();
        assertEq(fused.arbiter(), fused.agent(), "escape hatch: arbiter == agent diizinkan eksplisit");

        // --- Blok F: env WAJIB yang HILANG harus MENGHENTIKAN deploy (mutan D13/D14).
        // Yang diuji di sini BUKAN "apakah nilai env sampai ke kontrak" (blok A) melainkan "apakah
        // variabel wajib yang tidak di-set benar-benar menghentikan deploy". Bedanya nyata:
        // mengganti `vm.envAddress("ARBITER_ADDRESS")` menjadi `vm.envOr(..., deployer)` membuat
        // `ARBITER_ADDRESS` yang lupa di-set jatuh diam-diam ke `--sender` — dan `arbiter` IMMUTABLE,
        // jadi salah = redeploy (plus arbiter yang identik dengan agen: pemegang `sweepToken` = yang
        // memutus verdict).
        //
        // forge 1.7.1 tidak punya cheatcode untuk MENGHAPUS variabel env (`Vm.sol` hanya punya
        // `setEnv`), jadi yang dipakai adalah nilai KOSONG. Itu memang membedakan keduanya, dan ini
        // diukur bukan diasumsikan: dengan `vm.envAddress` blok ini REVERT, dengan `vm.envOr` ia
        // SUKSES — `envOr` memperlakukan nilai kosong sama dengan "tidak di-set".
        //
        // `ALLOW_ARBITER_EQ_AGENT` sengaja dibiarkan "true" di sini: kalau guard `ArbiterEqualsAgent`
        // aktif, ia akan ikut merevert pada varian `envOr` (arbiter default = deployer = agent) dan
        // MENUTUPI pertanyaan yang sedang diuji.
        vm.setEnv("ALLOW_ARBITER_EQ_AGENT", "true");
        vm.setEnv("ARBITER_ADDRESS", "");
        (bool okNoArbiter,) = address(harness).call(abi.encodeWithSignature("run()"));
        assertFalse(okNoArbiter, "ARBITER_ADDRESS kosong WAJIB menghentikan deploy");
        vm.setEnv("ARBITER_ADDRESS", vm.toString(ARBITER_TEST));

        vm.setEnv("ACP_ADDRESS", "");
        (bool okNoAcp,) = address(harness).call(abi.encodeWithSignature("run()"));
        assertFalse(okNoAcp, "ACP_ADDRESS kosong WAJIB menghentikan deploy");
        vm.setEnv("ACP_ADDRESS", vm.toString(ACP_TEST));

        // Kontrol positif: dengan kedua variabel dipulihkan, `run()` yang sama SUKSES. Tanpa ini,
        // dua assert di atas bisa hijau karena sebab lain yang tidak ada hubungannya dengan env.
        (bool okRestored,) = address(harness).call(abi.encodeWithSignature("run()"));
        assertTrue(okRestored, "kontrol positif: env lengkap harus tetap bisa deploy");

        // Kembalikan env ke bentuk netral supaya tidak ada nilai aneh yang tertinggal di proses.
        vm.setEnv("ALLOW_ARBITER_EQ_AGENT", "false");
        vm.setEnv("ARBITER_ADDRESS", vm.toString(ARBITER_TEST));
        vm.setEnv("MIN_BOND_WEI", "0");
    }
}
