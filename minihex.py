"""
minihex

Adapted from: https://github.com/FirefoxMetzger/minihex

License notice (MIT): Copyright 2020 Sebastian Wallkotter

Permission is hereby granted, free of charge, to any person obtaining a copy of
this software and associated documentation files (the "Software"), to deal in
the Software without restriction, including without limitation the rights to
use, copy, modify, merge, publish, distribute, sublicense, and/or sell copies of
the Software, and to permit persons to whom the Software is furnished to do so,
subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY, FITNESS
FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE AUTHORS OR
COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER
IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN
CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.
"""

import gymnasium as gym
from gymnasium import spaces
import numpy as np
from enum import IntEnum


class player(IntEnum):
    BLACK = 0
    WHITE = 1
    EMPTY = 2


class HexGame(object):
    """
    Hex Game Environment.
    """

    def __init__(self, active_player, board,
                 connected_stones=None, debug=False):
        self.board = board
        # track number of empty fields for speed
        self.empty_fields = np.count_nonzero(board == player.EMPTY)

        if debug:
            self.make_move = self.make_move_debug
        else:
            self.make_move = self.fast_move

        # self.special_moves = IntEnum("SpecialMoves", {
        #     "RESIGN": self.board_size ** 2,
        #     "SWAP": self.board_size ** 2 + 1
        # })

        if connected_stones is None:
            self.regions = np.stack([
                np.pad(np.zeros_like(self.board), 1),
                np.pad(np.zeros_like(self.board), 1)
            ], axis=0)
            self.regions[player.WHITE][:, 0] = 1
            self.regions[player.BLACK][0, :] = 1
            self.regions[player.WHITE][:, self.board_size + 1] = 2
            self.regions[player.BLACK][self.board_size + 1, :] = 2
        else:
            self.regions = connected_stones

        self.region_counter = np.zeros(2)
        self.region_counter[player.BLACK] = np.max(self.regions[player.BLACK]) + 1
        self.region_counter[player.WHITE] = np.max(self.regions[player.WHITE]) + 1

        if connected_stones is None:
            for y, row in enumerate(board):
                for x, value in enumerate(row):
                    if value == player.BLACK:
                        self.active_player = player.BLACK
                        self.flood_fill((y, x))
                    elif value == player.WHITE:
                        self.active_player = player.WHITE
                        self.flood_fill((y, x))

        self.active_player = active_player
        self.done = False
        self.winner = None

        self.actions = np.arange(self.board_size ** 2)
    
    def copy(self):
        game = HexGame(
            active_player=self.active_player,
            board=self.board.copy(),
            connected_stones=self.regions.copy(),
        )

        game.done = self.done
        game.winner = self.winner
        return game

    @property
    def board_size(self):
        return self.board.shape[1]

    def is_valid_move(self, action):
        coords = self.action_to_coordinate(action)
        return self.board[coords[0], coords[1]] == player.EMPTY

    def make_move_debug(self, action):
        if not self.is_valid_move(action):
            raise IndexError(("Illegal move "
                             f"{self.action_to_coordinate(action)}"))

        return self.fast_move(action)

    def fast_move(self, action):
        # # currently resigning is not a possible option
        # if action == self.special_moves.RESIGN:
        #     self.done = True
        #     self.winner = (self.active_player + 1) % 2
        #     return (self.active_player + 1) % 2

        y, x = self.action_to_coordinate(action)
        self.board[y, x] = self.active_player
        self.empty_fields -= 1

        self.flood_fill((y, x))

        regions = self.regions[self.active_player]
        if regions[-1, -1] == 1:
            self.done = True
            self.winner = player(self.active_player)
        elif self.empty_fields <= 0:
            self.done = True

        self.active_player = (self.active_player + 1) % 2
        return self.winner

    def coordinate_to_action(self, coords):
        return np.ravel_multi_index(coords, (self.board_size, self.board_size))

    def action_to_coordinate(self, action):
        y = action // self.board_size
        x = action - self.board_size * y
        return (y, x)

    def get_possible_actions(self):
        return self.actions[self.board.flatten() == player.EMPTY]

    def flood_fill(self, position):
        regions = self.regions[self.active_player]

        y, x = (position[0] + 1, position[1] + 1)
        neighborhood = regions[(y - 1):(y + 2), (x - 1):(x + 2)].copy()
        neighborhood[0, 0] = 0
        neighborhood[2, 2] = 0
        adjacent_regions = sorted(set(neighborhood.flatten().tolist()))

        ## region label = 0 is always present, but not a region
        adjacent_regions.pop(0)

        if len(adjacent_regions) == 0:
            regions[y, x] = self.region_counter[self.active_player]
            self.region_counter[self.active_player] += 1
        else:
            new_region_label = adjacent_regions.pop(0)
            regions[y, x] = new_region_label
            for label in adjacent_regions:
                regions[regions == label] = new_region_label


class HexEnv(gym.Env):
    """
    Hex environment. Play against a fixed opponent.
    """

    metadata = {"render.modes": ["ansi"]}

    def __init__(self, opponent_policy,
                 player_color=player.BLACK,
                 active_player=player.BLACK,
                 board=None,
                 regions=None,
                 board_size=5,
                 debug=False):
        self.opponent_policy = opponent_policy

        if board is None:
            board = player.EMPTY * np.ones((board_size, board_size))

        self.initial_board = board
        self.active_player = active_player
        self.player = player_color
        self.simulator = None
        self.winner = None
        self.previous_opponent_move = None
        self.debug = debug

        # cache initial connection matrix (approx +100 games/s)
        self.initial_regions = regions

    @property
    def opponent(self):
        return player((self.player + 1) % 2)

    def reset(self):
        if self.initial_regions is None:
            self.simulator = HexGame(self.active_player,
                                     self.initial_board.copy(),
                                     debug=self.debug)
            regions = self.simulator.regions.copy()
            self.initial_regions = regions
        else:
            regions = self.initial_regions.copy()
            self.simulator = HexGame(self.active_player,
                                     self.initial_board.copy(),
                                     connected_stones=regions,
                                     debug=self.debug)

        self.previous_opponent_move = None

        if self.player != self.active_player:
            info_opponent = {
                'state': self.simulator.board,
                'last_move_opponent': None,
                'last_move_player': None
            }
            self.opponent_move(info_opponent)

        info = {
            'state': self.simulator.board,
            'last_move_opponent': self.previous_opponent_move,
            'last_move_player': None
        }

        return (self.simulator.board, self.active_player), info

    def step(self, action):
        if not self.simulator.done:
            self.winner = self.simulator.make_move(action)

        opponent_action = None

        if not self.simulator.done:
            info_opponent = {
                'state': self.simulator.board,
                'last_move_opponent': action,
                'last_move_player': self.previous_opponent_move
            }
            opponent_action = self.opponent_move(info_opponent)

        if self.winner == self.player:
            reward = 1
        elif self.winner == self.opponent:
            reward = -1
        else:
            reward = 0

        info = {
            'state': self.simulator.board,
            'last_move_opponent': opponent_action,
            'last_move_player': action
        }

        return ((self.simulator.board, self.active_player), reward,
                self.simulator.done, info)

    def render(self, mode='ansi', close=False):
        board = self.simulator.board
        print(" " * 6, end="")
        for j in range(board.shape[1]):
            print(" ", j + 1, " ", end="")
            print("|", end="")
        print("")
        print(" " * 5, end="")
        print("-" * (board.shape[1] * 6 - 1), end="")
        print("")
        for i in range(board.shape[1]):
            print(" " * (1 + i * 3), i + 1, " ", end="")
            print("|", end="")
            for j in range(board.shape[1]):
                if board[i, j] == player.EMPTY:
                    print("  O  ", end="")
                elif board[i, j] == player.BLACK:
                    print("  B  ", end="")
                else:
                    print("  W  ", end="")
                print("|", end="")
            print("")
            print(" " * (i * 3 + 1), end="")
            print("-" * (board.shape[1] * 7 - 1), end="")
            print("")

    def opponent_move(self, info):
        opponent_action = self.opponent_policy(self.simulator.board,
                                               self.opponent,
                                               info)
        self.winner = self.simulator.make_move(opponent_action)
        self.previous_opponent_move = opponent_action
        return opponent_action


def print_board(board):
    print(" " * 6, end="")
    for j in range(board.shape[1]):
        print(" ", j + 1, " ", end="")
        print("|", end="")
    print("")
    print(" " * 5, end="")
    print("-" * (board.shape[1] * 6 - 1), end="")
    print("")
    for i in range(board.shape[1]):
        print(" " * (1 + i * 3), i + 1, " ", end="")
        print("|", end="")
        for j in range(board.shape[1]):
            if board[i, j] == player.EMPTY:
                print("  O  ", end="")
            elif board[i, j] == player.BLACK:
                print("  B  ", end="")
            else:
                print("  W  ", end="")
            print("|", end="")
        print("")
        print(" " * (i * 3 + 1), end="")
        print("-" * (board.shape[1] * 7 - 1), end="")
        print("")

def random_policy(board, player, info):
    actions = np.arange(board.shape[0] * board.shape[1])
    valid_actions = actions[board.flatten() == player.EMPTY]
    choice = int(np.random.random() * len(valid_actions))
    return valid_actions[choice]