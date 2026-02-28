# -*- coding: utf-8 -*-
"""
ADB 自动化操作脚本（带图像校验版）
===================================
每次点击操作前，先截取目标区域并与样本库比对：
  - 校验通过 → 执行点击
  - 校验失败 → 立即中止，防止误操作

依赖:  image_verify.py（同目录下的校验模块）
运行:  python tap_verified_main.py
"""

import subprocess
import time
import sys
import os

# 确保能导入同目录下的校验模块
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from image_verify import verified_tap, check_environment

# ================== 配置 ==================
SAMPLE_DIR = r"C:\Users\Linzhijian\Downloads\ADB操作\样本图片"


def sample(name: str) -> str:
    """拼接样本图片完整路径"""
    return os.path.join(SAMPLE_DIR, name)


def run_adb_command(command, sleep_time=0, log_message=""):
    """执行不需要校验的 ADB 命令（滑动、输入文字等）"""
    subprocess.run(command)
    if sleep_time > 0:
        time.sleep(sleep_time)
    if log_message:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {log_message}")


# ================== 主流程 ==================

def main():
    # 环境自检
    check_environment()

    print("\n" + "=" * 60)
    print("  开始执行 ADB 自动化操作（带图像校验）")
    print("=" * 60)

    # ────────── 1. 打开 APP ──────────
    if not verified_tap(
        940, 180,
        sample("APPlogo_840_80_200_200.png"),
        sleep_time=15,
        log_message="已打开APP"
    ):
        return

    # ────────── 2. 点击「我的」 ──────────
    if not verified_tap(
        968, 1802,
        sample("我的_868_1702_200_200.png"),
        sleep_time=3,
        log_message="已点击'我的'",
        expected_text="我的"
    ):
        return

    # ────────── 3. 点击「账号与安全」 ──────────
    if not verified_tap(
        160, 1445,
        sample("账号与安全_60_1345_200_200.png"),
        sleep_time=3,
        log_message="已点击'账号与安全'",
        expected_text="账号与安全"
    ):
        return

    # ────────── 4. 下滑找到退出登录按钮（无需校验） ──────────
    run_adb_command(
        ['adb', 'shell', 'input', 'swipe', '560', '1501', '560', '838', '300'],
        1, "已下滑找到退出登录按钮"
    )

    # ────────── 5. 点击退出按钮 ──────────
    if not verified_tap(
        539, 1738,
        sample("退出登录_439_1638_200_200.png"),
        sleep_time=1,
        log_message="已点击退出按钮",
        expected_text="退出登录"
    ):
        return

    # ────────── 6. 点击学号编辑框 ──────────
    if not verified_tap(
        739, 768,
        sample("学号输入框_639_668_200_200.png"),
        sleep_time=0,
        log_message="已点击学号编辑框"
    ):
        return

    # ────────── 7. 删除旧学号（无需校验） ──────────
    run_adb_command(
        ['adb', 'shell', 'input', 'swipe', '1013', '1696', '1013', '1696', '2000'],
        0, "已删除旧学号"
    )

    # ────────── 8. 输入学号（无需校验） ──────────
    run_adb_command(
        ['adb', 'shell', 'input', 'text', '25250113104'],
        1, "已输入学号"
    )

    # ────────── 9. 点击密码输入框 ──────────
    if not verified_tap(
        293, 923,
        sample("密码输入框_193_823_200_200.png"),
        sleep_time=1,
        log_message="已点击密码输入框"
    ):
        return

    # ────────── 10. 输入密码（无需校验） ──────────
    run_adb_command(
        ['adb', 'shell', 'input', 'text', 'Abc@060625'],
        0.3, "已输入密码"
    )

    # ────────── 11. 确认输入完成（无需校验，连续快速点击） ──────────
    subprocess.run(['adb', 'shell', 'input', 'tap', '984', '1850'])
    time.sleep(0.2)
    subprocess.run(['adb', 'shell', 'input', 'tap', '458', '890'])
    time.sleep(0.2)
    run_adb_command(
        ['adb', 'shell', 'input', 'tap', '948', '1850'],
        0.2, "已确认输入完成"
    )

    # ────────── 12. 点击同意协定 ──────────
    if not verified_tap(
        218, 1073,
        sample("同意协定_118_973_200_200.png"),
        sleep_time=0.5,
        log_message="已点击同意协定"
    ):
        return

    # ────────── 13. 点击确认登录 ──────────
    if not verified_tap(
        539, 1238,
        sample("登录439_1138_200_200.png"),
        sleep_time=3,
        log_message="已点击确认登录",
        expected_text="登录"
    ):
        return

    # ────────── 14. 点击阳光跑（原脚本末步，无样本暂不校验） ──────────
    run_adb_command(
        ['adb', 'shell', 'input', 'tap', '413', '1063'],
        0, "已点击阳光跑"
    )

    print("\n" + "=" * 60)
    print("  ✓ 所有操作已顺利完成！")
    print("=" * 60)


if __name__ == "__main__":
    main()
