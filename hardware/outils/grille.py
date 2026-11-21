#!/usr/bin/env python3
"""Routeur sur grille pour terminer le routage (API pcbnew de KiCad 9, numpy, Pillow).

Freerouting laisse quelques liaisons non routées, et l'éventail de router.py ne trouve pas
de place pour la via de certaines pastilles de plan. Ce module les termine :

  - le cuivre des 4 couches est dessiné sur une grille de 0,05 mm, chaque élément gonflé de
    son isolement + 0,1 mm (demi-largeur d'une piste de 0,2 mm). Une case vaut 0 (libre),
    le numéro du net qui l'occupe, ou -1 (plusieurs nets, zone interdite, bord de carte) ;
  - une liaison est cherchée par A* sur F.Cu et B.Cu (8 directions, via = 2 mm de piste),
    puis lissée (segments droits tant que la grille est libre) ;
  - pour une pastille de plan (GND, +3V3, GND_ISO, VISO), la cible est la case la plus proche
    où une via tient dans le plan de son net sur In1 ou In2 ;
  - chaque piste et via ajoutée est redessinée dans la grille avant la liaison suivante.

Le DRC de KiCad reste le juge : router.py relance le DRC après chaque tour.
"""
import heapq
import math

import numpy as np
import pcbnew
from PIL import Image, ImageDraw

PAS = 0.05            # mm par case
CL_MIN = 0.15         # isolement minimal des règles (classe Default)
DEMI = 0.10           # demi-largeur de la piste de référence (0,2 mm)
VIA_D, VIA_TROU = 0.6, 0.3
BORD = 0.5            # isolement cuivre - bord de carte
TROU = 0.25           # isolement cuivre - trou, et trou - trou
SUR = 4               # sous-pixels par case pour dessiner les polygones
MARGE = 0.015         # marge d'arrondi (sommets arrondis au sous-pixel, 0,0125 mm)
MARGE_VIA = 0.05      # marge de plus pour une via : le cuivre voisin peut passer entre deux centres de case
COUT_VIA = 60         # une via coûte 3 mm de piste
ROUTAGE = (pcbnew.F_Cu, pcbnew.B_Cu)
CUIVRE = (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu)
DIRS = [(-1, 0, 1.0), (1, 0, 1.0), (0, -1, 1.0), (0, 1, 1.0),
        (-1, -1, 1.4142), (-1, 1, 1.4142), (1, -1, 1.4142), (1, 1, 1.4142)]


def mm(v):
    return pcbnew.ToMM(v)


def disque(r):
    """Décalages (di, dj) d'un disque de rayon r cases."""
    n = int(math.ceil(r))
    return [(di, dj) for di in range(-n, n + 1) for dj in range(-n, n + 1) if di * di + dj * dj <= r * r + 1e-9]


def eroder(m, r):
    """Cases de m dont tout le disque de rayon r (cases) est dans m (dehors = occupé)."""
    if r <= 0:
        return m.copy()
    n = int(math.ceil(r))
    p = np.zeros((m.shape[0] + 2 * n, m.shape[1] + 2 * n), bool)
    p[n:-n, n:-n] = m
    out = m.copy()
    for di, dj in disque(r):
        out &= p[n + di:n + di + m.shape[0], n + dj:n + dj + m.shape[1]]
    return out


class Grille:
    def __init__(self, board, fin=False, couches=ROUTAGE):
        """fin : grille des passages étroits, pour pistes de 0,15 mm et vias de 0,45 / 0,2 mm
        (les minimums des règles de la carte), utilisée en dernier recours.
        couches : couches de routage ; In2.Cu en plus en tout dernier recours (quelques pistes
        courtes dans le plan +3V3, qui se découpe autour)."""
        self.b = board
        self.routage = tuple(couches)
        self.demi = 0.075 if fin else DEMI
        self.via_d, self.via_trou = (0.45, 0.2) if fin else (VIA_D, VIA_TROU)
        bb = board.GetBoardEdgesBoundingBox()
        self.x0 = mm(bb.GetX()) - 1.0
        self.y0 = mm(bb.GetY()) - 1.0
        self.W = int(math.ceil((mm(bb.GetWidth()) + 2.0) / PAS)) + 1
        self.H = int(math.ceil((mm(bb.GetHeight()) + 2.0) / PAS)) + 1
        self.own = {L: np.zeros((self.H, self.W), np.int32) for L in CUIVRE}
        # pistes non verrouillées : dessinées à part (« souples »), on peut les traverser en
        # payant, puis les arracher (routage négocié)
        self.mou = {L: np.zeros((self.H, self.W), np.int32) for L in self.routage}
        self.novia = np.zeros((self.H, self.W), bool)
        self.trous = np.zeros((self.H, self.W), bool)   # centres de via interdits (trou - trou)
        self._bords()
        for fp in board.GetFootprints():
            for p in fp.Pads():
                self.ajouter(p)
        for t in board.GetTracks():
            self.ajouter(t)
        for z in board.Zones():
            if z.GetIsRuleArea():
                self._interdit(z)
            else:
                for L in ROUTAGE:
                    if z.IsOnLayer(L):
                        self._peindre_poly(L, self._gonfle_zone(z, L), z.GetNetCode())
        if pcbnew.In2_Cu in self.routage:
            # pistes sur In2 : seulement dans le plan +3V3 (partie logique), à 0,5 mm de son bord,
            # hors des zones interdites
            ok = np.zeros((self.H, self.W), bool)
            for z in board.Zones():
                if not z.GetIsRuleArea() and z.IsOnLayer(pcbnew.In2_Cu) and z.GetNetname() == '+3V3':
                    r = self._masque(z.Outline())
                    if r is not None:
                        i0, j0, m = r
                        ok[i0:i0 + m.shape[0], j0:j0 + m.shape[1]] |= m
            for z in board.Zones():
                if z.GetIsRuleArea() and z.GetDoNotAllowTracks() and z.IsOnLayer(pcbnew.In2_Cu):
                    r = self._masque(z.Outline())
                    if r is not None:
                        i0, j0, m = r
                        ok[i0:i0 + m.shape[0], j0:j0 + m.shape[1]] &= ~m
            self.ok_in2 = eroder(ok, (0.5 + self.demi) / PAS)

    # ------------------------------------------------------------------ dessin
    def ij(self, x, y):
        return int(round((y - self.y0) / PAS)), int(round((x - self.x0) / PAS))

    def xy(self, i, j):
        return self.x0 + j * PAS, self.y0 + i * PAS

    def _masque(self, poly):
        """Masque booléen (fenêtre i0, j0) d'un SHAPE_POLY_SET (nm)."""
        bb = poly.BBox()
        i0 = max(0, int(math.floor((mm(bb.GetY()) - self.y0) / PAS)) - 1)
        j0 = max(0, int(math.floor((mm(bb.GetX()) - self.x0) / PAS)) - 1)
        i1 = min(self.H, int(math.ceil((mm(bb.GetBottom()) - self.y0) / PAS)) + 2)
        j1 = min(self.W, int(math.ceil((mm(bb.GetRight()) - self.x0) / PAS)) + 2)
        if i1 <= i0 or j1 <= j0:
            return None
        # dessin sur-échantillonné (k sous-pixels par case) : Pillow arrondit les sommets au pixel ;
        # une case est occupée si son centre (sous-pixel k*i, k*j) est dans le polygone
        k = SUR if (i1 - i0) * (j1 - j0) < 400_000 else 1
        img = Image.new('1', ((j1 - j0 - 1) * k + 1, (i1 - i0 - 1) * k + 1), 0)
        d = ImageDraw.Draw(img)

        def pts(ch):
            return [(((mm(ch.CPoint(n).x) - self.x0) / PAS - j0) * k, ((mm(ch.CPoint(n).y) - self.y0) / PAS - i0) * k)
                    for n in range(ch.PointCount())]
        for n in range(poly.OutlineCount()):
            p = pts(poly.Outline(n))
            if len(p) > 2:
                d.polygon(p, fill=1, outline=1)
            for h in range(poly.HoleCount(n)):
                q = pts(poly.Hole(n, h))
                if len(q) > 2:
                    d.polygon(q, fill=0, outline=0)
        return i0, j0, np.array(img, bool)[::k, ::k]

    def _peindre_poly(self, L, poly, net, cible=None):
        r = self._masque(poly)
        if r is None:
            return
        i0, j0, m = r
        sub = (cible or self.own)[L][i0:i0 + m.shape[0], j0:j0 + m.shape[1]]
        if net <= 0:
            sub[m] = -1
            return
        conflit = m & (sub != 0) & (sub != net)
        sub[m & (sub == 0)] = net
        sub[conflit] = -1

    def _isolement(self, item, L):
        try:
            c = mm(item.GetOwnClearance(L))
        except Exception:
            c = CL_MIN
        return max(c, CL_MIN)

    def _gonfle_zone(self, z, L):
        poly = pcbnew.SHAPE_POLY_SET(z.GetFilledPolysList(L))
        poly.Inflate(pcbnew.FromMM(self._isolement(z, L) + self.demi + MARGE), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS,
                     pcbnew.FromMM(0.005))
        return poly

    def ajouter(self, item):
        """Dessine une pastille, une piste ou une via (gonflée de son isolement + self.demi)."""
        net = item.GetNetCode()
        for L in CUIVRE:
            if not item.IsOnLayer(L):
                continue
            if item.GetClass() == 'PAD' and L in (pcbnew.In1_Cu, pcbnew.In2_Cu) and \
                    not item.FlashLayer(L):
                continue
            poly = pcbnew.SHAPE_POLY_SET()
            item.TransformShapeToPolygon(poly, L, pcbnew.FromMM(self._isolement(item, L) + self.demi + MARGE),
                                         pcbnew.FromMM(0.005), pcbnew.ERROR_OUTSIDE)
            souple = item.GetClass() in ('PCB_TRACK', 'PCB_ARC') and not item.IsLocked() and L in self.mou
            self._peindre_poly(L, poly, net, self.mou if souple else None)
        if item.GetClass() == 'PCB_VIA':
            self._trou(item.GetPosition(), mm(item.GetDrillValue()) / 2)
        if item.GetClass() == 'PAD' and item.HasHole():
            # trou : isolement cuivre - trou pour les autres nets, sur toutes les couches
            h = item.GetEffectiveHoleShape()
            self._trou(item.GetPosition(), mm(min(item.GetDrillSize().x, item.GetDrillSize().y)) / 2)
            poly = pcbnew.SHAPE_POLY_SET()
            h.TransformToPolygon(poly, pcbnew.FromMM(0.005), pcbnew.ERROR_OUTSIDE)
            poly.Inflate(pcbnew.FromMM(TROU + self.demi + MARGE), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS,
                         pcbnew.FromMM(0.005))
            for L in CUIVRE:
                self._peindre_poly(L, poly, net if item.GetAttribute() == pcbnew.PAD_ATTRIB_PTH else -1)

    def _trou(self, pos, r):
        """Interdit les centres de via trop près de ce trou (isolement trou - trou)."""
        R = (r + self.via_trou / 2 + TROU + MARGE) / PAS
        i, j = self.ij(mm(pos.x), mm(pos.y))
        n = int(math.ceil(R))
        for di, dj in disque(R):
            a, b = i + di, j + dj
            if 0 <= a < self.H and 0 <= b < self.W:
                self.trous[a, b] = True

    def _interdit(self, z):
        poly = pcbnew.SHAPE_POLY_SET(z.Outline())
        if z.GetDoNotAllowTracks():
            p = pcbnew.SHAPE_POLY_SET(poly)
            p.Inflate(pcbnew.FromMM(self.demi + MARGE), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS, pcbnew.FromMM(0.005))
            for L in ROUTAGE:
                if z.IsOnLayer(L):
                    self._peindre_poly(L, p, -1)
        if z.GetDoNotAllowVias():
            p = pcbnew.SHAPE_POLY_SET(poly)
            p.Inflate(pcbnew.FromMM(self.via_d / 2 + MARGE), pcbnew.CORNER_STRATEGY_ROUND_ALL_CORNERS,
                      pcbnew.FromMM(0.005))
            r = self._masque(p)
            if r is not None:
                i0, j0, m = r
                self.novia[i0:i0 + m.shape[0], j0:j0 + m.shape[1]] |= m

    def _bords(self):
        poly = pcbnew.SHAPE_POLY_SET()
        self.b.GetBoardPolygonOutlines(poly)
        r = self._masque(poly)
        dedans = np.zeros((self.H, self.W), bool)
        i0, j0, m = r
        dedans[i0:i0 + m.shape[0], j0:j0 + m.shape[1]] = m
        dedans = eroder(dedans, (BORD + self.demi + MARGE) / PAS)
        self.hors_via = ~eroder(dedans, (self.via_d / 2 - self.demi) / PAS)
        for L in CUIVRE:
            self.own[L][~dedans] = -1

    # ------------------------------------------------------------------ recherche
    def _fenetre(self, boites, marge):
        xs = [b[0] for b in boites] + [b[2] for b in boites]
        ys = [b[1] for b in boites] + [b[3] for b in boites]
        i0, j0 = self.ij(min(xs) - marge, min(ys) - marge)
        i1, j1 = self.ij(max(xs) + marge, max(ys) + marge)
        return max(0, i0), min(self.H, i1 + 1), max(0, j0), min(self.W, j1 + 1)

    def libres(self, net, fen, largeur, isolement, souple=False):
        """Cases libres pour l'axe d'une piste du net (par couche de routage) et pour une via."""
        i0, i1, j0, j1 = fen
        extra = max(0.0, isolement - CL_MIN)
        r_piste = (extra + largeur / 2 - self.demi) / PAS
        r_via = (extra + self.via_d / 2 - self.demi + MARGE_VIA) / PAS
        dur = {L: (self.own[L][i0:i1, j0:j1] == 0) | (self.own[L][i0:i1, j0:j1] == net) for L in CUIVRE}
        mou = {L: (self.mou[L][i0:i1, j0:j1] == 0) | (self.mou[L][i0:i1, j0:j1] == net) for L in self.routage}
        base = {L: dur[L] & mou[L] if L in mou else dur[L] for L in CUIVRE}
        libre = {L: eroder(base[L], r_piste) for L in self.routage}
        if pcbnew.In2_Cu in libre:
            libre[pcbnew.In2_Cu] &= self.ok_in2[i0:i1, j0:j1]
        via = ~self.novia[i0:i1, j0:j1] & ~self.hors_via[i0:i1, j0:j1] & ~self.trous[i0:i1, j0:j1]
        for L in CUIVRE:
            via &= eroder(base[L], r_via)
        if souple:
            # cases traversables en arrachant des pistes non verrouillées
            return libre, via, {L: eroder(dur[L], r_piste) for L in self.routage}
        return libre, via

    def cases_item(self, item, fen):
        """Cases (par couche de routage) du cuivre d'un élément, dans la fenêtre."""
        i0, i1, j0, j1 = fen
        out = {}
        for L in self.routage:
            if not item.IsOnLayer(L):
                continue
            poly = pcbnew.SHAPE_POLY_SET()
            item.TransformShapeToPolygon(poly, L, 0, pcbnew.FromMM(0.005), pcbnew.ERROR_INSIDE)
            r = self._masque(poly)
            if r is None:
                continue
            a, b, m = r
            full = np.zeros((i1 - i0, j1 - j0), bool)
            ya0, xa0 = max(a, i0), max(b, j0)
            ya1, xa1 = min(a + m.shape[0], i1), min(b + m.shape[1], j1)
            if ya1 > ya0 and xa1 > xa0:
                full[ya0 - i0:ya1 - i0, xa0 - j0:xa1 - j0] = m[ya0 - a:ya1 - a, xa0 - b:xa1 - b]
            # une case vers l'intérieur : l'extrémité de la piste doit être DANS la pastille
            # (sommets du polygone arrondis au pixel), sinon KiCad ne la considère pas reliée
            out[L] = eroder(full, 1.0) if eroder(full, 1.0).any() else full
        return out

    def plan(self, net, fen, marge=0.35):
        """Cases où une via touche le plan de son net (In1 ou In2), dans la fenêtre : dans le
        cuivre REMPLI du plan (pas seulement dans son contour : une zone prioritaire d'un autre
        net, ou les dégagements autour des vias voisines, y laissent des trous)."""
        if not hasattr(self, '_plans'):
            self._plans = {}
        if net not in self._plans:
            full = np.zeros((self.H, self.W), bool)
            for z in self.b.Zones():
                if z.GetIsRuleArea() or z.GetNetCode() != net:
                    continue
                for L in (pcbnew.In1_Cu, pcbnew.In2_Cu):
                    if not z.IsOnLayer(L):
                        continue
                    r = self._masque(z.GetFilledPolysList(L))
                    if r is None:
                        continue
                    a, b, mz = r
                    full[a:a + mz.shape[0], b:b + mz.shape[1]] |= mz
            self._plans[net] = full
        r = marge / PAS + (self.via_d / 2) / PAS
        n = int(math.ceil(r)) + 1
        i0, i1, j0, j1 = fen
        a0, a1, b0, b1 = max(0, i0 - n), min(self.H, i1 + n), max(0, j0 - n), min(self.W, j1 + n)
        m = eroder(self._plans[net][a0:a1, b0:b1], r)
        return m[i0 - a0:i0 - a0 + (i1 - i0), j0 - b0:j0 - b0 + (j1 - j0)]

    def astar(self, fen, libre, via, sources, cibles, max_noeuds=600_000, cout=(1.0, 1.0), passe=None,
              penalite=15.0, surcout=None, sens=None):
        """A* de sources vers cibles ({couche: masque}). Renvoie [(couche, i, j), ...] ou None.
        sens : {couche: 'h' ou 'v'}, direction préférée sur la couche (routage « horizontal sur
        une face, vertical sur l'autre », pour croiser un bus) ; l'autre direction coûte 3 fois
        plus, la diagonale 1,6 fois."""
        i0, i1, j0, j1 = fen
        h, w = i1 - i0, j1 - j0
        couches = list(self.routage)
        cout = tuple(cout) + (3.0,) * (len(couches) - len(cout))
        facs = []
        for L in couches:
            s = (sens or {}).get(L)
            facs.append((1.0, 3.0, 1.6) if s == 'h' else (3.0, 1.0, 1.6) if s == 'v' else (1.0, 1.0, 1.0))
        if passe is None:
            lib = [libre[L].tobytes() for L in couches]
            cher = [bytes(h * w) for L in couches]
        else:
            # cases « passe » : traversables, chacune coûte penalite de plus (piste à arracher),
            # plus l'historique des conflits à cet endroit (surcout)
            lib = [passe[L].tobytes() for L in couches]
            cher = []
            for L in couches:
                m = passe[L] & ~libre[L]
                c = np.where(m, penalite, 0.0)
                if surcout is not None:
                    c = c + np.where(m, surcout[L], 0.0)
                cher.append(np.minimum(c, 255).astype(np.uint8).tobytes())
        vb = via.tobytes()
        cib = [cibles[L].tobytes() if L in cibles else bytes(h * w) for L in couches]
        ci = np.argwhere(np.logical_or.reduce([cibles[L] for L in cibles]))
        if len(ci) == 0:
            return None
        ti0, tj0 = ci.min(0)
        ti1, tj1 = ci.max(0)

        def heur(i, j):
            di = ti0 - i if i < ti0 else (i - ti1 if i > ti1 else 0)
            dj = tj0 - j if j < tj0 else (j - tj1 if j > tj1 else 0)
            a, b = (di, dj) if di > dj else (dj, di)
            return a + 0.4142 * b

        g = {}
        par = {}
        tas = []
        for k, L in enumerate(couches):
            if L not in sources:
                continue
            for i, j in np.argwhere(sources[L] & libre[L]):
                n = (k * h + int(i)) * w + int(j)
                g[n] = 0.0
                par[n] = -1
                heapq.heappush(tas, (heur(i, j), 0.0, n))
        vus = 0
        hw = h * w
        while tas:
            f, gc, n = heapq.heappop(tas)
            if gc > g.get(n, 1e18):
                continue
            k, r = divmod(n, hw)
            i, j = divmod(r, w)
            if cib[k][r]:
                chemin = []
                while n != -1:
                    k2, r2 = divmod(n, hw)
                    i2, j2 = divmod(r2, w)
                    chemin.append((couches[k2], i2 + i0, j2 + j0))
                    n = par[n]
                return chemin[::-1]
            vus += 1
            if vus > max_noeuds:
                return None
            lk = lib[k]
            ck = cout[k]
            hk = cher[k]
            fh, fv, fd = facs[k]
            for di, dj, c in DIRS:
                a, b = i + di, j + dj
                if a < 0 or b < 0 or a >= h or b >= w:
                    continue
                r2 = a * w + b
                if not lk[r2]:
                    continue
                if di and dj and not (lk[i * w + b] and lk[a * w + j]):
                    continue
                m = k * hw + r2
                ng = gc + c * ck * (fd if di and dj else fv if di else fh) + hk[r2]
                if ng < g.get(m, 1e18):
                    g[m] = ng
                    par[m] = n
                    heapq.heappush(tas, (ng + heur(a, b), ng, m))
            if vb[r]:
                for k2 in range(len(couches)):
                    if k2 == k or not lib[k2][r]:
                        continue
                    m = k2 * hw + r
                    ng = gc + COUT_VIA
                    if ng < g.get(m, 1e18):
                        g[m] = ng
                        par[m] = n
                        heapq.heappush(tas, (ng + heur(i, j), ng, m))
        return None

    # ------------------------------------------------------------------ pistes
    def _vue(self, libre, fen, L, a, b):
        """Segment a -> b (cases absolues) entièrement libre sur la couche L ?"""
        i0, i1, j0, j1 = fen
        m = libre[L]
        n = int(max(abs(b[0] - a[0]), abs(b[1] - a[1])) * 2) + 1
        for t in range(n + 1):
            i = a[0] + (b[0] - a[0]) * t / n
            j = a[1] + (b[1] - a[1]) * t / n
            for ii in (int(math.floor(i)), int(math.ceil(i))):
                for jj in (int(math.floor(j)), int(math.ceil(j))):
                    if not m[ii - i0, jj - j0]:
                        return False
        return True

    def lisser(self, chemin, libre, fen):
        """Découpe le chemin en tronçons par couche et les tend (segments droits)."""
        troncons, cour = [], [chemin[0]]
        for p in chemin[1:]:
            if p[0] != cour[-1][0]:
                troncons.append(cour)
                cour = [p]
            else:
                cour.append(p)
        troncons.append(cour)
        out = []
        for tr in troncons:
            L = tr[0][0]
            pts = [(p[1], p[2]) for p in tr]
            res = [pts[0]]
            k = 0
            while k < len(pts) - 1:
                m = len(pts) - 1
                while m > k + 1 and not self._vue(libre, fen, L, pts[k], pts[m]):
                    m -= 1
                res.append(pts[m])
                k = m
            out.append((L, res))
        return out

    def poser(self, net_item, troncons, largeur, cree_via):
        """Crée pistes et vias ; les dessine dans la grille. Renvoie les éléments créés."""
        b = self.b
        faits = []
        for n, (L, pts) in enumerate(troncons):
            for (a, c) in zip(pts, pts[1:]):
                if a == c:
                    continue
                t = pcbnew.PCB_TRACK(b)
                t.SetStart(pcbnew.VECTOR2I(*[pcbnew.FromMM(v) for v in self.xy(*a)]))
                t.SetEnd(pcbnew.VECTOR2I(*[pcbnew.FromMM(v) for v in self.xy(*c)]))
                t.SetWidth(pcbnew.FromMM(largeur))
                t.SetLayer(L)
                t.SetNet(net_item)
                b.Add(t)
                faits.append(t)
            if n < len(troncons) - 1 or cree_via:
                faits.append(self._via(net_item, pts[-1]))
        for f in faits:
            self.ajouter(f)
        return faits

    def _via(self, net_item, p):
        v = pcbnew.PCB_VIA(self.b)
        v.SetPosition(pcbnew.VECTOR2I(*[pcbnew.FromMM(c) for c in self.xy(*p)]))
        v.SetViaType(pcbnew.VIATYPE_THROUGH)
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetWidth(pcbnew.FromMM(self.via_d))
        v.SetDrill(pcbnew.FromMM(self.via_trou))
        v.SetNet(net_item)
        self.b.Add(v)
        return v

    # ------------------------------------------------------------------ liaisons
    def bout(self, pad, longueur=0.6, largeur=0.2, isolement=0.15):
        """Amorce de piste sur F.Cu dans l'axe de la pastille, vers l'extérieur du boîtier.
        Posée avant de router un groupe de liaisons, elle réserve la sortie de chaque broche :
        une liaison routée plus tôt ne peut pas longer la rangée et boucher les suivantes."""
        fp = pad.GetParentFootprint()
        cx, cy = mm(fp.GetPosition().x), mm(fp.GetPosition().y)
        px, py = mm(pad.GetPosition().x), mm(pad.GetPosition().y)
        sx, sy = mm(pad.GetSize(pcbnew.F_Cu).x), mm(pad.GetSize(pcbnew.F_Cu).y)
        ang = pad.GetOrientation().AsDegrees() + (0 if sx >= sy else 90)
        ux, uy = math.cos(math.radians(ang)), -math.sin(math.radians(ang))
        if (px - cx) * ux + (py - cy) * uy < 0:
            ux, uy = -ux, -uy
        demi = max(sx, sy) / 2
        ia = self.ij(px, py)
        ib = self.ij(px + ux * (demi + longueur), py + uy * (demi + longueur))
        a, b = self.xy(*ia), self.xy(*ib)
        fen = self._fenetre([(min(a[0], b[0]), min(a[1], b[1]), max(a[0], b[0]), max(a[1], b[1]))], 1.0)
        libre, _ = self.libres(pad.GetNetCode(), fen, largeur, isolement)
        if not self._vue(libre, fen, pcbnew.F_Cu, ia, ib):
            return None
        t = pcbnew.PCB_TRACK(self.b)
        t.SetStart(pcbnew.VECTOR2I(pcbnew.FromMM(a[0]), pcbnew.FromMM(a[1])))
        t.SetEnd(pcbnew.VECTOR2I(pcbnew.FromMM(b[0]), pcbnew.FromMM(b[1])))
        t.SetWidth(pcbnew.FromMM(largeur))
        t.SetLayer(pcbnew.F_Cu)
        t.SetNet(pad.GetNet())
        self.b.Add(t)
        self.ajouter(t)
        return t

    def boite(self, item):
        bb = item.GetBoundingBox()
        return mm(bb.GetX()), mm(bb.GetY()), mm(bb.GetRight()), mm(bb.GetBottom())

    def relier(self, a, b, largeurs, isolement, cout=(1.0, 1.0), marges=(4.0, 12.0, 40.0), vias=True,
               sens=None):
        """Piste de l'élément a à l'élément b (même net). Renvoie les éléments créés ou None.
        vias=False : sans changer de couche (liaisons courtes des nets de plan : une via
        irait directement au plan)."""
        net = a.GetNetCode()
        for marge in marges:
            fen = self._fenetre([self.boite(a), self.boite(b)], marge)
            src, cib = self.cases_item(a, fen), self.cases_item(b, fen)
            if not src or not cib:
                return None
            for w in largeurs:
                libre, via = self.libres(net, fen, w, isolement)
                if not vias:
                    via = np.zeros_like(via)
                ch = self.astar(fen, libre, via, src, {L: cib[L] & libre[L] for L in cib}, cout=cout,
                                sens=sens)
                if ch:
                    return self.poser(a.GetNet(), self.lisser(ch, libre, fen), w, False)
        return None

    def relier_souple(self, a, b, largeur, isolement, retirer, marge=8.0, penalite=15.0, sens=None):
        """Routage négocié : comme relier, mais le chemin peut traverser des pistes non
        verrouillées d'autres nets (chaque case traversée coûte penalite) ; les pistes touchées
        sont arrachées (retirer(piste)) et seront re-routées au tour suivant.
        Renvoie (éléments créés, nombre de pistes arrachées) ou None."""
        net = a.GetNetCode()
        fen = self._fenetre([self.boite(a), self.boite(b)], marge)
        src, cib = self.cases_item(a, fen), self.cases_item(b, fen)
        if not src or not cib:
            return None
        libre, via, passe = self.libres(net, fen, largeur, isolement, souple=True)
        i0, i1, j0, j1 = fen
        hist = getattr(self, 'hist', None)
        sur = {L: hist[L][i0:i1, j0:j1] for L in ROUTAGE} if hist is not None else None
        ch = self.astar(fen, libre, via, src, {L: cib[L] & passe[L] for L in cib}, passe=passe,
                        penalite=penalite, max_noeuds=1_500_000, surcout=sur, sens=sens)
        if not ch:
            return None
        if hist is not None:
            # historique des conflits (PathFinder) : traverser encore ici coûtera plus cher
            for L, i, j in ch:
                if not libre[L][i - i0, j - j0]:
                    hist[L][max(i - 3, 0):i + 4, max(j - 3, 0):j + 4] += 6.0
            for L in ROUTAGE:
                np.minimum(hist[L], 200.0, out=hist[L])
        troncons = self.lisser(ch, passe, fen)
        # pistes souples touchées par les nouveaux segments (isolement compris)
        segs = []
        for L, pts in troncons:
            for p, q in zip(pts, pts[1:]):
                segs.append((L, pcbnew.SHAPE_SEGMENT(
                    pcbnew.VECTOR2I(*[pcbnew.FromMM(v) for v in self.xy(*p)]),
                    pcbnew.VECTOR2I(*[pcbnew.FromMM(v) for v in self.xy(*q)]),
                    pcbnew.FromMM(largeur))))
        vias = [pcbnew.SHAPE_CIRCLE(pcbnew.VECTOR2I(*[pcbnew.FromMM(v) for v in self.xy(*pts[-1])]),
                                    pcbnew.FromMM(self.via_d / 2)) for L, pts in troncons[:-1]]
        arr = []
        for t in list(self.b.GetTracks()):
            if t.IsLocked() or t.GetNetCode() == net or t.GetClass() not in ('PCB_TRACK', 'PCB_ARC'):
                continue
            L = t.GetLayer()
            if L not in ROUTAGE:
                continue
            jeu = pcbnew.FromMM(max(isolement, self._isolement(t, L)) + 0.02)
            forme = t.GetEffectiveShape(L)
            if any(L2 == L and forme.Collide(sg, jeu) for L2, sg in segs) or \
                    any(forme.Collide(v, jeu) for v in vias):
                arr.append(t)
        for t in arr:
            retirer(t)
        return self.poser(a.GetNet(), troncons, largeur, False), len(arr)

    def vers_plan(self, a, largeurs, isolement, rayon=6.0):
        """Piste sur F.Cu de l'élément a vers une via dans le plan de son net."""
        net = a.GetNetCode()
        fen = self._fenetre([self.boite(a)], rayon)
        src = self.cases_item(a, fen)
        if pcbnew.F_Cu not in src:
            return None
        # pas de via dans la pastille de départ ni contre elle
        pres = ~eroder(~src[pcbnew.F_Cu], (self.via_d / 2 + 0.1) / PAS)
        cible_plan = self.plan(net, fen) & ~pres
        for w in largeurs:
            libre, via = self.libres(net, fen, w, isolement)
            ok = cible_plan & via & libre[pcbnew.F_Cu]
            ch = self.astar(fen, {pcbnew.F_Cu: libre[pcbnew.F_Cu], pcbnew.B_Cu: np.zeros_like(ok)},
                            np.zeros_like(ok), {pcbnew.F_Cu: src[pcbnew.F_Cu]}, {pcbnew.F_Cu: ok})
            if ch:
                return self.poser(a.GetNet(), self.lisser(ch, libre, fen), w, True)
        return None
