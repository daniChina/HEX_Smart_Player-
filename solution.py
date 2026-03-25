from player import Player
from board import HexBoard

import math
import random
import time
import heapq
from collections import deque


# =============================================================================
# ZOBRIST HASHING
# =============================================================================
# Se genera una tabla de números aleatorios de 64 bits al importar el módulo.
# Cada celda (r, c) tiene un número para cada posible valor (0=vacío, 1, 2).
# El hash de un tablero es el XOR de los números correspondientes a cada
# celda ocupada. La propiedad clave: XOR es su propio inverso, así que
# colocar una ficha es una operación O(1): h ^= ZOBRIST[r][c][valor].

# Diccionario de números Zobrist generados bajo demanda.
# Clave: (r, c, valor)  →  entero de 64 bits aleatorio.
# Al usar un dict en vez de una lista fija, el tablero puede ser
# de CUALQUIER tamaño sin límite: la primera vez que se necesita
# una celda nueva se genera su número y se cachea.
_ZOBRIST: dict = {}

def _z(r: int, c: int, v: int) -> int:
    """Devuelve (y genera si no existe) el número Zobrist para (r,c,v)."""
    key = (r, c, v)
    if key not in _ZOBRIST:
        _ZOBRIST[key] = random.getrandbits(64)
    return _ZOBRIST[key]

def _zobrist_hash_full(cells: list, size: int) -> int:
    """Hash inicial calculado desde cero — se llama una sola vez."""
    h = 0
    for r in range(size):
        for c in range(size):
            v = cells[r][c]
            if v != 0:
                h ^= _z(r, c, v)
    return h

def _zobrist_update(h: int, r: int, c: int,
                    old_val: int, new_val: int) -> int:
    """Actualización incremental O(1): quita el valor viejo, pone el nuevo."""
    if old_val != 0:
        h ^= _z(r, c, old_val)
    if new_val != 0:
        h ^= _z(r, c, new_val)
    return h


# =============================================================================
# SmartPlayer
# =============================================================================

class SmartPlayer(Player):
    """
    Jugador MCTS con siete técnicas:
      1. Detección inmediata
      2. Progressive widening
      3. RAVE
      4. Rollout guiado
      5. Tabla de transposiciones con Zobrist hashing
      6. Poda temprana tipo alpha-beta en la selección UCB+RAVE
      7. Pesos estructurales (puentes, bordes, centro) en Dijkstra
    """

    def play(self, board: HexBoard) -> tuple:
        TIME_LIMIT = 4.5
        start  = time.perf_counter()
        my_id  = self.player_id
        opp_id = 3 - my_id

        state = BoardState.from_hexboard(board)

        legal = state.get_legal_moves()
        if not legal:
            raise RuntimeError("Sin movimientos legales.")
        if len(legal) == 1:
            return legal[0]

        # ── 0. Detección inmediata ────────────────────────────────────────
        for move in legal:
            if state.apply_move(move, my_id).check_winner() == my_id:
                return move
        for move in legal:
            if state.apply_move(move, opp_id).check_winner() == opp_id:
                return move

        # ── Inicialización MCTS ───────────────────────────────────────────
        rave_stats: dict = {m: [0, 0] for m in legal}

        # [OPT-1] Tabla de transposiciones local a este turno.
        # Mapea zobrist_hash -> Node. Local para evitar acumulación de
        # memoria entre turnos; cada llamada a play() empieza limpia.
        trans_table: dict = {}

        root = Node(state=state, move=None, parent=None,
                    player_who_moved=opp_id, rave_stats=rave_stats,
                    trans_table=trans_table)

        while time.perf_counter() - start < TIME_LIMIT:
            node = self._select(root)
            if not node.is_terminal():
                node = self._expand(node)
            winner, played = self._simulate(node)
            self._backpropagate(node, winner, played, rave_stats)

        best = max(root.children, key=lambda c: c.visits)
        return best.move

    # ─────────────────────────────────────────────────────────────────────
    # SELECCIÓN — UCB1 + RAVE + poda
    # ─────────────────────────────────────────────────────────────────────

    def _select(self, node: 'Node') -> 'Node':
        while node.is_fully_expanded() and not node.is_terminal():
            node = self._best_ucb_rave(node)
        return node

    def _best_ucb_rave(self, node: 'Node') -> 'Node':
        """
        Poda temprana sobre UCB1 + RAVE.

        Para cada hijo calculamos una cota superior conservadora:
            upper_bound = 1.0 + C * sqrt(ln N / n_i)
        donde 1.0 es el win-rate máximo posible (victoria en todas las
        simulaciones futuras). Si upper_bound ≤ mejor_score_ya_encontrado,
        ese hijo NUNCA podrá superar al mejor actual → lo saltamos.

        La poda es segura (no descarta nunca el hijo óptimo) porque
        upper_bound ≥ score_real siempre.  Reduce el trabajo en nodos con
        muchos hijos donde hay claramente dominados.
        """
        C     = math.sqrt(2)
        log_N = math.log(node.visits) if node.visits > 0 else 0

        best_node  = None
        best_score = -float('inf')

        for child in node.children:
            if child.visits == 0:
                return child   # nodo no visitado tiene prioridad absoluta

            explore = C * math.sqrt(log_N / child.visits)

            # [OPT-2] Cota superior: win_rate = 1 (optimista) + exploración
            upper_bound = 1.0 + explore
            if upper_bound <= best_score:
                continue       # poda: imposible mejorar best_score

            # Score real UCB1 + RAVE
            ucb1 = child.wins / child.visits + explore
            rw, rn = node.rave_stats.get(child.move, [0, 0])
            rave   = (rw / rn) if rn > 0 else 0.5
            beta   = math.sqrt(50 / (3 * child.visits + 50))
            s      = (1 - beta) * ucb1 + beta * rave

            if s > best_score:
                best_score = s
                best_node  = child

        return best_node

    # ─────────────────────────────────────────────────────────────────────
    # EXPANSIÓN — progressive widening + transposiciones
    # ─────────────────────────────────────────────────────────────────────

    def _expand(self, node: 'Node') -> 'Node':
        """
        Antes de crear un nodo nuevo, consulta la tabla de
        transposiciones.  Si el estado resultante de aplicar `move` ya
        existe en otra rama del árbol, reutilizamos ese nodo:
          - Sus estadísticas (visits, wins) ya incluyen información de
            simulaciones anteriores → la selección UCB se beneficia.
          - Se evita duplicar memoria y simulaciones redundantes.

        Si el estado es nuevo, se crea el nodo y se registra en la tabla.
        """
        untried     = node.get_untried_moves()
        next_player = 3 - node.player_who_moved

        # Puntuar candidatos con resistance_score (Dijkstra ponderado [OPT-3])
        scored = sorted(
            [(self._resistance_score(node.state, m, next_player), m)
             for m in untried],
            reverse=True
        )

        # Muestreo ponderado entre los 3 mejores
        top     = scored[:3]
        weights = [max(s, 0.01) for s, _ in top]
        total   = sum(weights)
        rv      = random.random() * total
        cumul   = 0.0
        move    = top[-1][1]
        for s, m in zip(weights, [m for _, m in top]):
            cumul += s
            if rv <= cumul:
                move = m
                break

        new_state = node.state.apply_move(move, next_player)
        h         = new_state.zobrist_hash   # O(1) gracias a hash incremental
        trans     = node.trans_table

        #  ¿El estado ya existe en la tabla?
        if h in trans:
            existing        = trans[h]
            # Redirigir parent al nodo actual para que la retropropagación
            # de esta iteración suba por la rama correcta
            existing.parent = node
            node.children.append(existing)
            return existing

        # Estado nuevo: crear y registrar
        child = Node(state=new_state, move=move, parent=node,
                     player_who_moved=next_player,
                     rave_stats=node.rave_stats,
                     trans_table=trans)
        trans[h] = child          # [OPT-1] registrar en tabla
        node.children.append(child)
        return child

    # ─────────────────────────────────────────────────────────────────────
    # SIMULACIÓN — rollout guiado
    # ─────────────────────────────────────────────────────────────────────

    def _simulate(self, node: 'Node') -> tuple:
        state   = node.state.clone()
        current = 3 - node.player_who_moved
        played  = []

        while True:
            winner = state.check_winner()
            if winner is not None:
                return winner, played

            moves = state.get_legal_moves()
            if not moves:
                return 3 - current, played

            if random.random() < 0.6:
                move = self._best_resistance_move(state, moves, current)
            else:
                move = random.choice(moves)

            played.append((move, current))
            state.apply_move_inplace(move, current)
            current = 3 - current

    # ─────────────────────────────────────────────────────────────────────
    # RETROPROPAGACIÓN — árbol + RAVE 
    # ─────────────────────────────────────────────────────────────────────

    def _backpropagate(self, node: 'Node', winner: int,
                       played: list, rave_stats: dict):
        for move, player in played:
            if move in rave_stats:
                rave_stats[move][1] += 1
                if player == winner:
                    rave_stats[move][0] += 1

        while node is not None:
            node.visits += 1
            if node.player_who_moved == winner:
                node.wins += 1
            node = node.parent

    # ─────────────────────────────────────────────────────────────────────
    # PESOS ESTRUCTURALES
    # ─────────────────────────────────────────────────────────────────────

    def _cell_weight(self, state: 'BoardState',
                     row: int, col: int, player: int) -> float:
        """
        Coste de traversal de una celda vacía para Dijkstra.
        Valor base 1.0; se reduce si la celda es estratégicamente valiosa.

        Criterios (se aplica el descuento más bajo = más valioso):

        A) PUENTE  (peso 0.5)
           La celda es punto de conexión de un puente entre dos fichas
           propias: está en la intersección de vecinos de dos fichas propias
           no adyacentes entre sí.  Un puente es casi tan bueno como una
           ficha ya colocada porque el rival necesita DOS movimientos para
           bloquearlo.

        B) SEGUNDA LÍNEA DE BORDE  (peso 0.7)
           Filas/columnas 1 y N-2 del eje propio del jugador.  Estas celdas
           están en la "zona de aterrizaje" donde el camino suele terminar.

        C) CUADRANTE CENTRAL  (peso 0.85)
           Celdas en el cuarto interior del tablero.  Mayor conectividad
           potencial, útiles para construir cadenas largas.
        """
        N      = state.size
        cells  = state.cells
        weight = 1.0   # base

        # ── A) Detección de puente ────────────────────────────────────
        own_nb = [(nr, nc) for nr, nc in state.get_neighbors(row, col)
                  if cells[nr][nc] == player]

        if len(own_nb) >= 2:
            for i in range(len(own_nb)):
                for j in range(i + 1, len(own_nb)):
                    r1, c1 = own_nb[i]
                    r2, c2 = own_nb[j]
                    # Vecinos comunes de las dos fichas propias
                    shared = set(state.get_neighbors(r1, c1)) & \
                             set(state.get_neighbors(r2, c2))
                    if (row, col) in shared:
                        weight = min(weight, 0.5)
                        break
                if weight <= 0.5:
                    break

        # ── B) Segunda línea de borde propio ─────────────────────────
        if player == 2:                         # azul: eje vertical
            if row in (1, N - 2):
                weight = min(weight, 0.7)
        else:                                   # rojo: eje horizontal
            if col in (1, N - 2):
                weight = min(weight, 0.7)

        # ── C) Cuadrante central ──────────────────────────────────────
        m = N // 4
        if m <= row <= N - 1 - m and m <= col <= N - 1 - m:
            weight = min(weight, 0.85)

        return weight

    def _min_path_distance(self, state: 'BoardState', player: int) -> float:
        """
        Dijkstra con pesos estructurales.

        Coste por celda:
          - Propia   → 0.0
          - Vacía    → _cell_weight()  ∈ [0.5, 1.0]
          - Rival    → ∞

        Al ponderar, Dijkstra encuentra la ruta que no solo es corta en
        número de celdas sino que pasa por posiciones estratégicamente
        mejores (puentes, segunda línea, centro).
        """
        N     = state.size
        cells = state.cells
        INF   = float('inf')
        rival = 3 - player
        dist  = [[INF] * N for _ in range(N)]
        heap  = []

        if player == 2:
            for c in range(N):
                v = cells[0][c]
                if v == rival:
                    continue
                cost = 0.0 if v == player else self._cell_weight(state, 0, c, player)
                dist[0][c] = cost
                heapq.heappush(heap, (cost, 0, c))
        else:
            for r in range(N):
                v = cells[r][0]
                if v == rival:
                    continue
                cost = 0.0 if v == player else self._cell_weight(state, r, 0, player)
                dist[r][0] = cost
                heapq.heappush(heap, (cost, r, 0))

        while heap:
            d, r, c = heapq.heappop(heap)
            if d > dist[r][c]:
                continue
            if player == 2 and r == N - 1:
                return d
            if player == 1 and c == N - 1:
                return d
            for nr, nc in state.get_neighbors(r, c):
                v = cells[nr][nc]
                if v == rival:
                    continue
                step = 0.0 if v == player else self._cell_weight(state, nr, nc, player)
                nd   = d + step
                if nd < dist[nr][nc]:
                    dist[nr][nc] = nd
                    heapq.heappush(heap, (nd, nr, nc))

        return INF

    def _resistance_score(self, state: 'BoardState',
                           move: tuple, player: int) -> float:
        """
        Cuánto mejora la distancia Dijkstra ponderada [OPT-3] al colocar
        en `move`.  La mejora ahora refleja no solo longitud sino calidad
        estructural del camino.
        """
        d_before    = self._min_path_distance(state, player)
        d_after     = self._min_path_distance(state.apply_move(move, player), player)
        improvement = max(0.0, d_before - d_after)
        own_n = sum(1 for nr, nc in state.get_neighbors(*move)
                    if state.cells[nr][nc] == player)
        return improvement * 3 + own_n + 0.1

    def _best_resistance_move(self, state: 'BoardState',
                               moves: list, player: int) -> tuple:
        best, best_s = moves[0], -1.0
        for m in moves:
            s = self._resistance_score(state, m, player)
            if s > best_s:
                best_s = s
                best   = m
        return best


# =============================================================================
# Node — ahora con trans_table en __slots__ 
# =============================================================================

class Node:
    __slots__ = ('state', 'move', 'parent', 'player_who_moved',
                 'children', 'visits', 'wins',
                 '_untried_moves', '_terminal',
                 'rave_stats', 'trans_table')   # [OPT-1]

    def __init__(self, state, move, parent, player_who_moved,
                 rave_stats, trans_table):
        self.state            = state
        self.move             = move
        self.parent           = parent
        self.player_who_moved = player_who_moved
        self.rave_stats       = rave_stats
        self.trans_table      = trans_table    # referencia compartida
        self.children         = []
        self.visits           = 0
        self.wins             = 0
        self._untried_moves   = None
        self._terminal        = None

    def get_untried_moves(self) -> list:
        tried = {c.move for c in self.children}
        if self._untried_moves is None:
            self._untried_moves = [m for m in self.state.get_legal_moves()
                                   if m not in tried]
        else:
            self._untried_moves = [m for m in self._untried_moves
                                   if m not in tried]
        return self._untried_moves

    def is_fully_expanded(self) -> bool:
        return len(self.get_untried_moves()) == 0

    def is_terminal(self) -> bool:
        if self._terminal is None:
            self._terminal = self.state.check_winner() is not None
        return self._terminal


# =============================================================================
# BoardState — con Zobrist hash incremental
# =============================================================================

class BoardState:
    """
    Tablero interno con hash Zobrist mantenido incrementalmente.
    Cada apply_move actualiza el hash en O(1) en vez de recalcular en O(N²).
    """

    def __init__(self, size: int, cells: list, zobrist_hash: int = 0):
        self.size         = size
        self.cells        = cells
        self.zobrist_hash = zobrist_hash   
    @classmethod
    def from_hexboard(cls, board: HexBoard) -> 'BoardState':
        N = board.size
        try:
            cells = [[board.board[r][c] for c in range(N)] for r in range(N)]
        except AttributeError:
            cells = [[(board.cells[r][c] or 0) for c in range(N)] for r in range(N)]
        h = _zobrist_hash_full(cells, N)   # hash inicial
        return cls(N, cells, h)

    def clone(self) -> 'BoardState':
        # El clon hereda el hash actual; apply_move lo actualizará
        return BoardState(self.size, [row[:] for row in self.cells],
                          self.zobrist_hash)

    def apply_move(self, move: tuple, player: int) -> 'BoardState':
        """Nuevo estado con hash actualizado en O(1) [OPT-1]."""
        s       = self.clone()
        r, c    = move
        old_val = s.cells[r][c]       # siempre 0 (celda vacía)
        s.cells[r][c]    = player
        s.zobrist_hash   = _zobrist_update(s.zobrist_hash, r, c, old_val, player)
        return s

    def apply_move_inplace(self, move: tuple, player: int):
        """Modifica en sitio y actualiza hash incrementalmente."""
        r, c    = move
        old_val = self.cells[r][c]
        self.cells[r][c]   = player
        self.zobrist_hash  = _zobrist_update(self.zobrist_hash, r, c,
                                              old_val, player)

    def get_legal_moves(self) -> list:
        return [(r, c)
                for r in range(self.size)
                for c in range(self.size)
                if self.cells[r][c] == 0]

    def get_neighbors(self, row: int, col: int) -> list:
        N = self.size
        if row % 2 == 0:
            cands = [(row-1, col-1), (row-1, col),
                     (row,   col-1), (row,   col+1),
                     (row+1, col-1), (row+1, col)]
        else:
            cands = [(row-1, col),   (row-1, col+1),
                     (row,   col-1), (row,   col+1),
                     (row+1, col),   (row+1, col+1)]
        return [(r, c) for r, c in cands if 0 <= r < N and 0 <= c < N]

    def check_winner(self) -> 'int | None':
        if self._check_win(2): return 2
        if self._check_win(1): return 1
        return None

    def _check_win(self, player: int) -> bool:
        N     = self.size
        cells = self.cells
        vis   = [[False] * N for _ in range(N)]
        q     = deque()

        if player == 2:
            for c in range(N):
                if cells[0][c] == 2:
                    q.append((0, c)); vis[0][c] = True
            while q:
                r, c = q.popleft()
                if r == N - 1: return True
                for nr, nc in self.get_neighbors(r, c):
                    if not vis[nr][nc] and cells[nr][nc] == 2:
                        vis[nr][nc] = True; q.append((nr, nc))
        else:
            for r in range(N):
                if cells[r][0] == 1:
                    q.append((r, 0)); vis[r][0] = True
            while q:
                r, c = q.popleft()
                if c == N - 1: return True
                for nr, nc in self.get_neighbors(r, c):
                    if not vis[nr][nc] and cells[nr][nc] == 1:
                        vis[nr][nc] = True; q.append((nr, nc))
        return False
