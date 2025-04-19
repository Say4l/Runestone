import os # Easy, nothing to explain here
import glob # Also easy, nothing to explain here
import pygame # Well... well... well... I don't know what to say
import sys # I'm not sure what to say about this one
import pytmx # This one... basically it's a library for reading Tiled maps
from pytmx.util_pygame import load_pygame # This one is for loading the Tiled maps
from PIL import Image  # This one is for loading the GIF images
from moviepy.editor import VideoFileClip # This one is for playing the intro video



# THANK YOU FOR REMEMBERING THAT THIS STUPID FADE IN AND OUT IS NOT WORKING
# I'M SO HAPPY THAT I REMEMBERED THAT
ORIGIN_SUBTRACT_MULTIPLIER = 0
CONVERT_COLLISION_ORIGIN = True
FADE_DURATION = 1.0  # seconds for fade out/in

DEBUG_DRAW_TRANSITIONS = True  # for debugging transition objects

# --- Helper Functions ---
def get_object_rect(obj):
    if CONVERT_COLLISION_ORIGIN:
        return pygame.Rect(obj.x, obj.y - ORIGIN_SUBTRACT_MULTIPLIER * obj.height, obj.width, obj.height)
    else:
        return pygame.Rect(obj.x, obj.y, obj.width, obj.height)

def clamp(val, min_val, max_val):
    return max(min_val, min(val, max_val))

def lerp(a, b, t):
    return a + (b - a) * t

# --- Map and Object Loading Functions ---
def load_all_maps(): ## this function is for loading all the maps
    maps = {}
    directory = os.path.dirname(os.path.abspath(__file__))
    for filepath in glob.glob(os.path.join(directory, "*.tmx")):
        try:
            tmx = load_pygame(filepath)
            map_id = os.path.splitext(os.path.basename(filepath))[0]
            maps[map_id] = tmx
            print(f"Loaded map '{map_id}' from {filepath}")
        except Exception as e:
            print(f"Error loading map {filepath}: {e}")
    return maps

def load_transition_objects(tmx_data, layer_name):
    transitions = []
    for group in tmx_data.objectgroups:
        if group.name.lower() == layer_name.lower():
            for obj in group:
                if "target_map" in obj.properties:
                    target_map = obj.properties["target_map"].strip()
                elif "transition_id" in obj.properties:
                    try:
                        target_map = str(int(obj.properties["transition_id"]))
                    except ValueError:
                        target_map = obj.properties["transition_id"].strip()
                else:
                    continue
                rect = get_object_rect(obj)
                transitions.append({"rect": rect, "target": target_map})
    return transitions

def point_in_poly(x, y, poly): # This function is for checking if a point is inside a polygon 
    num = len(poly)
    j = num - 1
    inside = False
    for i in range(num):
        xi, yi = poly[i]
        xj, yj = poly[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / ((yj - yi) + 1e-9) + xi):
            inside = not inside
        j = i
    return inside

def rect_polygon_collision(rect, poly):
    corners = [(rect.left, rect.top), (rect.right, rect.top),
               (rect.right, rect.bottom), (rect.left, rect.bottom)]
    for corner in corners:
        if point_in_poly(corner[0], corner[1], poly):
            return True
    for pt in poly:
        if rect.collidepoint(pt):
            return True
    return False

def resolve_horizontal_poly(initial_x, y, dx, width, height, collision_shapes):
    step = 1 if dx > 0 else -1
    allowed_dx = 0
    for i in range(0, int(abs(dx)) + 1):
        new_dx = step * i
        test_rect = pygame.Rect(initial_x + new_dx - width//2, y - height//2, width, height)
        if any(rect_polygon_collision(test_rect, poly) for poly in collision_shapes):
            break
        allowed_dx = new_dx
    return allowed_dx

def resolve_vertical_poly(x, initial_y, dy, width, height, collision_shapes):
    step = 1 if dy > 0 else -1
    allowed_dy = 0
    for i in range(0, int(abs(dy)) + 1):
        new_dy = step * i
        test_rect = pygame.Rect(x - width//2, initial_y + new_dy - height//2, width, height)
        if any(rect_polygon_collision(test_rect, poly) for poly in collision_shapes):
            break
        allowed_dy = new_dy
    return allowed_dy

def load_collision_shapes(tmx_data): # This function is for loading the collision shapes 
    shapes = []
    for group in tmx_data.objectgroups:
        if group.name.lower() == "collision":
            for obj in group:
                if hasattr(obj, 'points') and obj.points:
                    points = [(point.x, point.y - (ORIGIN_SUBTRACT_MULTIPLIER * obj.height if CONVERT_COLLISION_ORIGIN else 0))
                              for point in obj.points]
                else:
                    if CONVERT_COLLISION_ORIGIN:
                        points = [(obj.x, obj.y - ORIGIN_SUBTRACT_MULTIPLIER * obj.height),
                                  (obj.x + obj.width, obj.y - ORIGIN_SUBTRACT_MULTIPLIER * obj.height),
                                  (obj.x + obj.width, obj.y),
                                  (obj.x, obj.y)]
                    else:
                        points = [(obj.x, obj.y),
                                  (obj.x + obj.width, obj.y),
                                  (obj.x + obj.width, obj.y + obj.height),
                                  (obj.x, obj.y + obj.height)]
                if points and len(points) >= 3:
                    shapes.append(points)
    print(f"Total collision shapes loaded: {len(shapes)}")
    return shapes

def load_text_objects(tmx_data): # This function is for loading the text objects
    text_objects = []
    for group in tmx_data.objectgroups:
        if group.name.lower() == "text":
            for obj in group:
                messages = []
                for key, value in obj.properties.items():
                    if isinstance(value, str) and value.strip():
                        msgs = [msg.strip() for msg in value.split('|') if msg.strip()]
                        messages.extend(msgs)
                if messages:
                    rect = get_object_rect(obj)
                    text_objects.append({"rect": rect, "text": messages})
    return text_objects

def world_to_screen(point, camera_x, camera_y):
    return (point[0] - camera_x, point[1] - camera_y)

def wrap_text(text, font, max_width):
    words = text.split(' ')
    lines = []
    current_line = ""
    for word in words:
        test_line = current_line + (" " if current_line else "") + word
        if font.size(test_line)[0] <= max_width:
            current_line = test_line
        else:
            lines.append(current_line)
            current_line = word
    if current_line:
        lines.append(current_line)
    return lines

def draw_dialogue_box(surface, text, font): #   This function is for drawing the dialogue box
    border_padding = 20
    box_rect = pygame.Rect(0, WINDOW_HEIGHT * 3 // 4, WINDOW_WIDTH, WINDOW_HEIGHT // 4)
    pygame.draw.rect(surface, (128, 128, 128), box_rect)
    inner_rect = pygame.Rect(box_rect.x + border_padding, box_rect.y + border_padding,
                             box_rect.width - 2 * border_padding, box_rect.height - 2 * border_padding)
    pygame.draw.rect(surface, (255, 255, 255), inner_rect)
    # Word-wrap and center text both horizontally and vertically.
    lines = wrap_text(text, font, inner_rect.width)
    total_text_height = len(lines) * font.get_linesize()
    start_y = inner_rect.y + (inner_rect.height - total_text_height) // 2
    for i, line in enumerate(lines):
        line_surf = font.render(line, True, (0, 0, 0))
        start_x = inner_rect.x + (inner_rect.width - line_surf.get_width()) // 2
        surface.blit(line_surf, (start_x, start_y + i * font.get_linesize()))

def slow_print(full_text, elapsed_time, chars_per_sec=20):
    num_chars = int(elapsed_time * chars_per_sec)
    return full_text if num_chars >= len(full_text) else full_text[:num_chars]

def load_gif_frames(filename): # This function is for loading the GIF frames
    frames = []
    pil_img = Image.open(filename)
    try:
        while True:
            frame = pil_img.copy().convert('RGBA')
            image = pygame.image.fromstring(frame.tobytes(), frame.size, frame.mode)
            frames.append(image)
            pil_img.seek(pil_img.tell() + 1)
    except EOFError:
        pass
    return frames

# --- Pygame Initialization & Window Setup ---
pygame.init()
font = pygame.font.SysFont(None, 24)

# Grid and camera dimensions.
CAM_WIDTH = 640
CAM_HEIGHT = 360
FOLLOW_WIDTH = CAM_WIDTH // 2
FOLLOW_HEIGHT = CAM_HEIGHT // 2

WINDOW_WIDTH = 1920
WINDOW_HEIGHT = 1080
window = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT))
pygame.display.set_caption("Runestone")
pygame.display.set_icon(pygame.image.load("assets/CoverPic.jpg"))

#Resizable window
display_info = pygame.display.Info()
WINDOW_WIDTH, WINDOW_HEIGHT = display_info.current_w, display_info.current_h
window = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.RESIZABLE)

#Function to play intro
def play_intro():
    try:
        clip = VideoFileClip("assets/INTRO.mp4")
        clip.preview(fps=30)  # Limit FPS for smoother playback
        clip.close()
    except Exception as e:
        print(f"Error playing intro: {e}")

# Play the intro
play_intro()


# --- Fullscreen Toggle Function ---
fullscreen = False
fade_surface = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.SRCALPHA)
def toggle_fullscreen():
    global fullscreen, window, WINDOW_WIDTH, WINDOW_HEIGHT
    fullscreen = not fullscreen
    if fullscreen:
        display_info = pygame.display.Info()
        WINDOW_WIDTH, WINDOW_HEIGHT = display_info.current_w, display_info.current_h
        window = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.FULLSCREEN)
    else:
        WINDOW_WIDTH, WINDOW_HEIGHT = 1920, 1080  # Default window size
        window = pygame.display.set_mode((WINDOW_WIDTH, WINDOW_HEIGHT), pygame.RESIZABLE)

# --- Load Maps & Setup ---
maps = load_all_maps()
current_map_id = "map"  # Default map to start with TMX file is default, should be main lobby
if current_map_id not in maps:
    print(f"Default map '{current_map_id}' not found.")
    sys.exit(1)
tmx_data = maps[current_map_id]
map_width = tmx_data.width * tmx_data.tilewidth
map_height = tmx_data.height * tmx_data.tileheight
collision_shapes = load_collision_shapes(tmx_data)
text_objects = load_text_objects(tmx_data)
transition_to_objs = load_transition_objects(tmx_data, "Transition_To")
transition_from_objs = load_transition_objects(tmx_data, "Transition_From")

#Fullscreen
for event in pygame.event.get():
    if event.type == pygame.KEYDOWN:
        if event.key == pygame.K_f:  # Press 'F' to toggle fullscreen
            toggle_fullscreen()


player_spawn = None
startscreen_box = None
for group in tmx_data.objectgroups:
    if group.name.lower() == "startscreen":
        for obj in group:
            startscreen_box = get_object_rect(obj)
            break
    elif group.name.lower() == "player":
        for obj in group:
            rect = get_object_rect(obj)
            player_spawn = (rect.x + rect.width/2, rect.y + rect.height/2)
            break

if startscreen_box:
    CAM_WIDTH = min(startscreen_box.width, 1920)
    CAM_HEIGHT = min(startscreen_box.height, 1080)
    FOLLOW_WIDTH = CAM_WIDTH // 2
    FOLLOW_HEIGHT = CAM_HEIGHT // 2

def get_cell(x, y): #   This function is for getting the cell
    return (int(x // CAM_WIDTH), int(y // CAM_HEIGHT))

if player_spawn:
    current_cell = get_cell(player_spawn[0], player_spawn[1])
else:
    current_cell = (0, 0)

# --- Camera and Follow Logic. Transition points!!
def get_follow_cam(player_x, player_y, cell):
    cell_x = cell[0] * CAM_WIDTH
    cell_y = cell[1] * CAM_HEIGHT
    raw_x = player_x - FOLLOW_WIDTH / 2
    raw_y = player_y - FOLLOW_HEIGHT / 2
    follow_x = clamp(raw_x, cell_x, cell_x + CAM_WIDTH - FOLLOW_WIDTH)
    follow_y = clamp(raw_y, cell_y, cell_y + CAM_HEIGHT - FOLLOW_HEIGHT)
    return follow_x, follow_y

transitioning = False
transition_duration = 1.75  # seconds
transition_timer = 0
prev_cam_offset = (0, 0)
target_cam_offset = (0, 0)

# --- Player Setup ---
player = {
    "x": player_spawn[0] if player_spawn else CAM_WIDTH/2,
    "y": player_spawn[1] if player_spawn else CAM_HEIGHT/2,
    "speed": 80,  # pixels per second, average speed of player. Maybe changable !!!!!!!!
    "direction": "down",
    "anim_index": 0,
    "anim_timer": 0,
    "anim_speed": 0.1,
    "frames": {
         "up": load_gif_frames("assets/player_walk_up.gif"),
         "left": load_gif_frames("assets/player_walk_left.gif"),
         "down": load_gif_frames("assets/player_walk_down.gif"),
         "right": [pygame.transform.flip(frame, True, False) for frame in load_gif_frames("assets/player_walk_left.gif")]
    }
}
player["width"] = player["frames"]["down"][0].get_width()
player["height"] = player["frames"]["down"][0].get_height()
player["normal_frame"] = player["frames"]["down"][0]
player["current_sprite"] = player["normal_frame"]

# --- Load Attack Sprites ---
player["attack_up"] = pygame.image.load("assets/player_attack_up.png").convert_alpha()    
player["attack_down"] = pygame.image.load("assets/player_attack_down.png").convert_alpha()
player["attack_left"] = pygame.image.load("assets/player_attack_left.png").convert_alpha()
player["attack_right"] = pygame.transform.flip(player["attack_left"], True, False)

# --- Load Sword Attack Image ---
if os.path.exists("assets/player_sword.gif"):
    player_sword_img = load_gif_frames("assets/player_sword.gif")[0]
else:
    player_sword_img = None

# --- Attack State Variables ---
attacking = False         # True while an attack animation is active.
active_sword = None       # Holds sword attack info.
sword_offset = (0, 0)     # Computed based on player direction.
attack_cooldown = 0       # Delay (in seconds) before the next attack can be initiated.
ATTACK_DELAY = 0.4        # Cooldown delay between attacks.
ATTACK_DURATION = 0.3     # Attack lasts for 0.3 seconds.
attack_timer = 0          # Timer for the current attack.

# --- Dialogue and Fade Variables ---
dialogue_active = False
dialogue_texts = []
dialogue_index = 0
dialogue_elapsed_time = 0.0
CHARS_PER_SEC = 20

fading = False
fade_alpha = 0
fade_direction = 1
fade_surface = pygame.Surface((WINDOW_WIDTH, WINDOW_HEIGHT))
fade_surface.fill((0, 0, 0))
fade_surface.set_alpha(fade_alpha)
next_map_id = None

clock = pygame.time.Clock()
running = True

# We'll track the previous state of Z to detect taps.
z_prev = False

# --- Main Game Loop, also add sword attack and dialogue progression, either way it sucks ---
while running:
    dt = clock.tick(60) / 1000.0

    # Update attack cooldown timer.
    if attack_cooldown > 0:
        attack_cooldown -= dt
        if attack_cooldown < 0:
            attack_cooldown = 0

    # Get current state of Z key.
    keys = pygame.key.get_pressed()
    z_current = keys[pygame.K_z]

    for event in pygame.event.get():
        if event.type == pygame.QUIT:
            running = False

        elif event.type == pygame.KEYDOWN:
            if event.key == pygame.K_ESCAPE:
                running = False
            # Only update direction if not in dialogue and not transitioning.
            elif event.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN) and not dialogue_active and not transitioning:
                if not attacking:
                    if event.key == pygame.K_LEFT:
                        player["direction"] = "left"
                    elif event.key == pygame.K_RIGHT:
                        player["direction"] = "right"
                    elif event.key == pygame.K_UP:
                        player["direction"] = "up"
                    elif event.key == pygame.K_DOWN:
                        player["direction"] = "down"
        # Remove KEYUP for Z attack termination so the attack lasts full duration.
        elif event.type == pygame.KEYUP:
            if event.key in (pygame.K_LEFT, pygame.K_RIGHT, pygame.K_UP, pygame.K_DOWN) and not dialogue_active and not transitioning:
                # On key release, update player direction based on currently held keys.
                if keys[pygame.K_LEFT]:
                    player["direction"] = "left"
                elif keys[pygame.K_RIGHT]:
                    player["direction"] = "right"
                elif keys[pygame.K_UP]:
                    player["direction"] = "up"
                elif keys[pygame.K_DOWN]:
                    player["direction"] = "down"

    # If not in dialogue, not transitioning, not playing with my nerves and not attacking, update direction continuously from held arrow keys.
    if not dialogue_active and not transitioning and not attacking:
        if keys[pygame.K_LEFT]:
            player["direction"] = "left"
        elif keys[pygame.K_RIGHT]:
            player["direction"] = "right"
        elif keys[pygame.K_UP]:
            player["direction"] = "up"
        elif keys[pygame.K_DOWN]:
            player["direction"] = "down"



    # Update dialogue elapsed time !!!!!!!! IMPORTANT !!!!!!!! IT'S SHOWING ERROR, FIX IT ARMAN !!!!
    if dialogue_active:
        dialogue_elapsed_time += dt

    # --- Handle Z key taps (for dialogue progression OR attack) ---
    if z_current and not z_prev:
        if dialogue_active:
            # Progress dialogue.
            full_message = dialogue_texts[dialogue_index]
            # If the message is not yet fully printed, finish it immediately.
            if slow_print(full_message, dialogue_elapsed_time, CHARS_PER_SEC) != full_message:
                dialogue_elapsed_time = len(full_message) / CHARS_PER_SEC
            else:
                dialogue_index += 1
                if dialogue_index >= len(dialogue_texts):
                    dialogue_active = False
                else:
                    dialogue_elapsed_time = 0.0
        else:
            # First check if the player is colliding with a text object.
            player_rect = pygame.Rect(player["x"] - player["width"]//2,
                                      player["y"] - player["height"]//2,
                                      player["width"], player["height"])
            colliding_text = any(player_rect.colliderect(text_obj["rect"]) for text_obj in text_objects)
            if colliding_text:
                dialogue_active = True
                for text_obj in text_objects:
                    if player_rect.colliderect(text_obj["rect"]):
                        dialogue_texts = text_obj["text"]
                        dialogue_index = 0
                        dialogue_elapsed_time = 0.0
                        break
            # Otherwise, if no text is present and if the attack cooldown has elapsed, trigger an attack.
            elif attack_cooldown <= 0 and not attacking and not transitioning and not fading and player_sword_img is not None:
                attacking = True
                attack_timer = 0  # Start the attack timer.
                if player["direction"] == "up":
                    player["current_sprite"] = player["attack_up"]
                    sword_offset = (-5, -player["height"])
                elif player["direction"] == "down":
                    player["current_sprite"] = player["attack_down"]
                    sword_offset = (+5, player["height"])
                elif player["direction"] == "left":
                    player["current_sprite"] = player["attack_left"]
                    sword_offset = (-player["width"], 5)
                elif player["direction"] == "right":
                    player["current_sprite"] = player["attack_right"]
                    sword_offset = (player["width"], 5)
                if player["direction"] == "up":
                    rotated_sword = player_sword_img
                elif player["direction"] == "right":
                    rotated_sword = pygame.transform.rotate(player_sword_img, -90)
                elif player["direction"] == "down":
                    rotated_sword = pygame.transform.flip(player_sword_img, False, True)
                elif player["direction"] == "left":
                    rotated_sword = pygame.transform.rotate(player_sword_img, 90)
                active_sword = {
                    "image": rotated_sword,
                    "x": player["x"] + sword_offset[0],
                    "y": player["y"] + sword_offset[1],
                    "layer": "Sword"
                }
    z_prev = z_current

    # --- Update Attack Timer if Attacking ---
    if attacking:
        # Update the sword position based on player position and direction.
        if active_sword is not None:
            active_sword["x"] = player["x"] + sword_offset[0]
            active_sword["y"] = player["y"] + sword_offset[1]
        attack_timer += dt
        if attack_timer >= ATTACK_DURATION:
            attacking = False
            active_sword = None
            attack_cooldown = ATTACK_DELAY

    # --- Update Player Movement & Animation ---
    # Player movement is disabled during dialogue, fading, transitioning, or attacking.
    if not fading and not dialogue_active and not transitioning and not attacking:
        horiz = (1 if keys[pygame.K_RIGHT] else 0) - (1 if keys[pygame.K_LEFT] else 0)
        vert  = (1 if keys[pygame.K_DOWN] else 0) - (1 if keys[pygame.K_UP] else 0)
        dx = horiz * player["speed"] * dt
        dy = vert * player["speed"] * dt
        if horiz != 0 or vert != 0:
            player["anim_timer"] += dt
            if player["anim_timer"] >= player["anim_speed"]:
                player["anim_timer"] -= player["anim_speed"]
                player["anim_index"] = (player["anim_index"] + 1) % len(player["frames"][player["direction"]])
        else:
            player["anim_index"] = 0
            player["anim_timer"] = 0
        allowed_dx = resolve_horizontal_poly(player["x"], player["y"], dx, player["width"], player["height"], collision_shapes)
        player["x"] += allowed_dx
        allowed_dy = resolve_vertical_poly(player["x"], player["y"], dy, player["width"], player["height"], collision_shapes)
        player["y"] += allowed_dy

    # --- Check for Map Transition Triggers (skip if attacking) ---
    if not fading and not dialogue_active and not attacking:
        player_rect = pygame.Rect(player["x"] - player["width"]//2,
                                  player["y"] - player["height"]//2,
                                  player["width"], player["height"])
        for trans in transition_to_objs:
            if player_rect.colliderect(trans["rect"]):
                next_map_id = trans["target"]
                fading = True
                fade_direction = 1
                fade_alpha = 0
                break

    # --- Update Fade Transition ---
    if fading:
        fade_alpha += fade_direction * (255/FADE_DURATION) * dt
        if fade_alpha >= 255 and fade_direction == 1:
            fade_alpha = 255
            if next_map_id in maps:
                tmx_data = maps[next_map_id]
                current_map_id = next_map_id
                map_width = tmx_data.width * tmx_data.tilewidth
                map_height = tmx_data.height * tmx_data.tileheight
                collision_shapes = load_collision_shapes(tmx_data)
                text_objects = load_text_objects(tmx_data)
                transition_to_objs = load_transition_objects(tmx_data, "Transition_To")
                transition_from_objs = load_transition_objects(tmx_data, "Transition_From")
                if transition_from_objs:
                    trans = transition_from_objs[0]
                    player["x"] = trans["rect"].x + trans["rect"].width/2
                    player["y"] = trans["rect"].y + trans["rect"].height/2
                current_cell = get_cell(player["x"], player["y"])
            fade_direction = -1
        elif fade_alpha <= 0 and fade_direction == -1:
            fade_alpha = 0
            fading = False
        fade_surface.set_alpha(int(fade_alpha))

    # --- Camera Update ---
    new_cell = get_cell(player["x"], player["y"])
    if new_cell != current_cell and not transitioning and not attacking:
        prev_cam_offset = get_follow_cam(player["x"], player["y"], current_cell)
        target_cam_offset = get_follow_cam(player["x"], player["y"], new_cell)
        transition_timer = 0
        transitioning = True

    if not transitioning:
        cam_x, cam_y = get_follow_cam(player["x"], player["y"], current_cell)
        view_width, view_height = FOLLOW_WIDTH, FOLLOW_HEIGHT
    else:
        transition_timer += dt
        t_val = min(transition_timer / transition_duration, 1.0)
        cam_x = lerp(prev_cam_offset[0], target_cam_offset[0], t_val)
        cam_y = lerp(prev_cam_offset[1], target_cam_offset[1], t_val)
        view_width, view_height = FOLLOW_WIDTH, FOLLOW_HEIGHT
        if t_val >= 1.0:
            transitioning = False
            current_cell = new_cell
    
    # --- Render Map & Layers ---
    virtual_surface = pygame.Surface((view_width, view_height))
    virtual_surface.fill((0, 0, 0))
    for layer in tmx_data.visible_layers:
        if hasattr(layer, "data"):
            for x, y, gid in layer:
                tile = tmx_data.get_tile_image_by_gid(gid)
                if tile:
                    virtual_surface.blit(tile, (x * tmx_data.tilewidth - cam_x,
                                                 y * tmx_data.tileheight - cam_y))
    # --- Debug: Draw Collision & Transition Objects & Why I have this useless red dot in my monitor ---
    DEBUG_DRAW_COLLISION = False # for debugging collision shapes
    if DEBUG_DRAW_COLLISION:
        for shape in collision_shapes:
            points = [world_to_screen((x, y), cam_x, cam_y) for (x, y) in shape]
            if len(points) >= 3:
                pygame.draw.polygon(virtual_surface, (0, 255, 0), points, 2)
                for point in points:
                    pygame.draw.circle(virtual_surface, (255, 255, 0), (int(point[0]), int(point[1])), 2)
    if DEBUG_DRAW_TRANSITIONS:
        for trans in transition_to_objs:
            r = trans["rect"]
            r_screen = pygame.Rect(r.x - cam_x, r.y - cam_y, r.width, r.height)
            pygame.draw.rect(virtual_surface, (0, 0, 255), r_screen, 2)
        for trans in transition_from_objs:
            r = trans["rect"]
            r_screen = pygame.Rect(r.x - cam_x, r.y - cam_y, r.width, r.height)
            pygame.draw.rect(virtual_surface, (255, 0, 0), r_screen, 2)

    # --- Draw the Player ---
    current_frame = player["frames"][player["direction"]][player["anim_index"]]
    virtual_surface.blit(current_frame, (player["x"] - cam_x - player["width"]//2,
                                          player["y"] - cam_y - player["height"]//2))
    if attacking and active_sword is not None:
        virtual_surface.blit(player["current_sprite"], (player["x"] - cam_x - player["current_sprite"].get_width()//2,
                                                         player["y"] - cam_y - player["current_sprite"].get_height()//2))
        sword_img = active_sword["image"]
        virtual_surface.blit(sword_img, (active_sword["x"] - cam_x - sword_img.get_width()//2,
                                         active_sword["y"] - cam_y - sword_img.get_height()//2))
    # --- Blit to Window & Draw Dialogue Box ---
    try:
        scaled = pygame.transform.scale(virtual_surface, (WINDOW_WIDTH, WINDOW_HEIGHT))
        window.blit(scaled, (0, 0))
        if dialogue_active and dialogue_texts:
            full_message = dialogue_texts[dialogue_index]
            display_message = slow_print(full_message, dialogue_elapsed_time, CHARS_PER_SEC)
            draw_dialogue_box(window, display_message, font)
        if fading:
            window.blit(fade_surface, (0, 0))
        pygame.display.flip()
    except pygame.error as e:
        print(f"Error scaling surface: {e}")
        running = False




pygame.quit()
sys.exit()
