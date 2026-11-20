# 微信豆投放助手（wecoin-ad-ops）

微信豆（视频号加热）投放的标准化流程 + 工具。适合投**老罗系带货视频**的场景。

## 这是什么

一套让 AI agent（Codex / WorkBuddy / Claude Code / DeepSeek Harness）能直接操作的投放系统：
- **方法**在 `SKILL.md` 和 `references/`
- **工具**在 `scripts/`
- **你的账户配置**在 `config/rules.json`（首次运行自动生成）

## 适合谁

- 你在投视频号带货视频（视频号加热）；
- 你每天要建几十条加热计划、支付、复盘；
- 你希望 AI 帮你执行，而不是手动点。

## 不适合谁

- 不做视频号加热的（这是微信豆专用）；
- 想全自动无人值守的（这套需要你在关键节点确认）。

## 快速开始

### 1. 装环境

- Node.js ≥ 22.19
- Chrome

### 2. 启动能调试的 Chrome

```bash
chrome --remote-debugging-port=9444 \
  --user-data-dir=<你的独立目录> \
  --no-first-run \
  "https://channels.weixin.qq.com/promote/pages/platform/order-list"
```

扫码登录，**不要关这个窗口**。

### 3. 跑 setup

```bash
node scripts/setup.js --port=9444
```

它会自动读出你的投放账户名、商品、名单，生成配置。

### 4. 验证

```bash
node scripts/ops/cli.js catalog sync --account=account1
```

## 核心标准（摘要）

| 项 | 标准 |
|---|---|
| 59.9 成交数 | 90-110（不超 130）|
| 59.9 成交ROI | 0.6-0.8（不超 1.0）|
| 399 净成交 | 600-700，**预算 = 出价 × 2** |
| 视频窗口 | 只投 2026-07-01 之后 |
| 数据口径 | 只用 indicator（100000/301004/301005）|
| 取消订单 | **不擅自取消**，先列清单给人确认 |

完整规则见 `references/03-出价与选视频标准.md`。

## 目录

```
wecoin-ad-ops/
├── SKILL.md                  # agent 入口（读这个）
├── README.md                 # 本文件
├── references/               # 详细文档
├── scripts/
│   ├── setup.js              # 首次安装
│   ├── lib/                  # CDP、API、预检
│   ├── ops/                  # 建单、支付、同步
│   └── analysis/             # 策略生成
├── config/
│   └── rules.example.json    # 配置模板
└── docs/
    └── 案例-202611.md        # 真实案例（脱敏）
```

## 需要你确认的事

这套系统会**真实花钱**（微信豆/现金）。agent 执行时请确认：
- 建单前看 preflight 结果；
- 支付前确认金额；
- 取消订单前确认清单。

## 许可

内部使用。转发前请确认不含账户敏感信息。
