import pygame
import math
import sys
import time

WIDTH = 800
HEIGHT = 600
HEX_SIZE = 30
BOARD_OFFSET_X = 100
BOARD_OFFSET_Y = 220


def hex_points(x, y, size):
    points = []

    for i in range(6):
        angle = math.radians(60 * i - 30)
        px = x + size * math.cos(angle)
        py = y + size * math.sin(angle)
        points.append((px, py))

    return points


def draw_hex(surface, x, y, size, color):

    points = hex_points(x, y, size)

    pygame.draw.polygon(surface, color, points)
    pygame.draw.polygon(surface, (0,0,0), points, 2)


def draw_board(surface, board, last_move=None, winning_path=None):

    size = board.size

    hex_width = HEX_SIZE * 2
    hex_height = math.sqrt(3) * HEX_SIZE

    for r in range(size):
        for c in range(size):

            x = BOARD_OFFSET_X + c * hex_width * 0.75
            y = BOARD_OFFSET_Y + r * hex_height
            # even-r offset
            if r % 2 == 1:
                x += hex_width * 0.375

            cell = board.board[r][c]

            if cell == 0:
                color = (220,220,220)
            elif cell == 1:
                color = (220,50,50)
            else:
                color = (50,50,220)

            draw_hex(surface, x, y, HEX_SIZE, color)
            
            font = pygame.font.SysFont(None, 18)

            coord_text = font.render(f"{r},{c}", True, (0,0,0))
            rect = coord_text.get_rect(center=(x, y))

            surface.blit(coord_text, rect)
            

            if winning_path and (r,c) in winning_path:

                points = hex_points(x, y, HEX_SIZE + 6)

                pygame.draw.polygon(surface, (0,255,0), points, 6)
            
            # resaltar última jugada
            if last_move and (r, c) == last_move:

                points = hex_points(x, y, HEX_SIZE + 4)

                pygame.draw.polygon(surface, (0,255,0), points, 5) 
                #color verde lima saturado (#00FF00).verde lima saturado (#00FF00).

def draw_info(surface, player, move, think_time):

    font = pygame.font.SysFont(None, 32)

    text1 = font.render(
        f"Jugador {player} jugó en {move}", True, (0,0,0)
    )

    text2 = font.render(
        "Jugador 1 = ROJO   |   Jugador 2 = AZUL", True, (0,0,0)
    )

    text3 = font.render(
        f"Tiempo de decisión: {think_time:.3f} s", True, (0,0,0)
    )

    surface.blit(text1, (40, 20))
    surface.blit(text2, (40, 60))
    surface.blit(text3, (40, 100))

def draw_game_over(surface, winner):

    font_big = pygame.font.SysFont(None, 60)

    text = font_big.render(
        f"Juego terminado - Jugador {winner} ganó",
        True,
        (0,0,0)
    )

    rect = text.get_rect(center=(WIDTH//2, 120))

    surface.blit(text, rect)

def draw_button(surface, rect, text):

    font = pygame.font.SysFont(None, 30)

    pygame.draw.rect(surface, (200,200,200), rect)
    pygame.draw.rect(surface, (0,0,0), rect, 2)

    label = font.render(text, True, (0,0,0))
    text_rect = label.get_rect(center=rect.center)

    surface.blit(label, text_rect)

def confirm_exit(screen):

    font = pygame.font.SysFont(None, 36)

    yes_rect = pygame.Rect(300, 320, 100, 50)
    no_rect = pygame.Rect(420, 320, 100, 50)

    while True:

        screen.fill((240,240,240))

        text = font.render("¿Desea cerrar el juego?", True, (0,0,0))
        screen.blit(text, (260,250))

        draw_button(screen, yes_rect, "SI")
        draw_button(screen, no_rect, "NO")

        pygame.display.flip()

        for event in pygame.event.get():

            if event.type == pygame.QUIT:
                return True

            if event.type == pygame.MOUSEBUTTONDOWN:

                if yes_rect.collidepoint(event.pos):
                    return True

                if no_rect.collidepoint(event.pos):
                    return False

def find_winning_path(board, player):

    size = board.size
    visited = set()
    stack = []

    if player == 1:  # conecta izquierda → derecha
        for r in range(size):
            if board.board[r][0] == player:
                stack.append((r,0,[(r,0)]))
    else:  # conecta arriba → abajo
        for c in range(size):
            if board.board[0][c] == player:
                stack.append((0,c,[(0,c)]))

    directions = [(-1,0),(1,0),(0,-1),(0,1),(-1,1),(1,-1)]

    while stack:

        r,c,path = stack.pop()

        if (r,c) in visited:
            continue

        visited.add((r,c))

        if player == 1 and c == size-1:
            return path

        if player == 2 and r == size-1:
            return path

        for dr,dc in directions:

            nr = r + dr
            nc = c + dc

            if 0 <= nr < size and 0 <= nc < size:

                if board.board[nr][nc] == player:
                    stack.append((nr,nc,path+[(nr,nc)]))

    return []

def visualize(board, winner):

    pygame.init()

    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("HEX Board")

    winning_path = find_winning_path(board, winner)

    running = True

    while running:

        screen.fill((255,255,255))

        draw_game_over(screen, winner)

        draw_board(screen, board, None, winning_path)

        pygame.display.flip()

        for event in pygame.event.get():
            if event.type == pygame.QUIT:
                if confirm_exit(screen):
                    pygame.quit()
                    return

    pygame.quit()

def show_board_once(board, player, move, think_time):

    pygame.init()

    screen = pygame.display.set_mode((WIDTH, HEIGHT))
    pygame.display.set_caption("HEX Board")

    button_rect = pygame.Rect(600, 40, 160, 50)

    waiting = True

    while waiting:

        screen.fill((255,255,255))

        draw_info(screen, player, move, think_time)

        draw_board(screen, board, move)

        draw_button(screen, button_rect, "Siguiente jugada")

        pygame.display.flip()

        for event in pygame.event.get():

            if event.type == pygame.QUIT:

                if confirm_exit(screen):
                    pygame.quit()
                    sys.exit()

            if event.type == pygame.MOUSEBUTTONDOWN:

                if button_rect.collidepoint(event.pos):
                    waiting = False
