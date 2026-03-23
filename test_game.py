from board import HexBoard
from random_player import RandomPlayer
from solution import SmartPlayer

from visualize import visualize   # tu archivo pygame
from visualize import show_board_once
import time


def play_game(size=7):

    board = HexBoard(size)

    p2 = SmartPlayer(2)
    p1 = RandomPlayer(1)

    turn = 1

    while True:
        start = time.time()

        if turn == 1:
            move = p1.play(board.clone())
        else:
            move = p2.play(board.clone())

        think_time = time.time() - start

        board.place_piece(move[0], move[1], turn)

        print("Jugador", turn, "jugó", move)
        print(board)
        show_board_once(board, turn, move, think_time)

        if board.check_connection(turn):
            print("Gana jugador", turn)
            visualize(board, turn)
            break

        if board.is_full():
            print("Empate")
            break

        turn = 2 if turn == 1 else 1


play_game()