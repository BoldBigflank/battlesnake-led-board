import asyncio
import websockets
import argparse
import json
import curses
import contextlib
import time

parser = argparse.ArgumentParser()
parser.add_argument('game_id', type=str, help='game ID')
args = parser.parse_args()

@contextlib.contextmanager
def grab_screen():
    screen = curses.initscr()
    curses.noecho()
    curses.cbreak()
    screen.nodelay(True)
    try:
        yield screen
    finally:
        screen.nodelay(False)
        curses.nocbreak()
        curses.echo()
        curses.endwin()

def display_line(screen, y, line):
    screen.move(y, 0)
    screen.clrtoeol()
    screen.addstr(y, 0, line)
    screen.move(0, 0)

def display_frame(screen, frame):
    render_board(screen, frame)
    display_line(screen, 12, f"Turn #{frame['Turn']}")
    screen.refresh()

def render_board(screen, frame):
    symbols = {}
    for point in frame['Food']:
        symbols[point['X'], point['Y']] = 'F'
    for point in frame['Hazards']:
        symbols[point['X'], point['Y']] = '/'
    for i, snake in enumerate(frame['Snakes']):
        for point in snake['Body']:
            symbols[point['X'], point['Y']] = str(i)
    for y in reversed(range(11)):
        display_line(screen, y, ''.join(symbols.get((x, y), '.') for x in range(11)))

async def print_moves(screen):
    async with websockets.connect(f"wss://engine.battlesnake.com/games/{args.game_id}/events") as websocket:
        async for message in websocket:
            data = json.loads(message)
            if data['Type'] == 'frame':
                display_frame(screen, data['Data'])

with grab_screen() as screen:
    try:
        asyncio.run(print_moves(screen))
    except KeyboardInterrupt:
        pass