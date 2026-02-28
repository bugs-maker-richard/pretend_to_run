# -*- coding: utf-8 -*-
"""
ADB 点击操作前的图像校验模块
====================================
分级漏斗方案：
  第零层  ─ 尺寸预处理（差异 > 30% 直接拒绝）
  第一层  ─ dHash 感知哈希快速过滤
  第二层  ─ OCR 文字辅助校验（可选，需安装 PaddleOCR 或 Tesseract）
  第三层  ─ SSIM 结构相似度校验
  第四层  ─ 颜色直方图巴氏距离校验（边缘情况兜底）

公开接口:
  verified_tap(tap_x, tap_y, sample_path, ...)  — 校验通过则点击，否则中止
  compare_images(captured_img, sample_path, ...) — 仅做比对，返回 (bool, str)
"""

import os
import sys
import subprocess
import time
import tempfile
import numpy as np
from PIL import Image

# ──────────────────── 可选依赖检测 ────────────────────
HAS_CV2 = False
try:
    import cv2
    HAS_CV2 = True
except ImportError:
    pass

HAS_SKIMAGE = False
try:
    from skimage.metrics import structural_similarity as _skimage_ssim
    HAS_SKIMAGE = True
except ImportError:
    pass

OCR_ENGINE = None          # "paddleocr" | "tesseract" | None
_paddle_ocr_instance = None
try:
    from paddleocr import PaddleOCR
    OCR_ENGINE = "paddleocr"
except ImportError:
    try:
        import pytesseract
        OCR_ENGINE = "tesseract"
    except ImportError:
        pass


# ══════════════════════ 配置参数 ══════════════════════
SAMPLE_DIR      = r"C:\Users\Linzhijian\Downloads\ADB操作\样本图片"
REGION_SIZE     = 200        # 默认截取区域边长（像素）

# —— 阈值 ——
DHASH_MAX_DISTANCE      = 15      # dHash 汉明距离上限（64 位哈希）
SSIM_PASS_THRESHOLD     = 0.90    # SSIM ≥ 此值 → 高置信度直接通过
SSIM_EDGE_THRESHOLD     = 0.80    # SSIM ∈ [0.80, 0.90) → 进入边缘判定
SIZE_DIFF_MAX           = 0.30    # 尺寸差异 > 30% 直接拒绝
HIST_BHATTACHARYYA_MAX  = 0.35    # 巴氏距离上限

# —— 功能开关 ——
ENABLE_OCR              = True    # 是否启用 OCR 辅助校验
VERBOSE                 = True    # 打印详细校验日志
SAVE_FAILED_CAPTURE     = True    # 校验失败时保存截图供调试

# —— 调试输出目录 ——
DEBUG_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "校验失败截图")


# ══════════════════════ 工具函数 ══════════════════════

def _log(msg: str):
    """仅在 VERBOSE 开启时打印"""
    if VERBOSE:
        print(f"  [校验] {msg}")


def _save_debug_image(img: Image.Image, tag: str):
    """校验失败时将截图保存到调试目录"""
    if not SAVE_FAILED_CAPTURE:
        return
    os.makedirs(DEBUG_DIR, exist_ok=True)
    ts = time.strftime("%Y%m%d_%H%M%S")
    path = os.path.join(DEBUG_DIR, f"FAIL_{tag}_{ts}.png")
    img.save(path, "PNG")
    _log(f"调试截图已保存: {path}")


# ══════════════════════ 截图功能 ══════════════════════

def capture_screen_region(center_x: int, center_y: int,
                          width: int = 200, height: int = 200) -> Image.Image | None:
    """
    通过 ADB 截屏并裁剪以 (center_x, center_y) 为中心的 width×height 区域。

    返回 PIL.Image，失败返回 None。
    """
    left   = center_x - width // 2
    top    = center_y - height // 2
    right  = left + width
    bottom = top + height

    # 允许坐标为负时裁剪到 0
    left = max(0, left)
    top  = max(0, top)

    temp_device = "/sdcard/verify_screenshot.png"
    temp_local  = os.path.join(tempfile.gettempdir(), "adb_verify_screenshot.png")

    try:
        # 1. 截屏
        subprocess.run(
            ['adb', 'shell', 'screencap', '-p', temp_device],
            check=True, capture_output=True, timeout=15
        )
        time.sleep(0.3)

        # 2. 拉取
        subprocess.run(
            ['adb', 'pull', temp_device, temp_local],
            check=True, capture_output=True, timeout=15
        )

        # 3. 清理设备临时文件
        subprocess.run(['adb', 'shell', 'rm', temp_device],
                       capture_output=True, timeout=5)

        if not os.path.exists(temp_local):
            _log("截图文件未拉取成功")
            return None

        img = Image.open(temp_local)
        img_w, img_h = img.size

        # 修正裁剪范围不越界
        right  = min(right, img_w)
        bottom = min(bottom, img_h)

        cropped = img.crop((left, top, right, bottom))
        img.close()

        # 清理本地临时文件
        try:
            os.remove(temp_local)
        except OSError:
            pass

        return cropped

    except subprocess.TimeoutExpired:
        _log("ADB 命令超时")
        return None
    except subprocess.CalledProcessError as e:
        _log(f"ADB 命令执行失败: {e}")
        return None
    except Exception as e:
        _log(f"截图异常: {e}")
        return None


# ══════════════════════ 第一层：dHash ══════════════════════

def compute_dhash(pil_image: Image.Image, hash_size: int = 8) -> np.ndarray:
    """
    计算差异哈希 (dHash)。
    缩放至 (hash_size+1)×hash_size → 灰度 → 水平相邻像素比较。
    返回长度为 hash_size² 的 bool 数组。
    """
    resized = pil_image.resize((hash_size + 1, hash_size), Image.LANCZOS).convert('L')
    pixels  = np.array(resized, dtype=np.uint8)
    diff    = pixels[:, 1:] > pixels[:, :-1]      # 水平方向
    return diff.flatten()


def hamming_distance(h1: np.ndarray, h2: np.ndarray) -> int:
    """两个布尔哈希之间的汉明距离"""
    return int(np.sum(h1 != h2))


# ══════════════════════ 第二层：OCR ══════════════════════

def ocr_extract_text(pil_image: Image.Image) -> str:
    """提取图片中的文字。返回拼接后的字符串，无 OCR 引擎时返回空串。"""
    global _paddle_ocr_instance

    if OCR_ENGINE == "paddleocr":
        try:
            if _paddle_ocr_instance is None:
                _paddle_ocr_instance = PaddleOCR(use_angle_cls=True, lang='ch', show_log=False)
            img_arr = np.array(pil_image.convert('RGB'))
            result  = _paddle_ocr_instance.ocr(img_arr, cls=True)
            texts   = []
            if result and result[0]:
                for line in result[0]:
                    texts.append(line[1][0])
            return ''.join(texts)
        except Exception as e:
            _log(f"PaddleOCR 异常: {e}")
            return ""

    elif OCR_ENGINE == "tesseract":
        try:
            text = pytesseract.image_to_string(pil_image, lang='chi_sim+eng')
            return text.strip()
        except Exception as e:
            _log(f"Tesseract 异常: {e}")
            return ""

    return ""


# ══════════════════════ 第三层：SSIM ══════════════════════

def compute_ssim(img1: Image.Image, img2: Image.Image) -> float:
    """
    计算结构相似度 (SSIM)，返回 0~1。
    优先使用 scikit-image，其次使用 cv2 高斯加权实现，
    最后 fallback 到纯 numpy 简化版。
    """
    gray1 = np.array(img1.convert('L'), dtype=np.float64)
    gray2 = np.array(img2.convert('L'), dtype=np.float64)

    # 统一尺寸
    if gray1.shape != gray2.shape:
        h = min(gray1.shape[0], gray2.shape[0])
        w = min(gray1.shape[1], gray2.shape[1])
        gray1 = np.array(img1.convert('L').resize((w, h), Image.LANCZOS), dtype=np.float64)
        gray2 = np.array(img2.convert('L').resize((w, h), Image.LANCZOS), dtype=np.float64)

    # ---- scikit-image ----
    if HAS_SKIMAGE:
        return float(_skimage_ssim(gray1, gray2, data_range=255.0))

    # ---- OpenCV Gaussian ----
    if HAS_CV2:
        C1 = (0.01 * 255) ** 2
        C2 = (0.03 * 255) ** 2
        mu1       = cv2.GaussianBlur(gray1, (11, 11), 1.5)
        mu2       = cv2.GaussianBlur(gray2, (11, 11), 1.5)
        mu1_sq    = mu1 ** 2
        mu2_sq    = mu2 ** 2
        mu1_mu2   = mu1 * mu2
        sigma1_sq = cv2.GaussianBlur(gray1 ** 2, (11, 11), 1.5) - mu1_sq
        sigma2_sq = cv2.GaussianBlur(gray2 ** 2, (11, 11), 1.5) - mu2_sq
        sigma12   = cv2.GaussianBlur(gray1 * gray2, (11, 11), 1.5) - mu1_mu2
        ssim_map  = ((2 * mu1_mu2 + C1) * (2 * sigma12 + C2)) / \
                    ((mu1_sq + mu2_sq + C1) * (sigma1_sq + sigma2_sq + C2))
        return float(ssim_map.mean())

    # ---- 纯 numpy 简化版 ----
    C1 = (0.01 * 255) ** 2
    C2 = (0.03 * 255) ** 2
    mu1 = gray1.mean();  mu2 = gray2.mean()
    s1  = gray1.var();   s2  = gray2.var()
    s12 = ((gray1 - mu1) * (gray2 - mu2)).mean()
    return float(((2*mu1*mu2 + C1)*(2*s12 + C2)) /
                 ((mu1**2 + mu2**2 + C1)*(s1 + s2 + C2)))


# ══════════════════════ 第四层：直方图 ══════════════════════

def compute_hist_distance(img1: Image.Image, img2: Image.Image) -> float:
    """
    计算 BGR 三通道颜色直方图的平均巴氏距离 (Bhattacharyya)。
    返回 0~1，0 = 完全匹配。无 cv2 时返回 0（跳过该层）。
    """
    if not HAS_CV2:
        _log("未安装 cv2，跳过直方图比对")
        return 0.0

    arr1 = cv2.cvtColor(np.array(img1.convert('RGB')), cv2.COLOR_RGB2BGR)
    arr2 = cv2.cvtColor(np.array(img2.convert('RGB')), cv2.COLOR_RGB2BGR)

    if arr1.shape != arr2.shape:
        h = min(arr1.shape[0], arr2.shape[0])
        w = min(arr1.shape[1], arr2.shape[1])
        arr1 = cv2.resize(arr1, (w, h))
        arr2 = cv2.resize(arr2, (w, h))

    dist_sum = 0.0
    for ch in range(3):
        h1 = cv2.calcHist([arr1], [ch], None, [256], [0, 256])
        h2 = cv2.calcHist([arr2], [ch], None, [256], [0, 256])
        cv2.normalize(h1, h1)
        cv2.normalize(h2, h2)
        dist_sum += cv2.compareHist(h1, h2, cv2.HISTCMP_BHATTACHARYYA)

    return dist_sum / 3.0


# ══════════════════════ 多尺度模板匹配 (NCC) ══════════════════════

def template_match_ncc(img1: Image.Image, img2: Image.Image) -> float:
    """
    多尺度归一化相关系数 (NCC) 模板匹配。
    返回 -1~1，越接近 1 越相似。无 cv2 时返回 1.0（跳过）。
    """
    if not HAS_CV2:
        return 1.0

    g1 = np.array(img1.convert('L'))
    g2 = np.array(img2.convert('L'))

    # 确保 template 不大于 source
    if g1.shape[0] < g2.shape[0] or g1.shape[1] < g2.shape[1]:
        g1, g2 = g2, g1

    best = -1.0
    for scale in (0.90, 0.95, 1.00, 1.05, 1.10):
        h, w = int(g2.shape[0] * scale), int(g2.shape[1] * scale)
        if h <= 0 or w <= 0 or h > g1.shape[0] or w > g1.shape[1]:
            continue
        tmpl = cv2.resize(g2, (w, h))
        res  = cv2.matchTemplate(g1, tmpl, cv2.TM_CCOEFF_NORMED)
        _, max_val, _, _ = cv2.minMaxLoc(res)
        best = max(best, max_val)
    return best


# ══════════════════════ 主比对流程 ══════════════════════

def compare_images(captured_img: Image.Image,
                   sample_path: str,
                   expected_text: str | None = None) -> tuple[bool, str]:
    """
    分级漏斗式图像比对。

    返回 (是否匹配, 判定原因)。
    """
    if not os.path.exists(sample_path):
        return False, f"样本文件不存在: {sample_path}"

    sample_img = Image.open(sample_path)

    try:
        cap_w, cap_h = captured_img.size
        sam_w, sam_h = sample_img.size

        # ── 第零层：尺寸预处理 ──
        ratio_w = abs(cap_w - sam_w) / max(sam_w, 1)
        ratio_h = abs(cap_h - sam_h) / max(sam_h, 1)
        if ratio_w > SIZE_DIFF_MAX or ratio_h > SIZE_DIFF_MAX:
            return False, (f"尺寸差异过大: 截图({cap_w}×{cap_h}) "
                           f"vs 样本({sam_w}×{sam_h}), "
                           f"差异比 w={ratio_w:.2f} h={ratio_h:.2f}")

        # 微小差异 → 统一到样本尺寸
        if captured_img.size != sample_img.size:
            _log(f"尺寸微调: {captured_img.size} → {sample_img.size}")
            captured_img = captured_img.resize(sample_img.size, Image.LANCZOS)

        # ── 第一层：dHash 快速过滤 ──
        h_cap = compute_dhash(captured_img)
        h_sam = compute_dhash(sample_img)
        h_dist = hamming_distance(h_cap, h_sam)
        _log(f"[L1 dHash] 汉明距离 = {h_dist} (阈值 ≤ {DHASH_MAX_DISTANCE})")

        if h_dist > DHASH_MAX_DISTANCE:
            return False, f"dHash 不匹配 (距离={h_dist}, 阈值={DHASH_MAX_DISTANCE})"

        # ── 第二层：OCR 文字辅助 ──
        ocr_boost = False
        if ENABLE_OCR and expected_text and OCR_ENGINE:
            ocr_result = ocr_extract_text(captured_img)
            _log(f"[L2 OCR ] 识别='{ocr_result}' 期望='{expected_text}'")
            if expected_text in ocr_result:
                _log("[L2 OCR ] 文字命中 → 置信度提升")
                ocr_boost = True
            else:
                _log("[L2 OCR ] 文字未命中，继续后续校验")

        # ── 第三层：SSIM 结构校验 ──
        ssim_val = compute_ssim(captured_img, sample_img)
        _log(f"[L3 SSIM] 分数 = {ssim_val:.4f} "
             f"(通过≥{SSIM_PASS_THRESHOLD}, 边缘≥{SSIM_EDGE_THRESHOLD})")

        # OCR 命中时适当放宽 SSIM 阈值
        pass_thr = SSIM_PASS_THRESHOLD - (0.05 if ocr_boost else 0)
        edge_thr = SSIM_EDGE_THRESHOLD - (0.05 if ocr_boost else 0)

        if ssim_val >= pass_thr:
            return True, (f"SSIM 高置信度通过 (SSIM={ssim_val:.4f}"
                          f"{', OCR加持' if ocr_boost else ''})")

        if ssim_val < edge_thr:
            return False, f"SSIM 不匹配 (SSIM={ssim_val:.4f}, 阈值={edge_thr:.2f})"

        # ── 第四层：直方图 / 色彩校验（边缘情况） ──
        _log(f"[L4 Hist] SSIM 处于边缘区间 [{edge_thr:.2f}, {pass_thr:.2f})")
        hist_d = compute_hist_distance(captured_img, sample_img)
        _log(f"[L4 Hist] 巴氏距离 = {hist_d:.4f} (阈值 ≤ {HIST_BHATTACHARYYA_MAX})")

        if hist_d <= HIST_BHATTACHARYYA_MAX:
            return True, (f"边缘判定通过 (SSIM={ssim_val:.4f}, "
                          f"直方图={hist_d:.4f})")
        else:
            return False, (f"边缘判定失败 (SSIM={ssim_val:.4f}, "
                           f"直方图={hist_d:.4f})")

    finally:
        sample_img.close()


# ══════════════════════ 对外核心接口 ══════════════════════

def verified_tap(tap_x: int, tap_y: int,
                 sample_path: str,
                 sleep_time: float = 0,
                 log_message: str = "",
                 region_size: int = 200,
                 expected_text: str | None = None) -> bool:
    """
    带图像校验的 ADB 点击。

    流程：
      1. 以 (tap_x, tap_y) 为中心截取 region_size×region_size 区域
      2. 与样本图片进行分级比对
      3. 匹配 → 执行 adb tap → 等待 sleep_time
         不匹配 → 打印原因，返回 False

    返回:
      True  — 校验通过并已执行点击
      False — 校验失败，未执行点击
    """
    ts = time.strftime('%Y-%m-%d %H:%M:%S')
    print(f"\n[{ts}] >>> 准备执行: {log_message}")
    print(f"  点击坐标: ({tap_x}, {tap_y})")
    print(f"  校验样本: {os.path.basename(sample_path)}")

    # 1. 截取屏幕区域
    _log("正在截取屏幕区域...")
    captured = capture_screen_region(tap_x, tap_y, region_size, region_size)
    if captured is None:
        print(f"[{ts}] ✗ 截图失败，操作中止！")
        return False

    _log(f"截取完成: 中心({tap_x},{tap_y}), 实际大小{captured.size}")

    # 2. 图像比对
    _log("开始分级图像比对 >>>")
    matched, reason = compare_images(captured, sample_path, expected_text)

    if not matched:
        _save_debug_image(captured, log_message.replace("'", ""))
    captured.close()

    if matched:
        print(f"  [校验] ✓ 通过: {reason}")
        # 3. 执行点击
        subprocess.run(['adb', 'shell', 'input', 'tap', str(tap_x), str(tap_y)])
        if sleep_time > 0:
            time.sleep(sleep_time)
        print(f"[{time.strftime('%Y-%m-%d %H:%M:%S')}] {log_message}")
        return True
    else:
        print(f"  [校验] ✗ 失败: {reason}")
        print(f"[{ts}] !!! 操作已中止，请检查屏幕状态 !!!")
        return False


# ══════════════════════ 环境自检 ══════════════════════

def check_environment():
    """启动时打印依赖检测结果"""
    print("=" * 60)
    print("  图像校验模块 — 环境检测")
    print("=" * 60)
    print(f"  numpy        : ✓ ({np.__version__})")
    print(f"  Pillow       : ✓")
    print(f"  OpenCV (cv2) : {'✓ (' + cv2.__version__ + ')' if HAS_CV2 else '✗ (pip install opencv-python)'}")
    print(f"  scikit-image : {'✓' if HAS_SKIMAGE else '✗ (pip install scikit-image) — 将使用备选 SSIM'}")
    print(f"  OCR 引擎     : {OCR_ENGINE if OCR_ENGINE else '✗ (可选: pip install paddleocr / pytesseract)'}")
    print(f"  样本目录     : {SAMPLE_DIR}")
    print(f"  样本文件数   : {len([f for f in os.listdir(SAMPLE_DIR) if f.endswith('.png')]) if os.path.isdir(SAMPLE_DIR) else '目录不存在!'}")
    print("=" * 60)

    # 检查必要依赖
    if not HAS_CV2 and not HAS_SKIMAGE:
        print("\n[警告] cv2 和 scikit-image 均未安装，SSIM 将使用低精度简化算法。")
        print("       建议至少安装其中之一: pip install opencv-python scikit-image\n")


if __name__ == "__main__":
    check_environment()
