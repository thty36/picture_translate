from __future__ import annotations

import os
import queue
import threading
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk

from .models import BatchOptions
from .pipeline import translate_directory


OCR_LANGUAGES = {
    "中文/英文 (ch)": "ch",
    "日文漫画 (japan)": "japan",
    "韩文漫画 (korean)": "korean",
    "英文 (en)": "en",
}

TARGET_LANGUAGES = {
    "简体中文 (zh-CN)": "zh-CN",
    "英文 (en)": "en",
    "日文 (ja)": "ja",
    "韩文 (ko)": "ko",
}

TRANSLATORS = {
    "自动选择": "auto",
    "百度翻译": "baidu",
    "Google 免费接口": "google_web",
    "Deep Translator": "deep_translator",
    "不翻译": "none",
}

ERASE_MODES = {
    "智能修补": "inpaint",
    "填白": "white",
    "取背景色": "sample",
}


class MangaTranslatorApp(tk.Tk):
    def __init__(self) -> None:
        super().__init__()
        self.title("漫画图片批量翻译")
        self.geometry("900x640")
        self.minsize(780, 560)

        self.events: queue.Queue[dict] = queue.Queue()
        self.worker: threading.Thread | None = None
        self.stop_event = threading.Event()

        self.input_dir = tk.StringVar()
        self.output_dir = tk.StringVar()
        self.ocr_lang = tk.StringVar(value="日文漫画 (japan)")
        self.target_lang = tk.StringVar(value="简体中文 (zh-CN)")
        self.translator = tk.StringVar(value="自动选择")
        self.erase_mode = tk.StringVar(value="智能修补")
        self.font_path = tk.StringVar()
        self.recursive = tk.BooleanVar(value=False)
        self.overwrite = tk.BooleanVar(value=True)
        self.min_confidence = tk.DoubleVar(value=0.35)
        self.status_text = tk.StringVar(value="请选择图片目录。")
        self.progress_text = tk.StringVar(value="0 / 0")

        self._build_ui()
        self.after(120, self._poll_events)

    def _build_ui(self) -> None:
        self.columnconfigure(0, weight=1)
        self.rowconfigure(1, weight=1)

        top = ttk.Frame(self, padding=16)
        top.grid(row=0, column=0, sticky="ew")
        top.columnconfigure(1, weight=1)

        ttk.Label(top, text="图片目录").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(top, textvariable=self.input_dir).grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Button(top, text="选择", command=self._choose_input).grid(row=0, column=2, padx=(8, 0), pady=4)

        ttk.Label(top, text="输出目录").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(top, textvariable=self.output_dir).grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Button(top, text="选择", command=self._choose_output).grid(row=1, column=2, padx=(8, 0), pady=4)

        settings = ttk.LabelFrame(self, text="设置", padding=16)
        settings.grid(row=1, column=0, sticky="nsew", padx=16, pady=(0, 12))
        settings.columnconfigure(1, weight=1)
        settings.columnconfigure(3, weight=1)
        settings.rowconfigure(4, weight=1)

        ttk.Label(settings, text="OCR 语言").grid(row=0, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Combobox(
            settings,
            textvariable=self.ocr_lang,
            values=list(OCR_LANGUAGES.keys()),
            state="readonly",
        ).grid(row=0, column=1, sticky="ew", pady=4)

        ttk.Label(settings, text="目标语言").grid(row=0, column=2, sticky="w", padx=(24, 8), pady=4)
        ttk.Combobox(
            settings,
            textvariable=self.target_lang,
            values=list(TARGET_LANGUAGES.keys()),
            state="readonly",
        ).grid(row=0, column=3, sticky="ew", pady=4)

        ttk.Label(settings, text="翻译方式").grid(row=1, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Combobox(
            settings,
            textvariable=self.translator,
            values=list(TRANSLATORS.keys()),
            state="readonly",
        ).grid(row=1, column=1, sticky="ew", pady=4)

        ttk.Label(settings, text="擦字方式").grid(row=1, column=2, sticky="w", padx=(24, 8), pady=4)
        ttk.Combobox(
            settings,
            textvariable=self.erase_mode,
            values=list(ERASE_MODES.keys()),
            state="readonly",
        ).grid(row=1, column=3, sticky="ew", pady=4)

        ttk.Label(settings, text="字体文件").grid(row=2, column=0, sticky="w", padx=(0, 8), pady=4)
        ttk.Entry(settings, textvariable=self.font_path).grid(row=2, column=1, columnspan=2, sticky="ew", pady=4)
        ttk.Button(settings, text="选择字体", command=self._choose_font).grid(row=2, column=3, sticky="e", pady=4)

        options = ttk.Frame(settings)
        options.grid(row=3, column=0, columnspan=4, sticky="ew", pady=(8, 8))
        ttk.Checkbutton(options, text="包含子目录", variable=self.recursive).pack(side="left")
        ttk.Checkbutton(options, text="覆盖已存在输出", variable=self.overwrite).pack(side="left", padx=(24, 0))
        ttk.Label(options, text="最低置信度").pack(side="left", padx=(24, 8))
        ttk.Spinbox(
            options,
            from_=0.0,
            to=1.0,
            increment=0.05,
            textvariable=self.min_confidence,
            width=6,
        ).pack(side="left")

        log_frame = ttk.LabelFrame(settings, text="处理日志", padding=8)
        log_frame.grid(row=4, column=0, columnspan=4, sticky="nsew", pady=(4, 0))
        log_frame.rowconfigure(0, weight=1)
        log_frame.columnconfigure(0, weight=1)

        self.log = tk.Text(log_frame, height=12, wrap="word", state="disabled")
        self.log.grid(row=0, column=0, sticky="nsew")
        scroll = ttk.Scrollbar(log_frame, command=self.log.yview)
        scroll.grid(row=0, column=1, sticky="ns")
        self.log.configure(yscrollcommand=scroll.set)

        bottom = ttk.Frame(self, padding=(16, 0, 16, 16))
        bottom.grid(row=2, column=0, sticky="ew")
        bottom.columnconfigure(1, weight=1)

        self.start_button = ttk.Button(bottom, text="开始翻译", command=self._start)
        self.start_button.grid(row=0, column=0, padx=(0, 8))
        self.stop_button = ttk.Button(bottom, text="停止", command=self._stop, state="disabled")
        self.stop_button.grid(row=0, column=1, sticky="w")
        ttk.Button(bottom, text="打开输出目录", command=self._open_output).grid(row=0, column=2, padx=(8, 0))

        self.progress = ttk.Progressbar(bottom, mode="determinate")
        self.progress.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(12, 4))

        ttk.Label(bottom, textvariable=self.status_text).grid(row=2, column=0, columnspan=2, sticky="w")
        ttk.Label(bottom, textvariable=self.progress_text).grid(row=2, column=2, sticky="e")

    def _choose_input(self) -> None:
        directory = filedialog.askdirectory(title="选择图片目录")
        if not directory:
            return
        self.input_dir.set(directory)
        if not self.output_dir.get().strip():
            self.output_dir.set(str(Path(directory) / "translated"))
        self.status_text.set("目录已选择，可以开始翻译。")

    def _choose_output(self) -> None:
        directory = filedialog.askdirectory(title="选择输出目录")
        if directory:
            self.output_dir.set(directory)

    def _choose_font(self) -> None:
        file = filedialog.askopenfilename(
            title="选择字体文件",
            filetypes=[("Font files", "*.ttf *.ttc *.otf"), ("All files", "*.*")],
        )
        if file:
            self.font_path.set(file)

    def _start(self) -> None:
        if self.worker and self.worker.is_alive():
            return

        try:
            options = self._read_options()
        except ValueError as exc:
            messagebox.showerror("无法开始", str(exc))
            return

        self._clear_log()
        self._append_log("开始处理。")
        self.progress.configure(value=0, maximum=1)
        self.progress_text.set("0 / 0")
        self.status_text.set("正在启动...")
        self.stop_event.clear()
        self._set_running(True)

        self.worker = threading.Thread(target=self._run_worker, args=(options,), daemon=True)
        self.worker.start()

    def _read_options(self) -> BatchOptions:
        input_raw = self.input_dir.get().strip()
        output_raw = self.output_dir.get().strip()
        if not input_raw:
            raise ValueError("请选择图片目录。")
        if not output_raw:
            raise ValueError("请选择输出目录。")

        input_dir = Path(input_raw)
        output_dir = Path(output_raw)
        if not input_dir.exists() or not input_dir.is_dir():
            raise ValueError(f"图片目录不存在：{input_dir}")

        font = self.font_path.get().strip()
        font_path = Path(font) if font else None
        if font_path is not None and not font_path.exists():
            raise ValueError(f"字体文件不存在：{font_path}")

        return BatchOptions(
            input_dir=input_dir,
            output_dir=output_dir,
            ocr_lang=OCR_LANGUAGES[self.ocr_lang.get()],
            source_lang="auto",
            target_lang=TARGET_LANGUAGES[self.target_lang.get()],
            translator=TRANSLATORS[self.translator.get()],
            recursive=self.recursive.get(),
            overwrite=self.overwrite.get(),
            min_confidence=float(self.min_confidence.get()),
            erase_mode=ERASE_MODES[self.erase_mode.get()],
            font_path=font_path,
        )

    def _run_worker(self, options: BatchOptions) -> None:
        try:
            stats = translate_directory(options, progress=self.events.put, stop_event=self.stop_event)
            self.events.put({"type": "worker_done", "stats": stats.as_dict()})
        except Exception as exc:
            self.events.put({"type": "fatal", "message": str(exc)})

    def _stop(self) -> None:
        self.stop_event.set()
        self.status_text.set("正在请求停止，当前图片处理完后会退出。")
        self._append_log("已请求停止。")

    def _open_output(self) -> None:
        directory = self.output_dir.get().strip()
        if not directory:
            messagebox.showinfo("输出目录", "还没有选择输出目录。")
            return
        path = Path(directory)
        path.mkdir(parents=True, exist_ok=True)
        os.startfile(path)

    def _poll_events(self) -> None:
        try:
            while True:
                event = self.events.get_nowait()
                self._handle_event(event)
        except queue.Empty:
            pass
        self.after(120, self._poll_events)

    def _handle_event(self, event: dict) -> None:
        event_type = event.get("type")
        message = event.get("message")

        if event_type == "scan":
            total = int(event.get("total", 0))
            self.progress.configure(maximum=max(total, 1), value=0)
            self.progress_text.set(f"0 / {total}")
        elif event_type in {"file_start", "message"}:
            if message:
                self.status_text.set(message)
                self._append_log(message)
        elif event_type == "file_done":
            self._update_progress(event)
            if message:
                self._append_log(message)
        elif event_type == "file_skip":
            self._update_progress(event)
            self._append_log(f"跳过：{Path(event.get('file', '')).name}")
        elif event_type == "file_error":
            self._update_progress(event)
            if message:
                self._append_log(message)
        elif event_type == "cancelled":
            self.status_text.set("已停止。")
            if message:
                self._append_log(message)
        elif event_type == "done":
            if message:
                self._append_log(message)
        elif event_type == "worker_done":
            stats = event.get("stats", {})
            self.status_text.set(
                f"完成 {stats.get('completed', 0)}，失败 {stats.get('failed', 0)}，跳过 {stats.get('skipped', 0)}。"
            )
            self._set_running(False)
        elif event_type == "fatal":
            self.status_text.set("处理失败。")
            self._append_log(str(message))
            messagebox.showerror("处理失败", str(message))
            self._set_running(False)

    def _update_progress(self, event: dict) -> None:
        index = int(event.get("index", 0))
        total = int(event.get("total", 0))
        self.progress.configure(maximum=max(total, 1), value=index)
        self.progress_text.set(f"{index} / {total}")

    def _append_log(self, text: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _clear_log(self) -> None:
        self.log.configure(state="normal")
        self.log.delete("1.0", "end")
        self.log.configure(state="disabled")

    def _set_running(self, running: bool) -> None:
        self.start_button.configure(state="disabled" if running else "normal")
        self.stop_button.configure(state="normal" if running else "disabled")


def main() -> None:
    app = MangaTranslatorApp()
    app.mainloop()
