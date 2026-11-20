"""Lecture / écriture minimale du format S-expression de KiCad."""
import re

_TOK = re.compile(r'\s*(\(|\)|"(?:[^"\\]|\\.)*"|[^\s()"]+)')


class Sym(str):
    """Atome non quoté (mot-clé KiCad)."""


def parse(text):
    stack = [[]]
    for m in _TOK.finditer(text):
        tok = m.group(1)
        if tok == '(':
            stack.append([])
        elif tok == ')':
            x = stack.pop()
            stack[-1].append(x)
        elif tok.startswith('"'):
            stack[-1].append(tok[1:-1].replace('\\n', '\n').replace('\\"', '"').replace('\\\\', '\\'))
        else:
            stack[-1].append(Sym(tok))
    return stack[0]


def q(s):
    return '"' + str(s).replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n') + '"'


def fmt_num(x):
    if isinstance(x, bool):
        return 'yes' if x else 'no'
    if isinstance(x, int):
        return str(x)
    s = ('%.4f' % x).rstrip('0').rstrip('.')
    return '0' if s in ('-0', '') else s


def dump(x, ind=0):
    if isinstance(x, list):
        if all(not isinstance(e, list) for e in x):
            return '(' + ' '.join(dump(e) for e in x) + ')'
        out = '('
        first = True
        for e in x:
            if isinstance(e, list):
                out += '\n' + '  ' * (ind + 1) + dump(e, ind + 1)
            else:
                out += ('' if first else ' ') + dump(e)
            first = False
        return out + ')'
    if isinstance(x, Sym):
        return str(x)
    if isinstance(x, (int, float)):
        return fmt_num(x)
    return q(x)


def find(x, key):
    return [e for e in x if isinstance(e, list) and e and e[0] == key]


def pins(sym):
    """Liste des broches d'un symbole de bibliothèque (déjà aplati)."""
    res = []

    def walk(x):
        for e in x:
            if isinstance(e, list) and e:
                if e[0] == 'pin':
                    at = find(e, 'at')[0]
                    res.append(dict(
                        type=str(e[1]), x=float(at[1]), y=float(at[2]),
                        rot=float(at[3]) if len(at) > 3 else 0.0,
                        name=find(e, 'name')[0][1], num=find(e, 'number')[0][1],
                        length=float(find(e, 'length')[0][1])))
                elif e[0] == 'symbol':
                    walk(e)
    walk(sym)
    return res
