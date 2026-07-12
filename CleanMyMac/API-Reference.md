# CleanMyMac 5 API 接口文档

> 通过二进制逆向分析 + mitmdump 抓包 + cURL 实测验证。所有接口均已通过真实请求确认，返回数据为实测结果。

---

## 公共请求头

所有请求**必须**包含以下头部：

```
Content-Type: application/json
clientid: 746064c451c98f8675435e6e3c205f2f
User-Agent: cmm-main/5.5.6 (site/50506.0.2607101255; macOS 15.7.7; arm64)
```

需要鉴权的接口还须添加：

```
Authorization: Bearer <session_token>
```

可选头部：

```
language: zh
sentry-trace: <trace_id>-<span_id>-0
baggage: sentry-environment=production,sentry-public_key=2e6b73e103b7454b902ba46884966bfd,...
```

> **注意**：`clientid` 是 **HTTP 请求头**（不是 JSON body 字段），值固定为 `746064c451c98f8675435e6e3c205f2f`。缺失或错误将返回 `400 checkEmailRequest.clientId.notNull` 或 `401 clientId.required`。

---

## 关键变量

| 变量 | 说明 | 获取方式 |
|------|------|----------|
| `clientid` | 固定值 `746064c451c98f8675435e6e3c205f2f` | 硬编码在应用中，作为 HTTP 请求头 |
| `<session_token>` | 会话令牌 | `/sign-in` 返回的 `token` 字段 |
| `appBundleId` | 固定值 `com.macpaw.CleanMyMac5` | 应用 Bundle Identifier |
| `<customerProductPlanId>` | 用户的产品计划 ID（UUID） | `/customer/product-plan` 返回 |
| `<hardwareUuid>` | 设备 IOPlatformUUID | `ioreg -rd1 -c IOPlatformExpertDevice` |
| `<resetToken>` | 密码重置令牌 | `/recovery-password/send-email` 返回 |
| `<claimToken>` | 账户认领令牌 | `/claim-account/send-email` 返回 |

---

## 一、OAuth 认证服务 (`oauth.macpaw.com`)

### 1. 检查邮箱状态 — `POST /email/check`

```bash
curl -X POST 'https://oauth.macpaw.com/api/v2/public/email/check' \
  -H 'Content-Type: application/json' \
  -H 'clientid: 746064c451c98f8675435e6e3c205f2f' \
  -H 'User-Agent: cmm-main/5.5.6 (site/50506.0.2607101255; macOS 15.7.7; arm64)' \
  -d '{
    "email": "user@example.com"
  }'
```

**实测返回** — 已注册邮箱（`200 OK`）：

```json
{
    "exist": true,
    "completed": true,
    "timeFromCreation": 5884
}
```

**实测返回** — 未注册邮箱（`200 OK`）：

```json
{
    "exist": false,
    "completed": false,
    "timeFromCreation": null
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `exist` | boolean | 邮箱是否已注册 |
| `completed` | boolean | 账户注册是否完成（`false` 时需走 claim-account 流程） |
| `timeFromCreation` | int/null | 账户创建至今的秒数 |

---

### 2. 登录 — `POST /sign-in`

```bash
curl -X POST 'https://oauth.macpaw.com/api/v2/public/sign-in' \
  -H 'Content-Type: application/json' \
  -H 'clientid: 746064c451c98f8675435e6e3c205f2f' \
  -H 'User-Agent: cmm-main/5.5.6 (site/50506.0.2607101255; macOS 15.7.7; arm64)' \
  -d '{
    "email": "user@example.com",
    "password": "your_password"
  }'
```

**实测返回** — 登录成功（`200 OK`）：

```json
{
    "token": "KPCeG5lTZFbJcVrd4gP8Q1JgcZX4VVZYJ20knClAcpk"
}
```

**实测返回** — 密码错误（`401`）：

```json
{
    "code": "401",
    "message": "Http Unauthorized",
    "errors": [{"code": "password.invalid"}],
    "params": null
}
```

**实测返回** — 邮箱不存在（`401`）：

```json
{
    "code": "401",
    "message": "Http Unauthorized",
    "errors": [{"code": "customer.notFound"}],
    "params": null
}
```

> 返回的 `token` 即 `session_token`，后续所有鉴权接口通过 `Authorization: Bearer <token>` 头携带。每次登录生成新 token。

---

### 3. 注册 — `POST /sign-up`

```bash
curl -X POST 'https://oauth.macpaw.com/api/v2/public/sign-up' \
  -H 'Content-Type: application/json' \
  -H 'clientid: 746064c451c98f8675435e6e3c205f2f' \
  -H 'User-Agent: cmm-main/5.5.6 (site/50506.0.2607101255; macOS 15.7.7; arm64)' \
  -d '{
    "email": "user@example.com",
    "password": "your_password",
    "name": "Your Name",
    "newsAndOffersSubscription": false
  }'
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `email` | string | ✅ | 邮箱地址 |
| `password` | string | ✅ | 密码 |
| `name` | string | ❌ | 用户名 |
| `newsAndOffersSubscription` | boolean | ✅ | 是否订阅营销邮件 |

**实测返回** — 邮箱已存在（`422`）：

```json
{
    "code": "422",
    "message": "Http Exception",
    "errors": [{"code": "customer.alreadyExists"}],
    "params": {"customerId": "805d7485-9219-4d1d-aaa2-d130490342e2"}
}
```

---

### 4. 验证 Token — `POST /validate/token`

```bash
curl -X POST 'https://oauth.macpaw.com/api/v2/public/validate/token' \
  -H 'Content-Type: application/json' \
  -H 'clientid: 746064c451c98f8675435e6e3c205f2f' \
  -H 'Authorization: Bearer <session_token>' \
  -H 'User-Agent: cmm-main/5.5.6 (site/50506.0.2607101255; macOS 15.7.7; arm64)'
```

> Token 通过 `Authorization` 头传递，不需要 JSON body。

**实测返回** — Token 有效：`204 No Content`（无返回体）

**实测返回** — Token 无效（`401`）：

```json
{
    "code": "401",
    "message": "Http Unauthorized",
    "errors": [{"code": "customer.session.notFound"}],
    "params": null
}
```

---

### 5. 获取用户资料 — `GET /customer/profile`

```bash
curl -X GET 'https://oauth.macpaw.com/api/v2/public/customer/profile' \
  -H 'Content-Type: application/json' \
  -H 'clientid: 746064c451c98f8675435e6e3c205f2f' \
  -H 'Authorization: Bearer <session_token>' \
  -H 'User-Agent: cmm-main/5.5.6 (site/50506.0.2607101255; macOS 15.7.7; arm64)'
```

**实测返回**（`200 OK`）：

```json
{
    "id": "805d7485-9219-4d1d-aaa2-d130490342e2",
    "email": "qiansiqiu1996@gmail.com",
    "emailConfirmed": false,
    "name": null,
    "lastUpdatePassword": 1783779272,
    "language": "zh",
    "roles": ["ROLE_USER"]
}
```

| 字段 | 类型 | 说明 |
|------|------|------|
| `id` | string (UUID) | 客户唯一 ID |
| `email` | string | 注册邮箱 |
| `emailConfirmed` | boolean | 邮箱是否已验证 |
| `name` | string/null | 用户名 |
| `lastUpdatePassword` | int | 最后修改密码的 Unix 时间戳 |
| `language` | string | 语言偏好 |
| `roles` | string[] | 用户角色列表 |

---

### 6. 退出登录 — `POST /sign-out`

```bash
curl -X POST 'https://oauth.macpaw.com/api/v2/public/sign-out' \
  -H 'Content-Type: application/json' \
  -H 'clientid: 746064c451c98f8675435e6e3c205f2f' \
  -H 'Authorization: Bearer <session_token>' \
  -H 'User-Agent: cmm-main/5.5.6 (site/50506.0.2607101255; macOS 15.7.7; arm64)'
```

**实测返回**：`204 No Content`（成功退出，Token 立即失效）

---

### 7. 找回密码 — 发送验证邮件 — `POST /recovery-password/send-email`

```bash
curl -X POST 'https://oauth.macpaw.com/api/v2/public/recovery-password/send-email' \
  -H 'Content-Type: application/json' \
  -H 'clientid: 746064c451c98f8675435e6e3c205f2f' \
  -H 'User-Agent: cmm-main/5.5.6 (site/50506.0.2607101255; macOS 15.7.7; arm64)' \
  -d '{
    "email": "user@example.com"
  }'
```

**实测返回**（`200 OK`）：

```json
{
    "resetToken": "4e62b37cff5524973d8420c459e13a02b096a56c0118e8bc2a131531e860b092"
}
```

> 会向邮箱发送 6 位 PIN 码。返回的 `resetToken` 在后续验证和修改密码步骤中使用。

---

### 8. 找回密码 — 验证 PIN 码 — `POST /recovery-password/validate-pincode`

```bash
curl -X POST 'https://oauth.macpaw.com/api/v2/public/recovery-password/validate-pincode' \
  -H 'Content-Type: application/json' \
  -H 'clientid: 746064c451c98f8675435e6e3c205f2f' \
  -H 'User-Agent: cmm-main/5.5.6 (site/50506.0.2607101255; macOS 15.7.7; arm64)' \
  -d '{
    "resetToken": "<resetToken>",
    "pinCode": "123456"
  }'
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `resetToken` | string | ✅ | 第 7 步返回的令牌 |
| `pinCode` | string | ✅ | 邮件中收到的 6 位 PIN 码 |

---

### 9. 找回密码 — 设置新密码 — `POST /recovery-password/change-password`

```bash
curl -X POST 'https://oauth.macpaw.com/api/v2/public/recovery-password/change-password' \
  -H 'Content-Type: application/json' \
  -H 'clientid: 746064c451c98f8675435e6e3c205f2f' \
  -H 'User-Agent: cmm-main/5.5.6 (site/50506.0.2607101255; macOS 15.7.7; arm64)' \
  -d '{
    "resetToken": "<resetToken>",
    "pinCode": "123456",
    "password": "new_password_here"
  }'
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `resetToken` | string | ✅ | 第 7 步返回的令牌 |
| `pinCode` | string | ✅ | 邮件中收到的 6 位 PIN 码 |
| `password` | string | ✅ | 新密码 |

---

### 10. 认领账户 — 发送验证邮件 — `POST /claim-account/send-email`

```bash
curl -X POST 'https://oauth.macpaw.com/api/v2/public/claim-account/send-email' \
  -H 'Content-Type: application/json' \
  -H 'clientid: 746064c451c98f8675435e6e3c205f2f' \
  -H 'User-Agent: cmm-main/5.5.6 (site/50506.0.2607101255; macOS 15.7.7; arm64)' \
  -d '{
    "email": "user@example.com"
  }'
```

**实测返回** — 成功（`200 OK`）：

```json
{
    "claimToken": "4e62b37cff5524973d8420c459e13a02b096a56c0118e8bc2a131531e860b092"
}
```

**实测返回** — 邮箱不存在或已完成注册（`400`）：

```json
{
    "code": "400",
    "message": "Validation Failed",
    "errors": [{"code": "claimAccountSendPinCodeRequest.email.notFound", "path": "email"}],
    "params": null
}
```

> 仅用于 `email/check` 返回 `exist: true, completed: false` 的账户。

---

### 11. 认领账户 — 验证 PIN 码 — `POST /claim-account/validate-pincode`

```bash
curl -X POST 'https://oauth.macpaw.com/api/v2/public/claim-account/validate-pincode' \
  -H 'Content-Type: application/json' \
  -H 'clientid: 746064c451c98f8675435e6e3c205f2f' \
  -H 'User-Agent: cmm-main/5.5.6 (site/50506.0.2607101255; macOS 15.7.7; arm64)' \
  -d '{
    "claimToken": "<claimToken>",
    "pinCode": "123456"
  }'
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `claimToken` | string | ✅ | 第 10 步返回的令牌 |
| `pinCode` | string | ✅ | 邮件中收到的 6 位 PIN 码 |

---

### 12. 认领账户 — 完成注册 — `POST /claim-account/sign-up`

```bash
curl -X POST 'https://oauth.macpaw.com/api/v2/public/claim-account/sign-up' \
  -H 'Content-Type: application/json' \
  -H 'clientid: 746064c451c98f8675435e6e3c205f2f' \
  -H 'User-Agent: cmm-main/5.5.6 (site/50506.0.2607101255; macOS 15.7.7; arm64)' \
  -d '{
    "claimToken": "<claimToken>",
    "pinCode": "123456",
    "password": "your_password",
    "newsAndOffersSubscription": false
  }'
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `claimToken` | string | ✅ | 第 10 步返回的令牌 |
| `pinCode` | string | ✅ | 邮件中收到的 6 位 PIN 码 |
| `password` | string | ✅ | 账户密码 |
| `newsAndOffersSubscription` | boolean | ✅ | 是否订阅营销邮件 |

---

## 二、激活服务 (`activation.macpaw.com`)

### 13. 获取产品可用计划 — `GET /customer/product-plan`

```bash
curl -X GET 'https://activation.macpaw.com/api/v2/public/customer/product-plan?osLocale=zh-Hans&appBundleId=com.macpaw.CleanMyMac5' \
  -H 'Content-Type: application/json' \
  -H 'clientid: 746064c451c98f8675435e6e3c205f2f' \
  -H 'Authorization: Bearer <session_token>' \
  -H 'language: zh' \
  -H 'User-Agent: cmm-main/5.5.6 (site/50506.0.2607101255; macOS 15.7.7; arm64)'
```

| Query 参数 | 类型 | 必填 | 说明 |
|------------|------|------|------|
| `osLocale` | string | ❌ | 系统语言区域，如 `zh-Hans` |
| `appBundleId` | string | ✅ | 固定值 `com.macpaw.CleanMyMac5` |

**实测返回** — 无购买计划（`200 OK`）：

```json
{
    "data": []
}
```

> 有有效订阅时，`data` 数组内包含计划对象（含 `customerProductPlanId`、类型、座位数、状态等）。该 ID 用于后续激活座位。

---

### 14. 激活座位（新增设备） — `POST /activation/seat`

```bash
curl -X POST 'https://activation.macpaw.com/api/v2/public/activation/seat' \
  -H 'Content-Type: application/json' \
  -H 'clientid: 746064c451c98f8675435e6e3c205f2f' \
  -H 'Authorization: Bearer <session_token>' \
  -H 'User-Agent: cmm-main/5.5.6 (site/50506.0.2607101255; macOS 15.7.7; arm64)' \
  -d '{
    "customerProductPlanId": "<计划ID>",
    "hardwareUuid": "057F35F6-8018-5085-A1C6-63CD111E8EFD",
    "productBundleId": "com.macpaw.CleanMyMac5",
    "machineModel": "MacBookPro18,1",
    "machineName": "My-MacBook-Pro",
    "macAddress": "AA:BB:CC:DD:EE:FF"
  }'
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `customerProductPlanId` | string (UUID) | ✅ | 从第 13 步获取的计划 ID |
| `hardwareUuid` | string (UUID) | ✅ | 设备 `IOPlatformUUID` |
| `productBundleId` | string | ✅ | 固定值 `com.macpaw.CleanMyMac5` |
| `machineModel` | string | ✅ | 机型标识，如 `MacBookPro18,1` |
| `machineName` | string | ✅ | 设备名称，如 `My-MacBook-Pro` |
| `macAddress` | string | ✅ | MAC 地址，格式 `AA:BB:CC:DD:EE:FF` |

**实测返回** — 缺少必填字段（`400`）：

```json
{
    "code": "400",
    "message": "Validation Failed",
    "errors": [
        {"code": "activateCustomerProductPlanSeatRequest.customerProductPlanId.notBlank", "path": "customerProductPlanId"},
        {"code": "activateCustomerProductPlanSeatRequest.hardwareUuid.notBlank", "path": "hardwareUuid"},
        {"code": "activateCustomerProductPlanSeatRequest.productBundleId.notBlank", "path": "productBundleId"},
        {"code": "activateCustomerProductPlanSeatRequest.machineModel.notBlank", "path": "machineModel"},
        {"code": "activateCustomerProductPlanSeatRequest.machineName.notBlank", "path": "machineName"},
        {"code": "activateCustomerProductPlanSeatRequest.macAddress.notBlank", "path": "macAddress"}
    ],
    "params": null
}
```

**实测返回** — 计划 ID 无效（`400`）：

```json
{
    "code": "400",
    "message": "Validation Failed",
    "errors": [
        {"code": "activateCustomerProductPlanSeatRequest.customerProductPlanId.invalid", "path": "customerProductPlanId"}
    ],
    "params": null
}
```

> 成功时返回签名的 License Payload，包含 RSA 签名的许可证数据。

---

### 15. 替换座位（踢掉旧设备） — `PATCH /activation/seat`

```bash
curl -X PATCH 'https://activation.macpaw.com/api/v2/public/activation/seat' \
  -H 'Content-Type: application/json' \
  -H 'clientid: 746064c451c98f8675435e6e3c205f2f' \
  -H 'Authorization: Bearer <session_token>' \
  -H 'User-Agent: cmm-main/5.5.6 (site/50506.0.2607101255; macOS 15.7.7; arm64)' \
  -d '{
    "customerProductPlanId": "<计划ID>",
    "seatToReplace": "<要替换的座位ID>",
    "hardwareUuid": "057F35F6-8018-5085-A1C6-63CD111E8EFD",
    "productBundleId": "com.macpaw.CleanMyMac5",
    "machineModel": "MacBookPro18,1",
    "machineName": "My-MacBook-Pro",
    "macAddress": "AA:BB:CC:DD:EE:FF"
  }'
```

| 字段 | 类型 | 必填 | 说明 |
|------|------|------|------|
| `customerProductPlanId` | string (UUID) | ✅ | 计划 ID |
| `seatToReplace` | string (UUID) | ✅ | 要替换的旧座位 ID |
| `hardwareUuid` | string (UUID) | ✅ | 新设备 `IOPlatformUUID` |
| `productBundleId` | string | ✅ | 固定值 `com.macpaw.CleanMyMac5` |
| `machineModel` | string | ✅ | 新设备机型标识 |
| `machineName` | string | ✅ | 新设备名称 |
| `macAddress` | string | ✅ | 新设备 MAC 地址 |

**实测返回** — 缺少必填字段（`400`）：

```json
{
    "code": "400",
    "message": "Validation Failed",
    "errors": [
        {"code": "replaceCustomerProductPlanSeatRequest.customerProductPlanId.notBlank", "path": "customerProductPlanId"},
        {"code": "replaceCustomerProductPlanSeatRequest.seatToReplace.notBlank", "path": "seatToReplace"},
        {"code": "replaceCustomerProductPlanSeatRequest.hardwareUuid.notBlank", "path": "hardwareUuid"},
        {"code": "replaceCustomerProductPlanSeatRequest.productBundleId.notBlank", "path": "productBundleId"},
        {"code": "replaceCustomerProductPlanSeatRequest.machineModel.notBlank", "path": "machineModel"},
        {"code": "replaceCustomerProductPlanSeatRequest.machineName.notBlank", "path": "machineName"},
        {"code": "replaceCustomerProductPlanSeatRequest.macAddress.notBlank", "path": "macAddress"}
    ],
    "params": null
}
```

> `/activation/seat` 端点仅允许 `POST`（新增）和 `PATCH`（替换）方法，不支持 `GET` 和 `DELETE`。

---

### 16. 验证兑换码类型 — `POST /redeem-code/get-type`

```bash
curl -X POST 'https://activation.macpaw.com/api/v2/public/redeem-code/get-type' \
  -H 'Content-Type: application/json' \
  -H 'clientid: 746064c451c98f8675435e6e3c205f2f' \
  -H 'Authorization: Bearer <session_token>' \
  -H 'User-Agent: cmm-main/5.5.6 (site/50506.0.2607101255; macOS 15.7.7; arm64)' \
  -d '{
    "redeemCode": "XXXX-XXXX-XXXX-XXXX"
  }'
```

> 注意字段名为 **`redeemCode`**（camelCase），不是 `redeem_code`。

**实测返回** — 兑换码为空（`400`）：

```json
{
    "code": "400",
    "message": "Validation Failed",
    "errors": [{"code": "redeemCodeTypeRequest.redeemCode.notBlank", "path": "redeemCode"}],
    "params": null
}
```

**实测返回** — 兑换码格式无效（`400`）：

```json
{
    "code": "400",
    "message": "Validation Failed",
    "errors": [{"code": "redeemCodeTypeRequest.redeemCode.invalid", "path": "redeemCode"}],
    "params": null
}
```

---

### 17. 获取同伴应用计划 — `POST /activation/companion-app`

```bash
curl -X POST 'https://activation.macpaw.com/api/v2/public/activation/companion-app' \
  -H 'Content-Type: application/json' \
  -H 'clientid: 746064c451c98f8675435e6e3c205f2f' \
  -H 'Authorization: Bearer <session_token>' \
  -H 'User-Agent: cmm-main/5.5.6 (site/50506.0.2607101255; macOS 15.7.7; arm64)' \
  -d '{
    "appBundleId": "com.macpaw.CleanMyMac5"
  }'
```

> 查询附带的伴侣应用（如 CleanMyPhone）的激活资格。此接口可能需要有效的已激活计划才能正常返回，无计划时测试返回 `404`。

---

## 三、额外发现的接口

### 18. GrowthBook 特性开关 — `GET /api/features/<sdk-key>`

```bash
curl -X GET 'https://ft.macpaw.com/api/features/sdk-R8H6ciJOO53TBr' \
  -H 'User-Agent: CleanMyMac_5/50506.0.2607101255 CFNetwork/3826.600.41.1.1 Darwin/24.6.0' \
  -H 'Cache-Control: max-age=3600'
```

无需鉴权。

**实测返回**（`200 OK`）：

```json
{
    "dateUpdated": "2026-07-10T12:41:13.663Z",
    "features": {
        "CMY-3606": { "defaultValue": {"applyStrictValidation": false, "useMacPawReceiptValidator": false}, "rules": [...] },
        "TBT-96": { ... },
        "CMY-3619": { ... },
        "...": "共 36 个特性开关"
    }
}
```

> 包含所有远程 A/B 测试和功能开关配置。SDK Key `sdk-R8H6ciJOO53TBr` 在 URL 路径中传递。

---

### 19. 遥测/分析上报 — `POST /actions`

```bash
curl -X POST 'https://api-lytics.macpaw.com/actions' \
  -H 'Content-Type: application/json' \
  -H 'User-Agent: cmm-main/5.5.6 (site/50506.0.2607101255; macOS 15.7.7; arm64)' \
  -d '{
    "aid": "50506.0.2607101255",
    "an": "CleanMyMac 5 Site",
    "av": "5.5.6",
    "cd": "Smart Care",
    "cid": "<AnalyticsIdentifier UUID>",
    "ds": "app",
    "ea": "Open",
    "ec": "Smart Care",
    "t": "event",
    "uid": "",
    "ul": "zh-Hans-CN",
    "z": "60083135"
  }'
```

**实测返回**：`204 No Content`（数据已接收）

| 字段 | 说明 |
|------|------|
| `aid` | Application ID（Build 号） |
| `an` | Application Name |
| `av` | Application Version |
| `cd` | Content Description（模块名） |
| `cid` | Client ID（分析标识，存储在 `AnalyticsIdentifier`） |
| `ds` | Data Source |
| `ea` | Event Action |
| `ec` | Event Category |
| `t` | Hit Type |
| `uid` | User ID（未登录时为空） |
| `ul` | User Language |
| `z` | Cache Buster（随机数） |

---

### 20. 批量数据上报 — `POST /insert`

```bash
curl -X POST 'https://api-lytics.macpaw.com/insert' \
  -H 'Content-Type: application/json' \
  -H 'User-Agent: cmm-main/5.5.6 (site/50506.0.2607101255; macOS 15.7.7; arm64)' \
  -d '{...}'
```

> 批量上报分析数据。与 `/actions` 端点结构类似但支持批量提交。

---

## 四、典型调用流程

```
1. POST  /email/check                  → 检查邮箱: {exist, completed}
        ↓
2. POST  /sign-in                      → 登录: {token}
        ↓
3. GET   /customer/profile             → 获取用户信息: {id, email, roles}
        ↓
4. GET   /customer/product-plan        → 获取计划: {data: [{customerProductPlanId, ...}]}
        ↓
5. POST  /activation/seat              → 激活座位 (需 6 个设备信息字段)
        ↓
6. 服务器返回签名的 License Payload
        ↓
7. 客户端 RSA 验证许可证签名（SHA-256 + SecVerifyTransformCreate）
        ↓
8. 持久化到本地加密存储（MPASharedStorage / Keychain）
```

**密码重置流程：**

```
1. POST /recovery-password/send-email   → {resetToken} + 邮件发送 PIN
2. POST /recovery-password/validate-pincode → 验证 {resetToken, pinCode}
3. POST /recovery-password/change-password  → 设置 {resetToken, pinCode, password}
```

**账户认领流程（未完成注册的账户）：**

```
1. POST /claim-account/send-email       → {claimToken} + 邮件发送 PIN
2. POST /claim-account/validate-pincode → 验证 {claimToken, pinCode}
3. POST /claim-account/sign-up          → 完成 {claimToken, pinCode, password, newsAndOffersSubscription}
```

---

## 五、CORS 允许的请求头

```
Authorization, clientId, language, captchaToken, svn,
currentCustomerId, remoteAddress, baggage, sentry-trace
```

---

## 六、应用信息

| 属性 | 值 |
|------|-----|
| Bundle Identifier | `com.macpaw.CleanMyMac5` |
| 版本号 | `5.5.6` |
| Build | `50506.0.2607101255` |
| clientId | `746064c451c98f8675435e6e3c205f2f` |
| GrowthBook SDK Key | `sdk-R8H6ciJOO53TBr` |
| Sentry Public Key | `2e6b73e103b7454b902ba46884966bfd` |
| Sentry DSN Host | `o36975.ingest.sentry.io` |
| User-Agent (主应用) | `cmm-main/5.5.6 (site/50506.0.2607101255; macOS 15.7.7; arm64)` |
| User-Agent (网络层) | `CleanMyMac_5/50506.0.2607101255 CFNetwork/3826.600.41.1.1 Darwin/24.6.0` |

---

## 七、安全机制

- **传输加密**：所有 API 均通过 Cloudflare CDN（`cf-ray` 头）并使用 HTTPS
- **客户端标识**：通过 `clientid` 请求头验证合法客户端
- **许可证签名**：服务器使用 RSA 私钥签名 License Payload，客户端使用嵌入的 RSA 公钥验证（SHA-256 + `SecVerifyTransformCreate`）
- **本地存储加密**：`MPASharedStorage` 使用 AES 加密，密钥由 `IOPlatformUUID` 派生
- **Keychain 存储**：`session_token` 存储在 macOS Keychain（`MPAKeychainStorage`）
- **设备绑定**：座位激活需 `hardwareUuid`（IOPlatformUUID）、`machineModel`、`machineName`、`macAddress` 四项设备指纹
- **离线容忍**：已激活许可证有离线宽限期，但无纯离线激活路径
- **验证码防护**：CORS 头中包含 `captchaToken`，高频操作可能触发人机验证

---

## 八、错误响应格式

所有错误均返回统一结构：

```json
{
    "code": "<HTTP状态码>",
    "message": "<错误描述>",
    "errors": [
        {
            "code": "<请求名>.<字段名>.<规则>",
            "path": "<字段名>"
        }
    ],
    "params": null | { ... }
}
```

### 常见错误码速查

| HTTP 状态 | 错误码 | 说明 |
|-----------|--------|------|
| `400` | `*.clientId.notNull` | 缺少 `clientid` 请求头 |
| `400` | `*.clientId.invalid` | `clientid` 值不正确 |
| `400` | `*.notBlank` | 必填字段为空 |
| `400` | `*.invalid` | 字段值格式不正确 |
| `401` | `clientId.required` | sign-in 接口缺少 clientid |
| `401` | `password.invalid` | 密码错误 |
| `401` | `customer.notFound` | 用户不存在 |
| `401` | `customer.session.notFound` | Token 无效或已过期 |
| `422` | `customer.alreadyExists` | 注册时邮箱已存在 |
| `404` | `No route found for ...` | 接口路径或 HTTP 方法不正确 |
| `405` | `Method Not Allowed (Allow: ...)` | HTTP 方法不允许，响应中列出允许的方法 |

### 各端点允许的 HTTP 方法

| 端点 | 允许的方法 |
|------|-----------|
| `/email/check` | POST |
| `/sign-in` | POST |
| `/sign-up` | POST |
| `/validate/token` | POST |
| `/customer/profile` | **GET** |
| `/sign-out` | POST |
| `/recovery-password/*` | POST |
| `/claim-account/*` | POST |
| `/customer/product-plan` | **GET** |
| `/activation/seat` | **POST, PATCH** |
| `/redeem-code/get-type` | POST |
| `/activation/companion-app` | POST |
