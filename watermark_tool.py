"""
批量图片水印工具 v8
支持水印缩放控制框、四角拖动独立拉伸
"""
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
import urllib.request
from PIL import Image, ImageDraw, ImageFont, ImageEnhance, ImageOps, ImageTk
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
import threading


APP_VERSION = "1.0.12"
UPDATE_API_URL = "https://api.github.com/repos/kaiiii777/pic_shuiyin/releases/latest"
UPDATE_ASSET_NAME = "图片水印工具.exe"


class WatermarkItem:
    def __init__(self, content="", x=50, y=50, width_pct=20, height_pct=None):
        self.content = content
        self.x = x          # 左上角X (百分比)
        self.y = y          # 左上角Y (百分比)
        self.width_pct = width_pct   # 宽度百分比
        self.height_pct = height_pct if height_pct is not None else width_pct  # 高度百分比，默认等于宽度
        self.opacity = 1.0


class WatermarkApp:
    def __init__(self, root):
        self.root = root
        self.root.title(f"图片处理工具 {APP_VERSION}")
        self.root.geometry("1200x850")
        self.root.minsize(1080, 760)

        self.watermarks = []
        self.source_images = []
        self.source_root = None
        self.crop_positions = {}
        self.current_image_index = 0
        self.output_dir = tk.StringVar()
        self.output_prefix = tk.StringVar(value="")
        self.output_suffix = tk.StringVar(value="")
        self.use_original_name = tk.BooleanVar(value=False)
        self.overwrite_original = tk.BooleanVar(value=False)
        self.recursive_folders = tk.BooleanVar(value=False)
        self.enable_crop = tk.BooleanVar(value=False)
        self.crop_ratio_w = tk.DoubleVar(value=1)
        self.crop_ratio_h = tk.DoubleVar(value=1)
        self.crop_focus_x = tk.DoubleVar(value=50)
        self.crop_focus_y = tk.DoubleVar(value=50)
        self.enable_resize = tk.BooleanVar(value=False)
        self.resize_width = tk.IntVar(value=900)
        self.resize_height = tk.IntVar(value=900)
        self.resize_mode = tk.StringVar(value="fit")
        self.resize_bg_color = tk.StringVar(value="white")
        self.opacity_text = tk.StringVar(value="100%")
        self.loading_watermark = False
        self.preview_photo = None
        self.wm_photos = []

        # 预览图参数
        self.img_x = 0
        self.img_y = 0
        self.img_w = 0
        self.img_h = 0
        self.full_img_x = 0
        self.full_img_y = 0
        self.full_img_w = 0
        self.full_img_h = 0
        self.crop_box = None

        # 操作状态: 'none', 'move', 'resize_tl', 'resize_top' 等
        self.operation = 'none'
        self.op_wm_idx = -1
        self.op_start_x = 0
        self.op_start_y = 0
        self.op_start_size = 0
        self.op_start_x_percent = 0
        self.op_start_y_percent = 0
        self.op_start_h = 0
        self.op_start_crop_x = 50
        self.op_start_crop_y = 50

        # 控制点大小
        self.handle_size = 8

        self.configure_theme()
        self.set_window_icon()
        self.create_ui()
        self.add_watermark()
        self.root.after(1500, self.start_auto_update_check)

    def resource_path(self, relative_path):
        base_path = getattr(sys, "_MEIPASS", os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base_path, relative_path)

    def set_window_icon(self):
        icon_path = self.resource_path(os.path.join("assets", "app_icon.ico"))
        if os.path.exists(icon_path):
            try:
                self.root.iconbitmap(icon_path)
            except tk.TclError:
                pass

    def configure_theme(self):
        self.root.configure(bg="#F8FAFC")
        style = ttk.Style()
        for theme in ("vista", "xpnative", "winnative", "default"):
            try:
                style.theme_use(theme)
                break
            except tk.TclError:
                continue

        font = ("Microsoft YaHei UI", 9)
        heading_font = ("Microsoft YaHei UI", 9, "bold")
        style.configure(".", font=font, background="#F8FAFC", foreground="#111827")
        style.configure("TFrame", background="#F8FAFC")
        style.configure("TLabelframe", background="#F8FAFC")
        style.configure("TLabelframe.Label", background="#F8FAFC", foreground="#111827", font=heading_font)
        style.configure("TLabel", background="#F8FAFC", foreground="#1F2937")
        style.configure("Muted.TLabel", background="#F8FAFC", foreground="#64748B")
        style.configure("Status.TLabel", background="#F8FAFC", foreground="#0F766E", font=heading_font)
        style.configure("TCheckbutton", background="#F8FAFC", foreground="#1F2937")
        style.configure("TRadiobutton", background="#F8FAFC", foreground="#1F2937")
        style.configure("TButton", padding=(10, 5))
        style.configure("Accent.TButton", padding=(16, 6), foreground="#111827")
        style.configure("Horizontal.TProgressbar", background="#0D9488", troughcolor="#E2E8F0")

    def create_ui(self):
        main_frame = ttk.Frame(self.root, padding="12")
        main_frame.pack(fill=tk.BOTH, expand=True)

        self.create_batch_settings(main_frame)
        self.create_processing_bar(main_frame)

        # ===== 中部 =====
        middle_frame = ttk.Frame(main_frame)
        middle_frame.pack(fill=tk.BOTH, expand=True, pady=3)

        # 左侧：水印列表
        left_frame = ttk.LabelFrame(middle_frame, text="水印列表", padding="5")
        left_frame.pack(side=tk.LEFT, fill=tk.Y, padx=(0, 5))

        list_frame = ttk.Frame(left_frame)
        list_frame.pack(fill=tk.BOTH, expand=True)

        self.watermark_listbox = tk.Listbox(list_frame, height=10, width=28)
        self.watermark_listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.watermark_listbox.bind('<<ListboxSelect>>', self.on_watermark_select)
        self.watermark_listbox.bind('<Double-Button-1>', lambda e: self.delete_watermark())

        scrollbar = ttk.Scrollbar(list_frame, orient=tk.VERTICAL, command=self.watermark_listbox.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.watermark_listbox.config(yscrollcommand=scrollbar.set)

        # 水印编辑
        edit_frame = ttk.LabelFrame(left_frame, text="水印设置", padding="5")
        edit_frame.pack(fill=tk.X, pady=5)

        ttk.Label(edit_frame, text="图片:").grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        self.wm_path = tk.StringVar()
        ttk.Entry(edit_frame, textvariable=self.wm_path, width=16).grid(row=0, column=1, padx=2, pady=2)
        ttk.Button(edit_frame, text="浏览", command=self.browse_watermark).grid(row=0, column=2, padx=2, pady=2)

        ttk.Label(edit_frame, text="宽度(%):").grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        self.wm_width = tk.DoubleVar(value=20)
        width_entry = ttk.Entry(edit_frame, textvariable=self.wm_width, width=8)
        width_entry.grid(row=1, column=1, sticky=tk.W, padx=2, pady=2)
        width_entry.bind('<KeyRelease>', lambda e: self.apply_edit())
        width_entry.bind('<FocusOut>', lambda e: self.apply_edit())

        ttk.Label(edit_frame, text="高度(%):").grid(row=1, column=2, sticky=tk.W, padx=5, pady=2)
        self.wm_height = tk.DoubleVar(value=20)
        height_entry = ttk.Entry(edit_frame, textvariable=self.wm_height, width=8)
        height_entry.grid(row=1, column=3, sticky=tk.W, padx=2, pady=2)
        height_entry.bind('<KeyRelease>', lambda e: self.apply_edit())
        height_entry.bind('<FocusOut>', lambda e: self.apply_edit())

        ttk.Label(edit_frame, text="透明度:").grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        self.wm_opacity = tk.DoubleVar(value=100)
        opacity_scale = ttk.Scale(
            edit_frame,
            from_=0,
            to=100,
            orient=tk.HORIZONTAL,
            variable=self.wm_opacity,
            command=self.on_opacity_change
        )
        opacity_scale.grid(row=2, column=1, columnspan=2, sticky=tk.EW, padx=2, pady=2)
        ttk.Label(edit_frame, textvariable=self.opacity_text, width=5).grid(row=2, column=3, sticky=tk.W, padx=2, pady=2)
        edit_frame.columnconfigure(1, weight=1)

        ttk.Label(edit_frame, text="X(%):").grid(row=3, column=0, sticky=tk.W, padx=5, pady=2)
        self.wm_x = tk.DoubleVar(value=50)
        x_entry = ttk.Entry(edit_frame, textvariable=self.wm_x, width=8)
        x_entry.grid(row=3, column=1, sticky=tk.W, padx=2, pady=2)
        x_entry.bind('<KeyRelease>', lambda e: self.apply_edit())
        x_entry.bind('<FocusOut>', lambda e: self.apply_edit())

        ttk.Label(edit_frame, text="Y(%):").grid(row=3, column=2, sticky=tk.W, padx=5, pady=2)
        self.wm_y = tk.DoubleVar(value=50)
        y_entry = ttk.Entry(edit_frame, textvariable=self.wm_y, width=8)
        y_entry.grid(row=3, column=3, sticky=tk.W, padx=2, pady=2)
        y_entry.bind('<KeyRelease>', lambda e: self.apply_edit())
        y_entry.bind('<FocusOut>', lambda e: self.apply_edit())

        btn_frame = ttk.Frame(left_frame)
        btn_frame.pack(fill=tk.X, pady=5)
        ttk.Button(btn_frame, text="添加", command=self.add_watermark).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_frame, text="删除", command=self.delete_watermark).pack(side=tk.LEFT, padx=2)

        # 中间：图片列表
        center_frame = ttk.LabelFrame(middle_frame, text="图片列表", padding="5")
        center_frame.pack(side=tk.LEFT, fill=tk.Y, padx=5)

        self.image_listbox = tk.Listbox(center_frame, height=20, width=25)
        self.image_listbox.pack(fill=tk.Y, expand=True)
        self.image_listbox.bind('<<ListboxSelect>>', self.on_image_select)

        img_scroll = ttk.Scrollbar(center_frame, orient=tk.VERTICAL, command=self.image_listbox.yview)
        img_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.image_listbox.config(yscrollcommand=img_scroll.set)

        # 右侧：预览区
        right_frame = ttk.LabelFrame(middle_frame, text="预览 (拖动水印移动, 拖动裁切框调整位置)", padding="5")
        right_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.canvas = tk.Canvas(right_frame, bg='#555555', width=525, height=420)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        self.canvas.bind('<Button-1>', self.on_canvas_click)
        self.canvas.bind('<B1-Motion>', self.on_canvas_drag)
        self.canvas.bind('<ButtonRelease-1>', self.on_canvas_release)

        info_frame = ttk.Frame(right_frame)
        info_frame.pack(fill=tk.X, pady=2)
        self.preview_info = ttk.Label(info_frame, text="请选择源图片")
        self.preview_info.pack(side=tk.LEFT)
        ttk.Button(info_frame, text="刷新", command=self.update_preview).pack(side=tk.RIGHT)

        self.update_watermark_list()

    def create_batch_settings(self, parent):
        header_frame = ttk.Frame(parent)
        header_frame.pack(fill=tk.X, pady=(0, 6))

        ttk.Label(header_frame, text="批处理设置", font=("Microsoft YaHei UI", 10, "bold")).pack(side=tk.LEFT)
        ttk.Button(
            header_frame,
            text="检查更新",
            command=lambda: self.start_update_check(False)
        ).pack(side=tk.RIGHT)

        settings_frame = ttk.Frame(parent)
        settings_frame.pack(fill=tk.X, pady=(0, 6))
        settings_frame.columnconfigure(0, weight=3)
        settings_frame.columnconfigure(1, weight=2)

        input_frame = ttk.LabelFrame(settings_frame, text="输入与输出", padding=(10, 8))
        input_frame.grid(row=0, column=0, sticky=tk.NSEW, padx=(0, 6))
        input_frame.columnconfigure(3, weight=1)

        ttk.Label(input_frame, text="源图片").grid(row=0, column=0, sticky=tk.W, padx=(0, 8), pady=3)
        ttk.Button(input_frame, text="选择图片", command=self.select_images).grid(row=0, column=1, sticky=tk.W, padx=(0, 4), pady=3)
        ttk.Button(input_frame, text="选择文件夹", command=self.select_folder).grid(row=0, column=2, sticky=tk.W, padx=(0, 8), pady=3)
        self.source_count_label = ttk.Label(input_frame, text="已选择: 0 张图片", style="Muted.TLabel")
        self.source_count_label.grid(row=0, column=3, sticky=tk.W, pady=3)
        ttk.Checkbutton(
            input_frame,
            text="处理子文件夹",
            variable=self.recursive_folders
        ).grid(row=0, column=4, sticky=tk.E, padx=(8, 0), pady=3)

        ttk.Label(input_frame, text="输出目录").grid(row=1, column=0, sticky=tk.W, padx=(0, 8), pady=3)
        ttk.Entry(input_frame, textvariable=self.output_dir, width=34).grid(row=1, column=1, columnspan=3, sticky=tk.EW, padx=(0, 4), pady=3)
        ttk.Button(input_frame, text="浏览", command=self.select_output_dir).grid(row=1, column=4, sticky=tk.E, pady=3)

        option_tabs = ttk.Notebook(settings_frame)
        option_tabs.grid(row=0, column=1, sticky=tk.NSEW, padx=(6, 0))

        filename_frame = ttk.Frame(option_tabs, padding=(10, 8))
        option_tabs.add(filename_frame, text="导出")
        filename_frame.columnconfigure(1, weight=1)
        filename_frame.columnconfigure(3, weight=1)

        ttk.Label(filename_frame, text="前缀").grid(row=0, column=0, sticky=tk.W, padx=(0, 6), pady=3)
        ttk.Entry(filename_frame, textvariable=self.output_prefix, width=14).grid(row=0, column=1, sticky=tk.EW, padx=(0, 10), pady=3)
        ttk.Label(filename_frame, text="后缀").grid(row=0, column=2, sticky=tk.W, padx=(0, 6), pady=3)
        ttk.Entry(filename_frame, textvariable=self.output_suffix, width=14).grid(row=0, column=3, sticky=tk.EW, pady=3)
        ttk.Checkbutton(
            filename_frame,
            text="按原文件名导出",
            variable=self.use_original_name
        ).grid(row=1, column=0, columnspan=2, sticky=tk.W, pady=(5, 0))
        ttk.Checkbutton(
            filename_frame,
            text="覆盖原文件",
            variable=self.overwrite_original
        ).grid(row=1, column=2, columnspan=2, sticky=tk.W, pady=(5, 0))

        crop_frame = ttk.Frame(option_tabs, padding=(10, 8))
        option_tabs.add(crop_frame, text="裁切")
        crop_frame.columnconfigure(5, weight=1)

        ttk.Checkbutton(
            crop_frame,
            text="启用裁切",
            variable=self.enable_crop,
            command=self.update_preview
        ).grid(row=0, column=0, sticky=tk.W, padx=(0, 12), pady=3)
        ttk.Label(crop_frame, text="目标比例").grid(row=0, column=1, sticky=tk.W, padx=(0, 6), pady=3)
        ratio_box = ttk.Combobox(
            crop_frame,
            values=("1:1", "4:3", "3:4", "16:9", "9:16"),
            width=8,
            state="readonly"
        )
        ratio_box.set("1:1")
        ratio_box.grid(row=0, column=2, sticky=tk.W, padx=(0, 10), pady=3)
        ratio_box.bind("<<ComboboxSelected>>", lambda e: self.set_crop_ratio(ratio_box.get()))
        ttk.Entry(crop_frame, textvariable=self.crop_ratio_w, width=6).grid(row=0, column=3, sticky=tk.W, pady=3)
        ttk.Label(crop_frame, text=":").grid(row=0, column=4, padx=3, pady=3)
        ttk.Entry(crop_frame, textvariable=self.crop_ratio_h, width=6).grid(row=0, column=5, sticky=tk.W, pady=3)
        ttk.Button(crop_frame, text="应用比例", command=self.update_preview).grid(row=0, column=6, sticky=tk.E, padx=(10, 0), pady=3)

        resize_frame = ttk.Frame(option_tabs, padding=(10, 8))
        option_tabs.add(resize_frame, text="尺寸")
        resize_frame.columnconfigure(4, weight=1)

        ttk.Checkbutton(
            resize_frame,
            text="启用尺寸修改",
            variable=self.enable_resize,
            command=self.update_preview
        ).grid(row=0, column=0, columnspan=2, sticky=tk.W, padx=(0, 10), pady=3)
        ttk.Label(resize_frame, text="宽").grid(row=0, column=2, sticky=tk.E, padx=(0, 4), pady=3)
        ttk.Spinbox(resize_frame, from_=1, to=20000, textvariable=self.resize_width, width=8, command=self.update_preview).grid(row=0, column=3, sticky=tk.W, pady=3)
        ttk.Label(resize_frame, text="高").grid(row=0, column=4, sticky=tk.E, padx=(10, 4), pady=3)
        ttk.Spinbox(resize_frame, from_=1, to=20000, textvariable=self.resize_height, width=8, command=self.update_preview).grid(row=0, column=5, sticky=tk.W, pady=3)

        ttk.Label(resize_frame, text="缩放模式").grid(row=1, column=0, sticky=tk.W, pady=3)
        ttk.Radiobutton(resize_frame, text="留白适配", variable=self.resize_mode, value="fit", command=self.update_preview).grid(row=1, column=1, sticky=tk.W, pady=3)
        ttk.Radiobutton(resize_frame, text="裁剪填充", variable=self.resize_mode, value="fill", command=self.update_preview).grid(row=1, column=2, columnspan=2, sticky=tk.W, pady=3)
        ttk.Radiobutton(resize_frame, text="拉伸填充", variable=self.resize_mode, value="stretch", command=self.update_preview).grid(row=1, column=4, columnspan=2, sticky=tk.W, pady=3)

        ttk.Label(resize_frame, text="白边颜色").grid(row=2, column=0, sticky=tk.W, pady=3)
        ttk.Combobox(
            resize_frame,
            textvariable=self.resize_bg_color,
            values=("white", "black", "#f5f5f5", "#ffffff"),
            width=12
        ).grid(row=2, column=1, columnspan=2, sticky=tk.W, pady=3)
        ttk.Label(resize_frame, text="仅留白适配有效", style="Muted.TLabel").grid(row=2, column=3, columnspan=3, sticky=tk.W, padx=(10, 0), pady=3)

    def create_processing_bar(self, parent):
        processing_frame = ttk.LabelFrame(parent, text="处理进度", padding=(10, 8))
        processing_frame.pack(fill=tk.X, pady=(0, 8))
        processing_frame.columnconfigure(1, weight=1)

        self.status_label = ttk.Label(processing_frame, text="就绪", style="Status.TLabel", width=14)
        self.status_label.grid(row=0, column=0, sticky=tk.W, padx=(0, 10))

        self.progress = ttk.Progressbar(processing_frame, mode='determinate')
        self.progress.grid(row=0, column=1, sticky=tk.EW, padx=(0, 12))

        tk.Button(
            processing_frame,
            text="开始处理",
            command=self.start_processing,
            bg="#EA580C",
            fg="#FFFFFF",
            activebackground="#C2410C",
            activeforeground="#FFFFFF",
            relief=tk.FLAT,
            bd=0,
            cursor="hand2",
            font=("Microsoft YaHei UI", 10, "bold"),
            padx=18,
            pady=7
        ).grid(row=0, column=2, sticky=tk.E)

    def add_watermark(self):
        # 先保存当前编辑框的内容到当前选中水印（如果有内容）
        selection = self.watermark_listbox.curselection()
        if selection:
            self.apply_edit()

        # 创建一个新的空水印，避免误复制当前水印图片和位置
        wm = WatermarkItem(width_pct=15, height_pct=15)
        self.watermarks.append(wm)
        new_index = len(self.watermarks) - 1
        self.update_watermark_list(new_index)
        self.load_watermark_to_editor(new_index)
        self.update_preview()

    def update_watermark_list(self, selected_index=None):
        if selected_index is None:
            selection = self.watermark_listbox.curselection()
            selected_index = selection[0] if selection else None

        self.watermark_listbox.delete(0, tk.END)
        for i, wm in enumerate(self.watermarks):
            if wm.content:
                name = os.path.basename(wm.content)
                self.watermark_listbox.insert(
                    tk.END,
                    f"{i+1}. {name}  {wm.width_pct:.1f}x{wm.height_pct:.1f}%  透明度{int(wm.opacity * 100)}%"
                )
            else:
                self.watermark_listbox.insert(tk.END, f"{i+1}. (未设置)")

        if selected_index is not None and 0 <= selected_index < len(self.watermarks):
            self.watermark_listbox.selection_clear(0, tk.END)
            self.watermark_listbox.selection_set(selected_index)
            self.watermark_listbox.activate(selected_index)
            self.watermark_listbox.see(selected_index)

    def on_watermark_select(self, event):
        selection = self.watermark_listbox.curselection()
        if selection:
            self.load_watermark_to_editor(selection[0])
        self.update_preview()

    def load_watermark_to_editor(self, idx):
        if idx >= len(self.watermarks):
            return

        wm = self.watermarks[idx]
        self.loading_watermark = True
        self.wm_path.set(wm.content)
        self.wm_width.set(round(wm.width_pct, 1))
        self.wm_height.set(round(wm.height_pct, 1))
        self.wm_opacity.set(round(wm.opacity * 100))
        self.opacity_text.set(f"{int(round(wm.opacity * 100))}%")
        self.wm_x.set(round(wm.x, 1))
        self.wm_y.set(round(wm.y, 1))
        self.loading_watermark = False

    def on_opacity_change(self, value):
        try:
            percent = max(0, min(100, float(value)))
        except tk.TclError:
            return
        self.opacity_text.set(f"{int(round(percent))}%")
        if self.loading_watermark:
            return

        selection = self.watermark_listbox.curselection()
        if not selection:
            return

        idx = selection[0]
        if idx < len(self.watermarks):
            self.watermarks[idx].opacity = percent / 100
            self.update_watermark_list(idx)
            self.update_preview()

    def browse_watermark(self):
        file = filedialog.askopenfilename(
            title="选择水印图片",
            filetypes=[("图片文件", "*.png *.jpg *.jpeg *.bmp *.gif"), ("所有文件", "*.*")]
        )
        if file:
            if not self.watermarks or not self.watermark_listbox.curselection():
                self.add_watermark()
            self.wm_path.set(file)
            # 自动设置一个基于图片尺寸的默认宽度
            try:
                with Image.open(file) as img:
                    # 根据常见水印尺寸，设置一个合理的默认百分比
                    # 水印通常占图片的5%-30%，这里默认15%
                    self.wm_width.set(15)
                    self.wm_height.set(15)
            except:
                pass
            self.apply_edit()

    def get_number(self, variable, fallback):
        try:
            return variable.get()
        except tk.TclError:
            return fallback

    def apply_edit(self):
        selection = self.watermark_listbox.curselection()
        if not selection:
            return
        idx = selection[0]
        if idx < len(self.watermarks):
            wm = self.watermarks[idx]
            wm.content = self.wm_path.get()
            wm.width_pct = max(1, self.get_number(self.wm_width, wm.width_pct))
            wm.height_pct = max(1, self.get_number(self.wm_height, wm.height_pct))
            wm.opacity = max(0, min(100, self.get_number(self.wm_opacity, wm.opacity * 100))) / 100
            wm.x = self.get_number(self.wm_x, wm.x)
            wm.y = self.get_number(self.wm_y, wm.y)
            self.opacity_text.set(f"{int(round(wm.opacity * 100))}%")
            self.update_watermark_list(idx)
            self.update_preview()

    def delete_watermark(self):
        selection = self.watermark_listbox.curselection()
        if selection:
            idx = selection[0]
            del self.watermarks[idx]
            next_index = min(idx, len(self.watermarks) - 1)
            self.update_watermark_list(next_index)
            if next_index >= 0:
                self.load_watermark_to_editor(next_index)
            else:
                self.wm_path.set("")
                self.wm_width.set(15)
                self.wm_height.set(15)
                self.wm_opacity.set(100)
                self.opacity_text.set("100%")
                self.wm_x.set(50)
                self.wm_y.set(50)
            self.update_preview()

    def update_image_list(self):
        self.image_listbox.delete(0, tk.END)
        for i, img_path in enumerate(self.source_images):
            if self.source_root:
                try:
                    name = os.path.relpath(img_path, self.source_root)
                except ValueError:
                    name = os.path.basename(img_path)
            else:
                name = os.path.basename(img_path)
            prefix = "▶ " if i == self.current_image_index else "  "
            self.image_listbox.insert(tk.END, f"{prefix}{name}")
            if i == self.current_image_index:
                self.image_listbox.itemconfig(i, fg='blue')

    def on_image_select(self, event):
        selection = self.image_listbox.curselection()
        if selection:
            self.save_current_crop_position()
            self.current_image_index = selection[0]
            self.load_current_crop_position()
            self.update_image_list()
            self.update_preview()

    def get_current_image_path(self):
        if not self.source_images or self.current_image_index >= len(self.source_images):
            return None
        return self.source_images[self.current_image_index]

    def save_current_crop_position(self):
        img_path = self.get_current_image_path()
        if not img_path:
            return
        try:
            self.crop_positions[img_path] = (self.crop_focus_x.get(), self.crop_focus_y.get())
        except tk.TclError:
            pass

    def load_current_crop_position(self):
        img_path = self.get_current_image_path()
        focus_x, focus_y = self.crop_positions.get(img_path, (50, 50))
        self.crop_focus_x.set(focus_x)
        self.crop_focus_y.set(focus_y)

    def get_crop_focus_for_path(self, img_path):
        return self.crop_positions.get(img_path, (50, 50))

    def select_images(self):
        files = filedialog.askopenfilenames(
            title="选择图片",
            initialdir=self.output_dir.get() or None,
            filetypes=[("图片文件", "*.jpg *.jpeg *.png *.bmp *.gif *.webp *.tiff"), ("所有文件", "*.*")]
        )
        if files:
            self.source_images = list(files)
            self.source_root = None
            self.crop_positions = {}
            self.current_image_index = 0
            self.load_current_crop_position()
            self.source_count_label.config(text=f"已选择: {len(self.source_images)} 张图片")
            self.update_image_list()
            self.update_preview()

    def select_folder(self):
        folder = filedialog.askdirectory(
            title="选择文件夹",
            initialdir=self.output_dir.get() or None
        )
        if folder:
            extensions = ('.jpg', '.jpeg', '.png', '.bmp', '.gif', '.webp', '.tiff')
            if self.recursive_folders.get():
                image_paths = []
                for current_dir, _, filenames in os.walk(folder):
                    filenames = [f for f in filenames if f.lower().endswith(extensions)]
                    filenames.sort()
                    image_paths.extend(os.path.join(current_dir, f) for f in filenames)
                self.source_images = image_paths
            else:
                files = [f for f in os.listdir(folder) if f.lower().endswith(extensions)]
                files.sort()
                self.source_images = [os.path.join(folder, f) for f in files]
            self.source_root = folder
            self.crop_positions = {}
            self.current_image_index = 0
            self.load_current_crop_position()
            self.source_count_label.config(text=f"已选择: {len(self.source_images)} 张图片")
            self.update_image_list()
            self.update_preview()

    def select_output_dir(self):
        folder = filedialog.askdirectory(title="选择输出目录")
        if folder:
            self.output_dir.set(folder)

    def clean_filename_part(self, text):
        invalid_chars = '<>:"/\\|?*'
        cleaned = text.strip()
        for char in invalid_chars:
            cleaned = cleaned.replace(char, "_")
        return cleaned

    def get_output_path(self, img_path, output_dir):
        if self.overwrite_original.get():
            return img_path

        save_dir = output_dir if output_dir else os.path.dirname(img_path)
        if output_dir and self.source_root:
            try:
                rel_dir = os.path.dirname(os.path.relpath(img_path, self.source_root))
                if rel_dir and rel_dir != ".":
                    save_dir = os.path.join(output_dir, rel_dir)
            except ValueError:
                pass
        original_name = os.path.basename(img_path)

        if self.use_original_name.get():
            output_name = original_name
        else:
            name, ext = os.path.splitext(original_name)
            prefix = self.clean_filename_part(self.output_prefix.get())
            suffix = self.clean_filename_part(self.output_suffix.get())
            output_name = f"{prefix}{name}{suffix}{ext}"

        return os.path.join(save_dir, output_name)

    def set_crop_ratio(self, ratio_text):
        try:
            width_text, height_text = ratio_text.split(":", 1)
            self.crop_ratio_w.set(float(width_text))
            self.crop_ratio_h.set(float(height_text))
        except (ValueError, tk.TclError):
            return
        self.update_preview()

    def get_crop_ratio(self):
        try:
            width = self.crop_ratio_w.get()
            height = self.crop_ratio_h.get()
        except tk.TclError:
            return None
        if width <= 0 or height <= 0:
            return None
        return width / height

    def is_crop_enabled(self):
        return self.enable_crop.get() and self.get_crop_ratio() is not None

    def get_crop_box_for_image(self, img, img_path=None):
        target_ratio = self.get_crop_ratio()
        if target_ratio is None:
            return (0, 0, img.width, img.height)
        focus_x, focus_y = self.get_crop_focus_for_path(img_path) if img_path else (None, None)

        width, height = img.size
        current_ratio = width / height
        if abs(current_ratio - target_ratio) < 0.0001:
            return (0, 0, width, height)

        if current_ratio > target_ratio:
            new_width = int(height * target_ratio)
            max_left = width - new_width
            if focus_x is None:
                try:
                    focus_x = self.crop_focus_x.get()
                except tk.TclError:
                    focus_x = 50
            focus = focus_x / 100
            left = int(round(max_left * self.clamp_value(focus, 0, 1)))
            return (left, 0, left + new_width, height)

        new_height = int(width / target_ratio)
        max_top = height - new_height
        if focus_y is None:
            try:
                focus_y = self.crop_focus_y.get()
            except tk.TclError:
                focus_y = 50
        focus = focus_y / 100
        top = int(round(max_top * self.clamp_value(focus, 0, 1)))
        return (0, top, width, top + new_height)

    def center_crop_to_ratio(self, img, img_path=None):
        if not self.enable_crop.get():
            return img

        crop_box = self.get_crop_box_for_image(img, img_path)
        if crop_box == (0, 0, img.width, img.height):
            return img
        return img.crop(crop_box)

    def get_resize_size(self):
        try:
            width = int(self.resize_width.get())
            height = int(self.resize_height.get())
        except (tk.TclError, ValueError):
            return None
        if width <= 0 or height <= 0:
            return None
        return width, height

    def resize_image(self, img, img_path=None):
        if not self.enable_resize.get():
            return img

        size = self.get_resize_size()
        if size is None:
            return img

        target_w, target_h = size
        mode = self.resize_mode.get()
        if mode == "stretch":
            return img.resize((target_w, target_h), Image.LANCZOS)

        if mode == "fill":
            return ImageOps.fit(img, (target_w, target_h), method=Image.LANCZOS, centering=(0.5, 0.5))

        resized = img.copy()
        resized.thumbnail((target_w, target_h), Image.LANCZOS)
        bg_color = self.resize_bg_color.get().strip() or "white"
        try:
            canvas = Image.new("RGB", (target_w, target_h), bg_color)
        except ValueError:
            canvas = Image.new("RGB", (target_w, target_h), "white")
        if resized.mode in ("RGBA", "LA"):
            paste_img = resized.convert("RGBA")
            x = (target_w - paste_img.width) // 2
            y = (target_h - paste_img.height) // 2
            canvas.paste(paste_img, (x, y), paste_img)
        else:
            paste_img = resized.convert("RGB")
            x = (target_w - paste_img.width) // 2
            y = (target_h - paste_img.height) // 2
            canvas.paste(paste_img, (x, y))
        return canvas

    def get_canvas_crop_box(self, crop_box, scale):
        left, top, right, bottom = crop_box
        return (
            self.full_img_x + int(round(left * scale)),
            self.full_img_y + int(round(top * scale)),
            self.full_img_x + int(round(right * scale)),
            self.full_img_y + int(round(bottom * scale)),
        )

    def normalize_image_orientation(self, img):
        try:
            exif = img.getexif()
            if exif:
                orientation = exif.get(0x0112)
                if orientation == 3:
                    return img.rotate(180, expand=True)
                if orientation == 6:
                    return img.rotate(270, expand=True)
                if orientation == 8:
                    return img.rotate(90, expand=True)
        except Exception:
            pass
        return img

    def parse_version(self, version_text):
        version_text = version_text.strip().lower().lstrip("v")
        parts = []
        for item in version_text.split("."):
            number = ""
            for char in item:
                if char.isdigit():
                    number += char
                else:
                    break
            parts.append(int(number) if number else 0)
        while len(parts) < 3:
            parts.append(0)
        return tuple(parts[:3])

    def is_newer_version(self, remote_version):
        return self.parse_version(remote_version) > self.parse_version(APP_VERSION)

    def get_app_exe_path(self):
        if getattr(sys, "frozen", False):
            return sys.executable
        return os.path.abspath(__file__)

    def get_app_dir(self):
        if getattr(sys, "frozen", False):
            return os.path.dirname(sys.executable)
        return os.path.dirname(os.path.abspath(__file__))

    def start_auto_update_check(self):
        self.start_update_check(True)

    def start_update_check(self, silent_when_latest=False):
        thread = threading.Thread(target=lambda: self.check_for_updates(silent_when_latest), daemon=True)
        thread.start()

    def check_for_updates(self, silent_when_latest=False):
        try:
            self.status_label.config(text="正在检查更新...")
            release = self.fetch_latest_release()
            remote_version = release.get("tag_name", "").strip()
            if not remote_version:
                if not silent_when_latest:
                    messagebox.showinfo("检查更新", "没有找到有效的版本号。")
                return

            if not self.is_newer_version(remote_version):
                if not silent_when_latest:
                    messagebox.showinfo("检查更新", f"当前已是最新版本：{APP_VERSION}")
                return

            asset = self.find_update_asset(release)
            if not asset:
                messagebox.showwarning(
                    "检查更新",
                    f"发现新版本 {remote_version}，但 Release 中没有找到 {UPDATE_ASSET_NAME}。"
                )
                return

            release_notes = self.format_release_notes(release)
            message = (
                f"发现新版本 {remote_version}\n"
                f"当前版本 {APP_VERSION}\n\n"
                f"更新内容：\n{release_notes}\n\n"
                "是否立即下载并更新？"
            )
            if not messagebox.askyesno("发现新版本", message):
                return

            self.download_and_install_update(asset, remote_version)

        except urllib.error.HTTPError as e:
            if e.code in (401, 403, 404):
                messagebox.showwarning(
                    "检查更新",
                    "无法读取 GitHub Release。\n如果仓库是私有的，请把 Release 资源放到公开地址，或改用 OSS/COS 更新地址。"
                )
            else:
                messagebox.showerror("检查更新", f"检查更新失败：HTTP {e.code}")
        except Exception as e:
            messagebox.showerror("检查更新", f"检查更新失败：{e}")
        finally:
            self.status_label.config(text="就绪")

    def fetch_latest_release(self):
        request = urllib.request.Request(
            UPDATE_API_URL,
            headers={
                "Accept": "application/vnd.github+json",
                "User-Agent": f"pic-shuiyin/{APP_VERSION}",
            }
        )
        with urllib.request.urlopen(request, timeout=20) as response:
            return json.loads(response.read().decode("utf-8"))

    def format_release_notes(self, release):
        notes = (release.get("body") or "").strip()
        if not notes:
            return "本次更新未填写说明。"
        notes = notes.replace("\r\n", "\n").replace("\r", "\n")
        max_length = 900
        if len(notes) > max_length:
            notes = notes[:max_length].rstrip() + "\n..."
        return notes

    def find_update_asset(self, release):
        assets = release.get("assets", [])
        for asset in assets:
            if asset.get("name") == UPDATE_ASSET_NAME or asset.get("label") == UPDATE_ASSET_NAME:
                return asset
        for asset in assets:
            name = asset.get("name", "")
            if name.lower().endswith(".exe"):
                return asset
        return None

    def download_and_install_update(self, asset, remote_version):
        download_url = asset.get("browser_download_url")
        if not download_url:
            messagebox.showwarning("检查更新", "更新文件没有下载地址。")
            return

        update_dir = tempfile.mkdtemp(prefix="pic_shuiyin_update_")
        new_exe_path = os.path.join(update_dir, UPDATE_ASSET_NAME)
        self.status_label.config(text=f"正在下载更新 {remote_version}...")
        self.download_file(download_url, new_exe_path)

        expected_hash = self.get_asset_sha256(asset)
        if expected_hash:
            actual_hash = self.sha256_file(new_exe_path)
            if actual_hash.lower() != expected_hash.lower():
                messagebox.showerror("检查更新", "更新文件校验失败，已取消更新。")
                return

        current_exe = self.get_app_exe_path()
        if not getattr(sys, "frozen", False):
            messagebox.showinfo("检查更新", f"开发模式下已下载新版到：\n{new_exe_path}")
            return

        self.launch_updater(new_exe_path, current_exe)
        self.root.after(300, self.root.destroy)

    def download_file(self, url, destination):
        request = urllib.request.Request(url, headers={"User-Agent": f"pic-shuiyin/{APP_VERSION}"})
        with urllib.request.urlopen(request, timeout=60) as response, open(destination, "wb") as file:
            total = int(response.headers.get("Content-Length") or 0)
            downloaded = 0
            while True:
                chunk = response.read(1024 * 256)
                if not chunk:
                    break
                file.write(chunk)
                downloaded += len(chunk)
                if total:
                    percent = int(downloaded / total * 100)
                    self.status_label.config(text=f"正在下载更新... {percent}%")
                    self.root.update_idletasks()

    def get_asset_sha256(self, asset):
        name = asset.get("name", "")
        for key in ("digest", "sha256"):
            value = asset.get(key)
            if value:
                return value.replace("sha256:", "")
        if ".sha256-" in name:
            return name.rsplit(".sha256-", 1)[-1].split(".")[0]
        return None

    def sha256_file(self, path):
        sha256 = hashlib.sha256()
        with open(path, "rb") as file:
            for chunk in iter(lambda: file.read(1024 * 1024), b""):
                sha256.update(chunk)
        return sha256.hexdigest()

    def launch_updater(self, new_exe_path, current_exe):
        updater_path = os.path.join(os.path.dirname(new_exe_path), "update.bat")
        current_dir = os.path.dirname(current_exe)
        script = f"""@echo off
chcp 65001 >nul
set _PYI_APPLICATION_HOME_DIR=
set _PYI_ARCHIVE_FILE=
set _PYI_PARENT_PROCESS_LEVEL=
set _PYI_SPLASH_IPC=
timeout /t 2 /nobreak >nul
:wait_loop
copy /y "{new_exe_path}" "{current_exe}" >nul
if errorlevel 1 (
  timeout /t 1 /nobreak >nul
  goto wait_loop
)
timeout /t 1 /nobreak >nul
start "" /d "{current_dir}" "{current_exe}"
del "%~f0"
"""
        with open(updater_path, "w", encoding="utf-8") as file:
            file.write(script)
        subprocess.Popen(
            ["cmd", "/c", updater_path],
            creationflags=subprocess.CREATE_NO_WINDOW if hasattr(subprocess, "CREATE_NO_WINDOW") else 0
        )

    def get_watermark_rect(self, wm, wm_img):
        """获取水印在canvas上的矩形区域"""
        wm_w = int(self.img_w * wm.width_pct / 100)
        wm_h = int(self.img_h * wm.height_pct / 100)

        left = self.img_x + int(self.img_w * wm.x / 100)
        top = self.img_y + int(self.img_h * wm.y / 100)

        return left, top, wm_w, wm_h

    def get_resize_handles(self, left, top, width, height):
        right = left + width
        bottom = top + height
        center_x = left + width // 2
        center_y = top + height // 2
        return {
            'tl': (left, top),
            'top': (center_x, top),
            'tr': (right, top),
            'right': (right, center_y),
            'br': (right, bottom),
            'bottom': (center_x, bottom),
            'bl': (left, bottom),
            'left': (left, center_y),
        }

    def clamp_value(self, value, min_value, max_value):
        return max(min_value, min(max_value, value))

    def resize_corner_keep_ratio(self, wm, handle, delta_x_pct, delta_y_pct):
        start_x = self.op_start_x_percent
        start_y = self.op_start_y_percent
        start_w = max(1, self.op_start_size)
        start_h = max(1, self.op_start_h)
        start_right = start_x + start_w
        start_bottom = start_y + start_h

        raw_w = start_w + (delta_x_pct if 'r' in handle else -delta_x_pct)
        raw_h = start_h + (delta_y_pct if 'b' in handle else -delta_y_pct)
        scale_x = raw_w / start_w
        scale_y = raw_h / start_h
        scale = scale_x if abs(scale_x - 1) >= abs(scale_y - 1) else scale_y

        if handle == 'br':
            max_w, max_h = 100 - start_x, 100 - start_y
        elif handle == 'tl':
            max_w, max_h = start_right, start_bottom
        elif handle == 'tr':
            max_w, max_h = 100 - start_x, start_bottom
        else:  # bl
            max_w, max_h = start_right, 100 - start_y

        min_scale = max(1 / start_w, 1 / start_h)
        max_scale = min(200 / start_w, 200 / start_h, max_w / start_w, max_h / start_h)
        scale = self.clamp_value(scale, min_scale, max_scale)
        new_w = start_w * scale
        new_h = start_h * scale

        if handle == 'br':
            new_x, new_y = start_x, start_y
        elif handle == 'tl':
            new_x, new_y = start_right - new_w, start_bottom - new_h
        elif handle == 'tr':
            new_x, new_y = start_x, start_bottom - new_h
        else:  # bl
            new_x, new_y = start_right - new_w, start_y

        wm.x = self.clamp_value(new_x, 0, 100 - new_w)
        wm.y = self.clamp_value(new_y, 0, 100 - new_h)
        wm.width_pct = new_w
        wm.height_pct = new_h

    def resize_edge_stretch(self, wm, handle, delta_x_pct, delta_y_pct):
        start_x = self.op_start_x_percent
        start_y = self.op_start_y_percent
        start_w = max(1, self.op_start_size)
        start_h = max(1, self.op_start_h)
        start_right = start_x + start_w
        start_bottom = start_y + start_h

        if handle == 'right':
            wm.width_pct = self.clamp_value(start_w + delta_x_pct, 1, 100 - start_x)
            wm.x = start_x
        elif handle == 'left':
            new_w = self.clamp_value(start_w - delta_x_pct, 1, start_right)
            wm.x = start_right - new_w
            wm.width_pct = new_w
        elif handle == 'bottom':
            wm.height_pct = self.clamp_value(start_h + delta_y_pct, 1, 100 - start_y)
            wm.y = start_y
        elif handle == 'top':
            new_h = self.clamp_value(start_h - delta_y_pct, 1, start_bottom)
            wm.y = start_bottom - new_h
            wm.height_pct = new_h

    def get_handle_at_pos(self, x, y):
        """检测点击位置是否在某个水印的控制点上"""
        selection = self.watermark_listbox.curselection()
        if not selection:
            return None, None

        wm_idx = selection[0]
        if wm_idx >= len(self.watermarks):
            return None, None

        wm = self.watermarks[wm_idx]
        if not wm.content:
            return None, None

        try:
            wm_img = Image.open(wm.content)
            left, top, wm_w, wm_h = self.get_watermark_rect(wm, wm_img)
            hs = self.handle_size

            for handle, (hx, hy) in self.get_resize_handles(left, top, wm_w, wm_h).items():
                if abs(x - hx) <= hs and abs(y - hy) <= hs:
                    return wm_idx, handle

            # 移动区域（中间部分）
            if left <= x <= left + wm_w and top <= y <= top + wm_h:
                return wm_idx, 'move'

            return None, None

        except Exception as e:
            print(f"检测控制点失败: {e}")
            return None, None

    def point_in_crop_box(self, x, y):
        if not self.crop_box:
            return False
        left, top, right, bottom = self.crop_box
        return left <= x <= right and top <= y <= bottom

    def on_canvas_click(self, event):
        if not self.source_images or self.current_image_index >= len(self.source_images):
            return

        wm_idx, handle = self.get_handle_at_pos(event.x, event.y)

        if wm_idx is not None:
            self.op_wm_idx = wm_idx
            self.op_start_x = event.x
            self.op_start_y = event.y

            if handle == 'move':
                self.operation = 'move'
                wm = self.watermarks[wm_idx]
                self.op_start_x_percent = wm.x
                self.op_start_y_percent = wm.y
            else:
                self.operation = f'resize_{handle}'
                wm = self.watermarks[wm_idx]
                self.op_start_size = wm.width_pct
                self.op_start_h = wm.height_pct
                self.op_start_x_percent = wm.x
                self.op_start_y_percent = wm.y

            self.canvas.config(cursor="hand1" if handle == 'move' else "sizing")
        elif self.is_crop_enabled() and self.point_in_crop_box(event.x, event.y):
            self.operation = 'crop_move'
            self.op_wm_idx = -1
            self.op_start_x = event.x
            self.op_start_y = event.y
            try:
                self.op_start_crop_x = self.crop_focus_x.get()
                self.op_start_crop_y = self.crop_focus_y.get()
            except tk.TclError:
                self.op_start_crop_x = 50
                self.op_start_crop_y = 50
            self.canvas.config(cursor="fleur")

    def on_canvas_drag(self, event):
        if self.operation == 'crop_move':
            if self.crop_box:
                left, top, right, bottom = self.crop_box
                excess_w = self.full_img_w - (right - left)
                excess_h = self.full_img_h - (bottom - top)
                if excess_w > 0:
                    delta_x = (event.x - self.op_start_x) / excess_w * 100
                    self.crop_focus_x.set(self.clamp_value(self.op_start_crop_x + delta_x, 0, 100))
                if excess_h > 0:
                    delta_y = (event.y - self.op_start_y) / excess_h * 100
                    self.crop_focus_y.set(self.clamp_value(self.op_start_crop_y + delta_y, 0, 100))
                self.save_current_crop_position()
            self.update_preview()
            return

        if self.op_wm_idx < 0 or self.op_wm_idx >= len(self.watermarks):
            return

        wm = self.watermarks[self.op_wm_idx]

        if self.operation == 'move':
            # 移动水印
            delta_x = (event.x - self.op_start_x) / self.img_w * 100
            delta_y = (event.y - self.op_start_y) / self.img_h * 100

            new_x = self.op_start_x_percent + delta_x
            new_y = self.op_start_y_percent + delta_y

            new_x = max(0, min(100 - wm.width_pct, new_x))
            new_y = max(0, min(100 - wm.height_pct, new_y))

            wm.x = new_x
            wm.y = new_y

        elif self.operation.startswith('resize_'):
            handle = self.operation.replace('resize_', '', 1)
            delta_x_pct = (event.x - self.op_start_x) / self.img_w * 100
            delta_y_pct = (event.y - self.op_start_y) / self.img_h * 100

            if handle in ('tl', 'tr', 'bl', 'br'):
                self.resize_corner_keep_ratio(wm, handle, delta_x_pct, delta_y_pct)
            else:
                self.resize_edge_stretch(wm, handle, delta_x_pct, delta_y_pct)

        self.update_preview()

    def on_canvas_release(self, event):
        if self.op_wm_idx >= 0:
            wm = self.watermarks[self.op_wm_idx]
            self.wm_x.set(round(wm.x, 1))
            self.wm_y.set(round(wm.y, 1))
            self.wm_width.set(round(wm.width_pct, 1))
            self.wm_height.set(round(wm.height_pct, 1))
            self.update_watermark_list(self.op_wm_idx)

        self.op_wm_idx = -1
        self.operation = 'none'
        self.canvas.config(cursor="")

    def update_preview(self):
        self.canvas.delete("all")
        self.wm_photos = []

        if not self.source_images or self.current_image_index >= len(self.source_images):
            self.preview_info.config(text="请选择源图片")
            return

        img_path = self.source_images[self.current_image_index]
        try:
            img = Image.open(img_path)
            img = self.normalize_image_orientation(img)
            if not self.is_crop_enabled():
                img = self.resize_image(img, img_path)
            original_w, original_h = img.size

            canvas_w = self.canvas.winfo_width()
            canvas_h = self.canvas.winfo_height()
            if canvas_w < 100:
                canvas_w = 650
            if canvas_h < 100:
                canvas_h = 500

            scale = min(canvas_w / original_w, canvas_h / original_h) * 0.95
            self.full_img_w = int(original_w * scale)
            self.full_img_h = int(original_h * scale)
            self.full_img_x = (canvas_w - self.full_img_w) // 2
            self.full_img_y = (canvas_h - self.full_img_h) // 2

            # 绘制原图
            display_img = img.copy()
            display_img = display_img.resize((self.full_img_w, self.full_img_h), Image.LANCZOS)
            self.preview_photo = ImageTk.PhotoImage(display_img)
            self.canvas.create_image(self.full_img_x, self.full_img_y, anchor=tk.NW, image=self.preview_photo)

            if self.is_crop_enabled():
                crop_source_box = self.get_crop_box_for_image(img, img_path)
                crop_left, crop_top, crop_right, crop_bottom = self.get_canvas_crop_box(crop_source_box, scale)
                self.crop_box = (crop_left, crop_top, crop_right, crop_bottom)
                self.img_x = crop_left
                self.img_y = crop_top
                self.img_w = crop_right - crop_left
                self.img_h = crop_bottom - crop_top

                full_left = self.full_img_x
                full_top = self.full_img_y
                full_right = self.full_img_x + self.full_img_w
                full_bottom = self.full_img_y + self.full_img_h
                overlay_options = {'fill': '#000000', 'stipple': 'gray50', 'outline': ''}
                self.canvas.create_rectangle(full_left, full_top, full_right, crop_top, **overlay_options)
                self.canvas.create_rectangle(full_left, crop_bottom, full_right, full_bottom, **overlay_options)
                self.canvas.create_rectangle(full_left, crop_top, crop_left, crop_bottom, **overlay_options)
                self.canvas.create_rectangle(crop_right, crop_top, full_right, crop_bottom, **overlay_options)
                self.canvas.create_rectangle(crop_left, crop_top, crop_right, crop_bottom, outline='#ffffff', width=2)
                self.canvas.create_rectangle(crop_left + 2, crop_top + 2, crop_right - 2, crop_bottom - 2, outline='#0078D7', width=1)
            else:
                self.crop_box = None
                self.img_x = self.full_img_x
                self.img_y = self.full_img_y
                self.img_w = self.full_img_w
                self.img_h = self.full_img_h
                self.canvas.create_rectangle(
                    self.img_x, self.img_y,
                    self.img_x + self.img_w, self.img_y + self.img_h,
                    outline='#888888', width=2
                )

            wm_selection = self.watermark_listbox.curselection()

            for idx, wm in enumerate(self.watermarks):
                if not wm.content or not os.path.exists(wm.content):
                    continue

                try:
                    wm_img = Image.open(wm.content).convert("RGBA")
                    left, top, wm_w, wm_h = self.get_watermark_rect(wm, wm_img)

                    # 缩放水印
                    wm_thumb = wm_img.copy()
                    wm_thumb = wm_thumb.resize((wm_w, wm_h), Image.LANCZOS)

                    if wm.opacity < 1.0:
                        if wm_thumb.mode == 'RGBA':
                            alpha = wm_thumb.split()[3]
                            alpha = alpha.point(lambda p: int(p * wm.opacity))
                            wm_thumb.putalpha(alpha)

                    wm_photo = ImageTk.PhotoImage(wm_thumb)
                    self.wm_photos.append(wm_photo)

                    self.canvas.create_image(left, top, anchor=tk.NW, image=wm_photo)

                    # 选中项绘制控制框
                    if wm_selection and wm_selection[0] == idx:
                        hs = self.handle_size
                        handles = self.get_resize_handles(left, top, wm_w, wm_h)
                        for handle, (hx, hy) in handles.items():
                            x1, y1 = hx - hs // 2, hy - hs // 2
                            x2, y2 = hx + hs // 2, hy + hs // 2
                            if handle in ('tl', 'tr', 'bl', 'br'):
                                self.canvas.create_oval(x1, y1, x2, y2, fill='#0078D7', outline='#0056a3')
                            else:
                                self.canvas.create_rectangle(x1, y1, x2, y2, fill='#ffffff', outline='#0078D7')

                        # 边框
                        self.canvas.create_rectangle(
                            left, top, left + wm_w, top + wm_h,
                            outline='#0078D7', width=2
                        )

                except Exception as e:
                    print(f"绘制水印失败: {e}")

            if self.is_crop_enabled() and self.crop_box:
                crop_left, crop_top, crop_right, crop_bottom = self.crop_box
                self.canvas.create_rectangle(crop_left, crop_top, crop_right, crop_bottom, outline='#ffffff', width=2)

            valid_count = sum(1 for wm in self.watermarks if wm.content and os.path.exists(wm.content))
            crop_text = ""
            if self.is_crop_enabled() and self.crop_box:
                crop_text = f" | 裁切位置: {int(self.crop_focus_x.get())}%, {int(self.crop_focus_y.get())}%"
            resize_text = ""
            if self.enable_resize.get():
                resize_text = f" | 尺寸: {img.width}x{img.height}"
            self.preview_info.config(text=f"{os.path.basename(img_path)}{crop_text}{resize_text} | 水印: {valid_count} 个")

        except Exception as e:
            self.preview_info.config(text=f"预览失败: {e}")

    def process_images(self):
        if not self.source_images:
            messagebox.showwarning("警告", "请先选择源图片！")
            return

        crop_enabled = self.enable_crop.get()
        if crop_enabled and self.get_crop_ratio() is None:
            messagebox.showwarning("警告", "请设置有效的裁切比例！")
            return
        resize_enabled = self.enable_resize.get()
        if resize_enabled and self.get_resize_size() is None:
            messagebox.showwarning("警告", "请设置有效的目标尺寸！")
            return

        valid_wms = [wm for wm in self.watermarks if wm.content and os.path.exists(wm.content)]
        if not valid_wms and not crop_enabled and not resize_enabled:
            messagebox.showwarning("警告", "请先添加有效的水印图片，或启用图片裁切/尺寸修改！")
            return

        output_dir = self.output_dir.get().strip()

        if output_dir:
            os.makedirs(output_dir, exist_ok=True)

        overwrite_risks = [
            img_path for img_path in self.source_images
            if os.path.abspath(self.get_output_path(img_path, output_dir)) == os.path.abspath(img_path)
            and not self.overwrite_original.get()
        ]
        if overwrite_risks:
            messagebox.showwarning(
                "警告",
                "当前导出文件名会覆盖源图片。\n请先选择一个不同的输出目录，或设置前缀/后缀。"
            )
            return

        total = len(self.source_images)
        self.progress['maximum'] = total

        success_count = 0
        error_count = 0

        for i, img_path in enumerate(self.source_images):
            try:
                self.status_label.config(text=f"处理中: {os.path.basename(img_path)}")
                self.progress['value'] = i + 1
                self.root.update_idletasks()

                with Image.open(img_path) as src_img:
                    img = self.normalize_image_orientation(src_img.copy())
                result = self.center_crop_to_ratio(img, img_path)
                result = self.resize_image(result, img_path)
                result = self.apply_watermarks(result)

                output_path = self.get_output_path(img_path, output_dir)
                os.makedirs(os.path.dirname(output_path), exist_ok=True)

                if img_path.lower().endswith(('.png', '.gif')):
                    result.save(output_path, 'PNG')
                else:
                    result.save(output_path, 'JPEG', quality=95)

                success_count += 1

            except Exception as e:
                error_count += 1
                print(f"处理失败 {img_path}: {e}")

        self.status_label.config(text=f"完成！成功: {success_count}, 失败: {error_count}")
        messagebox.showinfo("完成", f"处理完成！\n成功: {success_count} 张\n失败: {error_count} 张")

    def apply_watermarks(self, img):
        result = img.convert("RGBA")

        for wm in self.watermarks:
            if not wm.content or not os.path.exists(wm.content):
                continue
            result = self.add_image_watermark(result, wm.content, wm.width_pct, wm.height_pct, wm.x, wm.y, wm.opacity)

        return result.convert("RGB")

    def add_image_watermark(self, img, wm_path, width_pct, height_pct, x_percent, y_percent, opacity):
        try:
            wm_img = Image.open(wm_path).convert("RGBA")
        except:
            return img

        wm_width = int(img.width * width_pct / 100)
        wm_height = int(img.height * height_pct / 100)
        wm_img = wm_img.resize((wm_width, wm_height), Image.LANCZOS)

        if opacity < 1.0:
            if wm_img.mode == 'RGBA':
                alpha = wm_img.split()[3]
                alpha = alpha.point(lambda p: int(p * opacity))
                wm_img.putalpha(alpha)

        x = int(img.width * x_percent / 100)
        y = int(img.height * y_percent / 100)
        x = max(0, min(x, img.width - wm_width))
        y = max(0, min(y, img.height - wm_height))

        wm_layer = Image.new("RGBA", img.size, (255, 255, 255, 0))
        wm_layer.paste(wm_img, (x, y))

        return Image.alpha_composite(img, wm_layer)

    def start_processing(self):
        thread = threading.Thread(target=self.process_images, daemon=True)
        thread.start()


if __name__ == "__main__":
    root = tk.Tk()
    app = WatermarkApp(root)
    root.mainloop()
