"""Run original FEM converter and validate all XML attributes against fixtures."""
from pathlib import Path
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[2]
OUT = Path(__file__).resolve().parent
SOURCE = Path('C:/python/public_domain/burkardt/fem_to_xml/fem_to_xml.py')
FLAGS = 'gfortran -O0 -g -fcheck=all -fbacktrace -ffpe-trap=invalid,zero,overflow -Wfatal-errors'
def run(cmd, cwd, name, timeout=120):
    with (OUT / (name + '.log')).open('w', encoding='utf-8') as log:
        log.write(subprocess.list2cmdline(cmd) + '\n')
        log.flush()
        proc = subprocess.run(cmd, cwd=cwd, stdout=log, stderr=subprocess.STDOUT,
                              stdin=subprocess.DEVNULL, timeout=timeout)
    return proc.returncode, (OUT / (name + '.log')).read_text()

generated = OUT / 'fem_to_xml_p.f90'
rc, text = run([sys.executable, str(ROOT / 'xp2f.py'), str(SOURCE),
               str(ROOT / 'python.f90'), str(ROOT / 'lapack_d.f90'), '--out', str(generated),
               '--compile', '--compiler', FLAGS], OUT, 'build', 240)
assert rc == 0, text
for label, cmd in [('python', [sys.executable, str(SOURCE)]), ('fortran', [str(generated.with_suffix('.exe'))])]:
    work = OUT / label
    work.mkdir(exist_ok=True)
    for fixture in (OUT / 'fixtures').glob('*.txt'):
        shutil.copy2(fixture, work / fixture.name)
    rc, text = run(cmd, work, label)
    assert rc == 0, text
    wrappers = []
    def number(value):
        match = re.fullmatch(r'np\.(?:float64|int64|int32)\((.*)\)', value)
        if match:
            wrappers.append(value)
            value = match[1]
        return float(value)
    for prefix, dim, celltype, base in [('cheby9',1,'interval',1), ('rectangle',2,'triangle',0), ('tet_mesh',3,'tetrahedron',1)]:
        nodes = [[float(x) for x in line.split()] for line in (work / (prefix+'_nodes.txt')).read_text().splitlines()]
        cells = [[int(x)-base for x in line.split()] for line in (work / (prefix+'_elements.txt')).read_text().splitlines()]
        root = ET.parse(work / (prefix+'.xml')).getroot()
        assert root.tag == 'dolfin'
        mesh = root.find('mesh')
        assert mesh.attrib == {'dim':str(dim),'celltype':celltype}
        vertices, elements = mesh.find('vertices'), mesh.find('cells')
        assert int(vertices.get('size')) == len(vertices) == len(nodes)
        assert int(elements.get('size')) == len(elements) == len(cells)
        for i, (v, coords) in enumerate(zip(vertices, nodes)):
            assert v.tag == 'vertex' and int(v.get('index')) == i
            assert set(v.attrib) == {'index', *'xyz'[:dim]}
            assert [number(v.get(axis)) for axis in 'xyz'[:dim]] == coords
        for i, (e, indices) in enumerate(zip(elements, cells)):
            assert e.tag == celltype and int(e.get('index')) == i
            assert set(e.attrib) == {'index', *(f'v{j}' for j in range(dim+1))}
            assert [number(e.get(f'v{j}')) for j in range(dim+1)] == indices
        print(label, prefix, 'geometry/connectivity PASS', flush=True)
    print(label, 'NumPy repr wrappers in numeric XML attributes:', len(wrappers), flush=True)
    missing = OUT / (label+'_missing')
    missing.mkdir(exist_ok=True)
    rc, text = run(cmd, missing, label+'_missing')
    assert rc != 0 and 'cheby9_nodes.txt' in text
    print(label, 'missing-file failure PASS', flush=True)
