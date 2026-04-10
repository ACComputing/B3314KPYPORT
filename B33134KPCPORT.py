"""
B3313: INTERNAL PLEXUS - PC PORT
A single‑file Pygame raycasting engine inspired by the B3313 ROM hack.
All procedural generation uses only the `math` module.
Controls: WASD / Arrows, ESC for menu.
"""

import pygame
import math
import sys
import time

# ==========================================
# Configuration
# ==========================================
WIDTH, HEIGHT = 800, 600
FPS = 60
N64_SPEED = 0.08
ROT_SPEED = 0.05
FOV = math.pi / 3          # 60°
MAX_DEPTH = 24.0
RAY_STRIP_WIDTH = 2        # Render columns at 2px width for performance

# Player start
player_x = 0.0
player_y = 5.0
player_angle = 0.0
current_area = "Peach's Castle Outskirts"

# ==========================================
# Map Configurations (50 Areas)
# ==========================================
MAP_CONFIGS = [
    {"name": "Peach's Castle Outskirts", "colors": [(120,180,100), (50,100,40), (135,206,235)], "algo": "organic"},
    {"name": "Plexal Lobby", "colors": [(180,180,190), (40,40,50), (20,20,20)], "algo": "pillars"},
    {"name": "Crimson Hallway", "colors": [(150,20,20), (60,10,10), (30,0,0)], "algo": "corridor"},
    {"name": "3rd Floor (beta)", "colors": [(100,150,100), (50,80,50), (150,200,255)], "algo": "maze"},
    {"name": "4th Floor (Final)", "colors": [(200,180,150), (100,80,60), (50,40,30)], "algo": "dense"},
    {"name": "4th Floor (Corrupted)", "colors": [(80,10,10), (20,0,0), (0,0,0)], "algo": "chaos"},
    {"name": "Crescent Castle", "colors": [(80,80,100), (30,30,50), (10,10,20)], "algo": "circular"},
    {"name": "Beta Lobby A", "colors": [(220,220,220), (120,120,120), (60,60,60)], "algo": "pillars"},
    {"name": "Beta Lobby B", "colors": [(200,220,200), (100,120,100), (50,60,50)], "algo": "pillars"},
    {"name": "Beta Lobby C", "colors": [(220,200,200), (120,100,100), (60,50,50)], "algo": "pillars"},
    {"name": "Vanilla Basement", "colors": [(100,100,150), (40,40,80), (20,20,40)], "algo": "corridor"},
    {"name": "Plexal Basement", "colors": [(90,110,130), (30,50,70), (10,20,30)], "algo": "maze"},
    {"name": "AI Undergrounds", "colors": [(40,255,40), (10,50,10), (0,10,0)], "algo": "grid"},
    {"name": "River Mountain", "colors": [(100,200,100), (40,100,40), (135,206,235)], "algo": "organic"},
    {"name": "Castle Grounds (Sunset)", "colors": [(150,100,50), (50,150,50), (255,100,50)], "algo": "organic"},
    {"name": "Uncanny Basement", "colors": [(50,50,50), (20,20,20), (5,5,5)], "algo": "corridor"},
    {"name": "Uncanny Courtyard", "colors": [(100,100,80), (60,60,40), (30,30,20)], "algo": "organic"},
    {"name": "Wet-Dry Paradise (Beta)", "colors": [(50,100,180), (20,40,60), (10,80,100)], "algo": "wave"},
    {"name": "Forgotten Battlefield", "colors": [(80,140,60), (30,70,20), (100,150,255)], "algo": "organic"},
    {"name": "Jolly Roger Bay (beta)", "colors": [(40,80,120), (10,30,60), (5,10,20)], "algo": "wave"},
    {"name": "The Void", "colors": [(30,30,30), (0,0,0), (0,0,0)], "algo": "sparse"},
    {"name": "Monochrome Castle Grounds", "colors": [(128,128,128), (64,64,64), (192,192,192)], "algo": "organic"},
    {"name": "Dark Downtown", "colors": [(60,60,80), (20,20,30), (10,10,15)], "algo": "grid"},
    {"name": "Challenge Lobby", "colors": [(180,150,50), (80,60,20), (40,30,10)], "algo": "maze"},
    {"name": "Hazy Maze Cave (beta)", "colors": [(120,100,150), (60,40,80), (30,20,40)], "algo": "organic"},
    {"name": "Hazy Memory Cave", "colors": [(80,80,100), (30,30,40), (10,10,15)], "algo": "organic"},
    {"name": "Bowser's Checkered Madness", "colors": [(200,50,50), (50,50,50), (0,0,0)], "algo": "grid"},
    {"name": "Big Boo's Haunt (beta)", "colors": [(100,80,60), (40,30,20), (10,5,5)], "algo": "maze"},
    {"name": "Tall, Tall Treetops", "colors": [(130,90,50), (50,120,40), (100,200,255)], "algo": "sparse"},
    {"name": "Star Road (beta)", "colors": [(255,255,150), (100,100,50), (20,20,40)], "algo": "pillars"},
    {"name": "Peach's Secret Slide (beta)", "colors": [(150,150,255), (80,80,150), (40,40,80)], "algo": "corridor"},
    {"name": "Floor 3B", "colors": [(140,160,140), (70,80,70), (40,50,40)], "algo": "dense"},
    {"name": "The Star", "colors": [(255,255,200), (150,150,100), (255,255,255)], "algo": "pillars"},
    {"name": "Motos Factory", "colors": [(100,100,100), (50,50,50), (30,30,30)], "algo": "grid"},
    {"name": "Polygonal Chaos", "colors": [(200,50,200), (50,100,50), (50,50,200)], "algo": "chaos"},
    {"name": "Nebula Lobby", "colors": [(100,50,150), (30,10,50), (10,0,20)], "algo": "circular"},
    {"name": "Cool, Cool Mountain (beta)", "colors": [(200,200,255), (150,150,200), (100,100,150)], "algo": "organic"},
    {"name": "Lethal Lava Land (beta)", "colors": [(200,50,0), (100,20,0), (50,0,0)], "algo": "dense"},
    {"name": "Shifting Sand Land (beta)", "colors": [(210,180,100), (150,120,50), (255,200,100)], "algo": "wave"},
    {"name": "Whomp's Fortress (beta)", "colors": [(150,150,150), (100,100,100), (135,206,235)], "algo": "pillars"},
    {"name": "Dire Dire Docks (beta)", "colors": [(30,60,120), (10,20,50), (5,10,20)], "algo": "circular"},
    {"name": "Tick Tock Clock (beta)", "colors": [(180,140,50), (100,80,20), (50,40,10)], "algo": "grid"},
    {"name": "Rainbow Ride (beta)", "colors": [(255,150,255), (150,200,255), (50,50,100)], "algo": "sparse"},
    {"name": "Endless Stairs", "colors": [(100,0,0), (50,0,0), (20,0,0)], "algo": "corridor"},
    {"name": "Plexal Corridors", "colors": [(150,150,160), (40,40,50), (20,20,20)], "algo": "corridor"},
    {"name": "Water Level (Corrupted)", "colors": [(0,50,100), (0,20,50), (0,10,20)], "algo": "chaos"},
    {"name": "Sky Island", "colors": [(100,200,100), (50,100,50), (135,206,235)], "algo": "sparse"},
    {"name": "Redial", "colors": [(255,0,0), (100,0,0), (50,0,0)], "algo": "chaos"},
    {"name": "The True Core", "colors": [(255,255,255), (200,200,200), (255,255,255)], "algo": "maze"},
    {"name": "The End", "colors": [(0,0,0), (0,0,0), (0,0,0)], "algo": "sparse"}
]

# Map spawn points: each 100 units apart on X axis
MAP_STARTS = [(cfg["name"], i * 100.0, 5.0) for i, cfg in enumerate(MAP_CONFIGS)]

# ==========================================
# Procedural World Generation
# ==========================================
def get_map_data(x, y):
    """Return (is_wall, wall_color, area_name, floor_color, ceiling_color)"""
    ix = x + 0.0001
    iy = y + 0.0001

    zone_index = int(max(0, x) // 100)
    if zone_index >= len(MAP_CONFIGS):
        zone_index = len(MAP_CONFIGS) - 1

    config = MAP_CONFIGS[zone_index]
    algo = config["algo"]
    wall_col, floor_col, ceil_col = config["colors"]
    area_name = config["name"]

    # Safe spawn circle
    dx_spawn = x - (zone_index * 100.0)
    dy_spawn = y - 5.0
    if math.sqrt(dx_spawn*dx_spawn + dy_spawn*dy_spawn) < 2.0:
        return False, (0,0,0), area_name, floor_col, ceil_col

    wall = False
    if algo == "pillars":
        wall = (math.sin(ix) * math.cos(iy)) > 0.8
    elif algo == "corridor":
        wall = math.sin(ix * 1.5) + math.cos(iy * 0.2) > 0.6
    elif algo == "maze":
        wall = math.sin(ix) + math.cos(iy) + math.sin(ix*iy*0.5) > 1.0
    elif algo == "dense":
        wall = math.cos(ix * 2) * math.sin(iy * 2) > 0.2
    elif algo == "chaos":
        wall = math.sin(ix * 1.3) * math.cos(iy * 1.7) + math.sin(ix * iy) > 0.8
    elif algo == "circular":
        wall = math.sin(math.sqrt(ix*ix + iy*iy)) > 0.5
    elif algo == "grid":
        wall = (math.sin(ix * 2) > 0.8) or (math.cos(iy * 2) > 0.8)
    elif algo == "organic":
        wall = math.sin(ix * 0.8) + math.cos(iy * 0.8) + math.sin(ix * iy * 0.1) > 1.2
    elif algo == "wave":
        lx, ly = ix % 100, iy % 100
        wall = math.sin(math.sqrt((lx-50)**2 + (ly-50)**2) * 1.5) > 0.5
    elif algo == "sparse":
        wall = (math.sin(ix * 0.2) * math.cos(iy * 0.2)) > 0.95

    return wall, wall_col, area_name, floor_col, ceil_col

# ==========================================
# Player Movement & Collision
# ==========================================
def handle_movement():
    global player_x, player_y, player_angle
    keys = pygame.key.get_pressed()

    if keys[pygame.K_LEFT] or keys[pygame.K_a]:
        player_angle -= ROT_SPEED
    if keys[pygame.K_RIGHT] or keys[pygame.K_d]:
        player_angle += ROT_SPEED

    move_step = N64_SPEED
    dx = math.cos(player_angle) * move_step
    dy = math.sin(player_angle) * move_step

    if keys[pygame.K_UP] or keys[pygame.K_w]:
        if not get_map_data(player_x + dx * 2, player_y)[0]:
            player_x += dx
        if not get_map_data(player_x, player_y + dy * 2)[0]:
            player_y += dy

    if keys[pygame.K_DOWN] or keys[pygame.K_s]:
        if not get_map_data(player_x - dx * 2, player_y)[0]:
            player_x -= dx
        if not get_map_data(player_x, player_y - dy * 2)[0]:
            player_y -= dy

# ==========================================
# UI Screens
# ==========================================
def show_info_screen(screen, font, title_font, title, lines):
    clock = pygame.time.Clock()
    in_screen = True
    while in_screen:
        screen.fill((10, 10, 15))
        title_text = title_font.render(title, True, (200, 200, 255))
        screen.blit(title_text, (WIDTH//2 - title_text.get_width()//2, 60))

        for i, line in enumerate(lines):
            line_text = font.render(line, True, (150, 150, 150))
            screen.blit(line_text, (WIDTH//2 - line_text.get_width()//2, 130 + i*35))

        pygame.display.flip()
        clock.tick(FPS)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key in (pygame.K_ESCAPE, pygame.K_RETURN):
                    in_screen = False

def level_select_menu(screen, font, title_font):
    global player_x, player_y
    selected = 0
    clock = pygame.time.Clock()
    in_menu = True

    while in_menu:
        screen.fill((10, 10, 15))

        title_text = title_font.render("SELECT MAP", True, (200, 200, 255))
        subtitle = font.render("Arrows + Enter (ESC to go back)", True, (150, 150, 150))
        screen.blit(title_text, (WIDTH//2 - title_text.get_width()//2, 60))
        screen.blit(subtitle, (WIDTH//2 - subtitle.get_width()//2, 110))

        max_visible = 10
        start_i = max(0, selected - max_visible//2)
        end_i = min(len(MAP_STARTS), start_i + max_visible)
        if end_i - start_i < max_visible:
            start_i = max(0, end_i - max_visible)

        for i in range(start_i, end_i):
            map_name = MAP_STARTS[i][0]
            if i == selected:
                color = (255, 255, 0)
                prefix = "> "
            else:
                color = (100, 100, 100)
                prefix = "  "
            option_text = font.render(f"{prefix}{map_name}", True, color)
            screen.blit(option_text, (WIDTH//2 - 180, 180 + (i - start_i)*35))

        pygame.display.flip()
        clock.tick(FPS)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_ESCAPE:
                    return False
                elif event.key == pygame.K_UP:
                    selected = (selected - 1) % len(MAP_STARTS)
                elif event.key == pygame.K_DOWN:
                    selected = (selected + 1) % len(MAP_STARTS)
                elif event.key == pygame.K_RETURN:
                    player_x = MAP_STARTS[selected][1]
                    player_y = MAP_STARTS[selected][2]
                    return True

def main_menu(screen, font, title_font):
    options = ["Resume Game", "Select Map", "About", "Help", "Credits", "Settings", "Exit Game"]
    selected = 0
    clock = pygame.time.Clock()
    in_menu = True

    while in_menu:
        screen.fill((10, 10, 15))

        title_text = title_font.render("B3313: INTERNAL PLEXUS", True, (200, 200, 255))
        subtitle = font.render("MAIN MENU (Arrows + Enter)", True, (150, 150, 150))
        screen.blit(title_text, (WIDTH//2 - title_text.get_width()//2, 60))
        screen.blit(subtitle, (WIDTH//2 - subtitle.get_width()//2, 110))

        for i, option in enumerate(options):
            color = (255, 255, 0) if i == selected else (100, 100, 100)
            prefix = "> " if i == selected else "  "
            text = font.render(f"{prefix}{option}", True, color)
            screen.blit(text, (WIDTH//2 - 120, 180 + i*45))

        pygame.display.flip()
        clock.tick(FPS)

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN:
                if event.key == pygame.K_UP:
                    selected = (selected - 1) % len(options)
                elif event.key == pygame.K_DOWN:
                    selected = (selected + 1) % len(options)
                elif event.key == pygame.K_RETURN:
                    if selected == 0:   # Resume
                        return True
                    elif selected == 1: # Select Map
                        if level_select_menu(screen, font, title_font):
                            return True
                    elif selected == 2: # About
                        show_info_screen(screen, font, title_font, "ABOUT",
                                         ["B3313: Internal Plexus - PC Port",
                                          "A procedural Pygame raycasting engine.",
                                          "Inspired by the B3313 ROM hack.",
                                          "", "Press ESC to return."])
                    elif selected == 3: # Help
                        show_info_screen(screen, font, title_font, "HELP",
                                         ["CONTROLS:",
                                          "W/S or UP/DOWN : Move",
                                          "A/D or L/R     : Turn",
                                          "ESC            : Menu",
                                          "", "Press ESC to return."])
                    elif selected == 4: # Credits
                        show_info_screen(screen, font, title_font, "CREDITS",
                                         ["Engine & Demake by B3313 Community",
                                          "Procedural generation using math only.",
                                          "", "Press ESC to return."])
                    elif selected == 5: # Settings
                        show_info_screen(screen, font, title_font, "SETTINGS",
                                         ["FPS: 60 | FOV: 60°",
                                          "Render distance: 24 units",
                                          "Strip width: 2px",
                                          "", "(Modify source to tweak)",
                                          "", "Press ESC to return."])
                    elif selected == 6: # Exit
                        pygame.quit()
                        sys.exit()

    return True

# ==========================================
# Main Game Loop
# ==========================================
def game_loop(screen, font):
    global current_area, player_x, player_y, player_angle
    clock = pygame.time.Clock()
    running = True

    while running:
        # Events
        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                pygame.quit()
                sys.exit()
            if event.type == pygame.KEYDOWN and event.key == pygame.K_ESCAPE:
                return  # exit to menu

        handle_movement()

        # Get environment info
        _, _, current_area, floor_c, ceil_c = get_map_data(player_x, player_y)

        # Draw ceiling / floor
        pygame.draw.rect(screen, ceil_c, (0, 0, WIDTH, HEIGHT//2))
        pygame.draw.rect(screen, floor_c, (0, HEIGHT//2, WIDTH, HEIGHT//2))

        # Raycasting
        for x in range(0, WIDTH, RAY_STRIP_WIDTH):
            ray_mult = (x / WIDTH) * 2.0 - 1.0
            ray_angle = player_angle + ray_mult * (FOV / 2.0)

            eye_x = math.cos(ray_angle)
            eye_y = math.sin(ray_angle)

            distance = 0.0
            hit_wall = False
            wall_color = (0,0,0)

            step = 0.05
            while not hit_wall and distance < MAX_DEPTH:
                distance += step
                test_x = player_x + eye_x * distance
                test_y = player_y + eye_y * distance
                is_wall, color, _, _, _ = get_map_data(test_x, test_y)
                if is_wall:
                    hit_wall = True
                    wall_color = color
                    break

            if hit_wall:
                # Correct fisheye
                corr_dist = distance * math.cos(ray_angle - player_angle)
                if corr_dist < 0.1:
                    corr_dist = 0.1

                wall_height = int(HEIGHT / corr_dist)

                # Distance fog
                shade = 1.0 - (distance / MAX_DEPTH)
                shade = max(0.0, min(1.0, shade))
                r = int(wall_color[0] * shade)
                g = int(wall_color[1] * shade)
                b = int(wall_color[2] * shade)

                y1 = max(0, HEIGHT//2 - wall_height//2)
                y2 = min(HEIGHT, HEIGHT//2 + wall_height//2)
                pygame.draw.rect(screen, (r, g, b), (x, y1, RAY_STRIP_WIDTH, y2 - y1))

        # HUD
        info_bg = pygame.Surface((380, 80))
        info_bg.set_alpha(180)
        info_bg.fill((10,10,10))
        screen.blit(info_bg, (10, 10))

        area_txt = font.render(f"AREA: {current_area}", True, (255,255,0))
        pos_txt  = font.render(f"X: {player_x:.1f}  Y: {player_y:.1f}", True, (255,255,255))
        fps_txt  = font.render(f"FPS: {int(clock.get_fps())} | N64 MODE", True, (0,255,255))

        screen.blit(area_txt, (20, 20))
        screen.blit(pos_txt,  (20, 45))
        screen.blit(fps_txt,  (20, 70))

        # Crosshair
        pygame.draw.circle(screen, (255,255,255), (WIDTH//2, HEIGHT//2), 2)

        pygame.display.flip()
        clock.tick(FPS)

# ==========================================
# Entry Point
# ==========================================
def main():
    pygame.init()
    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("B3313: Internal Plexus - PC Port")
    font = pygame.font.SysFont("Courier", 18, bold=True)
    title_font = pygame.font.SysFont("Courier", 32, bold=True)

    # Start directly in game
    game_loop(screen, font)

    # Then main menu loop
    while True:
        if main_menu(screen, font, title_font):
            game_loop(screen, font)

if __name__ == "__main__":
    main()
