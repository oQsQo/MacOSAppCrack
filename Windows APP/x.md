# Windows App for macOS：Command / Control 交换补丁交接文档

> 用途：交给后续 agent，在 Windows App 升级后重新制作补丁，或在另一台 Mac/另一份 Windows App 上复现。
>
> 最后核对日期：2026-08-20（Asia/Shanghai）

## 1. 目标和约定

仅改变 Windows App 的远程输入，使左右两侧分别交换：

| macOS 实际按键 | 希望远端 Windows 收到 |
|---|---|
| 左 Command | 左 Control |
| 右 Command | 右 Control |
| 左 Control | 左 Windows |
| 右 Control | 右 Windows |

不安装 Karabiner-Elements 等第三方键盘工具，也不在 macOS 全局交换按键。

本文按新的顺序命名：

1. **方案一：修改最终 Scancode 表**——本机当前实际采用的方案；原讨论中的“方案二”。
2. **方案二：修改物理修饰键映射**——语义更精确；原讨论中的“方案一”。

两套补丁是替代关系，**不要同时应用**。所有旧偏移仅适用于文中指定的二进制；软件升级后必须重新定位，不能盲打补丁。

## 2. 结论先行

| 项目 | 方案一：最终 Scancode 表 | 方案二：物理修饰键映射 |
|---|---|---|
| 修改层级 | 输出 RDP 扫描码的最后一层 | `MacKeyboardDriver` 识别物理修饰键的前段 |
| 修改内容 | 两个架构各交换4个64位表项 | 两个架构各修改4条立即数指令 |
| 升级后重新定位 | 较容易，优先通过 `Scancode.rawValue` 符号定位 | 稍难，优先通过 `MacKeyboardDriver` 初始化函数定位 |
| 普通组合键 | 能交换 | 能交换 |
| 单独按/松修饰键 | 能交换 | 能交换 |
| 修饰键配合鼠标 | 预期能交换，仍须实测 | 能交换，语义更直接 |
| App/XML 合成的按键 | 也会交换 | 不交换 |
| App 菜单的 Ctrl+Alt+Del | 会被破坏成 Win+Alt+Del | 保持 Ctrl+Alt+Del |
| 推荐用途 | 最容易复现的 data-only 补丁、快速验证 | 追求正确语义的长期版本 |

Windows App 内部路径可抽象为：

```text
macOS NSEvent
  → 物理修饰键识别
  → 快捷键/XML transformation
  → 内部 Scancode 枚举
  → Scancode.rawValue 查表
  → RDP 扫描码
```

方案一改最后一步，因此所有来源都会交换；方案二改第一步，因此只交换真实物理修饰键。

## 3. 当前机器和文件状态

### 3.1 原版信息

```text
产品：Windows App for macOS
版本：11.3.9
Build：3064
Bundle ID：com.microsoft.rdc.macos
架构：x86_64 + arm64
原始主程序 SHA-256：
b7f1d42dbe13a532a708f77ef1220aac09e90e95a86c2681ce613efa490525f8
微软 Team ID：UBF8T346G9
```

完整、未修改、微软签名仍有效的备份位于：

```text
/Applications/Windows App 11.3.9 (3064) Original.app
```

原版主程序：

```text
/Applications/Windows App 11.3.9 (3064) Original.app/Contents/MacOS/Windows App
```

原始 Universal/Fat 布局：

```text
x86_64 slice offset = 0x00004000  (16384)
x86_64 slice size   = 60935664

arm64 slice offset  = 0x03A24000  (60964864)
arm64 slice size    = 58433424
```

### 3.2 当前补丁版

当前 `/Applications/Windows App.app` 已应用本文的**方案一（最终 Scancode 表）**：

```text
/Applications/Windows App.app
主程序 SHA-256：
056a7d41123c0b7200366585aaf0e02be49c9607cb2f6255f5d789423b13926d
签名：ad-hoc
Team ID：无
主 App entitlement：无
Hardened Runtime：已去除
```

已验证结果：

- x86_64、arm64 共8个表项正确。
- `codesign --verify --deep --strict` 通过。
- 实际启动成功，进程持续运行通过基础冒烟测试。
- 没有自动修改“首选项 → 键盘”的开关。

重签名后 Fat 布局发生了变化：

```text
x86_64 slice offset = 0x00004000
x86_64 slice size   = 60931488

arm64 slice offset  = 0x03A20000
arm64 slice size    = 58429248
```

这说明：**签名前后的整文件偏移可能不同。重新定位和验证必须以架构切片内偏移、虚拟地址和段映射为准。**

## 4. 共同安全流程

后续 agent 无论选哪个方案，都应按下面顺序工作。

### 4.1 不直接覆盖唯一原版

1. 确认 Windows App 已退出；不要中断正在进行的 RDP 会话。
2. 记录版本、Build、原始 SHA-256、签名和 Fat 布局。
3. 保留完整 `.app` 备份，而不只是备份主程序。
4. 在 APFS 克隆/工作副本上完成补丁、签名和测试。
5. 工作副本成功启动后，才切换正式路径。

建议的只读采集命令：

```bash
APP='/Applications/Windows App.app'
BIN="$APP/Contents/MacOS/Windows App"

/usr/libexec/PlistBuddy -c 'Print :CFBundleShortVersionString' "$APP/Contents/Info.plist"
/usr/libexec/PlistBuddy -c 'Print :CFBundleVersion' "$APP/Contents/Info.plist"
shasum -a 256 "$BIN"
file "$BIN"
lipo -detailed_info "$BIN"
codesign -dvv "$APP"
codesign --verify --deep --strict --verbose=2 "$APP"
```

在 APFS 上可以先制作工作副本：

```bash
cp -cR '/Applications/Windows App.app' '/Applications/Windows App Patch Working.app'
```

复制后必须比较主程序 SHA-256，并在补丁前验证工作副本仍满足微软原签名。

### 4.2 文件偏移计算

不要默认所有版本的 `__TEXT` 都是 `fileoff = 0`。通用公式是：

```text
切片内文件偏移
  = 所在 Mach-O segment.fileoff
  + (目标虚拟地址 - segment.vmaddr)

Universal/Fat 整文件偏移
  = 当前架构 slice offset
  + 切片内文件偏移
```

使用 `otool -l -arch arm64` / `otool -l -arch x86_64` 核对段映射。11.3.9 的相关目标都在 `__TEXT`，且该段的 `fileoff = 0`，所以本版本恰好可以用 `VM 地址 - 0x100000000` 得到切片内偏移；升级后仍要重新确认。

### 4.3 补丁程序必须具备的保护

不要用不校验的 `dd`/十六进制编辑器盲写。补丁程序至少要：

1. 核对完整原始 SHA-256，或明确允许的新版本哈希。
2. 在任何写操作前，校验所有目标位置的旧字节。
3. 所有前置条件通过后才开始写入。
4. 原位写入或安全替换，并执行 `fsync`。
5. 写后逐表项/逐指令复核。
6. 与原版比较 byte diff，确认变化只出现在预期位置；重签名要在 diff 检查之后进行，因为签名会改变大量签名区字节，甚至改变 Fat 切片布局。

## 5. 方案一：修改最终 Scancode 表

### 5.1 原理

`Client.Scancode` 是 Windows App 的内部 Scancode 枚举。`rawValue` getter 依据枚举序号，从64位 `UInt` 表中取最终 RDP 扫描码。

相关内部枚举序号和原始输出：

| 内部枚举序号 | 内部含义 | 原始 RDP Scancode | 小端64位字节 |
|---:|---|---:|---|
| `0x35` | Right Command | `0xE05C`，Right Windows | `5C E0 00 00 00 00 00 00` |
| `0x36` | Left Command | `0xE05B`，Left Windows | `5B E0 00 00 00 00 00 00` |
| `0x3A` | Left Control | `0x001D` | `1D 00 00 00 00 00 00 00` |
| `0x3C` | Right Control | `0xE01D` | `1D E0 00 00 00 00 00 00` |

交换后的目标：

| 内部枚举 | 新 RDP Scancode | 新字节 |
|---|---:|---|
| Right Command | Right Control `0xE01D` | `1D E0 00 00 00 00 00 00` |
| Left Command | Left Control `0x001D` | `1D 00 00 00 00 00 00 00` |
| Left Control | Left Windows `0xE05B` | `5B E0 00 00 00 00 00 00` |
| Right Control | Right Windows `0xE05C` | `5C E0 00 00 00 00 00 00` |

### 5.2 11.3.9（3064）精确补丁

以下整文件偏移只适用于原始 SHA-256 为 `b7f1...25f8`、尚未重签名的原版。

#### x86_64

表基址：

```text
VM address        = 0x101A65628
slice-relative    = 0x01A65628
original slice    = 0x00004000
```

| 项目 | VM 地址 | 切片内偏移 | 原版整文件偏移 | 原字节 → 新字节 |
|---|---:|---:|---:|---|
| Right Command | `0x101A657D0` | `0x1A657D0` | `0x1A697D0` | `5C E0 00 00 00 00 00 00` → `1D E0 00 00 00 00 00 00` |
| Left Command | `0x101A657D8` | `0x1A657D8` | `0x1A697D8` | `5B E0 00 00 00 00 00 00` → `1D 00 00 00 00 00 00 00` |
| Left Control | `0x101A657F8` | `0x1A657F8` | `0x1A697F8` | `1D 00 00 00 00 00 00 00` → `5B E0 00 00 00 00 00 00` |
| Right Control | `0x101A65808` | `0x1A65808` | `0x1A69808` | `1D E0 00 00 00 00 00 00` → `5C E0 00 00 00 00 00 00` |

#### arm64

表基址：

```text
VM address        = 0x1018310B8
slice-relative    = 0x018310B8
original slice    = 0x03A24000
```

| 项目 | VM 地址 | 切片内偏移 | 原版整文件偏移 | 原字节 → 新字节 |
|---|---:|---:|---:|---|
| Right Command | `0x101831260` | `0x1831260` | `0x5255260` | `5C E0 00 00 00 00 00 00` → `1D E0 00 00 00 00 00 00` |
| Left Command | `0x101831268` | `0x1831268` | `0x5255268` | `5B E0 00 00 00 00 00 00` → `1D 00 00 00 00 00 00 00` |
| Left Control | `0x101831288` | `0x1831288` | `0x5255288` | `1D 00 00 00 00 00 00 00` → `5B E0 00 00 00 00 00 00` |
| Right Control | `0x101831298` | `0x1831298` | `0x5255298` | `1D E0 00 00 00 00 00 00` → `5C E0 00 00 00 00 00 00` |

本版本补丁前后，在签名区之外实际只有12个字节改变，而不是16个；原因是有些64位表项交换时第二个字节同为 `E0`，无需变化。

### 5.3 升级后如何重新定位

优先查找导出 Swift 符号：

```bash
nm -arch arm64 -nm "$BIN" | rg 'ScancodeO8rawValueSuvg'
nm -arch x86_64 -nm "$BIN" | rg 'ScancodeO8rawValueSuvg'
```

11.3.9 中完整符号是：

```text
_$s6Client8ScancodeO8rawValueSuvg
```

本版本位置：

```text
arm64  getter = 0x10002E61C
x86_64 getter = 0x100032F50
```

反汇编 getter：

```bash
lldb -b \
  -o "target create --arch arm64 '$BIN'" \
  -o 'disassemble --start-address <arm64-getter-address> --count 10'

lldb -b \
  -o "target create --arch x86_64 '$BIN'" \
  -o 'disassemble --start-address <x86-getter-address> --count 12'
```

11.3.9 的 arm64 形态：

```asm
sxtb x8, w0
adrp x9, ...
add  x9, x9, #...
ldr  x0, [x9, x8, lsl #3]
ret
```

`adrp + add` 得到表基址。x86_64 形态：

```asm
movsbq %dil, %rax
leaq   <table-base>(%rip), %rcx
movq   (%rcx,%rax,8), %rax
```

得到新版本表基址后，四个表项地址为：

```text
table + 0x35 * 8   # Right Command
table + 0x36 * 8   # Left Command
table + 0x3A * 8   # Left Control
table + 0x3C * 8   # Right Control
```

必须验证这四处仍依次包含 `E05C`、`E05B`、`001D`、`E01D`。如果值或枚举顺序改变，不要强行套用旧算法；应继续逆向枚举定义和调用者。

如果新版本去掉了符号：

1. 在 `__TEXT,__const` 搜索相邻的64位值和已知 Scancode 序列。
2. 找到引用该候选表的 getter；应存在按有符号8位枚举索引、步长8读取的代码。
3. 从 `keyDown(scancode:)`、`keyUp(scancode:)` 等调用路径交叉确认。
4. 至少用两个独立证据确认后再写入。

### 5.4 方案一的必知副作用

该表位于最后输出层，因此下列来源都会被交换：

- 用户物理键盘输入。
- `DefaultTransformations.xml` 或键盘布局 XML 生成的组合。
- “首选项 → 键盘”生成的 Cmd+C/Cmd+V 等 transformation。
- Windows App 菜单或内部逻辑合成的 Scancode。

典型副作用：

```text
App 内部生成 Ctrl + Alt + Delete
→ 最终表把 Control 改成 Windows
→ 远端收到 Win + Alt + Delete
```

所以 Windows App 自带的“发送 Ctrl+Alt+Del”功能预计失效。若用户依赖该功能，应改用方案二，或继续做额外的调用点修补。

## 6. 方案二：修改物理修饰键映射

### 6.1 原理

`MacKeyboardDriver` 初始化 `modifierFlagsAndScancodes`，把 macOS 的左/右修饰键标志映射为内部 Scancode 枚举：

```text
Left Command  = 0x36
Right Command = 0x35
Left Control  = 0x3A
Right Control = 0x3C
```

目标是只交换该物理映射：

```text
LeftControlKeyMask:   0x3A → 0x36
RightControlKeyMask:  0x3C → 0x35
LeftCommandKeyMask:   0x36 → 0x3A
RightCommandKeyMask:  0x35 → 0x3C
```

因此真实键盘的 Command/Control 会交换，但 App 自己生成的内部 Control 仍然是 Control；这能保留 Ctrl+Alt+Del 等程序语义。

### 6.2 11.3.9（3064）精确补丁

以下整文件偏移同样只适用于原始 SHA-256 为 `b7f1...25f8` 的未签名修改版。

#### arm64

| 物理标志 | VM 地址 | 切片内偏移 | 原版整文件偏移 | 原字节 → 新字节 |
|---|---:|---:|---:|---|
| Left Control | `0x10061C7E4` | `0x61C7E4` | `0x40407E4` | `48 07 80 52` → `C8 06 80 52` |
| Right Control | `0x10061C7F8` | `0x61C7F8` | `0x40407F8` | `88 07 80 52` → `A8 06 80 52` |
| Left Command | `0x10061C80C` | `0x61C80C` | `0x404080C` | `C8 06 80 52` → `48 07 80 52` |
| Right Command | `0x10061C820` | `0x61C820` | `0x4040820` | `A8 06 80 52` → `88 07 80 52` |

对应指令：

```asm
; before
mov w8, #0x3a
mov w8, #0x3c
mov w8, #0x36
mov w8, #0x35

; after
mov w8, #0x36
mov w8, #0x35
mov w8, #0x3a
mov w8, #0x3c
```

#### x86_64

| 物理标志 | VM 地址 | 切片内偏移 | 原版整文件偏移 | 原字节 → 新字节 |
|---|---:|---:|---:|---|
| Left Control | `0x10067E240` | `0x67E240` | `0x682240` | `41 C6 45 48 3A` → `41 C6 45 48 36` |
| Right Control | `0x10067E251` | `0x67E251` | `0x682251` | `41 C6 45 58 3C` → `41 C6 45 58 35` |
| Left Command | `0x10067E262` | `0x67E262` | `0x682262` | `41 C6 45 68 36` → `41 C6 45 68 3A` |
| Right Command | `0x10067E273` | `0x67E273` | `0x682273` | `41 C6 45 78 35` → `41 C6 45 78 3C` |

x86_64 实际只需替换每条指令的最后一个立即数字节，但补丁器最好校验完整5字节指令。

### 6.3 升级后如何重新定位

优先查找以下符号：

```bash
nm -arch arm64 -nm "$BIN" | rg 'MacKeyboardDriver.*modifierFlagsAndScancodes|MacKeyboardDriver.*layoutMappings.*transformations'
nm -arch x86_64 -nm "$BIN" | rg 'MacKeyboardDriver.*modifierFlagsAndScancodes|MacKeyboardDriver.*layoutMappings.*transformations'
```

11.3.9 中可用的关键符号包括：

```text
MacKeyboardDriver.modifierFlagsAndScancodes property initializer
_$s6Client17MacKeyboardDriverC25modifierFlagsAndScancodes...vpfi

MacKeyboardDriver.init(keyboard:layoutMappings:transformations:)
_$s6Client17MacKeyboardDriverC8keyboard14layoutMappings15transformations...tcfc
```

本版本真正写入四组映射的是构造函数：

```text
arm64  constructor = 0x10061C72C
x86_64 constructor = 0x10067E180
```

反汇编构造函数后，寻找按此顺序出现的 macOS flag accessor：

```text
LeftShiftKeyMask
RightShiftKeyMask
LeftControlKeyMask
RightControlKeyMask
LeftCommandKeyMask
RightCommandKeyMask
LeftAlternateKeyMask
RightAlternateKeyMask
```

每个 accessor 后会把一个单字节内部 Scancode 写入数组元素。必须结合 accessor 名称确认四个立即数分别属于左 Control、右 Control、左 Command、右 Command，不能只搜索裸字节 `3A 3C 36 35`。

若符号被移除，可以从以下路径反向定位：

```text
MacKeyboardDriver.flagsChanged(event:)
  → synchronizeModifiers(...)
  → 遍历 modifierFlagsAndScancodes
```

再追到数组的初始化位置。需要确认左右 Shift/Option 条目也在同一数组中，作为结构证据。

### 6.4 方案二的行为边界

方案二更接近“只交换物理按键”：

- 普通键盘组合、单独修饰键事件和修饰键配合鼠标都由物理映射处理。
- App 合成的 Ctrl+Alt+Del 不经过物理交换，能保持正常。
- XML 或首选项主动生成的内部 Scancode 不会被底层反转。

但 Windows App 自带的 Cmd+C/Cmd+V 等 transformation 仍可能形成二次处理，所以仍建议关闭全部 Mac 快捷键转换。

## 7. 重签名：最重要的坑

任何主程序字节修改都会破坏微软原始代码签名。没有微软私钥，就不能保留 `UBF8T346G9` 身份。

### 7.1 当前机器上验证失败的做法

以下做法虽然 `codesign --verify` 会显示通过，但实际启动会被 `amfid` 拒绝：

```bash
codesign --force --sign - \
  --preserve-metadata=identifier,entitlements,flags,runtime \
  '/Applications/Windows App.app'
```

原因是它保留了微软专属 entitlement，例如：

```text
com.apple.application-identifier = UBF8T346G9.com.microsoft.rdc.macos
com.apple.developer.team-identifier = UBF8T346G9
com.apple.security.application-groups = UBF8T346G9....
Microsoft OneAuth / Teams / Entra app groups
```

ad-hoc 或非微软签名无权声明这些 entitlement。实际症状：

```text
RBSRequestErrorDomain Code=5 "Launch failed"
NSPOSIXErrorDomain Code=153 "Launchd job spawn failed"
amfid: The signature on the file is invalid
```

所以**仅运行 `codesign --verify` 不足以证明应用可启动**。

### 7.2 当前机器上成功的基线做法

对工作副本的主 App 做不保留 entitlement、不保留 Hardened Runtime 的 ad-hoc 重签名：

```bash
codesign --force --sign - '/Applications/Windows App Patch Working.app'
codesign --verify --deep --strict --verbose=2 '/Applications/Windows App Patch Working.app'
```

这里没有使用 `--deep` 强制重签所有嵌套组件；原版 Framework/XPC/appex 可以继续保留各自的微软签名。`codesign` 会在签主 App 时准备并验证这些嵌套代码。

必须再做实际启动测试：

```bash
open -na '/Applications/Windows App Patch Working.app'
pgrep -x 'Windows App'
```

如果使用个人开发者证书，可以尝试制作一份明确删去微软 Team ID、App Groups、Keychain Groups 的最小 entitlement 文件，但不要伪造微软身份；必须重新做完整登录、网络、音频和 RDP 测试。

### 7.3 重签名的功能代价

当前成功启动的补丁版主 App 没有原 entitlement，因此以下能力可能异常：

- Microsoft OneAuth。
- 共享钥匙串和已保存凭据。
- Windows 365 / Azure Virtual Desktop 登录。
- Microsoft App Group 共享数据。
- 部分 XPC、粘贴板、Teams VDI 集成。
- 沙盒容器内原偏好和连接配置的访问方式。

直接 `.rdp`/普通远程桌面连接最值得优先测试。需要以上微软身份能力时，应保留并使用完整原版，而不是期待本地重签恢复微软权限。

## 8. Windows App 首选项设置

完成任一方案后，进入：

```text
Windows App → 首选项 → 键盘
```

关闭所有会把 macOS Command 快捷键转换为远端 Control 的选项，至少包括：

```text
Copy / Cut / Paste / Select All / Undo / Find
允许使用 Mac 快捷键关闭会话窗口（Cmd+W）
```

原因：补丁已经交换修饰键；首选项 transformation 再转换一次，会出现双重映射。例如方案一中，Cmd+C 先被转换为内部 Ctrl+C，最终 Scancode 表又把内部 Ctrl 改成 Windows，结果可能变成 Win+C。

## 9. 验证矩阵

仅仅“App 能打开”不代表补丁完成。至少测试以下项目，并记录左右键结果。

### 9.1 基础键盘

| 测试 | 远端期望 |
|---|---|
| 左 Command 单独按下/松开 | 左 Control down/up |
| 右 Command 单独按下/松开 | 右 Control down/up |
| 左 Control 单独按下/松开 | 左 Windows down/up |
| 右 Control 单独按下/松开 | 右 Windows down/up |
| 左 Command+C/V/X/A/Z/F | Ctrl+C/V/X/A/Z/F |
| 左 Control+R/E/L | Win+R/E/L |
| Shift/Option 与上述组合 | 无粘键、无丢失、左右语义正确 |

远端可用 PowerShell、AutoHotkey key history、浏览器键盘事件页或自写的低级键盘事件观察器确认左右 VK/Scancode；不要只根据应用行为猜测。

### 9.2 状态和焦点

- 按住修饰键时切出/切回远程窗口，确认没有 stuck modifier。
- 失去焦点、最小化、断线和重连后再次测试。
- 同时按两个修饰键。
- 修饰键配合鼠标左/右键、滚轮和拖拽。
- 键盘布局切换、Unicode 输入和 IME。

### 9.3 Windows App 功能

- 剪贴板双向复制。
- 直接 `.rdp` 连接。
- 保存凭据和重新连接。
- Windows 365 / AVD（如用户需要）。
- Ctrl+Alt+Del：方案一预期有已知问题；方案二应正常。
- Teams VDI、音频输入、USB/打印重定向（如用户需要）。

## 10. 回滚和恢复

当前完整原版备份的签名和 SHA-256 已验证有效：

```text
/Applications/Windows App 11.3.9 (3064) Original.app
SHA-256 = b7f1d42dbe13a532a708f77ef1220aac09e90e95a86c2681ce613efa490525f8
```

回滚原则：

1. 退出补丁版 Windows App。
2. 不删除补丁版，先改为另一个明确路径。
3. 把原版备份恢复为 `/Applications/Windows App.app`。
4. 再次核对 SHA-256 和微软签名。
5. 实际启动原版验证。

`/Applications` 中的 App 可能由 `root:wheel` 拥有，并受到 macOS“App 管理”权限保护。不要暴力修改权限或递归 `chown` 整个 `/Applications`；路径切换需要管理员认证时，使用系统原生授权，并确保第二次移动失败时立即把原版移回。

当前备份仍以 `.app` 结尾且 Bundle ID 与补丁版相同；LaunchServices/Spotlight 可能同时看到两个 Windows App。测试时使用明确的完整路径，不要用模糊的 `open -b com.microsoft.rdc.macos`。

## 11. 交接给后续 agent 的执行清单

后续 agent 应逐项回答并留痕：

- [ ] 用户要方案一还是方案二？不要把旧讨论的编号与本文编号混淆。
- [ ] 当前 Windows App 的版本、Build、主程序 SHA-256 是什么？
- [ ] 原始微软签名在补丁前是否有效？
- [ ] 是否已保留完整 `.app` 原版备份？
- [ ] x86_64 和 arm64 是否都存在？各 slice offset/size 是什么？
- [ ] 新版本相关 Swift 符号是否仍导出？
- [ ] 是否通过符号和反汇编重新定位，而不是照抄旧整文件偏移？
- [ ] 四个旧值是否与预期语义一致？
- [ ] 补丁前是否一次性校验全部旧字节？
- [ ] 补丁后、签名前的 byte diff 是否只在预期位置？
- [ ] 是否避免保留无权使用的微软 entitlement？
- [ ] `codesign --verify --deep --strict` 是否通过？
- [ ] 实际 `open -na` 是否能启动并持续运行？
- [ ] 左右 Command/Control、鼠标修饰、焦点切换是否实测？
- [ ] 是否明确告知方案一的 Ctrl+Alt+Del 和登录/OneAuth 副作用？
- [ ] 原版回滚路径和哈希是否再次验证？

## 12. 最终建议

- 用户当前选择的是**方案一：修改最终 Scancode 表**，因为补丁位置容易定位和复现。
- 如果未来确定需要 Windows App 的 Ctrl+Alt+Del、内部合成快捷键或更干净的语义，改用**方案二：修改物理修饰键映射**。
- 如果必须完整保留 Microsoft OneAuth、Windows 365/AVD、App Groups 和钥匙串能力，不应修改主程序并本地重签；应改用 App 外部的按键交换方案。

