import logging
import os
import math
import requests, json
from threading import Thread
from PIL import Image, ImageColor

from flask import Flask
from flask import request
from rgbmatrix import RGBMatrix, RGBMatrixOptions
from random import randrange
import websocket

import logic

# websocket.enableTrace(True)

app = Flask(__name__)

# Configuration for the matrix
options = RGBMatrixOptions()
options.rows = 16
options.cols = 32
options.chain_length = 1
options.parallel = 1
options.hardware_mapping = 'regular'

matrix = RGBMatrix(options = options)

# Game variables
class BattleSnakeGame:
    def __init__(self):
        self.wsapp = None
        # Host Variables
        self.queue = []
        self.snake_images = {}
        # Individual Game Variables
        self.offsetX = 16 - 6
        self.offsetY = 8 - 6
        self.width = 11
        self.height = 11
        self.game_id = None
        
    def add_to_queue(self, game_id):
        self.queue.append(game_id)
        self.queue = list(dict.fromkeys(self.queue)) # Remove duplicates
        print(f"Game {game_id} added to queue (size {len(self.queue)})")
        self.start_next_game()

    def play_game(self):
        self.game_id = self.queue[0]
        print(f"Game {self.game_id} playing from queue")
        # Get game data
        url = requests.get(f"https://engine.battlesnake.com/games/{self.game_id}")
        data = json.loads(url.text)
        self.width = data['Game']['Width']
        self.height = data['Game']['Height']
        self.offsetX = int(0.5 * (32 - self.width))
        self.offsetY = int(0.5 * (16 - self.height))
        self.ruleset = data['Game']['Ruleset']['name']
        if self.ruleset == 'wrapped':
            self.offsetX = 0
            self.offsetY = 0

        # websockets
        if not self.wsapp: # Another safeguard for race conditions
            self.wsapp = websocket.WebSocketApp(f"wss://engine.battlesnake.com/games/{self.game_id}/events", on_message=self.on_message)
            self.wsapp.run_forever()

    def start_next_game(self):
        if self.wsapp:
            return
        if len(self.queue) == 0:
            return
        self.play_game()

    def get_snake_image(self, head, tail, color):
        key = f"{head}-{tail}-{color}"
        color_string = color.lstrip("#")
        if not key in self.snake_images:
            url = f"https://exporter.battlesnake.com/avatars/head:{head}/tail:{tail}/color:%23{color_string}/32x16.svg"
            raw = requests.get(url, stream=True).raw
            # TODO: Actually load the svg somehow
            im = Image.new("RGB", (32, 16))
            self.snake_images[key] = im
            return im
        else:
            return self.snake_images[key]

    def set_pixel_on_board(self, canvas, x, y, r, g, b):
        if self.ruleset == "wrapped":
            while self.offsetX < options.cols:
                while self.offsetY < options.rows:
                    canvas.SetPixel(self.offsetX + x, self.offsetY + self.height - y - 1, r, g, b)
                    self.offsetY += self.height
                self.offsetY = 0
                self.offsetX += self.width
            self.offsetX = 0
        else:
            canvas.SetPixel(self.offsetX + x, self.offsetY + self.height - y - 1, r, g, b)

    def on_message(self, wsapp, msg):
        def run(*args):
            message = json.loads(msg)
            message_type = message['Type']
            data = message["Data"]
            if message_type == 'frame':
                canvas = matrix.CreateFrameCanvas()
                canvas.Fill(32, 32 ,32)

                # Draw a board
                for x in range(0, self.width):
                    for y in range(0, self.height):
                        self.set_pixel_on_board(canvas, x, y, 0, 0, 0)
                
                for o in data['Hazards']:
                    self.set_pixel_on_board(canvas, o['X'], o['Y'], 48, 24, 16)
                
                for o in data['Food']:
                    self.set_pixel_on_board(canvas, o['X'], o['Y'], 255, 92, 117)
                for snake in data['Snakes']:
                    if snake["Death"]:
                        continue
                    for i, o in enumerate(snake['Body']):
                        (r, g, b) = ImageColor.getcolor(snake["Color"], "RGB")                    
                        if i == 0:
                            (r, g, b) = rgb_brightness((r, g, b), 2)
                        elif i % 4 == 0:
                            (r, g, b) = rgb_brightness((r, g, b), 0.5)
                        
                        self.set_pixel_on_board(canvas, o['X'], o['Y'], r, g, b)

                canvas = matrix.SwapOnVSync(canvas)
                # TODO: Make it so there's a max speed on playback
            elif message_type == 'game_end':
                # Draw a background snake
                # im = self.get_snake_image("orca", "round-bum", "#BAD455")
                # canvas.SetImage(im.convert('RGB'))
                
                # TODO: Paint the winning snake's head/tail in the background
                wsapp.close()
                if self.game_id in self.queue: self.queue.remove(self.game_id)
                print(f"Game {self.game_id} removed from queue (size {len(self.queue)})")
                self.wsapp = None
                self.start_next_game()
                return
            else:
                print(f"Unhandled {message['Type']} message received")
        Thread(target=run).start()



game = BattleSnakeGame()

# Utility function
def rgb_brightness(rgb, factor):
    (r, g, b) = rgb
    r = max(min(int(r * factor), 255), 0)
    g = max(min(int(g * factor), 255), 0)
    b = max(min(int(b * factor), 255), 0)
    return (r, g, b)

@app.get("/")
def handle_info():
    """
    This function is called when you register your Battlesnake on play.battlesnake.com
    See https://docs.battlesnake.com/guides/getting-started#step-4-register-your-battlesnake
    """
    game_id = request.args.get('gameId')
    print(f"INFO {game_id}")
    if game_id:
        game.add_to_queue(game_id)
    return logic.get_info()


@app.post("/start")
def handle_start():
    """
    This function is called everytime your Battlesnake enters a game.
    It's purely for informational purposes, you don't have to make any decisions here.
    request.json contains information about the game that's about to be played.
    """
    data = request.get_json()

    print(f"{data['game']['id']} START")
    return "ok"


@app.post("/move")
def handle_move():
    """
    This function is called on every turn and is how your Battlesnake decides where to move.
    Valid moves are "up", "down", "left", or "right".
    """
    data = request.get_json()

    # TODO - look at the logic.py file to see how we decide what move to return!
    move = logic.choose_move(data)

    return {"move": move}


@app.post("/end")
def handle_end():
    """
    This function is called when a game your Battlesnake was in has ended.
    It's purely for informational purposes, you don't have to make any decisions here.
    """
    data = request.get_json()

    print(f"{data['game']['id']} END")
    return "ok"


@app.after_request
def identify_server(response):
    response.headers["Server"] = "BattlesnakeOfficial/starter-snake-python"
    return response


if __name__ == "__main__":
    # Flask server
    logging.getLogger("werkzeug").setLevel(logging.ERROR)

    host = "0.0.0.0"
    port = int(os.environ.get("PORT", "5555"))

    print(f"\nRunning Battlesnake server at http://{host}:{port}")
    app.env = 'development'
    app.run(host=host, port=port, debug=False)
