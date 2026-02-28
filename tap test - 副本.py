import subprocess
import time

def run_adb_command(command, sleep_time=0, log_message=""):
    subprocess.run(command)
    if sleep_time > 0:
        time.sleep(sleep_time)
    if log_message:
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {log_message}")

# 打开APP
run_adb_command(['adb', 'shell', 'input', 'tap', '940', '180'], 15, "已打开APP")

#点击我的
run_adb_command(['adb', 'shell', 'input', 'tap', '968', '1802'], 3, "已点击'我的'")

#点击账号与安全
run_adb_command(['adb', 'shell', 'input', 'tap', '160', '1445'], 3, "已点击'账号与安全'")

#下滑找到退出登录按钮
run_adb_command(['adb', 'shell', 'input', 'swipe', '560', '1501', '560', '838', '300'], 1, "已下滑找到退出登录按钮")

#点击退出按钮
run_adb_command(['adb', 'shell', 'input', 'tap', '539', '1738'], 1, "已点击退出按钮")

#点击学号编辑框
run_adb_command(['adb', 'shell', 'input', 'tap', '739', '768'], 0, "已点击学号编辑框")

#删除学号
run_adb_command(['adb', 'shell', 'input', 'swipe', '1013', '1696', '1013', '1696', '2000'], 0, "已删除旧学号")

#输入学号
run_adb_command(['adb', 'shell', 'input', 'text', '25250113104'], 1, "已输入学号")

#点击密码输入框
run_adb_command(['adb', 'shell', 'input', 'tap', '293', '923'], 1, "已点击密码输入框")

#输入密码
run_adb_command(['adb', 'shell', 'input', 'text', 'Abc@060625'], 0.3, "已输入密码")

#确认输入完成 (包含多个连续点击)
subprocess.run(['adb', 'shell', 'input', 'tap', '984', '1850'])
time.sleep(0.2)
subprocess.run(['adb', 'shell', 'input', 'tap', '458', '890'])
time.sleep(0.2)
run_adb_command(['adb', 'shell', 'input', 'tap', '948', '1850'], 0.2, "已确认输入完成")

#点击同意协定
run_adb_command(['adb', 'shell', 'input', 'tap', '218', '1073'], 0.5, "已点击同意协定")

#点击确认登录
run_adb_command(['adb', 'shell', 'input', 'tap', '539', '1238'], 3, "已点击确认登录")

#点击阳光跑
run_adb_command(['adb', 'shell', 'input', 'tap', '413', '1063'], 0, "已点击阳光跑")
