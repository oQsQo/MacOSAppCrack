# CleanMyMac 5 激活架构与流程深度分析

> 版本 5.5.6 (Build 50506.0.2607101255) · Site 版本 (非 Mac App Store) · MacPaw Way Ltd (S8EX82NJP6)  
> 分析方法：二进制符号表 (`nm` + `swift demangle`)、字符串提取 (`strings`)、mitmdump 抓包、cURL 实测

---

## 一、应用整体架构

### 1.1 应用包结构

```
/Applications/CleanMyMac_5.app/
├── Contents/
│   ├── MacOS/CleanMyMac_5                  ← 主可执行文件 (Universal Binary: x86_64 + arm64)
│   ├── Frameworks/                         ← 核心框架 (见 1.2)
│   ├── XPCServices/
│   │   └── com.macpaw.CleanMyMac5.MASUpdaterXPCService.xpc
│   ├── PlugIns/
│   │   └── CleanMyMac_5_FinderSyncExtension.appex
│   ├── Extensions/
│   │   └── CleanMyMac_5_AppIntentsExtension.appex
│   ├── Library/LoginItems/
│   │   ├── CleanMyMac_5_HealthMonitor.app  ← 健康监控常驻进程
│   │   └── CleanMyMac_5_Menu.app           ← 菜单栏常驻进程
│   ├── Resources/
│   │   ├── license_plan                    ← 当前计划类型 (值: "plus")
│   │   └── embedded.provisionprofile       ← 配置描述文件
│   └── Info.plist
```

### 1.2 许可证相关核心框架

| 框架 | 职责 |
|------|------|
| **MacPawAccount.framework** | 核心：账户管理、OAuth 认证、许可证获取/验证、UI 流程控制、本地加密存储 |
| **ActivationService.framework** | 激活管理器抽象层 (Protocol `ActivationManagerType`) |
| **CleanMyMacNFRService.framework** | NFR 功能限制管理、Mac App Store IAP 验证 |
| **AppAuth.framework / AppAuthCore.framework** | OAuth 2.0 协议支持 |
| **NetworkService.framework** | HTTP 网络层，提供 `ClientIDRequestConfigurator`、HMAC 签名等 |
| **SharedPreferences.framework** | 跨进程共享偏好（Group Container） |
| **PreferencesAPI.framework** | 偏好设置抽象层 |

### 1.3 分层架构

```
┌─────────────────────────────────────────────────────────┐
│  UI 层                                                    │
│  MPAFlowController / MPASignInEmailViewController /       │
│  MPASelectProductPlanViewController / MPARedeemCodeVC     │
├─────────────────────────────────────────────────────────┤
│  业务逻辑层                                                │
│  ActivationManagerMPA / LicensePlanService /               │
│  MPALicenseUpdateReactor / MPACustomerPlanRelationship    │
├─────────────────────────────────────────────────────────┤
│  验证层                                                    │
│  MPALibLicenseValidator / Security.framework /             │
│  SecVerifyTransformCreate + SHA-256                        │
├─────────────────────────────────────────────────────────┤
│  网络层                                                    │
│  MPAServerDataProviderImp / APIClient / NetworkService /   │
│  ClientIDRequestConfigurator / HMACRequestConfigurator     │
├─────────────────────────────────────────────────────────┤
│  持久化层                                                  │
│  MPASharedStorage (AES 加密文件) / MPAKeychainStorage /    │
│  UserDefaults / Group Container                            │
└─────────────────────────────────────────────────────────┘
              ↑ 自上而下的依赖方向
```

---

## 二、激活流程详解

### 2.1 MPAFlowController 状态机

`MPAFlowController` 是激活流程的核心控制器，基于状态机模式驱动 UI 流转。

**流程转换方法（从 ObjC 符号表提取）：**

| 方法 | 说明 |
|------|------|
| `proposeNextSelectActivationPlanFlowStep` | → 选择激活计划 |
| `proposeNextSelectActivationSeatToReplaceFlowStep` | → 选择要替换的座位 |
| `proposeNextRefreshActivationPlanSeatsFlowStep` | → 刷新座位列表 |
| `proposeNextActivateAppFlowStep` | → 执行应用激活 |
| `proposeNextLicenseValidationFlowStepForLicense` | → 许可证验证 |
| `proposeNextRetryActivationErrorStep` | → 重试激活错误 |
| `proposeNextRetryOfflineErrorStep` | → 重试离线错误 |
| `bestFlowForLicenseValidationResult` | → 根据验证结果选择最佳流程 |

**关键属性：**

- `currentStep` — 当前流程步骤
- `currentStepViewController` — 当前步骤的 ViewController
- `currentSubFlowName` — 当前子流程名称
- `completionHandler` — 流程完成回调
- `flowInfoStorage` — 流程信息存储

### 2.2 完整激活链路

```
用户触发激活
   │  (UI 按钮 / DeepLink / 启动时检查)
   ▼
┌─────────────────────────┐
│  1. 邮箱检查              │
│  POST /email/check        │
│  → exist? completed?      │
└─────────┬───────────────┘
          │
     ┌────┴────┐
     │exist=true│  exist=false → 注册流程
     │completed │  completed=false → 认领流程
     │ =true    │
     └────┬────┘
          ▼
┌─────────────────────────┐
│  2. 用户登录              │
│  POST /sign-in            │
│  → {token}                │
│  Token 存入 Keychain       │
└─────────┬───────────────┘
          ▼
┌─────────────────────────┐
│  3. Token 验证            │
│  POST /validate/token     │
│  → 204 (有效)             │
│  → 401 (需重新登录)       │
└─────────┬───────────────┘
          ▼
┌─────────────────────────┐
│  4. 获取用户资料          │
│  GET /customer/profile    │
│  → {id, email, roles}    │
│  创建 MPACustomerImp      │
│    (_customerId, _email,  │
│     _name, _sessionToken) │
└─────────┬───────────────┘
          ▼
┌─────────────────────────┐
│  5. 获取产品计划          │
│  GET /customer/           │
│    product-plan           │
│  ?appBundleId=            │
│   com.macpaw.CleanMyMac5  │
│  → {data: [plans...]}    │
└─────────┬───────────────┘
          │
     ┌────┴────┐
     │data=[]  │  → 无计划: 提示购买 (MPAProductPlanAbsenceVC)
     │data有值 │  → 多个计划: 选择计划 (MPASelectProductPlanVC)
     └────┬────┘
          ▼
┌─────────────────────────┐
│  6. 查询座位状态          │
│  (嵌入在计划数据中)       │
│  → HasFreeSeats: 直接激活 │
│  → HasNoFreeSeats:        │
│    选择替换 (MPASelect    │
│    PlanSeatVC)            │
└─────────┬───────────────┘
          │
     ┌────┴──────────┐
     │有空座位         │没有空座位
     │POST /seat      │PATCH /seat
     │(新增)          │(替换 seatToReplace)
     └────┬──────────┘
          ▼
┌─────────────────────────┐
│  7. 激活座位              │
│  POST/PATCH               │
│    /activation/seat       │
│  Body:                    │
│   customerProductPlanId   │
│   hardwareUuid            │
│   productBundleId         │
│   machineModel            │
│   machineName             │
│   macAddress              │
│  → 返回 License Payload   │
└─────────┬───────────────┘
          ▼
┌─────────────────────────┐
│  8. 本地密码学验证        │
│  MPALibLicenseValidator   │
│    .validateLicense:      │
│  Security.framework:      │
│   SecItemImport (导入公钥) │
│   SecVerifyTransformCreate│
│   SecTransformSetAttribute│
│     (kSecDigestSHA2, 256) │
│   SecTransformExecute     │
│  → MPALibLicenseValidation│
│    Result                 │
└─────────┬───────────────┘
          ▼
┌─────────────────────────┐
│  9. 持久化存储            │
│  MPASharedStorage:        │
│    AES 加密写入 Group     │
│    Container plist        │
│  MPAKeychainStorage:      │
│    kLicensePlanKey →      │
│    Keychain               │
│  UserDefaults:            │
│    缓存验证结果            │
└─────────┬───────────────┘
          ▼
┌─────────────────────────┐
│  10. 通知与 UI 更新       │
│  MPALicenseUpdateReactor  │
│    → 通知各模块许可证变更  │
│  LicensePlanService       │
│    → CMLicensePlanChanged │
│  ActivationFlowFinished   │
│    Running                │
└─────────────────────────┘
```

### 2.3 密码重置流程

```
POST /recovery-password/send-email     →  {resetToken} + 邮件 (6 位 PIN)
                     ↓
POST /recovery-password/validate-pincode  ←  {resetToken, pinCode}
                     ↓
POST /recovery-password/change-password   ←  {resetToken, pinCode, password}
```

### 2.4 账户认领流程

用于 `email/check` 返回 `exist: true, completed: false` 的账户：

```
POST /claim-account/send-email          →  {claimToken} + 邮件 (6 位 PIN)
                     ↓
POST /claim-account/validate-pincode     ←  {claimToken, pinCode}
                     ↓
POST /claim-account/sign-up              ←  {claimToken, pinCode, password, newsAndOffersSubscription}
```

### 2.5 兑换码流程

```
POST /redeem-code/get-type  ←  {redeemCode: "XXXX-XXXX-XXXX-XXXX"}
         ↓
    返回兑换码类型 (subscription / lifetime 等)
         ↓
    自动关联到用户账户 → 回到计划选择步骤
```

---

## 三、许可证验证机制

### 3.1 密码学验证链

```
服务端 (activation.macpaw.com)
  │
  │  RSA 私钥签名 License Payload
  ▼
┌───────────────────────┐
│  License Payload       │
│  (JSON 结构化数据)      │
│  + RSA 数字签名         │
└──────────┬────────────┘
           │  HTTPS 传输
           ▼
客户端 (CleanMyMac 5)
  │
  │  ① SecItemImport: 导入内嵌 RSA 公钥
  │  ② SecVerifyTransformCreate: 创建验证 Transform
  │  ③ SecTransformSetAttribute:
  │     - kSecTransformInputAttributeName = signature
  │     - kSecDigestTypeAttribute = kSecDigestSHA2
  │     - kSecDigestLengthAttribute = 256
  │  ④ SecTransformExecute: 执行验证
  ▼
┌───────────────────────┐
│  MPALibLicenseValidation│
│  Result:                │
│  - status (Active/...)  │
│  - ownership (Owner/    │
│    Member)              │
│  - expirationDate       │
│  - nextBillingDate      │
│  - seatID               │
│  - seatStatus           │
│  - activeUntilTimestamp  │
│  - needsAttentionType   │
│  - isActivated          │
└───────────────────────┘
```

### 3.2 许可证状态体系

| 状态 | 枚举名 | 说明 |
|------|--------|------|
| 有效 | `Active` | 许可证正常有效 |
| 试用 | `Trial` | 试用期中 |
| 过期 | `Expired` | 许可证/订阅已过期 |
| 停用 | `Deactivated` | 已手动停用 |
| 取消 | `Cancelled` | 订阅已取消（可能有剩余天数） |
| 暂停 | `Paused` | 订阅暂停中 |
| 争议 | `Dispute` | 付款争议中 |
| 逾期 | `PastDue / PaymentFailed` | 付款失败 |
| 待处理 | `Pending` | 等待处理中 |
| 离线 | `Offline` | 离线宽限期模式 |

### 3.3 本地存储的许可证结构

通过解码 Group Container 中的 plist 数据得到的实际存储格式：

```json
{
  "license": {
    "ownership": 0,
    "activeUntilTimestamp": 0,
    "seatStatus": 0
  },
  "needsAttentionType": 0,
  "isActivated": false
}
```

| 字段 | 说明 |
|------|------|
| `license.ownership` | 0 = 无 / Owner / Member |
| `license.activeUntilTimestamp` | 有效截止 Unix 时间戳 |
| `license.seatStatus` | 0 = 无座位 / HasFreeSeats / HasNoFreeSeats |
| `needsAttentionType` | 需要关注的类型（取消/暂停/争议/逾期等） |
| `isActivated` | 是否已激活 |

存储位置：`~/Library/Group Containers/S8EX82NJP6.com.macpaw.CleanMyMac5/Library/Preferences/S8EX82NJP6.com.macpaw.CleanMyMac5.plist`

存储键名为 MD5 哈希：`22ea3f1cac4e7127e54551884f2ab076`

---

## 四、持久化存储体系

### 4.1 三层存储架构

| 存储层 | 实现类 | 存储内容 | 安全措施 |
|--------|--------|----------|----------|
| **加密文件存储** | `MPASharedStorage` / `SharedFileDataStore` | 许可证数据（JSON） | AES 加密，密钥由 `IOPlatformUUID` 派生 |
| **Keychain 存储** | `MPAKeychainStorage` | Session Token、许可证计划敏感数据 | macOS Keychain (Access Group: `S8EX82NJP6.*`) |
| **偏好存储** | `UserDefaults` / `SharedPreferences` | 缓存状态、配置、统计 | Group Container 跨进程共享 |

### 4.2 存储位置

```
~/Library/Preferences/com.macpaw.CleanMyMac5.plist
    → UserDefaults (主应用)
    → MPA_<hash>_customer_ts: 加密的客户数据 (64 bytes AES)
    → CMAUIdentifier: 设备标识 UUID
    → SubscriptionCancelled: 订阅取消标记

~/Library/Group Containers/S8EX82NJP6.com.macpaw.CleanMyMac5/
    Library/Preferences/S8EX82NJP6.com.macpaw.CleanMyMac5.plist
    → 跨进程共享配置
    → <md5_hash>: 加密的许可证 JSON (license, isActivated 等)
    → AnalyticsIdentifier: 分析标识 UUID
    → RemoteConfig.*: 远程配置缓存

~/Library/HTTPStorages/com.macpaw.CleanMyMac5/
    httpstorages.sqlite
    → HTTP 缓存和 ALT-SVC 记录
```

### 4.3 加密方案

```
IOPlatformUUID (硬件 UUID)
    ↓  密钥派生
AES 对称密钥
    ↓  加密/解密
许可证 JSON 数据 ←→ 加密 blob (存入 plist/文件)
```

使用的加密 API：
- `CCCryptor` (CommonCrypto) — AES 对称加密
- `SecItemImport` — RSA 公钥导入
- `SecVerifyTransformCreate` — RSA 签名验证

---

## 五、网络通信架构

### 5.1 服务端点

| 域名 | 用途 |
|------|------|
| `oauth.macpaw.com` | OAuth 认证（登录/注册/Token/密码重置） |
| `activation.macpaw.com` | 许可证激活（计划/座位/兑换码/伴侣应用） |
| `ft.macpaw.com` | GrowthBook 特性开关 |
| `api-lytics.macpaw.com` | 遥测分析上报 |
| `public-apis.cleanmymac.com` | 远程配置 |
| `updates.cleanmymac.com` | Sparkle 应用更新 |
| `o36975.ingest.sentry.io` | Sentry 错误上报 |

### 5.2 请求认证机制

```
所有请求
    ├── clientid: 746064c451c98f8675435e6e3c205f2f     (HTTP Header, 固定值)
    ├── User-Agent: cmm-main/5.5.6 (site/...)           (HTTP Header)
    └── Authorization: Bearer <session_token>            (HTTP Header, 需登录后)

NetworkService.framework:
    ClientIDRequestConfigurator  →  注入 clientid 头
    HMACRequestConfigurator      →  HMAC 签名 (部分接口)
    JSONRequestConfigurator      →  JSON Content-Type
```

### 5.3 核心网络类

```
MPAServerDataProviderImp
    │  initWithClientID:userAgent:storage:
    │
    ├── checkEmail:withCallback:
    ├── signInWithEmail:password:callback:
    ├── fetchCustomerInfoWithToken:callback:
    ├── fetchCurrentCustomer:
    ├── fetchAvailablePlansForCurrentCustomerForProduct:callback:
    ├── fetchCurrentCustomerPlanWithPlanInfo:callback:
    ├── activateAppWithPlan:seatToReplace:callback:
    ├── deactivateAppWithCallback:
    ├── fetchActivationLicenseWithToken:planInfo:callback:
    ├── fetchCachedLicense:
    ├── updateCachedActivationLicenseWithCallback:
    ├── cacheCustomer:callback:
    ├── cacheLicense:callback:
    ├── replaceCustomer:callback:
    ├── sendRecoveryPinCode:callback:
    ├── recoverCustomerAccount:callback:
    ├── executeSignOutCurrentCustomer:callback:
    └── performRequestWithURLString:URLTag:httpMethod:httpHeaders:getParams:JSONBody:timeoutInterval:completionHandler:
```

---

## 六、设备绑定与座位管理

### 6.1 设备指纹采集

| 标识符 | 来源 | 用途 |
|--------|------|------|
| `hardwareUuid` (IOPlatformUUID) | `IOKit` `IOPlatformExpertDevice` | 主设备标识 + 加密密钥派生 |
| `machineModel` | `IOKit` | 机型标识 (如 `MacBookPro18,1`) |
| `machineName` | 系统设置 | 设备名称 (如 `My-MacBook-Pro`) |
| `macAddress` | 网络接口 | MAC 地址 |
| `IOPlatformSerialNumber` | `IOKit` | 设备序列号 (辅助标识) |

### 6.2 座位 (Seat) 模型

```
MPAActivatedSeatImp
    +makeSeatWithServerJSON:errorsLogger:
    +statusFromString:

座位状态:
    HasFreeSeats     → 有空闲座位，可直接激活
    HasNoFreeSeats   → 座位已满，需替换现有座位

所有权类型:
    Owner   → 计划所有者
    Member  → 计划成员（被分享者）
```

**座位管理 API 端点：**
- `POST /activation/seat` — 新增座位（激活新设备）
- `PATCH /activation/seat` — 替换座位（踢掉旧设备）
- 不支持 `GET`（查看）和 `DELETE`（删除）单独操作

---

## 七、错误处理与恢复

### 7.1 激活错误类型

| 错误枚举 | 处理策略 |
|----------|----------|
| `ActivationErrorExpired` | 提示续费 / 购买新计划 |
| `ActivationErrorDeactivated` | 提示重新激活 |
| `ActivationErrorCancelled` | 显示剩余天数 (`daysLeft`)，引导恢复订阅 |
| `ActivationErrorPaused` | 引导取消暂停 |
| `ActivationErrorDispute` | 区分 Owner/Member，引导联系支持 |
| `ActivationErrorPaymentFailed` | 引导更新支付信息 |
| `ActivationErrorOffline` | 离线宽限期 (`LastDaysOffline`)，等待网络恢复 |
| `ActivationInternalError` | Sentry 上报 + 显示重试选项 |
| `ActivationPlanError` | 计划不匹配/缺失，引导购买 |

### 7.2 服务端错误响应解析

```
MPAServerResponseError
    ├── isActivationTokenDeactivatedError  →  Token 已停用
    ├── isCustomerSessionInvalid           →  Session 过期
    ├── hasValidationErrorCode             →  字段校验错误码匹配
    └── MPAServerResponseValidationError   →  详细字段校验信息

统一错误格式:
{
    "code": "400",
    "message": "Validation Failed",
    "errors": [{"code": "<请求名>.<字段名>.<规则>", "path": "<字段名>"}],
    "params": null | {...}
}
```

### 7.3 错误上报

通过 `MPASentryIssuesReporter` 上报至 Sentry：

```
+reportError:forCustomer:licenseInfo:breadcrumbs:errorCallStack:
+eventPayloadForError:forCustomer:licenseInfo:breadcrumbs:errorCallStack:
+payloadUserInterfaceForCustomer:

Sentry DSN: o36975.ingest.sentry.io
Sentry Public Key: 2e6b73e103b7454b902ba46884966bfd
Sentry Client: sentry.cocoa=6.2.1
```

---

## 八、DeepLink 与外部触发

### 8.1 URL Scheme

| Scheme | 用途 |
|--------|------|
| `cleanmymac5://` | 主 URL Scheme（激活、登录等） |
| `cleanmymac5-site://` | Site 版本专用 |
| `cleanmymac5actions://` | 激活操作触发 (`com.macpaw.activation`) |
| `db-hfn3qmlc7uq9kxd://` | Dropbox OAuth 回调 |

### 8.2 激活路由

```
MacPawAccount
    +tryToSignInWithURLSchemeComponents:

路由类型:
    MainAppActivateRoute.Activate          →  触发完整激活流程
    MainAppActivateRoute.startFreeTrial    →  开始免费试用
    MainAppActivateRoute.unlockMyClutter   →  解锁 MyClutter 功能
    Reactivate deeplink (MPA)              →  重新激活
```

---

## 九、NFR 功能限制系统

### 9.1 NFR 架构

```
CleanMyMacNFRService.framework
    │
    ├── CleanMyMacNFRServiceType          →  核心 NFR 服务
    ├── ApplicationsNFRServiceType        →  应用模块限制
    ├── MASInAppPurchaseNFRServiceType    →  Mac App Store IAP 验证
    ├── AITipsNFRServiceType              →  AI 提示功能限制
    └── NFRPipelineScanServiceType        →  扫描管线 NFR 追踪

NFR 适配器:
    NFRPipelineServiceAdapter
    ApplicationsNFRServiceAdapter
```

### 9.2 许可证计划与功能映射

| 计划类型 | 说明 |
|----------|------|
| `Basic` | 基础版：有功能限制 |
| `Plus` | 增强版：完整功能 + 云存储清理 |
| `Plus Without Cloud` | 增强版（无云）：完整功能，无云存储 |

**许可证类型 (`ActivationPurchaseLicenseKind`)：**
- `subscription` — 订阅制（周期续费，`activeUntilTimestamp` 记录截止时间）
- `trial` — 试用期

**计划变更通知：**
- `CMLicensePlanChanged` — 许可证计划变更时广播
- `LicensePlanService` — 管理计划的存储和分发
- `LicensePlanManager` — 读取 `Resources/license_plan` 文件

---

## 十、远程配置与特性开关

### 10.1 GrowthBook / OpenFeature

```
SDK Key: sdk-R8H6ciJOO53TBr
端点: https://ft.macpaw.com/api/features/sdk-R8H6ciJOO53TBr
特性数量: 36 个 (截至 2026-07-10)

特性开关示例:
    CMY-3606: {applyStrictValidation, useMacPawReceiptValidator}
    test-pay-macpaw: A/B 测试
    CMY-3619, CMY-3686, CMY-3687: 功能开关
    TBT-96, TBT-98, TBT-103...: 测试变体
```

### 10.2 远程配置缓存

```
存储路径: Group Container Preferences
键前缀: RemoteConfig.*

已知配置项:
    RemoteConfig.CompanionAppActivationFeatureEnabled = 1
    RemoteConfig.MacPawReceiptValidationEnabled = 0
    RemoteConfig.MoonlockSupportedLocales = [en, de, fr, es, pt]
    RemoteConfig.ShouldShowExploreMoonlockRecommendation = 0
    RemoteConfig.ShouldTrackCloudStorageErrors = 1
    RemoteConfig.status = 0
    RemoteConfig.version = 24
```

---

## 十一、更新机制

### 11.1 Sparkle 更新框架

```
更新服务器: updates.cleanmymac.com
签名算法: EdDSA (Ed25519)
检查间隔: SULastCheckTime 记录
更新组: SUUpdateGroupIdentifier = 1418688534
```

---

## 十二、安全机制总结

| 层面 | 机制 | 实现 |
|------|------|------|
| **传输安全** | HTTPS + Cloudflare CDN | 所有 API 通过 TLS 加密传输 |
| **客户端标识** | `clientid` 请求头 | 固定值，用于验证合法客户端 |
| **会话安全** | Bearer Token | 每次登录生成新 Token，登出后失效 |
| **许可证防伪** | RSA 数字签名 | 服务端私钥签名，客户端内嵌公钥验签 |
| **本地数据防篡改** | AES 对称加密 | 密钥由 `IOPlatformUUID` 派生，绑定硬件 |
| **敏感数据保护** | macOS Keychain | Token 和许可证密钥存入 Keychain |
| **设备绑定** | 多维度指纹 | UUID + 机型 + 设备名 + MAC 地址 |
| **座位限制** | 服务端座位管理 | 限制并发激活设备数量 |
| **代码完整性** | Developer ID + Provisioning Profile | Apple 代码签名 |
| **更新安全** | Sparkle EdDSA | Ed25519 签名验证更新包 |
| **错误监控** | Sentry 集成 | 异常上报含许可证上下文 |
| **人机验证** | captchaToken | CORS 头暗示部分操作有验证码保护 |

---

## 十三、关键发现

1. **混合验证模型**：服务端签发 + 客户端验签。License Payload 由服务端 RSA 私钥签名，客户端使用内嵌公钥通过 `Security.framework` 验证，确保许可证不可伪造。

2. **无离线激活路径**：首次激活必须在线完成。已激活设备有离线宽限期 (`LastDaysOffline`)，宽限期内可离线使用。兑换码 (Redeem Code) 也需在线验证。

3. **硬件绑定加密**：本地存储的许可证数据使用 AES 加密，密钥由 `IOPlatformUUID` 派生，使得加密数据无法跨设备迁移。

4. **状态机驱动的 UI 流程**：`MPAFlowController` 通过 7 个 `proposeNext*` 方法管理所有激活子流程的转换，支持前进、后退、错误重试。

5. **统一账户体系**：深度集成 MacPaw 统一账户 (`oauth.macpaw.com`)，支持邮箱登录、账户认领、密码重置、QR 码两步验证。所有 MacPaw 产品共用同一账户。

6. **伴侣应用激活**：通过 `companion-app` 端点支持关联应用 (如 CleanMyPhone) 的交叉激活，使用 QR 码引导用户完成移动端激活。

7. **双版本策略**：Site 版本通过服务端 API 验证许可证；Mac App Store 版本通过 Apple Receipt (`macPawReceiptValidator` / `appleReceiptValidator`) 验证 IAP。GrowthBook 特性开关 `useMacPawReceiptValidator` 控制验证器的选择。
