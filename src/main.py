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
options.chain_length = 1
options.parallel = 1
options.hardware_mapping = 'regular'

matrix = RGBMatrix(options = options)

# Game variables
width = 11
height = 11
offsetX = 16 - 6
offsetY = 8 - 6

# width = 25
# height = 16
# offsetX = 3
# offsetY = 0

snake_images = {}

def get_snake_image(head, tail, color):
    key = f"{head}-{tail}-{color}"
    color_string = color.lstrip("#")
    if not key in snake_images:
        url = f"https://exporter.battlesnake.com/avatars/head:{head}/tail:{tail}/color:%23{color_string}/32x16.svg"
        raw = requests.get(url, stream=True).raw
        # TODO: Actually load the svg somehow
        im = Image.new("RGB", (32, 16))
        snake_images[key] = im
        return im
    else:
        return snake_images[key]

def rgb_brightness(rgb, factor):
    (r, g, b) = rgb
    r = max(min(int(r * factor), 255), 0)
    g = max(min(int(g * factor), 255), 0)
    b = max(min(int(b * factor), 255), 0)
    return (r, g, b)


def on_message(wsapp, msg):
    message = json.loads(msg)
    message_type = message['Type']
    data = message["Data"]
    if message_type == 'frame':
        # print(f"Turn {data['Turn']} - {width}x{height} board")
        canvas = matrix.CreateFrameCanvas()
        canvas.Fill(0, 0, 0)

        # Draw a board
        for x in range(0, width):
            for y in range(0, height):
                canvas.SetPixel(offsetX + x, offsetY + y, 32, 32, 32)
        
        for o in data['Hazards']:
            canvas.SetPixel(offsetX + o['X'], offsetY + height - o['Y'] - 1, 32, 12, 8)
        
        for o in data['Food']:
            canvas.SetPixel(offsetX + o['X'], offsetY + height - o['Y'] - 1, 255, 92, 117)
        for snake in data['Snakes']:
            if snake["Death"]:
                continue
            for i, o in enumerate(snake['Body']):
                (r, g, b) = ImageColor.getcolor(snake["Color"], "RGB")
                
                if i == 0:
                    (r, g, b) = rgb_brightness((r, g, b), 2)
                elif i % 4 == 0:
                    (r, g, b) = rgb_brightness((r, g, b), 0.5)
                
                canvas.SetPixel(offsetX + o['X'], offsetY + height - o['Y'] - 1, r, g, b)
        canvas = matrix.SwapOnVSync(canvas)
    elif message_type == 'game_end':
        # Draw a background snake
        im = get_snake_image("orca", "round-bum", "#BAD455")
        canvas.SetImage(im.convert('RGB'))
        
        # TODO: Paint the winning snake's head/tail in the background
        print('complete')
        wsapp.close()
        return
    else:
        print(f"{message['Type']} message received")

def on_close(ws, close_status_code, close_msg):
    print(">>>>>>CLOSED")

def start_websocket(game_id):
    url = requests.get(f"https://engine.battlesnake.com/games/{game_id}")
    data = json.loads(url.text)
    width = data['Game']['Width']
    height = data['Game']['Height']
    # TODO: Figure out why the websocket messages still use the old width/height

    # websockets
    wsapp = websocket.WebSocketApp(f"wss://engine.battlesnake.com/games/{game_id}/events", on_message=on_message, on_close=on_close)
    wsapp.run_forever()


@app.get("/")
def handle_info():
    """
    This function is called when you register your Battlesnake on play.battlesnake.com
    See https://docs.battlesnake.com/guides/getting-started#step-4-register-your-battlesnake
    """
    game_id = request.args.get('gameId')
    print(f"INFO {game_id}")
    if game_id:
        t1 = Thread(target=start_websocket, args=(game_id,))
        t1.start()
    
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
