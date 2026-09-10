// SPDX-License-Identifier: MIT
pragma solidity 0.8.36;

/// @notice Deterministic oracle fixture for the Execution Passport demo.
/// @dev This is not an oracle implementation and must never be used with real funds.
contract MockOracle {
    error NotOwner();
    error ZeroOwner();

    address public immutable owner;
    uint256 public timestamp;
    uint256 public price;

    event ObservationSet(uint256 timestamp, uint256 price);

    constructor(address owner_) {
        if (owner_ == address(0)) revert ZeroOwner();
        owner = owner_;
    }

    function setObservation(uint256 timestamp_, uint256 price_) external {
        if (msg.sender != owner) revert NotOwner();
        timestamp = timestamp_;
        price = price_;
        emit ObservationSet(timestamp_, price_);
    }
}
