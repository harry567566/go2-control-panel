#!/usr/bin/env python3
"""Go2 Control Panel: control a Unitree Go2 robot dog from a Mac, by Ethernet cable or by Wi-Fi.

One window with a button for every step: connect, read the robot's state, take a photo, record data,
stand up, walk, turn, lie down, STOP. The right side explains the selected button and shows what the
program prints. The EN / 中文 switch changes the language.

    bash setup.sh                       (once)
    .venv/bin/python control_panel.py

Cable: the official Unitree SDK (DDS) over a USB-Ethernet cable. Needs a Go2 EDU.
Wi-Fi: WebRTC, the way the phone app talks to the dog (unitree_webrtc_connect). Go2 AIR, PRO or EDU.
Every button runs a small script in robot/, so everything also works from the command line.
"""
import os
import queue
import re
import socket
import subprocess
import sys
import threading
import time
import tkinter as tk
from tkinter import messagebox, scrolledtext

HERE = os.path.dirname(os.path.abspath(__file__))
ROBOT = os.path.join(HERE, "robot")
DATA = os.path.join(HERE, "data")
PY = os.path.join(HERE, ".venv", "bin", "python")  # made by setup.sh
FONT = "PingFang SC"  # Tk falls back to the system font where it is missing
MONO = "Menlo"
HAND = "pointinghand" if sys.platform == "darwin" else "hand2"
ROBOT_IP = "192.168.123.161"  # the dog's computer on its wired network
DOG_AP_IP = "192.168.12.1"    # the dog on its own Wi-Fi hotspot
ROUTES = [("cable", "Cable", "网线"), ("wifi", "Wi-Fi", "Wi-Fi")]


def cable_iface():
    """The Mac network card that has a 192.168.123.x address (set by 1-1 on the cable), or None."""
    try:
        out = subprocess.run(["ifconfig"], capture_output=True, text=True).stdout
    except OSError:
        return None
    card = None
    for line in out.splitlines():
        if line and not line[0].isspace():
            card = line.split(":")[0]
        elif line.strip().startswith("inet 192.168.123."):
            return card
    return None


def wifi_target():
    """'ap' (the Mac on the dog's own hotspot), or the dog's IP on a shared router, written in robot/.go2_wifi_ip."""
    path = os.path.join(ROBOT, ".go2_wifi_ip")
    ip = open(path).read().strip() if os.path.exists(path) else ""
    return ip or "ap"


def wifi_dog_ip(target):
    return DOG_AP_IP if target == "ap" else target


def mac_wifi_ip():
    """The Mac's own address on Wi-Fi ('' if none). On the dog's hotspot it is 192.168.12.x."""
    try:
        ports = subprocess.run(["networksetup", "-listallhardwareports"], capture_output=True, text=True).stdout
        dev = re.search(r"Hardware Port: Wi-Fi\nDevice: (\S+)", ports).group(1)
        return subprocess.run(["ipconfig", "getifaddr", dev], capture_output=True, text=True).stdout.strip()
    except (OSError, AttributeError):
        return ""


def dog_wifi_port_open(ip, timeout=1.5):
    """Does the dog's Wi-Fi control (WebRTC signaling) port answer? New firmware uses 9991, older 8081."""
    for port in (9991, 8081):
        try:
            with socket.create_connection((ip, port), timeout=timeout):
                return True
        except OSError:
            pass
    return False


def A(key, run, en, zh, limit=20, **kw):
    """One button. run = (script, arguments after the connection); the script is robot/<route>_<script>.
    en / zh = (label, what it does, what you will see, why). limit = seconds before the script is ended."""
    d = dict(key=key, run=run, limit=limit, **kw)
    for lang, (label, what, see, why) in (("en", en), ("zh", zh)):
        d[lang] = dict(label=label, what=what, see=see, why=why)
    return d


SECTIONS = [
    (("1  Connect and watch", "1  连接和查看", "safe: the dog does not move", "安全:狗不会动"), [
        A("r_net", None,
          ("1-1  Connect to the dog",
           "Cable: finds the Mac's USB-Ethernet port with the cable, gives it the address 192.168.123.222 on the "
           f"dog's network (macOS asks for your Mac password once) and pings the dog ({ROBOT_IP}). "
           "Wi-Fi: checks that the Mac is on the dog's Wi-Fi and that the dog answers.",
           "'ROBOT REACHABLE' (cable) or 'DOG REACHABLE over Wi-Fi'. The top right then says 'Dog connected' "
           "(green dot).",
           "The dog only answers on its own network: 192.168.123.x on the cable, or its own Wi-Fi."),
          ("1-1  连上狗",
           "网线:找到插着网线的 USB 转网口,给它一个狗那个网络里的地址 192.168.123.222(macOS 会要一次 Mac 开机密码),"
           f"然后 ping 狗({ROBOT_IP})。Wi-Fi:检查 Mac 是否连着狗的 Wi-Fi、狗有没有回应。",
           "'ROBOT REACHABLE'(网线)或 'DOG REACHABLE over Wi-Fi'。右上角变成 '狗:已连上'(绿点)。",
           "狗只在它自己的网络上回话:网线是 192.168.123.x,Wi-Fi 是狗自己的热点。")),
        A("r_state", ("state.py", "10"),
          ("1-2  Read robot state", "Listens to the robot's messages for 10 s. Sends nothing, so the robot "
           "does not move.", "Battery, body tilt, body height, sport mode, leg angles, foot forces, messages per "
           "second.", "Do this first, every time: it shows the connection works before anything moves."),
          ("1-2  读取狗的状态", "听狗发来的消息 10 秒。什么都不发,狗不会动。",
           "电池、身体倾斜、身体高度、运动模式、腿的角度、脚底受力、每秒多少条消息。",
           "每次都先做这一步:在任何动作之前,先确认连接是通的。")),
        A("r_photo", ("photo.py", "{photo}"),
          ("1-3  Take a photo", "Asks the robot's front camera for one image.",
           "The photo opens on the Mac and is saved in data/photos/.", "Read-only; the robot does not move."),
          ("1-3  拍一张照片", "让狗的前置摄像头拍一张照片。", "照片会在 Mac 上打开,并存到 data/photos/。",
           "只读,狗不会动。")),
        A("r_record", ("record.py", "--secs", "20", "--fps", "5", "--out", "{run}"),
          ("1-4  Record data 20 s", "Records camera frames and robot state for 20 s. Someone can walk the dog "
           "with the remote while it records.", "The recording is saved in data/ and the folder opens: "
           "frame_XXXX.jpg, frames.csv, state.csv.", "Read-only. Useful data for vision or control projects."),
          ("1-4  录 20 秒数据", "录 20 秒摄像头画面和狗的状态。录的时候可以有人用遥控器遛狗。",
           "录好的数据存在 data/,并打开文件夹:frame_XXXX.jpg、frames.csv、state.csv。",
           "只读。可以给视觉或控制的作业用。"), limit=45),
    ]),
    (("2  Move the dog", "2  让狗动", "only with the instructor, 2 m clear around the dog",
      "只在老师在场、狗周围 2 米没人没东西时"), [
        A("m_standup", ("sport.py", "standup", "--yes"),
          ("2-1  Stand up", "Sends StandUp to the robot's own controller.", "The dog stands up and holds still.",
           "The program only says WHAT to do. The dog's built-in controller decides how to move the 12 motors."),
          ("2-1  站起来", "给狗自带的控制器发 StandUp。", "狗站起来,保持不动。",
           "程序只说'做什么',怎么动 12 个电机由狗自带的控制器决定。"), motion=True),
        A("m_balance", ("sport.py", "balance", "--yes"),
          ("2-2  Balance stand", "BalanceStand: stand and keep balance, ready to walk.",
           "The dog stands and makes small balancing movements.", "Do this after Stand up and before walking."),
          ("2-2  平衡站立", "BalanceStand:站着保持平衡,准备走路。", "狗站着,会轻微调整。", "站起来之后、走路之前做这一步。"),
          motion=True),
        A("m_walk", ("sport.py", "move", "0.2", "0", "0", "2", "--yes"),
          ("2-3  Walk forward 0.2 m/s, 2 s", "Move(0.2, 0, 0), re-sent 20 times a second for 2 seconds, then "
           "StopMove.", "The dog walks about 40 cm forward and stops.",
           "Speed and time are limited in the script: at most 0.3 m/s and 3 s."),
          ("2-3  往前走 2 秒(0.2 米/秒)", "Move(0.2, 0, 0),每秒重发 20 次,持续 2 秒,然后 StopMove。",
           "狗往前走大约 40 厘米然后停。", "脚本里限制了速度和时间:最多 0.3 米/秒、3 秒。"), motion=True),
        A("m_turn", ("sport.py", "move", "0", "0", "0.3", "2", "--yes"),
          ("2-4  Turn left slowly, 2 s", "Move(0, 0, 0.3) for 2 seconds, then StopMove.",
           "The dog turns left on the spot, about 35 degrees.", ""),
          ("2-4  原地慢慢左转 2 秒", "Move(0, 0, 0.3) 持续 2 秒,然后 StopMove。", "狗原地左转大约 35 度。", ""),
          motion=True),
        A("m_standdown", ("sport.py", "standdown", "--yes"),
          ("2-5  Lie down", "StandDown: the dog lowers its body to the ground.", "The dog lies down.",
           "The safe way to finish. Do this before Damp."),
          ("2-5  趴下", "StandDown:狗把身体放低到地上。", "狗趴下。", "结束时的安全做法,要在 Damp 之前做。"), motion=True),
        A("m_stop", None,
          ("■  STOP moving", "Ends any motion command still running, then sends StopMove. Always allowed, no "
           "questions asked.", "The dog stops walking and stands.",
           "Your first button if anything looks wrong. Emergency: L2 + B on the remote makes all motors go soft "
           "(the dog sinks to the ground); on Wi-Fi it acts faster than this button."),
          ("■  停止运动", "先掐掉还在运行的运动命令,再发 StopMove。随时可以按,不会弹窗。", "狗停下,站着。",
           "看到任何不对劲,第一个按这个。紧急情况:遥控器上按 L2 + B,所有电机会变软(狗会趴到地上);"
           "在 Wi-Fi 下它比这个按钮更快。")),
        A("m_damp", ("sport.py", "damp", "--yes"),
          ("Damp (motors go soft)", "Damp: all motors go limp. If the dog is standing it will DROP to the ground.",
           "The dog collapses and its legs go loose.", "Only after 'Lie down', or if the instructor says so."),
          ("Damp(电机放松)", "Damp:所有电机变软。如果狗是站着的,会直接摔到地上。", "狗瘫下去,腿变软。",
           "只在'趴下'之后用,或者老师让你用的时候。"),
          motion=True, confirm=("DAMP makes all motors go limp. A standing dog will DROP.\n\nIs the dog already lying down?",
                                "DAMP 会让所有电机变软,站着的狗会直接摔下来。\n\n狗已经趴下了吗?")),
    ]),
]

NOISE = ("multicast", "Warning", "warn(", "warnings.warn", "🕒")
UI = {  # small interface texts
    "title": ("Go2 Control Panel", "Go2 控制面板"),
    "tagline": ("Control a Unitree Go2 from this Mac, by Ethernet cable or by Wi-Fi.",
                "用这台 Mac 控制 Unitree Go2,网线或 Wi-Fi 都行。"),
    "allow": ("Allow motion: the instructor is here and 2 m around the dog is clear",
              "允许运动:老师在场,狗周围 2 米没人没东西"),
    "stopall": ("Close programs opened by this panel", "关掉面板打开的程序"),
    "output": ("Program output", "程序输出"),
    "clear": ("Clear", "清空"),
    "route": ("Connection:", "连接方式:"),
    "route_h": ("Connection to the dog", "连狗的方式"),
    "route_txt": ("Cable: Python on this Mac talks to the dog over a USB-Ethernet cable with the official Unitree "
                  "SDK. Needs a Go2 EDU. The Mac's Wi-Fi stays free for the internet.\n\n"
                  "Wi-Fi: the Mac joins the dog's own Wi-Fi and talks to it the way the phone app does (WebRTC). "
                  "Works on Go2 AIR, PRO and EDU. Close the phone app first: the dog takes one Wi-Fi client at a time, "
                  "so click one button at a time and wait for 'done' (or 'failed'). Firmware 1.1.15 or newer needs the dog's AES key "
                  "in robot/.go2_aes_key (see the README). On the dog's Wi-Fi the Mac has no internet, unless a phone "
                  "is connected by USB with its hotspot on.",
                  "网线:Mac 上的 Python 用 Unitree 官方 SDK,通过 USB 转网口的网线和狗通信。需要 Go2 EDU。"
                  "Mac 的 Wi-Fi 空着,可以继续上网。\n\n"
                  "Wi-Fi:Mac 连上狗自己的 Wi-Fi,用手机 App 同样的方式(WebRTC)和狗通信。AIR、PRO、EDU 都行。"
                  "先关掉手机 App:狗一次只接受一个 Wi-Fi 连接,所以一次只点一个按钮,等显示'完成'(或'失败')再点下一个。"
                  "固件 1.1.15 或更新需要狗的 AES 密钥(放在 robot/.go2_aes_key,见 README)。连着狗的 Wi-Fi 时 Mac "
                  "没有外网,除非用数据线连手机并打开热点。"),
    "where": ("Runs on: this Mac -> the dog, by the connection chosen at the top of box 1",
              "在哪跑:这台 Mac → 狗,走方框 1 顶上选的连接方式"),
    "what": ("What it does:  ", "在做什么:"), "see": ("You will see:  ", "你会看到:"), "why": ("Why:  ", "原理:"),
    "moves": ("This moves the real robot.", "这会让真狗动起来。"),
    "need_allow": ("Tick 'Allow motion' first.", "请先勾选 '允许运动'。"),
    "confirm_motion": ("The dog will MOVE: {label}.\n\nIs the instructor here and is the area 2 m around the dog clear?",
                       "狗要动了:{label}。\n\n老师在场吗?狗周围 2 米内没有人和东西吗?"),
}


# --- look ---------------------------------------------------------------------------------------
# Every color is set here by hand. Left to the system, macOS dark mode turns the default text white,
# which is unreadable on the light cards.
C = dict(
    bg="#EDF0F4", card="#FFFFFF", line="#D5DAE1", text="#1B1F24", muted="#5F6873",
    btn="#F3F5F8", btn_hover="#E3E8EF", btn_down="#D3DAE4",
    accent="#1F5FBF", accent_soft="#E8F0FC",
    move="#FFF1DC", move_hover="#FFE2B8", move_text="#7A4100",
    off="#F1F2F4", off_text="#6B7480",
    danger="#D92D20", danger_hover="#B42318", danger_soft="#FDECEA", danger_soft_hover="#F9D6D1",
    ok="#12A150", warn="#B86E00", err="#D92D20", idle="#8A94A0",
    console="#111827", console_text="#E5E7EB",
)
# style -> (background, background under the mouse, text color, number color)
BTN = {
    "normal": (C["btn"], C["btn_hover"], C["text"], C["accent"]),
    "move": (C["move"], C["move_hover"], C["move_text"], C["move_text"]),
    "danger": (C["danger"], C["danger_hover"], "#FFFFFF", "#FFFFFF"),
    "danger_soft": (C["danger_soft"], C["danger_soft_hover"], C["danger_hover"], C["danger_hover"]),
}


def inside(widget, other):
    """Is `other` the widget itself or one of its children?"""
    if other is None:
        return False
    w, o = str(widget), str(other)
    return o == w or o.startswith(w + ".")


class FlatButton(tk.Frame):
    """A button drawn with labels, so it looks the same in light and dark mode (native Mac buttons ignore colors).
    A label like "1-5  Stand up" is shown as a small step number plus the text."""

    def __init__(self, parent, command, style="normal", size=13, bold=False, pady=7):
        super().__init__(parent, bg=C["line"], padx=1, pady=1, cursor=HAND)
        self.command, self.style, self.enabled, self.hover = command, style, True, False
        self.body = tk.Frame(self, cursor=HAND)
        self.body.pack(fill="both", expand=True)
        self.num = tk.Label(self.body, font=(FONT, size - 1, "bold"), anchor="w", cursor=HAND)
        self.text = tk.Label(self.body, font=(FONT, size, "bold" if bold else "normal"), anchor="w",
                             justify="left", wraplength=310, cursor=HAND)
        self.text.pack(side="left", fill="x", expand=True, padx=(12, 10), pady=pady)
        for w in (self, self.body, self.num, self.text):
            w.bind("<Enter>", self._enter)
            w.bind("<Leave>", self._leave)
            w.bind("<ButtonPress-1>", self._press)
            w.bind("<ButtonRelease-1>", self._release)
        self._paint()

    def set_label(self, label):
        num, _, rest = label.partition("  ")
        if rest and (num[0].isdigit() or num == "■"):
            self.num.config(text=num, width=4 if num[0].isdigit() else 2)
            self.num.pack(side="left", padx=(12, 0), before=self.text)
            self.text.config(text=rest)
            self.text.pack_configure(padx=(4, 10))
        else:
            self.num.pack_forget()
            self.text.config(text=label)
            self.text.pack_configure(padx=(12, 10))

    def set_enabled(self, on):
        self.enabled = on
        for w in (self, self.body, self.num, self.text):
            w.config(cursor=HAND if on else "")
        self._paint()

    def _paint(self, down=False):
        bg, hover, fg, num = BTN[self.style]
        if not self.enabled:
            bg, fg, num = C["off"], C["off_text"], C["off_text"]
        elif down:
            bg = C["btn_down"] if self.style == "normal" else hover
        elif self.hover:
            bg = hover
        for w in (self.body, self.num, self.text):
            w.config(bg=bg)
        self.text.config(fg=fg)
        self.num.config(fg=num)

    def _enter(self, _):
        self.hover = True
        self._paint()

    def _leave(self, _):
        x, y = self.winfo_pointerxy()
        self.hover = inside(self, self.winfo_containing(x, y))
        self._paint()

    def _press(self, _):
        if self.enabled:
            self._paint(down=True)

    def _release(self, _):
        x, y = self.winfo_pointerxy()
        self._paint()
        if inside(self, self.winfo_containing(x, y)):  # run() explains why a greyed-out button does nothing
            self.command()


class Toggle(tk.Frame):
    """A check box drawn with labels (same reason as FlatButton). get() / set() like a BooleanVar."""

    def __init__(self, parent, command, on_bg, on_fg, size=12, bg=C["card"]):
        super().__init__(parent, cursor=HAND)
        self.command, self.value, self.bg = command, False, bg
        self.on_bg, self.on_fg = on_bg, on_fg
        self.box = tk.Canvas(self, width=18, height=18, highlightthickness=0, bd=0, cursor=HAND)
        self.box.pack(side="left", padx=(8, 6), pady=4)
        self.text = tk.Label(self, font=(FONT, size), anchor="w", justify="left", wraplength=320, cursor=HAND)
        self.text.pack(side="left", fill="x", expand=True, padx=(0, 8), pady=4)
        for w in (self, self.box, self.text):
            w.bind("<ButtonRelease-1>", self._click)
        self._paint()

    def get(self):
        return self.value

    def set(self, value):
        self.value = bool(value)
        self._paint()

    def set_label(self, text):
        self.text.config(text=text)

    def _click(self, _):
        x, y = self.winfo_pointerxy()
        if inside(self, self.winfo_containing(x, y)):
            self.set(not self.value)
            self.command()

    def _paint(self):
        bg, fg = (self.on_bg, self.on_fg) if self.value else (self.bg, C["muted"])
        for w in (self, self.box, self.text):
            w.config(bg=bg)
        self.box.delete("all")
        if self.value:  # filled box with a white tick
            self.box.create_rectangle(1, 1, 17, 17, fill=self.on_fg, outline=self.on_fg)
            self.box.create_line(4, 9, 8, 13, 14, 5, fill="#FFFFFF", width=2)
        else:
            self.box.create_rectangle(1, 1, 17, 17, fill="#FFFFFF", outline=C["muted"], width=1.5)
        self.text.config(fg=fg)


class Segmented(tk.Frame):
    """A row of options where exactly one is chosen, like the EN / 中文 switch. options = [(code, English, 中文)]."""

    def __init__(self, parent, options, command):
        super().__init__(parent, bg=C["line"], padx=1, pady=1)
        self.command, self.value, self.labels = command, options[0][0], {}
        for code, en, zh in options:
            b = tk.Label(self, font=(FONT, 12, "bold"), padx=10, pady=3, cursor=HAND)
            b.pack(side="left", padx=(0, 1))
            b.bind("<ButtonRelease-1>", lambda e, c=code, b=b: self._release(c, b))
            self.labels[code] = (b, en, zh)
        self._paint()

    def get(self):
        return self.value

    def set_lang(self, lang):
        for b, en, zh in self.labels.values():
            b.config(text=en if lang == "en" else zh)

    def _release(self, code, b):
        x, y = b.winfo_pointerxy()
        if inside(b, b.winfo_containing(x, y)) and code != self.value:
            self.value = code
            self._paint()
            self.command()

    def _paint(self):
        for code, (b, _, _) in self.labels.items():
            on = code == self.value
            b.config(bg=C["accent"] if on else C["card"], fg="#FFFFFF" if on else C["text"])


class Chip(tk.Frame):
    """A status light: a colored dot and a short text."""

    def __init__(self, parent):
        super().__init__(parent, bg=C["line"], padx=1, pady=1)
        inner = tk.Frame(self, bg=C["card"])
        inner.pack()
        self.dot = tk.Label(inner, text="●", font=(FONT, 12), bg=C["card"], fg=C["idle"])
        self.dot.pack(side="left", padx=(10, 3), pady=3)
        self.text = tk.Label(inner, font=(FONT, 12), bg=C["card"], fg=C["text"])
        self.text.pack(side="left", padx=(0, 10), pady=3)

    def set(self, color, text):
        self.dot.config(fg=color)
        self.text.config(text=text)


def card(parent, **pack):
    """A white box with a thin border. Returns the inside frame."""
    outer = tk.Frame(parent, bg=C["line"], padx=1, pady=1)
    outer.pack(**pack)
    inner = tk.Frame(outer, bg=C["card"], padx=14, pady=12)
    inner.pack(fill="both", expand=True)
    return inner


INTRO = [  # (text style, English, Chinese) for the start page
    ("h", "How to use\n", "怎么用\n"),
    (None, "A click on the left runs that button right away. This card explains it, and the dark box below shows "
           "what the program prints.\n",
     "点左边的按钮会马上运行;这里解释它在做什么,下面的黑框是程序的输出。\n"),
    ("k", "By cable (Go2 EDU):  ", "用网线(Go2 EDU):"),
    (None, "plug a USB-C to Ethernet adapter into the Mac and the cable into the dog, turn the dog on and wait "
           "1 minute. Choose Cable at the top of box 1, click 1-1, then 1-2.\n",
     "USB-C 转网口插到 Mac 上,网线接到狗身上,狗开机后等 1 分钟。在方框 1 顶上选网线,点 1-1,再点 1-2。\n"),
    ("k", "By Wi-Fi (any Go2):  ", "用 Wi-Fi(任何 Go2):"),
    (None, "close the Unitree phone app and join the dog's Wi-Fi (Wi-Fi menu, top right of the screen). Choose "
           "Wi-Fi, click 1-1, then 1-2. One button at a time.\n",
     "关掉手机上的 Unitree App,在屏幕右上角的 Wi-Fi 菜单里连上狗的 Wi-Fi。选 Wi-Fi,点 1-1,再点 1-2。"
     "一次只点一个按钮。\n"),
    ("k", "Moving the dog, only with the instructor:  ", "让狗动(只在老师在场时):"),
    (None, "tick 'Allow motion', then 2-1 Stand up -> 2-2 Balance stand -> 2-3 Walk -> 2-5 Lie down.\n",
     "勾选 '允许运动',再按 2-1 站起来 → 2-2 平衡站立 → 2-3 走 → 2-5 趴下。\n"),
    ("warn", "The red STOP (top right) is always there. Emergency: L2 + B on the remote makes all motors go soft.",
     "右上角红色的「停止」随时能按。紧急情况:遥控器上按 L2 + B,所有电机会变软。"),
]


class Panel:
    def __init__(self, root):
        self.root = root
        self.lang = "en"
        self.route = "cable"  # plain copies of the switches, for the background threads
        self.q = queue.Queue()
        self.procs = []
        self.buttons = {}  # key -> list of (FlatButton, action); STOP has two buttons
        self.current = None
        self.status = ("?", "")
        self.closing = False
        try:  # always draw this window in light mode, whatever the system setting
            root.tk.call("::tk::unsupported::MacWindowStyle", "appearance", root, "aqua")
        except tk.TclError:
            pass
        w, h = min(1320, root.winfo_screenwidth() - 60), min(880, root.winfo_screenheight() - 90)
        root.geometry(f"{w}x{h}")
        root.minsize(1100, 640)
        root.configure(bg=C["bg"])
        icon = os.path.join(HERE, "tools", "panel_icon.png")  # also the Dock icon
        if os.path.exists(icon):
            self.icon = tk.PhotoImage(file=icon)
            root.iconphoto(True, self.icon)
        actions = {a["key"]: a for _, items in SECTIONS for a in items}

        # ---- top bar: title, language, status light, STOP -------------------------------------
        top = tk.Frame(root, bg=C["card"])
        top.pack(fill="x")
        tk.Frame(root, bg=C["line"], height=1).pack(fill="x")
        row = tk.Frame(top, bg=C["card"])
        row.pack(fill="x", padx=20, pady=(12, 0))
        self.title_lbl = tk.Label(row, font=(FONT, 21, "bold"), bg=C["card"], fg=C["text"])
        self.title_lbl.pack(side="left")
        self.lang_seg = Segmented(row, [("en", "EN", "EN"), ("zh", "中文", "中文")], self.lang_changed)
        self.lang_seg.pack(side="left", padx=16, pady=(4, 0))
        stop = actions["m_stop"]
        self.top_stop = FlatButton(row, lambda: self.run(stop), style="danger", size=16, bold=True, pady=8)
        self.top_stop.pack(side="right", padx=(10, 0))
        self.buttons["m_stop"] = [(self.top_stop, stop)]
        self.chip = Chip(row)
        self.chip.pack(side="right")
        self.tag_lbl = tk.Label(top, font=(FONT, 12), bg=C["card"], fg=C["muted"], anchor="w")
        self.tag_lbl.pack(fill="x", padx=20, pady=(2, 12))

        # ---- body: buttons on the left, explanation and output on the right -------------------
        body = tk.Frame(root, bg=C["bg"])
        body.pack(fill="both", expand=True, padx=16, pady=14)
        self.left_outer = tk.Frame(body, bg=C["bg"])
        self.left_outer.pack(side="left", fill="y")
        self.canvas = tk.Canvas(self.left_outer, width=430, bg=C["bg"], highlightthickness=0, bd=0,
                                yscrollincrement=15)
        sb = tk.Scrollbar(self.left_outer, orient="vertical", command=self.canvas.yview)
        left = tk.Frame(self.canvas, bg=C["bg"])
        win = self.canvas.create_window((0, 0), window=left, anchor="nw")
        left.bind("<Configure>", lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.bind("<Configure>", lambda e: self.canvas.itemconfigure(win, width=e.width))
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="y")
        sb.pack(side="left", fill="y", padx=(4, 0))
        for ev in ("<MouseWheel>", "<Button-4>", "<Button-5>"):
            root.bind_all(ev, self.wheel)

        self.section_lbls = []
        for (t_en, t_zh, s_en, s_zh), items in SECTIONS:
            box = card(left, fill="x", pady=(0, 12))
            title = tk.Label(box, font=(FONT, 15, "bold"), bg=C["card"], fg=C["text"], anchor="w")
            title.pack(fill="x")
            sub = tk.Label(box, font=(FONT, 11), bg=C["card"], fg=C["muted"], anchor="w", justify="left",
                           wraplength=390)
            sub.pack(fill="x", pady=(0, 8))
            self.section_lbls.append((title, sub, t_en, t_zh, s_en, s_zh))
            if items[0]["key"] == "r_net":
                route_row = tk.Frame(box, bg=C["card"])
                route_row.pack(fill="x", pady=(0, 8))
                self.route_lbl = tk.Label(route_row, font=(FONT, 11), bg=C["card"], fg=C["muted"])
                self.route_lbl.pack(side="left", padx=(0, 8))
                self.route_seg = Segmented(route_row, ROUTES, self.route_changed)
                self.route_seg.pack(side="left")
            if items[0]["key"] == "m_standup":
                self.allow = Toggle(box, self.refresh_motion, on_bg=C["move"], on_fg=C["move_text"], size=12)
                self.allow.pack(fill="x", pady=(0, 6))
            for a in items:
                style = ("danger" if a["key"] == "m_stop" else "danger_soft" if a["key"] == "m_damp"
                         else "move" if a.get("motion") else "normal")
                b = FlatButton(box, lambda a=a: self.run(a), style=style, bold=a["key"] == "m_stop")
                b.pack(fill="x", pady=2)
                self.buttons.setdefault(a["key"], []).append((b, a))
        self.stop_btn = FlatButton(left, self.stop_all, size=12)
        self.stop_btn.pack(fill="x", pady=(0, 12))

        right = tk.Frame(body, bg=C["bg"])
        right.pack(side="left", fill="both", expand=True, padx=(16, 0))
        ebox = card(right, fill="x")
        self.explain = tk.Text(ebox, height=15, wrap="word", font=(FONT, 14), relief="flat", bd=0,
                               bg=C["card"], fg=C["text"], highlightthickness=0, padx=4, pady=2,
                               spacing1=2, spacing3=4, cursor="arrow")
        self.explain.pack(fill="x")
        self.explain.tag_configure("h", font=(FONT, 19, "bold"), foreground=C["text"], spacing3=6)
        self.explain.tag_configure("where", font=(FONT, 12), foreground=C["muted"], spacing3=10)
        self.explain.tag_configure("k", font=(FONT, 14, "bold"), foreground=C["accent"], spacing1=10)
        self.explain.tag_configure("warn", font=(FONT, 14, "bold"), foreground=C["danger"], spacing1=10)
        self.explain.tag_configure("step", lmargin1=14, lmargin2=34)

        obox = card(right, fill="both", expand=True, pady=(12, 0))
        orow = tk.Frame(obox, bg=C["card"])
        orow.pack(fill="x", pady=(0, 8))
        self.out_lbl = tk.Label(orow, font=(FONT, 14, "bold"), bg=C["card"], fg=C["text"])
        self.out_lbl.pack(side="left")
        self.clear_btn = FlatButton(orow, lambda: self.log.delete("1.0", "end"), size=11, pady=2)
        self.clear_btn.pack(side="right")
        self.log = scrolledtext.ScrolledText(obox, wrap="word", font=(MONO, 12), bg=C["console"],
                                             fg=C["console_text"], insertbackground=C["console_text"],
                                             relief="flat", bd=0, highlightthickness=0, padx=12, pady=10)
        self.log.configure(selectbackground="#3A4A66", inactiveselectbackground="#3A4A66", selectforeground="#FFFFFF")
        self.log.pack(fill="both", expand=True)
        for tag, col in (("info", "#7DD3FC"), ("bad", "#FCA5A5")):
            self.log.tag_configure(tag, foreground=col)
        self.apply_lang()
        self.root.after(60, self.pump)
        threading.Thread(target=self.watch, daemon=True).start()
        root.protocol("WM_DELETE_WINDOW", self.quit)
        root.createcommand("::tk::mac::Quit", self.quit)  # Cmd+Q and Dock > Quit

    def wheel(self, e):
        """Mouse wheel / trackpad: scroll the button list, but only while the pointer is over it."""
        x, y = self.root.winfo_pointerxy()
        if not inside(self.left_outer, self.root.winfo_containing(x, y)):
            return
        if e.num in (4, 5):  # Linux
            step = -3 if e.num == 4 else 3
        elif sys.platform == "darwin":
            if e.state & 0x1:  # Shift is set for a sideways trackpad swipe
                return
            step = -e.delta
        else:
            step = -(e.delta // 120) * 3
        self.canvas.yview_scroll(step, "units")

    # ------------------------------------------------------------------ language
    def t(self, key):
        en, zh = UI[key]
        return en if self.lang == "en" else zh

    def tt(self, en, zh):
        return en if self.lang == "en" else zh

    def lang_changed(self):
        self.lang = self.lang_seg.get()
        self.apply_lang()

    def apply_lang(self):
        self.root.title(self.t("title"))
        self.title_lbl.config(text=self.t("title"))
        self.tag_lbl.config(text=self.t("tagline"))
        self.lang_seg.set_lang(self.lang)
        for title, sub, t_en, t_zh, s_en, s_zh in self.section_lbls:
            title.config(text=t_en if self.lang == "en" else t_zh)
            sub.config(text=s_en if self.lang == "en" else s_zh)
        for pairs in self.buttons.values():
            for b, a in pairs:
                b.set_label(a[self.lang]["label"])
        self.top_stop.set_label("■  " + self.tt("STOP", "停止"))
        self.allow.set_label(self.t("allow"))
        self.route_lbl.config(text=self.t("route"))
        self.route_seg.set_lang(self.lang)
        self.stop_btn.set_label(self.t("stopall"))
        self.clear_btn.set_label(self.t("clear"))
        self.out_lbl.config(text=self.t("output"))
        self.refresh_motion()
        self.show_status()
        if self.current:
            self.show(self.current)
        else:
            self.show_intro()

    def refresh_motion(self):
        for pairs in self.buttons.values():
            for b, a in pairs:
                if a.get("motion"):
                    b.set_enabled(self.allow.get())

    def route_changed(self):
        self.route = self.route_seg.get()
        self.current = None
        self.fill([("h", self.t("route_h") + "\n"), (None, self.t("route_txt"))])

    def fill(self, parts):
        e = self.explain
        e.config(state="normal", wrap="char" if self.lang == "zh" else "word")
        e.delete("1.0", "end")
        for tag, text in parts:
            e.insert("end", text, tag)
        e.config(state="disabled")

    def show_intro(self):
        self.fill([(tag, en if self.lang == "en" else zh) for tag, en, zh in INTRO])

    def show(self, a):
        self.current = a
        d = a[self.lang]
        parts = [("h", d["label"].strip() + "\n"), ("where", self.t("where") + "\n")]
        for k in ("what", "see", "why"):
            if d[k]:
                parts += [("k", self.t(k)), (None, d[k] + "\n")]
        if a.get("motion"):
            parts.append(("warn", "\n" + self.t("moves") + "\n"))
        self.fill(parts)

    def write(self, line, tag=None):
        self.log.insert("end", line + "\n", tag)
        self.log.see("end")

    # ------------------------------------------------------------------ running
    def run(self, a):
        self.show(a)
        label = a[self.lang]["label"].strip()
        if a.get("motion") and not self.allow.get():
            self.write(self.t("need_allow"), "bad")
            return
        if a.get("motion") or a.get("confirm"):
            text = a["confirm"][0 if self.lang == "en" else 1] if a.get("confirm") else \
                self.t("confirm_motion").format(label=label)
            if not messagebox.askyesno(label, text, icon="warning", default="no", parent=self.root):
                return
        self.write(f"\n▶ {label}", "info")
        threading.Thread(target=self.run_robot, args=(a, label, self.route), daemon=True).start()

    def start(self, cmd, a, label, after=None, limit=None, wifi=False):
        """Start a program and stream what it prints into the dark box. Safe to call from any thread."""
        env = dict(os.environ, GO2_LANG=self.lang, PYTHONUNBUFFERED="1")  # scripts answer in the panel's language
        try:
            p = subprocess.Popen(cmd, cwd=HERE, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                 bufsize=1)
        except OSError as err:
            self.q.put(("line", f"✗ could not start: {err}", "bad"))
            return
        p.key, p.wifi = a["key"], wifi
        self.procs.append(p)
        if limit:  # end it after `limit` seconds (SIGTERM; a walk command still sends StopMove)
            timer = threading.Timer(limit, lambda: p.poll() is None and p.terminate())
            timer.daemon = True  # does not keep the program alive after the window is closed
            timer.start()
        threading.Thread(target=self.reader, args=(p, label, after), daemon=True).start()

    def bad(self, en, zh):
        self.q.put(("line", self.tt(en, zh), "bad"))

    def run_robot(self, a, label, route):
        """Every robot button: check the connection, then run robot/<route>_<script> with the right arguments."""
        if a["key"] == "r_net":
            target = wifi_target()
            cmd = (["bash", "robot/cable_check.sh"] if route == "cable" else
                   ["bash", "robot/wifi_check.sh"] + ([] if target == "ap" else [target]))
            self.start(cmd, a, label)
            return
        if not os.path.exists(PY):
            self.bad("The Python environment is missing: run  bash setup.sh  in this folder, then restart the panel.",
                     "还没装好环境:在这个文件夹里运行 bash setup.sh,再重新打开面板。")
            return
        if route == "wifi":
            self.run_wifi(a, label)
        else:
            self.run_cable(a, label)

    def end_motion(self, running, pattern):
        """End motion commands still running: a walk sends StopMove on its way out, and a command that has not
        gone out yet is not sent at all (the scripts check for STOP before sending)."""
        for p in running:
            if p.key in ("m_standup", "m_balance", "m_walk", "m_turn"):
                p.terminate()
                self.q.put(("line", self.tt("  ended the running motion command", "  已掐掉正在运行的运动命令"),
                            "info"))
        subprocess.run(["pkill", "-f", pattern])

    def script_cmd(self, a, route, conn):
        """[python, robot/<route>_<script>, <connection>, args...] plus what to open when it has finished."""
        stamp = time.strftime("%Y%m%d_%H%M%S")
        photo = os.path.join(DATA, "photos", f"photo_{stamp}.jpg")
        run_dir = os.path.join(DATA, f"{route}_run_{stamp}")
        os.makedirs(os.path.dirname(photo), exist_ok=True)
        script, *args = a["run"]
        args = [x.replace("{photo}", photo).replace("{run}", run_dir) for x in args]
        after = ["open", photo] if "{photo}" in a["run"] else ["open", run_dir] if "{run}" in a["run"] else None
        return [PY, "-u", os.path.join(ROBOT, f"{route}_{script}"), conn, *args], after

    def run_cable(self, a, label):
        """Robot buttons over the Ethernet cable (official Unitree SDK, DDS)."""
        iface = cable_iface()
        if a["key"] == "m_stop":
            self.end_motion([p for p in self.procs if p.poll() is None], "[c]able_sport.py .* (standup|balance|move)")
            if not iface:
                self.bad("The Mac is not connected to the dog by cable. Use the remote: L2 + B.",
                         "Mac 没用网线连上狗,用遥控器 L2 + B 停狗。")
                return
            self.start([PY, "-u", os.path.join(ROBOT, "cable_sport.py"), iface, "stop", "--yes"], a, label, limit=15)
            return
        if not iface:
            self.bad("The Mac is not connected to the dog by cable yet: click 1-1 Connect to the dog first.",
                     "Mac 还没用网线连上狗:先点 1-1。")
            return
        if subprocess.run(["ping", "-c", "1", "-t", "1", ROBOT_IP], capture_output=True).returncode != 0:
            self.bad(f"Cannot reach the dog at {ROBOT_IP} on {iface}: check the cable and that the dog is on.",
                     "连不上狗:检查网线和狗有没有开机。")
            return
        cmd, after = self.script_cmd(a, "cable", iface)
        self.start(cmd, a, label, after=after, limit=a["limit"])

    def run_wifi(self, a, label):
        """Robot buttons over Wi-Fi (WebRTC, like the phone app). The dog takes one Wi-Fi client at a time."""
        target = wifi_target()
        busy = [p for p in self.procs if p.wifi and p.poll() is None]
        if a["key"] == "m_stop":
            self.end_motion(busy, "[w]ifi_sport.py .* (standup|balance|move)")
            t0 = time.time()  # give them a moment to hang up, since the dog takes one Wi-Fi client
            while any(p.poll() is None for p in busy) and time.time() - t0 < 6:
                time.sleep(0.1)
            self.start([PY, "-u", os.path.join(ROBOT, "wifi_sport.py"), target, "stop", "--yes"], a, label,
                       limit=30, wifi=True)
            return
        if busy:
            self.bad("Wait for the running Wi-Fi command to finish: the dog accepts one Wi-Fi client at a time.",
                     "等上一个 Wi-Fi 命令结束:狗一次只接受一个 Wi-Fi 连接。")
            return
        if target == "ap" and not mac_wifi_ip().startswith("192.168.12."):
            self.bad("The Mac is not on the dog's Wi-Fi: join it in the Wi-Fi menu (top right of the screen), "
                     "then click 1-1.", "Mac 没连上狗的 Wi-Fi:在屏幕右上角的 Wi-Fi 菜单里连上狗的网络,再点 1-1。")
            return
        if not dog_wifi_port_open(wifi_dog_ip(target)):
            self.bad(f"The dog does not answer over Wi-Fi at {wifi_dog_ip(target)}: is it on? Click 1-1 to check.",
                     "狗没有回应:开机了吗?点 1-1 检查。")
            return
        cmd, after = self.script_cmd(a, "wifi", target)
        # a Wi-Fi command first spends a few seconds connecting, so it gets more time than over the cable
        self.start(cmd, a, label, after=after, limit=a["limit"] + 15, wifi=True)

    def reader(self, p, label, after):
        for line in p.stdout:
            line = line.rstrip()
            if line and not any(n in line for n in NOISE):
                self.q.put(line)
        rc = p.wait()
        if rc == 0 and after:
            subprocess.Popen(after)
        self.q.put(("done", label, rc))

    def pump(self):
        try:
            while True:
                item = self.q.get_nowait()
                if isinstance(item, tuple) and item[0] == "line":
                    self.write(item[1], item[2])
                elif isinstance(item, tuple):
                    _, label, rc = item
                    self.procs = [p for p in self.procs if p.poll() is None]
                    ok = rc in (0, -15, None)  # -15: ended by STOP or by its time limit
                    self.write(f"■ {label}: " + (self.tt("done", "完成") if ok else
                                                 self.tt(f"failed (code {rc})", f"失败(代码 {rc})")),
                               "info" if ok else "bad")
                else:
                    self.write(item)
        except queue.Empty:
            pass
        self.root.after(60, self.pump)

    def stop_all(self):
        n = 0
        for p in self.procs:
            if p.poll() is None:
                p.terminate()
                n += 1
        self.write(self.tt(f"■ closed {n} program(s) opened here. To stop the dog, use STOP.",
                           f"■ 关掉了 {n} 个面板打开的程序。要停狗,用 STOP。"), "info")

    def watch(self):
        """Every 3 s: can the dog be reached on the chosen connection? (in a background thread)"""
        while not self.closing:
            if self.route == "wifi":
                target = wifi_target()
                ip = wifi_dog_ip(target)
                if target == "ap" and not mac_wifi_ip().startswith("192.168.12."):
                    status = ("nowifi", "Wi-Fi")
                elif (subprocess.run(["ping", "-c", "1", "-t", "1", ip], capture_output=True).returncode == 0
                      or dog_wifi_port_open(ip)):
                    status = ("ok", "Wi-Fi")
                else:
                    status = ("noreply", "Wi-Fi")
            else:
                iface = cable_iface()
                if not iface:
                    status = ("nocard", "")
                elif subprocess.run(["ping", "-c", "1", "-t", "1", ROBOT_IP], capture_output=True).returncode == 0:
                    status = ("ok", iface)
                else:
                    status = ("noreply", iface)
            self.status = status
            try:
                self.root.after(0, self.show_status)
            except (RuntimeError, tk.TclError):  # the window is closing
                return
            threading.Event().wait(3)

    def show_status(self):
        state, where = self.status
        en = self.lang == "en"
        self.chip.set(*{
            "ok": (C["ok"], f"Dog connected ({where})" if en else f"狗:已连上({where})"),
            "noreply": (C["warn"], f"Dog: no reply on {where}" if en else f"狗:没回应({where})"),
            "nocard": (C["idle"], "Dog: no cable connection yet" if en else "狗:还没用网线连上"),
            "nowifi": (C["idle"], "Dog: join its Wi-Fi first" if en else "狗:先连上狗的 Wi-Fi"),
            "?": (C["idle"], "Dog: checking..." if en else "狗:检查中..."),
        }[state])

    def quit(self):
        """Closing the panel ends the programs it started (a walk still sends StopMove on the way out)."""
        if self.closing:
            return
        self.closing = True
        for p in self.procs:
            if p.poll() is None:
                p.terminate()
        self.root.destroy()


if __name__ == "__main__":
    root = tk.Tk()
    Panel(root)
    root.mainloop()
