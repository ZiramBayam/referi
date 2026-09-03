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
/// @dev Jalankan:
///      `forge script script/Deploy.s.sol:Deploy --rpc-url $RPC_URL --broadcast`
///
///      JANGAN menambahkan `--json` pada perintah itu, dan jangan menaruh `--json` di
///      Makefile/skrip/CI yang memanggil skrip ini (ADR-016). Skrip ini meneruskan
///      `AGENT_PRIVATE_KEY` sebagai ARGUMEN cheatcode (`vm.addr`, `vm.startBroadcast`), dan
///      keluaran `--json` mendump calldata cheatcode mentah TANPA sensor — kunci privat utuh
///      tercetak 2x per run, pada jalur SUKSES dan di verbositas DEFAULT. Bukti & rincian ada di
///      `_envPrivateKey`. Alamat vault hasil deploy TIDAK butuh `--json`: pakai baris
///      `EvaluatorVault …` dari `console.log`, atau baca artefak broadcast
///      `contracts/broadcast/Deploy.s.sol/84532/run-latest.json` dengan `python3` (artefak itu
///      berisi transaksi, bukan calldata cheatcode, jadi bersih dari kunci).
///      Env yang dibaca:
///        ACP_ADDRESS       (wajib) kontrak ACP di jaringan target; WAJIB punya kode.
///        ARBITER_ADDRESS   (wajib) arbiter sengketa (perannya belum aktif, ADR-013)
///        AGENT_PRIVATE_KEY (wajib) wallet agen evaluator; juga dipakai sebagai deployer.
///                          Diterima DENGAN maupun TANPA prefiks `0x` (lihat `_envPrivateKey`).
///        AGENT_ADDRESS     (opsional) bila di-set WAJIB sama dengan alamat turunan
///                          `AGENT_PRIVATE_KEY`; vault menyimpan `agent` sebagai immutable, jadi
///                          salah alamat = vault yang tidak akan pernah bisa `postVerdict`.
///        CHAIN_ID          (opsional, default 84532) jaringan yang diharapkan. Deploy menolak
///                          jalan bila `block.chainid` berbeda — salah ketik `--rpc-url` tidak
///                          boleh berakhir jadi deploy ke jaringan lain.
///        MIN_BOND_WEI      (opsional, default 0) bond minimum sebelum agen boleh `postVerdict`.
///                          Default 0 dipilih sadar: selama ADR-013 berlaku vault belum punya jalur
///                          ETH keluar, jadi bond yang disetor akan terkunci. Naikkan hanya setelah
///                          `resolve`/penarikan bond ada.
///        ALLOW_ARBITER_EQ_AGENT (opsional, default false) escape hatch eksplisit untuk
///                          `arbiter == agent`. Default MENOLAK: arbiter yang sama dengan agen
///                          meniadakan pemisahan peran, dan nilainya immutable.
contract Deploy is Script {
    /// @dev Base Sepolia (docs/versions.md §Jaringan & alamat). Dipakai hanya bila `CHAIN_ID` kosong.
    uint256 internal constant DEFAULT_CHAIN_ID = 84532;

    /// @dev `AGENT_PRIVATE_KEY` kosong atau hanya spasi.
    error MissingPrivateKey();
    /// @dev `AGENT_PRIVATE_KEY` bukan 64 digit heksadesimal (dengan atau tanpa prefiks `0x`).
    ///      Sengaja TANPA parameter: memasukkan nilainya ke pesan revert = membocorkannya ke
    ///      stdout/stderr dan ke setiap log yang menyimpan keluaran perintah.
    error InvalidPrivateKeyFormat();
    /// @dev `AGENT_PRIVATE_KEY` tanpa prefiks dan seluruhnya digit 0-9 → tidak bisa dibedakan
    ///      antara heksadesimal dan desimal. Tambahkan `0x` bila memang heksadesimal.
    error AmbiguousPrivateKeyFormat();
    /// @dev `block.chainid` bukan jaringan yang diharapkan (`CHAIN_ID`).
    error WrongChain();
    /// @dev `ACP_ADDRESS` tidak punya kode di jaringan ini.
    error AcpNotContract();
    /// @dev `arbiter == agent` tanpa `ALLOW_ARBITER_EQ_AGENT=true`.
    error ArbiterEqualsAgent();
    /// @dev `AGENT_ADDRESS` di-set tetapi berbeda dari alamat turunan `AGENT_PRIVATE_KEY`.
    error AgentMismatch();

    function run() external returns (EvaluatorVault vault) {
        uint256 deployerKey = _envPrivateKey();
        address deployer = vm.addr(deployerKey);

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

        vm.startBroadcast(deployerKey);
        vault = new EvaluatorVault(IACP(acp), agent, arbiter, minBond);
        vm.stopBroadcast();

        console.log("EvaluatorVault", address(vault));
    }

    /// @notice Guard konsistensi. Semua nilai di bawah masuk ke immutable konstruktor dan vault
    ///         sendiri hanya punya cek `ZeroAddress()`, jadi skrip ini adalah SATU-SATUNYA tempat
    ///         kekeliruan berikut masih bisa dicegat. Semua revert, bukan warning.
    /// @dev Sengaja terpisah dari pembacaan env supaya bisa diuji tanpa menyentuh environment proses
    ///      (`vm.setEnv` bersifat global untuk seluruh proses `forge test` yang menjalankan fungsi
    ///      tes secara paralel — tes yang saling menimpa env satu sama lain jadi flaky).
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

    /// @notice Membaca `AGENT_PRIVATE_KEY` dan menerima KEDUA bentuk penyimpanan yang lazim di
    ///         berkas `.env`: dengan prefiks `0x` maupun tanpa prefiks.
    /// @dev Aturan: spasi/tab/CR/LF di ujung dipangkas, prefiks `0x`/`0X` opsional, sisanya WAJIB
    ///      tepat 64 karakter `[0-9a-fA-F]`. Nilai tanpa prefiks yang seluruhnya digit 0-9 ditolak
    ///      (`AmbiguousPrivateKeyFormat`): kunci desimal 64 digit akan diam-diam terbaca sebagai
    ///      heksadesimal lain dan menghasilkan vault dengan `agent` yang salah — dan `agent`
    ///      immutable. Tulis `0x…` bila memang heksadesimal.
    ///
    ///      KENAPA konversi hex ditulis sendiri, bukan `vm.parseUint`/`vm.parseBytes32`:
    ///      `vm.parseUint(string.concat("0x", kunci))` menyerahkan kunci sebagai argumen STRING
    ///      BIASA, dan argumen string biasa tidak pernah disensor Foundry: kunci tampil apa adanya
    ///      di trace `-vvvv` dan — pada nilai cacat — di pesan revert
    ///      `failed parsing "0x…" as type uint256` yang muncul pada verbositas DEFAULT, di stdout
    ///      MAUPUN stderr. Parser di bawah menutup dua kanal itu: kunci tidak pernah masuk
    ///      `console.log`, dan semua error di file ini tanpa parameter sehingga kunci tidak pernah
    ///      masuk pesan revert.
    ///
    ///      YANG BELUM TERTUTUP — `--json` DILARANG dipakai dengan skrip ini (ADR-016):
    ///      kunci TETAP menjadi argumen cheatcode di `run()`, yaitu `vm.addr(deployerKey)` dan
    ///      `vm.startBroadcast(deployerKey)`. Foundry menyensor trace TEKS
    ///      (`VM::addr(<pk>)`, `VM::startBroadcast(<pk>)`, `VM::envString(...) → <env var value>`)
    ///      TETAPI TIDAK menyensor keluaran `--json`, yang mendump calldata cheatcode mentah.
    ///      Pada jalur SUKSES, verbositas DEFAULT, kunci utuh karena itu tercetak 2x per run ke
    ///      stdout — 32 byte sesudah selector pada tiap `data:` adalah kuncinya:
    ///        "data":"0xffa18649<kunci 32 byte>"   // addr(uint256)
    ///        "data":"0xce817d47<kunci 32 byte>"   // startBroadcast(uint256)
    ///      (Direproduksi dengan kunci uji Anvil #0 yang publik; jangan ulangi dengan kunci asli.)
    ///      `vm.startBroadcast()` TANPA argumen terbukti menghasilkan nol kemunculan kunci di
    ///      `--json`, tetapi bentuk broadcast di sini sengaja TIDAK diubah dulu; perombakan ke
    ///      keystore/`--account` dijadwalkan terpisah. Sampai itu terjadi, larangan `--json` di
    ///      atas adalah satu-satunya mitigasi (ADR-016).
    function _envPrivateKey() internal view returns (uint256) {
        return _parsePrivateKey(bytes(vm.envString("AGENT_PRIVATE_KEY")));
    }

    /// @notice Parser murni dari `_envPrivateKey`, dipisah agar bisa diuji tanpa menyentuh
    ///         environment proses (lihat catatan paralelisme di `_validate`).
    function _parsePrivateKey(bytes memory raw) internal pure returns (uint256) {
        uint256 start = 0;
        uint256 end = raw.length;
        while (start < end && _isSpace(raw[start])) {
            start++;
        }
        while (end > start && _isSpace(raw[end - 1])) {
            end--;
        }
        if (end == start) revert MissingPrivateKey();

        bool hasPrefix = end - start >= 2 && raw[start] == bytes1("0")
            && (raw[start + 1] == bytes1("x") || raw[start + 1] == bytes1("X"));
        if (hasPrefix) start += 2;

        if (end - start != 64) revert InvalidPrivateKeyFormat();

        uint256 key = 0;
        bool anyLetter = false;
        for (uint256 i = start; i < end; i++) {
            (uint256 nibble, bool isLetter) = _nibble(raw[i]);
            key = (key << 4) | nibble;
            anyLetter = anyLetter || isLetter;
        }
        if (!hasPrefix && !anyLetter) revert AmbiguousPrivateKeyFormat();

        return key;
    }

    /// @dev Nilai nibble sebuah karakter hex + apakah karakter itu huruf `a-f`/`A-F`.
    ///      Revert TANPA parameter pada karakter non-hex (termasuk byte UTF-8 dari NBSP 0xC2 0xA0).
    function _nibble(bytes1 c) private pure returns (uint256 value, bool isLetter) {
        uint8 b = uint8(c);
        if (b >= 0x30 && b <= 0x39) return (b - 0x30, false); // '0'-'9'
        if (b >= 0x61 && b <= 0x66) return (b - 0x57, true); // 'a'-'f'
        if (b >= 0x41 && b <= 0x46) return (b - 0x37, true); // 'A'-'F'
        revert InvalidPrivateKeyFormat();
    }

    function _isSpace(bytes1 c) private pure returns (bool) {
        return c == 0x20 || c == 0x09 || c == 0x0a || c == 0x0d;
    }
}
