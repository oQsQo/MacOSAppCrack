# CleanMyMac 5 许可证验证与 Patch 方案分析

> 版本 5.5.6 (Build 50506.0.2607101255) · Site 版本 · MacPaw Way Ltd (S8EX82NJP6)  
> 架构：Universal Binary (arm64 + x86_64)  
> 分析方法：otool 反汇编、mitmdump 抓包、二进制 patch、黑盒测试

---

## 一、二次许可证验证流程（每次启动）

### 1.1 核心发现：启动时不联网验证

通过 `mitmdump` 抓取实际 App 启动的网络流量，观察到：

| 序号 | 目标 | 方法 | 用途 |
|------|------|------|------|
| 1 | `ft.macpaw.com/api/features/sdk-*` | GET | GrowthBook 功能开关 |
| 2 | `public-apis.moonlock.com/engine/v3/database` | GET | Moonlock 恶意软件库更新 |
| 3 | `api-lytics.macpaw.com/actions` + `/insert` | POST | 遥测/统计上报 |
| 4 | `public-apis.cleanmymac.com/v1.0/remote-config/` | GET | 远程配置 |

**关键事实：`oauth.macpaw.com` 和 `activation.macpaw.com` 在正常启动时完全没有被请求。**  
没有 `/validate/token`，没有 `/customer/product-plan`，没有 `/activation` —— 零许可证相关的网络请求。

### 1.2 完整启动验证流程链路

```
App 启动 (applicationDidFinishLaunching)
    │
    ├─ "Starting CleanMyMac launch activities"
    │
    ▼
┌──────────────────────────────────────────────────┐
│  Step 1: 加载本地缓存的许可证数据                  │
│                                                    │
│  MPAServerDataProviderImp.fetchCachedLicense:      │
│    → 读取 Group Container plist                    │
│    → 键名: 22ea3f1cac4e7127e54551884f2ab076        │
│    → 解析 JSON → {isActivated, license, ...}       │
│                                                    │
│  数据位置:                                          │
│  ~/Library/Group Containers/                        │
│    S8EX82NJP6.com.macpaw.CleanMyMac5/              │
│    Library/Preferences/                             │
│    S8EX82NJP6.com.macpaw.CleanMyMac5.plist         │
└──────────────────┬───────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────┐
│  Step 2: 构建 MPALibLicenseValidationResult       │
│                                                    │
│  对象内存布局:                                      │
│    +0x00: isa (NSObject)                           │
│    +0x08: license (MPALicenseImp)                  │
│    +0x10: libValidationStatus (整数, 9=签名通过)    │
│    +0x18: libLicenseInfo (NSDictionary, 服务端数据) │
│                                                    │
│  关键方法:                                          │
│    .status → 读 +0x10, 判断 == 9 → 返回 0/1        │
│    .needsAttentionType → 读 +0x18 + 时间比较 +     │
│                          网络状态 → 返回枚举值       │
└──────────────────┬───────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────┐
│  Step 3: 主二进制快速路径检查                       │
│                                                    │
│  主二进制 (CleanMyMac_5) 直接检查缓存字段:          │
│    ① isActivated == true?                          │
│        → false: 不显示主窗口（但不一定弹激活框）     │
│        → true: 继续                                │
│    ② license.ownership 是否有效?                    │
│    ③ needsAttentionType == 0?                      │
│        → 非 0: 弹出对应的警告/错误对话框             │
│        → 0: 正常显示主窗口                          │
└──────────────────┬───────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────┐
│  Step 4: FlowController 验证决策                    │
│                                                    │
│  -[MPAFlowController                               │
│     bestFlowForLicenseValidationResult:]            │
│                                                    │
│  分支逻辑:                                          │
│    switch (validationResult.status) {              │
│      case 1 (Active):                              │
│        → 检查 needsAttentionType                   │
│        → 0: 不弹任何 UI, 正常使用 ✓                 │
│        → 非0: 弹对应警告 (过期/取消/暂停...)         │
│      case 0 (Inactive):                            │
│        → 触发激活流程 (MPAFlowController)           │
│    }                                               │
│                                                    │
│  -[MPAFlowController                               │
│     proposedFlowStepForLicenseValidationResult:]    │
│    → 调用 [license status]                         │
│    → 调用 [result needsAttentionType]              │
│    → 决定具体的 UI 步骤                             │
└──────────────────┬───────────────────────────────┘
                   │
                   ▼
┌──────────────────────────────────────────────────┐
│  Step 5: 功能门控检查 (按需)                        │
│                                                    │
│  ModuleCore.framework:                             │
│    LockedFunctionalityPerformer                    │
│      → 功能被锁定时的处理 (弹购买提示)               │
│    UnlockedFunctionalityPerformer                  │
│      → 功能解锁时的处理 (正常执行)                   │
│    .performIfUnlocked (0xf5ad8)                    │
│      → 检查 NFR 服务判断功能是否可用                 │
│                                                    │
│  CleanMyMacNFRService.framework:                   │
│    isAllowed / canPerform / isLicensed              │
│      → 结合许可证状态和功能限制判断                   │
└──────────────────────────────────────────────────┘
```

### 1.3 两层数据存储的区别

| | 第一层：缓存 plist | 第二层：libLicenseInfo |
|---|---|---|
| **来源** | 本地 JSON 缓存 | 服务端 RSA 签名的 License Payload 解析 |
| **用途** | 主二进制快速判断（冷启动路径） | `MPALibLicenseValidationResult` 的详细字段 |
| **加密** | 明文 JSON（存于 plist 键值中） | 经 RSA 签名保护完整性 |
| **可篡改** | 可直接修改 | 无法伪造（需要服务端私钥） |
| **关键字段** | `isActivated`, `needsAttentionType`, `license.ownership`, `license.activeUntilTimestamp` | `validUntilDate`, `nextBillingDate`, `needs_attention_type`, `ownership` |
| **读取时机** | App 启动立即读取 | `MPALibLicenseValidator.validateLicense:` 执行后 |

### 1.4 网络刷新测试结论

通过实际断网 → 重连测试：

- plist 缓存**没有被覆写**
- 原因：账号无付费订阅，服务端 `fetchActivationLicense` 返回错误，`onLicenseCacheChanged:` 未触发
- 结论：无需额外阻断网络刷新

---

## 二、Patch 方案对比分析

分析了 6 种从验证链底层到上层的 Patch 方案：

### 2.1 方案总览

| 方案 | Patch 点 | 目标 | 难度 | 稳定性 | 覆盖面 |
|------|----------|------|------|--------|--------|
| **A** | RSA 签名验证 | MacPawAccount.framework | ★★☆ | ★★★ | 最彻底 |
| **B** | 验证结果状态 getter | MacPawAccount.framework | ★★☆ | ★★★ | 彻底 |
| **C** | FlowController 决策 | MacPawAccount.framework | ★★★ | ★★☆ | 仅 UI 流程 |
| **D** | 本地缓存数据 | plist 数据文件 | ★★★★ | ★☆☆ | 有限 |
| **E** | 功能锁定门控 | ModuleCore.framework | ★★★ | ★★☆ | 仅功能执行 |
| **F** | Dylib 注入 Hook | 运行时注入 | ★★☆ | ★★★ | 最灵活 |

### 2.2 方案 A：Patch RSA 签名验证（根源级）

**目标：** `MPALibLicenseValidator.validateLicense:completion:`

```
验证链: licensePayload → SecVerifyTransformCreate → SHA-256 → 比对签名
                                                        ↑
                                              Patch: 让验证永远返回 true
```

**Patch 点：**
- 方法地址：`0x23684`（`-[MPALibLicenseValidator initWithDeviceID:publicKeyFileURL:]`）
- 或 `SecVerifyTransformCreate` 调用后的结果判断

**优点：** 最彻底，从根源让所有 License Payload 都"验签通过"  
**缺点：** 需要伪造完整的 License Payload 数据（JSON 结构），否则验签通过但解析阶段仍可能缺字段

---

### 2.3 方案 B：Patch 验证结果状态 getter（最终选用）

**目标：** `MPALibLicenseValidationResult` 的两个 getter 方法

```
所有调用者
    → [validationResult status]           ← Patch: 永远返回 1 (Active)
    → [validationResult needsAttentionType] ← Patch: 永远返回 0 (无需关注)
```

**优点：** 不需要伪造 License Payload；两个简单方法替换，改动最小  
**缺点：** 需要配合 plist 缓存修改（主二进制有独立的快速路径检查）

---

### 2.4 方案 C：Patch FlowController 决策

**目标：** `MPAFlowController.bestFlowForLicenseValidationResult:`

```
原始逻辑:
    switch (status) {
        case Active: check needsAttention → 弹窗/正常
        case Inactive: → 激活流程
    }

Patch: 让该方法永远走 "Active + 无需关注" 分支
```

**优点：** 阻止所有激活相关 UI 弹窗  
**缺点：** 只覆盖 UI 流程层；其他调用 `status` 的地方（NFR 服务、Reactor 等）不受影响，功能层面可能仍被锁定

---

### 2.5 方案 D：仅修改本地缓存数据

**目标：** Group Container plist 文件

```
修改 22ea3f1cac4e7127e54551884f2ab076 键中的 JSON:
    isActivated: true
    needsAttentionType: 0
    license.ownership: 1
    license.activeUntilTimestamp: <未来时间戳>
```

**优点：** 无需修改二进制、无需重签名  
**缺点：**
- `MPALibLicenseValidator` 的原始验证逻辑仍会运行
- 缓存可能被后台网络刷新覆写
- 无法欺骗通过 `MPALibLicenseValidationResult` 的原始方法进行判断的调用者
- **实测结论：仅修改 plist 不 patch 二进制，App 启动后不显示主窗口**

---

### 2.6 方案 E：Patch 功能锁定门控

**目标：** `ModuleCore.framework` → `UnlockedFunctionalityPerformer.performIfUnlocked`

```
地址: 0xf5ad8
原始: 检查 NFR 服务 → 功能锁定? → 弹购买提示
Patch: 跳过检查，直接执行功能
```

**优点：** 直接解锁所有功能  
**缺点：** 只覆盖功能执行层；激活对话框、状态显示等仍由上层控制，需要配合其他 patch

---

### 2.7 方案 F：Dylib 注入 Hook（运行时）

**目标：** 注入自定义 dylib，用 Objective-C runtime 在运行时替换方法实现

```
注入方式: DYLD_INSERT_LIBRARIES 或修改 Mach-O Load Commands
Hook:
    method_exchangeImplementations(
        [MPALibLicenseValidationResult status],
        myStatus  // return 1
    )
```

**优点：** 最灵活，不修改原始二进制；可 Hook 任意方法；版本更新后只需调整偏移  
**缺点：**
- 需要禁用 SIP 或使用特殊加载方式
- Hardened Runtime 可能阻止 dylib 注入
- 需要维护独立的注入 dylib 文件

---

## 三、最终选用方案（方案 B + D 组合）

> ⚠️ **本节已被 §六 取代（2026-07-12 实测复核）。** 经完整重签实测发现：本节的 plist 修改（方案 D）**并非必需**、"需先登录账号"的前提**不成立**，且本节**遗漏**了 root 级清理与菜单栏监控这两条在 ad-hoc 重签后会断的链路。请以 **§六 最小必要集与完整方案**为准。以下内容保留作为分析过程记录。

### 3.1 方案概述

选择**方案 B**（二进制 Patch 验证结果 getter）+ **方案 D 的数据修改**部分，两者结合实现完整绕过。

### 3.2 前提条件

- 需要先用真实账号完成一次**登录**（不需要有付费订阅），让本地缓存中写入基础客户信息
- App 版本 5.5.6 (Site 版)
- 当前设备架构为 arm64

### 3.3 具体修改内容

一共 **3 处修改**，涉及 1 个二进制文件 + 1 个数据文件 + 重签名。

---

#### 修改 1：二进制 Patch — `status` 方法

**文件：** `MacPawAccount.framework/Versions/A/MacPawAccount`  
**位置：** arm64 slice（fat offset `0x2F4000`）+ VM 地址 `0x230c0`  
**文件偏移：** `0x2F4000 + 0x230c0 = 0x3170c0`

```
方法: -[MPALibLicenseValidationResult status]

原始 ARM64 指令 (5 条):
  0x230c0: cbz  x0, 0x230d0       ; if (self == nil) goto ret
  0x230c4: ldr  x8, [x0, #0x10]   ; x8 = self->libValidationStatus
  0x230c8: cmp  x8, #0x9          ; 比较 x8 与 9
  0x230cc: cset w0, eq            ; w0 = (x8 == 9) ? 1 : 0
  0x230d0: ret

原始含义: 读取 libValidationStatus 字段, 判断是否等于 9 (RSA 签名验证通过),
         返回 0 (Inactive) 或 1 (Active)

Patch 后 (2 条):
  0x230c0: mov  w0, #1            ; 0x52800020 — 直接返回 1 (Active)
  0x230c4: ret                    ; 0xd65f03c0

作用: 所有调用者 (FlowController、LicenseUpdateReactor、主二进制等)
     读取 status 时都会得到 Active
```

**字节对照：**

| 偏移 | 原始字节 | Patch 字节 |
|------|----------|------------|
| `0x3170c0` | `80 00 00 b4` | `20 00 80 52` |
| `0x3170c4` | `08 08 40 f9` | `c0 03 5f d6` |

---

#### 修改 2：二进制 Patch — `needsAttentionType` 方法

**同一文件，** VM 地址 `0x230d4`  
**文件偏移：** `0x2F4000 + 0x230d4 = 0x3170d4`

```
方法: -[MPALibLicenseValidationResult needsAttentionType]

原始 ARM64 指令 (开头部分):
  0x230d4: stp  d11, d10, [sp, #-0x50]!  ; 函数序言：保存寄存器
  0x230d8: stp  d9, d8, [sp, #0x10]
  0x230dc: stp  x22, x21, [sp, #0x20]
  ... (后续约 40 条指令)

原始含义: 复杂的计算逻辑 —
  ① 从 libLicenseInfo 字典读取 needs_attention_type
  ② 查表映射为内部枚举值 (cancelled=1, paused=2, dispute=3, ...)
  ③ 读取 validUntilDate, 与当前时间比较
  ④ 检查网络状态 (离线?)
  ⑤ 组合判断返回最终的 attentionType

Patch 后 (2 条):
  0x230d4: mov  x0, #0            ; 0xd2800000 — 直接返回 0 (无需关注)
  0x230d8: ret                    ; 0xd65f03c0

作用: 跳过所有过期检查、网络状态检查、时间比较, 阻止任何警告/错误弹窗出现
```

**字节对照：**

| 偏移 | 原始字节 | Patch 字节 |
|------|----------|------------|
| `0x3170d4` | `eb 2b bb 6d` | `00 00 80 d2` |
| `0x3170d8` | `e9 23 01 6d` | `c0 03 5f d6` |

---

#### 修改 3：缓存数据 — Group Container plist

**文件：** `~/Library/Group Containers/S8EX82NJP6.com.macpaw.CleanMyMac5/Library/Preferences/S8EX82NJP6.com.macpaw.CleanMyMac5.plist`

**键名：** `22ea3f1cac4e7127e54551884f2ab076`（MD5 哈希值）

```json
{
  "isActivated": true,
  "needsAttentionType": 0,
  "license": {
    "ownership": 1,
    "seatStatus": 1,
    "activeUntilTimestamp": 2099152018
  }
}
```

| 字段 | 原始值 | 修改后 | 说明 |
|------|--------|--------|------|
| `isActivated` | `false` | `true` | 主二进制冷启动快速路径的关键判断 |
| `needsAttentionType` | `0` | `0` | 保持为 0（无需关注） |
| `license.ownership` | `0` | `1` (Owner) | 标识为计划所有者 |
| `license.seatStatus` | `0` | `1` (HasFreeSeats) | 标识为有座位 |
| `license.activeUntilTimestamp` | `0` | `2099152018` | 有效期至 2036 年 |

> **为什么需要修改 plist？**  
> 主二进制 (`CleanMyMac_5`) 在启动时有一个**独立的快速路径**，直接读取 plist 中的 `isActivated` 字段来决定是否显示主窗口。这个路径不经过 `MPALibLicenseValidationResult.status`，所以单靠二进制 patch 不够。

> **为什么 plist 中没有 `validUntilDate`？**  
> `validUntilDate` 存在于第二层数据（`libLicenseInfo` 字典，由 RSA 签名的 License Payload 解析而来）。我们 patch 的 `needsAttentionType` 方法在第一条指令就返回了 0，永远不会走到读取 `validUntilDate` 的逻辑，所以无需在 plist 中构造此字段。

---

#### 辅助操作：重签名

修改二进制后需要重签名整个 App Bundle：

```bash
codesign --force --deep -s - /Applications/CleanMyMac_5.app
```

**副作用：** Ad-hoc 重签会移除原始 Team ID (`S8EX82NJP6`)，导致已安装的特权帮助程序 (PrivilegedHelper) 不信任新签名。首次启动会弹出系统密码框要求重新安装帮助程序，仅一次。

---

### 3.4 各修改的作用与配合关系

```
┌──────────────────────────────────────────────────────────┐
│  修改 3: plist 缓存数据                                    │
│  isActivated=true → 主二进制显示主窗口                      │
│  ownership=1, seatStatus=1 → 通过快速路径检查               │
│                                                            │
│  作用层: 冷启动快速路径 (主二进制直接读 plist)                │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼  (主窗口显示后, 后台验证启动)
┌──────────────────────────────────────────────────────────┐
│  修改 1: status → 永远返回 Active                          │
│                                                            │
│  作用层:                                                    │
│    FlowController.bestFlowForLicenseValidationResult       │
│    FlowController.proposedFlowStepForLicenseValidationResult│
│    MPALicenseUpdateReactor                                  │
│    CleanMyMacNFRService                                    │
│    → 所有依赖 status 的组件都认为许可证有效                   │
└──────────────────────────┬───────────────────────────────┘
                           │
                           ▼
┌──────────────────────────────────────────────────────────┐
│  修改 2: needsAttentionType → 永远返回 0                   │
│                                                            │
│  作用层:                                                    │
│    阻止 FlowController 弹出以下警告:                        │
│      cancelled (取消), paused (暂停), dispute (争议),       │
│      pastDue (逾期), expired (过期), offline (离线)         │
│    → 即使 status=Active, 如果 needsAttentionType≠0         │
│      仍会弹警告对话框, 所以此 patch 不可省略                 │
└──────────────────────────────────────────────────────────┘
```

### 3.5 稳定性验证

| 测试场景 | 结果 |
|----------|------|
| 冷启动 | 主窗口正常显示 ✓ |
| 功能使用 | 清理、卸载等功能正常 ✓ |
| 断网 → 重连 | plist 未被覆写，功能正常 ✓ |
| 菜单栏进程 | 正常运行 ✓ |
| 辅助工具弹窗 | 首次出现一次（重签名副作用），后续不再出现 ✓ |

### 3.6 仅修改 plist 不 patch 二进制（方案 D 独立测试）

将二进制恢复为原始状态，仅保留 plist 修改，重签名后启动：

- **结果：** App 启动，菜单栏正常显示，但**主窗口不出现**
- **原因：** 原始 `MPALibLicenseValidationResult.status` 因为没有真实的 RSA 签名 payload（`libValidationStatus ≠ 9`），返回 0（Inactive），FlowController 判定需要走激活流程
- **结论：** 方案 D 单独使用不可行，必须配合二进制 patch

---

## 四、方案选择决策树

```
你的目标是什么?
    │
    ├─ 想要最简单的操作?
    │   → 方案 B + D（选用方案）: 改 4 个字节 + 1 个 plist + 重签名
    │
    ├─ 想要最彻底的破解?
    │   → 方案 A: Patch RSA 验签 + 伪造 License Payload
    │     （需要逆向完整的 payload JSON 结构, 工作量大）
    │
    ├─ 想要不修改二进制?
    │   → 方案 D 单独不可行（已验证）
    │   → 方案 F (Dylib 注入): 不改原始二进制, 但需禁用 SIP
    │
    ├─ 想要只解锁特定功能?
    │   → 方案 E: Patch ModuleCore.framework 的门控
    │
    └─ 想要最灵活可维护?
        → 方案 F (Dylib 注入): 版本更新后只需调整偏移量
```

---

## 五、附录

### 5.1 `needsAttentionType` 枚举映射

从反汇编 `needsAttentionType` 方法中的查表逻辑推断：

| 服务端值 (字符串) | 内部枚举值 | 含义 |
|-------------------|------------|------|
| `""` / null | 0 | 无需关注（正常） |
| `"cancelled"` | 1 | 订阅已取消 |
| `"paused"` | 2 | 订阅已暂停 |
| `"dispute"` | 3 | 付款争议中 |
| `"past_due"` | 4 | 付款逾期 |
| `"expired"` | 5 | 已过期 |
| `"offline"` | 6 | 离线模式 |

### 5.2 `status` 枚举映射

```
libValidationStatus == 9  →  status = 1 (Active)
libValidationStatus != 9  →  status = 0 (Inactive)
```

其中 9 代表 RSA 数字签名验证成功。

### 5.3 关键地址速查表（arm64）

| 方法 | VM 地址 | Fat 文件偏移 | 大小 |
|------|---------|-------------|------|
| `-[MPALibLicenseValidationResult status]` | `0x230c0` | `0x3170c0` | 20 bytes |
| `-[MPALibLicenseValidationResult needsAttentionType]` | `0x230d4` | `0x3170d4` | ~160 bytes |
| `-[MPALibLicenseValidationResult initForLicense:libValidationStatus:libLicenseInfo:]` | `0x23094` | `0x317094` | ~44 bytes |
| `-[MPALibLicenseValidator initWithDeviceID:publicKeyFileURL:]` | `0x23684` | `0x317684` | — |
| `UnlockedFunctionalityPerformer.performIfUnlocked` | `0xf5ad8` | — | — |

---

## 六、实测复核与最终方案（重要修正 · 2026-07-12）

> 本节基于对 5.5.6 (arm64) 的**完整重签 + 端到端**实测（含 root 清理、菜单栏监控），修正 §二/§三 的若干结论，并给出经验证的**最小必要集**与新设备**部署方法**。与前文冲突处以本节为准。

### 6.1 对前文的修正

| 前文结论 | 实测修正 |
|----------|----------|
| 需配合修改 plist 缓存（方案 D） | **不需要**。纯二进制补丁即可，无需改 plist。 |
| 需先用真实账号登录写入客户信息 | **不需要**。全新设备（已清空全部用户数据）直接激活可用。 |
| 缓存 plist 键 `22ea3f...` 为 AES 加密（见 Activation 文档 §4.1） | 实为**明文 JSON**，客户字段是账号级、**无硬件绑定**（该处描述有误）。 |
| `needsAttentionType→0` 必须 | 对全新设备**非必须**（无真实订阅时该方法本就返回 0）；仅当本地缓存存在真实的过期/取消订阅时才需要。 |
| （未覆盖） | ad-hoc 重签会连带打断 **root 级清理（特权 Agent）** 与 **菜单栏监控**，需额外处理（6.4、6.5）。 |

**结论**：前文只验证了"主窗口是否显示"，导致把 plist 当成必需、并漏掉了两条关键链路。真正让 App **完整可用**的是下面的 4 处修改 + 深度重签。

### 6.2 根本约束：为什么改一处会牵连一大片

```
patch 任意 Mach-O 字节
   └─ arm64 + Hardened Runtime + Library Validation
        └─ 只能加载同签名身份的库 ⇒ 必须 ad-hoc 重签主 App
             └─ 主 App 丢失团队号 S8EX82NJP6
                  └─ 所有"基于团队号的组件互信"全部失效：
                       · 特权 Agent(root) ⇄ 主App 互认      → root 清理失败
                       · 登录项(Menu/HealthMonitor) 身份不一致 → 菜单栏死锁
```
无法规避：没有 MacPaw 私钥就无法复原 S8EX82NJP6，也伪造不出 `anchor apple generic`。唯一出路是**逐一放宽/绕过这些互信校验**，并让**所有组件统一为 ad-hoc 身份**。

### 6.3 最小必要集（4 处修改 + 深度重签）

编号与 `patch_cleanmymac.py` 一致：

| # | 位置 | 修改 | 作用 |
|---|------|------|------|
| **#1** | `MacPawAccount` | `-[MPALibLicenseValidationResult status]` 恒返回 1 | 许可证恒为已激活；全链路视为有效 |
| **#2** | `PrivilegedOperationsPerformerService` | 绕过 `SecStaticCodeCheckValidity`（cbz→b） | 让 App 肯安装 ad-hoc 的 Agent |
| **#3** | 主 App `Info.plist` | `SMPrivilegedExecutables[Agent]` 降为只认 identifier | `SMJobBless` 装载时肯接受 ad-hoc helper |
| **#4** | `Agent` | `SMAuthorizedClients` 主 App 条目降为只认 identifier | Agent 肯接受 ad-hoc 主 App 客户端 |
| **E** | 全包 | ad-hoc `--deep` 重签（先单独签 Agent）+ 去隔离 | 全组件统一 ad-hoc 身份 |

**字节/数据细节**

- **#1**（`MacPawAccount`）：8 字节 `80 00 00 b4 08 08 40 f9` 在包内**出现 2 次不唯一**，故匹配含 `cmp x8,#9` 的 **20 字节唯一方法体**，仅改写开头两条指令为 `mov w0,#1 / ret`：
  `80 00 00 b4 08 08 40 f9 1f 25 00 f1 e0 17 9f 1a c0 03 5f d6` → `20 00 80 52 c0 03 5f d6 1f 25 00 f1 e0 17 9f 1a c0 03 5f d6`
- **#2**（`PrivilegedOperationsPerformerService`，VM `0x6518`，fat `0x3E518`）：`8b 41 00 94 80 05 00 34`(bl+cbz) → `8b 41 00 94 2c 00 00 14`(bl+**无条件 b**)。全局唯一。
- **#3**（主 App `Info.plist`）：键 `SMPrivilegedExecutables:com.macpaw.CleanMyMac5.Agent`
  `identifier "…Agent" and anchor apple generic and certificate leaf[subject.OU]="S8EX82NJP6"` → `identifier "com.macpaw.CleanMyMac5.Agent"`
- **#4**（`Agent` 内嵌 Info.plist 的 `SMAuthorizedClients` 主 App 那条，两 slice 各一份，共 2 处，**等长补空格**原地改）：
  `identifier "com.macpaw.CleanMyMac5" and info […] &gt;= "0.0.1" and anchor apple generic and certificate leaf[subject.OU]="S8EX82NJP6"` → `identifier "com.macpaw.CleanMyMac5"`

**排除项（实测非必需）**：`needsAttentionType→0`（6.1）；Agent 内 `SecCodeCheckValidity` 的 in-code bypass（与 #4 冗余——#4 已从源头放松其读取的要求）。

### 6.4 特权（root）清理链路：组件互信全景

root 级操作（删系统登录项、卸载带特权组件的 App、系统级垃圾等）经由 **root 守护进程 `com.macpaw.CleanMyMac5.Agent`**（SMJobBless 安装到 `/Library/PrivilegedHelperTools`）。App 与 Agent **双向代码签名互认**：

```
App 首次需要 root 操作
   │
   ▼ ① 校验包内 Agent 二进制签名        ←── #2  (SecStaticCodeCheckValidity)
   │    不过 → 日志 "Couldn't verify bundle" → 中止
   ▼ ② SMJobBless 安装 Agent 为 root 守护进程
   │    · 验 helper 是否满足 App 的 SMPrivilegedExecutables ←── #3
   │    · 验调用方是否满足 Agent 的 SMAuthorizedClients      ←── #4(装载侧)
   ▼ ③ XPC 连接向 Agent 发特权请求
        · Agent 用 audit token 取客户端 SecCode,
          按 SMAuthorizedClients 拼 ClientRequirement 校验    ←── #4(运行侧)
```

安全模型本质：**"谁能以 root 运行"（helper 侧，#2/#3 验 helper）** 与 **"谁能指挥 root"（client 侧，#4 验 client）** 两个方向都用代码签名要求锁死到团队 `S8EX82NJP6`。ad-hoc 后两向全断，#2/#3/#4 正是把两向逐一打开。

- `SMAuthorizedClients` 是 Agent 内嵌 Info.plist（`__TEXT,__info_plist`，因 Agent 是独立可执行文件无 .app 外壳）里的**授权客户端白名单**，含 `com.macpaw.CleanMyMac5` / `.Menu` / `.HealthMonitor` 三条要求。
- #2 校验的是**包内那份即将被扶正为 root 的 Agent**，属"纵深防御 + 反篡改"——防止有人替换 Agent 二进制后被 App 用 `SMJobBless` 装成恶意 root 守护进程。

### 6.5 菜单栏监控死锁与 `--deep` 修复

**现象**：点菜单栏图标转圈/卡死。**采样**显示 `CleanMyMac_5_Menu` 主线程阻塞在 `_dispatch_semaphore_wait_slow`（`viewDidAppear` 里同步等待到 `HealthMonitor` 的 XPC 回复）。

**根因**：登录项 `Menu`/`HealthMonitor` 由主 App 经 **SMAppService** 注册，macOS 以**启动约束(LWCR)/对等身份**把它们与注册方(主 App)绑定。若主 App 为 ad-hoc 而登录项仍是 Developer ID（团队 S8EX82NJP6），**身份不一致** → Menu↔HealthMonitor 的 XPC 建立不起来 → Menu 同步等待永不返回 → 主线程死锁。

**修复**：让**所有组件与主 App 同为 ad-hoc 身份**——收尾用 `codesign --deep` 统一整包（登录项/XPC/扩展/框架/主 exe）。实测：把两个登录项也 ad-hoc 深签后，菜单栏恢复正常。

### 6.6 关键坑（都踩过并已规避）

1. **不能带回 entitlements**：给 ad-hoc 二进制加 `application-identifier`/`team-identifier` 等**受限** entitlements 会被 AMFI 拒绝启动（`RBSRequestError 5 / spawn failed, POSIX 153`）。→ 一律 `codesign -f -s -` **不带 entitlements**（App 无 entitlements 也能正常读 Group Container 等）。
2. **`--deep` 覆盖不到 `Contents/Library/LaunchServices`**：里面的 **Agent 必须先单独签**，再 `--deep` 整包（否则 Agent 保留失效的原签名/未被签）。
3. **#1 特征码不唯一**（8 字节出现 2 次）：必须用 20 字节唯一方法体或按偏移，避免误改另一处。
4. **#4 需替换 2 处**：`SMAuthorizedClients` 串在 x86_64 / arm64 两个 slice 各一份。
5. **登录项改签后需重新注册**：全新安装时由主 App 注册天然一致，无需干预；对已安装实例改签会因 cdhash 变化需重注册。

### 6.7 必要性判定（#2/#3/#4 均 100% 必要）

用 `nm`（强制点是否真实存在）+ `codesign -R`（ad-hoc 组件是否满足原始严格要求）两把尺子，不依赖 UI 复现：

| # | 强制点存在性（nm） | ad-hoc 满足原始要求？（codesign -R） | 结论 |
|---|---|---|---|
| #2 | POPS 调用 `SecStaticCodeCheckValidity` ✅（且实测报 "Couldn't verify bundle"） | — | **必要** |
| #3 | `SMJobBless` 被真实调用 ✅ | ad-hoc Agent **不满足**原始 `SMPrivilegedExecutables` 要求 | **必要** |
| #4 | `SMJobBless` + Agent 内 `SecCodeCheckValidity` ✅ | ad-hoc 主 App **不满足**原始 `SMAuthorizedClients` 要求 | **必要** |

三者分处不同校验点、检查不同对象（#2/#3 验 helper、#4 验 client），**互不冗余，无一可省**。

### 6.8 代码位置速查（arm64，`PrivilegedOperationsPerformerService`）

| 用途 | 所在函数(符号已 strip) | 调用/补丁 VM 地址 |
|------|------|------|
| #2 校验 Agent 签名 | 0x6444（含 `SecRequirementCreateWithString`+日志 "Couldn't check validity bundle at Bundle:"） | bl `_SecStaticCodeCheckValidity` @`0x6514`；**补丁 cbz→b @`0x6518`** |
| #3 触发点（SMJobBless 安装 helper） | 0x48a4（引用 `kSMDomainSystemLaunchd`） | bl `_SMJobBless` @`0x491c`（校验在系统 `SMJobBless` 内部，故 #3 只能改 plist 数据） |

### 6.9 部署到新设备（经端到端验证）

```bash
# 1) 从原版 DMG 拷出（保留原始 Developer ID 签名的干净副本）
ditto /Volumes/CleanMyMac/CleanMyMac_5.app /tmp/CleanMyMac_5.app
# 2) 打补丁：#1~#4 + 去隔离 + 深度 ad-hoc 重签（脚本内含 Agent 先单独签）
python3 patch_cleanmymac.py /tmp/CleanMyMac_5.app
# 3) 装入 /Applications
ditto /tmp/CleanMyMac_5.app /Applications/CleanMyMac_5.app && open -a /Applications/CleanMyMac_5.app
```

**效果**：首启即**已激活、无登录、无购买 nag**；菜单栏监控正常；**首次触发特权操作**弹一次密码框安装守护进程（仅此一次），此后 root 清理正常。补丁字节/改动与设备无关，可复用到任意 arm64 机器；字节偏移为 5.5.6 专用，换版本若特征码不匹配脚本会报错停止而非乱改。

> 完整实现见同目录 `patch_cleanmymac.py`（幂等、全特征码匹配、支持任意 app 路径）。
