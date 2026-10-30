# -*- coding: utf-8 -*-
"""自动打卡：到达打卡点弹窗 → 打卡 → 等人脸 → 拍照 → 上传"""
import subprocess, time, re, sys, os

ADB = r"C:\leidian\LDPlayer9\adb.exe"
SERIAL = "emulator-5554"
SHOT = r"C:\Users\Administrator\Desktop\temp_20261030_01\auto.png"
UI = r"C:\Users\Administrator\Desktop\temp_20261030_01\auto_ui.xml"


def sh(*args, timeout=15):
    return subprocess.run([ADB, "-s", SERIAL] + list(args),
                          capture_output=True, timeout=timeout)


def screencap():
    sh("shell", "screencap -p /sdcard/auto.png")
    sh("pull", "/sdcard/auto.png", SHOT)
    return SHOT


def uidump():
    """返回 [(text, (cx, cy), w, h)]"""
    r = sh("shell", "uiautomator dump /sdcard/auto_ui.xml", timeout=20)
    if b"dumped" not in (r.stdout + r.stderr).lower():
        time.sleep(1)
        sh("shell", "uiautomator dump --compressed /sdcard/auto_ui.xml", timeout=20)
    p = sh("pull", "/sdcard/auto_ui.xml", UI)
    if p.returncode != 0 or not os.path.exists(UI):
        return []
    try:
        s = open(UI, encoding="utf-8").read()
    except Exception:
        return []
    out = []
    for m in re.finditer(r'<node[^>]*?text="([^"]{1,30})"[^>]*?bounds="\[(\d+),(\d+)\]\[(\d+),(\d+)\]"', s):
        t, x1, y1, x2, y2 = m.group(1), *map(int, m.groups()[1:])
        if t.strip():
            out.append((t.strip(), ((x1 + x2) // 2, (y1 + y2) // 2), x2 - x1, y2 - y1))
    return out


def tap(x, y):
    sh("shell", "input tap %d %d" % (x, y))


def button_enabled(cx, cy):
    """采样按钮中心颜色，灰=不可用"""
    from PIL import Image
    try:
        im = Image.open(SHOT).convert("RGB")
    except Exception:
        return False
    r, g, b = im.getpixel((cx, cy))
    return not (abs(r - g) < 18 and abs(g - b) < 18 and 120 < r < 190)


def log(msg):
    print("[%s] %s" % (time.strftime("%H:%M:%S"), msg), flush=True)


log("自动打卡监听启动")
stage = "idle"          # idle / photo / confirm / upload
last_act = ""
while True:
    try:
        r = sh("shell", "dumpsys window | grep mCurrentFocus", timeout=10)
        focus = r.stdout.decode("utf-8", "ignore")
        act = focus.split("/")[1].rstrip("}").strip() if "/" in focus else ""
        if act != last_act and act:
            log("界面: " + act)
            last_act = act

        if "FaceVerify" in act:
            nodes = uidump()
            texts = {t: (c, w, h) for t, c, w, h in nodes}
            # 找拍照按钮
            shoot = None
            for t, c, w, h in nodes:
                if t == "拍照":
                    shoot = (t, c, w, h)
            if stage == "idle":
                if shoot:
                    screencap()
                    if button_enabled(*shoot[1]):
                        log("检测到人脸，点击拍照")
                        tap(*shoot[1])
                        stage = "confirm"
                        time.sleep(2.5)
                    else:
                        pass  # 等人脸
                time.sleep(1.5)
            elif stage == "confirm":
                # 拍照后确认/上传界面
                done = False
                for t, c, w, h in nodes:
                    if any(k in t for k in ("上传", "确定", "确认", "完成", "使用照片")):
                        log("点击: " + t)
                        tap(*c)
                        done = True
                        stage = "upload"
                        time.sleep(2.5)
                        break
                if not done:
                    screencap()
                    log("拍照后未找到确认按钮，界面: " + str([t for t, _, _, _ in nodes][:8]))
                    stage = "idle"
            elif stage == "upload":
                for t, c, w, h in nodes:
                    if any(k in t for k in ("上传", "提交", "确定", "完成")):
                        log("点击: " + t)
                        tap(*c)
                        time.sleep(2.5)
                        stage = "idle"
                        break
                else:
                    stage = "idle"
        else:
            # 打卡提示弹窗（到达打卡点）
            if "huihai" in focus:
                nodes = uidump()
                for t, c, w, h in nodes:
                    if t == "打卡":
                        log("到达打卡点，点击打卡")
                        tap(*c)
                        time.sleep(2.5)
                        break
            stage = "idle"
            time.sleep(1.5)
    except Exception as e:
        log("ERR " + repr(e))
        time.sleep(2)
