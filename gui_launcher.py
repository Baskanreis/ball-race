# -*- coding: utf-8 -*-
"""
Satisfying Ball Race - Grafik Arayuz Baslatici
------------------------------------------------
win.py icindeki simulasyon motorunu (Config, BallRaceSimulation, COURSES,
PALETTES) oldugu gibi kullanir; komut satiri yerine basit bir Tkinter
penceresinden secim yapip video uretmeyi saglar.

Bu dosya PyInstaller ile derlenip tek bir .exe haline getirilir
(bkz. .github/workflows/build.yml).
"""

import os
import sys
import threading
import traceback
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

# win.py'nin yaninda / exe icinde bulunmasini garanti altina al
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import win as core  # noqa: E402  (Config, BallRaceSimulation, COURSES, PALETTES, ...)


GAME_MODES = [
    ("elimination_enabled", "Elimination (Sudden-Death)"),
    ("redlight_enabled", "Red Light / Green Light"),
    ("boss_enabled", "Boss Race"),
    ("reverse_win", "Ters Kazanma (son biten kazanir)"),
    ("carousel_enabled", "Carousel (daralan alan)"),
    ("gravityflip_enabled", "Gravity Flip"),
    ("minefield_enabled", "Minefield"),
    ("magnet_enabled", "Magnet Pulse"),
    ("colorgate_enabled", "Color Gate"),
    ("goldenball_enabled", "Golden Ball"),
    ("laser_enabled", "Laser Sweep"),
    ("jumppad_enabled", "Jump Pads"),
]

VISUAL_TOGGLES = [
    ("show_countdown", "Geri sayim goster"),
    ("show_leaderboard", "Siralama tablosu goster"),
    ("confetti_enabled", "Konfeti"),
    ("glow", "Parlama (glow)"),
    ("slowmo_finish_enabled", "Slow-Mo Finish"),
]

RESOLUTIONS = {
    "1080x1920 (YouTube Shorts / TikTok)": (1080, 1920),
    "720x1280 (Dusuk cozunurluk)": (720, 1280),
    "1080x1080 (Kare)": (1080, 1080),
}


class BallRaceGUI(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Satisfying Ball Race - Video Olusturucu")
        self.geometry("760x680")
        self.minsize(700, 600)
        self._worker = None
        self._build_ui()

    # ------------------------------------------------------------------ #
    def _build_ui(self):
        nb = ttk.Notebook(self)
        nb.pack(fill="both", expand=True, padx=10, pady=10)

        temel = ttk.Frame(nb)
        modlar = ttk.Frame(nb)
        gorsel = ttk.Frame(nb)
        nb.add(temel, text="Temel Ayarlar")
        nb.add(modlar, text="Oyun Modlari")
        nb.add(gorsel, text="Gorsel / Cikti")

        self._build_temel(temel)
        self._build_modlar(modlar)
        self._build_gorsel(gorsel)

        alt = ttk.Frame(self)
        alt.pack(fill="x", padx=10, pady=(0, 10))

        self.run_btn = ttk.Button(alt, text="Video Olustur", command=self._on_run)
        self.run_btn.pack(side="left")

        self.open_btn = ttk.Button(alt, text="Cikti Klasorunu Ac", command=self._open_output_dir, state="disabled")
        self.open_btn.pack(side="left", padx=(8, 0))

        self.progress = ttk.Progressbar(alt, mode="indeterminate")
        self.progress.pack(side="left", fill="x", expand=True, padx=10)

        log_frame = ttk.LabelFrame(self, text="Gunluk")
        log_frame.pack(fill="both", expand=False, padx=10, pady=(0, 10))
        self.log = tk.Text(log_frame, height=10, state="disabled", wrap="word")
        self.log.pack(fill="both", expand=True)

    # ------------------------------------------------------------------ #
    def _build_temel(self, parent):
        pad = {"padx": 8, "pady": 6}

        row = 0
        ttk.Label(parent, text="Top sayisi:").grid(row=row, column=0, sticky="w", **pad)
        self.num_balls = tk.IntVar(value=core.Config.num_balls)
        ttk.Spinbox(parent, from_=2, to=30, textvariable=self.num_balls, width=8).grid(row=row, column=1, sticky="w", **pad)

        row += 1
        ttk.Label(parent, text="Parkur tipi:").grid(row=row, column=0, sticky="w", **pad)
        self.course = tk.StringVar(value=core.Config.course_type)
        ttk.Combobox(parent, textvariable=self.course, values=list(core.COURSES.keys()),
                     state="readonly", width=20).grid(row=row, column=1, sticky="w", **pad)

        row += 1
        ttk.Label(parent, text="Renk paleti:").grid(row=row, column=0, sticky="w", **pad)
        self.palette = tk.StringVar(value=core.Config.palette)
        ttk.Combobox(parent, textvariable=self.palette,
                     values=list(core.PALETTES.keys()) + ["rainbow"],
                     state="readonly", width=20).grid(row=row, column=1, sticky="w", **pad)

        row += 1
        ttk.Label(parent, text="Baslik metni:").grid(row=row, column=0, sticky="w", **pad)
        self.title_text = tk.StringVar(value=core.Config.title_text)
        ttk.Entry(parent, textvariable=self.title_text, width=34).grid(row=row, column=1, columnspan=2, sticky="w", **pad)

        row += 1
        ttk.Label(parent, text="Alt yazi (opsiyonel):").grid(row=row, column=0, sticky="w", **pad)
        self.subtitle_text = tk.StringVar(value="")
        ttk.Entry(parent, textvariable=self.subtitle_text, width=34).grid(row=row, column=1, columnspan=2, sticky="w", **pad)

        row += 1
        ttk.Label(parent, text="Suresi (sn, guvenlik limiti):").grid(row=row, column=0, sticky="w", **pad)
        self.duration = tk.DoubleVar(value=core.Config.duration_cap)
        ttk.Spinbox(parent, from_=5, to=120, textvariable=self.duration, width=8).grid(row=row, column=1, sticky="w", **pad)

        row += 1
        ttk.Label(parent, text="Seed (bos = rastgele):").grid(row=row, column=0, sticky="w", **pad)
        self.seed = tk.StringVar(value="")
        ttk.Entry(parent, textvariable=self.seed, width=12).grid(row=row, column=1, sticky="w", **pad)

        row += 1
        ttk.Label(parent, text="FPS:").grid(row=row, column=0, sticky="w", **pad)
        self.fps = tk.IntVar(value=core.Config.fps)
        ttk.Spinbox(parent, from_=24, to=60, textvariable=self.fps, width=8).grid(row=row, column=1, sticky="w", **pad)

    # ------------------------------------------------------------------ #
    def _build_modlar(self, parent):
        ttk.Label(parent, text="Birbiriyle kombinlenebilir oyun modlarini sec:",
                  font=("", 10, "bold")).grid(row=0, column=0, columnspan=2, sticky="w", padx=8, pady=(10, 4))

        self.mode_vars = {}
        for i, (field, label) in enumerate(GAME_MODES):
            var = tk.BooleanVar(value=getattr(core.Config, field))
            ttk.Checkbutton(parent, text=label, variable=var).grid(
                row=1 + i // 2, column=i % 2, sticky="w", padx=8, pady=3)
            self.mode_vars[field] = var

    # ------------------------------------------------------------------ #
    def _build_gorsel(self, parent):
        pad = {"padx": 8, "pady": 6}
        row = 0
        ttk.Label(parent, text="Cozunurluk:").grid(row=row, column=0, sticky="w", **pad)
        self.resolution = tk.StringVar(value=list(RESOLUTIONS.keys())[0])
        ttk.Combobox(parent, textvariable=self.resolution, values=list(RESOLUTIONS.keys()),
                     state="readonly", width=34).grid(row=row, column=1, sticky="w", **pad)

        row += 1
        ttk.Label(parent, text="Cikti dosyasi:").grid(row=row, column=0, sticky="w", **pad)
        out_frame = ttk.Frame(parent)
        out_frame.grid(row=row, column=1, sticky="w", **pad)
        self.output = tk.StringVar(value=os.path.abspath("viral_ball_race.mp4"))
        ttk.Entry(out_frame, textvariable=self.output, width=38).pack(side="left")
        ttk.Button(out_frame, text="...", width=3, command=self._pick_output).pack(side="left", padx=(4, 0))

        row += 1
        self.visual_vars = {}
        for i, (field, label) in enumerate(VISUAL_TOGGLES):
            var = tk.BooleanVar(value=getattr(core.Config, field))
            ttk.Checkbutton(parent, text=label, variable=var).grid(
                row=row + 1 + i, column=0, columnspan=2, sticky="w", padx=8, pady=2)
            self.visual_vars[field] = var

    # ------------------------------------------------------------------ #
    def _pick_output(self):
        path = filedialog.asksaveasfilename(defaultextension=".mp4",
                                             filetypes=[("MP4 video", "*.mp4")],
                                             initialfile=os.path.basename(self.output.get()))
        if path:
            self.output.set(path)

    def _open_output_dir(self):
        folder = os.path.dirname(os.path.abspath(self.output.get())) or "."
        try:
            if sys.platform.startswith("win"):
                os.startfile(folder)
            else:
                webbrowser.open(folder)
        except Exception as exc:
            messagebox.showerror("Hata", str(exc))

    # ------------------------------------------------------------------ #
    def _log(self, msg):
        self.log.configure(state="normal")
        self.log.insert("end", msg + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _build_config(self) -> "core.Config":
        cfg = core.Config()
        cfg.num_balls = self.num_balls.get()
        cfg.course_type = self.course.get()
        cfg.palette = self.palette.get()
        cfg.title_text = self.title_text.get()
        cfg.subtitle_text = self.subtitle_text.get()
        cfg.duration_cap = self.duration.get()
        cfg.fps = self.fps.get()
        cfg.output = self.output.get() or "viral_ball_race.mp4"
        w, h = RESOLUTIONS[self.resolution.get()]
        cfg.width, cfg.height = w, h

        seed_raw = self.seed.get().strip()
        cfg.seed = int(seed_raw) if seed_raw else None

        for field, var in self.mode_vars.items():
            setattr(cfg, field, var.get())
        for field, var in self.visual_vars.items():
            setattr(cfg, field, var.get())
        return cfg

    # ------------------------------------------------------------------ #
    def _on_run(self):
        if self._worker and self._worker.is_alive():
            return
        try:
            cfg = self._build_config()
        except Exception as exc:
            messagebox.showerror("Gecersiz ayar", str(exc))
            return

        self.run_btn.configure(state="disabled")
        self.open_btn.configure(state="disabled")
        self.progress.start(12)
        self._log(f"Uretim basladi -> {cfg.output}")

        self._worker = threading.Thread(target=self._run_simulation, args=(cfg,), daemon=True)
        self._worker.start()

    def _run_simulation(self, cfg):
        try:
            sim = core.BallRaceSimulation(cfg)
            sim.run()
            winner = sim._get_winner()
            winner_name = winner["name"] if winner else "?"
            self.after(0, self._on_done, True, f"Video hazir: {cfg.output}\nKazanan: {winner_name}")
        except Exception:
            err = traceback.format_exc()
            self.after(0, self._on_done, False, err)

    def _on_done(self, ok, msg):
        self.progress.stop()
        self.run_btn.configure(state="normal")
        if ok:
            self.open_btn.configure(state="normal")
            self._log(msg)
            messagebox.showinfo("Tamamlandi", msg)
        else:
            self._log("HATA:\n" + msg)
            messagebox.showerror("Hata", "Video uretilirken bir hata olustu. Gunluge bakin.")


def main():
    app = BallRaceGUI()
    app.mainloop()


if __name__ == "__main__":
    main()
