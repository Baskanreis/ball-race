"""
Satisfying Ball Race - YouTube Shorts Video Generator
-------------------------------------------------------
Cok sayida topun fizik parkurunda yarisini simule edip dikey (Shorts
formatinda) MP4 video olarak kaydeder. Kazanan/siralama otomatik
tespit edilir, konfeti ve leaderboard ile kapanis yapilir.

Hizli baslangic:
    python win.py
    python win.py --num-balls 6 --course plinko --palette neon --seed 7
    python win.py --num-balls 6 --course chevron --palette fire_ice --seed 3
    python win.py --elimination --duration 25 --output shorts_01.mp4
    python win.py --carousel --carousel-shape circle --num-balls 10
    python win.py --carousel --carousel-shape square --carousel-start 6 --carousel-duration 14
    python win.py --gravity-flip --num-balls 8
    python win.py --minefield --magnet --num-balls 10
    python win.py --color-gate --golden-ball
    python win.py --laser --laser-axis horizontal --num-balls 8
    python win.py --jump-pads --jump-pads-count 5 --num-balls 8
    python win.py --no-slowmo   # Slow-Mo Finish efekti varsayilan acik, boylece kapatabilirsin
    python win.py --config my_settings.json
    python win.py --save-config my_settings.json   # mevcut ayarlari kaydet
    python win.py --batch 5 --num-balls 4           # 5 farkli video uret
    python win.py --batch 8 --parallel --max-workers 4   # 8 videoyu 4 process ile paralel uret

Ileri duzey ayar icin herhangi bir Config alanini komut satirindan
degistirebilirsin:
    python win.py --set trail_length=25 --set glow=false --set bg_color_top=#000000

Gereksinimler: pip install pygame pymunk opencv-python numpy
Muzik eklemek icin (opsiyonel): pip install moviepy
"""

import argparse
import ast
import colorsys
import concurrent.futures
import copy
import dataclasses
import json
import math
import os
import random
import sys
from dataclasses import dataclass, asdict
from typing import List, Optional, Tuple

import cv2
import numpy as np
import pygame
import pygame.gfxdraw
import pymunk


# ===================================================================== #
# CONFIG
# ===================================================================== #

@dataclass
class Config:
    # Video
    width: int = 1080
    height: int = 1920
    fps: int = 60
    duration_cap: float = 30.0          # kimse bitiremezse guvenlik limiti
    celebration_seconds: float = 4.0    # kazanan sonrasi kapanis suresi
    output: str = "viral_ball_race.mp4"
    seed: Optional[int] = None

    # Toplar
    num_balls: int = 2
    palette: str = "neon"               # neon|pastel|fire_ice|mono_red_blue|rainbow|custom
    custom_colors: Optional[List[str]] = None
    ball_radius_ratio: float = 0.0306   # genislige oranli yaricap
    gravity_y: float = 1600.0
    elasticity_min: float = 0.88
    elasticity_max: float = 0.98
    friction: float = 0.1
    substeps: int = 10

    # Parkur
    course_type: str = "plinko"         # funnel|plinko|cascade|vortex|chevron
    wall_color: str = "#DCDCDC"
    finish_y_ratio: float = 0.90

    # Gorsel stil
    background_style: str = "gradient"  # solid|gradient|starfield
    bg_color_top: str = "#0A0A14"
    bg_color_bottom: str = "#1A1030"
    trail_length: int = 15
    glow: bool = True

    # Metinler
    title_text: str = "WHICH BALL WINS?"
    subtitle_text: str = ""
    watermark_text: str = ""

    # Ozellikler
    show_countdown: bool = True
    show_leaderboard: bool = True
    confetti_enabled: bool = True

    # Eleme modu (sudden-death)
    elimination_enabled: bool = False
    elimination_interval_seconds: float = 4.0
    eliminate_per_round: int = 1
    min_survivors: int = 1

    # Muzik (opsiyonel, moviepy gerekir)
    music_path: Optional[str] = None
    music_dir: Optional[str] = None     # muzik dosyalarinin bulundugu klasor (--music-name / --music-random icin)
    music_name: Optional[str] = None    # music_dir icinde bu isme (kismi, harf duyarsiz) uyan parcayi sec

    # Red Light Green Light modu: yesilde serbest dusus, kirmizida donma - hareket halinde yakalanan elenir
    redlight_enabled: bool = False
    redlight_green_min: float = 1.5
    redlight_green_max: float = 3.0
    redlight_red_min: float = 1.0
    redlight_red_max: float = 2.2
    redlight_speed_threshold: float = 110.0
    redlight_eliminate_per_round: int = 1   # her kirmizida en hizli hareket eden kac top elenir

    # Boss Race modu: belli bir sureden sonra ekranda gezinen dev bir engel belirir, degen top elenir
    boss_enabled: bool = False
    boss_spawn_time: float = 7.0
    boss_radius_ratio: float = 0.085
    boss_speed: float = 260.0
    boss_color: str = "#FF2244"

    # Ters kazanma modu: ilk degil, EN SON bitiren top kazanir
    reverse_win: bool = False

    # Carousel modu: zamanla daralan guvenli alan (daire/kare) - disinda kalan top aninda elenir
    carousel_enabled: bool = False
    carousel_shape: str = "circle"            # circle|square
    carousel_start_time: float = 5.0          # kac saniye sonra daralma baslar
    carousel_shrink_duration: float = 16.0    # tam boyuttan min boyuta inis suresi (sn)
    carousel_min_size_ratio: float = 0.16     # min guvenli alan boyutu (genislige oranli)
    carousel_min_survivors: int = 1
    carousel_color: str = "#FF2244"
    carousel_pulse: bool = True

    # Gravity Flip modu: rastgele araliklarla yercekimi aniden ters doner, siralama altust olur
    gravityflip_enabled: bool = False
    gravityflip_interval_min: float = 3.0
    gravityflip_interval_max: float = 6.0
    gravityflip_warning_seconds: float = 0.5   # flipten once ekranda uyari suresi

    # Minefield modu: parkurda rastgele gizli minler belirir, deyen top infilak eder
    minefield_enabled: bool = False
    minefield_interval_min: float = 1.4
    minefield_interval_max: float = 2.6
    minefield_max_active: int = 3
    minefield_warning_seconds: float = 0.8     # armed olmadan once yanip sonme suresi
    minefield_radius_ratio: float = 0.034
    minefield_color: str = "#FFAA00"

    # Magnet Pulse modu: periyodik olarak ekranda bir nokta toplari ceker/iter, kaos yaratir
    magnet_enabled: bool = False
    magnet_interval_min: float = 3.0
    magnet_interval_max: float = 5.0
    magnet_duration: float = 1.2
    magnet_strength: float = 1800000.0
    magnet_mode: str = "random"                # attract|repel|random

    # Color Gate modu: periyodik "kapi" cizgileri belirir, sadece istenen renk gecebilir
    colorgate_enabled: bool = False
    colorgate_interval_min: float = 3.0
    colorgate_interval_max: float = 5.0
    colorgate_min_active_balls: int = 2

    # Golden Ball modu: rastgele bir top "altin" secilir, kazanirsa extra konfeti/kutlama
    goldenball_enabled: bool = False

    # Laser Sweep modu: periyodik olarak ekrani bastan basa tarayan bir lazer cizgisi
    # belirir, kisa bir uyari sonrasi aktif olur ve degen top elenir
    laser_enabled: bool = False
    laser_axis: str = "random"                 # horizontal|vertical|random
    laser_interval_min: float = 3.0
    laser_interval_max: float = 5.5
    laser_sweep_duration: float = 1.3          # ekrani bastan basa gecme suresi (sn)
    laser_warning_seconds: float = 0.6         # aktif olmadan once uyari suresi
    laser_thickness_ratio: float = 0.012       # cizgi kalinligi, genislige oranli
    laser_color: str = "#FF0044"

    # Jump Pads modu: parkurda sabit konumlu "trambolin" pedler belirir, deyen topa
    # guclu bir itki uygulanir (eleme yok, sadece kaos/hareket katar)
    jumppad_enabled: bool = False
    jumppad_count: int = 4
    jumppad_boost: float = 1250.0              # pedin topa verdigi yukari-doğru itki (hiz birimi)
    jumppad_radius_ratio: float = 0.042        # ped yaricapi, genislige oranli
    jumppad_cooldown: float = 0.35             # ayni topun ayni pedi tekrar tetikleyebilmesi icin bekleme (sn)
    jumppad_color: str = "#39FF88"

    # Slow-Mo Finish: lider bitis cizgisine yaklasinca otomatik yavas cekim + yakinlastirma
    slowmo_finish_enabled: bool = True
    slowmo_trigger_ratio: float = 0.93         # finish_y'ye oranla tetiklenme noktasi
    slowmo_duration: float = 1.4               # slow-mo'nun video suresince surecegi saniye
    slowmo_factor: float = 0.35                # fizik hizi carpani (kucuk = daha yavas)
    slowmo_zoom: float = 1.22                  # kamera yakinlastirma orani

    # Yuzler / avatarlar (opsiyonel) - her topun ortasina yerlesen daire kirpmali resimler
    face_images: Optional[List[str]] = None   # dosya yollari, sirayla toplara atanir, yetersizse tekrar eder
    face_names: Optional[List[str]] = None    # yuzlerle birlikte gosterilecek isimler (opsiyonel, uzunluk face_images ile ayni olmali)
    face_scale: float = 1.0                   # yuzun top yaricapina orani (1.0 = tam top capi)

    @classmethod
    def from_dict(cls, d):
        base = cls()
        valid = {f.name for f in dataclasses.fields(cls)}
        for k, v in d.items():
            if k in valid:
                setattr(base, k, v)
            else:
                print(f"Uyari: bilinmeyen config alani '{k}' atlandi.")
        return base

    def to_dict(self):
        return asdict(self)


# ===================================================================== #
# RENK PALETLERI
# ===================================================================== #

AUTO_TITLES = [
    "WHICH BALL WINS?",
    "ONLY 1 CAN WIN \U0001F3C6",
    "WHO MAKES IT TO THE END?",
    "PICK YOUR BALL NOW!",
    "CAN YOU GUESS THE WINNER?",
    "LAST ONE STANDING WINS",
    "THIS IS SO SATISFYING \U0001F60D",
    "COMMENT YOUR BALL BELOW \U0001F447",
]

PALETTES = {
    "neon": ["#FF3366", "#33CCFF", "#FFD93D", "#6BFF6B", "#C77DFF", "#FF8C42"],
    "pastel": ["#FFADAD", "#FFD6A5", "#FDFFB6", "#CAFFBF", "#9BF6FF", "#A0C4FF", "#BDB2FF", "#FFC6FF"],
    "fire_ice": ["#FF4500", "#1E90FF"],
    "mono_red_blue": ["#FF3250", "#00C8FF"],
}


class NoRepeatPool:
    """--batch ile cok sayida video uretilirken --auto-title / --music-random
    eskiden her video icin bagimsiz bir rastgele secim yapiyordu; bu da 8 basliktan
    olusan bir havuzda ayni basligin arka arkaya (hatta ayni batch icinde 3-4 kez)
    cikmasina yol aciyordu. Bu havuz, listeyi karistirip sirayla tuketir; havuz
    tukenince yeniden karistirir, ve bir sonraki turun ilk ogesinin bir onceki turun
    son ogesiyle ayni olmamasina (mumkunse) dikkat eder - boylece 'tekrar' hissi
    sadece istatistiksel olarak degil, gozle de en aza iner."""

    def __init__(self, items, rng: random.Random):
        if not items:
            raise ValueError("NoRepeatPool bos bir liste ile olusturulamaz")
        self._items = list(items)
        self._rng = rng
        self._queue = []
        self._last = None

    def _refill(self):
        pool = list(self._items)
        self._rng.shuffle(pool)
        # Tek elemanli havuzda kacinilmaz tekrar disinda, onceki turun son ogesi
        # yeni turun ilk ogesi olmasin diye bir deneme yap (best-effort).
        if len(pool) > 1 and self._last is not None and pool[0] == self._last:
            swap_i = self._rng.randrange(1, len(pool))
            pool[0], pool[swap_i] = pool[swap_i], pool[0]
        self._queue = pool

    def next(self):
        if not self._queue:
            self._refill()
        item = self._queue.pop(0)
        self._last = item
        return item


def hex_to_rgb(h):
    h = h.lstrip("#")
    return tuple(int(h[i:i + 2], 16) for i in (0, 2, 4))


def get_colors(cfg: Config, n: int) -> List[Tuple[int, int, int]]:
    if cfg.palette == "custom" and cfg.custom_colors:
        hexes = cfg.custom_colors
    elif cfg.palette == "rainbow":
        hexes = None
    else:
        hexes = PALETTES.get(cfg.palette, PALETTES["neon"])

    if hexes is None:
        colors = []
        for i in range(n):
            hue = i / max(n, 1)
            r, g, b = colorsys.hsv_to_rgb(hue, 0.85, 1.0)
            colors.append((int(r * 255), int(g * 255), int(b * 255)))
        return colors

    colors = [hex_to_rgb(h) for h in hexes]
    if len(colors) < n:
        reps = (n // len(colors)) + 1
        colors = (colors * reps)[:n]
    return colors[:n]


def draw_aa_circle(surface, color, center, radius, width=0):
    """Anti-aliased daire. pygame.draw.circle 1080p videoda pikselli/tirtikli kenar birakir;
    gfxdraw ile dolu daire + ince AA kontur cizerek toplari/pegleri belirgin sekilde
    pürüzsuzlestirir. width=0 -> dolu, width>0 -> sadece kontur (icten disa katmanli)."""
    cx, cy = int(round(center[0])), int(round(center[1]))
    r = max(1, int(round(radius)))
    col = tuple(color) if len(color) == 4 else (*color, 255)
    if width <= 0:
        pygame.gfxdraw.filled_circle(surface, cx, cy, r, col)
        pygame.gfxdraw.aacircle(surface, cx, cy, r, col)
    else:
        for i in range(max(1, int(width))):
            rr = max(1, r - i)
            pygame.gfxdraw.aacircle(surface, cx, cy, rr, col)


def draw_glow(surface, center, radius, color, layers=5, max_alpha=70, spread=2.3):
    """Additive (BLEND_RGBA_ADD) katmanli bloom/glow. Eski kod sadece 2 yari-saydam
    katman kullaniyordu; burada daha fazla katman + ismiga yakin yerde yogunlasan bir
    alpha egrisi ile gercekci bir 'isik sacma' hissi olusturuluyor."""
    glow_r = max(2, int(radius * spread))
    glow_s = pygame.Surface((glow_r * 2, glow_r * 2), pygame.SRCALPHA)
    for i in range(layers, 0, -1):
        f = i / layers
        gr = max(1, int(radius * (0.85 + (spread - 0.85) * f)))
        ga = max(2, int(max_alpha * (1 - f) ** 1.6) + 4)
        pygame.gfxdraw.filled_circle(glow_s, glow_r, glow_r, gr, (*color, ga))
    surface.blit(glow_s, (center[0] - glow_r, center[1] - glow_r), special_flags=pygame.BLEND_RGBA_ADD)


def get_font(name, size, bold=False):
    try:
        font = pygame.font.SysFont(name, size, bold=bold)
        if font is not None:
            return font
    except Exception:
        pass
    return pygame.font.Font(None, size)


def load_circular_face(path, diameter):
    """Bir resmi yukleyip kare/daire seklinde kirpar (cover-fit) ve daire maskesi uygular.
    Basarisiz olursa (dosya yok, bozuk vb.) None doner; cagiran yer duz renkli topa geri duser."""
    try:
        raw = pygame.image.load(path)
    except Exception as exc:
        print(f"Uyari: yuz resmi yuklenemedi '{path}' ({exc}), duz renkli topa dusuluyor.")
        return None

    diameter = max(2, int(diameter))
    iw, ih = raw.get_width(), raw.get_height()
    if iw == 0 or ih == 0:
        return None
    # convert()/convert_alpha() bir display mode gerektirir; bu script headless calistigi icin
    # alfa kanalli bir yuzeye manuel blit ederek esdeger bir sonuc elde ediyoruz.
    img = pygame.Surface((iw, ih), pygame.SRCALPHA)
    img.blit(raw, (0, 0))
    # Cover-fit: kisa kenari diameter'a esitle, fazlayi ortadan kirp
    scale = diameter / min(iw, ih)
    new_w, new_h = max(1, int(iw * scale)), max(1, int(ih * scale))
    scaled = pygame.transform.smoothscale(img, (new_w, new_h))
    crop_x = (new_w - diameter) // 2
    crop_y = (new_h - diameter) // 2
    cropped = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
    cropped.blit(scaled, (0, 0), area=pygame.Rect(crop_x, crop_y, diameter, diameter))

    # Daire maskesi: kare resmi yuvarlak hale getirir
    mask = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
    pygame.draw.circle(mask, (255, 255, 255, 255), (diameter // 2, diameter // 2), diameter // 2)
    result = pygame.Surface((diameter, diameter), pygame.SRCALPHA)
    result.blit(cropped, (0, 0))
    result.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
    return result


def render_text_outline(font, text, color, outline_color=(0, 0, 0), outline_px=3, shadow=True):
    """Konturlu (+ istege bagli golgeli) metin render eder, satisfying/viral stilde okunurlugu artirir."""
    base = font.render(text, True, color)
    w, h = base.get_width() + outline_px * 2 + 6, base.get_height() + outline_px * 2 + 10
    surf = pygame.Surface((w, h), pygame.SRCALPHA)
    cx, cy = w // 2 - base.get_width() // 2, h // 2 - base.get_height() // 2
    if shadow:
        shadow_layer = font.render(text, True, (0, 0, 0))
        shadow_layer.set_alpha(130)
        surf.blit(shadow_layer, (cx + 5, cy + 7))
    outline_layer = font.render(text, True, outline_color)
    for dx in range(-outline_px, outline_px + 1):
        for dy in range(-outline_px, outline_px + 1):
            if dx * dx + dy * dy <= outline_px * outline_px and (dx, dy) != (0, 0):
                surf.blit(outline_layer, (cx + dx, cy + dy))
    surf.blit(base, (cx, cy))
    return surf


# ===================================================================== #
# PARKUR URETICILERI
# Her biri (wall_segments, peg_circles) dondurur.
#   wall_segments: [((x1,y1),(x2,y2)), ...]
#   peg_circles:   [((x,y), radius), ...]
# ===================================================================== #

def course_funnel(w, h, rng: random.Random):
    walls = [
        ((w * 0.069, h * 0.234), (w * rng.uniform(0.40, 0.48), h * 0.430)),
        ((w * 0.931, h * 0.234), (w * rng.uniform(0.52, 0.60), h * 0.430)),
    ]
    gate_w = rng.uniform(0.045, 0.075)
    cx = 0.5 + rng.uniform(-0.03, 0.03)
    walls += [
        ((w * (cx - gate_w), h * 0.430), (w * (cx - gate_w), h * 0.65)),
        ((w * (cx + gate_w), h * 0.430), (w * (cx + gate_w), h * 0.65)),
    ]
    for side in (-1, 1):
        y0, y1 = h * 0.70, h * 0.75
        x_out = w * (0.5 + side * rng.uniform(0.28, 0.35))
        x_in = w * (0.5 + side * rng.uniform(0.10, 0.16))
        walls.append(((x_out, y0), (x_in, y1)))
    walls += [((0, 0), (0, h)), ((w, 0), (w, h))]
    return walls, []


def course_plinko(w, h, rng: random.Random):
    walls = [((0, 0), (0, h)), ((w, 0), (w, h))]
    pegs = []
    row_count = 11
    top = h * 0.22
    bottom = h * 0.80
    peg_r = w * 0.012
    for row in range(row_count):
        y = top + (bottom - top) * row / (row_count - 1)
        offset = (w * 0.05) if row % 2 == 0 else 0
        cols = 9
        for col in range(cols):
            x = (w * 0.08) + offset + col * (w * 0.84 / (cols - 1))
            jitter = rng.uniform(-w * 0.012, w * 0.012)
            if 0 < x + jitter < w:
                pegs.append(((x + jitter, y), peg_r))
    return walls, pegs


def course_cascade(w, h, rng: random.Random):
    walls = [((0, 0), (0, h)), ((w, 0), (w, h))]
    ramp_count = 5
    band = (h * 0.72) / ramp_count
    y0 = h * 0.22
    for i in range(ramp_count):
        y_top = y0 + i * band
        y_bot = y_top + band * rng.uniform(0.55, 0.75)
        gap = w * rng.uniform(0.12, 0.18)
        if i % 2 == 0:
            walls.append(((w * 0.02, y_top), (w - gap, y_bot)))
        else:
            walls.append(((w * 0.98, y_top), (gap, y_bot)))
    return walls, []


def course_vortex(w, h, rng: random.Random):
    """Merkeze dogru daralan spiral huni - toplar donerek asagi iner."""
    walls = [((0, 0), (0, h)), ((w, 0), (w, h))]
    cx = w / 2
    top_y = h * 0.20
    bottom_y = h * 0.78
    turns = 2.6
    steps = 90
    start_r = w * 0.46
    end_r = w * 0.10
    prev_l = prev_r = None
    for i in range(steps + 1):
        f = i / steps
        y = top_y + (bottom_y - top_y) * f
        r = start_r + (end_r - start_r) * f
        angle = f * turns * math.tau + rng.uniform(-0.03, 0.03)
        dx = math.sin(angle) * r * 0.35
        lx, rx = cx - r + dx, cx + r + dx
        if prev_l is not None:
            walls.append((prev_l, (lx, y)))
            walls.append((prev_r, (rx, y)))
        prev_l, prev_r = (lx, y), (rx, y)
    return walls, []


def course_chevron(w, h, rng: random.Random):
    """Zigzag (sevron) raylar: toplari sag-sol-sag diye sektiren egimli perdeler,
    her bandin ortasinda kucuk bir peg kumesi var. Plinko'nun duzenli peg izgarasindan
    ve funnel/cascade'in sade cizgilerinden farkli olarak, hem keskin yon degisimleri
    (gorsel enerji) hem de yerel peg kumeleri (parlama/isiltili an) biraraya geliyor."""
    walls = [((0, 0), (0, h)), ((w, 0), (w, h))]
    pegs = []
    band_count = 6
    top = h * 0.20
    bottom = h * 0.82
    band_h = (bottom - top) / band_count
    gap = w * 0.16  # toplarin gecebilecegi bosluk genisligi

    for i in range(band_count):
        y_top = top + i * band_h
        y_bot = y_top + band_h * 0.82
        # Bir banda sagdan sola, bir sonrakine soldan saga egimli perde - zigzag hissi
        if i % 2 == 0:
            x_top, x_bot = w * 0.04, w - gap
        else:
            x_top, x_bot = w - w * 0.04, gap
        jitter = rng.uniform(-w * 0.02, w * 0.02)
        walls.append(((x_top, y_top), (x_bot + jitter, y_bot)))

        # Bandin acik tarafinda (perdenin olmadigi bosluga yakin) kucuk bir peg kumesi:
        # topu son anda hafifce sapan, gozle takip edilebilir bir "surpriz" noktasi.
        cluster_x = gap * 0.5 if i % 2 == 0 else w - gap * 0.5
        cluster_y = (y_top + y_bot) / 2
        peg_r = w * 0.010
        for dx, dy in ((0, 0), (w * 0.035, -w * 0.02), (-w * 0.03, w * 0.025)):
            pegs.append(((cluster_x + dx + rng.uniform(-6, 6), cluster_y + dy), peg_r))

    return walls, pegs


COURSES = {
    "funnel": course_funnel,
    "plinko": course_plinko,
    "cascade": course_cascade,
    "vortex": course_vortex,
    "chevron": course_chevron,
}


# ===================================================================== #
# PARCACIKLAR (konfeti + elenme efekti)
# ===================================================================== #

class Particle:
    __slots__ = ("x", "y", "vx", "vy", "color", "size", "life", "max_life", "angle", "spin", "shape", "_surf")

    def __init__(self, x, y, color, rng: random.Random):
        self.x, self.y = x, y
        angle = rng.uniform(0, math.tau)
        speed = rng.uniform(150, 520)
        self.vx = math.cos(angle) * speed
        self.vy = math.sin(angle) * speed - rng.uniform(150, 350)
        self.color = color
        self.size = rng.uniform(4, 9)
        self.max_life = rng.uniform(1.4, 2.4)
        self.life = self.max_life
        self.angle = rng.uniform(0, 360)
        self.spin = rng.uniform(-360, 360)
        # Karisik sekiller (kurdele + yuvarlak parlama noktasi) tek tip dikdortgen
        # yagmurundan cok daha "zengin"/gercekci bir konfeti patlamasi hissi verir.
        self.shape = "dot" if rng.random() < 0.3 else "ribbon"
        # Her karede yeni bir pygame.Surface() ayirmak (confetti patlamasinda 100+
        # parcacik x 60fps) olcumde fark edilir bir maliyetti; boyut parcaciğin
        # omru boyunca sabit kaldigindan "damga" yuzeyini bir kere ayirip her karede
        # sadece temizleyip (fill) yeniden kullaniyoruz.
        self._surf = None

    def update(self, dt):
        self.vy += 900 * dt
        self.x += self.vx * dt
        self.y += self.vy * dt
        self.angle += self.spin * dt
        self.life -= dt
        return self.life > 0

    def draw(self, surface):
        life_f = max(0.0, self.life / self.max_life)
        alpha = max(0, min(255, int(255 * life_f)))
        if self.shape == "dot":
            # AA'li parlak nokta - additive blend ile isiltili bir kivilcim gibi gorunur
            r = max(1, int(self.size * 0.6))
            if self._surf is None:
                self._surf = pygame.Surface((r * 2 + 2, r * 2 + 2), pygame.SRCALPHA)
            else:
                self._surf.fill((0, 0, 0, 0))
            s = self._surf
            c = s.get_width() // 2
            pygame.gfxdraw.filled_circle(s, c, c, r, (*self.color, min(255, alpha + 40)))
            pygame.gfxdraw.aacircle(s, c, c, r, (*self.color, min(255, alpha + 40)))
            surface.blit(s, (self.x - c, self.y - c), special_flags=pygame.BLEND_RGBA_ADD)
        else:
            if self._surf is None:
                self._surf = pygame.Surface((self.size * 2, self.size * 2), pygame.SRCALPHA)
            else:
                self._surf.fill((0, 0, 0, 0))
            s = self._surf
            pygame.draw.rect(s, (*self.color, alpha), pygame.Rect(0, 0, self.size * 2, self.size),
                              border_radius=max(1, int(self.size * 0.3)))
            # Kurdelenin uzun kenarina ince bir parlaklik seridi - don/pul hissi guclendirir
            pygame.draw.line(s, (255, 255, 255, int(alpha * 0.55)),
                              (1, self.size * 0.3), (self.size * 2 - 2, self.size * 0.3), 1)
            rotated = pygame.transform.rotate(s, self.angle)
            surface.blit(rotated, (self.x - rotated.get_width() / 2, self.y - rotated.get_height() / 2))


class EliminationFlash:
    """Elenen topun oldugu yerde kisa, genisleyen bir halka."""
    __slots__ = ("x", "y", "color", "t", "duration")

    def __init__(self, x, y, color):
        self.x, self.y, self.color = x, y, color
        self.t = 0.0
        self.duration = 0.45

    def update(self, dt):
        self.t += dt
        return self.t < self.duration

    def draw(self, surface):
        prog = self.t / self.duration
        radius = max(2, int(10 + prog * 70))
        alpha = max(0, int(255 * (1 - prog)))
        s = pygame.Surface((radius * 2 + 4, radius * 2 + 4), pygame.SRCALPHA)
        c = s.get_width() // 2
        # Ana halka (AA'li, kalin) + hemen disinda daha soluk ikinci bir halka: bir
        # "sok dalgasi" genisliyormus gibi gorunur, eskisinden daha "patlama" hissi verir.
        draw_aa_circle(s, (*self.color, alpha), (c, c), radius, width=6)
        draw_aa_circle(s, (*self.color, max(0, alpha // 3)), (c, c), radius + 8, width=3)
        surface.blit(s, (self.x - c, self.y - c), special_flags=pygame.BLEND_RGBA_ADD)


# ===================================================================== #
# SIMULASYON
# ===================================================================== #

class BallRaceSimulation:
    def __init__(self, cfg: Config):
        self.cfg = cfg
        self.rng = random.Random(cfg.seed)
        self.w, self.h = cfg.width, cfg.height
        self.finish_y = int(self.h * cfg.finish_y_ratio)

        pygame.init()
        self.screen = pygame.Surface((self.w, self.h))

        self.title_font = get_font("impact", int(self.h * 0.045), bold=True)
        self.banner_font = get_font("impact", int(self.h * 0.07), bold=True)
        self.sub_font = get_font("arial", int(self.h * 0.022))
        self.hud_font = get_font("arial", int(self.h * 0.02), bold=True)

        # render_text_outline font.render + (2*outline_px+1)^2 blit dongusu yapar;
        # baslik/isim/leaderboard etiketleri gibi metinler her karede ayni kaliyor
        # ama eskiden her karede yeniden cizilyordu. Bu cache ile ayni (font, metin,
        # renk, outline) kombinasyonu bir kez cizilip tekrar tekrar blit ediliyor -
        # binlerce karelik bir videoda ciddi bir CPU tasarrufu saglar.
        self._text_cache = {}

        self.space = pymunk.Space()
        self.space.gravity = (0, cfg.gravity_y)

        out_dir = os.path.dirname(os.path.abspath(cfg.output))
        os.makedirs(out_dir, exist_ok=True)
        self._raw_output = cfg.output + ".raw.mp4" if cfg.music_path else cfg.output
        self.video_writer = None
        for codec in ("avc1", "mp4v"):
            fourcc = cv2.VideoWriter_fourcc(*codec)
            writer = cv2.VideoWriter(self._raw_output, fourcc, cfg.fps, (self.w, self.h))
            if writer.isOpened():
                self.video_writer = writer
                break
            writer.release()
        if self.video_writer is None:
            raise RuntimeError(f"Video yazici acilamadi: {self._raw_output}")

        self.balls = []
        self.particles = []
        self.flashes = []
        self.finish_order = []       # bitiren toplar, siraya gore
        self.eliminated_order = []   # elenen toplar, elenme sirasina gore
        self.last_elim_time = 0.0

        # Red Light Green Light durumu
        self._light_phase = "green"
        self._light_timer = (self.rng.uniform(cfg.redlight_green_min, cfg.redlight_green_max)
                              if cfg.redlight_enabled else None)

        self._bg_cache = None
        self._vignette = None
        self._shake_t = 0.0
        self._shake_max = 0.0001

        # Gravity Flip durumu
        self._gravflip_dir = 1
        self._gravflip_timer = (self.rng.uniform(cfg.gravityflip_interval_min, cfg.gravityflip_interval_max)
                                 if cfg.gravityflip_enabled else None)
        self._gravflip_warning = False

        # Minefield durumu
        self.mines = []
        self._mine_timer = (self.rng.uniform(cfg.minefield_interval_min, cfg.minefield_interval_max)
                             if cfg.minefield_enabled else None)

        # Magnet Pulse durumu
        self._magnet_timer = (self.rng.uniform(cfg.magnet_interval_min, cfg.magnet_interval_max)
                               if cfg.magnet_enabled else None)
        self._magnet_active = False
        self._magnet_remaining = 0.0
        self._magnet_pos = (self.w / 2, self.h / 2)
        self._magnet_polarity = 1

        # Color Gate durumu
        self._color_gates = []
        self._next_gate_time = (self.rng.uniform(cfg.colorgate_interval_min, cfg.colorgate_interval_max)
                                 if cfg.colorgate_enabled else None)

        # Laser Sweep durumu - uc asamali state machine: waiting -> warning -> active
        self._laser_state = "waiting" if cfg.laser_enabled else None
        self._laser_timer = (self.rng.uniform(cfg.laser_interval_min, cfg.laser_interval_max)
                              if cfg.laser_enabled else None)
        self._laser_progress = 0.0
        self._laser_axis_cur = "horizontal"
        self._laser_hit = set()

        # Jump Pads durumu: pedler sabit (bir kere yerlestirilir), her ped kendi
        # cooldown saatini top id'sine gore tutar (ayni topun ayni pede bitisik
        # kalip her karede tekrar tetiklenmesini engeller).
        self.jumppads = []

        # Slow-Mo Finish durumu
        self._slowmo_triggered = False
        self._slowmo_active = False
        self._slowmo_remaining = 0.0
        self._slowmo_focus_id = None
        self._slowmo_focus_pos = None
        self._slowmo_zoom_cur = 1.0

        self._build_background()
        self._build_vignette()
        self._build_course()
        self._spawn_balls()
        self._init_carousel()
        self._init_goldenball()
        self._init_jumppads()

    def _init_goldenball(self):
        if not self.cfg.goldenball_enabled or not self.balls:
            return
        chosen = self.rng.choice(self.balls)
        chosen["golden"] = True

    def _init_jumppads(self):
        """Jump Pads icin sabit konumlar secer (bir kere, simulasyon basinda).
        Rejection sampling ile pedlerin birbirine ve start/finish bolgelerine
        asiri yakin dusmesini engeller; makul bir deneme sayisi sonrasinda
        (parkur cok dar olabilir) elindeki en iyi sonuca razi olur."""
        cfg = self.cfg
        if not cfg.jumppad_enabled or cfg.jumppad_count <= 0:
            return
        radius = self.w * cfg.jumppad_radius_ratio
        min_gap = radius * 2.6
        play_top = self.h * 0.22
        play_bottom = self.finish_y - radius * 2
        margin_x = self.w * 0.12

        placed = []
        attempts = 0
        max_attempts = cfg.jumppad_count * 60
        while len(placed) < cfg.jumppad_count and attempts < max_attempts:
            attempts += 1
            x = self.rng.uniform(margin_x, self.w - margin_x)
            y = self.rng.uniform(play_top, max(play_top + 1, play_bottom))
            if all(math.hypot(x - px, y - py) >= min_gap for px, py in placed):
                placed.append((x, y))

        for (x, y) in placed:
            self.jumppads.append({"x": x, "y": y, "radius": radius, "cooldowns": {}})

    def _init_carousel(self):
        """Carousel modu icin guvenli alan merkezi/boyutlarini hesaplar (bir kere)."""
        cfg = self.cfg
        if not cfg.carousel_enabled:
            self._carousel_center = None
            return
        play_top = self.h * 0.17
        play_bottom = self.finish_y
        cx, cy = self.w / 2.0, (play_top + play_bottom) / 2.0
        self._carousel_center = (cx, cy)
        corners = [(0, play_top), (self.w, play_top), (0, play_bottom), (self.w, play_bottom)]
        self._carousel_full_size = max(math.hypot(x - cx, y - cy) for x, y in corners)
        self._carousel_min_size = self.w * cfg.carousel_min_size_ratio
        self._carousel_frozen_size = None  # min_survivors'a ulasilinca boyut burada donar

    def _carousel_current_size(self, t):
        if self._carousel_frozen_size is not None:
            return self._carousel_frozen_size
        cfg = self.cfg
        t_rel = t - cfg.carousel_start_time
        if t_rel <= 0:
            return self._carousel_full_size
        f = min(1.0, t_rel / max(0.01, cfg.carousel_shrink_duration))
        ease = f * f * (3 - 2 * f)  # smoothstep - daha "satisfying" bir daralma hissi
        return self._carousel_full_size + (self._carousel_min_size - self._carousel_full_size) * ease

    def _build_vignette(self):
        """Kenarlari hafifce karartan sabit bir overlay - sinematik/odakli his verir."""
        surf = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        max_d = math.hypot(self.w / 2, self.h / 2)
        cx, cy = self.w / 2, self.h / 2
        for i in range(24):
            f = i / 23
            r = int(max_d * (0.55 + f * 0.6))
            alpha = int(f * 70)
            pygame.draw.circle(surf, (0, 0, 0, alpha), (int(cx), int(cy)), r, width=int(max_d / 20) + 2)
        self._vignette = surf

    # ------------------------------------------------------------- #
    def _build_background(self):
        cfg = self.cfg
        surf = pygame.Surface((self.w, self.h))
        if cfg.background_style == "solid":
            surf.fill(hex_to_rgb(cfg.bg_color_top))
        elif cfg.background_style == "starfield":
            surf.fill(hex_to_rgb(cfg.bg_color_top))
            star_rng = random.Random(cfg.seed)
            for _ in range(140):
                x, y = star_rng.randint(0, self.w), star_rng.randint(0, self.h)
                b = star_rng.randint(80, 255)
                r = star_rng.choice([1, 1, 1, 2])
                pygame.draw.circle(surf, (b, b, b), (x, y), r)
        else:  # gradient
            top = hex_to_rgb(cfg.bg_color_top)
            bot = hex_to_rgb(cfg.bg_color_bottom)
            for y in range(self.h):
                t = y / self.h
                color = tuple(int(top[i] + (bot[i] - top[i]) * t) for i in range(3))
                pygame.draw.line(surf, color, (0, y), (self.w, y))

        # Ustte, baslik metninin arkasinda cok hafif bir "spot light" halesi: duz tek renk
        # fon yerine hafif bir derinlik/odak noktasi verir, sinematik bir his katar.
        spot = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        spot_cx, spot_cy = self.w / 2, self.h * 0.08
        spot_r = self.w * 0.75
        for i in range(10, 0, -1):
            f = i / 10
            r = int(spot_r * (0.25 + 0.75 * f))
            a = max(1, int(14 * (1 - f) ** 1.5))
            pygame.gfxdraw.filled_circle(spot, int(spot_cx), int(spot_cy), r, (255, 255, 255, a))
        surf.blit(spot, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)

        if cfg.background_style == "gradient":
            # Dusuk kontrastli gradyanlar MP4 sikistirmasinda belirgin "bant" cizgileri
            # birakir; cok hafif bir rastgele gurultu (dithering) ekleyerek bu banding'i
            # goze gorunmeyecek sekilde kiriyoruz - fon artik cok daha pürüzsuz gorunuyor.
            noise_rng = np.random.default_rng(cfg.seed if cfg.seed is not None else 0)
            arr = pygame.surfarray.pixels3d(surf)
            noise = noise_rng.integers(-3, 4, size=arr.shape, dtype=np.int16)
            arr[:] = np.clip(arr.astype(np.int16) + noise, 0, 255).astype(np.uint8)
            del arr

        self._bg_cache = surf

    def _build_course(self):
        gen = COURSES.get(self.cfg.course_type, course_plinko)
        walls, pegs = gen(self.w, self.h, self.rng)
        walls.append(((0, 0), (self.w, 0)))  # ust sinir

        self.wall_segments = walls
        self.peg_defs = pegs

        for p1, p2 in walls:
            shape = pymunk.Segment(self.space.static_body, p1, p2, self.w * 0.0167)
            shape.elasticity = 1.0
            shape.friction = 0.1
            self.space.add(shape)
        for (cx, cy), r in pegs:
            body = pymunk.Body(body_type=pymunk.Body.STATIC)
            body.position = (cx, cy)
            shape = pymunk.Circle(body, r)
            shape.elasticity = 1.0
            shape.friction = 0.1
            self.space.add(body, shape)

    def _spawn_balls(self):
        cfg = self.cfg
        n = max(1, cfg.num_balls)
        colors = get_colors(cfg, n)
        radius = self.w * cfg.ball_radius_ratio
        cols = min(n, 6)
        spacing_x = self.w * 0.7 / max(cols - 1, 1) if cols > 1 else 0
        start_x = self.w * 0.15
        start_y = self.h * 0.06

        face_cache = {}
        for i in range(n):
            row, col = divmod(i, cols)
            x = start_x + col * spacing_x if cols > 1 else self.w / 2
            y = start_y + row * (radius * 2.6)

            face_surf = None
            if cfg.face_images:
                path = cfg.face_images[i % len(cfg.face_images)]
                if path not in face_cache:
                    diameter = int(radius * 2 * max(0.3, cfg.face_scale))
                    face_cache[path] = load_circular_face(path, diameter)
                face_surf = face_cache[path]

            if cfg.face_names and i < len(cfg.face_names):
                name = cfg.face_names[i]
            else:
                name = f"#{i + 1}"

            self._add_ball((x, y), colors[i], name, radius, face_surf)

    def _add_ball(self, pos, color, name, radius, face_surf=None):
        cfg = self.cfg
        mass = self.rng.uniform(0.9, 1.1)
        moment = pymunk.moment_for_circle(mass, 0, radius)
        body = pymunk.Body(mass, moment)
        jitter_x = self.rng.uniform(-30, 30)
        jitter_y = self.rng.uniform(-15, 15)
        body.position = (pos[0] + jitter_x, pos[1])
        body.velocity = (jitter_x * 0.5, 80 + jitter_y)

        shape = pymunk.Circle(body, radius)
        shape.elasticity = self.rng.uniform(cfg.elasticity_min, cfg.elasticity_max)
        shape.friction = cfg.friction
        self.space.add(body, shape)
        self.balls.append({
            "shape": shape, "color": color, "name": name, "radius": radius,
            "trail": [], "finished": False, "eliminated": False, "face": face_surf,
            "golden": False, "_prev_y": pos[1],
        })

    # ------------------------------------------------------------- #
    # Cizim
    # ------------------------------------------------------------- #
    def _cached_text(self, font, text, color, outline_color=(0, 0, 0), outline_px=3, shadow=True):
        """render_text_outline'in sonucunu (font, metin, renk, outline) anahtariyla
        onbelleğe alir. YALNIZCA donen Surface'i blit etmek icin kullan; set_alpha()
        gibi yerinde (in-place) mutasyonlar onbellekteki tum gelecek kullanimlari
        bozar - oyle bir durumda dogrudan render_text_outline cagir (orn. geri
        sayim/kazanan banner'i gibi alpha/scale animasyonu olan tek seferlik metinler)."""
        key = (id(font), text, color, outline_color, outline_px, shadow)
        surf = self._text_cache.get(key)
        if surf is None:
            surf = render_text_outline(font, text, color, outline_color, outline_px, shadow)
            self._text_cache[key] = surf
        return surf

    def draw_background(self):
        self.screen.blit(self._bg_cache, (0, 0))
        text = self._cached_text(self.title_font, self.cfg.title_text, (255, 255, 255))
        self.screen.blit(text, (self.w // 2 - text.get_width() // 2, self.h * 0.03 - 10))
        if self.cfg.subtitle_text:
            sub = self._cached_text(self.sub_font, self.cfg.subtitle_text, (210, 210, 220), outline_px=2)
            self.screen.blit(sub, (self.w // 2 - sub.get_width() // 2, self.h * 0.085 - 8))
        if self._vignette is not None:
            self.screen.blit(self._vignette, (0, 0))

    def draw_course(self):
        wc = hex_to_rgb(self.cfg.wall_color)
        for p1, p2 in self.wall_segments:
            pygame.draw.line(self.screen, wc, p1, p2, int(self.w * 0.0167))
        for (cx, cy), r in self.peg_defs:
            # Hafif dusen golge: pegin hacimli/3D gorunmesini saglar
            pygame.gfxdraw.filled_circle(self.screen, int(cx) + 2, int(cy) + 3, int(r), (0, 0, 0, 70))
            draw_aa_circle(self.screen, wc, (cx, cy), r)
            draw_aa_circle(self.screen, (255, 255, 255), (cx, cy), r, width=2)
            # Ust-solda kucuk bir speküler nokta
            hl_r = max(1, int(r * 0.3))
            pygame.gfxdraw.filled_circle(self.screen, int(cx - r * 0.3), int(cy - r * 0.3), hl_r, (255, 255, 255, 120))

    def draw_finish_line(self):
        sq = int(self.w * 0.0694)
        for x in range(0, self.w, sq):
            c = (255, 255, 255) if (x // sq) % 2 == 0 else (30, 30, 30)
            pygame.draw.rect(self.screen, c, (x, self.finish_y, sq, sq))
        # Cizginin hemen ustunde ince, additive bir isik seridi: bitis cizgisini
        # gercek bir "race finish" gibi vurgular, duz damali desenden daha dikkat cekici.
        glow_h = max(6, int(sq * 0.4))
        strip = pygame.Surface((self.w, glow_h * 2), pygame.SRCALPHA)
        for i in range(glow_h, 0, -1):
            f = i / glow_h
            a = max(1, int(50 * (1 - f) ** 1.3))
            pygame.draw.line(strip, (255, 255, 255, a), (0, glow_h - i), (self.w, glow_h - i))
        self.screen.blit(strip, (0, self.finish_y - glow_h), special_flags=pygame.BLEND_RGBA_ADD)

    def draw_balls(self):
        for b in self.balls:
            if b["eliminated"]:
                continue
            pos = b["shape"].body.position
            color = b["color"]
            radius = b["radius"]

            trail = b["trail"]
            trail.append((pos.x, pos.y))
            if len(trail) > self.cfg.trail_length:
                trail.pop(0)

            trail_len = len(trail)
            for i, p in enumerate(trail):
                f = i / trail_len
                # Kuyruk ucuna dogru yumusakca sonen, basa dogru buyuyen "kuyruklu yildiz" hissi;
                # additive blend sayesinde ust uste binen halkalar bulanik/kirli gorunmuyor,
                # tersine isik birikiyormus gibi parliyor.
                alpha = max(0, int(95 * (f ** 1.6)))
                size = max(1, radius * (0.22 + 0.78 * f))
                s = pygame.Surface((int(size * 2) + 2, int(size * 2) + 2), pygame.SRCALPHA)
                sc = s.get_width() // 2
                pygame.gfxdraw.filled_circle(s, sc, sc, max(1, int(size)), (*color, alpha))
                self.screen.blit(s, (p[0] - sc, p[1] - sc), special_flags=pygame.BLEND_RGBA_ADD)

            if self.cfg.glow:
                draw_glow(self.screen, (pos.x, pos.y), radius, color, layers=5, max_alpha=65, spread=2.4)

            if b["face"] is not None:
                # Yuz modu: deformasyon yok (resim bozulmasin diye), renkli halka + ortada daire resim
                face = b["face"]
                ring_r = int(radius) + 3
                draw_aa_circle(self.screen, color, (pos.x, pos.y), ring_r, width=5)
                self.screen.blit(face, (pos.x - face.get_width() / 2, pos.y - face.get_height() / 2))
                draw_aa_circle(self.screen, (255, 255, 255), (pos.x, pos.y), radius, width=2)
            else:
                # Squash & stretch: hiz yonunde hafif uzama, dikine sikisma - "juicy" his verir
                vel = b["shape"].body.velocity
                speed = math.hypot(vel.x, vel.y)
                stretch = min(0.35, speed / 2800.0)
                if stretch > 0.02:
                    move_angle = math.degrees(math.atan2(vel.y, vel.x))
                    ball_w = int(radius * 2 * (1 + stretch))
                    ball_h = int(radius * 2 * (1 - stretch * 0.6))
                    ball_s = pygame.Surface((ball_w, ball_h), pygame.SRCALPHA)
                    ew, eh = ball_w // 2, ball_h // 2
                    pygame.gfxdraw.filled_ellipse(ball_s, ew, eh, ew, eh, color)
                    pygame.gfxdraw.aaellipse(ball_s, ew, eh, ew, eh, color)
                    pygame.draw.ellipse(ball_s, (255, 255, 255), (0, 0, ball_w, ball_h), 3)
                    rotated = pygame.transform.rotate(ball_s, -move_angle)
                    self.screen.blit(rotated, (pos.x - rotated.get_width() / 2, pos.y - rotated.get_height() / 2))
                else:
                    draw_aa_circle(self.screen, color, (pos.x, pos.y), radius)
                    draw_aa_circle(self.screen, (255, 255, 255), (pos.x, pos.y), radius, width=3)

                # Spekuler highlight: hafif ustte-solda parlak nokta, 3D/cam hissi verir.
                # Artik yumusak (AA'li) bir cekirdek + onun etrafinda daha genis, cok
                # soluk ikinci bir halka var - gercek cam/plastik yansimasina daha yakin.
                hl_r = max(2, int(radius * 0.26))
                hl_pos = (pos.x - radius * 0.33, pos.y - radius * 0.35)
                hl_surf = pygame.Surface((hl_r * 5, hl_r * 5), pygame.SRCALPHA)
                hc = hl_surf.get_width() // 2
                pygame.gfxdraw.filled_circle(hl_surf, hc, hc, int(hl_r * 1.8), (255, 255, 255, 50))
                pygame.gfxdraw.filled_circle(hl_surf, hc, hc, hl_r, (255, 255, 255, 215))
                pygame.gfxdraw.aacircle(hl_surf, hc, hc, hl_r, (255, 255, 255, 215))
                self.screen.blit(hl_surf, (hl_pos[0] - hc, hl_pos[1] - hc))

            if b["golden"]:
                gr = int(radius) + 6 + int(2 * math.sin(pygame.time.get_ticks() * 0.01))
                draw_glow(self.screen, (pos.x, pos.y), radius, (255, 215, 0), layers=4, max_alpha=55, spread=2.6)
                draw_aa_circle(self.screen, (255, 215, 0), (pos.x, pos.y), gr, width=3)
                for i in range(4):
                    sa = pygame.time.get_ticks() * 0.004 + i * (math.tau / 4)
                    sx = pos.x + math.cos(sa) * (gr + 10)
                    sy = pos.y + math.sin(sa) * (gr + 10)
                    pygame.gfxdraw.filled_circle(self.screen, int(sx), int(sy), 3, (255, 230, 120, 230))
                    pygame.gfxdraw.aacircle(self.screen, int(sx), int(sy), 3, (255, 230, 120, 230))

            # Isim etiketi: yuz modunda topun hemen altinda, normalde tam ortasinda
            if radius > self.w * 0.018:
                label = self._cached_text(self.hud_font, b["name"], (255, 255, 255), outline_px=2, shadow=False)
                max_w = radius * 2.2 if b["face"] is not None else radius * 1.5
                scale = min(1.0, max_w / max(label.get_width(), 1))
                if scale < 1.0:
                    label = pygame.transform.smoothscale(
                        label, (max(1, int(label.get_width() * scale)), max(1, int(label.get_height() * scale)))
                    )
                label_y = pos.y + radius + 4 if b["face"] is not None else pos.y - label.get_height() / 2
                self.screen.blit(label, (pos.x - label.get_width() / 2, label_y))

    def draw_progress_bar(self):
        """Ustte ince bir cubuk: en onde giden topun bitis cizgisine ne kadar yakin oldugunu gosterir."""
        active = self.active_balls()
        if not active:
            progress = 1.0
        else:
            top_ref = self.h * 0.05
            max_y = max(b["shape"].body.position.y for b in active)
            progress = max(0.0, min(1.0, (max_y - top_ref) / (self.finish_y - top_ref)))

        margin = int(self.w * 0.08)
        bar_y = int(self.h * 0.122)
        bar_w = self.w - margin * 2
        bar_h = max(4, int(self.h * 0.006))
        pygame.draw.rect(self.screen, (255, 255, 255, 60), (margin, bar_y, bar_w, bar_h), border_radius=bar_h)
        fill_w = max(bar_h, int(bar_w * progress))
        fill_color = (255, 215, 0) if progress > 0.85 else (120, 220, 255)
        pygame.draw.rect(self.screen, fill_color, (margin, bar_y, fill_w, bar_h), border_radius=bar_h)

    def draw_leaderboard(self):
        if not self.cfg.show_leaderboard:
            return
        x0, y0 = int(self.w * 0.03), int(self.h * 0.72)
        medal_colors = {1: (255, 215, 0), 2: (200, 200, 210), 3: (205, 140, 70)}
        rank = 1
        for b in self.finish_order:
            label = self._cached_text(self.hud_font, f"{rank}. {b['name']}", (255, 255, 255),
                                       outline_px=2, shadow=False)
            dot_color = medal_colors.get(rank, b["color"])
            if rank <= 3:
                draw_glow(self.screen, (x0 + 8, y0 - 6), 8, dot_color, layers=3, max_alpha=70, spread=2.2)
            draw_aa_circle(self.screen, dot_color, (x0 + 8, y0 - 6), 8)
            draw_aa_circle(self.screen, b["color"], (x0 + 8, y0 - 6), 8, width=2)
            self.screen.blit(label, (x0 + 24, y0 - 16))
            y0 += int(self.h * 0.03)
            rank += 1
            if rank > 5:
                break

    def draw_watermark(self):
        if not self.cfg.watermark_text:
            return
        wm = self.sub_font.render(self.cfg.watermark_text, True, (255, 255, 255))
        wm.set_alpha(160)
        self.screen.blit(wm, (self.w // 2 - wm.get_width() // 2, self.h * 0.965))

    def draw_countdown(self, label, progress=1.0):
        """progress: 0 -> rakam yeni belirdi, 1 -> gosterim suresi bitiyor.
        Eskiden rakam statik olarak ekrana oturuyordu; simdi disaridan icerı 'pop'
        layan bir olcek animasyonu + arkasinda hizla sonen bir isik patlamasi var,
        boylece her rakam gecisi daha 'punchy'/dikkat cekici hissettiriyor."""
        overlay = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 120))
        self.screen.blit(overlay, (0, 0))

        is_go = label.upper().startswith("GO")
        accent = (120, 255, 150) if is_go else (255, 255, 255)

        # Giris animasyonu: ilk ~%22'lik kisimda buyuk bir ease-out ile 1.0'a oturur
        pop_window = 0.22
        if progress < pop_window:
            pf = progress / pop_window
            ease = 1 - (1 - pf) ** 3
            scale = 1.65 - 0.65 * ease
            alpha = int(255 * ease)
        else:
            scale = 1.0 + 0.035 * math.sin(progress * math.pi)  # hafif "nefes alma"
            alpha = 255

        # Isik patlamasi: rakam belirir belirmez disari dogru HIZLA sonen kucuk bir halka
        # (eskisi gibi genis/donuk bir hale yerine kisa, keskin bir 'pop' kivilcimi)
        flash_window = pop_window * 0.9
        if progress < flash_window:
            flash_f = progress / flash_window
            flash_r = int(self.w * (0.05 + 0.12 * flash_f))
            flash_a = max(0, int(100 * (1 - flash_f) ** 3))
            if flash_a > 2:
                draw_glow(self.screen, (self.w // 2, self.h // 2), flash_r, accent,
                          layers=4, max_alpha=flash_a, spread=1.6)

        text = render_text_outline(self.banner_font, label, accent, outline_px=4)
        if alpha < 255:
            text.set_alpha(alpha)
        if abs(scale - 1.0) > 0.01:
            text = pygame.transform.rotozoom(text, 0, scale)
        self.screen.blit(text, (self.w // 2 - text.get_width() // 2, self.h // 2 - text.get_height() // 2))

    def draw_winner_banner(self, frames_since_win):
        winner = self._get_winner()
        if winner is None:
            return
        overlay = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        overlay.fill((0, 0, 0, 150))
        self.screen.blit(overlay, (0, 0))

        pulse = 1.0 + 0.08 * math.sin(frames_since_win / self.cfg.fps * 6.0)
        base_label = f"{winner['name']} LAST = WINS!" if self.cfg.reverse_win else f"{winner['name']} WINS!"
        label = f"\u2728 GOLDEN BALL WINS! \u2728" if winner.get("golden") else base_label
        banner_color = (255, 215, 0) if winner.get("golden") else winner["color"]
        banner_cx, banner_cy = self.w // 2, int(self.h * 0.40)

        # Banner arkasinda yumusakca donen isinlar + buyuk bir isik halesi: kazanan
        # ekrani eskisinden cok daha "kutlama" hissi verir, metin bos siyah fon
        # yerine isik saçan bir odak noktasinin ustunde duruyor gibi gorunur.
        spin = frames_since_win / self.cfg.fps * 0.8
        ray_s = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        n_rays = 10
        ray_len = self.w * 0.62
        for i in range(n_rays):
            ang = spin + i * (math.tau / n_rays)
            ex = banner_cx + math.cos(ang) * ray_len
            ey = banner_cy + math.sin(ang) * ray_len
            perp = ang + math.pi / 2
            half_w = 10
            p1 = (banner_cx + math.cos(perp) * half_w, banner_cy + math.sin(perp) * half_w)
            p2 = (banner_cx - math.cos(perp) * half_w, banner_cy - math.sin(perp) * half_w)
            pygame.gfxdraw.filled_trigon(ray_s, int(p1[0]), int(p1[1]), int(p2[0]), int(p2[1]),
                                          int(ex), int(ey), (*banner_color, 26))
        self.screen.blit(ray_s, (0, 0), special_flags=pygame.BLEND_RGBA_ADD)
        draw_glow(self.screen, (banner_cx, banner_cy), int(self.w * 0.16), banner_color,
                  layers=6, max_alpha=55, spread=2.6)

        text = render_text_outline(self.banner_font, label, banner_color, outline_px=4)
        scaled = pygame.transform.rotozoom(text, 0, pulse)
        self.screen.blit(
            scaled,
            (self.w // 2 - scaled.get_width() // 2, self.h * 0.40 - scaled.get_height() // 2),
        )
        self.draw_leaderboard()

    def spawn_confetti(self, winner):
        if not self.cfg.confetti_enabled:
            return
        cx, cy = self.w // 2, int(self.h * 0.40)
        if winner is not None and winner.get("golden"):
            gold_palette = [(255, 215, 0), (255, 235, 120), (255, 255, 255)]
            for _ in range(140):
                self.particles.append(Particle(cx, cy, self.rng.choice(gold_palette), self.rng))
        palette = [b["color"] for b in self.balls] + [(255, 215, 0), (255, 255, 255)]
        for _ in range(160):
            self.particles.append(Particle(cx, cy, self.rng.choice(palette), self.rng))

    def update_and_draw_effects(self, dt):
        alive = []
        for p in self.particles:
            if p.update(dt):
                p.draw(self.screen)
                alive.append(p)
        self.particles = alive

        alive_flash = []
        for f in self.flashes:
            if f.update(dt):
                f.draw(self.screen)
                alive_flash.append(f)
        self.flashes = alive_flash

    # ------------------------------------------------------------- #
    # Oyun mantigi
    # ------------------------------------------------------------- #
    def _trigger_shake(self, duration):
        """Kamera sarsintisini baslatir ve suresini kaydeder, boylece _surface_to_bgr
        sarsintiyi zamanla sonumleyebilir (sabit genlikte ani zipla-dur yerine)."""
        self._shake_t = duration
        self._shake_max = max(duration, 0.0001)

    def _eliminate(self, b, t, reason, shake=0.18, flash_color=None):
        """Ortak elenme islemi: eleme modlari (sudden-death, redlight, boss, minefield,
        color-gate, carousel) ayni 6 satiri (flash + fizikten cikar + bayrak + kayit +
        shake + log) tekrar ediyordu; hepsi artik bu tek metoda cagri yapiyor."""
        pos = b["shape"].body.position
        color = flash_color if flash_color is not None else b["color"]
        self.flashes.append(EliminationFlash(pos.x, pos.y, color))
        self.space.remove(b["shape"].body, b["shape"])
        b["eliminated"] = True
        self.eliminated_order.append(b)
        self._trigger_shake(shake)
        print(f"[{t:5.2f}s] {reason}: {b['name']}")

    def active_balls(self):
        return [b for b in self.balls if not b["finished"] and not b["eliminated"]]

    def check_finishers(self, t):
        for b in self.active_balls():
            if b["shape"].body.position.y >= self.finish_y:
                b["finished"] = True
                self.finish_order.append(b)
                print(f"[{t:5.2f}s] Bitirdi: {b['name']}  (sira: {len(self.finish_order)})")

    def check_eliminations(self, t):
        cfg = self.cfg
        if not cfg.elimination_enabled:
            return
        active = self.active_balls()
        if t - self.last_elim_time < cfg.elimination_interval_seconds:
            return
        if len(active) <= cfg.min_survivors:
            return
        self.last_elim_time = t
        active.sort(key=lambda b: b["shape"].body.position.y)  # en geride olan basta
        to_remove = active[: cfg.eliminate_per_round]
        for b in to_remove:
            if len(self.active_balls()) <= cfg.min_survivors:
                break
            self._eliminate(b, t, "Elendi")

    def check_redlight(self, t, dt):
        """Squid Game tarzi: yesilde serbest dusus, kirmizida tum fizik donar.
        Isik kirmiziya gecerken belirlenen esikten hizli hareket eden toplar elenir."""
        cfg = self.cfg
        if not cfg.redlight_enabled or self._light_timer is None:
            return
        self._light_timer -= dt
        if self._light_timer > 0:
            return

        if self._light_phase == "green":
            active = list(self.active_balls())
            # Hepsi yercekimiyle surekli hizlandigindan sabit esik herkesi ayni anda eler;
            # bunun yerine sadece o anda EN HIZLI hareket eden(ler) "yakalanmis" sayilir.
            active.sort(key=lambda b: math.hypot(*b["shape"].body.velocity), reverse=True)
            n_catch = min(cfg.redlight_eliminate_per_round, max(0, len(active) - cfg.min_survivors))
            caught = {id(b) for b in active[:n_catch]
                      if math.hypot(*b["shape"].body.velocity) > cfg.redlight_speed_threshold}
            for b in active:
                if id(b) in caught:
                    self._eliminate(b, t, "Kirmizi isikta yakalandi", shake=0.12)
                else:
                    b["shape"].body.velocity = (0, 0)
            self._light_phase = "red"
            self.space.gravity = (0, 0)
            self._light_timer = self.rng.uniform(cfg.redlight_red_min, cfg.redlight_red_max)
        else:
            self._light_phase = "green"
            self.space.gravity = (0, cfg.gravity_y * self._gravflip_dir)
            self._light_timer = self.rng.uniform(cfg.redlight_green_min, cfg.redlight_green_max)

    def _boss_position(self, elapsed):
        cfg = self.cfg
        bx = self.w / 2 + math.sin(elapsed * cfg.boss_speed / 150.0) * (self.w * 0.34)
        by = self.h * 0.52 + math.sin(elapsed * 0.7) * (self.h * 0.05)
        return bx, by

    def check_boss(self, t):
        """Belli bir sureden sonra ekranda gezinen bir 'boss' belirir; degen top elenir."""
        cfg = self.cfg
        if not cfg.boss_enabled or t < cfg.boss_spawn_time:
            return
        bx, by = self._boss_position(t - cfg.boss_spawn_time)
        br = self.w * cfg.boss_radius_ratio
        for b in list(self.active_balls()):
            pos = b["shape"].body.position
            if math.hypot(pos.x - bx, pos.y - by) < br + b["radius"]:
                self._eliminate(b, t, "BOSS yuttu", shake=0.2)

    def draw_boss(self, t):
        cfg = self.cfg
        if not cfg.boss_enabled or t < cfg.boss_spawn_time:
            return
        bx, by = self._boss_position(t - cfg.boss_spawn_time)
        br = self.w * cfg.boss_radius_ratio
        color = hex_to_rgb(cfg.boss_color)
        pulse = 1.0 + 0.1 * math.sin(t * 10.0)
        r = max(4, int(br * pulse))

        draw_glow(self.screen, (bx, by), r, color, layers=4, max_alpha=60, spread=2.1)
        draw_aa_circle(self.screen, color, (bx, by), r)
        draw_aa_circle(self.screen, (0, 0, 0), (bx, by), r, width=4)
        eye_off = r * 0.35
        for sx in (-1, 1):
            ex, ey = bx + sx * eye_off, by - r * 0.1
            pygame.draw.line(self.screen, (255, 255, 255), (ex - 7, ey - 7), (ex + 7, ey + 7), 4)
            pygame.draw.line(self.screen, (255, 255, 255), (ex - 7, ey + 7), (ex + 7, ey - 7), 4)

    # ------------------------------------------------------------- #
    # Gravity Flip
    # ------------------------------------------------------------- #
    def check_gravityflip(self, t, dt):
        cfg = self.cfg
        if not cfg.gravityflip_enabled or self._gravflip_timer is None:
            return
        self._gravflip_timer -= dt
        if not self._gravflip_warning and self._gravflip_timer <= cfg.gravityflip_warning_seconds:
            self._gravflip_warning = True
        if self._gravflip_timer > 0:
            return
        self._gravflip_dir *= -1
        self._gravflip_warning = False
        self.space.gravity = (0, cfg.gravity_y * self._gravflip_dir)
        self._gravflip_timer = self.rng.uniform(cfg.gravityflip_interval_min, cfg.gravityflip_interval_max)
        self._trigger_shake(0.22)
        print(f"[{t:5.2f}s] YERCEKIMI TERS DONDU! (yon: {'asagi' if self._gravflip_dir > 0 else 'yukari'})")

    def draw_gravityflip_overlay(self):
        cfg = self.cfg
        if not cfg.gravityflip_enabled:
            return
        if self._gravflip_warning:
            tint = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
            flash = 60 + int(60 * abs(math.sin(pygame.time.get_ticks() * 0.03)))
            tint.fill((255, 255, 255, flash))
            self.screen.blit(tint, (0, 0))
        arrow_up = self._gravflip_dir < 0
        label = "\u2191 TERS YERCEKIMI \u2191" if arrow_up else "\u2193 YERCEKIMI \u2193"
        color = (120, 220, 255) if arrow_up else (255, 220, 100)
        badge = self._cached_text(self.hud_font, label, color, outline_px=2)
        self.screen.blit(badge, (self.w // 2 - badge.get_width() // 2, int(self.h * 0.175)))

    # ------------------------------------------------------------- #
    # Minefield
    # ------------------------------------------------------------- #
    def check_minefield(self, t, dt):
        cfg = self.cfg
        if not cfg.minefield_enabled or self._mine_timer is None:
            return
        self._mine_timer -= dt
        if self._mine_timer <= 0 and len(self.mines) < cfg.minefield_max_active:
            mx = self.rng.uniform(self.w * 0.12, self.w * 0.88)
            my = self.rng.uniform(self.h * 0.26, self.h * 0.78)
            self.mines.append({
                "x": mx, "y": my, "radius": self.w * cfg.minefield_radius_ratio,
                "timer": cfg.minefield_warning_seconds, "armed": False,
            })
            self._mine_timer = self.rng.uniform(cfg.minefield_interval_min, cfg.minefield_interval_max)

        still_alive = []
        for mine in self.mines:
            if not mine["armed"]:
                mine["timer"] -= dt
                if mine["timer"] <= 0:
                    mine["armed"] = True
            exploded = False
            if mine["armed"]:
                for b in self.active_balls():
                    pos = b["shape"].body.position
                    if math.hypot(pos.x - mine["x"], pos.y - mine["y"]) < mine["radius"] + b["radius"]:
                        self._eliminate(b, t, "MINA PATLADI", shake=0.25, flash_color=(255, 170, 0))
                        exploded = True
                        break
            if not exploded:
                still_alive.append(mine)
        self.mines = still_alive

    def draw_minefield(self):
        if not self.cfg.minefield_enabled:
            return
        color = hex_to_rgb(self.cfg.minefield_color)
        for mine in self.mines:
            r = int(mine["radius"])
            if mine["armed"]:
                pulse = 1.0 + 0.12 * math.sin(pygame.time.get_ticks() * 0.02)
                rr = max(2, int(r * pulse))
                draw_glow(self.screen, (mine["x"], mine["y"]), rr, color, layers=4, max_alpha=55, spread=2.3)
                draw_aa_circle(self.screen, color, (mine["x"], mine["y"]), rr)
                draw_aa_circle(self.screen, (0, 0, 0), (mine["x"], mine["y"]), rr, width=3)
            else:
                blink_on = int(pygame.time.get_ticks() / 110) % 2 == 0
                c = color if blink_on else (90, 50, 0)
                draw_aa_circle(self.screen, c, (mine["x"], mine["y"]), r, width=3)

    # ------------------------------------------------------------- #
    # Magnet Pulse
    # ------------------------------------------------------------- #
    def check_magnet(self, t, dt):
        cfg = self.cfg
        if not cfg.magnet_enabled or self._magnet_timer is None:
            return
        if self._magnet_active:
            self._magnet_remaining -= dt
            if self._magnet_remaining <= 0:
                self._magnet_active = False
                self._magnet_timer = self.rng.uniform(cfg.magnet_interval_min, cfg.magnet_interval_max)
            return
        self._magnet_timer -= dt
        if self._magnet_timer <= 0:
            self._magnet_active = True
            self._magnet_remaining = cfg.magnet_duration
            self._magnet_pos = (self.rng.uniform(self.w * 0.2, self.w * 0.8),
                                 self.rng.uniform(self.h * 0.3, self.h * 0.7))
            if cfg.magnet_mode == "attract":
                self._magnet_polarity = 1
            elif cfg.magnet_mode == "repel":
                self._magnet_polarity = -1
            else:
                self._magnet_polarity = self.rng.choice([1, -1])
            print(f"[{t:5.2f}s] MIKNATIS AKTIF ({'cekiyor' if self._magnet_polarity > 0 else 'itiyor'})")

    def apply_magnet_forces(self):
        if not self._magnet_active:
            return
        cfg = self.cfg
        mx, my = self._magnet_pos
        for b in self.active_balls():
            body = b["shape"].body
            dx, dy = mx - body.position.x, my - body.position.y
            dist = max(40.0, math.hypot(dx, dy))
            force_mag = cfg.magnet_strength / dist
            fx = (dx / dist) * force_mag * self._magnet_polarity
            fy = (dy / dist) * force_mag * self._magnet_polarity
            body.apply_force_at_world_point((fx, fy), body.position)

    def draw_magnet(self):
        if not self.cfg.magnet_enabled or not self._magnet_active:
            return
        mx, my = self._magnet_pos
        color = (120, 200, 255) if self._magnet_polarity > 0 else (255, 110, 110)
        pulse = 1.0 + 0.15 * math.sin(pygame.time.get_ticks() * 0.025)
        r = int(self.w * 0.045 * pulse)
        draw_glow(self.screen, (mx, my), r, color, layers=4, max_alpha=55, spread=2.4)
        draw_aa_circle(self.screen, color, (mx, my), r, width=4)
        symbol = "+" if self._magnet_polarity > 0 else "-"
        badge = self._cached_text(self.hud_font, symbol, color, outline_px=2)
        self.screen.blit(badge, (mx - badge.get_width() / 2, my - badge.get_height() / 2))

    # ------------------------------------------------------------- #
    # Color Gate
    # ------------------------------------------------------------- #
    def check_colorgate(self, t, dt):
        cfg = self.cfg
        if not cfg.colorgate_enabled or self._next_gate_time is None:
            return
        active = self.active_balls()
        if t >= self._next_gate_time and len(active) >= cfg.colorgate_min_active_balls:
            gy = self.rng.uniform(self.h * 0.28, self.h * 0.72)
            required = self.rng.choice(active)
            self._color_gates.append({"y": gy, "color": required["color"], "resolved": set()})
            if len(self._color_gates) > 4:
                self._color_gates.pop(0)
            self._next_gate_time = t + self.rng.uniform(cfg.colorgate_interval_min, cfg.colorgate_interval_max)

        for gate in self._color_gates:
            for b in active:
                if b["eliminated"]:
                    continue
                bid = id(b)
                if bid in gate["resolved"]:
                    continue
                prev_y, cur_y = b["_prev_y"], b["shape"].body.position.y
                crossed = (prev_y < gate["y"] <= cur_y) or (prev_y > gate["y"] >= cur_y)
                if not crossed:
                    continue
                gate["resolved"].add(bid)
                if b["color"] != gate["color"]:
                    self._eliminate(b, t, "YANLIS RENK KAPIDA ELENDI")

        for b in self.balls:
            if not b["eliminated"]:
                b["_prev_y"] = b["shape"].body.position.y

    def draw_colorgate(self):
        if not self.cfg.colorgate_enabled:
            return
        for gate in self._color_gates:
            y = int(gate["y"])
            color = gate["color"]
            dash_w, gap_w, x = 22, 12, 0
            while x < self.w:
                pygame.draw.line(self.screen, color, (x, y), (min(x + dash_w, self.w), y), 5)
                x += dash_w + gap_w
            draw_aa_circle(self.screen, color, (self.w * 0.12, y), 14)
            draw_aa_circle(self.screen, (255, 255, 255), (self.w * 0.12, y), 14, width=2)
            badge = self._cached_text(self.hud_font, "SADECE", (255, 255, 255), outline_px=2)
            self.screen.blit(badge, (int(self.w * 0.16), y - badge.get_height() // 2))

    # ------------------------------------------------------------- #
    # Laser Sweep
    # ------------------------------------------------------------- #
    def check_laser(self, t, dt):
        """Periyodik olarak ekrani bastan basa tarayan bir lazer: kisa bir uyaridan
        sonra aktif olur, parkuru belirlenen eksende (yatay/dikey) bastan basa kat
        eder; o anda cizginin kalinligi icinde kalan aktif toplar elenir. Uc asamali
        bir state machine: waiting (sira bekliyor) -> warning (uyari yanip sonuyor)
        -> active (cizgi taraniyor) -> tekrar waiting."""
        cfg = self.cfg
        if not cfg.laser_enabled:
            return

        if self._laser_state == "waiting":
            self._laser_timer -= dt
            if self._laser_timer <= 0:
                self._laser_state = "warning"
                self._laser_timer = cfg.laser_warning_seconds
                self._laser_axis_cur = (self.rng.choice(["horizontal", "vertical"])
                                         if cfg.laser_axis == "random" else cfg.laser_axis)
            return

        if self._laser_state == "warning":
            self._laser_timer -= dt
            if self._laser_timer <= 0:
                self._laser_state = "active"
                self._laser_progress = 0.0
                self._laser_hit.clear()
            return

        # active
        self._laser_progress += dt / max(0.01, cfg.laser_sweep_duration)
        if self._laser_progress >= 1.0:
            self._laser_state = "waiting"
            self._laser_timer = self.rng.uniform(cfg.laser_interval_min, cfg.laser_interval_max)
            self._laser_hit.clear()
            return
        thickness = self.w * cfg.laser_thickness_ratio
        pos = self._laser_progress * (self.h if self._laser_axis_cur == "horizontal" else self.w)
        for b in self.active_balls():
            bid = id(b)
            if bid in self._laser_hit:
                continue
            bp = b["shape"].body.position
            coord = bp.y if self._laser_axis_cur == "horizontal" else bp.x
            if abs(coord - pos) <= thickness / 2 + b["radius"]:
                self._laser_hit.add(bid)
                self._eliminate(b, t, "LAZER KESTI", shake=0.2, flash_color=hex_to_rgb(cfg.laser_color))

    def draw_laser(self):
        cfg = self.cfg
        if not cfg.laser_enabled:
            return
        color = hex_to_rgb(cfg.laser_color)
        if self._laser_state == "warning":
            # Uyari: lazerin baslayacagi kenarda yanip sonen ince bir cizgi
            blink_on = int(pygame.time.get_ticks() / 90) % 2 == 0
            c = color if blink_on else (90, 0, 15)
            if self._laser_axis_cur == "horizontal":
                pygame.draw.line(self.screen, c, (0, 2), (self.w, 2), 6)
            else:
                pygame.draw.line(self.screen, c, (2, 0), (2, self.h), 6)
            badge = self._cached_text(self.hud_font, "LAZER GELIYOR", color, outline_px=2)
            self.screen.blit(badge, (self.w // 2 - badge.get_width() // 2, int(self.h * 0.20)))
            return
        if self._laser_state != "active":
            return
        thickness = max(2, int(self.w * cfg.laser_thickness_ratio))
        if self._laser_axis_cur == "horizontal":
            y = int(self._laser_progress * self.h)
            strip = pygame.Surface((self.w, thickness * 6), pygame.SRCALPHA)
            sh = strip.get_height() // 2
            for i in range(sh, 0, -1):
                f = i / sh
                a = max(2, int(90 * (1 - f) ** 1.4))
                pygame.draw.line(strip, (*color, a), (0, sh - i), (self.w, sh - i))
                pygame.draw.line(strip, (*color, a), (0, sh + i), (self.w, sh + i))
            pygame.draw.line(strip, (255, 255, 255), (0, sh), (self.w, sh), max(2, thickness // 2))
            self.screen.blit(strip, (0, y - sh), special_flags=pygame.BLEND_RGBA_ADD)
        else:
            x = int(self._laser_progress * self.w)
            strip = pygame.Surface((thickness * 6, self.h), pygame.SRCALPHA)
            sw = strip.get_width() // 2
            for i in range(sw, 0, -1):
                f = i / sw
                a = max(2, int(90 * (1 - f) ** 1.4))
                pygame.draw.line(strip, (*color, a), (sw - i, 0), (sw - i, self.h))
                pygame.draw.line(strip, (*color, a), (sw + i, 0), (sw + i, self.h))
            pygame.draw.line(strip, (255, 255, 255), (sw, 0), (sw, self.h), max(2, thickness // 2))
            self.screen.blit(strip, (x - sw, 0), special_flags=pygame.BLEND_RGBA_ADD)

    # ------------------------------------------------------------- #
    # Jump Pads
    # ------------------------------------------------------------- #
    def check_jumppads(self, t, dt):
        """Sabit konumlu trambolin pedleri: bir topun merkezi pedin yaricapi +
        topun yaricapi icine girince hizina guclu bir yukari-doğru itki uygulanir.
        Elenme yok, sadece hareket/kaos katar. Her ped kendi cooldown saatini top
        id'sine gore tutar - boylece bir top pedin uzerinde birkac kare boyunca
        kalsa bile (temas suresince) tek bir itki alir, sonraki itki icin
        jumppad_cooldown saniye gecmesi gerekir."""
        cfg = self.cfg
        if not cfg.jumppad_enabled or not self.jumppads:
            return
        for pad in self.jumppads:
            cooldowns = pad["cooldowns"]
            # Suresi dolan cooldown kayitlarini temizle (bellek birikmesin)
            expired = [bid for bid, remaining in cooldowns.items() if remaining - dt <= 0]
            for bid in expired:
                del cooldowns[bid]
            for bid in list(cooldowns.keys()):
                cooldowns[bid] -= dt

            for b in self.active_balls():
                bid = id(b)
                if bid in cooldowns:
                    continue
                bp = b["shape"].body.position
                if math.hypot(bp.x - pad["x"], bp.y - pad["y"]) <= pad["radius"] + b["radius"]:
                    body = b["shape"].body
                    vx, vy = body.velocity
                    # Guclu, sabit bir yukari itki + mevcut yatay hizin bir kismini
                    # koru: "trambolin" hissi verir, topu tamamen durdurup yeniden
                    # firlatmak yerine mevcut yonunu de hafifce tasir.
                    body.velocity = (vx * 0.6, -cfg.jumppad_boost)
                    cooldowns[bid] = cfg.jumppad_cooldown
                    self.flashes.append(EliminationFlash(pad["x"], pad["y"], hex_to_rgb(cfg.jumppad_color)))
                    self._trigger_shake(0.08)

    def draw_jumppads(self):
        cfg = self.cfg
        if not cfg.jumppad_enabled or not self.jumppads:
            return
        color = hex_to_rgb(cfg.jumppad_color)
        pulse = 1.0 + 0.12 * math.sin(pygame.time.get_ticks() * 0.006)
        for pad in self.jumppads:
            r = int(pad["radius"] * pulse)
            draw_glow(self.screen, (pad["x"], pad["y"]), r, color, layers=4, max_alpha=60, spread=2.2)
            draw_aa_circle(self.screen, color, (pad["x"], pad["y"]), r, width=4)
            # Ortada yukari isaret eden kucuk bir ok - "ziplama" niyetini goz gezdirince anlatir
            ax, ay = pad["x"], pad["y"]
            tip = (ax, ay - r * 0.5)
            left = (ax - r * 0.32, ay + r * 0.18)
            right = (ax + r * 0.32, ay + r * 0.18)
            pygame.gfxdraw.filled_trigon(
                self.screen, int(tip[0]), int(tip[1]), int(left[0]), int(left[1]),
                int(right[0]), int(right[1]), (*color, 230))

    def check_carousel(self, t):
        """The Carousel: zamanla daralan guvenli alan disinda kalan top aninda elenir."""
        cfg = self.cfg
        if not cfg.carousel_enabled or self._carousel_center is None:
            return
        active = self.active_balls()
        if len(active) <= cfg.carousel_min_survivors:
            if self._carousel_frozen_size is None:
                self._carousel_frozen_size = self._carousel_current_size(t)
            return
        size = self._carousel_current_size(t)
        cx, cy = self._carousel_center
        for b in active:
            pos = b["shape"].body.position
            dx, dy = pos.x - cx, pos.y - cy
            r = b["radius"]
            if cfg.carousel_shape == "square":
                outside = (abs(dx) - r > size) or (abs(dy) - r > size)
            else:
                outside = (math.hypot(dx, dy) - r) > size
            if outside:
                self._eliminate(b, t, "Guvenli alan disinda kaldi")
                if len(self.active_balls()) <= cfg.carousel_min_survivors:
                    self._carousel_frozen_size = self._carousel_current_size(t)
                    break

    def draw_carousel_zone(self, t):
        cfg = self.cfg
        if not cfg.carousel_enabled or self._carousel_center is None:
            return
        size = self._carousel_current_size(t)
        if cfg.carousel_pulse:
            size *= 1.0 + 0.015 * math.sin(t * 6.0)
        cx, cy = self._carousel_center
        color = hex_to_rgb(cfg.carousel_color)

        # Daire/kare disini karartan overlay: alfa-carpim maskesiyle guvenli alanda "delik" acilir
        mask = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        mask.fill((120, 0, 20, 95))
        hole = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
        hole.fill((255, 255, 255, 255))
        if cfg.carousel_shape == "square":
            rect = pygame.Rect(0, 0, int(size * 2), int(size * 2))
            rect.center = (int(cx), int(cy))
            pygame.draw.rect(hole, (255, 255, 255, 0), rect)
        else:
            pygame.draw.circle(hole, (255, 255, 255, 0), (int(cx), int(cy)), int(size))
        mask.blit(hole, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        self.screen.blit(mask, (0, 0))

        # Sinir cizgisi
        if cfg.carousel_shape == "square":
            rect = pygame.Rect(0, 0, int(size * 2), int(size * 2))
            rect.center = (int(cx), int(cy))
            pygame.draw.rect(self.screen, color, rect, 5)
        else:
            draw_aa_circle(self.screen, color, (cx, cy), size, width=5)

        t_rel = t - cfg.carousel_start_time
        if t_rel < 0:
            label = f"ALAN {int(-t_rel) + 1}SN SONRA DARALIYOR"
            badge = self._cached_text(self.hud_font, label, color, outline_px=2)
            self.screen.blit(badge, (self.w // 2 - badge.get_width() // 2, int(self.h * 0.145)))

    def draw_redlight_overlay(self):
        if not self.cfg.redlight_enabled:
            return
        is_red = self._light_phase == "red"
        if is_red:
            tint = pygame.Surface((self.w, self.h), pygame.SRCALPHA)
            tint.fill((255, 0, 0, 30))
            self.screen.blit(tint, (0, 0))
        badge_color = (255, 60, 60) if is_red else (70, 255, 130)
        badge_label = "DUR!" if is_red else "GIT!"
        badge = self._cached_text(self.hud_font, badge_label, badge_color, outline_px=2)
        self.screen.blit(badge, (self.w - badge.get_width() - int(self.w * 0.04), int(self.h * 0.15)))

    # ------------------------------------------------------------- #
    def _is_race_decided(self):
        """Ters kazanma modunda butun aktif toplar bitirene/elenene kadar kazanan belli olmaz."""
        if not self.finish_order:
            return False
        if self.cfg.reverse_win:
            return len(self.active_balls()) == 0
        return True

    def _get_winner(self):
        if not self.finish_order:
            return None
        return self.finish_order[-1] if self.cfg.reverse_win else self.finish_order[0]

    # ------------------------------------------------------------- #
    # Slow-Mo Finish
    # ------------------------------------------------------------- #
    def update_slowmo_trigger(self):
        """Lider bitis cizgisine yaklasinca bir kereye mahsus slow-mo'yu tetikler.
        Bu kontrol, o karenin fizigini etkileyebilmesi icin space.step'ten ONCE cagrilir,
        bu yuzden bir onceki karenin (henuz guncel) top konumlarini kullanir."""
        cfg = self.cfg
        if not cfg.slowmo_finish_enabled or self._slowmo_triggered:
            return
        active = self.active_balls()
        if not active:
            return
        leader = max(active, key=lambda b: b["shape"].body.position.y)
        if leader["shape"].body.position.y >= self.finish_y * cfg.slowmo_trigger_ratio:
            self._slowmo_triggered = True
            self._slowmo_active = True
            self._slowmo_remaining = cfg.slowmo_duration
            self._slowmo_focus_id = id(leader)

    def _update_slowmo_focus(self):
        if self._slowmo_focus_id is None:
            return
        for b in self.balls:
            if id(b) == self._slowmo_focus_id and not b["eliminated"]:
                pos = b["shape"].body.position
                self._slowmo_focus_pos = (pos.x, pos.y)
                return

    def _update_zoom(self, dt_frame):
        target = self.cfg.slowmo_zoom if self._slowmo_active else 1.0
        self._slowmo_zoom_cur += (target - self._slowmo_zoom_cur) * min(1.0, 4.0 * dt_frame)

    def _apply_zoom(self, surf, zoom):
        focus = self._slowmo_focus_pos or (self.w / 2, self.h * 0.5)
        cw, ch = self.w / zoom, self.h / zoom
        cx = min(max(focus[0] - cw / 2, 0), self.w - cw)
        cy = min(max(focus[1] - ch / 2, 0), self.h - ch)
        rect = pygame.Rect(int(cx), int(cy), max(1, int(cw)), max(1, int(ch)))
        cropped = surf.subsurface(rect).copy()
        return pygame.transform.smoothscale(cropped, (self.w, self.h))

    # ------------------------------------------------------------- #
    def run(self):
        cfg = self.cfg
        safe_substeps = max(1, cfg.substeps)
        dt_physics = 1.0 / cfg.fps / safe_substeps
        dt_frame = 1.0 / cfg.fps
        max_frames = int(cfg.duration_cap * cfg.fps)

        print("Video uretiliyor, lutfen bekleyin...")

        if cfg.show_countdown:
            for label in ("3", "2", "1", "GO!"):
                # Sabit arka plan/toplar bir kere cizilir (fizik henuz baslamadi, top
                # konumlari degismiyor); yalnizca geri sayim metni her karede farkli
                # bir 'progress' degeriyle yeniden cizilerek pop/flash animasyonu elde edilir.
                self.draw_background()
                self.draw_course()
                self.draw_finish_line()
                self.draw_balls()
                base = self.screen.copy()
                hold_frames = max(1, int(cfg.fps * 0.6))
                for i in range(hold_frames):
                    progress = i / max(1, hold_frames - 1)
                    self.screen.blit(base, (0, 0))
                    self.draw_countdown(label, progress)
                    img = self._surface_to_bgr()
                    self.video_writer.write(img)

        frame = 0
        winner_frame = None
        try:
            while frame < max_frames:
                t = frame / cfg.fps

                # Slow-mo tetiklemesi, bu karenin fizigini yavaslatabilmesi icin stepten ONCE kontrol edilir
                self.update_slowmo_trigger()
                physics_dt = dt_physics * cfg.slowmo_factor if self._slowmo_active else dt_physics

                for _ in range(safe_substeps):
                    self.apply_magnet_forces()
                    self.space.step(physics_dt)

                self.check_finishers(t)
                self.check_eliminations(t)
                self.check_redlight(t, dt_frame)
                self.check_boss(t)
                self.check_carousel(t)
                self.check_gravityflip(t, dt_frame)
                self.check_minefield(t, dt_frame)
                self.check_magnet(t, dt_frame)
                self.check_colorgate(t, dt_frame)
                self.check_laser(t, dt_frame)
                self.check_jumppads(t, dt_frame)
                self._update_slowmo_focus()
                self._update_zoom(dt_frame)

                self.draw_background()
                self.draw_course()
                self.draw_finish_line()
                self.draw_boss(t)
                self.draw_minefield()
                self.draw_colorgate()
                self.draw_jumppads()
                self.draw_balls()
                self.draw_carousel_zone(t)
                self.draw_magnet()
                self.draw_laser()
                self.draw_progress_bar()
                self.draw_redlight_overlay()
                self.draw_gravityflip_overlay()
                self.update_and_draw_effects(dt_frame)

                if self._is_race_decided():
                    if winner_frame is None:
                        winner_frame = frame
                        self.spawn_confetti(self._get_winner())
                    self.draw_winner_banner(frame - winner_frame)
                    if (frame - winner_frame) / cfg.fps >= cfg.celebration_seconds:
                        break
                else:
                    self.draw_leaderboard()

                self.draw_watermark()

                bgr = self._surface_to_bgr()
                self.video_writer.write(bgr)
                self._shake_t = max(0.0, self._shake_t - dt_frame)

                if self._slowmo_active:
                    self._slowmo_remaining -= dt_frame
                    if self._slowmo_remaining <= 0:
                        self._slowmo_active = False

                # Kazanin acilmasindan ~0.5 saniye sonraki kareyi YT Shorts kapak gorseli olarak kaydet
                if winner_frame is not None and frame - winner_frame == int(cfg.fps * 0.5):
                    thumb_path = os.path.splitext(cfg.output)[0] + "_thumbnail.jpg"
                    cv2.imwrite(thumb_path, bgr)

                if frame % 100 == 0:
                    print(f"Ilerleme: %{int((frame / max_frames) * 100)}")
                frame += 1
        finally:
            self.video_writer.release()
            pygame.quit()

        self._finalize_ranking()
        self._attach_music_if_any()

        if self.finish_order:
            final_winner = self.finish_order[-1] if cfg.reverse_win else self.finish_order[0]
            print(f"Basariyla tamamlandi! Kazanan: {final_winner['name']}")
        elif self.eliminated_order and len(self.eliminated_order) == len(self.balls):
            print("Tum toplar elendi, kazanan yok!")
        else:
            print("Sure doldu, kimse bitiremedi.")
        print("Final siralama:", [b["name"] for b in self._full_ranking()])
        print(f"Video: {os.path.abspath(cfg.output)}")

    def _surface_to_bgr(self):
        surf = self.screen
        if self._shake_t > 0:
            # Sabit genlikte ani zipla-dur yerine, kalan sureye gore karesel sonumlenen
            # (ease-out) bir genlik kullaniyoruz - darbe hala sert hissettiriyor ama
            # cikisi pürüzlu degil, yumusak/sinematik bir "titreme sonumu" gibi bitiyor.
            decay = max(0.0, self._shake_t / self._shake_max)
            amp = 10 * (decay ** 1.5)
            dx = int(self.rng.uniform(-amp, amp))
            dy = int(self.rng.uniform(-amp, amp))
            shaken = pygame.Surface((self.w, self.h))
            shaken.blit(surf, (dx, dy))
            surf = shaken
        if self._slowmo_zoom_cur > 1.01:
            surf = self._apply_zoom(surf, self._slowmo_zoom_cur)
        img = pygame.surfarray.array3d(surf).transpose([1, 0, 2])

        # Slow-mo yakinlastirmasi aktifken hafif bir kromatik aberasyon (kirmizi/mavi
        # kanallarin yatayda zitt yonde kaymasi): yuksek hizli kamera/sinema lensi
        # hissi verir, zoom orani arttikca etkisi de orantili olarak guclenir.
        zoom_amt = self._slowmo_zoom_cur - 1.0
        if zoom_amt > 0.08:
            shift = min(3, max(1, int(round(zoom_amt * 4))))
            # %100 sert kanal degisimi yerine orijinal ile harmanlanmis (yaklasik %45
            # karisim) hafif bir kayma: yuksek kontrastli kenarlarda (metin, damali
            # bitis cizgisi) abartili "glitch" gorunumu yerine ince/zarif bir sinema
            # lensi hissi birakir.
            blend = min(0.45, zoom_amt * 1.1)
            ca = img.astype(np.int16)
            shifted_r = ca.copy()
            shifted_r[:, shift:, 0] = ca[:, :-shift, 0]
            shifted_b = ca.copy()
            shifted_b[:, :-shift, 2] = ca[:, shift:, 2]
            out = ca.copy()
            out[..., 0] = ca[..., 0] * (1 - blend) + shifted_r[..., 0] * blend
            out[..., 2] = ca[..., 2] * (1 - blend) + shifted_b[..., 2] * blend
            img = np.clip(out, 0, 255).astype(np.uint8)

        return cv2.cvtColor(img, cv2.COLOR_RGB2BGR)

    def _full_ranking(self):
        return self.finish_order + list(reversed(self.eliminated_order))

    def _finalize_ranking(self):
        leftover = [b for b in self.balls if not b["finished"] and not b["eliminated"]]
        leftover.sort(key=lambda b: -b["shape"].body.position.y)
        self.finish_order += leftover

    def _attach_music_if_any(self):
        cfg = self.cfg
        if not cfg.music_path:
            return
        try:
            from moviepy.editor import VideoFileClip, AudioFileClip, afx
        except ImportError:
            print("Not: moviepy kurulu degil, muzik eklenmedi (pip install moviepy).")
            os.replace(self._raw_output, cfg.output)
            return
        if not os.path.exists(cfg.music_path):
            print(f"Not: muzik dosyasi bulunamadi: {cfg.music_path}")
            os.replace(self._raw_output, cfg.output)
            return
        try:
            video = VideoFileClip(self._raw_output)
            audio = AudioFileClip(cfg.music_path).fx(afx.audio_loop, duration=video.duration)
            video = video.set_audio(audio)
            video.write_videofile(cfg.output, codec="libx264", audio_codec="aac", logger=None)
            video.close()
            audio.close()
            os.remove(self._raw_output)
        except Exception as exc:
            print(f"Muzik eklenemedi ({exc}); muziksiz video kullanilacak.")
            os.replace(self._raw_output, cfg.output)


# ===================================================================== #
# CLI
# ===================================================================== #

def build_arg_parser():
    p = argparse.ArgumentParser(
        description="Satisfying ball race - YouTube Shorts video uretici",
        formatter_class=argparse.ArgumentDefaultsHelpFormatter,
    )
    p.add_argument("--config", type=str, help="JSON config dosyasindan ayarlari yukle")
    p.add_argument("--save-config", type=str, help="Guncel ayarlari bu JSON dosyasina kaydet ve cik")
    p.add_argument("--list-presets", action="store_true", help="Parkur tiplerini ve paletleri listele")

    p.add_argument("--num-balls", type=int)
    p.add_argument("--course", choices=list(COURSES.keys()), dest="course_type")
    p.add_argument("--palette", choices=list(PALETTES.keys()) + ["rainbow", "custom"])
    p.add_argument("--custom-colors", type=str, help="Virgulle ayrilmis hex renkler: #FF0000,#00FF00")
    p.add_argument("--faces", type=str,
                    help="Virgulle ayrilmis yerel resim dosyalari, toplarin ortasina yuvarlak kirpilarak yerlesir: "
                         "foto1.jpg,foto2.png,... (yetersizse basa donup tekrar eder)")
    p.add_argument("--face-names", type=str,
                    help="Yuzlerle birlikte gosterilecek isimler, virgulle ayrilmis (sirasi --faces ile eslesmeli)")
    p.add_argument("--face-scale", type=float,
                    help="Yuz resminin top capina orani (varsayilan 1.0, kucultmek icin 0.8 gibi bir deger ver)")
    p.add_argument("--duration", type=float, dest="duration_cap")
    p.add_argument("--celebration", type=float, dest="celebration_seconds")
    p.add_argument("--seed", type=int)
    p.add_argument("--output", type=str)
    p.add_argument("--width", type=int)
    p.add_argument("--height", type=int)
    p.add_argument("--fps", type=int)
    p.add_argument("--title", type=str, dest="title_text")
    p.add_argument("--auto-title", action="store_true",
                    help="title_text'i viral baslik havuzundan rastgele sec (her batch videosu icin farkli)")
    p.add_argument("--subtitle", type=str, dest="subtitle_text")
    p.add_argument("--watermark", type=str, dest="watermark_text")
    p.add_argument("--music", type=str, dest="music_path", help="Dogrudan bir muzik dosyasi yolu (moviepy gerekir)")
    p.add_argument("--music-dir", type=str, dest="music_dir",
                    help="Muzik dosyalarinin bulundugu klasor (mp3/wav/m4a/ogg/flac)")
    p.add_argument("--music-name", type=str, dest="music_name",
                    help="--music-dir icinde bu isme (kismi, harf duyarsiz) uyan parcayi sec")
    p.add_argument("--music-random", action="store_true",
                    help="--music-dir icinden rastgele parca sec (batch'te her video icin farkli)")
    p.add_argument("--list-music", action="store_true",
                    help="--music-dir icindeki muzik dosyalarini listele ve cik")
    p.add_argument("--no-countdown", action="store_false", dest="show_countdown")
    p.add_argument("--no-leaderboard", action="store_false", dest="show_leaderboard")
    p.add_argument("--no-confetti", action="store_false", dest="confetti_enabled")
    p.add_argument("--no-glow", action="store_false", dest="glow")

    # Oyun modlari (birbiriyle kombinlenebilir, orn: --elimination --redlight ayni videoda)
    p.add_argument("--elimination", action="store_true", dest="elimination_enabled",
                    help="Sudden-death: periyodik olarak en geride kalan(lar) elenir")
    p.add_argument("--elimination-interval", type=float, dest="elimination_interval_seconds")
    p.add_argument("--eliminate-per-round", type=int)
    p.add_argument("--min-survivors", type=int)
    p.add_argument("--redlight", action="store_true", dest="redlight_enabled",
                    help="Red Light Green Light: kirmizida hareket halinde yakalanan elenir")
    p.add_argument("--redlight-threshold", type=float, dest="redlight_speed_threshold",
                    help="Kirmizida elenmeden once izin verilen maksimum hiz")
    p.add_argument("--redlight-eliminate-per-round", type=int,
                    help="Her kirmizi isikta en hizli hareket eden kac top elenir (varsayilan 1)")
    p.add_argument("--boss", action="store_true", dest="boss_enabled",
                    help="Boss Race: belli bir sureden sonra gezinen bir engel belirir, degen top elenir")
    p.add_argument("--boss-spawn-time", type=float, dest="boss_spawn_time",
                    help="Boss'un kac saniye sonra belirecegi")
    p.add_argument("--reverse-win", action="store_true", dest="reverse_win",
                    help="Ters kazanma: ilk degil EN SON bitiren top kazanir")
    p.add_argument("--carousel", action="store_true", dest="carousel_enabled",
                    help="The Carousel: zamanla daralan guvenli alan (daire/kare) - disinda kalan top aninda elenir")
    p.add_argument("--carousel-shape", choices=["circle", "square"], dest="carousel_shape",
                    help="Guvenli alanin sekli (varsayilan: circle)")
    p.add_argument("--carousel-start", type=float, dest="carousel_start_time",
                    help="Daralmanin kac saniye sonra baslayacagi")
    p.add_argument("--carousel-duration", type=float, dest="carousel_shrink_duration",
                    help="Tam boyuttan minimuma daralma suresi (saniye)")
    p.add_argument("--carousel-min-size", type=float, dest="carousel_min_size_ratio",
                    help="Min guvenli alan boyutu, ekran genisligine oran (0-1)")
    p.add_argument("--carousel-min-survivors", type=int, dest="carousel_min_survivors",
                    help="Daralma bu sayida top kalinca durur")
    p.add_argument("--carousel-color", type=str, dest="carousel_color")

    p.add_argument("--gravity-flip", action="store_true", dest="gravityflip_enabled",
                    help="Gravity Flip: rastgele araliklarla yercekimi aniden ters doner")
    p.add_argument("--gravity-flip-interval-min", type=float, dest="gravityflip_interval_min")
    p.add_argument("--gravity-flip-interval-max", type=float, dest="gravityflip_interval_max")

    p.add_argument("--minefield", action="store_true", dest="minefield_enabled",
                    help="Minefield: parkurda rastgele gizli minler belirir, deyen top elenir")
    p.add_argument("--minefield-interval-min", type=float, dest="minefield_interval_min")
    p.add_argument("--minefield-interval-max", type=float, dest="minefield_interval_max")
    p.add_argument("--minefield-max-active", type=int, dest="minefield_max_active")
    p.add_argument("--minefield-warning", type=float, dest="minefield_warning_seconds",
                    help="Mina armed olmadan once yanip sonme suresi (sn)")

    p.add_argument("--magnet", action="store_true", dest="magnet_enabled",
                    help="Magnet Pulse: periyodik olarak ekranda bir nokta toplari ceker/iter")
    p.add_argument("--magnet-interval-min", type=float, dest="magnet_interval_min")
    p.add_argument("--magnet-interval-max", type=float, dest="magnet_interval_max")
    p.add_argument("--magnet-duration", type=float, dest="magnet_duration")
    p.add_argument("--magnet-strength", type=float, dest="magnet_strength")
    p.add_argument("--magnet-mode", choices=["attract", "repel", "random"], dest="magnet_mode")

    p.add_argument("--color-gate", action="store_true", dest="colorgate_enabled",
                    help="Color Gate: periyodik kapi cizgileri belirir, sadece istenen renk gecebilir")
    p.add_argument("--color-gate-interval-min", type=float, dest="colorgate_interval_min")
    p.add_argument("--color-gate-interval-max", type=float, dest="colorgate_interval_max")

    p.add_argument("--golden-ball", action="store_true", dest="goldenball_enabled",
                    help="Golden Ball: rastgele bir top 'altin' secilir, kazanirsa extra kutlama")

    p.add_argument("--laser", action="store_true", dest="laser_enabled",
                    help="Laser Sweep: periyodik olarak ekrani bastan basa tarayan bir lazer belirir, degen top elenir")
    p.add_argument("--laser-axis", choices=["horizontal", "vertical", "random"], dest="laser_axis",
                    help="Lazerin tarama ekseni (varsayilan: random)")
    p.add_argument("--laser-interval-min", type=float, dest="laser_interval_min")
    p.add_argument("--laser-interval-max", type=float, dest="laser_interval_max")
    p.add_argument("--laser-sweep-duration", type=float, dest="laser_sweep_duration",
                    help="Lazerin ekrani bastan basa gecme suresi (sn)")
    p.add_argument("--laser-warning", type=float, dest="laser_warning_seconds",
                    help="Lazer aktif olmadan once uyari suresi (sn)")
    p.add_argument("--laser-color", type=str, dest="laser_color")

    p.add_argument("--jump-pads", action="store_true", dest="jumppad_enabled",
                    help="Jump Pads: parkurda sabit trambolin pedler belirir, degen topa guclu bir itki uygulanir")
    p.add_argument("--jump-pads-count", type=int, dest="jumppad_count")
    p.add_argument("--jump-pads-boost", type=float, dest="jumppad_boost",
                    help="Pedin topa verdigi yukari itki buyuklugu")
    p.add_argument("--jump-pads-color", type=str, dest="jumppad_color")

    p.add_argument("--no-slowmo", action="store_false", dest="slowmo_finish_enabled",
                    help="Slow-Mo Finish efektini kapat (varsayilan: acik)")
    p.add_argument("--slowmo-trigger", type=float, dest="slowmo_trigger_ratio",
                    help="Lider finish_y'nin yuzde kacina ulasinca slow-mo tetiklenir (0-1)")
    p.add_argument("--slowmo-duration", type=float, dest="slowmo_duration")
    p.add_argument("--slowmo-factor", type=float, dest="slowmo_factor", help="Fizik hizi carpani (kucuk=yavas)")
    p.add_argument("--slowmo-zoom", type=float, dest="slowmo_zoom")

    p.add_argument("--set", action="append", default=[], metavar="KEY=VALUE",
                    help="Herhangi bir Config alanini serbestce ayarla, orn: --set trail_length=25")
    p.add_argument("--batch", type=int, default=1, help="Kac farkli video uretilsin (seed'ler otomatik artar)")
    p.add_argument("--vary-course", action="store_true",
                    help="Batch'teki her video farkli parkur tipini sirayla kullansin")
    p.add_argument("--vary-palette", action="store_true",
                    help="Batch'teki her video farkli renk paletini sirayla kullansin")
    p.add_argument("--parallel", action="store_true", dest="parallel_batch",
                    help="--batch > 1 iken videolari ayri processlerde paralel uret (coklu cekirdek kullanir)")
    p.add_argument("--max-workers", type=int, dest="max_workers",
                    help="--parallel ile ayni anda calisacak maksimum process sayisi (varsayilan: CPU sayisi)")
    return p


def apply_cli_overrides(cfg: Config, args):
    for f in dataclasses.fields(cfg):
        val = getattr(args, f.name, None)
        if val is not None:
            setattr(cfg, f.name, val)

    if args.custom_colors:
        cfg.custom_colors = [c.strip() for c in args.custom_colors.split(",")]
        cfg.palette = "custom"

    if args.faces:
        cfg.face_images = [p.strip() for p in args.faces.split(",") if p.strip()]
        missing = [p for p in cfg.face_images if not os.path.isfile(p)]
        if missing:
            print(f"Uyari: su yuz resmi dosyalari bulunamadi, atlanacak: {', '.join(missing)}")

    if args.face_names:
        cfg.face_names = [n.strip() for n in args.face_names.split(",") if n.strip()]

    for item in args.set:
        if "=" not in item:
            print(f"Uyari: gecersiz --set '{item}', atlandi (KEY=VALUE bekleniyor).")
            continue
        key, raw_val = item.split("=", 1)
        if not hasattr(cfg, key):
            print(f"Uyari: bilinmeyen alan '{key}', atlandi.")
            continue
        try:
            val = ast.literal_eval(raw_val)
        except Exception:
            val = raw_val
        setattr(cfg, key, val)
    return cfg


MUSIC_EXTENSIONS = (".mp3", ".wav", ".m4a", ".ogg", ".flac")


def scan_music_dir(music_dir):
    """music_dir icindeki desteklenen ses dosyalarini isme gore sirali dondurur."""
    if not music_dir or not os.path.isdir(music_dir):
        return []
    return sorted(f for f in os.listdir(music_dir) if f.lower().endswith(MUSIC_EXTENSIONS))


def print_presets():
    print("Parkur tipleri:", ", ".join(COURSES.keys()))
    print("Renk paletleri:", ", ".join(list(PALETTES.keys()) + ["rainbow", "custom"]))
    print("Oyun modlari (kombinlenebilir): --elimination, --redlight, --boss, --reverse-win, --carousel, "
          "--gravity-flip, --minefield, --magnet, --color-gate, --golden-ball, --laser, --jump-pads")
    print("Efektler: --no-slowmo (Slow-Mo Finish varsayilan acik, kapatmak icin kullan)")


def _produce_video(run_cfg, index, total):
    """Tek bir videoyu uretir (simulasyon + meta JSON). --batch > 1 durumunda bu
    fonksiyon sirayla ya da (--parallel ile) ProcessPoolExecutor uzerinden ayri
    processlerde cagrilir; bu yuzden picklable olmasi icin modul seviyesinde
    tanimlanmistir (main() icine nested bir fonksiyon ProcessPoolExecutor ile
    calismaz, cunku pickle edilemez)."""
    music_label = os.path.basename(run_cfg.music_path) if run_cfg.music_path else "yok"
    print(f"\n=== Video {index + 1}/{total}: {run_cfg.output} "
          f"(baslik: \"{run_cfg.title_text}\", parkur: {run_cfg.course_type}, "
          f"palet: {run_cfg.palette}, muzik: {music_label}) ===")
    try:
        sim = BallRaceSimulation(run_cfg)
        sim.run()
        winner_ball = sim._get_winner()
        meta = {
            "output": os.path.abspath(run_cfg.output),
            "title_text": run_cfg.title_text,
            "course_type": run_cfg.course_type,
            "palette": run_cfg.palette,
            "num_balls": run_cfg.num_balls,
            "seed": run_cfg.seed,
            "music": os.path.basename(run_cfg.music_path) if run_cfg.music_path else None,
            "game_modes": {
                "elimination": run_cfg.elimination_enabled,
                "redlight": run_cfg.redlight_enabled,
                "boss": run_cfg.boss_enabled,
                "reverse_win": run_cfg.reverse_win,
                "carousel": run_cfg.carousel_enabled,
                "gravity_flip": run_cfg.gravityflip_enabled,
                "minefield": run_cfg.minefield_enabled,
                "magnet": run_cfg.magnet_enabled,
                "color_gate": run_cfg.colorgate_enabled,
                "golden_ball": run_cfg.goldenball_enabled,
                "jump_pads": run_cfg.jumppad_enabled,
                "laser": run_cfg.laser_enabled,
                "slowmo_finish": run_cfg.slowmo_finish_enabled,
            },
            "winner": winner_ball["name"] if winner_ball else None,
            "ranking": [b["name"] for b in sim._full_ranking()],
        }
        meta_path = os.path.splitext(run_cfg.output)[0] + "_meta.json"
        with open(meta_path, "w", encoding="utf-8") as fh:
            json.dump(meta, fh, ensure_ascii=False, indent=2)
        return {"ok": True, "output": run_cfg.output, "winner": meta["winner"], "error": None}
    except Exception as exc:
        print(f"Hata: {exc}", file=sys.stderr)
        return {"ok": False, "output": run_cfg.output, "winner": None, "error": str(exc)}


def main():
    args = build_arg_parser().parse_args()

    if args.list_presets:
        print_presets()
        return

    cfg = Config()
    if args.config:
        with open(args.config, "r", encoding="utf-8") as fh:
            cfg = Config.from_dict(json.load(fh))
    cfg = apply_cli_overrides(cfg, args)

    if args.list_music:
        files = scan_music_dir(cfg.music_dir)
        if not files:
            print(f"'{cfg.music_dir}' klasorunde desteklenen ses dosyasi bulunamadi "
                  f"({', '.join(MUSIC_EXTENSIONS)}).")
        else:
            print(f"'{cfg.music_dir}' klasorundeki muzik parcalari:")
            for f in files:
                print(" -", os.path.splitext(f)[0])
        return

    if args.save_config:
        with open(args.save_config, "w", encoding="utf-8") as fh:
            json.dump(cfg.to_dict(), fh, ensure_ascii=False, indent=2)
        print(f"Config kaydedildi: {args.save_config}")
        return

    base_output = cfg.output
    base_seed = cfg.seed

    # Batch genelinde paylasilan rotasyon havuzlari: eskiden --auto-title /
    # --music-random her video icin BAGIMSIZ bir rastgele secim yapiyordu (ayni
    # baslik/muzik art arda veya ayni batch icinde defalarca cikabiliyordu). Simdi
    # tum batch suresince paylasilan tek bir NoRepeatPool kullanilir: havuz tukenene
    # kadar tekrar yok, tukenince yeniden karisir. Tekrarlanabilirlik icin pool'u
    # besleyen rng, base_seed varsa ondan turetilir.
    pool_seed = (base_seed + 999_000) if base_seed is not None else random.randint(0, 999_999)
    pool_rng = random.Random(pool_seed)
    title_pool = NoRepeatPool(AUTO_TITLES, pool_rng) if args.auto_title else None
    music_pool = None  # ilk kez muzik dosyalari taranince, o listeyle kurulacak

    # 1) Hazirlik: her video icin tam bir Config uret (isimlendirme, seed, baslik,
    # parkur/palet varyasyonu, muzik secimi) - fiili uretim (pahali/paralellenebilir
    # kisim) asagida ayri bir asamada yapiliyor.
    run_cfgs = []
    for i in range(args.batch):
        run_cfg = copy.deepcopy(cfg)
        if args.batch > 1:
            name, ext = os.path.splitext(base_output)
            run_cfg.output = f"{name}_{i + 1}{ext or '.mp4'}"
            run_cfg.seed = (base_seed + i) if base_seed is not None else None
        if title_pool is not None:
            run_cfg.title_text = title_pool.next()
        if args.vary_course:
            course_names = list(COURSES.keys())
            run_cfg.course_type = course_names[i % len(course_names)]
        if args.vary_palette:
            palette_names = list(PALETTES.keys()) + ["rainbow"]
            run_cfg.palette = palette_names[i % len(palette_names)]

        if not run_cfg.music_path and run_cfg.music_dir:
            music_files = scan_music_dir(run_cfg.music_dir)
            if not music_files:
                print(f"Uyari: '{run_cfg.music_dir}' icinde muzik dosyasi bulunamadi, muziksiz devam.")
            elif run_cfg.music_name:
                matches = [f for f in music_files if run_cfg.music_name.lower() in f.lower()]
                if matches:
                    run_cfg.music_path = os.path.join(run_cfg.music_dir, matches[0])
                else:
                    print(f"Uyari: '{run_cfg.music_name}' ile eslesen muzik bulunamadi, muziksiz devam.")
            elif args.music_random:
                if music_pool is None:
                    music_pool = NoRepeatPool(music_files, pool_rng)
                run_cfg.music_path = os.path.join(run_cfg.music_dir, music_pool.next())

        run_cfgs.append(run_cfg)

    total = len(run_cfgs)
    any_failed = False

    # 2) Uretim: varsayilan sirayla (eski davranis, degismedi); --parallel ve
    # birden fazla video varsa her biri ayri bir process'te (CPU-bound pygame/
    # pymunk/opencv isi oldugundan threading degil multiprocessing kullanilir).
    if args.parallel_batch and total > 1:
        max_workers = args.max_workers or min(total, os.cpu_count() or 1)
        print(f"\n{total} video, {max_workers} paralel process ile uretiliyor...")
        results = [None] * total
        with concurrent.futures.ProcessPoolExecutor(max_workers=max_workers) as executor:
            future_map = {executor.submit(_produce_video, rc, i, total): i
                          for i, rc in enumerate(run_cfgs)}
            for future in concurrent.futures.as_completed(future_map):
                idx = future_map[future]
                try:
                    results[idx] = future.result()
                except Exception as exc:
                    print(f"Hata (video {idx + 1}): {exc}", file=sys.stderr)
                    results[idx] = {"ok": False, "output": run_cfgs[idx].output, "error": str(exc)}
        any_failed = any(r is None or not r.get("ok") for r in results)
    else:
        for i, run_cfg in enumerate(run_cfgs):
            result = _produce_video(run_cfg, i, total)
            if not result["ok"]:
                any_failed = True

    if any_failed and total == 1:
        sys.exit(1)


if __name__ == "__main__":
    main()
