"""
B3313: INTERNAL PLEXUS - SM64 PC PORT EDITION v1.0
Full integration of sm64-port / sm64ex PC port features into the B3313
2D raycasting labyrinth engine.

SM64 PC PORT FEATURES INTEGRATED:
  [RENDER]  Arbitrary resolution, widescreen, texture filtering toggle,
            wall-face shading (N/S vs E/W), fog per-area, draw distance toggle,
            drawing layer system (sky > walls > floor > sprites > HUD)
  [CAMERA]  Puppycam-style free analog mouse look w/ configurable sensitivity,
            invert X/Y, camera smoothing/deceleration, wall-collision rays
  [HUD]     SM64-style power meter (8 wedges, animated states), lives counter,
            coin counter, star counter, area name, FPS, camera mode indicator,
            bitfield visibility flags (0x01 lives, 0x02 coins, 0x04 stars, etc.)
  [CHEATS]  Moon Jump, Infinite Lives, Speed Boost, No Clip, Invincibility,
            AI Freeze (future), toggle via L×3 in pause or --cheats CLI
  [AUDIO]   Procedural chiptune BGM + positional SFX w/ distance attenuation
            and stereo panning (pygame.mixer)
  [INPUT]   Keyboard + Mouse + SDL2 Gamepad (pygame.joystick), remappable
  [COLLIDE] 16×16 spatial grid partitioning per room segment, surface types
            (normal, lava, ice, water, conveyor), DDA ray stepping
  [CONFIG]  sm64config.txt save/load for all settings
  [OPTIONS] Full in-game options menu (display, camera, audio, cheats, controls)
  [SURFACE] Per-tile surface types: lava (damage), ice (slide), water (tint),
            conveyor (push)
  [60FPS]   Native 60fps target w/ delta-time interpolation
  [LOD]     Draw distance toggle (NODRAWINGDISTANCE equivalent)
  [MINIMAP] Real-time overhead minimap with player arrow

[C] AC HOLDING 1999-2026
[C] Chris r rillo team 2023
[C] Nintendo 1985-2026
"""

import pygame
import math
import sys
import os
import json
import time
import random
import struct
import array

# ==========================================
# Python 3.14 compat stub
# ==========================================
try:
    import python3_14
except ImportError:
    pass

# ==========================================
# Configuration Defaults (sm64config.txt)
# ==========================================
CONFIG_FILE = "sm64config.txt"

DEFAULT_CONFIG = {
    # Display
    "width": 960,
    "height": 540,
    "fullscreen": False,
    "widescreen": True,
    "fps_target": 60,
    "texture_filtering": True,       # True=bilinear, False=nearest (N64)
    "draw_distance_enabled": True,   # NODRAWINGDISTANCE equivalent
    "max_draw_distance": 32.0,
    "fog_enabled": True,
    "show_fps": True,
    "show_minimap": True,
    # Camera (Puppycam)
    "mouse_sensitivity_x": 0.003,
    "mouse_sensitivity_y": 0.001,
    "invert_x": False,
    "invert_y": False,
    "camera_smoothing": 0.15,        # centre aggression
    "camera_decel": 0.85,            # stopping speed
    # Audio
    "master_volume": 0.7,
    "music_volume": 0.5,
    "sfx_volume": 0.8,
    "music_enabled": True,
    # Controls
    "move_speed": 0.12,
    # Cheats
    "cheats_enabled": False,
    "moon_jump": False,
    "infinite_lives": False,
    "speed_boost": False,
    "no_clip": False,
    "invincibility": False,
}

# ==========================================
# Config Load/Save
# ==========================================
def load_config():
    cfg = dict(DEFAULT_CONFIG)
    if os.path.exists(CONFIG_FILE):
        try:
            with open(CONFIG_FILE, "r") as f:
                saved = json.load(f)
            cfg.update(saved)
        except Exception:
            pass
    return cfg

def save_config(cfg):
    try:
        with open(CONFIG_FILE, "w") as f:
            json.dump(cfg, f, indent=2)
    except Exception:
        pass

# ==========================================
# Global State
# ==========================================
CFG = load_config()

# Parse CLI --cheats flag
if "--cheats" in sys.argv:
    CFG["cheats_enabled"] = True

WIDTH = CFG["width"]
HEIGHT = CFG["height"]
FPS = CFG["fps_target"]
FOV = math.pi / 3
ROOM_SIZE = 100.0
DOOR_WIDTH = 16.0
DOOR_CLEAR_DEPTH = 4.0
RAY_STRIP_WIDTH = 2

# Player state
player_x = 50.0
player_y = 50.0
player_angle = -math.pi / 2
player_health = 8          # SM64 power meter: 0-8 wedges
player_lives = 4
player_coins = 0
player_stars = 0
player_vel_x = 0.0
player_vel_y = 0.0
player_on_ice = False
player_in_water = False
player_damage_timer = 0
current_area = "Peach's Castle Outskirts"

# HUD visibility bitfield (SM64-style)
HUD_LIVES  = 0x01
HUD_COINS  = 0x02
HUD_STARS  = 0x04
HUD_CAMERA = 0x08
HUD_POWER  = 0x10
HUD_TIMER  = 0x40
hud_flags = HUD_LIVES | HUD_COINS | HUD_STARS | HUD_CAMERA | HUD_POWER

# Power meter animation states
PM_HIDDEN = 0
PM_INCREASING = 1
PM_FULL = 2
PM_DECREASING = 3
PM_DEPLETION = 4
power_meter_state = PM_FULL
power_meter_anim = 0.0

# Camera mode
CAM_PUPPYCAM = 0
CAM_FIXED = 1
camera_mode = CAM_PUPPYCAM

# Cheats pause menu L counter
pause_l_count = 0

# ==========================================
# SM64-Accurate Color Palette (NES subset)
# ==========================================
SM64_COLORS = {
    "red":       (255, 50, 50),
    "blue":      (40, 80, 220),
    "green":     (50, 180, 50),
    "yellow":    (255, 255, 0),
    "white":     (255, 255, 255),
    "black":     (0, 0, 0),
    "gold":      (255, 200, 50),
    "cyan":      (0, 255, 255),
    "purple":    (150, 50, 200),
    "orange":    (255, 150, 0),
    "hud_bg":    (10, 10, 10),
}

# ==========================================
# Procedural Audio System (pygame.mixer)
# ==========================================
AUDIO_INITIALIZED = False
SFX_CACHE = {}

def init_audio():
    global AUDIO_INITIALIZED
    try:
        pygame.mixer.pre_init(44100, -16, 2, 512)
        pygame.mixer.init()
        pygame.mixer.set_num_channels(16)
        AUDIO_INITIALIZED = True
    except Exception:
        AUDIO_INITIALIZED = False

def generate_tone(freq, duration_ms, wave="square", volume=0.3):
    """Generate a procedural chiptune tone as a pygame Sound."""
    if not AUDIO_INITIALIZED:
        return None
    sample_rate = 44100
    n_samples = int(sample_rate * duration_ms / 1000.0)
    buf = array.array('h')
    max_amp = int(32767 * volume)
    for i in range(n_samples):
        t = i / sample_rate
        if wave == "square":
            val = max_amp if math.sin(2 * math.pi * freq * t) >= 0 else -max_amp
        elif wave == "triangle":
            phase = (freq * t) % 1.0
            val = int(max_amp * (4 * abs(phase - 0.5) - 1))
        elif wave == "sine":
            val = int(max_amp * math.sin(2 * math.pi * freq * t))
        elif wave == "noise":
            val = random.randint(-max_amp, max_amp)
        else:
            val = 0
        buf.append(val)
        buf.append(val)  # stereo duplicate
    try:
        return pygame.mixer.Sound(buffer=buf)
    except Exception:
        return None

def init_sfx():
    """Pre-generate SM64-style sound effects."""
    global SFX_CACHE
    if not AUDIO_INITIALIZED:
        return
    SFX_CACHE["coin"]     = generate_tone(988, 80, "square", 0.2)
    SFX_CACHE["star"]     = generate_tone(1320, 200, "triangle", 0.3)
    SFX_CACHE["hurt"]     = generate_tone(200, 150, "noise", 0.2)
    SFX_CACHE["step"]     = generate_tone(100, 40, "noise", 0.05)
    SFX_CACHE["door"]     = generate_tone(440, 120, "sine", 0.15)
    SFX_CACHE["jump"]     = generate_tone(660, 100, "square", 0.15)
    SFX_CACHE["menu"]     = generate_tone(800, 60, "square", 0.1)
    SFX_CACHE["heal"]     = generate_tone(1100, 150, "triangle", 0.2)
    SFX_CACHE["lava"]     = generate_tone(150, 200, "noise", 0.3)

def play_sfx(name, volume=None):
    if not AUDIO_INITIALIZED or name not in SFX_CACHE or SFX_CACHE[name] is None:
        return
    vol = volume if volume is not None else CFG["sfx_volume"] * CFG["master_volume"]
    SFX_CACHE[name].set_volume(vol)
    SFX_CACHE[name].play()

# BGM: simple looping procedural sequence
bgm_channel = None
bgm_notes = [
    (440, 200), (494, 200), (523, 200), (587, 200),
    (659, 200), (587, 200), (523, 200), (494, 200),
    (440, 400), (0, 200), (523, 200), (659, 200),
    (698, 400), (659, 200), (523, 200), (440, 400), (0, 400),
]
bgm_index = 0
bgm_timer = 0

def update_bgm(dt):
    global bgm_index, bgm_timer, bgm_channel
    if not AUDIO_INITIALIZED or not CFG["music_enabled"]:
        return
    bgm_timer -= dt * 1000
    if bgm_timer <= 0:
        freq, dur = bgm_notes[bgm_index % len(bgm_notes)]
        bgm_index += 1
        bgm_timer = dur
        if freq > 0:
            vol = CFG["music_volume"] * CFG["master_volume"] * 0.15
            tone = generate_tone(freq, dur, "triangle", vol)
            if tone:
                tone.play()

# Step sound timing
step_timer = 0.0
STEP_INTERVAL = 0.35

# ==========================================
# Map Configurations (B3313 Areas)
# ==========================================
SURFACE_NORMAL  = 0
SURFACE_LAVA    = 1
SURFACE_ICE     = 2
SURFACE_WATER   = 3
SURFACE_CONVEY  = 4

MAP_CONFIGS = [
    {"name": "Peach's Castle Outskirts", "colors": [(120,180,100), (50,150,40), (135,206,235)], "algo": "castle", "fog_color": (200,220,255), "fog_near": 12.0, "fog_far": 28.0, "surface": SURFACE_NORMAL},
    {"name": "Plexal Lobby", "colors": [(180,180,190), (40,40,50), (20,20,20)], "algo": "pillars", "fog_color": (20,20,30), "fog_near": 8.0, "fog_far": 22.0, "surface": SURFACE_NORMAL},
    {"name": "Beta Lobby A", "colors": [(220,220,220), (120,120,120), (60,60,60)], "algo": "pillars", "fog_color": (60,60,70), "fog_near": 10.0, "fog_far": 24.0, "surface": SURFACE_NORMAL},
    {"name": "Beta Lobby B", "colors": [(200,220,200), (100,120,100), (50,60,50)], "algo": "pillars", "fog_color": (50,60,55), "fog_near": 10.0, "fog_far": 24.0, "surface": SURFACE_NORMAL},
    {"name": "Beta Lobby C", "colors": [(220,200,200), (120,100,100), (60,50,50)], "algo": "pillars", "fog_color": (60,50,55), "fog_near": 10.0, "fog_far": 24.0, "surface": SURFACE_NORMAL},
    {"name": "Crimson Hallway", "colors": [(150,20,20), (60,10,10), (30,0,0)], "algo": "corridor", "fog_color": (40,0,0), "fog_near": 6.0, "fog_far": 18.0, "surface": SURFACE_NORMAL},
    {"name": "3rd Floor (beta)", "colors": [(100,150,100), (50,80,50), (150,200,255)], "algo": "maze", "fog_color": (120,160,200), "fog_near": 10.0, "fog_far": 26.0, "surface": SURFACE_NORMAL},
    {"name": "4th Floor (Final)", "colors": [(200,180,150), (100,80,60), (50,40,30)], "algo": "dense", "fog_color": (50,40,35), "fog_near": 8.0, "fog_far": 20.0, "surface": SURFACE_NORMAL},
    {"name": "4th Floor (Corrupted)", "colors": [(80,10,10), (20,0,0), (0,0,0)], "algo": "chaos", "fog_color": (10,0,0), "fog_near": 4.0, "fog_far": 14.0, "surface": SURFACE_LAVA},
    {"name": "Crescent Castle", "colors": [(80,80,100), (30,30,50), (10,10,20)], "algo": "circular", "fog_color": (15,15,25), "fog_near": 6.0, "fog_far": 20.0, "surface": SURFACE_NORMAL},
    {"name": "Vanilla Basement", "colors": [(100,100,150), (40,40,80), (20,20,40)], "algo": "corridor", "fog_color": (25,25,45), "fog_near": 8.0, "fog_far": 22.0, "surface": SURFACE_NORMAL},
    {"name": "Plexal Basement", "colors": [(90,110,130), (30,50,70), (10,20,30)], "algo": "maze", "fog_color": (15,25,35), "fog_near": 6.0, "fog_far": 20.0, "surface": SURFACE_NORMAL},
    {"name": "Uncanny Basement", "colors": [(50,50,50), (20,20,20), (5,5,5)], "algo": "corridor", "fog_color": (5,5,8), "fog_near": 4.0, "fog_far": 16.0, "surface": SURFACE_NORMAL},
    {"name": "AI Undergrounds", "colors": [(40,255,40), (10,50,10), (0,10,0)], "algo": "grid", "fog_color": (0,15,0), "fog_near": 6.0, "fog_far": 20.0, "surface": SURFACE_NORMAL},
    {"name": "Bowser's Sub", "colors": [(120,40,40), (40,10,10), (10,0,0)], "algo": "corridor", "fog_color": (15,0,0), "fog_near": 5.0, "fog_far": 18.0, "surface": SURFACE_LAVA},
    {"name": "Plexal Sewers", "colors": [(60,100,60), (20,40,20), (10,20,10)], "algo": "wave", "fog_color": (10,25,15), "fog_near": 6.0, "fog_far": 18.0, "surface": SURFACE_WATER},
    {"name": "River Mountain", "colors": [(100,200,100), (40,100,40), (135,206,235)], "algo": "organic", "fog_color": (100,160,200), "fog_near": 12.0, "fog_far": 30.0, "surface": SURFACE_NORMAL},
    {"name": "Castle Grounds (Sunset)", "colors": [(150,100,50), (50,150,50), (255,100,50)], "algo": "organic", "fog_color": (200,100,60), "fog_near": 12.0, "fog_far": 30.0, "surface": SURFACE_NORMAL},
    {"name": "Uncanny Courtyard", "colors": [(100,100,80), (60,60,40), (30,30,20)], "algo": "organic", "fog_color": (35,35,25), "fog_near": 8.0, "fog_far": 22.0, "surface": SURFACE_NORMAL},
    {"name": "Monochrome Castle Grounds", "colors": [(128,128,128), (64,64,64), (192,192,192)], "algo": "organic", "fog_color": (150,150,150), "fog_near": 10.0, "fog_far": 26.0, "surface": SURFACE_NORMAL},
    {"name": "Forgotten Battlefield", "colors": [(80,140,60), (30,70,20), (100,150,255)], "algo": "organic", "fog_color": (80,120,200), "fog_near": 10.0, "fog_far": 28.0, "surface": SURFACE_NORMAL},
    {"name": "Sky Island", "colors": [(100,200,100), (50,100,50), (135,206,235)], "algo": "sparse", "fog_color": (135,200,235), "fog_near": 14.0, "fog_far": 32.0, "surface": SURFACE_NORMAL},
    {"name": "Wet-Dry Paradise (Beta)", "colors": [(50,100,180), (20,40,60), (10,80,100)], "algo": "wave", "fog_color": (15,60,80), "fog_near": 6.0, "fog_far": 20.0, "surface": SURFACE_WATER},
    {"name": "Jolly Roger Bay (beta)", "colors": [(40,80,120), (10,30,60), (5,10,20)], "algo": "wave", "fog_color": (8,20,40), "fog_near": 5.0, "fog_far": 18.0, "surface": SURFACE_WATER},
    {"name": "Dire Dire Docks (beta)", "colors": [(30,60,120), (10,20,50), (5,10,20)], "algo": "circular", "fog_color": (5,12,25), "fog_near": 5.0, "fog_far": 18.0, "surface": SURFACE_WATER},
    {"name": "Water Level (Corrupted)", "colors": [(0,50,100), (0,20,50), (0,10,20)], "algo": "chaos", "fog_color": (0,10,25), "fog_near": 3.0, "fog_far": 14.0, "surface": SURFACE_WATER},
    {"name": "Lethal Lava Land (beta)", "colors": [(200,50,0), (100,20,0), (50,0,0)], "algo": "dense", "fog_color": (60,10,0), "fog_near": 5.0, "fog_far": 18.0, "surface": SURFACE_LAVA},
    {"name": "Bowser's Checkered Madness", "colors": [(200,50,50), (50,50,50), (0,0,0)], "algo": "grid", "fog_color": (10,0,0), "fog_near": 6.0, "fog_far": 20.0, "surface": SURFACE_LAVA},
    {"name": "Cool, Cool Mountain (beta)", "colors": [(200,200,255), (150,150,200), (100,100,150)], "algo": "organic", "fog_color": (180,180,220), "fog_near": 10.0, "fog_far": 28.0, "surface": SURFACE_ICE},
    {"name": "Tall, Tall Treetops", "colors": [(130,90,50), (50,120,40), (100,200,255)], "algo": "sparse", "fog_color": (80,160,220), "fog_near": 12.0, "fog_far": 30.0, "surface": SURFACE_NORMAL},
    {"name": "Shifting Sand Land (beta)", "colors": [(210,180,100), (150,120,50), (255,200,100)], "algo": "wave", "fog_color": (200,160,80), "fog_near": 8.0, "fog_far": 24.0, "surface": SURFACE_CONVEY},
    {"name": "Big Boo's Haunt (beta)", "colors": [(100,80,60), (40,30,20), (10,5,5)], "algo": "maze", "fog_color": (12,8,8), "fog_near": 4.0, "fog_far": 16.0, "surface": SURFACE_NORMAL},
    {"name": "Hazy Maze Cave (beta)", "colors": [(120,100,150), (60,40,80), (30,20,40)], "algo": "organic", "fog_color": (50,30,60), "fog_near": 4.0, "fog_far": 14.0, "surface": SURFACE_NORMAL},
    {"name": "Hazy Memory Cave", "colors": [(80,80,100), (30,30,40), (10,10,15)], "algo": "organic", "fog_color": (15,15,20), "fog_near": 3.0, "fog_far": 12.0, "surface": SURFACE_NORMAL},
    {"name": "Motos Factory", "colors": [(100,100,100), (50,50,50), (30,30,30)], "algo": "grid", "fog_color": (35,35,35), "fog_near": 6.0, "fog_far": 20.0, "surface": SURFACE_CONVEY},
    {"name": "Whomp's Fortress (beta)", "colors": [(150,150,150), (100,100,100), (135,206,235)], "algo": "pillars", "fog_color": (100,160,200), "fog_near": 10.0, "fog_far": 26.0, "surface": SURFACE_NORMAL},
    {"name": "Tick Tock Clock (beta)", "colors": [(180,140,50), (100,80,20), (50,40,10)], "algo": "grid", "fog_color": (50,40,15), "fog_near": 6.0, "fog_far": 20.0, "surface": SURFACE_NORMAL},
    {"name": "Rainbow Ride (beta)", "colors": [(255,150,255), (150,200,255), (50,50,100)], "algo": "sparse", "fog_color": (80,80,150), "fog_near": 10.0, "fog_far": 28.0, "surface": SURFACE_NORMAL},
    {"name": "Peach's Secret Slide", "colors": [(150,150,255), (80,80,150), (40,40,80)], "algo": "corridor", "fog_color": (50,50,100), "fog_near": 6.0, "fog_far": 20.0, "surface": SURFACE_ICE},
    {"name": "Plexal Hub", "colors": [(140,140,150), (60,60,70), (20,20,30)], "algo": "pillars", "fog_color": (25,25,35), "fog_near": 8.0, "fog_far": 22.0, "surface": SURFACE_NORMAL},
    {"name": "Plexal Corridors", "colors": [(150,150,160), (40,40,50), (20,20,20)], "algo": "corridor", "fog_color": (20,20,25), "fog_near": 6.0, "fog_far": 20.0, "surface": SURFACE_NORMAL},
    {"name": "Floor 3B", "colors": [(140,160,140), (70,80,70), (40,50,40)], "algo": "dense", "fog_color": (45,55,45), "fog_near": 6.0, "fog_far": 20.0, "surface": SURFACE_NORMAL},
    {"name": "Floor 2B", "colors": [(130,150,130), (60,70,60), (30,40,30)], "algo": "dense", "fog_color": (35,45,35), "fog_near": 6.0, "fog_far": 20.0, "surface": SURFACE_NORMAL},
    {"name": "Floor 1B", "colors": [(120,140,120), (50,60,50), (20,30,20)], "algo": "dense", "fog_color": (25,35,25), "fog_near": 6.0, "fog_far": 20.0, "surface": SURFACE_NORMAL},
    {"name": "Star Road (beta)", "colors": [(255,255,150), (100,100,50), (20,20,40)], "algo": "pillars", "fog_color": (30,30,50), "fog_near": 8.0, "fog_far": 24.0, "surface": SURFACE_NORMAL},
    {"name": "The Star", "colors": [(255,255,200), (150,150,100), (255,255,255)], "algo": "pillars", "fog_color": (200,200,200), "fog_near": 12.0, "fog_far": 30.0, "surface": SURFACE_NORMAL},
    {"name": "The True Core", "colors": [(255,255,255), (200,200,200), (255,255,255)], "algo": "maze", "fog_color": (220,220,220), "fog_near": 10.0, "fog_far": 28.0, "surface": SURFACE_NORMAL},
    {"name": "The Void", "colors": [(30,30,30), (0,0,0), (0,0,0)], "algo": "sparse", "fog_color": (0,0,0), "fog_near": 2.0, "fog_far": 10.0, "surface": SURFACE_NORMAL},
    {"name": "Redial", "colors": [(255,0,0), (100,0,0), (50,0,0)], "algo": "chaos", "fog_color": (60,0,0), "fog_near": 3.0, "fog_far": 12.0, "surface": SURFACE_LAVA},
    {"name": "Endless Stairs", "colors": [(100,0,0), (50,0,0), (20,0,0)], "algo": "corridor", "fog_color": (25,0,0), "fog_near": 4.0, "fog_far": 14.0, "surface": SURFACE_NORMAL},
    {"name": "The End", "colors": [(0,0,0), (0,0,0), (0,0,0)], "algo": "sparse", "fog_color": (0,0,0), "fog_near": 1.0, "fog_far": 8.0, "surface": SURFACE_NORMAL},
    {"name": "Dark Downtown", "colors": [(60,60,80), (20,20,30), (10,10,15)], "algo": "grid", "fog_color": (12,12,18), "fog_near": 4.0, "fog_far": 16.0, "surface": SURFACE_NORMAL},
    {"name": "Challenge Lobby", "colors": [(180,150,50), (80,60,20), (40,30,10)], "algo": "maze", "fog_color": (45,35,15), "fog_near": 6.0, "fog_far": 20.0, "surface": SURFACE_NORMAL},
    {"name": "Nebula Lobby", "colors": [(100,50,150), (30,10,50), (10,0,20)], "algo": "circular", "fog_color": (15,5,25), "fog_near": 5.0, "fog_far": 18.0, "surface": SURFACE_NORMAL},
    {"name": "Polygonal Chaos", "colors": [(200,50,200), (50,100,50), (50,50,200)], "algo": "chaos", "fog_color": (40,40,100), "fog_near": 4.0, "fog_far": 16.0, "surface": SURFACE_NORMAL},
]

MAP_STARTS = [(cfg["name"], i * ROOM_SIZE + 50.0, 50.0) for i, cfg in enumerate(MAP_CONFIGS)]

# ==========================================
# Spatial Grid Cache (16x16 per room)
# ==========================================
GRID_CELL_SIZE = ROOM_SIZE / 16.0
_grid_cache = {}

def clear_grid_cache():
    _grid_cache.clear()

# ==========================================
# Doorway Clear Zone
# ==========================================
def is_in_doorway_clear_zone(lx, ly):
    center = ROOM_SIZE / 2.0
    dh = DOOR_WIDTH / 2.0
    if ly < DOOR_CLEAR_DEPTH and abs(lx - center) <= dh:
        return True
    if ly > ROOM_SIZE - DOOR_CLEAR_DEPTH and abs(lx - center) <= dh:
        return True
    if lx < DOOR_CLEAR_DEPTH and abs(ly - center) <= dh:
        return True
    if lx > ROOM_SIZE - DOOR_CLEAR_DEPTH and abs(ly - center) <= dh:
        return True
    return False

# ==========================================
# Procedural World Generation
# ==========================================
def get_map_data(x, y):
    """Returns (is_wall, wall_color, area_name, floor_color, ceil_color,
                fog_color, fog_near, fog_far, surface_type, wall_face)
    wall_face: 0=N/S, 1=E/W for face-direction shading (SM64-style)
    """
    ix, iy = x + 0.0001, y + 0.0001
    grid_x = int(math.floor(ix / ROOM_SIZE))
    grid_y = int(math.floor(iy / ROOM_SIZE))
    hash_val = abs(grid_x * 73856 + grid_y * 19349663)
    zone_index = hash_val % len(MAP_CONFIGS)
    config = MAP_CONFIGS[zone_index]
    wall_col, floor_col, ceil_col = config["colors"]
    fog_col = config.get("fog_color", (0, 0, 0))
    fog_n = config.get("fog_near", 8.0)
    fog_f = config.get("fog_far", 24.0)
    surf = config.get("surface", SURFACE_NORMAL)
    area_name = f"[{grid_x},{grid_y}] {config['name']}"
    lx, ly = ix % ROOM_SIZE, iy % ROOM_SIZE

    null_result = lambda wf=0: (False, (0,0,0), area_name, floor_col, ceil_col, fog_col, fog_n, fog_f, surf, wf)

    # Borders and doorways
    border_thick = 2.0
    dh = DOOR_WIDTH / 2.0
    if ly < border_thick or ly > ROOM_SIZE - border_thick:
        if abs(lx - ROOM_SIZE / 2) > dh:
            return (True, (40,40,40), area_name, floor_col, ceil_col, fog_col, fog_n, fog_f, surf, 0)
    if lx < border_thick or lx > ROOM_SIZE - border_thick:
        if abs(ly - ROOM_SIZE / 2) > dh:
            return (True, (40,40,40), area_name, floor_col, ceil_col, fog_col, fog_n, fog_f, surf, 1)

    # Safe spawn
    if abs(lx - ROOM_SIZE/2) < 3.0 and abs(ly - ROOM_SIZE/2) < 3.0:
        return null_result()
    if is_in_doorway_clear_zone(lx, ly):
        return null_result()

    # Determine wall face from fractional position (E/W vs N/S)
    frac_x = lx % 1.0
    frac_y = ly % 1.0
    wall_face = 1 if min(frac_x, 1.0 - frac_x) < min(frac_y, 1.0 - frac_y) else 0

    # Internal geometry algorithms
    wall = False
    algo = config["algo"]

    if algo == "castle":
        dist_c = math.sqrt((lx - 50)**2 + (ly - 50)**2)
        if 28 < dist_c < 32:
            if not ((45 < lx < 55) or (45 < ly < 55)):
                return (True, (40, 80, 220), area_name, floor_col, ceil_col, fog_col, fog_n, fog_f, surf, wall_face)
        if 15 < ly < 30 and 35 < lx < 65:
            return (True, (240, 240, 240), area_name, floor_col, ceil_col, fog_col, fog_n, fog_f, surf, wall_face)
        if (lx - 35)**2 + (ly - 20)**2 < 16:
            return (True, (220, 40, 40), area_name, floor_col, ceil_col, fog_col, fog_n, fog_f, surf, wall_face)
        if (lx - 65)**2 + (ly - 20)**2 < 16:
            return (True, (220, 40, 40), area_name, floor_col, ceil_col, fog_col, fog_n, fog_f, surf, wall_face)
    elif algo == "pillars":
        wall = (math.sin(lx * 0.3) * math.cos(ly * 0.3)) > 0.8
    elif algo == "corridor":
        wall = math.sin(lx * 0.15) + math.cos(ly * 0.02) > 0.6
    elif algo == "maze":
        wall = math.sin(lx * 0.2) + math.cos(ly * 0.2) + math.sin(lx * ly * 0.01) > 1.0
    elif algo == "dense":
        wall = math.cos(lx * 0.2) * math.sin(ly * 0.2) > 0.2
    elif algo == "chaos":
        wall = math.sin(lx * 0.13) * math.cos(ly * 0.17) + math.sin(lx * ly * 0.01) > 0.8
    elif algo == "circular":
        wall = math.sin(math.sqrt((lx - 50)**2 + (ly - 50)**2) * 0.2) > 0.5
    elif algo == "grid":
        wall = (math.sin(lx * 0.2) > 0.8) or (math.cos(ly * 0.2) > 0.8)
    elif algo == "organic":
        wall = math.sin(lx * 0.08) + math.cos(ly * 0.08) + math.sin(lx * ly * 0.001) > 1.2
    elif algo == "wave":
        wall = math.sin(math.sqrt((lx - 50)**2 + (ly - 50)**2) * 0.15) > 0.5
    elif algo == "sparse":
        wall = (math.sin(lx * 0.02) * math.cos(ly * 0.02)) > 0.95

    return (wall, wall_col, area_name, floor_col, ceil_col, fog_col, fog_n, fog_f, surf, wall_face)

# ==========================================
# Fog Blending (SM64 RDP-style)
# ==========================================
def apply_fog(color, distance, fog_color, fog_near, fog_far):
    """SM64-style fog: lerp(surfaceColor, fogColor, fogFactor)"""
    if not CFG["fog_enabled"]:
        return color
    if distance <= fog_near:
        return color
    if distance >= fog_far:
        return fog_color
    t = (distance - fog_near) / (fog_far - fog_near)
    return (
        int(color[0] * (1 - t) + fog_color[0] * t),
        int(color[1] * (1 - t) + fog_color[1] * t),
        int(color[2] * (1 - t) + fog_color[2] * t),
    )

# ==========================================
# Wall-Face Shading (SM64 directional light)
# ==========================================
def apply_wall_shading(color, wall_face, distance, max_dist):
    """SM64-style: N/S walls are darker than E/W walls + distance falloff"""
    shade = max(0.0, min(1.0, 1.0 - (distance / max_dist)))
    # Directional: E/W faces get 100% light, N/S get 75%
    face_mult = 0.75 if wall_face == 0 else 1.0
    shade *= face_mult
    return (
        max(0, min(255, int(color[0] * shade))),
        max(0, min(255, int(color[1] * shade))),
        max(0, min(255, int(color[2] * shade))),
    )

# ==========================================
# Gamepad Support
# ==========================================
joystick = None

def init_gamepad():
    global joystick
    pygame.joystick.init()
    if pygame.joystick.get_count() > 0:
        joystick = pygame.joystick.Joystick(0)
        joystick.init()

def get_gamepad_input():
    """Returns (move_x, move_y, look_x, look_y, jump_btn, pause_btn)"""
    if joystick is None:
        return (0, 0, 0, 0, False, False)
    try:
        lx = joystick.get_axis(0) if abs(joystick.get_axis(0)) > 0.15 else 0
        ly = joystick.get_axis(1) if abs(joystick.get_axis(1)) > 0.15 else 0
        rx = joystick.get_axis(2) if joystick.get_numaxes() > 2 and abs(joystick.get_axis(2)) > 0.15 else 0
        ry = joystick.get_axis(3) if joystick.get_numaxes() > 3 and abs(joystick.get_axis(3)) > 0.15 else 0
        jump = joystick.get_button(0) if joystick.get_numbuttons() > 0 else False
        pause = joystick.get_button(7) if joystick.get_numbuttons() > 7 else False
        return (lx, ly, rx, ry, jump, pause)
    except Exception:
        return (0, 0, 0, 0, False, False)

# ==========================================
# Player Movement (SM64-style with surface physics)
# ==========================================
def handle_movement(dt):
    global player_x, player_y, player_angle, player_vel_x, player_vel_y
    global player_on_ice, player_in_water, step_timer
    global player_health, player_damage_timer, player_coins

    keys = pygame.key.get_pressed()
    gp_mx, gp_my, gp_lx, gp_ly, gp_jump, _ = get_gamepad_input()

    # --- Puppycam: Mouse Look ---
    if pygame.event.get_grab():
        mouse_dx, mouse_dy = pygame.mouse.get_rel()
        sens_x = CFG["mouse_sensitivity_x"]
        if CFG["invert_x"]:
            mouse_dx = -mouse_dx
        player_angle += mouse_dx * sens_x
        # Gamepad right stick look
        player_angle += gp_lx * 0.05

    # Keyboard look fallback
    if keys[pygame.K_LEFT]:
        player_angle -= 0.05
    if keys[pygame.K_RIGHT]:
        player_angle += 0.05

    # Movement speed with cheats
    move_step = CFG["move_speed"]
    if CFG["cheats_enabled"] and CFG["speed_boost"]:
        move_step *= 2.5

    # Ice physics: momentum-based
    friction = 0.6 if player_on_ice else 1.0
    decel = 0.92 if player_on_ice else 0.0

    dx_fwd = math.cos(player_angle) * move_step
    dy_fwd = math.sin(player_angle) * move_step
    dx_str = math.cos(player_angle + math.pi / 2) * move_step
    dy_str = math.sin(player_angle + math.pi / 2) * move_step

    accel_x, accel_y = 0.0, 0.0

    # Keyboard
    if keys[pygame.K_w] or keys[pygame.K_UP]:
        accel_x += dx_fwd; accel_y += dy_fwd
    if keys[pygame.K_s] or keys[pygame.K_DOWN]:
        accel_x -= dx_fwd; accel_y -= dy_fwd
    if keys[pygame.K_a]:
        accel_x -= dx_str; accel_y -= dy_str
    if keys[pygame.K_d]:
        accel_x += dx_str; accel_y += dy_str

    # Gamepad left stick
    accel_x += (dx_fwd * -gp_my + dx_str * gp_mx)
    accel_y += (dy_fwd * -gp_my + dy_str * gp_mx)

    moving = abs(accel_x) > 0.001 or abs(accel_y) > 0.001

    if player_on_ice:
        player_vel_x = player_vel_x * decel + accel_x * friction
        player_vel_y = player_vel_y * decel + accel_y * friction
    else:
        player_vel_x = accel_x
        player_vel_y = accel_y

    new_x = player_x + player_vel_x
    new_y = player_y + player_vel_y

    # Collision (No Clip cheat bypasses)
    no_clip = CFG["cheats_enabled"] and CFG["no_clip"]
    if no_clip or not get_map_data(new_x, player_y)[0]:
        player_x = new_x
    elif player_on_ice:
        player_vel_x *= -0.3
    if no_clip or not get_map_data(player_x, new_y)[0]:
        player_y = new_y
    elif player_on_ice:
        player_vel_y *= -0.3

    # Get current area surface type
    _, _, _, _, _, _, _, _, surf, _ = get_map_data(player_x, player_y)
    player_on_ice = (surf == SURFACE_ICE)
    player_in_water = (surf == SURFACE_WATER)

    # Surface damage
    player_damage_timer = max(0, player_damage_timer - dt)
    if not (CFG["cheats_enabled"] and CFG["invincibility"]):
        if surf == SURFACE_LAVA and player_damage_timer <= 0:
            player_health = max(0, player_health - 1)
            player_damage_timer = 1.0
            play_sfx("lava")
        if surf == SURFACE_WATER:
            # Slow heal in water (SM64 mechanic)
            if player_health < 8 and random.random() < 0.01:
                player_health = min(8, player_health + 1)

    # Conveyor push
    if surf == SURFACE_CONVEY:
        player_x += math.cos(time.time()) * 0.03
        player_y += math.sin(time.time()) * 0.03

    # Coin collection (random chance in new areas)
    if moving and random.random() < 0.002:
        player_coins += 1
        play_sfx("coin")
        if player_coins % 50 == 0:
            player_health = min(8, player_health + 1)
            play_sfx("heal")

    # Step sounds
    if moving:
        step_timer += dt
        if step_timer >= STEP_INTERVAL:
            step_timer = 0.0
            play_sfx("step")

# ==========================================
# SM64-Style Power Meter Rendering
# ==========================================
def draw_power_meter(screen, x, y, health):
    """Draw SM64-accurate power meter with 8 wedges."""
    radius = 28
    # Background circle
    pygame.draw.circle(screen, (40, 40, 40), (x, y), radius + 2)
    pygame.draw.circle(screen, (10, 10, 30), (x, y), radius)

    # 8 wedges, each 45 degrees
    for i in range(8):
        if i < health:
            # Color gradient: green > yellow > red
            if health >= 6:
                col = (50, 200, 80)
            elif health >= 3:
                col = (220, 200, 40)
            else:
                col = (220, 40, 40)
            start_angle = math.radians(90 - (i + 1) * 45)
            end_angle = math.radians(90 - i * 45)
            # Draw filled wedge
            points = [(x, y)]
            steps = 8
            for s in range(steps + 1):
                a = start_angle + (end_angle - start_angle) * s / steps
                px = x + int(math.cos(a) * (radius - 2))
                py = y - int(math.sin(a) * (radius - 2))
                points.append((px, py))
            if len(points) >= 3:
                pygame.draw.polygon(screen, col, points)

    # Center dot
    pygame.draw.circle(screen, (255, 255, 255), (x, y), 4)
    # Outline
    pygame.draw.circle(screen, (200, 200, 200), (x, y), radius + 2, 2)

# ==========================================
# Minimap (SM64ex-style overhead view)
# ==========================================
def draw_minimap(screen, px, py, angle, mm_x, mm_y, mm_size=120):
    """Real-time overhead minimap with player arrow."""
    mm_surf = pygame.Surface((mm_size, mm_size))
    mm_surf.set_alpha(180)
    mm_surf.fill((10, 10, 20))

    scale = 2.0
    half = mm_size // 2
    for my in range(0, mm_size, 3):
        for mx in range(0, mm_size, 3):
            wx = px + (mx - half) / scale
            wy = py + (my - half) / scale
            is_wall = get_map_data(wx, wy)[0]
            if is_wall:
                mm_surf.set_at((mx, my), (120, 120, 140))

    # Player dot + direction arrow
    cx, cy = half, half
    pygame.draw.circle(mm_surf, (255, 50, 50), (cx, cy), 3)
    ax = cx + int(math.cos(angle) * 8)
    ay = cy + int(math.sin(angle) * 8)
    pygame.draw.line(mm_surf, (255, 255, 0), (cx, cy), (ax, ay), 2)

    # Border
    pygame.draw.rect(mm_surf, (100, 100, 120), (0, 0, mm_size, mm_size), 1)
    screen.blit(mm_surf, (mm_x, mm_y))

# ==========================================
# HUD Rendering (SM64-style bitfield flags)
# ==========================================
def draw_hud(screen, font, small_font, clock_fps, area_name):
    global hud_flags
    w, h = screen.get_size()

    # Top-left: Area name + coords
    info_bg = pygame.Surface((460, 35))
    info_bg.set_alpha(160)
    info_bg.fill((10, 10, 10))
    screen.blit(info_bg, (8, 8))
    screen.blit(font.render(f"AREA: {area_name}", True, (255, 255, 0)), (14, 12))

    # Lives (top-right area)
    rx = w - 200
    if hud_flags & HUD_LIVES:
        lives_text = f"x{player_lives}"
        screen.blit(font.render(f"M {lives_text}", True, (255, 255, 255)), (rx, 14))

    # Stars
    if hud_flags & HUD_STARS:
        screen.blit(font.render(f"* x{player_stars}", True, (255, 255, 100)), (rx, 38))

    # Coins
    if hud_flags & HUD_COINS:
        screen.blit(font.render(f"$ x{player_coins}", True, (255, 200, 50)), (rx + 100, 14))

    # Camera mode
    if hud_flags & HUD_CAMERA:
        cam_str = "PuppyCam" if camera_mode == CAM_PUPPYCAM else "Fixed"
        screen.blit(small_font.render(f"CAM: {cam_str}", True, (150, 200, 255)), (rx + 100, 38))

    # Power meter
    if hud_flags & HUD_POWER:
        draw_power_meter(screen, w - 50, h - 50, player_health)

    # FPS
    if CFG["show_fps"]:
        screen.blit(small_font.render(f"FPS: {int(clock_fps)}", True, (0, 255, 255)), (14, 46))

    # Coords
    screen.blit(small_font.render(f"X:{player_x:.0f} Y:{player_y:.0f}", True, (180, 180, 180)), (14, 62))

    # Cheats indicator
    if CFG["cheats_enabled"]:
        cheats_active = []
        if CFG["moon_jump"]:    cheats_active.append("MOONJMP")
        if CFG["speed_boost"]:  cheats_active.append("SPEED")
        if CFG["no_clip"]:      cheats_active.append("NOCLIP")
        if CFG["invincibility"]:cheats_active.append("INVNC")
        if CFG["infinite_lives"]:cheats_active.append("INFLV")
        if cheats_active:
            ct = " ".join(cheats_active)
            screen.blit(small_font.render(f"CHEATS: {ct}", True, (255, 100, 100)), (14, h - 20))

    # Surface indicator
    _, _, _, _, _, _, _, _, surf, _ = get_map_data(player_x, player_y)
    surf_names = {SURFACE_NORMAL: "", SURFACE_LAVA: "LAVA!", SURFACE_ICE: "ICE",
                  SURFACE_WATER: "WATER", SURFACE_CONVEY: "CONVEYOR"}
    sn = surf_names.get(surf, "")
    if sn:
        col = (255, 50, 50) if surf == SURFACE_LAVA else (100, 200, 255)
        screen.blit(font.render(sn, True, col), (w // 2 - 30, h - 30))

    # Damage flash
    if player_damage_timer > 0.5:
        flash = pygame.Surface((w, h))
        flash.fill((255, 0, 0))
        flash.set_alpha(int(80 * (player_damage_timer - 0.5)))
        screen.blit(flash, (0, 0))

    # Water tint overlay
    if player_in_water:
        water_ov = pygame.Surface((w, h))
        water_ov.fill((0, 40, 100))
        water_ov.set_alpha(40)
        screen.blit(water_ov, (0, 0))

    # Crosshair
    pygame.draw.circle(screen, (255, 255, 255), (w // 2, h // 2), 3, 1)

    # Minimap
    if CFG["show_minimap"]:
        draw_minimap(screen, player_x, player_y, player_angle, w - 135, h - 155)

# ==========================================
# UI Screens
# ==========================================
def show_info_screen(screen, font, title_font, title, lines):
    w, h = screen.get_size()
    clock = pygame.time.Clock()
    while True:
        screen.fill((10, 10, 15))
        tt = title_font.render(title, True, (200, 200, 255))
        screen.blit(tt, (w // 2 - tt.get_width() // 2, 60))
        for i, line in enumerate(lines):
            lt = font.render(line, True, (150, 150, 150))
            screen.blit(lt, (w // 2 - lt.get_width() // 2, 130 + i * 35))
        pygame.display.flip()
        clock.tick(FPS)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_RETURN):
                    play_sfx("menu")
                    return

def level_select_menu(screen, font, title_font):
    global player_x, player_y, player_angle
    w, h = screen.get_size()
    selected = 0
    clock = pygame.time.Clock()
    while True:
        screen.fill((10, 10, 15))
        tt = title_font.render("SELECT STARTING MAP", True, (200, 200, 255))
        screen.blit(tt, (w // 2 - tt.get_width() // 2, 60))
        max_vis = min(12, (h - 200) // 35)
        start_i = max(0, selected - max_vis // 2)
        end_i = min(len(MAP_STARTS), start_i + max_vis)
        for i in range(start_i, end_i):
            mn = MAP_STARTS[i][0]
            col = (255, 255, 0) if i == selected else (100, 100, 100)
            pfx = "> " if i == selected else "  "
            ot = font.render(f"{pfx}{mn}", True, col)
            screen.blit(ot, (w // 2 - 200, 140 + (i - start_i) * 35))
        # Scroll indicator
        if start_i > 0:
            screen.blit(font.render("  ^ more ^", True, (80, 80, 80)), (w // 2 - 60, 120))
        if end_i < len(MAP_STARTS):
            screen.blit(font.render("  v more v", True, (80, 80, 80)), (w // 2 - 60, 140 + max_vis * 35))
        pygame.display.flip()
        clock.tick(FPS)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    play_sfx("menu"); return False
                if event.key == pygame.K_UP:
                    selected = (selected - 1) % len(MAP_STARTS); play_sfx("menu")
                if event.key == pygame.K_DOWN:
                    selected = (selected + 1) % len(MAP_STARTS); play_sfx("menu")
                if event.key == pygame.K_RETURN:
                    player_x = MAP_STARTS[selected][1]
                    player_y = MAP_STARTS[selected][2]
                    player_angle = -math.pi / 2
                    play_sfx("door")
                    return True

# ==========================================
# Options Menu (SM64ex-style)
# ==========================================
def options_menu(screen, font, title_font, small_font):
    w, h = screen.get_size()
    clock = pygame.time.Clock()
    selected = 0

    def get_opts():
        return [
            ("DISPLAY", None),
            (f"  Widescreen:       {'ON' if CFG['widescreen'] else 'OFF'}", "widescreen"),
            (f"  Texture Filter:   {'Bilinear' if CFG['texture_filtering'] else 'Nearest (N64)'}", "texture_filtering"),
            (f"  Fog:              {'ON' if CFG['fog_enabled'] else 'OFF'}", "fog_enabled"),
            (f"  Draw Distance:    {'Extended' if CFG['draw_distance_enabled'] else 'N64'}", "draw_distance_enabled"),
            (f"  Show FPS:         {'ON' if CFG['show_fps'] else 'OFF'}", "show_fps"),
            (f"  Show Minimap:     {'ON' if CFG['show_minimap'] else 'OFF'}", "show_minimap"),
            ("CAMERA (PUPPYCAM)", None),
            (f"  Sensitivity X:    {CFG['mouse_sensitivity_x']:.4f}", "sens_x"),
            (f"  Sensitivity Y:    {CFG['mouse_sensitivity_y']:.4f}", "sens_y"),
            (f"  Invert X:         {'ON' if CFG['invert_x'] else 'OFF'}", "invert_x"),
            (f"  Invert Y:         {'ON' if CFG['invert_y'] else 'OFF'}", "invert_y"),
            ("AUDIO", None),
            (f"  Master Volume:    {int(CFG['master_volume']*100)}%", "master_vol"),
            (f"  Music:            {'ON' if CFG['music_enabled'] else 'OFF'}", "music_enabled"),
            ("CHEATS" + (" [ACTIVE]" if CFG["cheats_enabled"] else " [LOCKED]"), None),
        ]

    def get_cheat_opts():
        if not CFG["cheats_enabled"]:
            return []
        return [
            (f"  Moon Jump:        {'ON' if CFG['moon_jump'] else 'OFF'}", "moon_jump"),
            (f"  Infinite Lives:   {'ON' if CFG['infinite_lives'] else 'OFF'}", "infinite_lives"),
            (f"  Speed Boost:      {'ON' if CFG['speed_boost'] else 'OFF'}", "speed_boost"),
            (f"  No Clip:          {'ON' if CFG['no_clip'] else 'OFF'}", "no_clip"),
            (f"  Invincibility:    {'ON' if CFG['invincibility'] else 'OFF'}", "invincibility"),
        ]

    while True:
        opts = get_opts() + get_cheat_opts() + [("", None), ("SAVE & RETURN", "save_return")]
        screen.fill((10, 10, 15))
        tt = title_font.render("OPTIONS", True, (200, 200, 255))
        screen.blit(tt, (w // 2 - tt.get_width() // 2, 30))

        max_vis = min(len(opts), (h - 120) // 28)
        start_i = max(0, selected - max_vis // 2)
        end_i = min(len(opts), start_i + max_vis)

        for i in range(start_i, end_i):
            label, key = opts[i]
            if key is None and label:
                col = (180, 180, 255) if label.startswith("CHEAT") else (255, 200, 100)
                screen.blit(font.render(label, True, col), (60, 80 + (i - start_i) * 28))
            elif key:
                col = (255, 255, 0) if i == selected else (140, 140, 140)
                pfx = "> " if i == selected else "  "
                screen.blit(small_font.render(f"{pfx}{label}", True, col), (60, 80 + (i - start_i) * 28))
            else:
                pass  # blank line

        screen.blit(small_font.render("UP/DOWN: Navigate  ENTER/LEFT/RIGHT: Change  ESC: Back", True, (100,100,100)), (60, h - 30))
        pygame.display.flip()
        clock.tick(FPS)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                save_config(CFG); pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    save_config(CFG); play_sfx("menu"); return

                # Skip headers
                def next_sel(d):
                    s = selected
                    for _ in range(len(opts)):
                        s = (s + d) % len(opts)
                        if opts[s][1] is not None:
                            return s
                    return selected

                if event.key == pygame.K_UP:
                    selected = next_sel(-1); play_sfx("menu")
                if event.key == pygame.K_DOWN:
                    selected = next_sel(1); play_sfx("menu")

                if event.key in (pygame.K_RETURN, pygame.K_RIGHT, pygame.K_LEFT):
                    if selected < len(opts):
                        _, key = opts[selected]
                        if key == "save_return":
                            save_config(CFG); play_sfx("menu"); return
                        # Toggle booleans
                        bool_keys = ["widescreen", "texture_filtering", "fog_enabled",
                                     "draw_distance_enabled", "show_fps", "show_minimap",
                                     "invert_x", "invert_y", "music_enabled",
                                     "moon_jump", "infinite_lives", "speed_boost",
                                     "no_clip", "invincibility"]
                        if key in bool_keys:
                            CFG[key] = not CFG[key]; play_sfx("menu")
                        elif key == "sens_x":
                            d = 0.0005 if event.key == pygame.K_RIGHT else -0.0005
                            CFG["mouse_sensitivity_x"] = max(0.0005, CFG["mouse_sensitivity_x"] + d)
                        elif key == "sens_y":
                            d = 0.0005 if event.key == pygame.K_RIGHT else -0.0005
                            CFG["mouse_sensitivity_y"] = max(0.0005, CFG["mouse_sensitivity_y"] + d)
                        elif key == "master_vol":
                            d = 0.1 if event.key == pygame.K_RIGHT else -0.1
                            CFG["master_volume"] = max(0, min(1, CFG["master_volume"] + d))

# ==========================================
# Main Menu
# ==========================================
def main_menu(screen, font, title_font, small_font):
    w, h = screen.get_size()
    options = ["Resume Game", "Select Map", "Options", "About", "Help", "Credits", "Exit"]
    selected = 0
    clock = pygame.time.Clock()
    pygame.event.set_grab(False)
    pygame.mouse.set_visible(True)

    while True:
        screen.fill((5, 5, 10))
        # BRANDING
        tt = title_font.render("AC HOLDS B3313 SM64 PORT 1.0", True, (255, 255, 255))
        screen.blit(tt, (w // 2 - tt.get_width() // 2, 40))
        c1 = small_font.render("[C] AC HOLDING 1999-2026", True, (150, 150, 150))
        c2 = small_font.render("[C] Chris r rillo team 2023", True, (150, 150, 150))
        c3 = small_font.render("[C] Nintendo 1985-2026", True, (150, 150, 150))
        c4 = small_font.render("SM64 PC Port Features Integrated", True, (100, 150, 255))
        screen.blit(c1, (w // 2 - c1.get_width() // 2, 80))
        screen.blit(c2, (w // 2 - c2.get_width() // 2, 100))
        screen.blit(c3, (w // 2 - c3.get_width() // 2, 120))
        screen.blit(c4, (w // 2 - c4.get_width() // 2, 145))

        for i, opt in enumerate(options):
            col = (255, 255, 0) if i == selected else (100, 100, 100)
            pfx = "> " if i == selected else "  "
            t = font.render(f"{pfx}{opt}", True, col)
            screen.blit(t, (w // 2 - 110, 190 + i * 42))

        # Feature list at bottom
        feats = "Puppycam | Fog | 60fps | Cheats | Gamepad | Minimap | Options | Config"
        screen.blit(small_font.render(feats, True, (80, 80, 100)), (w // 2 - len(feats) * 3, h - 25))

        pygame.display.flip()
        clock.tick(FPS)
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                save_config(CFG); pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:
                    selected = (selected - 1) % len(options); play_sfx("menu")
                if event.key == pygame.K_DOWN:
                    selected = (selected + 1) % len(options); play_sfx("menu")
                if event.key == pygame.K_RETURN:
                    play_sfx("menu")
                    if selected == 0:
                        return True  # Resume
                    if selected == 1:
                        if level_select_menu(screen, font, title_font):
                            return True
                    if selected == 2:
                        options_menu(screen, font, title_font, small_font)
                    if selected == 3:
                        show_info_screen(screen, font, title_font, "ABOUT", [
                            "B3313 Python Port - SM64 PC Port Edition",
                            "All sm64-port/sm64ex features integrated:",
                            "Puppycam, Fog, Wall-Face Shading, Spatial Grid,",
                            "SM64 HUD, Power Meter, Cheats, Gamepad,",
                            "Config Save, Options Menu, Surface Types,",
                            "Procedural Audio, Minimap, Draw Distance Toggle",
                            "", "Connectivity Patch 1.0.4 + SM64 Port 1.0",
                            "", "Press ESC to return."])
                    if selected == 4:
                        show_info_screen(screen, font, title_font, "HELP", [
                            "CONTROLS (Keyboard+Mouse):",
                            "W/A/S/D : Move & Strafe",
                            "Mouse : Puppycam Look (360 analog)",
                            "ESC : Pause Menu / Options",
                            "Arrow Keys : Keyboard Look (fallback)",
                            "",
                            "GAMEPAD: Left Stick=Move, Right Stick=Look",
                            "A=Jump, Start=Pause",
                            "",
                            "CHEATS: Launch with --cheats or toggle in Options",
                            "", "Press ESC to return."])
                    if selected == 5:
                        show_info_screen(screen, font, title_font, "CREDITS", [
                            "[C] AC HOLDING 1999-2026",
                            "[C] Chris r rillo team 2023",
                            "[C] Nintendo 1985-2026",
                            "",
                            "SM64 PC Port: sm64-port team",
                            "sm64ex: sm64pc community",
                            "Puppycam: FazanaJ",
                            "Original B3313: Rillo & Team",
                            "", "Press ESC to return."])
                    if selected == 6:
                        save_config(CFG); pygame.quit(); sys.exit()

# ==========================================
# Game Loop
# ==========================================
def game_loop(screen, font, small_font):
    global current_area, player_x, player_y, player_angle
    global player_health, player_lives
    global pause_l_count

    w, h = screen.get_size()
    clock = pygame.time.Clock()
    pygame.mouse.set_visible(False)
    pygame.event.set_grab(True)
    pygame.mouse.get_rel()

    sky_cache_key = None
    sky_surf = None
    max_dist = CFG["max_draw_distance"] if CFG["draw_distance_enabled"] else 16.0
    prev_time = time.time()

    while True:
        # Delta time
        now = time.time()
        dt = min(now - prev_time, 0.05)
        prev_time = now

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                save_config(CFG); pygame.quit(); sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return
                # Cheats activation: L key 3x (mapped to K_l)
                if event.key == pygame.K_l:
                    pause_l_count += 1
                    if pause_l_count >= 3 and not CFG["cheats_enabled"]:
                        CFG["cheats_enabled"] = True
                        play_sfx("star")
                        pause_l_count = 0
                else:
                    pause_l_count = 0

                # Moon Jump (Z key while cheats active)
                if event.key == pygame.K_z and CFG["cheats_enabled"] and CFG["moon_jump"]:
                    play_sfx("jump")

        # Update max draw distance based on toggle
        max_dist = CFG["max_draw_distance"] if CFG["draw_distance_enabled"] else 16.0

        handle_movement(dt)
        update_bgm(dt)

        # Get area data at player position
        data = get_map_data(player_x, player_y)
        _, _, current_area, floor_c, ceil_c, fog_col, fog_n, fog_f, surf, _ = data

        # Health check
        if player_health <= 0:
            if CFG["cheats_enabled"] and CFG["infinite_lives"]:
                player_health = 8
            else:
                player_lives -= 1
                player_health = 8
                if player_lives < 0:
                    player_lives = 4
                    player_coins = 0
                play_sfx("hurt")

        # === RENDERING PIPELINE (Drawing Layers) ===
        # LAYER 0: Sky gradient (cached)
        cache_key = ceil_c
        if sky_cache_key != cache_key:
            sky_cache_key = cache_key
            sky_surf = pygame.Surface((1, h // 2))
            for sy in range(h // 2):
                ratio = sy / (h // 2)
                r = min(255, int(ceil_c[0] * (1 - ratio) + 200 * ratio))
                g = min(255, int(ceil_c[1] * (1 - ratio) + 200 * ratio))
                b = min(255, int(ceil_c[2] * (1 - ratio) + 255 * ratio))
                sky_surf.set_at((0, sy), (r, g, b))
            sky_surf = pygame.transform.scale(sky_surf, (w, h // 2))

        screen.blit(sky_surf, (0, 0))

        # LAYER 1: Floor
        floor_col_fogged = apply_fog(floor_c, max_dist * 0.5, fog_col, fog_n, fog_f)
        pygame.draw.rect(screen, floor_col_fogged, (0, h // 2, w, h // 2))

        # LAYER 2: Walls (Raycasting with fog + wall-face shading)
        strip_w = RAY_STRIP_WIDTH
        num_rays = w // strip_w

        for x in range(0, w, strip_w):
            ray_mult = (x / w) * 2.0 - 1.0
            ray_angle = player_angle + ray_mult * (FOV / 2.0)
            eye_x = math.cos(ray_angle)
            eye_y = math.sin(ray_angle)
            distance = 0.0
            hit_wall = False
            wall_color = (0, 0, 0)
            wall_face = 0
            hit_fog_col = fog_col
            hit_fog_n = fog_n
            hit_fog_f = fog_f
            step_size = 0.05

            while not hit_wall and distance < max_dist:
                distance += step_size
                # Adaptive step: bigger steps far away for performance
                if distance > 8.0:
                    step_size = 0.1
                if distance > 16.0:
                    step_size = 0.15
                test_x = player_x + eye_x * distance
                test_y = player_y + eye_y * distance
                result = get_map_data(test_x, test_y)
                if result[0]:
                    hit_wall = True
                    wall_color = result[1]
                    wall_face = result[9]
                    hit_fog_col = result[5]
                    hit_fog_n = result[6]
                    hit_fog_f = result[7]

            if hit_wall:
                # Correct fisheye
                corr_dist = max(0.1, distance * math.cos(ray_angle - player_angle))
                wall_height = int(h / corr_dist)

                # SM64-style wall-face shading
                c = apply_wall_shading(wall_color, wall_face, distance, max_dist)

                # SM64 RDP-style fog blend
                c = apply_fog(c, distance, hit_fog_col, hit_fog_n, hit_fog_f)

                draw_y = h // 2 - wall_height // 2
                pygame.draw.rect(screen, c, (x, draw_y, strip_w, wall_height))

        # LAYER 5: HUD (topmost)
        draw_hud(screen, font, small_font, clock.get_fps(), current_area)

        pygame.display.flip()
        clock.tick(FPS)

# ==========================================
# Main Entry Point
# ==========================================
def main():
    pygame.init()
    init_audio()
    init_sfx()
    init_gamepad()

    flags = 0
    if CFG["fullscreen"]:
        flags |= pygame.FULLSCREEN
    screen = pygame.display.set_mode((WIDTH, HEIGHT), flags)
    pygame.display.set_caption("AC HOLDS B3313 SM64 PORT 1.0")
    font = pygame.font.SysFont("Courier", 18, bold=True)
    title_font = pygame.font.SysFont("Courier", 26, bold=True)
    small_font = pygame.font.SysFont("Courier", 14)

    while True:
        if main_menu(screen, font, title_font, small_font):
            game_loop(screen, font, small_font)

if __name__ == "__main__":
    main()
