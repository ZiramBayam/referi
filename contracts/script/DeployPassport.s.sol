// SPDX-License-Identifier: MIT
pragma solidity 0.8.36;

import {Script} from "forge-std/Script.sol";
import {console} from "forge-std/console.sol";
import {MockOracle} from "../src/MockOracle.sol";
import {MockTreasury} from "../src/MockTreasury.sol";
import {PassportVerifier} from "../src/PassportVerifier.sol";

/// @title DeployPassport, men-deploy fixture Execution Passport ke jaringan persisten.
/// @notice Tiga kontrak sekaligus, karena PassportVerifier menyimpan alamat treasury sebagai
///         immutable: men-deploy verifier terhadap treasury yang salah menghasilkan verifier
///         yang tidak bisa dipakai, dan satu-satunya cara mencegahnya adalah men-deploy
///         keduanya dalam satu transaksi berurutan yang sama.
///
/// @dev Jalankan (ADR-016 tahap 2, keystore terenkripsi, BUKAN kunci di `.env`):
///        forge script script/DeployPassport.s.sol:DeployPassport \
///            --rpc-url $RPC_URL --broadcast \
///            --account agent --sender 0xfa5AF5BAeB4aC500267D7189fa1f0AA923eCA894
///      (`--sender` WAJIB alamat LITERAL: `scripts/guard.sh` memblokir argumen hasil substitusi
///      perintah. Keystore dibuat sekali dengan `cast wallet import agent --interactive`.)
///
///      KUNCI PRIVAT TIDAK PERNAH MASUK KE SKRIP INI, sama seperti `Deploy.s.sol`: tidak ada
///      `vm.envString` untuk kunci, tidak ada cheatcode `vm.addr`, dan `vm.startBroadcast()`
///      dipanggil TANPA argumen. Itu menutup kebocoran `--json` di akarnya (ADR-016).
///
///      Env yang dibaca:
///        POLICY_SIGNER    (opsional, default `msg.sender`) alamat yang tanda tangannya diterima
///                         verifier sebagai penerbit passport. Ia immutable di verifier, jadi salah
///                         alamat = verifier yang menolak setiap passport yang pernah kita terbitkan.
///        INITIAL_RESERVE  (opsional, default 1_000_000) cadangan awal treasury fixture.
///        MINIMUM_RESERVE  (opsional, default 250_000) lantai cadangan yang dijaga invariant.
///        CHAIN_ID         (opsional, default 84532) chain yang diharapkan; salah jaringan revert.
///
///      Alamat hasil deploy dibaca dari baris `console.log` di bawah, atau dari artefak
///      `contracts/broadcast/DeployPassport.s.sol/<chainid>/run-latest.json`.
contract DeployPassport is Script {
    uint256 internal constant DEFAULT_CHAIN_ID = 84532;
    uint256 internal constant DEFAULT_INITIAL_RESERVE = 1_000_000;
    uint256 internal constant DEFAULT_MINIMUM_RESERVE = 250_000;

    error WrongChain(uint256 expected, uint256 actual);
    error ReserveBelowMinimum(uint256 initialReserve, uint256 minimumReserve);
    error ZeroAddress();

    function run()
        external
        returns (MockTreasury treasury, MockOracle oracle, PassportVerifier verifier)
    {
        address deployer = msg.sender;
        address policySigner = vm.envOr("POLICY_SIGNER", deployer);
        uint256 initialReserve = vm.envOr("INITIAL_RESERVE", DEFAULT_INITIAL_RESERVE);
        uint256 minimumReserve = vm.envOr("MINIMUM_RESERVE", DEFAULT_MINIMUM_RESERVE);
        uint256 expectedChainId = vm.envOr("CHAIN_ID", DEFAULT_CHAIN_ID);

        _validate(policySigner, initialReserve, minimumReserve, expectedChainId);

        console.log("chainid       ", block.chainid);
        console.log("deployer      ", deployer);
        console.log("policySigner  ", policySigner);
        console.log("initialReserve", initialReserve);
        console.log("minimumReserve", minimumReserve);

        vm.startBroadcast();
        treasury = new MockTreasury(deployer, initialReserve, minimumReserve);
        oracle = new MockOracle(deployer);
        verifier = new PassportVerifier(treasury, policySigner);
        treasury.configureVerifier(address(verifier));
        vm.stopBroadcast();

        console.log("MockTreasury    ", address(treasury));
        console.log("MockOracle      ", address(oracle));
        console.log("PassportVerifier", address(verifier));
    }

    /// @notice Guard konsistensi. Ketiga nilai di bawah masuk ke immutable atau ke state awal, jadi
    ///         skrip ini satu-satunya tempat kekeliruannya masih bisa dicegat. Semua revert.
    /// @dev Terpisah dari pembacaan env supaya bisa diuji tanpa menyentuh environment proses:
    ///      `vm.setEnv` bersifat global untuk seluruh proses `forge test`.
    function _validate(
        address policySigner,
        uint256 initialReserve,
        uint256 minimumReserve,
        uint256 expectedChainId
    ) public view {
        if (block.chainid != expectedChainId) {
            revert WrongChain(expectedChainId, block.chainid);
        }
        if (policySigner == address(0)) revert ZeroAddress();
        // Treasury yang lahir di bawah lantainya sendiri membuat setiap rebalance gagal pada
        // invariant post-state, dan gerbangnya tidak akan pernah bisa dibuka sekali pun.
        if (initialReserve < minimumReserve) {
            revert ReserveBelowMinimum(initialReserve, minimumReserve);
        }
    }
}
