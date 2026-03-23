import pygame
import math
import sys
import threading

from board import HexBoard
from solution import SmartPlayer
from random_player import RandomPlayer

# ── Dimensiones y colores ────────────────────────────────────────────────────
W, H     = 1100, 720
HEX_SIZE = 28
PANEL_X  = 760
BOARD_OX = 45
BOARD_OY = 90

C_BG       = (15,  17,  26)
C_PANEL    = (22,  26,  40)
C_BORDER   = (45,  52,  80)
C_TEXT     = (220, 225, 240)
C_SUBTEXT  = (120, 130, 160)
C_RED      = (220,  65,  65)
C_BLUE     = ( 55, 120, 220)
C_RDARK    = (140,  35,  35)
C_BDARK    = ( 30,  70, 145)
C_EMPTY    = ( 38,  44,  64)
C_EMBD     = ( 55,  65,  95)
C_GOLD     = (255, 195,  50)
C_GREEN    = ( 60, 200, 100)
C_WINGLOW  = (255, 215,   0)
C_HOVER    = ( 80, 200, 130)
C_BTN      = ( 40,  48,  75)
C_BTNHOV   = ( 60,  72, 115)
C_BTNACT   = ( 55, 120, 220)

# Fuentes: se rellenan en main() DESPUÉS de pygame.init()
FT = {}   # FT["title"], FT["h2"], FT["body"], FT["small"], FT["mono"]


def _init_fonts():
    """Crea todas las fuentes. Llamar DESPUÉS de pygame.init()."""
    def f(size, bold=False):
        # pygame.font.Font(None, size) usa la fuente built-in de pygame.
        # Nunca lanza excepción ni devuelve None en ningún sistema.
        return pygame.font.Font(None, size)
    FT["title"] = f(52, bold=True)
    FT["h2"]    = f(34, bold=True)
    FT["body"]  = f(26)
    FT["small"] = f(20)
    FT["mono"]  = f(22)


# ── Utilidades de dibujo ─────────────────────────────────────────────────────

def _corners(cx, cy, size):
    return [(cx + size * math.cos(math.radians(60*i - 30)),
             cy + size * math.sin(math.radians(60*i - 30)))
            for i in range(6)]

def _hex(surf, cx, cy, size, fill, border, bw=1):
    pts = _corners(cx, cy, size)
    pygame.draw.polygon(surf, fill,   pts)
    pygame.draw.polygon(surf, border, pts, bw)

def _center(r, c):
    hw = HEX_SIZE * 2
    hh = math.sqrt(3) * HEX_SIZE
    x  = BOARD_OX + c * hw * 0.75 + HEX_SIZE
    y  = BOARD_OY + r * hh + HEX_SIZE
    if r % 2 == 1:
        x += hw * 0.375
    return x, y

def _pix_to_cell(px, py, N):
    best, bd = None, HEX_SIZE * 1.1
    for r in range(N):
        for c in range(N):
            cx, cy = _center(r, c)
            d = math.hypot(px - cx, py - cy)
            if d < bd:
                bd, best = d, (r, c)
    return best

def _btn(surf, rect, text, hover=False, active=False, fkey="body"):
    col = C_BTNACT if active else (C_BTNHOV if hover else C_BTN)
    pygame.draw.rect(surf, col,      rect, border_radius=8)
    pygame.draw.rect(surf, C_BORDER, rect, 1, border_radius=8)
    lbl = FT[fkey].render(text, True, C_TEXT)
    surf.blit(lbl, lbl.get_rect(center=rect.center))

def _tc(surf, text, y, fkey, color=None):
    color = color or C_TEXT
    lbl = FT[fkey].render(text, True, color)
    surf.blit(lbl, (W//2 - lbl.get_width()//2, y))

def _tl(surf, text, x, y, fkey, color=None):
    color = color or C_TEXT
    lbl = FT[fkey].render(text, True, color)
    surf.blit(lbl, (x, y))


# ── Camino ganador ───────────────────────────────────────────────────────────

def _winning_path(board, player):
    N = board.size
    vis, stack = set(), []
    de = [(-1,-1),(-1,0),(0,-1),(0,1),(1,-1),(1,0)]
    do = [(-1,0),(-1,1),(0,-1),(0,1),(1,0),(1,1)]
    if player == 1:
        for r in range(N):
            if board.board[r][0] == 1:
                stack.append((r, 0, [(r,0)]))
    else:
        for c in range(N):
            if board.board[0][c] == 2:
                stack.append((0, c, [(0,c)]))
    while stack:
        r, c, path = stack.pop()
        if (r,c) in vis: continue
        vis.add((r,c))
        if player==1 and c==N-1: return set(path)
        if player==2 and r==N-1: return set(path)
        dirs = de if r%2==0 else do
        for dr,dc in dirs:
            nr,nc = r+dr, c+dc
            if 0<=nr<N and 0<=nc<N and board.board[nr][nc]==player:
                stack.append((nr, nc, path+[(nr,nc)]))
    return set()


# ── Etiquetas de jugadores ───────────────────────────────────────────────────

def _labels(mode):
    if mode == "human_smart":  return "Humano", "SmartPlayer"
    if mode == "human_random": return "Humano", "Random"
    return "SmartPlayer", "Random"


# ── MENÚ PRINCIPAL ───────────────────────────────────────────────────────────

def run_menu(screen):
    pygame.display.set_caption("HEX — Menú")
    clock  = pygame.time.Clock()
    cfg    = {"mode":"human_smart","size":7,"games":3,"hcolor":1}
    mouse  = (0,0)

    R = pygame.Rect
    modes  = [R(200,210,230,44), R(200,264,230,44), R(200,318,230,44)]
    mlbls  = ["Humano vs SmartPlayer","Humano vs Random","Smart vs Random (auto)"]
    mvals  = ["human_smart","human_random","auto"]

    sizes  = [R(200,418,68,40),R(278,418,68,40),R(356,418,68,40),R(434,418,80,40)]
    slbls  = ["5×5","7×7","9×9","11×11"]
    svals  = [5,7,9,11]

    gnums  = [R(200,500,55,40),R(265,500,55,40),R(330,500,55,40),R(395,500,55,40)]
    glbls  = ["1","3","5","10"]
    gvals  = [1,3,5,10]

    clrs   = [R(200,582,155,40),R(365,582,155,40)]
    clbls  = ["Empezar como Rojo","Empezar como Azul"]
    cvals  = [1,2]

    start  = R(W//2-110, H-68, 220,48)

    while True:
        screen.fill(C_BG)
        for i in range(0,W,60): pygame.draw.line(screen,(25,30,48),(i,0),(i,H))
        for j in range(0,H,60): pygame.draw.line(screen,(25,30,48),(0,j),(W,j))

        _tc(screen,"HEX",32,"title",C_GOLD)
        _tc(screen,"Configuración de partida",84,"body",C_SUBTEXT)

        _tl(screen,"MODO DE JUEGO",200,178,"h2",C_SUBTEXT)
        for i,(r,l,v) in enumerate(zip(modes,mlbls,mvals)):
            _btn(screen,r,l,r.collidepoint(mouse),cfg["mode"]==v)

        _tl(screen,"TAMAÑO",200,390,"h2",C_SUBTEXT)
        for r,l,v in zip(sizes,slbls,svals):
            _btn(screen,r,l,r.collidepoint(mouse),cfg["size"]==v)

        _tl(screen,"PARTIDAS",200,472,"h2",C_SUBTEXT)
        for r,l,v in zip(gnums,glbls,gvals):
            _btn(screen,r,l,r.collidepoint(mouse),cfg["games"]==v)

        if cfg["mode"]!="auto":
            _tl(screen,"TU COLOR (1ª partida)",200,554,"h2",C_SUBTEXT)
            for r,l,v in zip(clrs,clbls,cvals):
                _btn(screen,r,l,r.collidepoint(mouse),cfg["hcolor"]==v)

        _btn(screen,start,"▶  JUGAR",start.collidepoint(mouse),fkey="h2")

        # Panel de reglas
        rx=650
        _tl(screen,"REGLAS",rx,178,"h2",C_SUBTEXT)
        for i,line in enumerate([
            "Rojo (J1): izquierda → derecha",
            "Azul (J2): arriba → abajo",
            "",
            "Clic en celda vacía para jugar",
            "El primer turno alterna cada partida",
            "",
            "ESC durante partida → menú",
        ]):
            _tl(screen,line,rx,216+i*28,"body",C_TEXT if line else C_SUBTEXT)

        pygame.display.flip()
        clock.tick(60)

        for ev in pygame.event.get():
            if ev.type==pygame.QUIT: pygame.quit(); sys.exit()
            if ev.type==pygame.MOUSEMOTION: mouse=ev.pos
            if ev.type==pygame.MOUSEBUTTONDOWN and ev.button==1:
                p=ev.pos
                for r,v in zip(modes,mvals):
                    if r.collidepoint(p): cfg["mode"]=v
                for r,v in zip(sizes,svals):
                    if r.collidepoint(p): cfg["size"]=v
                for r,v in zip(gnums,gvals):
                    if r.collidepoint(p): cfg["games"]=v
                if cfg["mode"]!="auto":
                    for r,v in zip(clrs,cvals):
                        if r.collidepoint(p): cfg["hcolor"]=v
                if start.collidepoint(p): return cfg


# ── RESULTADOS FINALES ───────────────────────────────────────────────────────

def run_results(screen, scores, mode):
    pygame.display.set_caption("HEX — Resultados")
    clock    = pygame.time.Clock()
    l1,l2    = _labels(mode)
    back     = pygame.Rect(W//2-215,H-78,200,48)
    quit_btn = pygame.Rect(W//2+15, H-78,200,48)
    mouse    = (0,0)

    while True:
        screen.fill(C_BG)
        _tc(screen,"RESULTADOS FINALES",55,"title",C_GOLD)
        s1,s2  = scores
        total  = s1+s2
        _tc(screen,f"{l1}   {s1} — {s2}   {l2}",150,"h2")

        bx,by,bw,bh = W//2-240,205,480,30
        pygame.draw.rect(screen,C_EMPTY,(bx,by,bw,bh),border_radius=6)
        if total:
            w1=int(bw*s1/total)
            if w1:    pygame.draw.rect(screen,C_RED, (bx,by,w1,bh),border_radius=6)
            if w1<bw: pygame.draw.rect(screen,C_BLUE,(bx+w1,by,bw-w1,bh),border_radius=6)
        pct1=int(100*s1/total) if total else 0
        _tl(screen,f"{pct1}%",       bx,   by+bh+4,"small",C_RED)
        _tl(screen,f"{100-pct1}%",   bx+bw-40,by+bh+4,"small",C_BLUE)

        if   s1>s2: msg,col=f"¡Ganó {l1}!",C_RED
        elif s2>s1: msg,col=f"¡Ganó {l2}!",C_BLUE
        else:       msg,col="Serie empatada",C_GOLD
        _tc(screen,msg,278,"h2",col)

        _btn(screen,back,    "↩  Menú principal",back.collidepoint(mouse))
        _btn(screen,quit_btn,"✕  Salir",          quit_btn.collidepoint(mouse))

        pygame.display.flip(); clock.tick(60)

        for ev in pygame.event.get():
            if ev.type==pygame.QUIT: pygame.quit(); sys.exit()
            if ev.type==pygame.MOUSEMOTION: mouse=ev.pos
            if ev.type==pygame.MOUSEBUTTONDOWN and ev.button==1:
                if back.collidepoint(ev.pos):     return "menu"
                if quit_btn.collidepoint(ev.pos): pygame.quit(); sys.exit()


# ── SESIÓN DE PARTIDAS ───────────────────────────────────────────────────────

def run_session(screen, cfg):
    mode   = cfg["mode"]
    N      = cfg["size"]
    ngames = cfg["games"]
    l1,l2  = _labels(mode)
    scores = [0,0]

    for idx in range(ngames):
        first = 1 if idx%2==0 else 2
        res   = run_game(screen, cfg, idx, ngames, scores, first, l1, l2)
        if res=="quit": pygame.quit(); sys.exit()
        if res=="menu": return "menu"
        if res in (1,2): scores[res-1]+=1

    return run_results(screen, scores, mode)


# ── PARTIDA INDIVIDUAL ───────────────────────────────────────────────────────

def run_game(screen, cfg, idx, ngames, scores, first, l1, l2):
    pygame.display.set_caption(f"HEX — Partida {idx+1}/{ngames}")
    clock   = pygame.time.Clock()
    mode    = cfg["mode"]
    N       = cfg["size"]
    ehuman  = cfg["hcolor"] if idx%2==0 else 3-cfg["hcolor"]
    board   = HexBoard(N)

    def mkp(pid):
        if mode=="human_smart":  return "human" if pid==ehuman else SmartPlayer(pid)
        if mode=="human_random": return "human" if pid==ehuman else RandomPlayer(pid)
        return SmartPlayer(pid) if pid==1 else RandomPlayer(pid)

    players = {1:mkp(1), 2:mkp(2)}
    turn    = first
    last    = None
    winner  = None
    wpath   = set()
    log     = []
    hover   = None
    ai_on   = False
    ai_res  = [None]

    def ai_fn(pid):
        ai_res[0] = players[pid].play(board.clone())

    while True:
        mp = pygame.mouse.get_pos()
        hover = None
        if winner is None and players[turn]=="human":
            cell = _pix_to_cell(*mp, N)
            if cell and board.board[cell[0]][cell[1]]==0:
                hover = cell

        if winner is None and players[turn]!="human" and not ai_on:
            ai_on=True; ai_res[0]=None
            threading.Thread(target=ai_fn,args=(turn,),daemon=True).start()

        if ai_on and ai_res[0] is not None:
            mv=ai_res[0]; ai_on=False
            r,c=mv
            if board.board[r][c]==0:
                board.place_piece(r,c,turn)
                last=mv
                log.append(f"J{turn} ({l1 if turn==1 else l2}): ({r},{c})")
                if board.check_connection(turn):
                    winner=turn; wpath=_winning_path(board,winner)
                else:
                    turn=3-turn

        # ── Dibujo ────────────────────────────────────────────────────
        screen.fill(C_BG)

        # Indicadores de borde
        for rr in range(N):
            cx0,cy0=_center(rr,0);     cxN,cyN=_center(rr,N-1)
            pygame.draw.circle(screen,C_RDARK,(int(cx0-HEX_SIZE*.9),int(cy0)),5)
            pygame.draw.circle(screen,C_RDARK,(int(cxN+HEX_SIZE*.9),int(cyN)),5)
        for cc in range(N):
            cx0,cy0=_center(0,cc);     cxN,cyN=_center(N-1,cc)
            pygame.draw.circle(screen,C_BDARK,(int(cx0),int(cy0-HEX_SIZE*.95)),5)
            pygame.draw.circle(screen,C_BDARK,(int(cxN),int(cyN+HEX_SIZE*.95)),5)

        # Celdas
        for rr in range(N):
            for cc in range(N):
                cx,cy=_center(rr,cc)
                v=board.board[rr][cc]
                if   v==1:              fill,brd,bw=C_RED, C_RDARK,1
                elif v==2:              fill,brd,bw=C_BLUE,C_BDARK,1
                elif hover==(rr,cc):   fill,brd,bw=C_HOVER,C_GREEN,2
                else:                  fill,brd,bw=C_EMPTY,C_EMBD,1
                if last==(rr,cc):      brd,bw=C_GOLD,3
                if (rr,cc) in wpath:   brd,bw=C_WINGLOW,4
                _hex(screen,cx,cy,HEX_SIZE-1,fill,brd,bw)
                lbl=FT["small"].render(f"{rr},{cc}",True,
                                       (200,200,200) if v==0 else (255,255,255))
                screen.blit(lbl,(cx-lbl.get_width()//2,cy-lbl.get_height()//2))

        # Panel
        pygame.draw.rect(screen,C_PANEL,(PANEL_X,0,W-PANEL_X,H))
        pygame.draw.line(screen,C_BORDER,(PANEL_X,0),(PANEL_X,H),2)
        px,py=PANEL_X+18,16

        _tl(screen,f"PARTIDA {idx+1}/{ngames}",px,py,"h2",C_GOLD);  py+=36
        sc=FT["h2"].render(f"{scores[0]}  —  {scores[1]}",True,C_TEXT)
        screen.blit(sc,(px,py)); py+=32
        _tl(screen,l1,px,py,"small",C_RED)
        _tl(screen,l2,px+120,py,"small",C_BLUE); py+=26
        pygame.draw.line(screen,C_BORDER,(px,py),(px+300,py)); py+=10

        strt=l1 if first==1 else l2
        _tl(screen,f"Inicia: {strt}",px,py,"small",C_SUBTEXT); py+=22

        if winner:
            wn=l1 if winner==1 else l2
            wc=C_RED if winner==1 else C_BLUE
            _tl(screen,f"¡Ganó {wn}!",px,py,"h2",wc)
        else:
            cn=l1 if turn==1 else l2; cc2=C_RED if turn==1 else C_BLUE
            if ai_on:
                _tl(screen,f"Pensando... ({cn})",px,py,"body",C_GOLD)
            else:
                msg="Tu turno" if mode!="auto" and turn==ehuman else f"Turno: {cn}"
                _tl(screen,msg,px,py,"body",cc2)
        py+=30

        pygame.draw.rect(screen,C_RED, (px,py,12,12),border_radius=3)
        _tl(screen,f"J1={l1}",px+16,py,"small"); py+=20
        pygame.draw.rect(screen,C_BLUE,(px,py,12,12),border_radius=3)
        _tl(screen,f"J2={l2}",px+16,py,"small"); py+=26
        pygame.draw.line(screen,C_BORDER,(px,py),(px+300,py)); py+=10

        _tl(screen,"HISTORIAL",px,py,"small",C_SUBTEXT); py+=18
        for line in log[-14:]:
            col=C_RED if line.startswith("J1") else C_BLUE
            _tl(screen,line,px,py,"mono",col); py+=18

        _tl(screen,"ESC → menú",px,H-185,"small",C_SUBTEXT)
        if not winner and mode!="auto" and not ai_on and turn==ehuman:
            _tl(screen,"Clic en celda para jugar",px,H-162,"small",C_SUBTEXT)

        if winner:
            is_last=idx+1==ngames
            nlbl="Ver resultados ▶" if is_last else "Siguiente partida ▶"
            mpos=pygame.mouse.get_pos()
            mb=pygame.Rect(px,H-135,300,42)
            nb=pygame.Rect(px,H-82, 300,42)
            _btn(screen,mb,"↩  Menú principal",mb.collidepoint(mpos))
            _btn(screen,nb,nlbl,nb.collidepoint(mpos),active=True)

        pygame.display.flip(); clock.tick(60)

        # ── Eventos ───────────────────────────────────────────────────
        for ev in pygame.event.get():
            if ev.type==pygame.QUIT: return "quit"
            if ev.type==pygame.KEYDOWN and ev.key==pygame.K_ESCAPE:
                return "menu"
            if ev.type==pygame.MOUSEBUTTONDOWN and ev.button==1:
                p=ev.pos
                if winner is not None:
                    nb=pygame.Rect(px,H-82, 300,42)
                    mb=pygame.Rect(px,H-135,300,42)
                    if nb.collidepoint(p): return winner
                    if mb.collidepoint(p): return "menu"
                if winner is None and players[turn]=="human" and not ai_on:
                    cell=_pix_to_cell(*p,N)
                    if cell and board.board[cell[0]][cell[1]]==0:
                        r2,c2=cell
                        board.place_piece(r2,c2,turn)
                        last=(r2,c2)
                        log.append(f"J{turn} ({l1 if turn==1 else l2}): ({r2},{c2})")
                        if board.check_connection(turn):
                            winner=turn; wpath=_winning_path(board,winner)
                        else:
                            turn=3-turn


# ── MAIN ─────────────────────────────────────────────────────────────────────

def main():
    pygame.init()                            # 1. inicializar pygame
    screen = pygame.display.set_mode((W,H)) # 2. crear ventana
    pygame.display.set_caption("HEX")
    _init_fonts()                            # 3. fuentes (DESPUÉS de init)

    while True:
        cfg = run_menu(screen)
        res = run_session(screen, cfg)
        if res == "quit":
            break
        # res=="menu" -> vuelve al bucle

    pygame.quit()
    sys.exit()


if __name__ == "__main__":
    main()
