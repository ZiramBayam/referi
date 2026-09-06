// SPDX-License-Identifier: MIT
pragma solidity 0.8.36;

import {AgenticCommerce} from "./AgenticCommerce.sol";

/// @title ProxiableAgenticCommerce — mock ACP yang bisa dipasang DI BELAKANG `ERC1967Proxy`.
/// @notice ACP nyata adalah proxy ERC-1967 (`docs/api-facts.md` §A: proxy
///         `0x0b93793923CD5De81850aF8604a233f3f24d461e`, implementasi `0xc4E9…30fF`). Artinya setiap
///         panggilan dari vault menempuh `vault → proxy (CALL) → implementasi (DELEGATECALL) →
///         paymentToken (CALL)`, yaitu kedalaman >= 3. Sisa gas EIP-150 (aturan 63/64) MENUMPUK per
///         level — 1/64 di kedalaman 1, 127/4096 di kedalaman 2, ~4,6% di kedalaman 3 — sehingga
///         harness kedalaman-1 memberi angka sisa gas yang SALAH saat menguji jalur kehabisan gas.
///         Semua tes jalur-gagal `finalize` karena itu memakai mock ini lewat proxy.
/// @dev Kontrak ini SENGAJA tidak menyalin satu baris pun logika ACP: ia hanya `AgenticCommerce`
///      (salinan setia kontrak terverifikasi) ditambah satu inisialisator. Alasannya: konstruktor
///      TIDAK pernah dieksekusi di storage proxy, jadi field yang di mock diisi konstruktor /
///      inisialisator inline (`platformTreasury`, `evaluatorFeeBP`, `platformFeeBP`, `nextJobId`) akan
///      bernilai nol di belakang proxy. `paymentToken` dan `mockAdmin` `immutable` TIDAK bermasalah:
///      keduanya tertanam di KODE implementasi dan terbaca benar saat `delegatecall`.
///      Nilai yang dipakai untuk inisialisasi WAJIB dibaca dari instance implementasi itu sendiri
///      (lihat `EvaluatorVaultTest._deployProxiedAcp`), bukan ditulis ulang di sini — supaya mock dan
///      harness tidak bisa hanyut diam-diam.
contract ProxiableAgenticCommerce is AgenticCommerce {
    error AlreadyInitialized();

    constructor(address paymentToken_, address treasury_) AgenticCommerce(paymentToken_, treasury_) {}

    /// @notice Menyalin state hasil-konstruktor ke storage proxy. Hanya boleh sekali.
    /// @dev `nextJobId` di mock mulai dari 1, jadi nol = belum pernah diinisialisasi.
    function initProxyState(address treasury_, uint256 evaluatorFeeBP_, uint256 platformFeeBP_, uint256 nextJobId_)
        external
    {
        if (nextJobId != 0) revert AlreadyInitialized();
        platformTreasury = treasury_;
        evaluatorFeeBP = evaluatorFeeBP_;
        platformFeeBP = platformFeeBP_;
        nextJobId = nextJobId_;
    }
}

/// @title PausedACPImpl — implementasi pengganti yang meniru ACP dalam keadaan `pause()`.
/// @notice `AgenticCommerce` sengaja TIDAK `Pausable` (mock itu salinan setia kontrak asli untuk alur
///         job, dan tidak boleh diubah). Untuk menguji cabang "ACP dipause" kita memanfaatkan sifat
///         ACP nyata yang memang ERC-1967: alamat yang dilihat vault tetap proxy, hanya slot
///         implementasi yang ditukar ke kontrak ini (lihat `_pauseAcp`/`_unpauseAcp` di tes).
///         Semua entry point revert `EnforcedPause()` — selector OZ yang sama dengan yang dipakai
///         ACP nyata (`docs/api-facts.md` §A: "saat dipause `complete`/`claimRefund` pun revert
///         `EnforcedPause()`").
/// @dev Storage proxy TIDAK disentuh, jadi menukar balik implementasinya memulihkan seluruh state job.
contract PausedACPImpl {
    error EnforcedPause();

    fallback() external payable {
        revert EnforcedPause();
    }
}
