"""System tray entry point for 金智汇连ETL.

Shows splash window, starts uvicorn in background thread, manages tray icon — all in one process.
"""
import os
import sys
import threading
import socket
import logging
import subprocess
import queue
import tkinter as tk
import ctypes
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

logger = logging.getLogger(__name__)

# ─── Tray Icon Manager ─────────────────────────────────────────

class _TrayIcon:
    """Manage system tray icon using ctypes + win32gui. Independent of main window."""

    def __init__(self, title: str, tooltip: str):
        import ctypes
        import win32gui
        import win32con
        import win32api

        self.ctypes = ctypes
        self.win32gui = win32gui
        self.win32con = win32con
        self.win32api = win32api
        self.title = title
        self.tooltip = tooltip
        self._hwnd = None
        self._hicon = None
        self._exiting = False

    class NOTIFYICONDATAW(ctypes.Structure):
        _fields_ = [
            ("cbSize", ctypes.c_uint), ("hWnd", ctypes.c_void_p),
            ("uID", ctypes.c_uint), ("uFlags", ctypes.c_uint),
            ("uCallbackMessage", ctypes.c_uint), ("hIcon", ctypes.c_void_p),
            ("szTip", ctypes.c_wchar * 128),
            ("dwState", ctypes.c_uint), ("dwStateMask", ctypes.c_uint),
            ("szInfo", ctypes.c_wchar * 256), ("uTimeout", ctypes.c_uint),
            ("szInfoTitle", ctypes.c_wchar * 64), ("dwInfoFlags", ctypes.c_uint),
            ("guidItem", ctypes.c_byte * 16), ("hBalloonIcon", ctypes.c_void_p),
        ]

    def _make_icon(self):
        """Create icon from PIL image."""
        img = _create_tray_icon()
        icon_data = img.tobytes("raw", "BGRA")
        gdi32 = self.ctypes.windll.gdi32
        user32 = self.ctypes.windll.user32
        size = 32
        hbm_color = gdi32.CreateBitmap(size, size, 1, 32, icon_data)

        class ICONINFO(self.ctypes.Structure):
            _fields_ = [
                ("fIcon", self.ctypes.c_bool), ("xHotspot", self.ctypes.c_uint),
                ("yHotspot", self.ctypes.c_uint), ("hbmMask", self.ctypes.c_void_p),
                ("hbmColor", self.ctypes.c_void_p),
            ]
        ii = ICONINFO()
        ii.fIcon = True
        ii.hbmMask = 0
        ii.hbmColor = hbm_color
        hIcon = user32.CreateIconIndirect(self.ctypes.byref(ii))
        gdi32.DeleteObject(hbm_color)
        return hIcon

    def _on_command(self, hwnd, msg, wparam, lparam):
        if msg == self.WM_TRAY:
            event = self.win32api.LOWORD(lparam)
            if event == self.win32con.WM_LBUTTONDBLCLK or event == self.win32con.WM_LBUTTONUP:
                if self._on_click:
                    self._on_click()
            elif event == self.win32con.WM_RBUTTONUP:
                self._show_popup(hwnd)
        elif msg == self.win32con.WM_COMMAND:
            cmd_id = self.win32api.LOWORD(wparam)
            handler = self._menu_map.get(cmd_id)
            if handler:
                handler()
        return 0

    def _show_popup(self, hwnd):
        try:
            menu = self.win32gui.CreatePopupMenu()
            self._menu_map = {}
            for i, item in enumerate(self._menu_items):
                label = item[0]
                handler = item[1] if len(item) > 1 else None
                menu_id = i + 1
                if label == "—":
                    # Separator line
                    self.win32gui.AppendMenu(menu, self.win32con.MF_SEPARATOR, menu_id, "")
                    self._menu_map[menu_id] = None
                elif handler is None:
                    # Disabled/status item (no callback)
                    self.win32gui.AppendMenu(menu, self.win32con.MF_STRING | self.win32con.MF_GRAYED, menu_id, label)
                    self._menu_map[menu_id] = None
                else:
                    self.win32gui.AppendMenu(menu, self.win32con.MF_STRING, menu_id, label)
                    self._menu_map[menu_id] = handler
            pos = self.win32gui.GetCursorPos()
            self.win32gui.SetForegroundWindow(hwnd)
            cmd = self.win32gui.TrackPopupMenu(
                menu,
                self.win32con.TPM_LEFTALIGN | self.win32con.TPM_RETURNCMD | self.win32con.TPM_NONOTIFY,
                pos[0], pos[1], hwnd,
            )
            self.win32gui.DestroyMenu(menu)
            handler = self._menu_map.get(cmd)
            if handler:
                handler()
        except Exception as e:
            logger.exception(f"Tray popup error: {e}")

    def show(self, menu_items, on_click):
        """Show tray icon.
        menu_items: list of (label, callback) tuples
        on_click: callback for double-click
        """
        self._menu_items = menu_items
        self._menu_map = {}
        self._on_click = on_click

        if self._hwnd:
            self.win32gui.ShowWindow(self._hwnd, self.win32con.SW_SHOW)
            return

        WM_TRAY = self.win32con.WM_USER + 1
        self.WM_TRAY = WM_TRAY

        self._hicon = self._make_icon()
        if not self._hicon:
            return

        # Register & create window
        class_name = f"QSTray_{os.getpid()}"
        wnd_class = self.win32gui.WNDCLASS()
        wnd_class.hInstance = self.win32api.GetModuleHandle()
        wnd_class.lpszClassName = class_name
        wnd_class.style = 0
        wnd_class.hCursor = self.win32gui.LoadCursor(0, self.win32con.IDC_ARROW)
        wnd_class.hbrBackground = self.win32con.COLOR_WINDOW + 1
        wnd_class.lpfnWndProc = self._on_command
        try:
            self.win32gui.RegisterClass(wnd_class)
        except self.win32gui.error:
            pass

        self._hwnd = self.win32gui.CreateWindow(
            class_name, "QSTray", 0, 0, 0, 0, 0, 0, 0,
            wnd_class.hInstance, None,
        )
        if not self._hwnd:
            return

        nid = self.NOTIFYICONDATAW()
        nid.cbSize = self.ctypes.sizeof(self.NOTIFYICONDATAW)
        nid.hWnd = self._hwnd
        nid.uID = 1
        nid.uFlags = 0x00000001 | 0x00000002 | 0x00000004
        nid.uCallbackMessage = WM_TRAY
        nid.hIcon = self._hicon
        nid.szTip = self.tooltip

        shell32 = self.ctypes.windll.shell32
        shell32.Shell_NotifyIconW(0, self.ctypes.byref(nid))
        logger.info(f"Tray icon shown: {self.tooltip}")

    def hide(self):
        if not self._hwnd:
            return
        try:
            nid = self.NOTIFYICONDATAW()
            nid.cbSize = self.ctypes.sizeof(self.NOTIFYICONDATAW)
            nid.hWnd = self._hwnd
            nid.uID = 1
            self.ctypes.windll.shell32.Shell_NotifyIconW(2, self.ctypes.byref(nid))
        except Exception:
            pass
        try:
            self.win32gui.DestroyWindow(self._hwnd)
        except Exception:
            pass
        if self._hicon:
            self.ctypes.windll.user32.DestroyIcon(self._hicon)
        self._hwnd = None
        self._hicon = None
        logger.info("Tray icon hidden")

    def destroy(self):
        self.hide()

DEFAULT_PORT = 8080
MAX_PORT = 8099

# ─── Global state ──────────────────────────────────────────────
_tray_port = [8080]
_tray_shutdown_fn = [None]
_tray_server_ref = [None]
_tray_hwnd = [None]
_tray_stop_event = threading.Event()


# ─── Environment Helpers ───────────────────────────────────────

def _get_data_dir() -> Path:
    if os.environ.get("JINZHIHUI_DATA_DIR"):
        return Path(os.environ["JINZHIHUI_DATA_DIR"])
    if sys.platform == "win32":
        base = Path(os.environ.get("APPDATA", Path.home() / "AppData" / "Roaming"))
    elif sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "JinZhiHuiETL"


def _is_port_in_use(port: int) -> bool:
    """Check if a port has a listening service. Uses connect_ex with timeout for speed."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.settimeout(0.1)
        return s.connect_ex(("127.0.0.1", port)) == 0


def _find_any_port_in_use(start: int = DEFAULT_PORT, max_port: int = MAX_PORT) -> bool:
    """Check all ports in range in parallel — returns as soon as first found."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    with ThreadPoolExecutor(max_workers=20) as executor:
        futures = [executor.submit(_is_port_in_use, p) for p in range(start, max_port + 1)]
        for future in as_completed(futures):
            if future.result():
                return True
    return False


def _find_free_port(start: int = DEFAULT_PORT, max_port: int = MAX_PORT) -> int:
    """Find first free port in range using parallel scan."""
    from concurrent.futures import ThreadPoolExecutor, as_completed
    ports = list(range(start, max_port + 1))
    with ThreadPoolExecutor(max_workers=20) as executor:
        future_to_port = {executor.submit(_is_port_in_use, p): p for p in ports}
        for future in as_completed(future_to_port):
            if not future.result():
                return future_to_port[future]
    raise RuntimeError(f"No free port found in [{start}, {max_port}]")


def _check_path_writable(path: str) -> tuple[bool, str]:
    p = Path(path)
    if not p.exists():
        try:
            p.mkdir(parents=True, exist_ok=True)
            return True, f"Created directory: {path}"
        except OSError as e:
            return False, f"Cannot create directory {path}: {e}"
    if not p.is_dir():
        return False, f"{path} exists but is not a directory"
    if not os.access(path, os.W_OK):
        return False, f"Directory {path} is not writable"
    return True, f"Directory {path} is writable"


def _redirect_stdio(data_dir: Path):
    if not getattr(sys, 'frozen', False):
        return
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"etl_{datetime.now().strftime('%Y%m%d')}.log"
    fh = open(log_file, "a", encoding="utf-8")
    sys.stdout = fh
    sys.stderr = fh


def _setup_logging(data_dir: Path):
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file = log_dir / f"etl_{datetime.now().strftime('%Y%m%d')}.log"

    root_logger = logging.getLogger()
    for h in root_logger.handlers[:]:
        root_logger.removeHandler(h)
    root_logger.setLevel(logging.INFO)

    fh = logging.FileHandler(str(log_file), encoding="utf-8")
    fh.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
    root_logger.addHandler(fh)

    if not getattr(sys, 'frozen', False):
        ch = logging.StreamHandler()
        ch.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(name)s: %(message)s"))
        root_logger.addHandler(ch)


def _resource_path(relative: str) -> str:
    if getattr(sys, 'frozen', False):
        base = Path(sys._MEIPASS)
        candidate = base / "app" / relative
        if not candidate.exists():
            candidate = base / relative
        return str(candidate)
    else:
        base = Path(__file__).parent
    return str(base / relative)


# ─── Loading Window ────────────────────────────────────────────

def _show_loading_window(root):
    """Show a loading overlay on the given Tk root. Returns (set_status, set_progress, close_func)."""

    q: queue.Queue = queue.Queue()
    cancelled = [False]

    # ── Loading overlay (replaces root content) ──
    for w in root.winfo_children():
        w.destroy()

    root.configure(bg="#1a1a2e")
    root.overrideredirect(True)
    root.attributes("-topmost", True)
    root.deiconify()

    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    w, h = 420, 240
    root.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    BTN_SIZE = 28
    btn_x = w - BTN_SIZE - 6

    def _close_btn(event=None):
        if cancelled[0]:
            return
        try:
            dialog = tk.Toplevel(root)
            dialog.overrideredirect(True)
            dialog.attributes("-topmost", True)
            dialog.configure(bg="#2a2a3e")
            dw, dh = 260, 120
            dialog.geometry(f"{dw}x{dh}+{(sw - dw) // 2}+{(sh - dh) // 2}")

            tk.Label(
                dialog, text="是否要退出 金智汇连ETL？",
                font=("Microsoft YaHei", 10),
                fg="#ccccdd", bg="#2a2a3e",
            ).pack(pady=(25, 15))

            frame = tk.Frame(dialog, bg="#2a2a3e")
            frame.pack()

            def on_yes():
                dialog.destroy()
                cancelled[0] = True
                q.put(("close", None))

            def on_no():
                dialog.destroy()

            tk.Button(
                frame, text="确定", width=8, command=on_yes,
                font=("Microsoft YaHei", 9),
                bg="#444466", fg="white", relief="flat",
            ).pack(side="left", padx=8)
            tk.Button(
                frame, text="取消", width=8, command=on_no,
                font=("Microsoft YaHei", 9),
                bg="#444466", fg="white", relief="flat",
            ).pack(side="left", padx=8)

            dialog.bind("<Escape>", lambda e: on_no())
        except Exception:
            cancelled[0] = True
            q.put(("close", None))

    close_canvas = tk.Canvas(
        root, width=BTN_SIZE, height=BTN_SIZE,
        bg="#1a1a2e", highlightthickness=0,
    )
    close_canvas.place(x=btn_x, y=6)
    txt_id = close_canvas.create_text(
        BTN_SIZE // 2, BTN_SIZE // 2, text="✕",
        font=("Consolas", 14, "bold"), fill="#8899bb",
    )
    close_canvas.tag_bind(txt_id, "<Enter>",
                           lambda e: close_canvas.itemconfig(txt_id, fill="#ff6b6b"))
    close_canvas.tag_bind(txt_id, "<Leave>",
                           lambda e: close_canvas.itemconfig(txt_id, fill="#8899bb"))
    close_canvas.tag_bind(txt_id, "<Button-1>", _close_btn)

    drag = [0, 0, 0, 0]

    def _drag_start(event):
        drag[0] = root.winfo_rootx()
        drag[1] = root.winfo_rooty()
        drag[2] = event.x_root
        drag[3] = event.y_root

    def _drag_move(event):
        root.geometry(f"+{drag[0] + event.x_root - drag[2]}+{drag[1] + event.y_root - drag[3]}")

    root.bind("<Button-1>", _drag_start, add=True)
    root.bind("<B1-Motion>", _drag_move, add=True)

    tk.Label(
        root, text="金智汇连ETL",
        font=("Microsoft YaHei", 22, "bold"),
        fg="#508cff", bg="#1a1a2e",
    ).pack(pady=(10, 4))

    tk.Label(
        root, text="通用可视化ETL数据同步工具",
        font=("Microsoft YaHei", 10),
        fg="#8899bb", bg="#1a1a2e",
    ).pack(pady=(0, 18))

    status_label = tk.Label(
        root, text="正在启动...",
        font=("Microsoft YaHei", 9),
        fg="#667799", bg="#1a1a2e",
    )
    status_label.pack(pady=(0, 8))

    canvas = tk.Canvas(
        root, width=300, height=5, bg="#2a2a4e", highlightthickness=0,
    )
    canvas.pack()
    bar_id = canvas.create_rectangle(0, 0, 0, 5, fill="#508cff", outline="")

    prog = [0.05]
    closing = [False]

    def tick():
        if closing[0]:
            return
        if prog[0] < 0.85:
            prog[0] = min(0.85, prog[0] + 0.004)
        try:
            while True:
                msg_type, val = q.get_nowait()
                if msg_type == "status":
                    status_label.config(text=val)
                elif msg_type == "progress":
                    prog[0] = val
                elif msg_type == "close":
                    closing[0] = True
                    return
        except queue.Empty:
            pass
        canvas.coords(bar_id, 0, 0, int(300 * prog[0]), 5)
        root.after(50, tick)

    tick()

    def set_status(text: str):
        q.put(("status", text))

    def set_progress(ratio: float):
        q.put(("progress", ratio))

    def close():
        q.put(("close", None))

    return set_status, set_progress, close, cancelled, q


# ─── Instance Check Dialog ──────────────────────────────────────

def _show_instance_dialog(root) -> str:
    """Show a blocking dialog: service already running, click OK to kill this process.
    Returns: always returns 'cancel' (we kill the process immediately on OK).
    Uses the given Tk root.
    """
    root.attributes("-topmost", True)
    root.lift()
    root.focus_force()

    dlg = tk.Toplevel(root)
    dlg.title("金智汇连ETL")
    dlg.overrideredirect(True)
    dlg.attributes("-topmost", True)
    dlg.configure(bg="#2a2a3e")

    sw = dlg.winfo_screenwidth()
    sh = dlg.winfo_screenheight()
    w, h = 360, 160
    dlg.geometry(f"{w}x{h}+{(sw - w) // 2}+{(sh - h) // 2}")

    # Find existing port for display
    existing_port = "8080"
    for p in range(8080, 8100):
        if _is_port_in_use(p):
            existing_port = str(p)
            break

    tk.Label(
        dlg,
        text="金智汇连ETL 已在运行中",
        font=("Microsoft YaHei", 12, "bold"),
        fg="#ffffff", bg="#2a2a3e",
    ).pack(pady=(20, 10))

    tk.Label(
        dlg,
        text=f"检测到已有服务运行于 http://127.0.0.1:{existing_port}\n\n"
             "请直接使用已打开的窗口，勿重复启动。\n"
             "点击「确定」关闭本窗口。",
        font=("Microsoft YaHei", 9),
        fg="#aaaaaa", bg="#2a2a3e",
        justify="left",
    ).pack(pady=(0, 15))

    def on_ok():
        dlg.destroy()
        root.quit()
        # 立即杀死当前进程，不留任何残留
        os._exit(0)

    tk.Button(
        dlg, text="确定", width=12,
        font=("Microsoft YaHei", 10),
        bg="#508cff", fg="white", relief="flat",
        bd=0, pady=6,
        command=on_ok,
    ).pack()

    root.wait_window()
    root.update()
    return "cancel"


# ─── Browser ───────────────────────────────────────────────────

def _open_browser(port: int):
    url = f"http://127.0.0.1:{port}"
    if sys.platform == "win32":
        os.startfile(url)
    elif sys.platform == "darwin":
        subprocess.Popen(["open", url])
    else:
        subprocess.Popen(["xdg-open", url])


def _get_license_status_menu_text() -> str:
    """Get license status text for tray menu."""
    try:
        from app.core.license_manager import get_license_info
        info = get_license_info()
        if info and info.get("activated"):
            tier = info.get("tier", "free")
            tier_names = {"free": "免费版", "personal": "个人版", "professional": "专业版"}
            return f"当前授权: {tier_names.get(tier, tier)}"
    except Exception:
        pass
    return "当前授权: 免费基础版"


def _get_menu_items(on_open, on_logs, on_exit):
    """Build tray menu items with license status."""
    return [
        _get_license_status_menu_text(),
        ("—", None),
        ("打开主界面", on_open),
        ("查看日志", on_logs),
        ("退出", on_exit),
    ]


# ─── Tray Icon ─────────────────────────────────────────────────

def _resource_path(relative: str) -> str:
    """Get absolute path to resource, works for dev and PyInstaller."""
    if getattr(sys, 'frozen', False):
        base = Path(sys._MEIPASS)
        candidate = base / "app" / relative
        if candidate.exists():
            return str(candidate)
        candidate = base / relative
        if candidate.exists():
            return str(candidate)
        return ""
    else:
        base = Path(__file__).parent
    return str(base / relative)


def _create_tray_icon():
    """Load 32x32 tray icon from logo.png."""
    path = _resource_path("static/logo.png")
    if not path:
        path = _resource_path("static/logo.ico")
    if path:
        return Image.open(path).resize((32, 32)).convert("RGBA")
    # Fallback: generate a blue circle
    size = 32
    img = Image.new("RGBA", (size, size), (26, 26, 46, 255))
    draw = ImageDraw.Draw(img)
    draw.ellipse([4, 4, size - 5, size - 5], outline=(80, 140, 255, 255), width=2)
    return img


def _set_window_icon(root):
    """Set tkinter window icon — works in dev and frozen."""
    png_path = _resource_path("static/logo.png")
    ico_path = _resource_path("static/logo.ico")
    if png_path:
        try:
            icon_img = tk.PhotoImage(file=png_path)
            root.iconphoto(True, icon_img)
            root._icon_ref = icon_img  # prevent GC
            return
        except Exception:
            pass
    if ico_path:
        try:
            root.iconbitmap(ico_path)
        except Exception:
            pass


# ─── Open Log Folder ──────────────────────────────────────────

def _open_log_folder():
    data_dir = _get_data_dir()
    log_dir = data_dir / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    if sys.platform == "win32":
        os.startfile(str(log_dir))
    elif sys.platform == "darwin":
        subprocess.run(["open", str(log_dir)])
    else:
        subprocess.run(["xdg-open", str(log_dir)])


# ─── Simple Window (minimizable, with tray icon) ─────────────

# Singleton tray icon instance
_tray_icon = None


def _start_main_window(root, port, server, shutdown_scheduler_fn):
    """Transform the existing Tk root into the main window.
    Uses the same Tk instance to avoid multiple mainloops.
    Shows tray icon; close button asks whether to minimize to tray or exit.
    """
    global _tray_icon

    _tray_port[0] = port
    _tray_shutdown_fn[0] = shutdown_scheduler_fn
    _tray_server_ref[0] = server

    logger.info(f"Simple window: starting for port {port}")

    # ── Reset to normal window ──
    root.withdraw()
    for w in root.winfo_children():
        w.destroy()

    root.title("金智汇连ETL")
    # Set window icon — try PNG first, fall back to ICO
    _set_window_icon(root)
    root.configure(bg="#1a1a2e")
    root.overrideredirect(False)
    root.attributes("-topmost", False)
    root.resizable(False, False)

    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    w, h = 480, 280
    root.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    # ── Build UI ──
    frm = tk.Frame(root, bg="#1a1a2e")
    frm.pack(fill="both", expand=True)

    tk.Label(frm, text="金智汇连ETL",
             font=("Microsoft YaHei", 20, "bold"),
             fg="#508cff", bg="#1a1a2e").pack(pady=(30, 4))

    tk.Label(frm, text="通用可视化ETL数据同步工具",
             font=("Microsoft YaHei", 9),
             fg="#8899bb", bg="#1a1a2e").pack(pady=(0, 12))

    tk.Label(frm, text=f"服务运行中  http://127.0.0.1:{port}",
             font=("Microsoft YaHei", 9),
             fg="#667799", bg="#1a1a2e").pack(pady=(0, 20))

    btn_frame = tk.Frame(frm, bg="#1a1a2e")
    btn_frame.pack(pady=10)

    def on_open():
        _open_browser(port)

    def on_logs():
        _open_log_folder()

    def on_exit():
        global _tray_icon
        logger.info("Main window: exit triggered")
        # Destroy tray icon immediately
        if _tray_icon:
            try:
                _tray_icon.destroy()
            except Exception:
                pass
            _tray_icon = None
        # Kill the uvicorn server hard
        if _tray_server_ref[0]:
            try:
                _tray_server_ref[0].should_exit = True
            except Exception:
                pass
        # Kill scheduler
        if _tray_shutdown_fn[0]:
            try:
                _tray_shutdown_fn[0]()
            except Exception:
                pass
        # Schedule os._exit in next Tk event cycle to ensure complete cleanup
        root.after(50, lambda: os._exit(0))
        root.quit()

    tk.Button(btn_frame, text="打开主界面", width=12, command=on_open,
              font=("Microsoft YaHei", 9), bg="#508cff", fg="white",
              relief="flat", activebackground="#4070dd", activeforeground="white",
              bd=0, pady=6).pack(side="left", padx=6)

    tk.Button(btn_frame, text="查看日志", width=12, command=on_logs,
              font=("Microsoft YaHei", 9), bg="#333355", fg="#aaaaaa",
              relief="flat", activebackground="#444466", activeforeground="white",
              bd=0, pady=6).pack(side="left", padx=6)

    tk.Button(btn_frame, text="退出", width=12, command=on_exit,
              font=("Microsoft YaHei", 9), bg="#552222", fg="#ff8888",
              relief="flat", activebackground="#662222", activeforeground="white",
              bd=0, pady=6).pack(side="left", padx=6)

    tk.Label(frm, text="提示：关闭此窗口将最小化到托盘，可右键退出",
             font=("Microsoft YaHei", 8),
             fg="#555577", bg="#1a1a2e").pack(side="bottom", pady=(0, 8))

    # ── Close button: ask minimize or exit ──
    def on_closing():
        dlg = tk.Toplevel(root)
        dlg.title("关闭")
        dlg.overrideredirect(True)
        dlg.attributes("-topmost", True)
        dlg.configure(bg="#2a2a3e")
        dlg.transient(root)

        sw_s = dlg.winfo_screenwidth()
        sh_s = dlg.winfo_screenheight()
        dw, dh = 300, 150
        dlg.geometry(f"{dw}x{dh}+{(sw_s-dw)//2}+{(sh_s-dh)//2}")

        tk.Label(dlg, text="关闭 金智汇连ETL？",
                 font=("Microsoft YaHei", 11),
                 fg="#ffffff", bg="#2a2a3e").pack(pady=(20, 10))

        tk.Label(dlg, text="最小化到托盘：服务继续在后台运行\n退出程序：完全关闭服务和窗口",
                 font=("Microsoft YaHei", 8),
                 fg="#aaaaaa", bg="#2a2a3e").pack(pady=(0, 15))

        bf = tk.Frame(dlg, bg="#2a2a3e")
        bf.pack()

        def do_minimize():
            dlg.destroy()
            root.withdraw()
            if not _tray_icon:
                _tray_icon = _TrayIcon("金智汇连ETL", f"金智汇连ETL (:{port})")
            _tray_icon.show([
                _get_license_status_menu_text(),
                ("—", None),
                ("打开主界面", on_open),
                ("查看日志", on_logs),
                ("退出", on_exit),
            ], on_open)

        def do_exit():
            dlg.destroy()
            on_exit()

        def do_cancel():
            dlg.destroy()

        tk.Button(bf, text="最小化到托盘", width=11, command=do_minimize,
                  font=("Microsoft YaHei", 9), bg="#444466", fg="white",
                  relief="flat", bd=0, pady=5).pack(side="left", padx=5)

        tk.Button(bf, text="退出程序", width=11, command=do_exit,
                  font=("Microsoft YaHei", 9), bg="#552222", fg="#ff8888",
                  relief="flat", bd=0, pady=5).pack(side="left", padx=5)

        tk.Button(bf, text="取消", width=8, command=do_cancel,
                  font=("Microsoft YaHei", 9), bg="#333355", fg="#aaaaaa",
                  relief="flat", bd=0, pady=5).pack(side="left", padx=5)

    root.protocol("WM_DELETE_WINDOW", on_closing)

    # ── Show window + tray icon ──
    root.deiconify()
    root.update()

    # Show tray icon immediately
    _tray_icon = _TrayIcon("金智汇连ETL", f"金智汇连ETL (:{port})")
    _tray_icon.show([
        _get_license_status_menu_text(),
        ("—", None),
        ("打开主界面", on_open),
        ("查看日志", on_logs),
        ("退出", on_exit),
    ], on_open)

    logger.info("Simple window: entering mainloop...")
    root.mainloop()
    # At this point on_exit() has called os._exit(0) — process is dead.
    # This block only runs if os._exit was bypassed (shouldn't happen).
    logger.info("Main window: mainloop ended, shutting down...")


# ─── Instance Dialog (Tk-invoked) ─────────────────────────────

def _handle_instance_dialog(root, instance_choice):
    """Show blocking dialog: service already running. Click OK → kill this process."""
    root.attributes("-topmost", True)
    root.lift()
    root.focus_force()

    dlg = tk.Toplevel(root)
    dlg.title("金智汇连ETL")
    dlg.overrideredirect(True)
    dlg.attributes("-topmost", True)
    dlg.configure(bg="#2a2a3e")

    sw = dlg.winfo_screenwidth()
    sh = dlg.winfo_screenheight()
    w, h = 360, 160
    dlg.geometry(f"{w}x{h}+{(sw-w)//2}+{(sh-h)//2}")

    existing_port = "8080"
    for p in range(8080, 8100):
        if _is_port_in_use(p):
            existing_port = str(p)
            break

    tk.Label(dlg, text="金智汇连ETL 已在运行中",
             font=("Microsoft YaHei", 12, "bold"),
             fg="#ffffff", bg="#2a2a3e").pack(pady=(20, 10))

    tk.Label(dlg,
             text=f"检测到已有服务运行于 http://127.0.0.1:{existing_port}\n\n"
                  "请直接使用已打开的窗口，勿重复启动。\n"
                  "点击「确定」关闭本窗口。",
             font=("Microsoft YaHei", 9),
             fg="#aaaaaa", bg="#2a2a3e",
             justify="left").pack(pady=(0, 15))

    def on_ok():
        dlg.destroy()
        root.quit()
        os._exit(0)

    tk.Button(dlg, text="确定", width=12,
              font=("Microsoft YaHei", 10),
              bg="#508cff", fg="white", relief="flat",
              bd=0, pady=6, command=on_ok).pack()


# ─── Main Entry ────────────────────────────────────────────────

def run_tray_app():
    """Main entry point.
    Slow init (db, scheduler, uvicorn) runs in a background thread.
    Tk mainloop handles UI animations, then transitions to main window.
    Uses a SINGLE Tk instance throughout.
    """

    # ── Shared state between background thread and Tk UI ────────
    init_result = [None]  # None=loading, dict=ready, "dialog"=instance_dialog, "error"=error
    init_progress = [0.0]  # 0.0-1.0
    init_status = ["正在启动..."]
    instance_choice = [None]  # 'new', 'open', 'cancel', None=waiting

    # ── 0. Create the ONE AND ONLY Tk root ────────────────────
    root = tk.Tk()
    root.withdraw()
    root.configure(bg="#1a1a2e")
    # Set window icon
    _set_window_icon(root)

    # ── Build loading UI ───────────────────────────────────────
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    lw, lh = 420, 240
    root.geometry(f"{lw}x{lh}+{(sw-lw)//2}+{(sh-lh)//2}")
    root.overrideredirect(True)
    root.attributes("-topmost", True)

    frm = tk.Frame(root, bg="#1a1a2e")
    frm.pack(fill="both", expand=True)

    tk.Label(frm, text="金智汇连ETL",
             font=("Microsoft YaHei", 22, "bold"),
             fg="#508cff", bg="#1a1a2e").pack(pady=(10, 4))

    tk.Label(frm, text="通用可视化ETL数据同步工具",
             font=("Microsoft YaHei", 10),
             fg="#8899bb", bg="#1a1a2e").pack(pady=(0, 18))

    status_lbl = tk.Label(frm, text="正在启动...",
                           font=("Microsoft YaHei", 9),
                           fg="#667799", bg="#1a1a2e")
    status_lbl.pack(pady=(0, 8))

    bar_canvas = tk.Canvas(frm, width=300, height=5, bg="#2a2a4e", highlightthickness=0)
    bar_canvas.pack()
    bar_id = bar_canvas.create_rectangle(0, 0, 0, 5, fill="#508cff", outline="")

    # ── UI update tick ─────────────────────────────────────────
    def _tick():
        # Update status and progress from shared state
        if init_status:
            status_lbl.config(text=init_status[0])
        prog = init_progress[0]
        bar_canvas.coords(bar_id, 0, 0, int(300 * prog), 5)

        r = init_result[0]
        if r is None:
            root.after(100, _tick)
        elif r == "dialog":
            # Instance check needed — show dialog in Tk thread
            root.after(10, lambda: _handle_instance_dialog(root, instance_choice))
        elif isinstance(r, dict):
            # Init complete — switch to main window
            root.after(10, lambda: _start_main_window(root, r["port"], r["server"], r["shutdown"]))
        elif r == "error":
            root.quit()
        else:
            root.quit()
    root.after(100, _tick)

    root.deiconify()

    # ── Background init thread ─────────────────────────────────
    import time

    def _init_thread():
        t0 = time.time()
        try:
            # Step 1: Data dir + logging
            init_status[0] = "检查数据目录..."
            init_progress[0] = 0.10
            data_dir = _get_data_dir()
            ok, msg = _check_path_writable(str(data_dir))
            if not ok:
                init_result[0] = "error"
                logger.error(f"Data dir error: {msg}")
                return
            os.environ["JINZHIHUI_DATA_DIR"] = str(data_dir)
            _redirect_stdio(data_dir)
            _setup_logging(data_dir)
            logger.info(f"[{time.time()-t0:.1f}s] Data dir: {data_dir}")

            # Step 2: Instance check
            init_status[0] = "检查服务状态..."
            init_progress[0] = 0.20
            t2 = time.time()
            logger.info(f"[{time.time()-t0:.1f}s] Starting port scan...")
            if _find_any_port_in_use():
                logger.info(f"[{time.time()-t0:.1f}s] Port in use detected, showing dialog...")
                init_result[0] = "dialog"
                while instance_choice[0] is None:
                    threading.Event().wait(0.1)
                choice = instance_choice[0]
                logger.info(f"[{time.time()-t0:.1f}s] Dialog choice: {choice} (waited {time.time()-t2:.1f}s for user)")
                if choice == "cancel":
                    return
                elif choice == "open":
                    for p in range(DEFAULT_PORT, MAX_PORT + 1):
                        if _is_port_in_use(p):
                            _open_browser(p)
                            return
                    return
                logger.info("User chose to start new instance despite existing service")

            # Step 3: Init db & scheduler
            init_status[0] = "初始化数据库..."
            init_progress[0] = 0.35
            t3 = time.time()
            logger.info(f"[{time.time()-t0:.1f}s] Starting init_db + init_scheduler...")
            from app.persistence.sqlite_repo import init_db
            from app.core.task_scheduler import init_scheduler, shutdown_scheduler
            init_db()
            init_scheduler()
            logger.info(f"[{time.time()-t0:.1f}s] DB + scheduler done in {time.time()-t3:.1f}s")

            # Step 4: Find port
            init_status[0] = "检查端口..."
            init_progress[0] = 0.50
            t4 = time.time()
            logger.info(f"[{time.time()-t0:.1f}s] Finding free port...")
            port = _find_free_port()
            logger.info(f"[{time.time()-t0:.1f}s] Found port {port} in {time.time()-t4:.1f}s")
            if port != DEFAULT_PORT:
                logger.warning(f"Port {DEFAULT_PORT} busy, using {port}")
            else:
                logger.info(f"Starting on port {port}")

            # Step 5: Import app
            init_status[0] = "加载应用组件..."
            init_progress[0] = 0.65
            t5 = time.time()
            logger.info(f"[{time.time()-t0:.1f}s] Importing app.main...")
            import time as _time_module
            _t_import = _time_module.time

            t5a = _t_import()
            from app.main import app
            logger.info(f"[{_t_import()-t0:.1f}s] app.main imported ({_t_import()-t5a:.1f}s)")

            logger.info(f"[{time.time()-t0:.1f}s] Import done in {time.time()-t5:.1f}s")

            # Step 6: Start uvicorn
            init_status[0] = "启动服务..."
            init_progress[0] = 0.80
            t6 = time.time()
            logger.info(f"[{time.time()-t0:.1f}s] Starting uvicorn...")
            import uvicorn
            config = uvicorn.Config(
                app, host="127.0.0.1", port=port,
                log_level="info", access_log=False, log_config=None,
            )
            server = uvicorn.Server(config)
            srv_t = threading.Thread(target=server.run, daemon=True)
            srv_t.start()
            logger.info(f"[{time.time()-t0:.1f}s] Uvicorn started in {time.time()-t6:.1f}s")

            # Step 7: Wait for server ready
            init_status[0] = "等待服务就绪..."
            init_progress[0] = 0.90
            t7 = time.time()
            import urllib.request
            for i in range(30):
                threading.Event().wait(0.2)
                try:
                    with urllib.request.urlopen(f"http://127.0.0.1:{port}/health", timeout=1):
                        break
                except Exception:
                    if i == 29:
                        logger.error(f"Server failed to start on port {port} after {time.time()-t7:.1f}s")
            else:
                init_result[0] = "error"
                return
            logger.info(f"[{time.time()-t0:.1f}s] Server healthy in {time.time()-t7:.1f}s")

            # Step 8: Open browser
            init_status[0] = "打开浏览器..."
            init_progress[0] = 0.95
            _open_browser(port)

            # Done
            init_status[0] = "启动完成"
            init_progress[0] = 1.0
            logger.info(f"[{time.time()-t0:.1f}s] Total init complete, starting main window")
            init_result[0] = {"port": port, "server": server, "shutdown": shutdown_scheduler}

        except Exception as e:
            logger.exception(f"Init thread error after {time.time()-t0:.1f}s: {e}")
            init_result[0] = "error"

    threading.Thread(target=_init_thread, daemon=True).start()

    # ── Tk mainloop ────────────────────────────────────────────
    root.mainloop()

if __name__ == "__main__":
    run_tray_app()