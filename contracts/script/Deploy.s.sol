// SPDX-License-Identifier: MIT
pragma solidity 0.8.36;

import {Script} from "forge-std/Script.sol";
import {console} from "forge-std/console.sol";
import {EvaluatorVault} from "../src/EvaluatorVault.sol";
import {IACP} from "../src/IACP.sol";

/// @title Deploy — men-deploy EvaluatorVault.
/// @notice Semua alamat dibaca dari environment; TIDAK ADA alamat hardcode di file ini.
///         Nilai yang sah untuk `ACP_ADDRESS` ada di `docs/versions.md`
///         (Base Sepolia 84532: 0x0b93793923CD5De81850aF8604a233f3f24d461e).
/// @dev Jalankan (ADR-016 tahap 2 — keystore terenkripsi, BUKAN kunci di `.env`):
///        forge script script/Deploy.s.sol:Deploy --rpc-url $RPC_URL --broadcast \
///            --account agent --sender 0xfa5AF5BAeB4aC500267D7189fa1f0AA923eCA894
///      (`--sender` WAJIB alamat LITERAL: `scripts/guard.sh` memblokir argumen hasil substitusi
///      perintah. Keystore dibuat sekali dengan `cast wallet import agent --interactive`.)
///
///      KUNCI PRIVAT TIDAK PERNAH MASUK KE SKRIP INI. Tidak ada `vm.envString("AGENT_PRIVATE_KEY")`,
///      tidak ada cheatcode `vm.addr`, dan `vm.startBroadcast()` dipanggil TANPA argumen — kunci tidak
///      pernah menjadi argumen cheatcode. Itu menutup kebocoran `--json` di AKARNYA (ADR-016): keluaran
///      `--json` mendump calldata cheatcode MENTAH tanpa sensor, sehingga bentuk lama — `vm.addr` dan
///      `vm.startBroadcast` yang menerima kunci sebagai ARGUMEN — mencetak kunci utuh 2x per run, pada
///      jalur SUKSES dan di verbositas DEFAULT.
///      `AGENT_PRIVATE_KEY` TETAP ada di `.env` untuk `agent/vault_client.py` (web3.py),
///      tetapi ia sudah keluar dari jalur deploy. Larangan `--json` di `Makefile`/`scripts/guard.sh`
///      sengaja DIPERTAHANKAN sebagai lapis kedua, bukan sebagai satu-satunya pertahanan.
///
///      Alamat vault hasil deploy dibaca dari baris `EvaluatorVault …` (`console.log`) atau dari
///      artefak `contracts/broadcast/Deploy.s.sol/84532/run-latest.json`.
///
///      `deployer` = `msg.sender`, yaitu alamat `--sender`. Nilai itu HANYA dipakai sebagai
///      pembanding guard (`AgentMismatch`) dan sebagai default `AGENT_ADDRESS`.
///
///      Env yang dibaca:
///        ACP_ADDRESS       (wajib) kontrak ACP di jaringan target; WAJIB punya kode.
///        ARBITER_ADDRESS   (wajib) arbiter sengketa. Sejak task 1.2c ia pemegang satu-satunya kunci
///                          `sweepToken`, jadi salah alamat = fee evaluator tidak bisa dikeluarkan.
///        AGENT_ADDRESS     (opsional, default `msg.sender`) bila di-set WAJIB sama dengan `--sender`;
///                          vault menyimpan `agent` sebagai immutable, jadi salah alamat = vault yang
///                          tidak akan pernah bisa `postVerdict`.
///        CHAIN_ID          (opsional, default 84532) jaringan yang diharapkan. Deploy menolak
///                          jalan bila `block.chainid` berbeda — salah ketik `--rpc-url` tidak
///                          boleh berakhir jadi deploy ke jaringan lain.
///        MIN_BOND_WEI      (opsional, default 0) bond minimum sebelum agen boleh `postVerdict`.
///                          Default 0 dipilih sadar: selama ADR-013 berlaku vault belum punya jalur
///                          ETH keluar (`sweepToken` HANYA ERC-20), jadi bond yang disetor terkunci.
///                          Naikkan hanya setelah `resolve`/penarikan bond ada.
///        ALLOW_ARBITER_EQ_AGENT (opsional, default false) escape hatch eksplisit untuk
///                          `arbiter == agent`. Default MENOLAK: arbiter yang sama dengan agen
///                          meniadakan pemisahan peran, nilainya immutable, dan sejak `sweepToken`
///                          ada ia juga menyerahkan fee evaluator ke pihak yang memutus verdict.
///                          Sesudah task 1.2c-arb jalur ini seharusnya tidak dipakai lagi; guardnya
///                          tetap ada supaya deploy lama tetap bisa direproduksi.
contract Deploy is Script {
    /// @dev Base Sepolia (docs/versions.md §Jaringan & alamat). Dipakai hanya bila `CHAIN_ID` kosong.
    uint256 internal constant DEFAULT_CHAIN_ID = 84532;

    /// @dev `block.chainid` bukan jaringan yang diharapkan (`CHAIN_ID`).
    error WrongChain();
    /// @dev `ACP_ADDRESS` tidak punya kode di jaringan ini.
    error AcpNotContract();
    /// @dev `arbiter == agent` tanpa `ALLOW_ARBITER_EQ_AGENT=true`.
    error ArbiterEqualsAgent();
    /// @dev `AGENT_ADDRESS` di-set tetapi berbeda dari `--sender`.
    error AgentMismatch();

    function run() external returns (EvaluatorVault vault) {
        address deployer = msg.sender;

        address acp = vm.envAddress("ACP_ADDRESS");
        address arbiter = vm.envAddress("ARBITER_ADDRESS");
        address agent = vm.envOr("AGENT_ADDRESS", deployer);
        uint256 minBond = vm.envOr("MIN_BOND_WEI", uint256(0));
        uint256 expectedChainId = vm.envOr("CHAIN_ID", DEFAULT_CHAIN_ID);
        bool allowArbiterEqAgent = vm.envOr("ALLOW_ARBITER_EQ_AGENT", false);

        _validate(acp, agent, arbiter, deployer, expectedChainId, allowArbiterEqAgent);

        console.log("chainid   ", block.chainid);
        console.log("acp       ", acp);
        console.log("agent     ", agent);
        console.log("arbiter   ", arbiter);
        console.log("minBondWei", minBond);

        vm.startBroadcast();
        vault = new EvaluatorVault(IACP(acp), agent, arbiter, minBond);
        vm.stopBroadcast();

        console.log("EvaluatorVault", address(vault));
    }

    /// @notice Guard konsistensi. Semua nilai di bawah masuk ke immutable konstruktor dan vault
    ///         sendiri hanya punya cek `ZeroAddress()`, jadi skrip ini adalah SATU-SATUNYA tempat
    ///         kekeliruan berikut masih bisa dicegat. Semua revert, bukan warning.
    /// @dev Sengaja terpisah dari pembacaan env supaya bisa diuji tanpa menyentuh environment proses
    ///      (`vm.setEnv` bersifat global untuk seluruh proses `forge test` yang menjalankan fungsi
    ///      tes secara paralel — tes yang saling menimpa env satu sama lain jadi flaky). SAMBUNGAN
    ///      env → guard ini sendiri diuji `test_deployFromEnv_everyEnvVarIsWired`, satu-satunya
    ///      fungsi penulis env di `test/Deploy.t.sol`.
    function _validate(
        address acp,
        address agent,
        address arbiter,
        address deployer,
        uint256 expectedChainId,
        bool allowArbiterEqAgent
    ) internal view {
        if (block.chainid != expectedChainId) revert WrongChain();
        if (acp.code.length == 0) revert AcpNotContract();
        if (agent != deployer) revert AgentMismatch();
        if (arbiter == agent && !allowArbiterEqAgent) revert ArbiterEqualsAgent();
    }
}
