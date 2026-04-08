```text
dark-pool-contracts/
├── .gitignore               ← git 제외 규칙
├── .env.example             ← 환경변수 템플릿 (실제 키 없음)
├── package.json             ← 의존성 정의
├── package-lock.json        ← 의존성 버전 고정
├── hardhat.config.js        ← 컴파일러/네트워크 설정
├── contracts/
│   ├── DarkPoolEscrow.sol    ← 메인 컨트랙트
│   └── mocks/
│       ├── MockERC20.sol      ← 테스트용 토큰
│       └── ReentrancyAttacker.sol ← 보안 테스트용
├── scripts/
│   └── deploy.js             ← 배포 스크립트
└── test/
    └── DarkPoolEscrow.test.js ← 32개 테스트
