# -*- coding: utf-8 -*-
"""face_feed.py —— 全屏置顶展示一张照片，供雷电「实时截取屏幕」相机源读取。
用法: python face_feed.py <图片路径>
按键: ESC/关闭窗口退出
"""
import sys, tkinter as tk
from PIL import Image, ImageTk

def main():
    if len(sys.argv) < 2:
        print("usage: face_feed.py <image>"); return
    path = sys.argv[1]
    img = Image.open(path).convert("RGB")

    root = tk.Tk()
    root.overrideredirect(True)          # 无边框
    root.geometry("%dx%d+0+0" % (root.winfo_screenwidth(), root.winfo_screenheight()))
    root.attributes("-topmost", True)
    root.configure(bg="black")
    root.lift()

    sw, sh = root.winfo_screenwidth(), root.winfo_screenheight()
    # 照片放大铺满屏幕高度（人脸尽量大，便于人脸检测）
    ratio = max(sw / img.width, sh / img.height)
    img = img.resize((int(img.width * ratio), int(img.height * ratio)), Image.LANCZOS)
    # 居中裁剪
    left = (img.width - sw) // 2
    top = (img.height - sh) // 2
    img = img.crop((left, top, left + sw, top + sh))

    ph = ImageTk.PhotoImage(img)
    cv = tk.Label(root, image=ph, bg="black")
    cv.pack(fill="both", expand=True)

    root.bind("<Escape>", lambda e: root.destroy())
    root.bind("<Button-1>", lambda e: root.destroy())
    root.focus_force()
    root.mainloop()
    print("face_feed closed")

if __name__ == "__main__":
    main()
