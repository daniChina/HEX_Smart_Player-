from __future__ import annotations

import random
from player import Player
from board import HexBoard


class RandomPlayer(Player):
    """Jugador simple para probar tu solución localmente."""

    def play(self, board: HexBoard) -> tuple:
        legal = board.get_legal_moves()
        if not legal:
            return (0, 0)
        return random.choice(legal)
