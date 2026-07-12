#!/usr/bin/env python3
from __future__ import annotations

import argparse
import plistlib
import subprocess
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description="CleanMyMac破解补丁")
    parser.add_argument("app", type=Path, help="Path")
    app = parser.parse_args().app

    fw = app / "Contents/Frameworks/MacPawAccount.framework/Versions/A/MacPawAccount"
    pops = app / "Contents/Frameworks/PrivilegedOperationsPerformerService.framework/Versions/A/PrivilegedOperationsPerformerService"
    info = app / "Contents/Info.plist"
    agent = app / "Contents/Library/LaunchServices/com.macpaw.CleanMyMac5.Agent"

    for f in (fw, pops, info, agent):
        if not f.exists():
            sys.exit(f"找不到: {f}")

    def patch(path: Path, old: bytes, new: bytes, label: str) -> None:
        """按字节特征串替换全部匹配（幂等）。old 需为全局唯一或成对出现的特征串。"""
        data = path.read_bytes()
        if old not in data:
            if new in data:
                return print(f"  [已] {label}")
            sys.exit(f"  [!] {label}: 未找到目标")
        path.write_bytes(data.replace(old, new))
        print(f"  [改] {label}")

    print(f"目标: {app}")

    # #1 许可证恒为已激活：-[MPALibLicenseValidationResult status] 恒返回 1
    #    8 字节不唯一，故匹配含 cmp x8,#9 的 20 字节唯一方法体，仅改写开头两条指令
    patch(fw, bytes.fromhex("80 00 00 b4 08 08 40 f9 1f 25 00 f1 e0 17 9f 1a c0 03 5f d6"),
              bytes.fromhex("20 00 80 52 c0 03 5f d6 1f 25 00 f1 e0 17 9f 1a c0 03 5f d6"),
              "#1 status 恒返回 1")

    # #2 绕过 App 端对 Agent 的签名校验：SecStaticCodeCheckValidity 后的 cbz 改为无条件跳转
    patch(pops, bytes.fromhex("8b 41 00 94 80 05 00 34"),
                bytes.fromhex("8b 41 00 94 2c 00 00 14"), "#2 绕过 Agent 校验")

    # #3 放宽 App 对 Agent 的信任：SMPrivilegedExecutables 只认 identifier
    raw = info.read_bytes()
    plist = plistlib.loads(raw)
    requirement = 'identifier "com.macpaw.CleanMyMac5.Agent"'
    if plist["SMPrivilegedExecutables"]["com.macpaw.CleanMyMac5.Agent"] == requirement:
        print("  [已] #3 App 对 Agent 要求放宽")
    else:
        plist["SMPrivilegedExecutables"]["com.macpaw.CleanMyMac5.Agent"] = requirement
        fmt = plistlib.FMT_BINARY if raw[:8] == b"bplist00" else plistlib.FMT_XML
        info.write_bytes(plistlib.dumps(plist, fmt=fmt))
        print("  [改] #3 App 对 Agent 要求放宽")

    # #4 放宽 Agent 对客户端的信任：SMAuthorizedClients 主 App 条目只认 identifier（补空格保持长度）
    old = b'identifier "com.macpaw.CleanMyMac5" and info [CFBundleShortVersionString] &gt;= "0.0.1" and anchor apple generic and certificate leaf[subject.OU] = "S8EX82NJP6"'
    keep = b'identifier "com.macpaw.CleanMyMac5"'
    patch(agent, old, keep + b" " * (len(old) - len(keep)), "#4 Agent 客户端要求放宽")

    # 去隔离 & 重签名
    subprocess.run(["xattr", "-dr", "com.apple.quarantine", str(app)],
                   stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # Agent 在 Contents/Library/LaunchServices，--deep 覆盖不到，需先单独签
    subprocess.run(["codesign", "--force", "--sign", "-", str(agent)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    # --deep 递归签主 exe / Frameworks / 登录项 / XPC / 扩展，并重封含 Agent 的资源哈希
    subprocess.run(["codesign", "--force", "--sign", "-", "--deep", str(app)],
                   check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    subprocess.run(["codesign", "--verify", str(app)], check=True)

    print(f"完成: {app}\n首次触发特权操作会弹一次密码框安装守护进程（仅一次）。")


if __name__ == "__main__":
    main()
