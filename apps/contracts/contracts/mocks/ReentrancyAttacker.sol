// SPDX-License-Identifier: MIT
pragma solidity ^0.8.24;

import "@openzeppelin/contracts/token/ERC20/IERC20.sol";

interface IDarkPoolEscrow {
    function executeSwap(
        bytes32 swapId,
        bytes32 makerOrderId,
        bytes32 takerOrderId,
        uint256 makerFillAmount,
        uint256 takerFillAmount,
        bytes calldata teeSignature
    ) external;
    function cancelOrder(bytes32 orderId) external;
}

/**
 * @dev Malicious ERC-20 that re-enters DarkPoolEscrow on safeTransfer.
 *      Used to verify ReentrancyGuard blocks the attack.
 */
contract ReentrancyAttacker is IERC20 {
    IDarkPoolEscrow public target;

    // Attack config
    bytes32 public attackSwapId;
    bytes32 public attackMakerOrderId;
    bytes32 public attackTakerOrderId;
    uint256 public attackMakerFill;
    uint256 public attackTakerFill;
    bytes   public attackSig;
    bytes32 public attackCancelOrderId;
    bool    public attackOnExecute; // true → re-enter executeSwap, false → cancelOrder
    bool    public attacked;

    // Minimal ERC-20 state
    mapping(address => uint256) private _balances;
    mapping(address => mapping(address => uint256)) private _allowances;
    uint256 private _totalSupply;

    string  public constant name     = "Attacker Token";
    string  public constant symbol   = "ATK";
    uint8   public constant decimals = 18;

    constructor(address _target) {
        target = IDarkPoolEscrow(_target);
    }

    function configureExecuteAttack(
        bytes32 swapId_,
        bytes32 makerOrderId_,
        bytes32 takerOrderId_,
        uint256 makerFill_,
        uint256 takerFill_,
        bytes calldata sig_
    ) external {
        attackSwapId       = swapId_;
        attackMakerOrderId = makerOrderId_;
        attackTakerOrderId = takerOrderId_;
        attackMakerFill    = makerFill_;
        attackTakerFill    = takerFill_;
        attackSig          = sig_;
        attackOnExecute    = true;
        attacked           = false;
    }

    function configureCancelAttack(bytes32 cancelOrderId_) external {
        attackCancelOrderId = cancelOrderId_;
        attackOnExecute     = false;
        attacked            = false;
    }

    function mint(address to, uint256 amount) external {
        _balances[to] += amount;
        _totalSupply  += amount;
        emit Transfer(address(0), to, amount);
    }

    // ── ERC-20 interface ─────────────────────────────────────────────────────

    function totalSupply() external view override returns (uint256) { return _totalSupply; }
    function balanceOf(address a) external view override returns (uint256) { return _balances[a]; }

    function transfer(address to, uint256 amount) external override returns (bool) {
        _balances[msg.sender] -= amount;
        _balances[to]         += amount;
        emit Transfer(msg.sender, to, amount);

        // ── Reentrancy hook ─────────────────────────────────────────────────
        if (!attacked) {
            attacked = true;
            if (attackOnExecute) {
                target.executeSwap(
                    attackSwapId,
                    attackMakerOrderId,
                    attackTakerOrderId,
                    attackMakerFill,
                    attackTakerFill,
                    attackSig
                );
            } else {
                target.cancelOrder(attackCancelOrderId);
            }
        }
        return true;
    }

    function transferFrom(address from, address to, uint256 amount) external override returns (bool) {
        _allowances[from][msg.sender] -= amount;
        _balances[from]               -= amount;
        _balances[to]                 += amount;
        emit Transfer(from, to, amount);
        return true;
    }

    function approve(address spender, uint256 amount) external override returns (bool) {
        _allowances[msg.sender][spender] = amount;
        emit Approval(msg.sender, spender, amount);
        return true;
    }

    function allowance(address owner_, address spender) external view override returns (uint256) {
        return _allowances[owner_][spender];
    }
}
