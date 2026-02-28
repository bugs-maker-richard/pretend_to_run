import os
import subprocess
import time
from datetime import datetime
from PIL import Image

# ==================== 配置区域 ====================
# 目标保存文件夹
SAVE_FOLDER = r"C:\Users\Linzhijian\Downloads\ADB操作\样本图片"

# 截图区域（单位：像素）
CAPTURE_REGION = {
    'x': 869,      # 左上角 x 坐标
    'y': 1751,      # 左上角 y 坐标
    'width': 200,  # 区域宽度
    'height': 200  # 区域高度
}

# ADB 路径（如已加入环境变量可留空）
ADB_PATH = ""  # 例如：r"C:\platform-tools\adb.exe"

# 设备序列号（留空则使用默认设备）
DEVICE_ID = ""
# ==================================================

def get_adb_command():
    return ADB_PATH if ADB_PATH and os.path.exists(ADB_PATH) else "adb"

def capture_and_save():
    adb = get_adb_command()
    device_flag = f'-s {DEVICE_ID}' if DEVICE_ID else ''
    temp_path = "/sdcard/screenshot_temp.png"
    local_temp_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), "screenshot_temp.png")
    
    cmd_cap = f'{adb} {device_flag} shell screencap -p {temp_path}'
    cmd_pull = f'{adb} {device_flag} pull {temp_path} "{local_temp_path}"'
    cmd_del = f'{adb} {device_flag} shell rm {temp_path}'

    try:
        # 1. 截图并拉取到本地
        subprocess.run(cmd_cap, shell=True, check=True, capture_output=True)
        time.sleep(0.5)
        subprocess.run(cmd_pull, shell=True, check=True, capture_output=True)
        subprocess.run(cmd_del, shell=True, capture_output=True)
        
        if not os.path.exists(local_temp_path):
            print("图片保存失败")
            return

        # 2. 裁剪图片
        img = Image.open(local_temp_path)
        x, y, w, h = CAPTURE_REGION['x'], CAPTURE_REGION['y'], CAPTURE_REGION['width'], CAPTURE_REGION['height']
        cropped = img.crop((x, y, x + w, y + h))
        
        # 3. 保存图片
        os.makedirs(SAVE_FOLDER, exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filepath = os.path.join(SAVE_FOLDER, f"screenshot_{timestamp}.png")
        cropped.save(filepath, "PNG")
        
        # 4. 清理临时文件
        img.close()
        os.remove(local_temp_path)
        
        print("图片保存成功")
        
    except Exception:
        print("图片保存失败")
        if os.path.exists(local_temp_path):
            try:
                os.remove(local_temp_path)
            except:
                pass

if __name__ == "__main__":
    capture_and_save()
