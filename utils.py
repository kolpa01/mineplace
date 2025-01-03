import opensimplex
import random
import pygame
import json
import sys, os
from PIL import Image, ImageFilter
from keybindsscr import KEYBINDS

def resource_path(relative_path):
    """ Get absolute path to resource, works for dev and PyInstaller """
    base_path = getattr(sys, '_MEIPASS', os.path.abspath("."))
    return os.path.join(base_path, relative_path)

def map_noise_to_height(noise_value, height):
    # Normalize noise from [-1, 1] to [0, 1]
    normalized_value = (noise_value + 1) / 2

    # Map to the range [0, height]
    mapped_value = normalized_value * height

    # Round to nearest integer
    return int(mapped_value)

class SoundManager:
    @staticmethod
    def checkmixer_online():
        if not pygame.mixer.get_init():
            pygame.mixer.init()

    @staticmethod
    def playsound(soundfile_path):
        SoundManager.checkmixer_online()
        pygame.mixer.music.load(soundfile_path)
        pygame.mixer.music.play()

class SettingsManager:
    @staticmethod
    def apply_settings(settings):
        SoundManager.checkmixer_online()
        pygame.mixer.music.set_volume(settings["volume"] / 100)
        
        panorama_image = Image.open(resource_path("assets/game/panorama.png"))
        panorama_image = panorama_image.filter(ImageFilter.GaussianBlur(settings["panorama_blur"]))
        panorama_image.save(resource_path("assets/game/panorama_blurred.png"))

class Block:
    def __init__(self, name, attr={}):
        self.name = name
        self.attr = attr

    def __repr__(self):
        # Turns a dict to [key=value, key=value, ...]
        string = ", ".join([f"{key}=\"{value}\"" for key, value in self.attr.items()])
        return self.name + "[" + string + "]"

    def getattr(self, key):
        return self.attr.get(key, None)

    def copy(self):
        return Block(self.name, self.attr.copy())

    @staticmethod
    def from_string(string):
        import re

        def parse_attributes(attr_string):
            """Parse attributes with support for nested brackets."""
            attr = {}
            key, value, depth = "", "", 0
            in_key = True
            for char in attr_string:
                if char == "[":
                    depth += 1
                elif char == "]":
                    depth -= 1
                elif char == "=" and depth == 0:
                    in_key = False
                    continue
                elif char == "," and depth == 0:
                    attr[key.strip()] = value.strip()
                    key, value = "", ""
                    in_key = True
                    continue

                if in_key:
                    key += char
                else:
                    value += char
            if key:  # Add the final key-value pair
                attr[key.strip()] = value.strip()

            # Remove surrounding quotes from values
            for k, v in attr.items():
                if v.startswith("\"") and v.endswith("\""):
                    attr[k] = v[1:-1]
            return attr

        # Match the block name and attributes
        match = re.match(r"(\w+)\[(.*)\]", string)

        if not match:
            # If no attributes are provided, return a block with just a name
            return Block(name=string.strip())

        # Extract the name and attributes
        name = match.group(1)
        attr_string = match.group(2)

        # Parse attributes
        attr = parse_attributes(attr_string)

        return Block(name=name, attr=attr)

    # How a block is equal to another block
    def __eq__(self, other):
        if not isinstance(other, Block):
            return False
        return self.name == other.name and self.attr == other.attr

    # How a block is not equal to another block
    def __ne__(self, other):
        return not self.__eq__(other)

class WorldGenerator:
    def __init__(self, seed, width, height, scale=0.1):
        self.seed = seed
        self.noise = opensimplex.OpenSimplex(seed)
        self.secondary_noise = opensimplex.OpenSimplex(seed + 1)
        self.width = width
        self.height = height
        self.scale = scale  # Added scale factor

    def generate(self):
        # Uses 1D noise to generate a heightmap to later generate the world
        heightmap = []
        for x in range(self.width):
            noise_value = self.noise.noise2(x * self.scale, 0)  # Scaled noise
            noise_value = map_noise_to_height(noise_value, self.height)
            noise_value -= 2
            heightmap.append(noise_value)

        waterlevel = self.height // 3

        oremap = []
        for x in range(self.width):
            column = []
            for y in range(self.height):
                noise_value = self.noise.noise2(x * self.scale, y * self.scale)
                # Do NOT allow negatives, so map them from [-1, 1] to [0, 1]
                noise_value = (noise_value + 1) / 2
                column.append(noise_value)
            oremap.append(column)

        orethresholds = {
            "diamond_ore": 0.7,
            "gold_ore": 0.6,
            "iron_ore": 0.5,
            "coal_ore": 0.3
        }

        gravelmap = []
        for x in range(self.width):
            column = []
            for y in range(self.height):
                noise_value = self.secondary_noise.noise2(x * self.scale, y * self.scale)
                # Do NOT allow negatives, so map them from [-1, 1] to [0, 1]
                noise_value = (noise_value + 1) / 2
                column.append(noise_value)
            gravelmap.append(column)

        world = []
        for x in range(self.width):
            column = []
            for y in range(self.height):
                terrain_height = heightmap[x]

                # Add a second noise layer for caves
                cave_noise = self.noise.noise2(x * self.scale, y * self.scale)
                is_cave = cave_noise > 0.5  # Adjust threshold for cave density
                
                if y == terrain_height and not is_cave:
                    should_add_grass = True
                    if y < waterlevel:
                        column.append(Block("sand"))
                        should_add_grass = False
                    if should_add_grass:
                        column.append(Block("grass"))
                elif y > terrain_height - 3 and y < terrain_height and not is_cave:
                    column.append(Block("dirt"))
                elif y < terrain_height and not is_cave:
                    should_add_stone = True
                    # WAIT! What if we can add some ores here?
                    for ore, threshold in orethresholds.items():
                        if oremap[x][y] > threshold:
                            # BUT! The higher we are, the lower chance of spawning ores
                            if random.random() < 0.3 - (y / self.height):
                                column.append(Block(ore))
                                # Don't add a stone now
                                # continue
                                should_add_stone = False
                            break
                    # WAIT (again)! What if we can add some gravel here?
                    if gravelmap[x][y] > 0.7:
                        column.append(Block("gravel", { "static": "T" })) # It doesn't fall
                        # Don't add a stone now
                        # continue
                        should_add_stone = False
                    if should_add_stone:
                        column.append(Block("stone"))
                elif is_cave and y < terrain_height:
                    should_add_air = True
                    if y < waterlevel:
                        column.append(Block("water"))
                        should_add_air = False
                    if should_add_air:
                        column.append(Block("air"))
                else:
                    should_add_air = True
                    if y < waterlevel:
                        column.append(Block("water"))
                        should_add_air = False
                    if should_add_air:
                        column.append(Block("air"))
            world.append(column)

        # Transpose it
        world = list(map(list, zip(*world)))

        # Flip it
        world = world[::-1]

        # Wait! Let's add some trees!
        for x in range(self.width):
            for y in range(self.height):
                if world[y][x].name == "grass" and random.random() < 0.1:
                    structure = StructureManager.load_structure("oak_tree")
                    world = StructureManager.place_structure(world, structure, x, y + 1)

        return world

class FlatWorldGenerator:
    def __init__(self, width, height):
        self.width = width
        self.height = height

    def generate(self):
        grass_height = self.height - self.height // 3

        world = []
        for x in range(self.width):
            column = []
            for y in range(self.height):
                if y > grass_height + 3:
                    column.append(Block("stone"))
                    continue
                if y == grass_height:
                    column.append(Block("grass"))
                elif y > grass_height:
                    column.append(Block("dirt"))
                else:
                    column.append(Block("air"))
            world.append(column)
        
        # Transpose it
        world = list(map(list, zip(*world)))

        # Flip it
        # world = world[::-1]

        return world

class Player:
    def __init__(self, x, y):
        self.pos = [x, y]
        self.blockselector = [0, 0]
        self.placeable_blocks = [
                Block("grass"),
                Block("dirt"),
                Block("stone"),
                Block("cobblestone"),
                Block("stone_bricks"),
                Block("coal_ore"),
                Block("iron_ore"),
                Block("gold_ore"),
                Block("diamond_ore"),
                Block("coal_block"),
                Block("iron_block"),
                Block("gold_block"),
                Block("diamond_block"),
                Block("bricks"),
                Block("oak_planks"),
                Block("oak_log"), # Horizontal = false
                Block("oak_log", {"horiz": "T"}), # Horizontal = true
                Block("oak_leaves"),
                Block("oak_stairs", {"orientation": "ur"}), # Upper right
                Block("oak_stairs", {"orientation": "ul"}), # Upper left
                Block("oak_stairs", {"orientation": "dl"}), # Down left
                Block("oak_stairs", {"orientation": "dr"}), # Down right
                Block("oak_slab", {"orientation": "u"}), # Upper
                Block("oak_slab", {"orientation": "d"}), # Down
                Block("glass"),
                Block("sand"),
                Block("gravel"),
                Block("water"),
                Block("redstone_dust", {"state": "off", "power": "0"}), # Unpowered
                Block("redstone_repeater", {"state": "off", "orientation": "l"}), # Unpowered left
                Block("redstone_repeater", {"state": "off", "orientation": "r"}), # Unpowered right
                Block("redstone_lamp", {"state": "off"}), # Unpowered
                Block("redstone_observer", {"state": "off", "orientation": "l", "last": "air[]"}), # Unpowered left
                Block("redstone_observer", {"state": "off", "orientation": "r", "last": "air[]"}), # Unpowered right
                Block("redstone_observer", {"state": "off", "orientation": "u", "last": "air[]"}), # Unpowered up
                Block("redstone_observer", {"state": "off", "orientation": "d", "last": "air[]"}), # Unpowered down
                Block("redstone_block"),
        ]
        self.collision_ignore = ["air", "water"]
        self.selected_block = 0

    def keypress(self, world, keys, tick):
        # if event.type == pygame.KEYDOWN:
        if keys[KEYBINDS.move_left]:
            # Move left
            if tick % 2 != 0:
                return
            if self.pos[0] > 0 and world[self.pos[1]][self.pos[0] - 1].name in self.collision_ignore:
                self.pos[0] -= 1
        if keys[KEYBINDS.move_right]:
            # Move right
            if tick % 2 != 0:
                return
            if self.pos[0] < len(world[0]) - 1 and world[self.pos[1]][self.pos[0] + 1].name in self.collision_ignore:
                self.pos[0] += 1
        if keys[KEYBINDS.move_up]:
            # Move up
            if tick % 2 != 0:
                return
            if self.pos[1] > 0 and world[self.pos[1] - 1][self.pos[0]].name in self.collision_ignore:
                self.pos[1] -= 1
        if keys[KEYBINDS.move_down]:
            # Move down
            if tick % 2 != 0:
                return
            if self.pos[1] < len(world) - 1 and world[self.pos[1] + 1][self.pos[0]].name in self.collision_ignore:
                self.pos[1] += 1

        if keys[KEYBINDS.move_blockselector_left]:
            # Move left in the block selector
            if tick % 2 != 0:
                return
            if self.blockselector[0] == -1:
                return
            self.blockselector[0] -= 1
        if keys[KEYBINDS.move_blockselector_right]:
            # Move right in the block selector
            if tick % 2 != 0:
                return
            if self.blockselector[0] == 1:
                return
            self.blockselector[0] += 1
        if keys[KEYBINDS.move_blockselector_up]:
            # Move up in the block selector
            if tick % 2 != 0:
                return
            if self.blockselector[1] == -1:
                return
            self.blockselector[1] -= 1
        if keys[KEYBINDS.move_blockselector_down]:
            # Move down in the block selector
            if tick % 2 != 0:
                return
            if self.blockselector[1] == 1:
                return
            self.blockselector[1] += 1
        if keys[KEYBINDS.place_block]:
            # Place a block
            added_up = [self.pos[1] + self.blockselector[1], self.pos[0] + self.blockselector[0]]
            if added_up[0] >= 0 and added_up[1] >= 0 and added_up[0] < len(world) and added_up[1] < len(world[0]):
                world[added_up[0]][added_up[1]] = self.placeable_blocks[self.selected_block]
        if keys[KEYBINDS.break_block]:
            # Remove a block
            added_up = [self.pos[1] + self.blockselector[1], self.pos[0] + self.blockselector[0]]
            if added_up[0] >= 0 and added_up[1] >= 0 and added_up[0] < len(world) and added_up[1] < len(world[0]):
                world[added_up[0]][added_up[1]] = Block("air")

    def keydown(self, world, event, tick):
        if event.type == pygame.KEYDOWN:
            if event.key == KEYBINDS.switch_block_left:
                self.selected_block -= 1
                self.selected_block %= len(self.placeable_blocks)
            if event.key == KEYBINDS.switch_block_right:
                self.selected_block += 1
                self.selected_block %= len(self.placeable_blocks)

    @staticmethod
    def find_best_spawn(world):
        for x in range(len(world)):
            for y in range(len(world[x])):
                if world[y][x].name != "air":
                    return x, y - 1

        return 0, 0

class StructureManager:
    @staticmethod
    def load_structure(name):
        with open(resource_path(f"assets/structures/{name}.json"), "r") as f:
            data = json.load(f)

        return data
    
    @staticmethod
    def place_structure(world, structure_dict, x, y):
        # {
        # 	"keys": {
		#       "s": "oak_log",
        # 		"l": "oak_leaves",
        # 		" ": "air"
        # 	},
	    #   "dim": [5, 7],
        # 	"structure": [
        # 		" lll ",
        # 		" lll ",
        # 		"lllll",
	    #       "lllll",
        # 	    "  s  ",
		#       "  s  ",
        # 		"  s  "
	    #   ],
	    #   "placepoint": [2, 6]
        # }

        keys = structure_dict["keys"]
        dim = structure_dict["dim"]
        structure = structure_dict["structure"]
        placepoint = structure_dict["placepoint"]

        x -= placepoint[0]
        y -= placepoint[1]

        for dx in range(dim[0]):
            for dy in range(dim[1]):
                if x + dx >= len(world[0]) or y + dy >= len(world):
                    continue
                if structure[dy][dx] in keys:
                    if keys[structure[dy][dx]] == "air":
                        continue
                    world[y + dy][x + dx] = Block(keys[structure[dy][dx]])

        return world

class WorldManager:
    @staticmethod
    def save_world(name, world):
        # {
        #     "world": [[Block, Block, ...], [Block, Block, ...], ...]
        #     "wf_version": 1 (worldfile version)
        # }
        
        # Convert the world to a list of lists of strings
        world_data = [[block.__repr__() for block in column] for column in world]

        # Save the world to a JSON file
        # Variable to store ~/.mineplace/worlds or %APPDATA%/mineplace/worlds
        folder_to_save = ""
        if os.name == "nt":
            folder_to_save = os.getenv("APPDATA")
        else:
            folder_to_save = os.path.expanduser("~")
        folder_to_save = os.path.join(folder_to_save, "mineplace", "saves")

        with open(f"{folder_to_save}/{name}.json", "w") as f:
            json.dump({"world": world_data, "wf_version": 1}, f)

    @staticmethod
    def load_world(name):
        # Load the world from a JSON file
        folder_to_load = ""
        if os.name == "nt":
            folder_to_load = os.getenv("APPDATA")
        else:
            folder_to_load = os.path.expanduser("~")
        folder_to_load = os.path.join(folder_to_load, "mineplace", "saves")

        with open(f"{folder_to_load}/{name}.json", "r") as f:
            data = json.load(f)

        # Convert the list of lists of strings back to a list of lists of Blocks
        world = [[Block.from_string(block_string) for block_string in column] for column in data["world"]]
        
        datanew = {
            "world": world,
            "wf_version": data["wf_version"]
        }

        return datanew
    
    @staticmethod
    def all_world_files():
        folder_to_load = ""
        if os.name == "nt":
            folder_to_load = os.getenv("APPDATA")
        else:
            folder_to_load = os.path.expanduser("~")
        folder_to_load = os.path.join(folder_to_load, "mineplace", "saves")

        return [f.split(".")[0] for f in os.listdir(folder_to_load) if f.endswith(".json")]

    @staticmethod
    def get_world_ver(name):
        folder_to_load = ""
        if os.name == "nt":
            folder_to_load = os.getenv("APPDATA")
        else:
            folder_to_load = os.path.expanduser("~")
        folder_to_load = os.path.join(folder_to_load, "mineplace", "saves")

        with open(f"{folder_to_load}/{name}.json", "r") as f:
            data = json.load(f)

        return data["wf_version"]

    @staticmethod
    def delete_world(name):
        folder_to_load = ""
        if os.name == "nt":
            folder_to_load = os.getenv("APPDATA")
        else:
            folder_to_load = os.path.expanduser("~")
        folder_to_load = os.path.join(folder_to_load, "mineplace", "saves")

        os.remove(f"{folder_to_load}/{name}.json")

def update_world(world, tick):
    # Make a copy of the world for updates, so changes don't affect current processing
    new_world = [[block for block in row] for row in world]

    for y in range(len(world)):
        for x in range(len(world[y])):
            # Dirt to grass conversion
            if world[y][x].name == "dirt":
                for dy in range(-1, 2):
                    for dx in range(-1, 2):
                        ny, nx = y + dy, x + dx
                        if ny < 0 or ny >= len(world) or nx < 0 or nx >= len(world[y]):
                            continue
                        if world[y - 1][x].name != "air":
                            continue
                        if world[ny][nx].name == "grass" and random.random() < 0.1:
                            new_world[y][x] = Block("grass")

            # Grass to dirt conversion
            if world[y][x].name == "grass":
                if y - 1 >= 0 and world[y - 1][x].name != "air":
                    new_world[y][x] = Block("dirt")

            # Water spreading logic (only on ticks divisible by 15)
            if world[y][x].name == "water" and tick % 15 == 0:
                if y + 1 < len(world) and world[y + 1][x].name in ["air", "water"]:
                    new_world[y + 1][x] = Block("water")
                else:
                    if x - 1 >= 0 and world[y][x - 1].name == "air":
                        new_world[y][x - 1] = Block("water")
                    if x + 1 < len(world[y]) and world[y][x + 1].name == "air":
                        new_world[y][x + 1] = Block("water")

            # Sand and gravel falling logic
            if world[y][x].name in ["sand", "gravel"] and tick % 10 == 0:
                if y + 1 < len(world) and world[y + 1][x].name == "air":
                    # Check if the block is NOT static
                    if world[y][x].getattr("static") != "T":
                        # If it is, move the block down
                        new_world[y + 1][x] = Block(world[y][x].name)
                        new_world[y][x] = Block("air")

            # Redstone dust power logic
            if world[y][x].name == "redstone_dust" and tick % 2 == 0:
                greatest_power = 0
                # If a nearby block is a redstone block, power the redstone dust
                # (or a powered redstone dust)
                for dy in range(-1, 2):
                    for dx in range(-1, 2):
                        ny, nx = y + dy, x + dx
                        if ny < 0 or ny >= len(world) or nx < 0 or nx >= len(world[y]):
                            continue
                        if ny == y and nx == x:
                            continue
                        if world[ny][nx].name == "redstone_block":
                            greatest_power = 16 # 15 + 1
                        if world[ny][nx].name == "redstone_dust":
                            if int(world[ny][nx].getattr("power")) > greatest_power:
                                greatest_power = int(world[ny][nx].getattr("power"))
                if greatest_power - 1 > 0:
                    new_world[y][x] = Block("redstone_dust", {"state": "on", "power": str(greatest_power - 1)})
                else:
                    new_world[y][x] = Block("redstone_dust", {"state": "off", "power": "0"})
            
            # Redstone repeater power logic
            if world[y][x].name == "redstone_repeater" and tick % 2 == 0:
                # Detect the block behind the repeater (using orientation)
                orientation = world[y][x].getattr("orientation")
                behind = [0, 0]
                if orientation == "l":
                    behind = [x + 1, y]
                if orientation == "r":
                    behind = [x - 1, y]

                # If the block behind the repeater is powered, power the repeater
                should_power_up = False
                if behind[0] >= 0 and behind[0] < len(world[y]) and behind[1] >= 0 and behind[1] < len(world):
                    if world[behind[1]][behind[0]].name == "redstone_dust":
                        if world[behind[1]][behind[0]].getattr("state") == "on":
                            should_power_up = True
                    if world[behind[1]][behind[0]].name == "redstone_repeater":
                        if world[behind[1]][behind[0]].getattr("state") == "on":
                            should_power_up = True
                    if world[behind[1]][behind[0]].name == "redstone_block":
                        should_power_up = True
                
                if should_power_up:
                    new_world[y][x] = Block("redstone_repeater", {"state": "on", "orientation": world[y][x].getattr("orientation")})
                else:
                    new_world[y][x] = Block("redstone_repeater", {"state": "off", "orientation": world[y][x].getattr("orientation")})

                # Now for the fun part: power the block in front of the repeater
                front = [0, 0]
                if orientation == "l":
                    front = [x - 1, y]
                if orientation == "r":
                    front = [x + 1, y]

                if front[0] >= 0 and front[0] < len(world[y]) and front[1] >= 0 and front[1] < len(world):
                    if world[y][x].getattr("state") == "on":
                        if world[front[1]][front[0]].name == "redstone_dust":
                            new_world[front[1]][front[0]] = Block("redstone_dust", {"state": "on", "power": "15"})
                        if world[front[1]][front[0]].name == "redstone_repeater":
                            new_world[front[1]][front[0]] = Block("redstone_repeater", {"state": "on", "orientation": world[y][x].getattr("orientation")})
                    else:
                        if world[front[1]][front[0]].name == "redstone_dust":
                            new_world[front[1]][front[0]] = Block("redstone_dust", {"state": "off", "power": "0"})
                        if world[front[1]][front[0]].name == "redstone_repeater":
                            new_world[front[1]][front[0]] = Block("redstone_repeater", {"state": "off", "orientation": world[y][x].getattr("orientation")})

            # Redstone lamp power logic
            if world[y][x].name == "redstone_lamp" and tick % 2 == 0:
                should_power_up = False
                for dy in range(-1, 2):
                    for dx in range(-1, 2):
                        ny, nx = y + dy, x + dx
                        if ny < 0 or ny >= len(world) or nx < 0 or nx >= len(world[y]):
                            continue
                        if ny == y and nx == x:
                            continue
                        if world[ny][nx].name == "redstone_block":
                            should_power_up = True
                        if world[ny][nx].name == "redstone_dust":
                            if world[ny][nx].getattr("state") == "on":
                                should_power_up = True
                        if world[ny][nx].name == "redstone_repeater":
                            if world[ny][nx].getattr("state") == "on":
                                should_power_up = True
                        if world[ny][nx].name == "redstone_observer":
                            if world[ny][nx].getattr("state") == "on":
                                # If the observer's power direction is this block, power up
                                orientation = world[ny][nx].getattr("orientation")
                                if orientation == "l" and nx == x - 1:
                                    should_power_up = True
                                if orientation == "r" and nx == x + 1:
                                    should_power_up = True
                                if orientation == "u" and ny == y - 1:
                                    should_power_up = True
                                if orientation == "d" and ny == y + 1:
                                    should_power_up = True
                if should_power_up:
                    new_world[y][x] = Block("redstone_lamp", {"state": "on"})
                else:
                    new_world[y][x] = Block("redstone_lamp", {"state": "off"})

            # Redstone observer power logic
            if world[y][x].name == "redstone_observer" and tick % 2 == 0:
                should_power_up = False
                orientation = world[y][x].getattr("orientation")
                last = world[y][x].getattr("last")
                new_last = last
                last_block = Block.from_string(last)
                if orientation == "l":
                    if x - 1 >= 0:
                        if world[y][x - 1] != last_block:
                            should_power_up = True
                            new_last = world[y][x - 1].__repr__()
                if orientation == "r":
                    if x + 1 < len(world[y]):
                        if world[y][x + 1] != last_block:
                            should_power_up = True
                            new_last = world[y][x + 1].__repr__()
                if orientation == "u":
                    if y - 1 >= 0:
                        if world[y - 1][x] != last_block:
                            should_power_up = True
                            new_last = world[y - 1][x].__repr__()
                if orientation == "d":
                    if y + 1 < len(world):
                        if world[y + 1][x] != last_block:
                            should_power_up = True
                            new_last = world[y + 1][x].__repr__()
                if should_power_up:
                    new_world[y][x] = Block("redstone_observer", {"state": "on", "orientation": orientation, "last": new_last})
                else:
                    new_world[y][x] = Block("redstone_observer", {"state": "off", "orientation": orientation, "last": new_last})

                # Make nearby blocks power up
                if should_power_up:
                    power_dir = [0, 0]
                    # Changes depending on the orientation
                    if orientation == "l":
                        power_dir = [x + 1, y]
                    if orientation == "r":
                        power_dir = [x - 1, y]
                    if orientation == "d":
                        power_dir = [x, y - 1]
                    if orientation == "u":
                        power_dir = [x, y + 1]
                    if power_dir[0] >= 0 and power_dir[0] < len(world[y]) and power_dir[1] >= 0 and power_dir[1] < len(world):
                        if world[power_dir[1]][power_dir[0]].name == "redstone_dust":
                            new_world[power_dir[1]][power_dir[0]] = Block("redstone_dust", {"state": "on", "power": "15"})
                        if world[power_dir[1]][power_dir[0]].name == "redstone_repeater":
                            new_world[power_dir[1]][power_dir[0]] = Block("redstone_repeater", {"state": "on", "orientation": world[y][x].getattr("orientation")})
                        if world[power_dir[1]][power_dir[0]].name == "redstone_lamp":
                            new_world[power_dir[1]][power_dir[0]] = Block("redstone_lamp", {"state": "on"})
                            print("Powered up lamp")

    # Return the updated world
    return new_world
