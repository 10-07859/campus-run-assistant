# -*- coding: utf-8 -*-
"""校园跑 · 一键投喂器（精美版）

贵阳职业技术学院 · 第3道 · 8 圈 · 2 Hz · 约7'40"配速
跑完或手动停止后可选择：原地停 / 回到起点
"""
import math
import os
import queue
import shutil
import subprocess
import threading
import time
import tkinter as tk
from tkinter import scrolledtext

try:
    from PIL import Image, ImageTk
    HAS_PIL = True
except Exception:
    HAS_PIL = False

# ---------------- 配置 ----------------
# 定位 ldconsole.exe：环境变量 > PATH > 常见安装目录 > 盘符扫描
LDCONSOLE_ENV = "LDCONSOLE"          # 手动指定：set LDCONSOLE=D:\xxx\ldconsole.exe
SEARCH_DIRS = [
    r"D:\leidian\LDPlayer9",
    r"D:\leidian\LDPlayer14",
    r"D:\LDPlayer\LDPlayer9",
    r"D:\LDPlayer\LDPlayer14",
    r"D:\雷电模拟器\leidian\LDPlayer9",
    r"D:\雷电模拟器\leidian\LDPlayer14",
    r"C:\LDPlayer\LDPlayer9",
    r"C:\LDPlayer\LDPlayer14",
    r"C:\Program Files\LDPlayer\LDPlayer9",
    r"C:\Program Files\LDPlayer\LDPlayer14",
]


def _scan_drives():
    """在盘符根目录下浅扫两层，兜底找 ldconsole.exe"""
    import glob
    found = []
    for drive in "CDEFG":
        root = drive + ":\\"
        if not os.path.exists(root):
            continue
        for pat in ("*/ldconsole.exe", "*/*/ldconsole.exe", "*/*/*/ldconsole.exe"):
            try:
                found.extend(glob.glob(os.path.join(root, pat)))
            except Exception:
                pass
            if found:
                return found
    return found


def _candidates():
    cands = []
    env = os.environ.get(LDCONSOLE_ENV, "").strip('"')
    if env:
        cands.append(env)
    for d in SEARCH_DIRS:
        cands.append(os.path.join(d, "ldconsole.exe"))
    w = shutil.which("ldconsole") or shutil.which("ldconsole.exe")
    if w:
        cands.append(w)
    cands.extend(_scan_drives())
    seen, out = set(), []
    for c in cands:
        if c and c not in seen:
            seen.add(c)
            out.append(c)
    return out


def _pick_ldconsole():
    """返回 (路径, 状态)。优先运行中的实例，其次第一个存在的。"""
    cands = _candidates()
    existing = [c for c in cands if os.path.exists(c)]
    if not existing:
        return (cands[0] if cands else "ldconsole.exe"), "未找到"
    for c in existing:
        try:
            out = subprocess.run([c, "list2"], capture_output=True, timeout=8)
            for line in out.stdout.decode("gbk", "ignore").splitlines():
                cols = line.split(",")
                if len(cols) >= 5 and cols[4].strip() == "1":
                    return c, "运行中"
        except Exception:
            continue
    return existing[0], "未启动"


LDCONSOLE, LDCONSOLE_STATE = _pick_ldconsole()
INDEX = "0"
FISH_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fish.png")

CENTER_LAT, CENTER_LNG = 26.622167, 106.599023   # 操场中心（用户视觉校准值，勿改）
A_SEMI = 76.6             # 长轴端到中心距离（米），弯道最远点过 1、2 号打卡点
B_SEMI = 40.0             # 直道半宽（米）＝弯道半径 R（按实测轨迹往里收 11m：51→40）
LANE_W = 10.0             # 跑道宽（米）
ROT_DEG = 15.3            # 长轴方位：北偏西 15.3°
LAPS = 8                  # 8 圈 ≈ 3182m（App 因 GPS 抖动会记 ~4000m，按 3000 封顶）
PACE_SEC = 370            # 6'10"/km = 2.70 m/s（速度区间 1.39~5.56 内）
HZ = 2.0                  # 2Hz 注入：单步 1.1m，即使合并也远低于超速线
A_IN, B_IN = A_SEMI - LANE_W / 2, B_SEMI - LANE_W / 2
A_OUT, B_OUT = A_SEMI + LANE_W / 2, B_SEMI + LANE_W / 2

# ---------------- 配色 ----------------
BG = "#0b1220"
PANEL = "#121c31"
PANEL2 = "#17233d"
CARD = "#1b2a45"
TEXT = "#e6edf7"
MUTED = "#8aa0bf"
CYAN = "#22d3ee"
GREEN = "#22c55e"
RED = "#ef4444"
TRACK = "#b4451f"
TRACK2 = "#8f3517"
INFIELD = "#14532d"
LINE = "#f1f5f9"

# 体育场形轨迹（两条直道 + 两端半圆弯道），分段精确弧长，无需数值积分
H_ST = A_SEMI - B_SEMI            # 直道半长（米）
R_ST = B_SEMI                     # 弯道半径（米）
S_CAP = math.pi * R_ST / 2.0      # 1/4 圆弧长
S_STR = 2.0 * H_ST                # 一条直道长
PER = 2 * math.pi * R_ST + 4 * H_ST
TOTAL_M = PER * LAPS
SPEED = 1000.0 / PACE_SEC
KF = 111320.0 * math.cos(math.radians(CENTER_LAT))


def route_point(d):
    """体育场轨迹，d 为沿程弧长（米）。d=0 在长轴北端，逆时针（北→西→南→东）。
    (u=北, v=东) 米。两直道为直线，南北弯道最北/最南点精确过 1、2 号打卡点。"""
    d = d % PER
    if d < S_CAP:                                   # 北弯道右半：最北点 → 西北角
        th = -d / R_ST
        return (H_ST + R_ST * math.cos(th), R_ST * math.sin(th))
    d -= S_CAP
    if d < S_STR:                                   # 西直道（直线）
        return (H_ST - d, -R_ST)
    d -= S_STR
    if d < math.pi * R_ST:                          # 南弯道：西北角 → 东南角
        th = -math.pi / 2.0 - d / R_ST
        return (-H_ST + R_ST * math.cos(th), R_ST * math.sin(th))
    d -= math.pi * R_ST
    if d < S_STR:                                   # 东直道（直线）
        return (-H_ST + d, R_ST)
    d -= S_STR                                      # 北弯道左半：东北角 → 最北点
    th = math.pi / 2.0 - d / R_ST
    return (H_ST + R_ST * math.cos(th), R_ST * math.sin(th))


def to_geo(u, v):
    # 轨迹绕操场中心旋转：长轴由正北转为北偏西 ROT_DEG
    rot = math.radians(ROT_DEG)
    u2 = u * math.cos(rot) + v * math.sin(rot)
    v2 = -u * math.sin(rot) + v * math.cos(rot)
    return CENTER_LAT + u2 / 111320.0, CENTER_LNG + v2 / KF


N_PTS = int(round(TOTAL_M / SPEED * HZ))
ROUTE = [(i * SPEED / HZ,) + to_geo(*route_point(i * SPEED / HZ)) for i in range(N_PTS)]
START_LAT, START_LNG = ROUTE[0][1], ROUTE[0][2]


def stadium(h, r, n=48):
    """体育场形闭合路径：直道半长 h、弯道半径 r，(u=北, v=东) 米，t=0 在最北点"""
    pts = []
    for i in range(n):                                    # 北弯道：最北点 → 西北角
        th = -math.pi / 2.0 * i / n
        pts.append((h + r * math.cos(th), r * math.sin(th)))
    pts.append((-h, -r))                                  # 西直道
    for i in range(n):                                    # 南弯道：西北角 → 东南角
        th = -math.pi / 2.0 - math.pi * i / n
        pts.append((-h + r * math.cos(th), r * math.sin(th)))
    pts.append((h, r))                                    # 东直道
    for i in range(n):                                    # 北弯道：东北角 → 最北点
        th = math.pi / 2.0 - math.pi / 2.0 * i / n
        pts.append((h + r * math.cos(th), r * math.sin(th)))
    return pts


def locate(lat, lng):
    subprocess.run([LDCONSOLE, "locate", "--index", INDEX, "--LLI", "%.6f,%.6f" % (lng, lat)],
                   capture_output=True, timeout=10,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


class FishSprite:
    """把你的 fish.png 预旋转成一圈角度，动画时按航向取图"""
    def __init__(self, path, size=58, steps=36):
        self.ok = False
        self.imgs = []
        self.size = size
        if not (HAS_PIL and os.path.exists(path)):
            return
        try:
            im = Image.open(path).convert("RGBA")
            bbox = im.getbbox()
            if bbox:
                im = im.crop(bbox)
            w, h = im.size
            k = size / float(max(w, h))
            im = im.resize((max(1, int(w * k)), max(1, int(h * k))), Image.LANCZOS)
            canvas = Image.new("RGBA", (size + 14, size + 14), (0, 0, 0, 0))
            canvas.paste(im, ((size + 14 - im.size[0]) // 2, (size + 14 - im.size[1]) // 2), im)
            for i in range(steps):
                rot = canvas.rotate(-i * (360.0 / steps), resample=Image.BICUBIC, expand=False)
                self.imgs.append(ImageTk.PhotoImage(rot))
            self.ok = True
        except Exception:
            self.ok = False

    def get(self, ang_deg):
        if not self.ok:
            return None
        idx = int(round(ang_deg / (360.0 / len(self.imgs)))) % len(self.imgs)
        return self.imgs[idx]


class Runner:
    def __init__(self, cv, x0, y0, w, h):
        self.cv = cv
        self.tag = "runner"
        self.trail = []

    def clear(self):
        self.cv.delete(self.tag)

    def draw_fish_vector(self, x, y, ang, scale=1.0):
        """没有 fish.png 时手绘一条胖鱼"""
        cv = self.cv
        pts = [(18, 0), (6, -11), (-8, -13), (-16, -6), (-16, 6), (-8, 13), (6, 11)]
        tail = [(-16, -2), (-27, -11), (-24, 0), (-27, 11), (-16, 2)]
        body, tl = [], []
        ca, sa = math.cos(ang), math.sin(ang)
        for px, py in pts:
            body += [x + (px * ca - py * sa) * scale, y + (px * sa + py * ca) * scale]
        for px, py in tail:
            tl += [x + (px * ca - py * sa) * scale, y + (px * sa + py * ca) * scale]
        cv.create_polygon(tl, fill="#3b6cf6", outline="", tags=self.tag)
        cv.create_polygon(body, fill="#4d6bfe", outline="#c7d2fe", width=1.5, smooth=True, tags=self.tag)
        ex = x + (8 * ca - 0) * scale
        ey = y + (8 * sa - 0) * scale
        cv.create_oval(ex - 3 * scale, ey - 3 * scale, ex + 3 * scale, ey + 3 * scale,
                       fill="white", outline="", tags=self.tag)
        cv.create_oval(ex - 1.2 * scale, ey - 1.2 * scale, ex + 1.2 * scale, ey + 1.2 * scale,
                       fill="#0b1220", outline="", tags=self.tag)


class MapView(tk.Canvas):
    def __init__(self, master, w=660, h=620):
        super().__init__(master, width=w, height=h, bg=BG, highlightthickness=0)
        self.W, self.H = w, h
        self.sprite = FishSprite(FISH_PATH)
        self.runner = Runner(self, 0, 0, w, h)
        self.fit()
        self.draw_static()

    def fit(self):
        us = [route_point(i * 0.5)[0] for i in range(int(PER * 2))]
        vs = [route_point(i * 0.5)[1] for i in range(int(PER * 2))]
        u0, u1 = min(us) - 12, max(us) + 12
        v0, v1 = min(vs) - 12, max(vs) + 12
        pad = 46
        s = min((self.W - 2 * pad) / (v1 - v0), (self.H - 2 * pad) / (u1 - u0))
        self.s = s
        self.cx = self.W / 2.0 - ((v0 + v1) / 2.0) * s
        self.cy = self.H / 2.0 + ((u0 + u1) / 2.0) * s

    def px(self, u, v):
        return self.cx + v * self.s, self.cy - u * self.s

    def draw_static(self):
        cv = self
        # 背景网格
        for i in range(0, self.W, 40):
            cv.create_line(i, 0, i, self.H, fill="#0f1a2e")
        for j in range(0, self.H, 40):
            cv.create_line(0, j, self.W, j, fill="#0f1a2e")

        # 内场
        inner = stadium(H_ST, B_IN - 1.2)
        poly = []
        for u, v in inner:
            poly += list(self.px(u, v))
        cv.create_polygon(poly, fill=INFIELD, outline="", smooth=True)
        # 内场纹理
        for k in range(-4, 5):
            u = k * (H_ST / 4.0) if H_ST else 0
            vv = B_IN * math.sqrt(max(0.0, 1.0 - (u / max(A_IN, 1e-6)) ** 2)) - 2
            a = self.px(u, -vv)
            b = self.px(u, vv)
            cv.create_line(a[0], a[1], b[0], b[1], fill="#186b3a", width=1)

        # 跑道环（外沿 + 内沿反向，填充出环形）
        outer = stadium(H_ST, B_OUT)
        inn = stadium(H_ST, B_IN)
        ring = []
        for u, v in outer:
            ring += list(self.px(u, v))
        for u, v in reversed(inn):
            ring += list(self.px(u, v))
        cv.create_polygon(ring, fill=TRACK, outline="#6b2a12", width=1, smooth=True)

        # 分道线
        for k in range(9):
            kr = B_IN + k * (B_OUT - B_IN) / 8.0
            pts = []
            for u, v in stadium(H_ST, kr, 36):
                pts += list(self.px(u, v))
            pts += pts[:2]
            cv.create_line(pts, fill=LINE, width=1, smooth=True)

        # 起终点线（长轴北端，跨跑道宽）
        p1 = self.px(A_OUT, 0)
        p2 = self.px(A_IN, 0)
        cv.create_line(p1[0], p1[1], p2[0], p2[1], fill="#fde047", width=3)

        # 指北针
        ax, ay = self.W - 52, 56
        cv.create_oval(ax - 18, ay - 18, ax + 18, ay + 18, outline=MUTED, width=1)
        cv.create_line(ax, ay + 12, ax, ay - 12, fill=CYAN, width=2, arrow="last", arrowshape=(8, 10, 4))
        cv.create_text(ax, ay + 28, text="N", fill=MUTED, font=("Consolas", 9))

        # 比例尺 100 m
        sx, sy = 26, self.H - 30
        L100 = 100 * self.s
        cv.create_line(sx, sy, sx + L100, sy, fill=MUTED, width=2)
        cv.create_line(sx, sy - 4, sx, sy + 4, fill=MUTED, width=2)
        cv.create_line(sx + L100, sy - 4, sx + L100, sy + 4, fill=MUTED, width=2)
        cv.create_text(sx + L100 / 2, sy - 12, text="100 m", fill=MUTED, font=("Consolas", 9))

        cv.create_text(18, 20, text="贵阳职业技术学院", anchor="w",
                       fill=TEXT, font=("Microsoft YaHei", 11, "bold"))

    def draw_dynamic(self, idx_float, trail_idx=None):
        cv = self
        STEP = SPEED / HZ
        cv.delete("dyn")
        # 拖尾
        n = len(ROUTE)
        start = max(0, int(idx_float) - 46)
        pts = []
        for i in range(start, min(n, int(idx_float) + 1)):
            u, v = route_point(i * STEP)
            x, y = self.px(u, v)
            pts += [x, y]
        xu, xv = route_point(idx_float * STEP)
        fx, fy = self.px(xu, xv)
        pts += [fx, fy]
        if len(pts) >= 4:
            cv.create_line(pts, fill="#0e7490", width=7, smooth=True, tags="dyn")
            cv.create_line(pts, fill=CYAN, width=3, smooth=True, tags="dyn")

        # 光晕
        for rr, col in ((26, "#0e7490"), (18, "#22d3ee")):
            cv.create_oval(fx - rr, fy - rr, fx + rr, fy + rr, outline=col, width=1, tags="dyn")

        # 航向
        i0 = max(0, int(idx_float) - 1)
        i1 = min(len(ROUTE) - 1, i0 + 1)
        ua, va = route_point(i0 * STEP)
        ub, vb = route_point(i1 * STEP)
        dx = (vb - va) * self.s
        dy = -(ub - ua) * self.s
        ang = math.degrees(math.atan2(dy, dx))

        img = self.sprite.get(ang)
        if img is not None:
            cv.create_image(fx, fy, image=img, tags="dyn")
            self._keep = img
        else:
            self.runner.tag = "dyn"
            self.runner.draw_fish_vector(fx, fy, math.radians(ang), 1.15)


class App:
    def __init__(self, root):
        self.root = root
        self.stop_flag = threading.Event()
        self.worker = None
        self.running = False
        self.t0 = None
        self.frozen_idx = 0.0
        self.silent_stop = False
        self.cur_lat, self.cur_lng = START_LAT, START_LNG
        self._offset = 0

        root.title("校园跑 · 一键投喂器")
        root.configure(bg=BG)
        root.geometry("1140x700+120+60")   # 固定初始位置，避免被系统恢复到屏幕外
        root.resizable(False, False)

        wrap = tk.Frame(root, bg=BG)
        wrap.pack(fill="both", expand=True, padx=10, pady=10)

        self.map = MapView(wrap, 660, 620)
        self.map.pack(side="left", fill="both", expand=True)

        right = tk.Frame(wrap, bg=BG, width=440)
        right.pack(side="left", fill="both", padx=(12, 0))
        right.pack_propagate(False)

        head = tk.Frame(right, bg=BG)
        head.pack(fill="x", pady=(4, 10))
        tk.Label(head, text="校园跑", bg=BG, fg=TEXT,
                 font=("Microsoft YaHei", 20, "bold")).pack(anchor="w")
        tk.Label(head, text="打卡管家", bg=BG, fg=MUTED,
                 font=("Microsoft YaHei", 9)).pack(anchor="w")

        cards = tk.Frame(right, bg=BG)
        cards.pack(fill="x")
        self.v_dist = tk.StringVar(value="0")
        self.v_time = tk.StringVar(value="00:00")
        self.v_pace = tk.StringVar(value="--'--\"")
        for i, (t, var, unit) in enumerate([("距离", self.v_dist, "m"),
                                           ("用时", self.v_time, ""),
                                           ("配速", self.v_pace, "/km")]):
            c = tk.Frame(cards, bg=CARD)
            c.grid(row=0, column=i, padx=(0, 8), sticky="nsew")
            cards.columnconfigure(i, weight=1)
            tk.Label(c, text=t, bg=CARD, fg=MUTED, font=("Microsoft YaHei", 9)).pack(anchor="w", padx=12, pady=(10, 0))
            row = tk.Frame(c, bg=CARD)
            row.pack(anchor="w", padx=12)
            tk.Label(row, textvariable=var, bg=CARD, fg=TEXT,
                     font=("Consolas", 20, "bold")).pack(side="left")
            tk.Label(row, text=unit, bg=CARD, fg=MUTED, font=("Consolas", 9)).pack(side="left", pady=(8, 0))
            tk.Frame(c, bg=CARD, height=8).pack()

        self.lbl_lap = tk.Label(right, text="第 0 / %d 圈" % LAPS, bg=BG, fg=MUTED,
                                font=("Microsoft YaHei", 9))
        self.lbl_lap.pack(anchor="w", pady=(12, 4))
        self.bar_bg = tk.Frame(right, bg=PANEL2, height=8)
        self.bar_bg.pack(fill="x")
        self.bar_fg = tk.Frame(self.bar_bg, bg=CYAN, height=8)
        self.bar_fg.place(x=0, y=0, relheight=1, relwidth=0)

        self.btn_run = tk.Button(right, text="▶   开 始 跑", command=self.start,
                                 bg=GREEN, fg="white", activebackground="#16a34a",
                                 font=("Microsoft YaHei", 15, "bold"), relief="flat",
                                 height=2, cursor="hand2", bd=0)
        self.btn_run.pack(fill="x", pady=(18, 8))

        row = tk.Frame(right, bg=BG)
        row.pack(fill="x")
        self.btn_stop = tk.Button(row, text="■ 停止", command=self.stop, state="disabled",
                                  bg=PANEL2, fg=TEXT, activebackground="#243454",
                                  font=("Microsoft YaHei", 11), relief="flat", height=2, bd=0)
        self.btn_stop.pack(side="left", fill="x", expand=True, padx=(0, 6))
        tk.Button(row, text="📍 原地", command=self.stay_here, bg=PANEL2, fg=TEXT,
                  activebackground="#243454", font=("Microsoft YaHei", 11),
                  relief="flat", height=2, bd=0).pack(side="left", fill="x", expand=True, padx=(0, 6))
        tk.Button(row, text="⟲ 回起点", command=self.park, bg=PANEL2, fg=TEXT,
                  activebackground="#243454", font=("Microsoft YaHei", 11),
                  relief="flat", height=2, bd=0).pack(side="left", fill="x", expand=True)

        self.log = scrolledtext.ScrolledText(right, height=7, bg=PANEL, fg=MUTED,
                                             font=("Consolas", 9), relief="flat",
                                             insertbackground=TEXT, bd=0)
        self.log.pack(fill="both", expand=True, pady=(12, 0))

        self.q = queue.Queue()
        self.root.after(100, self.drain)
        self.root.after(33, self.tick)
        self.w("就绪：起点 = 终点 = %.6f, %.6f" % (START_LAT, START_LNG))
        self.w("鱼素材：" + ("已载入 fish.png" if self.map.sprite.ok else "未找到 fish.png，使用手绘矢量鱼"))
        # 启动时预置位到起点，避免开跑瞬移
        threading.Thread(target=self._preset_start, daemon=True).start()

    def _preset_start(self):
        try:
            locate(START_LAT, START_LNG)
            self.w("已预置位到起点")
        except Exception as e:
            self.w("预置位失败: %s" % e)

    def w(self, msg):
        self.q.put(msg)

    def drain(self):
        try:
            while True:
                self.log.insert("end", time.strftime("%H:%M:%S ") + self.q.get_nowait() + "\n")
                self.log.see("end")
        except queue.Empty:
            pass
        self.root.after(100, self.drain)

    def idx_at(self, elapsed):
        return max(0.0, min(float(len(ROUTE) - 1), elapsed * SPEED / SPEED))

    def tick(self):
        off = getattr(self, "_offset", 0)
        if self.running and self.t0:
            el = time.monotonic() - self.t0
            idx = min(off + len(ROUTE) - 1.0, off + el * HZ)
            self.frozen_idx = idx
        else:
            idx = self.frozen_idx
        self.map.draw_dynamic(idx)
        STEP = SPEED / HZ
        prog = max(0.0, idx - getattr(self, "_offset", 0))   # 已跑进度（从起跑点算）
        dist = min(TOTAL_M, prog * STEP)
        self.v_dist.set("%.0f" % dist)
        sec = int(prog / HZ)
        self.v_time.set("%02d:%02d" % (sec // 60, sec % 60))
        if dist > 25:
            self.v_pace.set("%d'%02d\"" % (PACE_SEC // 60, PACE_SEC % 60))
        lap = min(LAPS, int(dist / PER) + (1 if dist < TOTAL_M - 0.5 else 0))
        self.lbl_lap.config(text="第 %d / %d 圈" % (lap, LAPS))
        self.bar_fg.place_configure(relwidth=min(1.0, prog / max(1, len(ROUTE) - 1)))
        self.root.after(33, self.tick)

    def park(self):
        try:
            locate(START_LAT, START_LNG)
            self.cur_lat, self.cur_lng = START_LAT, START_LNG
            self.w("已回到起点")
        except Exception as e:
            self.w("回起点失败: %s" % e)

    def stay_here(self):
        """原地停留：立刻停止注入，把定位保持在当前点。
        注意：注入是一次性下发，停掉定时注入后会一直停在最后一次坐标。"""
        self.silent_stop = True
        self.stop_flag.set()
        self.running = False
        self.t0 = None
        idx = int(min(len(ROUTE) - 1, max(0, self.frozen_idx)))
        lat, lng = ROUTE[idx][1], ROUTE[idx][2]
        try:
            locate(lat, lng)
            self.cur_lat, self.cur_lng = lat, lng
            self.w("📍 原地停留：%.6f, %.6f" % (lat, lng))
        except Exception as e:
            self.w("原地停留失败: %s" % e)

    def _nearest_idx(self, lat, lng):
        """在轨迹上找距离 (lat,lng) 最近的点，返回 (序号, 距离米)"""
        kf = 111320.0 * math.cos(math.radians(lat))
        best, bestd = 0, 1e18
        for i, (d, la, ln) in enumerate(ROUTE):
            dy = (la - lat) * 111320.0
            dx = (ln - lng) * kf
            dd = dx * dx + dy * dy
            if dd < bestd:
                bestd, best = dd, i
        return best, math.sqrt(bestd)

    def start(self):
        if self.worker and self.worker.is_alive():
            return
        # 从当前位置就近接入轨迹：不瞬移，接着当前点跑完整一整圈数
        idx, dist = self._nearest_idx(self.cur_lat, self.cur_lng)
        if dist > 30.0:
            idx = 0                     # 离跑道太远（>30m）才回起点重开
            self.w("当前点距跑道 %.0fm，已改从起点起跑" % dist)
        else:
            self.w("从当前位置起跑（轨迹第 %d 点，偏 %.1fm）" % (idx, dist))
        self._offset = idx
        self.stop_flag.clear()
        self.running = True
        self.t0 = time.monotonic()
        self.frozen_idx = float(idx)
        self.btn_run.config(state="disabled", bg="#15803d")
        self.btn_stop.config(state="normal")
        self.worker = threading.Thread(target=self.run_route, daemon=True)
        self.worker.start()

    def stop(self):
        self.silent_stop = False
        self.stop_flag.set()
        self.running = False
        self.t0 = None
        self.btn_stop.config(state="disabled")
        self.w("收到停止指令…")

    def run_route(self):
        off = int(getattr(self, "_offset", 0))
        step = SPEED / HZ
        start_d = off * step
        self.w("开始：%.0f m（%.2f m/s ≈ %d'%02d\"/km，%dHz）"
               % (TOTAL_M, SPEED, PACE_SEC // 60, PACE_SEC % 60, HZ))
        ok = 0
        fail = 0
        finished = False
        # 起跑前把定位压在当前位置连发 2 次（共 0.3s）：够 App 记住基准点，
        # 又不会因为长时间静止把最低速度拉到 1.39 以下
        try:
            for _ in range(2):
                locate(self.cur_lat, self.cur_lng)
                time.sleep(0.15)
        except Exception as e:
            self.w("起跑定位失败: %s" % e)
        interval = 1.0 / HZ
        t_next = time.monotonic() + interval
        d = start_d
        # 起跑 2.5 秒平滑加速：第一档 0.62 → 1.67 m/s，已高于 1.39 下限，坐标始终在轨迹线上
        RAMP = [0.62, 0.70, 0.78, 0.87, 0.94]
        n_total = int(round(TOTAL_M / step))
        for i in range(n_total):
            if self.stop_flag.is_set():
                self.w("手动停止，已投喂 %d 点 / %.0f m" % (i, d - start_d))
                break
            lat, lng = to_geo(*route_point(d))
            sent = False
            for _ in range(2):          # 失败重试留 0.15s 间隔，立刻重发会造成瞬时速度尖峰
                try:
                    locate(lat, lng)
                    self.cur_lat, self.cur_lng = lat, lng
                    sent = True
                    break
                except Exception as e:
                    self.w("第 %d 点失败重试: %s" % (i, e))
                    time.sleep(0.15)
            if sent:
                ok += 1
            else:
                fail += 1
            d += step * (RAMP[i] if i < len(RAMP) else 1.0)
            # 绝对时间调度：不受单次注入耗时波动影响，周期稳定
            t_next += interval
            delay = t_next - time.monotonic()
            if delay > 0:
                time.sleep(delay)
            else:
                t_next = time.monotonic()   # 已落后则重新对齐
        else:
            finished = True
            self.w("完成：%d 点 / %.0f m%s" % (ok, d - start_d, ("，失败 %d 点" % fail) if fail else ""))
        self.root.after(0, lambda: self.done(finished, ok))

    def done(self, finished, ok):
        self.running = False
        self.t0 = None
        self.btn_stop.config(state="disabled")
        self.btn_run.config(state="normal", bg=GREEN)
        if finished:
            self.frozen_idx = getattr(self, "_offset", 0) + len(ROUTE) - 1.0
            # 跑完不要立刻回起点：App 可能仍在记录，那一跳瞬移会被算成 100+ m/s，
            # 直接触发 5.56 上限判无效。等 App 里点完「结束跑步」再手动点 ⟲ 回起点。
            self.w("跑完 %d 点 / %.0f m。请先在手机 App 点『结束跑步』提交，"
                   "提交完成后再点 ⟲ 回起点（现在回会被记成瞬移超速）" % (ok, TOTAL_M))
            return
        if self.silent_stop:      # 点了「原地」：停在当前位置，不弹窗
            self.silent_stop = False
            return
        self.ask_after(finished, ok)

    def ask_after(self, finished, ok):
        win = tk.Toplevel(self.root)
        win.title("停下位置")
        win.configure(bg=PANEL)
        win.transient(self.root)
        win.resizable(False, False)
        win.grab_set()
        title = "三圈跑完" if finished else "已手动停止"
        tk.Label(win, text=title, bg=PANEL, fg=TEXT,
                 font=("Microsoft YaHei", 15, "bold")).pack(padx=30, pady=(22, 4))
        tk.Label(win, text="想让定位停在哪里？", bg=PANEL, fg=MUTED,
                 font=("Microsoft YaHei", 10)).pack(padx=30)
        tk.Label(win, text="原地停：保持当前位置\n回起点：拉回 %.6f, %.6f" % (START_LAT, START_LNG),
                 bg=PANEL, fg=MUTED, font=("Consolas", 9), justify="left").pack(padx=30, pady=(8, 14), anchor="w")
        rw = tk.Frame(win, bg=PANEL)
        rw.pack(pady=(0, 20))

        def stay():
            win.destroy()
            self.btn_run.config(state="normal", bg=GREEN)
            self.w("选择：原地停留")

        def back():
            win.destroy()
            self.btn_run.config(state="normal", bg=GREEN)
            self.w("选择：回到起点")
            self.park()

        tk.Button(rw, text="📍 在原地停", command=stay, bg=PANEL2, fg=TEXT,
                  font=("Microsoft YaHei", 11), relief="flat", width=13, height=2, bd=0).pack(side="left", padx=7)
        tk.Button(rw, text="⟲ 回到起点", command=back, bg="#2563eb", fg="white",
                  font=("Microsoft YaHei", 11), relief="flat", width=13, height=2, bd=0).pack(side="left", padx=7)
        win.protocol("WM_DELETE_WINDOW", stay)
        win.update_idletasks()
        x = self.root.winfo_x() + (self.root.winfo_width() - win.winfo_width()) // 2
        y = self.root.winfo_y() + (self.root.winfo_height() - win.winfo_height()) // 2
        win.geometry("+%d+%d" % (max(0, x), max(0, y)))
        win.wait_window()


if __name__ == "__main__":
    root = tk.Tk()
    # 窗口图标：优先用同目录的 app.ico，缺了也不影响运行
    try:
        _ico = os.path.join(os.path.dirname(os.path.abspath(__file__)), "app.ico")
        if os.path.exists(_ico):
            root.iconbitmap(default=_ico)
    except Exception:
        pass
    App(root)
    # 启动后再强制归位一次：Windows 有时会把窗口恢复到屏幕外（-48000,-48000）
    def _place():
        try:
            root.geometry("1140x700+120+60")
            root.deiconify()
            root.lift()
        except Exception:
            pass
    root.after(250, _place)
    root.mainloop()
