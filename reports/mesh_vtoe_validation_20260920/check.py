"""Validate original mesh_vtoe drivers against independent adjacency lists."""
from pathlib import Path
import re
import sys

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
sys.path.insert(0, str(ROOT / 'reports/burkardt_recheck_20260915'))
from recheck import command, COMPILER

source = Path('C:/python/public_domain/burkardt/mesh_vtoe/mesh_vtoe.py')
valid = OUT / 'valid'
missing = OUT / 'missing'
missing.mkdir(exist_ok=True)
generated = OUT / 'mesh_vtoe_p.f90'
rc, _ = command([sys.executable, str(ROOT / 'xp2f.py'), str(source),
                 str(ROOT / 'python.f90'), str(ROOT / 'lapack_d.f90'),
                 '--out', str(generated), '--compile', '--compiler', COMPILER],
                OUT, OUT / 'build.log', 240)
assert rc == 0, (OUT / 'build.log').read_text()
for label, cmd in [('python', [sys.executable, str(source)]), ('fortran', [str(generated.with_suffix('.exe'))])]:
    rc, _ = command(cmd, valid, OUT / f'{label}.log', 60)
    assert rc == 0, label
    output = (OUT / f'{label}.log').read_text()
    blocks = output.split('VTOE_POINTER')[1:]
    assert len(blocks) == 2
    for name, block in zip(('boxy', 'pool'), blocks):
        elements = [[int(v) for v in line.split()] for line in (valid / f'{name}_elements.txt').read_text().splitlines()]
        vertex_count = max(max(e) for e in elements) + 1
        adjacency = [[e for e, vertices in enumerate(elements) if v in vertices] for v in range(vertex_count)]
        pointers = [0]
        for neighbors in adjacency:
            pointers.append(pointers[-1] + len(neighbors))
        pointer_text, adjacency_text = block.split('VTOE', 1)
        def rows(text):
            return [(int(v), [int(k) for k in values.split()]) for v, values in
                    re.findall(r'^\s*(\d+):[ \t]*([^\r\n]*)', text, re.M)]
        assert rows(pointer_text) == [(i, [p]) for i, p in enumerate(pointers)], (label, name, 'pointers')
        assert rows(adjacency_text) == list(enumerate(adjacency)), (label, name, 'adjacency')
        print(label, name, 'PASS:', vertex_count, 'vertices,', pointers[-1], 'incidences; all pointers and lists match', flush=True)
    rc, _ = command(cmd, missing, OUT / f'{label}_missing.log', 60)
    assert rc != 0
    assert 'boxy_elements.txt' in (OUT / f'{label}_missing.log').read_text()
    print(label, 'missing input: correct failure', flush=True)

historical = ROOT / 'reports/burkardt_audit_20260920/cases/mesh_vtoe/mesh_vtoe_p.exe'
if historical.exists():
    for case in ('valid', 'missing'):
        rc, _ = command([str(historical)], OUT / case, OUT / f'historical_{case}.log', 30)
        print('historical', case, 'exit', rc, flush=True)
