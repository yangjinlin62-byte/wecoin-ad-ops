---
name: wecoin-ad-ops
description: 微信豆（视频号加热）投放自动化。适用于投老罗系带货视频的场景：拉新增视频、建计划、支付、复盘。通过首次 setup 自动识别操作账号与投放账户，适配不同人的账户。
---

# 微信豆投放助手

把「微信豆视频号加热」投放做成可执行的标准化流程。你（agent）负责按本文件执行命令、检查数据、汇报结果；**不要凭记忆猜账户名、商品ID、名单ID**，全部从平台实时拉取。

## 何时使用

用户要做以下任一操作时：
- 给视频号带货视频投微信豆加热
- 拉新增视频、挑视频测试
- 建加热计划（59.9 或 399）
- 支付加热订单
- 复盘消耗/成交/ROI

## 硬规则（违反会造成损失）

1. **数据口径**：消耗/成交/成交额只能用 `getPromotionOrderIndicator`：
   - 100000 = 消耗（分）
   - 301004 = 成交单数
   - 301005 = 成交金额（分）
   - `order-list` 的 `actualCostQuota` 滞后显示 0，**不能用**
2. **出价**：
   - 成交数（target 8）：90-110，**不要超过 130**（130 会花 ¥347 得 0 单、无赔付）
   - 成交ROI（target 11）：0.6-0.8，**不要 1.0+**（1.0+ 不出单）
   - 净ROI（target 40）：0.7-0.8
   - 净成交数（target 42）：600-700
3. **399 预算 = 出价 × 2**：
   - 600 → 预算 1200
   - 650 → 预算 1300
   - 700 → 预算 1400
   - 预算不足会报 `11770120`
4. **视频窗口**：只投 `2026-07-01` 之后的视频（配置项 `videoWindow.minCreateTime`）
5. **不擅自取消订单**：0 消耗 >24h 的也要先列清单给用户确认
6. **不刷接口**：连续报 429 就停手，等 10 分钟再低频重试

## 首次安装（agent 执行，只做一次）

### 1. 检查环境
```bash
node --version   # 需要 >= 22.19
```

### 2. 启动 Chrome（CDP）
```bash
chrome --remote-debugging-port=9444 --user-data-dir=<本机目录> --no-first-run https://channels.weixin.qq.com/promote/pages/platform/order-list
```
让用户扫码登录，登录后**不要关闭这个窗口**。

### 3. 跑 setup
```bash
node scripts/setup.js --port=9444
```
它会：
- 探测 CDP，确认已登录
- 调 `getUserPrepare` 拿到**投放账户真实名称**（如「元智成文化」）
- 扫描商品目录，列出可用商品让用户选
- 读取排除名单（`excludeUinPackageIds`）
- 生成 `config/rules.json`

### 4. 让用户确认三项
- 现金底线（`cashFloor`）
- 每户每日计划上限
- 主投商品

### 5. 验证
```bash
node scripts/catalog.js sync --account=account1
```
能拉到视频目录就说明装好了。

## 每日流程（agent 执行）

> 所有命令都通过 `scripts/ops/cli.js` 执行。

```bash
# ① 复盘：看昨日消耗/成交/ROI
node scripts/ops/cli.js report

# ② 拉新增：同步视频目录
node scripts/ops/cli.js catalog sync --account=<accountId>

# ③ 建单：先预检，再正式建
node scripts/ops/cli.js preflight --file=<planFile> --account=<accountId>
node scripts/ops/cli.js create --file=<planFile> --account=<accountId> --confirm=YES

# ④ 支付
node scripts/ops/cli.js pay --file=<payFile> --account=<accountId>

# ⑤ 复核：查实际消耗/成交（用 indicator）
node scripts/ops/cli.js report
```

## 建计划的标准结构

每户每天建议（可按用户调整）：

| 组 | 目标 | 出价 | 预算 | 条数 |
|---|---|---|---|---|
| 59.9 成交数 | 8 | 95 | 1000 | 10 |
| 59.9 成交ROI | 11 | 0.70 | 1000 | 8 |
| 399 净成交 | 42 | 650 | 1300 | 6 |
| 399 净ROI | 40 | 0.70 | 1000 | 6 |

- 扣费：实时:预付 = 1:1
- 定向：年龄按用户要求（默认不限），排除名单用配置里的
- 399 用老罗数字新机遇的视频（若商品不同，以 setup 扫描结果为准）

## 排障

| 现象 | 原因 | 处理 |
|---|---|---|
| `429 / 操作过于频繁` | 刷太快 | 停手，等 10 分钟 |
| `11770120` | 399 预算不足出价 2 倍 | 加大预算 |
| `11770175` | 账户加热订单过多 | 减少建单量/等存量结束 |
| 建单轮询超时 | 批量太大 | 缩短批量（≤50） |
| 支付 0 单到账 | 免密失效 | 让用户扫码 |
| 支付报 `-9 系统错误` | 批量太快 | 分批（≤5 条/次，间隔） |
| `headers not captured` | 页面没发接口 | reload 页面 |

详细见 `references/04-排障手册.md`。

## 重要约束

- **先读 `references/`**：`02-每日流程.md` 有完整命令，`03-出价与选视频标准.md` 有全部规则；
- **不要改代码**去绕 preflight（现金/日期/商品/视频/出价/预算都是硬约束）；
- **不要用测试数据替代真实数据**；每天以实际消耗/订单/ROI 为准；
- **不确定就问用户**，特别是取消订单、改出价、加预算。

## 文件说明

| 文件 | 内容 |
|---|---|
| `references/01-快速开始.md` | 环境、Chrome、登录 |
| `references/02-每日流程.md` | 完整命令 + 参数 |
| `references/03-出价与选视频标准.md` | 全部硬规则 + 历史数据 |
| `references/04-排障手册.md` | 错误码 + 处理 |
| `references/05-配置说明.md` | `rules.json` 每个字段 |
| `docs/案例-202611.md` | 真实投放案例（脱敏） |
