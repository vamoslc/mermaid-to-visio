#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Mermaid → Visio GUI：主题配色选择 + 结果预览 + 导出 .vsdx。"""

from __future__ import annotations

import io
import os
import sys
import threading
import traceback
import webbrowser
from pathlib import Path
from tkinter import (
    BOTH,
    BOTTOM,
    DISABLED,
    END,
    LEFT,
    NORMAL,
    RIGHT,
    WORD,
    BooleanVar,
    Canvas,
    Frame,
    Label,
    Menu,
    StringVar,
    Text,
    Tk,
    Toplevel,
    X,
    Y,
    filedialog,
    messagebox,
    ttk,
)

from PIL import Image, ImageTk

from mermaid_to_visio import (
    convert_mermaid_to_vsdx,
    detect_kind,
    iter_inputs,
    read_source,
    render_png,
    strip_fences,
)

# ---------------------------------------------------------------------------
# Theme / style catalog (mermaid-render)
# ---------------------------------------------------------------------------

THEMES = [
    {
        "id": "redux-color",
        "name": "彩色 (Redux)",
        "desc": "鲜明彩色，默认推荐",
        "swatches": ("#ECECFF", "#4A6CF7", "#BBDEFB", "#333333", "#FFFFFF"),
        "preview_bg": "#F7F8FC",
    },
    {
        "id": "default",
        "name": "经典蓝",
        "desc": "Mermaid 经典配色",
        "swatches": ("#ECECFF", "#9370DB", "#333333", "#FFFFFF", "#CCCCFF"),
        "preview_bg": "#FAFAFA",
    },
    {
        "id": "forest",
        "name": "森林绿",
        "desc": "绿色系，偏自然/运维",
        "swatches": ("#C8E6C9", "#2E7D32", "#81C784", "#1B5E20", "#FFFFFF"),
        "preview_bg": "#F3F7F3",
    },
    {
        "id": "neutral",
        "name": "中性灰",
        "desc": "低饱和，适合文档打印",
        "swatches": ("#EEEEEE", "#616161", "#BDBDBD", "#212121", "#FAFAFA"),
        "preview_bg": "#F5F5F5",
    },
    {
        "id": "dark",
        "name": "深色",
        "desc": "深色背景，演示/大屏",
        "swatches": ("#1E1E2E", "#7AA2F7", "#A6ADC8", "#CDD6F4", "#313244"),
        "preview_bg": "#1E1E2E",
    },
]

MODES = [
    ("auto", "自动（推荐）"),
    ("connected", "可编辑连接（flowchart/类图/时序/状态）"),
    ("geometry", "几何形状（ER/饼图等）"),
    ("picture", "整图嵌入（最高保真）"),
]

CONNECTORS = [
    ("right-angle", "直角折线"),
    ("straight", "直线"),
    ("mermaid", "Mermaid 曲线"),
]

SAMPLE = """flowchart LR
  A[输入] --> B{合法?}
  B -->|是| C(处理)
  B -->|否| D[拒绝]
  C --> E[[归档]]
"""


def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


class MermaidVisioApp:
    def __init__(self, root: Tk) -> None:
        self.root = root
        self.root.title("Mermaid → Visio")
        self.root.geometry("1180x760")
        self.root.minsize(960, 640)

        self.theme_var = StringVar(value="redux-color")
        self.mode_var = StringVar(value="auto")
        self.conn_var = StringVar(value="right-angle")
        self.auto_preview = BooleanVar(value=True)
        self.status_var = StringVar(value="就绪")
        self.kind_var = StringVar(value="—")
        self._preview_job: str | None = None
        self._busy = False
        self._photo: ImageTk.PhotoImage | None = None
        self._last_png: bytes | None = None
        self._source_path: Path | None = None
        self._batch_cancel = False

        self._build_style()
        self._build_menu()
        self._build_ui()
        self._load_sample(silent=True)
        self.root.after(200, self.preview)

    # ---- UI ----
    def _build_style(self) -> None:
        style = ttk.Style(self.root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure("TFrame", background="#F0F2F5")
        style.configure("Card.TFrame", background="#FFFFFF")
        style.configure("Title.TLabel", font=("Microsoft YaHei UI", 14, "bold"), background="#F0F2F5")
        style.configure("Muted.TLabel", font=("Microsoft YaHei UI", 9), foreground="#666", background="#FFFFFF")
        style.configure("Theme.TRadiobutton", background="#FFFFFF", font=("Microsoft YaHei UI", 9))
        style.configure("Accent.TButton", font=("Microsoft YaHei UI", 10, "bold"), padding=8)
        style.configure("TButton", font=("Microsoft YaHei UI", 9), padding=6)
        style.configure("TLabelframe", background="#FFFFFF")
        style.configure("TLabelframe.Label", font=("Microsoft YaHei UI", 9, "bold"), background="#FFFFFF")
        self.root.configure(bg="#F0F2F5")

    def _build_menu(self) -> None:
        menubar = Menu(self.root)
        file_m = Menu(menubar, tearoff=0)
        file_m.add_command(label="打开…", command=self.open_file, accelerator="Ctrl+O")
        file_m.add_command(label="导出 Visio…", command=self.export_vsdx, accelerator="Ctrl+S")
        file_m.add_command(label="批量转 Visio…", command=self.batch_export, accelerator="Ctrl+B")
        file_m.add_command(label="保存预览图 PNG…", command=self.save_preview_png)
        file_m.add_separator()
        file_m.add_command(label="退出", command=self.root.destroy)
        menubar.add_cascade(label="文件", menu=file_m)

        edit_m = Menu(menubar, tearoff=0)
        edit_m.add_command(label="载入示例", command=self._load_sample)
        edit_m.add_command(label="清空", command=self.clear_editor)
        menubar.add_cascade(label="编辑", menu=edit_m)

        help_m = Menu(menubar, tearoff=0)
        help_m.add_command(label="Mermaid 语法", command=lambda: webbrowser.open("https://mermaid.js.org/intro/"))
        help_m.add_command(label="关于", command=self._about)
        menubar.add_cascade(label="帮助", menu=help_m)
        self.root.config(menu=menubar)
        self.root.bind("<Control-o>", lambda e: self.open_file())
        self.root.bind("<Control-s>", lambda e: self.export_vsdx())
        self.root.bind("<Control-b>", lambda e: self.batch_export())
        self.root.bind("<F5>", lambda e: self.preview())

    def _build_ui(self) -> None:
        top = ttk.Frame(self.root, padding=10)
        top.pack(fill=BOTH, expand=True)

        ttk.Label(top, text="Mermaid → Visio 转换器", style="Title.TLabel").pack(anchor="w", pady=(0, 8))

        body = ttk.Frame(top)
        body.pack(fill=BOTH, expand=True)
        body.columnconfigure(0, weight=1)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(0, weight=1)

        # Left: editor + options
        left = ttk.Frame(body, style="Card.TFrame", padding=10)
        left.grid(row=0, column=0, sticky="nsew", padx=(0, 6))
        left.rowconfigure(1, weight=1)
        left.columnconfigure(0, weight=1)

        ttk.Label(left, text="Mermaid 源码", font=("Microsoft YaHei UI", 10, "bold"), background="#FFFFFF").grid(
            row=0, column=0, sticky="w"
        )
        ed_frame = Frame(left, bg="#FFFFFF")
        ed_frame.grid(row=1, column=0, sticky="nsew", pady=(6, 8))
        self.editor = Text(
            ed_frame,
            wrap=WORD,
            font=("Consolas", 11),
            undo=True,
            bg="#FAFBFC",
            relief="solid",
            borderwidth=1,
            padx=8,
            pady=8,
        )
        scroll = ttk.Scrollbar(ed_frame, command=self.editor.yview)
        self.editor.configure(yscrollcommand=scroll.set)
        self.editor.pack(side=LEFT, fill=BOTH, expand=True)
        scroll.pack(side=RIGHT, fill=Y)
        self.editor.bind("<<Modified>>", self._on_edit)

        opts = ttk.LabelFrame(left, text="导出风格", padding=8)
        opts.grid(row=2, column=0, sticky="ew")

        ttk.Label(opts, text="颜色风格", style="Muted.TLabel").pack(anchor="w")
        theme_row = Frame(opts, bg="#FFFFFF")
        theme_row.pack(fill=X, pady=(4, 8))
        self._theme_cards: list[Frame] = []
        for i, th in enumerate(THEMES):
            card = self._make_theme_card(theme_row, th)
            card.grid(row=0, column=i, padx=3, sticky="n")
            self._theme_cards.append(card)

        row2 = Frame(opts, bg="#FFFFFF")
        row2.pack(fill=X, pady=2)
        ttk.Label(row2, text="导出模式", background="#FFFFFF").pack(side=LEFT)
        mode_cb = ttk.Combobox(
            row2,
            textvariable=self.mode_var,
            values=[m[0] for m in MODES],
            state="readonly",
            width=14,
        )
        mode_cb.pack(side=LEFT, padx=6)
        self.mode_label = ttk.Label(row2, text=dict(MODES)["auto"], style="Muted.TLabel")
        self.mode_label.pack(side=LEFT)
        mode_cb.bind("<<ComboboxSelected>>", self._on_mode)

        row3 = Frame(opts, bg="#FFFFFF")
        row3.pack(fill=X, pady=4)
        ttk.Label(row3, text="连接线", background="#FFFFFF").pack(side=LEFT)
        ttk.Combobox(
            row3,
            textvariable=self.conn_var,
            values=[c[0] for c in CONNECTORS],
            state="readonly",
            width=14,
        ).pack(side=LEFT, padx=6)
        ttk.Label(row3, text="（仅可编辑连接模式）", style="Muted.TLabel").pack(side=LEFT)

        btns = Frame(left, bg="#FFFFFF")
        btns.grid(row=3, column=0, sticky="ew", pady=(10, 0))
        ttk.Button(btns, text="打开文件", command=self.open_file).pack(side=LEFT)
        ttk.Button(btns, text="预览 (F5)", command=self.preview).pack(side=LEFT, padx=6)
        ttk.Checkbutton(btns, text="自动预览", variable=self.auto_preview).pack(side=LEFT, padx=4)
        self.export_btn = ttk.Button(btns, text="导出 Visio…", style="Accent.TButton", command=self.export_vsdx)
        self.export_btn.pack(side=RIGHT)
        self.batch_btn = ttk.Button(btns, text="批量转 Visio…", command=self.batch_export)
        self.batch_btn.pack(side=RIGHT, padx=(0, 8))

        # Right: preview
        right = ttk.Frame(body, style="Card.TFrame", padding=10)
        right.grid(row=0, column=1, sticky="nsew", padx=(6, 0))
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        head = Frame(right, bg="#FFFFFF")
        head.grid(row=0, column=0, sticky="ew")
        ttk.Label(head, text="预览", font=("Microsoft YaHei UI", 10, "bold"), background="#FFFFFF").pack(side=LEFT)
        ttk.Label(head, textvariable=self.kind_var, style="Muted.TLabel").pack(side=LEFT, padx=10)
        ttk.Button(head, text="放大查看", command=self._zoom_preview).pack(side=RIGHT)

        canvas_wrap = Frame(right, bg="#E8EAED", highlightthickness=1, highlightbackground="#D0D4DA")
        canvas_wrap.grid(row=1, column=0, sticky="nsew", pady=(8, 0))
        self.canvas = Canvas(canvas_wrap, bg="#F7F8FC", highlightthickness=0)
        self.hbar = ttk.Scrollbar(canvas_wrap, orient="horizontal", command=self.canvas.xview)
        self.vbar = ttk.Scrollbar(canvas_wrap, orient="vertical", command=self.canvas.yview)
        self.canvas.configure(xscrollcommand=self.hbar.set, yscrollcommand=self.vbar.set)
        self.vbar.pack(side=RIGHT, fill=Y)
        self.hbar.pack(side=BOTTOM, fill=X)
        self.canvas.pack(side=LEFT, fill=BOTH, expand=True)
        self.canvas.bind("<Configure>", lambda e: self._fit_preview())

        status = ttk.Frame(top)
        status.pack(fill=X, pady=(8, 0))
        ttk.Label(status, textvariable=self.status_var, style="Muted.TLabel").pack(side=LEFT)
        self.progress = ttk.Progressbar(status, mode="indeterminate", length=120)
        self.progress.pack(side=RIGHT)

    def _make_theme_card(self, parent: Frame, th: dict) -> Frame:
        outer = Frame(parent, bg="#FFFFFF", padx=4, pady=4, highlightthickness=2, highlightbackground="#DDD")
        inner = Frame(outer, bg="#FFFFFF", cursor="hand2")
        inner.pack()
        Label(inner, text=th["name"], font=("Microsoft YaHei UI", 8, "bold"), bg="#FFFFFF").pack()
        sw = Frame(inner, bg="#FFFFFF")
        sw.pack(pady=3)
        for c in th["swatches"]:
            Frame(sw, bg=c, width=14, height=14, highlightthickness=1, highlightbackground="#999").pack(
                side=LEFT, padx=1
            )
        Label(inner, text=th["desc"], font=("Microsoft YaHei UI", 7), fg="#777", bg="#FFFFFF", wraplength=96).pack()

        def select(_e=None, tid=th["id"]):
            self.theme_var.set(tid)
            self._highlight_themes()
            self._schedule_preview()

        def bind_tree(widget):
            widget.bind("<Button-1>", select)
            for child in widget.winfo_children():
                bind_tree(child)

        bind_tree(outer)
        outer._theme_id = th["id"]  # type: ignore[attr-defined]
        return outer

    def _highlight_themes(self) -> None:
        cur = self.theme_var.get()
        for card in self._theme_cards:
            tid = getattr(card, "_theme_id", "")
            card.configure(highlightbackground="#2F6FED" if tid == cur else "#DDD", highlightthickness=2)

    def _on_mode(self, _e=None) -> None:
        self.mode_label.configure(text=dict(MODES).get(self.mode_var.get(), ""))

    def _on_edit(self, _e=None) -> None:
        if self.editor.edit_modified():
            self.editor.edit_modified(False)
            src = self.editor.get("1.0", END)
            self.kind_var.set(f"类型: {detect_kind(src)}")
            if self.auto_preview.get():
                self._schedule_preview()

    def _schedule_preview(self) -> None:
        if self._preview_job:
            self.root.after_cancel(self._preview_job)
        self._preview_job = self.root.after(450, self.preview)

    def _set_busy(self, busy: bool, msg: str = "") -> None:
        self._busy = busy
        state = DISABLED if busy else NORMAL
        self.export_btn.configure(state=state)
        self.batch_btn.configure(state=state)
        if busy:
            self.progress.start(12)
            if msg:
                self.status_var.set(msg)
        else:
            self.progress.stop()
            if msg:
                self.status_var.set(msg)

    # ---- actions ----
    def _load_sample(self, silent: bool = False) -> None:
        self.editor.delete("1.0", END)
        self.editor.insert("1.0", SAMPLE)
        self.editor.edit_modified(False)
        self.kind_var.set(f"类型: {detect_kind(SAMPLE)}")
        self._highlight_themes()
        if not silent:
            self.preview()

    def clear_editor(self) -> None:
        self.editor.delete("1.0", END)

    def open_file(self) -> None:
        path = filedialog.askopenfilename(
            title="打开 Mermaid",
            filetypes=[
                ("Mermaid", "*.mmd *.mermaid"),
                ("Markdown", "*.md"),
                ("文本", "*.txt"),
                ("全部", "*.*"),
            ],
        )
        if not path:
            return
        p = Path(path)
        text = p.read_text(encoding="utf-8")
        if p.suffix.lower() == ".md":
            import re

            m = re.search(r"```mermaid\s*\n(.*?)```", text, re.DOTALL | re.IGNORECASE)
            if m:
                text = m.group(1)
        self.editor.delete("1.0", END)
        self.editor.insert("1.0", text)
        self._source_path = p
        self.kind_var.set(f"类型: {detect_kind(text)}")
        self.status_var.set(f"已打开: {p.name}")
        self.preview()

    def _theme_meta(self) -> dict:
        tid = self.theme_var.get()
        return next((t for t in THEMES if t["id"] == tid), THEMES[0])

    def preview(self) -> None:
        if self._busy:
            return
        source = strip_fences(self.editor.get("1.0", END))
        if not source.strip():
            self.canvas.delete("all")
            self.status_var.set("请输入 Mermaid 源码")
            return
        theme = self.theme_var.get()
        bg = self._theme_meta()["preview_bg"]
        self.canvas.configure(bg=bg)
        self._set_busy(True, "正在渲染预览…")

        def work():
            try:
                png = render_png(source, theme=theme, scale=2.0)
                err = None
            except Exception as e:
                png, err = None, e
            self.root.after(0, lambda: self._on_preview_done(png, err, source))

        threading.Thread(target=work, daemon=True).start()

    def _on_preview_done(self, png: bytes | None, err: Exception | None, source: str) -> None:
        self._set_busy(False)
        if err is not None:
            self.status_var.set(f"预览失败: {err}")
            self.canvas.delete("all")
            self.canvas.create_text(
                20,
                20,
                anchor="nw",
                text=f"预览失败\n{err}",
                fill="#B00020",
                font=("Microsoft YaHei UI", 10),
                width=max(self.canvas.winfo_width() - 40, 200),
            )
            return
        assert png is not None
        self._last_png = png
        self.kind_var.set(f"类型: {detect_kind(source)}  ·  主题: {self._theme_meta()['name']}")
        self.status_var.set(f"预览就绪  ({len(png)} bytes)")
        self._show_png(png)

    def _show_png(self, png: bytes) -> None:
        img = Image.open(io.BytesIO(png)).convert("RGBA")
        self._raw_img = img
        self._fit_preview()

    def _fit_preview(self) -> None:
        if not hasattr(self, "_raw_img"):
            return
        img = self._raw_img
        cw = max(self.canvas.winfo_width(), 100)
        ch = max(self.canvas.winfo_height(), 100)
        scale = min(cw / img.width, ch / img.height, 1.0)
        # allow slight upscale for tiny diagrams
        if scale > 0.98:
            scale = min(cw / img.width, ch / img.height, 1.5)
        nw, nh = max(1, int(img.width * scale)), max(1, int(img.height * scale))
        shown = img.resize((nw, nh), Image.Resampling.LANCZOS)
        self._photo = ImageTk.PhotoImage(shown)
        self.canvas.delete("all")
        self.canvas.create_image(cw // 2, ch // 2, image=self._photo, anchor="center")
        self.canvas.configure(scrollregion=(0, 0, max(cw, nw), max(ch, nh)))

    def _zoom_preview(self) -> None:
        if not self._last_png:
            messagebox.showinfo("预览", "请先生成预览")
            return
        win = Toplevel(self.root)
        win.title("预览放大")
        win.geometry("1000x700")
        img = Image.open(io.BytesIO(self._last_png)).convert("RGBA")
        canvas = Canvas(win, bg=self._theme_meta()["preview_bg"])
        hbar = ttk.Scrollbar(win, orient="horizontal", command=canvas.xview)
        vbar = ttk.Scrollbar(win, orient="vertical", command=canvas.yview)
        canvas.configure(xscrollcommand=hbar.set, yscrollcommand=vbar.set)
        vbar.pack(side=RIGHT, fill=Y)
        hbar.pack(side=BOTTOM, fill=X)
        canvas.pack(fill=BOTH, expand=True)
        photo = ImageTk.PhotoImage(img)
        canvas.create_image(0, 0, image=photo, anchor="nw")
        canvas.configure(scrollregion=(0, 0, img.width, img.height))
        win._photo = photo  # noqa: SLF001 keep ref

    def save_preview_png(self) -> None:
        if not self._last_png:
            messagebox.showinfo("保存", "请先预览")
            return
        path = filedialog.asksaveasfilename(
            defaultextension=".png",
            filetypes=[("PNG", "*.png")],
            initialfile="mermaid_preview.png",
        )
        if path:
            Path(path).write_bytes(self._last_png)
            self.status_var.set(f"已保存预览: {path}")

    def export_vsdx(self) -> None:
        if self._busy:
            return
        source = strip_fences(self.editor.get("1.0", END))
        if not source.strip():
            messagebox.showwarning("导出", "请先输入 Mermaid 源码")
            return
        initial = "diagram.vsdx"
        if self._source_path:
            initial = self._source_path.with_suffix(".vsdx").name
        path = filedialog.asksaveasfilename(
            title="导出 Visio",
            defaultextension=".vsdx",
            filetypes=[("Visio", "*.vsdx")],
            initialfile=initial,
        )
        if not path:
            return

        theme = self.theme_var.get()
        mode = self.mode_var.get()
        connectors = self.conn_var.get()
        title = Path(path).stem
        self._set_busy(True, "正在导出 Visio…")

        def work():
            try:
                data, method = convert_mermaid_to_vsdx(
                    source,
                    mode=mode,
                    theme=theme,
                    connectors=connectors,
                    title=title,
                )
                Path(path).write_bytes(data)
                err = None
            except Exception as e:
                data, method, err = None, "", e
                traceback.print_exc()
            self.root.after(0, lambda: self._on_export_done(path, method, data, err))

        threading.Thread(target=work, daemon=True).start()

    def _on_export_done(self, path: str, method: str, data: bytes | None, err: Exception | None) -> None:
        self._set_busy(False)
        if err is not None:
            messagebox.showerror("导出失败", str(err))
            self.status_var.set(f"导出失败: {err}")
            return
        assert data is not None
        hint = {"connected": "可编辑+连接", "geometry": "几何形状", "picture": "整图嵌入"}.get(method, method)
        self.status_var.set(f"已导出: {path}  ({hint}, {len(data)} bytes)")
        if messagebox.askyesno("完成", f"已导出 Visio：\n{path}\n\n方式: {hint}\n\n是否打开所在文件夹？"):
            try:
                os.startfile(str(Path(path).resolve().parent))  # type: ignore[attr-defined]
            except Exception:
                pass

    # ---- batch ----
    def batch_export(self) -> None:
        if self._busy:
            return
        BatchDialog(self)

    def _about(self) -> None:
        messagebox.showinfo(
            "关于",
            "Mermaid → Visio\n\n"
            "支持 flowchart / 类图 / ER / 时序 / 状态 / 饼图等全部 Mermaid 图。\n"
            "可选颜色风格，预览后导出 .vsdx。\n"
            "支持单文件导出与批量转 Visio。\n\n"
            "引擎: mermaid-render",
        )


class BatchDialog:
    """批量选择目录/多文件 → 按当前主题/模式导出 .vsdx。"""

    def __init__(self, app: MermaidVisioApp) -> None:
        self.app = app
        self.win = Toplevel(app.root)
        self.win.title("批量转 Visio")
        self.win.geometry("720x560")
        self.win.minsize(640, 480)
        self.win.transient(app.root)
        self.win.grab_set()

        self.in_var = StringVar()
        self.out_var = StringVar()
        self.recursive = BooleanVar(value=True)
        self.files: list[Path] = []
        self._running = False
        self._cancel = False

        pad = ttk.Frame(self.win, padding=12)
        pad.pack(fill=BOTH, expand=True)

        ttk.Label(pad, text="批量将 Mermaid 文件转为 .vsdx（沿用主界面的颜色风格 / 导出模式）").pack(anchor="w")

        row_in = ttk.Frame(pad)
        row_in.pack(fill=X, pady=(10, 4))
        ttk.Label(row_in, text="输入", width=8).pack(side=LEFT)
        ttk.Entry(row_in, textvariable=self.in_var).pack(side=LEFT, fill=X, expand=True, padx=4)
        ttk.Button(row_in, text="选文件夹", command=self._pick_in_dir).pack(side=LEFT)
        ttk.Button(row_in, text="选多文件", command=self._pick_files).pack(side=LEFT, padx=(4, 0))

        row_out = ttk.Frame(pad)
        row_out.pack(fill=X, pady=4)
        ttk.Label(row_out, text="输出", width=8).pack(side=LEFT)
        ttk.Entry(row_out, textvariable=self.out_var).pack(side=LEFT, fill=X, expand=True, padx=4)
        ttk.Button(row_out, text="选文件夹", command=self._pick_out_dir).pack(side=LEFT)

        opts = ttk.Frame(pad)
        opts.pack(fill=X, pady=4)
        ttk.Checkbutton(opts, text="包含子文件夹", variable=self.recursive, command=self._rescan).pack(side=LEFT)
        theme_name = app._theme_meta()["name"]
        mode_name = dict(MODES).get(app.mode_var.get(), app.mode_var.get())
        ttk.Label(
            opts,
            text=f"风格: {theme_name}  ·  模式: {mode_name}",
            style="Muted.TLabel",
        ).pack(side=RIGHT)

        ttk.Label(pad, text="待转换文件").pack(anchor="w", pady=(8, 2))
        list_wrap = Frame(pad)
        list_wrap.pack(fill=BOTH, expand=True)
        self.listbox = Text(list_wrap, height=10, font=("Consolas", 9), wrap=WORD, state=DISABLED)
        sb = ttk.Scrollbar(list_wrap, command=self.listbox.yview)
        self.listbox.configure(yscrollcommand=sb.set)
        self.listbox.pack(side=LEFT, fill=BOTH, expand=True)
        sb.pack(side=RIGHT, fill=Y)

        self.prog = ttk.Progressbar(pad, mode="determinate")
        self.prog.pack(fill=X, pady=(8, 4))
        self.prog_label = StringVar(value="尚未开始")
        ttk.Label(pad, textvariable=self.prog_label).pack(anchor="w")

        ttk.Label(pad, text="日志").pack(anchor="w", pady=(6, 2))
        log_wrap = Frame(pad)
        log_wrap.pack(fill=BOTH, expand=True)
        self.log = Text(log_wrap, height=8, font=("Consolas", 9), wrap=WORD, state=DISABLED)
        lsb = ttk.Scrollbar(log_wrap, command=self.log.yview)
        self.log.configure(yscrollcommand=lsb.set)
        self.log.pack(side=LEFT, fill=BOTH, expand=True)
        lsb.pack(side=RIGHT, fill=Y)

        btns = ttk.Frame(pad)
        btns.pack(fill=X, pady=(10, 0))
        self.start_btn = ttk.Button(btns, text="开始转换", style="Accent.TButton", command=self._start)
        self.start_btn.pack(side=LEFT)
        self.cancel_btn = ttk.Button(btns, text="取消", command=self._cancel_run, state=DISABLED)
        self.cancel_btn.pack(side=LEFT, padx=6)
        ttk.Button(btns, text="打开输出目录", command=self._open_out).pack(side=LEFT)
        ttk.Button(btns, text="关闭", command=self._close).pack(side=RIGHT)

        self.win.protocol("WM_DELETE_WINDOW", self._close)

    def _append_log(self, line: str) -> None:
        self.log.configure(state=NORMAL)
        self.log.insert(END, line + "\n")
        self.log.see(END)
        self.log.configure(state=DISABLED)

    def _set_list(self, lines: list[str]) -> None:
        self.listbox.configure(state=NORMAL)
        self.listbox.delete("1.0", END)
        self.listbox.insert("1.0", "\n".join(lines) if lines else "（未找到 .mmd / .mermaid / .md）")
        self.listbox.configure(state=DISABLED)

    def _pick_in_dir(self) -> None:
        d = filedialog.askdirectory(title="选择包含 Mermaid 的文件夹", parent=self.win)
        if not d:
            return
        self.in_var.set(d)
        if not self.out_var.get():
            self.out_var.set(str(Path(d) / "vsdx_out"))
        self._rescan()

    def _pick_files(self) -> None:
        paths = filedialog.askopenfilenames(
            title="选择多个 Mermaid 文件",
            parent=self.win,
            filetypes=[
                ("Mermaid / Markdown", "*.mmd *.mermaid *.md"),
                ("全部", "*.*"),
            ],
        )
        if not paths:
            return
        self.files = [Path(p) for p in paths]
        self.in_var.set(f"（已选 {len(self.files)} 个文件）")
        if not self.out_var.get() and self.files:
            self.out_var.set(str(self.files[0].parent / "vsdx_out"))
        self._set_list([str(p) for p in self.files])
        self.prog_label.set(f"共 {len(self.files)} 个文件")

    def _pick_out_dir(self) -> None:
        d = filedialog.askdirectory(title="选择输出文件夹", parent=self.win)
        if d:
            self.out_var.set(d)

    def _rescan(self) -> None:
        raw = self.in_var.get().strip()
        if not raw or raw.startswith("（已选"):
            if self.files and raw.startswith("（已选"):
                self._set_list([str(p) for p in self.files])
                self.prog_label.set(f"共 {len(self.files)} 个文件")
            return
        root = Path(raw)
        if not root.exists():
            self.files = []
            self._set_list([])
            self.prog_label.set("输入路径不存在")
            return
        if root.is_file():
            self.files = [root]
        elif self.recursive.get():
            self.files = list(iter_inputs(root))
        else:
            self.files = sorted(
                p
                for p in root.iterdir()
                if p.is_file() and p.suffix.lower() in {".mmd", ".mermaid", ".md"}
            )
        # Prefer showing relative paths when scanning a folder
        if root.is_dir():
            shown = []
            for p in self.files:
                try:
                    shown.append(str(p.relative_to(root)))
                except ValueError:
                    shown.append(str(p))
            self._set_list(shown)
        else:
            self._set_list([p.name for p in self.files])
        self.prog_label.set(f"共 {len(self.files)} 个文件")

    def _start(self) -> None:
        if self._running:
            return
        if not self.files:
            self._rescan()
        if not self.files:
            messagebox.showwarning("批量转换", "没有可转换的文件", parent=self.win)
            return
        out_dir = Path(self.out_var.get().strip() or ".")
        try:
            out_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            messagebox.showerror("输出目录", str(e), parent=self.win)
            return

        theme = self.app.theme_var.get()
        mode = self.app.mode_var.get()
        connectors = self.app.conn_var.get()
        in_root = Path(self.in_var.get()) if Path(self.in_var.get()).is_dir() else None

        self._running = True
        self._cancel = False
        self.start_btn.configure(state=DISABLED)
        self.cancel_btn.configure(state=NORMAL)
        self.app._set_busy(True, "批量转换中…")
        self.prog.configure(maximum=max(len(self.files), 1), value=0)
        self._append_log(f"开始：{len(self.files)} 个文件 → {out_dir}")

        files = list(self.files)

        def work():
            ok = fail = 0
            results: list[str] = []
            for i, src in enumerate(files, 1):
                if self._cancel:
                    results.append("已取消")
                    break
                try:
                    source = read_source(src)
                    if not source.strip():
                        raise ValueError("空文件或未找到 mermaid 代码块")
                    data, method = convert_mermaid_to_vsdx(
                        source,
                        mode=mode,
                        theme=theme,
                        connectors=connectors,
                        title=src.stem,
                    )
                    if in_root is not None:
                        try:
                            rel = src.relative_to(in_root)
                        except ValueError:
                            rel = Path(src.name)
                        dest = out_dir / rel.with_suffix(".vsdx")
                    else:
                        dest = out_dir / f"{src.stem}.vsdx"
                    dest.parent.mkdir(parents=True, exist_ok=True)
                    # Avoid overwrite clash when multiple flat files share stem
                    if in_root is None and dest.exists():
                        dest = out_dir / f"{src.stem}_{i}.vsdx"
                    dest.write_bytes(data)
                    ok += 1
                    line = f"[OK] {src.name} → {dest.name} ({method})"
                except Exception as e:  # noqa: BLE001
                    fail += 1
                    line = f"[FAIL] {src.name}: {e}"
                    traceback.print_exc()
                results.append(line)
                self.win.after(0, lambda i=i, line=line: self._on_progress(i, line))

            self.win.after(0, lambda: self._on_done(ok, fail, out_dir, self._cancel))

        threading.Thread(target=work, daemon=True).start()

    def _on_progress(self, i: int, line: str) -> None:
        self.prog.configure(value=i)
        self.prog_label.set(f"进度 {i}/{len(self.files)}")
        self._append_log(line)

    def _on_done(self, ok: int, fail: int, out_dir: Path, cancelled: bool) -> None:
        self._running = False
        self.start_btn.configure(state=NORMAL)
        self.cancel_btn.configure(state=DISABLED)
        self.app._set_busy(False)
        msg = f"批量完成: 成功 {ok}, 失败 {fail}" + ("（已取消）" if cancelled else "")
        self.prog_label.set(msg)
        self.app.status_var.set(msg)
        self._append_log(msg)
        if ok and messagebox.askyesno("批量转换", f"{msg}\n\n是否打开输出文件夹？", parent=self.win):
            try:
                os.startfile(str(out_dir.resolve()))  # type: ignore[attr-defined]
            except Exception:
                pass

    def _cancel_run(self) -> None:
        self._cancel = True
        self.prog_label.set("正在取消…")

    def _open_out(self) -> None:
        d = self.out_var.get().strip()
        if not d:
            return
        p = Path(d)
        p.mkdir(parents=True, exist_ok=True)
        try:
            os.startfile(str(p.resolve()))  # type: ignore[attr-defined]
        except Exception as e:
            messagebox.showerror("打开目录", str(e), parent=self.win)

    def _close(self) -> None:
        if self._running:
            if not messagebox.askyesno("批量转换", "转换仍在进行，确定取消并关闭？", parent=self.win):
                return
            self._cancel = True
        try:
            self.win.grab_release()
        except Exception:
            pass
        self.win.destroy()


def main() -> None:
    # HiDPI on Windows
    try:
        from ctypes import windll

        windll.shcore.SetProcessDpiAwareness(1)
    except Exception:
        pass
    root = Tk()
    MermaidVisioApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
