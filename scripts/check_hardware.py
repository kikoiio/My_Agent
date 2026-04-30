"""一次性硬件检测脚本：USB 摄像头 + 音频设备。"""
from __future__ import annotations
import subprocess

# --- 摄像头检测 ---
try:
    import cv2
    cap = cv2.VideoCapture(0, cv2.CAP_DSHOW)  # Windows: CAP_DSHOW
    if cap.isOpened():
        w = cap.get(cv2.CAP_PROP_FRAME_WIDTH)
        h = cap.get(cv2.CAP_PROP_FRAME_HEIGHT)
        print(f"[camera] ✓  index=0  {int(w)}x{int(h)}")
        cap.release()
    else:
        print("[camera] ✗  VideoCapture(0) 打不开")
except ImportError:
    try:
        result = subprocess.run(
            ["powershell", "-Command",
             "Get-PnpDevice -Class Camera | Select-Object Status,FriendlyName | Format-Table -AutoSize"],
            capture_output=True, text=True, timeout=10,
        )
        print("[camera] opencv 未安装，PnP 摄像头列表：")
        print(result.stdout or "  (无输出)")
    except Exception as e:
        print(f"[camera] 检测失败: {e}")

# --- 音频设备检测 ---
try:
    import sounddevice as sd
    devs = sd.query_devices()
    print("\n[audio] sounddevice 设备列表：")
    for i, d in enumerate(devs):
        tag = ""
        if d["max_input_channels"] > 0:
            tag += " [输入]"
        if d["max_output_channels"] > 0:
            tag += " [输出]"
        print(f"  {i:2d}: {d['name']}{tag}")
    print(f"  默认输入: {sd.query_devices(kind='input')['name']}")
    print(f"  默认输出: {sd.query_devices(kind='output')['name']}")
except ImportError:
    try:
        result = subprocess.run(
            ["powershell", "-Command",
             "Get-PnpDevice -Class AudioEndpoint | Select-Object Status,FriendlyName | Format-Table -AutoSize"],
            capture_output=True, text=True, timeout=10,
        )
        print("\n[audio] sounddevice 未安装，PnP 音频设备列表：")
        print(result.stdout or "  (无输出)")
    except Exception as e:
        print(f"[audio] 检测失败: {e}")
