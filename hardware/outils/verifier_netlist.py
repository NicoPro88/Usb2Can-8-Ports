#!/usr/bin/env python3
"""Régénère les schémas puis vérifie, avec kicad-cli, que la netlist produite par
KiCad correspond exactement à la netlist décrite dans generer_schemas.py.

    python3 hardware/outils/verifier_netlist.py

Contrôles :
  - chaque net attendu existe dans KiCad avec exactement les mêmes broches ;
  - aucune broche déclarée « non connectée » n'est reliée à quelque chose ;
  - aucune référence n'est en double ou non annotée (« ? »).
Sort avec le code 1 en cas d'écart.
"""
import collections
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

import generer_schemas as gen  # noqa: E402
import schema  # noqa: E402
import sexp  # noqa: E402


def kicad_netlist(sch):
    with tempfile.TemporaryDirectory() as d:
        out = os.path.join(d, 'n.net')
        subprocess.run(['kicad-cli', 'sch', 'export', 'netlist', '-o', out, sch], check=True,
                       capture_output=True)
        t = sexp.parse(open(out).read())[0]
    comps = [sexp.find(c, 'ref')[0][1] for c in sexp.find(sexp.find(t, 'components')[0], 'comp')]
    nets = {}
    for n in sexp.find(sexp.find(t, 'nets')[0], 'net'):
        name = sexp.find(n, 'name')[0][1]
        nets[name] = frozenset((sexp.find(x, 'ref')[0][1], sexp.find(x, 'pin')[0][1])
                               for x in sexp.find(n, 'node'))
    return comps, nets


def attendu(sheets):
    groups = collections.defaultdict(set)
    nc = set()
    for sh in sheets:
        for i, (_, pre, _) in enumerate(sh.instances):
            port = int(pre) if sh.key == 'port_can' else None
            for part in sh.parts:
                ref = part.refs[i]
                for p in part.pins:
                    net = part.net_of(p['num'])
                    if net is None:
                        nc.add((ref, p['num']))
                        continue
                    kind = schema.label_kind(sh, net)
                    if kind == 'hier':
                        b = gen.PORT_BUS[port]
                        net = {'SCK': 'SPI%d_SCK' % b, 'MOSI': 'SPI%d_MOSI' % b, 'MISO': 'SPI%d_MISO' % b,
                               '~{CS}': '~{CS%d}' % port, '~{INT}': '~{INT%d}' % port}[net]
                        key = net
                    elif kind in ('power', 'global'):
                        key = net
                    else:
                        key = (sh.key, pre, net)
                    groups[key].add((ref, p['num']))
    return groups, nc


def verifier(nom, sheets):
    comps, nets = kicad_netlist(os.path.join(gen.HW, nom, nom + '.kicad_sch'))
    erreurs = []
    dup = [r for r, c in collections.Counter(comps).items() if c > 1]
    if dup:
        erreurs.append('références en double : %s' % dup)
    if any('?' in r for r in comps):
        erreurs.append('références non annotées')
    groups, nc = attendu(sheets)
    by_nodes = {v: k for k, v in nets.items()}
    for key, nodes in groups.items():
        if frozenset(nodes) not in by_nodes:
            proches = [k for k, v in nets.items() if v & nodes]
            erreurs.append('net %s : attendu %s, KiCad : %s' % (key, sorted(nodes),
                                                               [(k, sorted(nets[k])) for k in proches]))
    for node in nc:
        for k, v in nets.items():
            if node in v and len(v) > 1:
                erreurs.append('broche %s-%s devait rester non connectée (net %s)' % (node + (k,)))
    print('%s : %d composants, %d nets KiCad, %d nets attendus, %d broches non connectées, %d écart(s)'
          % (nom, len(comps), len(nets), len(groups), len(nc), len(erreurs)))
    for e in erreurs[:30]:
        print('  ERREUR', e)
    return not erreurs


def main():
    mere, fille = gen.main()
    ok = verifier('can8-mere', mere) & verifier('can8-fille', fille)
    sys.exit(0 if ok else 1)


if __name__ == '__main__':
    main()
