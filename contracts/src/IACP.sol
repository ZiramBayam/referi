// SPDX-License-Identifier: MIT
pragma solidity 0.8.36;

/// @title IACP — potongan ABI kontrak ACP (ERC-8183 milik Virtuals) yang BOLEH dipanggil vault.
/// @notice Signature diambil APA ADANYA dari `docs/api-facts.md` §A (ABI paket
///         acp-node-v2 0.1.12 + dikonfirmasi ke bytecode Base Sepolia
///         `0x0b93793923CD5De81850aF8604a233f3f24d461e`). JANGAN menambah fungsi yang tidak ada di
///         sana, dan JANGAN mengubah signature supaya tes lebih mudah.
/// @dev Sengaja HANYA dua fungsi: `EvaluatorVault` tidak pernah memanggil ACP di luar `finalize`,
///      dan di dalam `finalize` hanya `complete` ATAU `reject`. Khususnya `getJob` TIDAK dipakai —
///      keputusan product-manager 2026-09-03 untuk menghindari decode returndata (struct
///      `Job` memuat `string description`) di jalur kritis 1.3d.
interface IACP {
    /// @notice Evaluator meluluskan job (Submitted→Completed). `reason` = bytes32 (api-facts §B.1).
    function complete(uint256 jobId, bytes32 reason, bytes calldata optParams) external;

    /// @notice Evaluator menolak job (Funded/Submitted→Rejected), refund 100% ke client.
    function reject(uint256 jobId, bytes32 reason, bytes calldata optParams) external;
}
