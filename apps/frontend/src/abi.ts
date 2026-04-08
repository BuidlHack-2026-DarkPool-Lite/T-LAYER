/** 최소 컨트랙트 ABI — ethers v6 human-readable 포맷 */

export const ERC20_ABI = [
  'function approve(address spender, uint256 amount) returns (bool)',
  'function allowance(address owner, address spender) view returns (uint256)',
  'function balanceOf(address account) view returns (uint256)',
  'function decimals() view returns (uint8)',
  'function symbol() view returns (string)',
];

export const ESCROW_ABI = [
  'function deposit(bytes32 orderId, address token, uint256 amount)',
  'function cancelOrder(bytes32 orderId)',
  'function orders(bytes32) view returns (address trader, address token, uint256 totalAmount, uint256 filledAmount, bool active)',
  'function getOrderRemaining(bytes32 orderId) view returns (uint256)',
  'event Deposited(bytes32 indexed orderId, address indexed trader, address token, uint256 amount)',
  'event SwapExecuted(bytes32 indexed swapId, bytes32 indexed makerOrderId, bytes32 indexed takerOrderId, uint256 makerFillAmount, uint256 takerFillAmount)',
  'event Cancelled(bytes32 indexed orderId, address indexed trader, uint256 refundAmount)',
];
