// SPDX-License-Identifier: MIT
pragma solidity 0.8.36;

import {Test} from "forge-std/Test.sol";
import {Deploy} from "../script/Deploy.s.sol";
import {EvaluatorVault} from "../src/EvaluatorVault.sol";

/// @dev Membuka helper `internal` skrip deploy untuk diuji. Kunci yang dipakai di berkas ini adalah
///      kunci uji Anvil yang dipublikasikan luas — BUKAN rahasia proyek.
contract DeployHarness is Deploy {
    function exposedParse(string calldata raw) external pure returns (uint256) {
        return _parsePrivateKey(bytes(raw));
    }

    function exposedParseBytes(bytes calldata raw) external pure returns (uint256) {
        return _parsePrivateKey(raw);
    }

    function exposedEnvKey() external view returns (uint256) {
        return _envPrivateKey();
    }

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
///      1. `AGENT_PRIVATE_KEY` — menerima bentuk DENGAN dan TANPA prefiks `0x` (banyak berkas `.env`
///         menyimpannya tanpa `0x`), tetapi menolak KERAS segala bentuk lain. Penolakan WAJIB lewat
///         custom error TANPA parameter: nilai kunci tidak boleh pernah masuk ke pesan revert atau
///         ke argumen cheatcode, karena keduanya dirender ke stdout/stderr.
///      2. Guard konsistensi sebelum konstruktor — semua argumen konstruktor immutable, jadi skrip
///         adalah satu-satunya tempat salah jaringan/ACP/agen/arbiter bisa dicegat.
///
///      CATATAN PARALELISME: `forge test` 1.7.1 menjalankan fungsi-fungsi tes dalam satu kontrak
///      secara PARALEL, sedangkan `vm.setEnv` mengubah environment PROSES. Karena itu hanya SATU
///      fungsi di berkas ini yang menulis env (`test_deployFromEnv_happyPath`) dan nilainya sama di
///      setiap pemanggilan; sisanya memanggil parser/guard secara langsung. Versi yang menulis
///      nilai berbeda-beda dari banyak fungsi terbukti flaky (5 dari 24 tes gagal acak).
contract DeployTest is Test {
    /// Kunci uji Anvil #0 (publik, dokumentasi Foundry) → 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266.
    string internal constant KEY_NO_PREFIX = "ac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80";
    uint256 internal constant KEY_VALUE = 0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80;
    address internal constant KEY_ADDR = 0xf39Fd6e51aad88F6F4ce6aB8827279cffFb92266;

    /// Nilai uji lain (bukan alamat nyata; ACP nyata ada di docs/versions.md, dibaca dari env).
    address internal constant ACP_TEST = address(0xACADE);
    address internal constant ARBITER_TEST = address(0xA4B17E);
    uint256 internal constant CHAIN_TEST = 84532;

    DeployHarness internal harness;

    function setUp() public {
        harness = new DeployHarness();
    }

    // ------------------------------------------------------------------
    // AGENT_PRIVATE_KEY — bentuk yang diterima
    // ------------------------------------------------------------------

    function test_parseKey_acceptsHexPrefix() public view {
        assertEq(harness.exposedParse(string.concat("0x", KEY_NO_PREFIX)), KEY_VALUE);
    }

    function test_parseKey_acceptsMissingHexPrefix() public view {
        assertEq(harness.exposedParse(KEY_NO_PREFIX), KEY_VALUE);
    }

    function test_parseKey_acceptsUppercasePrefix() public view {
        assertEq(harness.exposedParse(string.concat("0X", KEY_NO_PREFIX)), KEY_VALUE);
    }

    function test_parseKey_acceptsUppercaseDigits() public view {
        assertEq(harness.exposedParse("AC0974BEC39A17E36BA4A6B4D238FF944BACB478CBED5EFCAE784D7BF4F2FF80"), KEY_VALUE);
    }

    function test_parseKey_trimsSurroundingWhitespace() public view {
        assertEq(harness.exposedParse(string.concat(" \t", KEY_NO_PREFIX, " \r\n")), KEY_VALUE);
    }

    function test_parseKey_derivesExpectedAddress() public view {
        assertEq(vm.addr(harness.exposedParse(KEY_NO_PREFIX)), KEY_ADDR);
    }

    /// @dev Nilai heksadesimal yang kebetulan hanya berisi digit 0-9 tetap sah — asal ditulis
    ///      eksplisit dengan `0x`, ambiguitas hex/desimal hilang.
    function test_parseKey_acceptsAllDigitsWithPrefix() public view {
        assertEq(
            harness.exposedParse("0x1111111111111111111111111111111111111111111111111111111111111111"),
            uint256(0x1111111111111111111111111111111111111111111111111111111111111111)
        );
    }

    // ------------------------------------------------------------------
    // AGENT_PRIVATE_KEY — bentuk yang ditolak (error TANPA parameter)
    // ------------------------------------------------------------------

    function test_parseKey_emptyReverts() public {
        _assertBareSelector("", Deploy.MissingPrivateKey.selector);
    }

    function test_parseKey_whitespaceOnlyReverts() public {
        _assertBareSelector("   ", Deploy.MissingPrivateKey.selector);
    }

    /// 64 karakter, tetapi ada yang di luar `[0-9a-fA-F]`.
    function test_parseKey_nonHexReverts() public {
        _assertBareSelector(
            "zz0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff80", Deploy.InvalidPrivateKeyFormat.selector
        );
    }

    /// 63 karakter (satu digit hilang saat menempel).
    function test_parseKey_tooShortReverts() public {
        _assertBareSelector(
            "ac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff8", Deploy.InvalidPrivateKeyFormat.selector
        );
    }

    /// 65 karakter (satu digit ganda).
    function test_parseKey_tooLongReverts() public {
        _assertBareSelector(
            "ac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff800", Deploy.InvalidPrivateKeyFormat.selector
        );
    }

    /// Prefiks `0x` + 66 digit: prefiks dipangkas dulu, sisanya tetap wajib 64.
    function test_parseKey_prefixedTooLongReverts() public {
        _assertBareSelector(
            "0xac0974bec39a17e36ba4a6b4d238ff944bacb478cbed5efcae784d7bf4f2ff8000",
            Deploy.InvalidPrivateKeyFormat.selector
        );
    }

    /// Prefiks `0x` saja.
    function test_parseKey_prefixOnlyReverts() public {
        _assertBareSelector("0x", Deploy.InvalidPrivateKeyFormat.selector);
    }

    /// Spasi DI TENGAH tidak dipangkas (hanya ujung yang dipangkas) → karakter non-hex.
    function test_parseKey_innerSpaceReverts() public {
        _assertBareSelector(
            "ac0974bec39a17e36ba4a6b4 238ff944bacb478cbed5efcae784d7bf4f2ff80", Deploy.InvalidPrivateKeyFormat.selector
        );
    }

    /// Kunci 64 digit DESIMAL tanpa prefiks: sah sebagai hex maupun desimal → tolak keras.
    /// Sebelum perbaikan ini nilai seperti itu ter-deploy DIAM-DIAM dengan `agent` yang salah,
    /// dan `agent` immutable (vault itu tidak akan pernah bisa `postVerdict`).
    function test_parseKey_allDecimalDigitsWithoutPrefixReverts() public {
        _assertBareSelector(
            "1234567890123456789012345678901234567890123456789012345678901234",
            Deploy.AmbiguousPrivateKeyFormat.selector
        );
    }

    /// NBSP (U+00A0 = 0xC2 0xA0 dalam UTF-8) hasil salin-tempel dari halaman web; bukan whitespace
    /// ASCII sehingga TIDAK dipangkas, dan bukan karakter hex.
    function test_parseKey_leadingNbspReverts() public {
        bytes memory withNbsp = abi.encodePacked(hex"c2a0", bytes(KEY_NO_PREFIX));
        (bool ok, bytes memory data) =
            address(harness).call(abi.encodeCall(DeployHarness.exposedParseBytes, (withNbsp)));
        assertFalse(ok, "seharusnya revert");
        assertEq(data.length, 4, "error revert membawa parameter (kanal bocor)");
        assertEq(bytes4(data), Deploy.InvalidPrivateKeyFormat.selector);
    }

    /// @dev Sekaligus BUKTI di dalam EVM bahwa kunci tidak ikut di pesan revert: returndata error
    ///      persis 4 byte (selector saja), tidak ada ruang untuk nilai apa pun. Bukti pada level
    ///      proses (stdout/stderr `forge script`) ada di catatan task 1.3: `grep -c` = 0 kemunculan.
    function _assertBareSelector(string memory raw, bytes4 expected) internal {
        (bool ok, bytes memory data) = address(harness).call(abi.encodeCall(DeployHarness.exposedParse, (raw)));
        assertFalse(ok, "seharusnya revert");
        assertEq(data.length, 4, "error revert membawa parameter (kanal bocor)");
        assertEq(bytes4(data), expected, "selector error tidak sesuai");
    }

    // ------------------------------------------------------------------
    // Guard konsistensi sebelum konstruktor immutable
    // ------------------------------------------------------------------

    function test_validate_happyPath() public {
        vm.chainId(CHAIN_TEST);
        vm.etch(ACP_TEST, hex"60006000fd"); // kode apa pun; guard hanya melihat `code.length`
        harness.exposedValidate(ACP_TEST, KEY_ADDR, ARBITER_TEST, KEY_ADDR, CHAIN_TEST, false);
    }

    function test_validate_wrongChainReverts() public {
        vm.chainId(31337);
        vm.etch(ACP_TEST, hex"60006000fd");
        vm.expectRevert(Deploy.WrongChain.selector);
        harness.exposedValidate(ACP_TEST, KEY_ADDR, ARBITER_TEST, KEY_ADDR, CHAIN_TEST, false);
    }

    function test_validate_acpWithoutCodeReverts() public {
        vm.chainId(CHAIN_TEST);
        assertEq(ACP_TEST.code.length, 0, "prasyarat: ACP_TEST masih EOA");
        vm.expectRevert(Deploy.AcpNotContract.selector);
        harness.exposedValidate(ACP_TEST, KEY_ADDR, ARBITER_TEST, KEY_ADDR, CHAIN_TEST, false);
    }

    function test_validate_agentMismatchReverts() public {
        vm.chainId(CHAIN_TEST);
        vm.etch(ACP_TEST, hex"60006000fd");
        vm.expectRevert(Deploy.AgentMismatch.selector);
        harness.exposedValidate(ACP_TEST, address(0xBEEF), ARBITER_TEST, KEY_ADDR, CHAIN_TEST, false);
    }

    function test_validate_arbiterEqualsAgentReverts() public {
        vm.chainId(CHAIN_TEST);
        vm.etch(ACP_TEST, hex"60006000fd");
        vm.expectRevert(Deploy.ArbiterEqualsAgent.selector);
        harness.exposedValidate(ACP_TEST, KEY_ADDR, KEY_ADDR, KEY_ADDR, CHAIN_TEST, false);
    }

    /// Escape hatch eksplisit — supaya deploy 84532 yang sudah ada tetap bisa direproduksi.
    function test_validate_arbiterEqualsAgentAllowedByEscapeHatch() public {
        vm.chainId(CHAIN_TEST);
        vm.etch(ACP_TEST, hex"60006000fd");
        harness.exposedValidate(ACP_TEST, KEY_ADDR, KEY_ADDR, KEY_ADDR, CHAIN_TEST, true);
    }

    /// Escape hatch TIDAK melonggarkan guard lain.
    function test_validate_escapeHatchDoesNotBypassOtherGuards() public {
        vm.chainId(31337);
        vm.etch(ACP_TEST, hex"60006000fd");
        vm.expectRevert(Deploy.WrongChain.selector);
        harness.exposedValidate(ACP_TEST, KEY_ADDR, KEY_ADDR, KEY_ADDR, CHAIN_TEST, true);

        vm.chainId(CHAIN_TEST);
        vm.expectRevert(Deploy.AgentMismatch.selector);
        harness.exposedValidate(ACP_TEST, address(0xBEEF), address(0xBEEF), KEY_ADDR, CHAIN_TEST, true);
    }

    // ------------------------------------------------------------------
    // Jalur env end-to-end — SATU-SATUNYA tes yang menulis environment proses
    // ------------------------------------------------------------------

    /// @dev Menutup jalur yang tidak tercakup tes parser/guard: `run()` benar-benar membaca env,
    ///      menurunkan alamat dari kunci, dan meneruskan nilainya ke konstruktor immutable.
    function test_deployFromEnv_happyPath() public {
        vm.chainId(CHAIN_TEST);
        vm.etch(ACP_TEST, hex"60006000fd");
        vm.setEnv("AGENT_PRIVATE_KEY", KEY_NO_PREFIX);
        vm.setEnv("ACP_ADDRESS", vm.toString(ACP_TEST));
        vm.setEnv("ARBITER_ADDRESS", vm.toString(ARBITER_TEST));
        vm.setEnv("AGENT_ADDRESS", vm.toString(KEY_ADDR));
        vm.setEnv("CHAIN_ID", vm.toString(CHAIN_TEST));
        vm.setEnv("MIN_BOND_WEI", "0");
        vm.setEnv("ALLOW_ARBITER_EQ_AGENT", "false");

        assertEq(harness.exposedEnvKey(), KEY_VALUE);

        EvaluatorVault vault = harness.run();
        assertEq(address(vault.acp()), ACP_TEST);
        assertEq(vault.agent(), KEY_ADDR);
        assertEq(vault.arbiter(), ARBITER_TEST);
        assertEq(vault.MIN_BOND(), 0);
    }
}
