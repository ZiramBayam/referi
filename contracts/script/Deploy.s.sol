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
///      Env yang dibaca:
///        ACP_ADDRESS       (wajib) kontrak ACP di jaringan target
///        ARBITER_ADDRESS   (wajib) arbiter sengketa (perannya belum aktif, ADR-013)
///        AGENT_PRIVATE_KEY (wajib) wallet agen evaluator; juga dipakai sebagai deployer
///        AGENT_ADDRESS     (opsional) bila agen berbeda dari deployer
///        MIN_BOND_WEI      (opsional, default 0) bond minimum sebelum agen boleh `postVerdict`.
///                          Default 0 dipilih sadar: selama ADR-013 berlaku vault belum punya jalur
///                          ETH keluar, jadi bond yang disetor akan terkunci. Naikkan hanya setelah
///                          `resolve`/penarikan bond ada.
contract Deploy is Script {
    function run() external returns (EvaluatorVault vault) {
        address acp = vm.envAddress("ACP_ADDRESS");
        address arbiter = vm.envAddress("ARBITER_ADDRESS");
        uint256 deployerKey = vm.envUint("AGENT_PRIVATE_KEY");
        address agent = vm.envOr("AGENT_ADDRESS", vm.addr(deployerKey));
        uint256 minBond = vm.envOr("MIN_BOND_WEI", uint256(0));

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
}
