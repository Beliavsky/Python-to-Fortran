"""Standalone checks; does not change or invoke the ongoing pytest suite."""
import ast
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from xp2f import reject_numpy_slice_view_swaps


def main():
    cases = [
        ('constant rows', 't = a[0,:]\na[0,:] = a[1,:]\na[1,:] = t', True),
        ('constant columns', 't = a[:,0]\na[:,0] = a[:,1]\na[:,1] = t', True),
        ('copy', 't = a[0,:].copy()\na[0,:] = a[1,:]\na[1,:] = t', False),
        ('same row', 't = a[0,:]\na[0,:] = a[0,:]\na[0,:] = t', False),
        ('list slice', 't = a[0:1]\na[0:1] = a[1:2]\na[1:2] = t', False),
        ('scalar entries', 't = a[0,0]\na[0,0] = a[1,0]\na[1,0] = t', False),
        ('advanced indices', 'def f(a):\n    j = np.array([0])\n    p = np.array([1])\n    t = a[j,:]\n    a[j,:] = a[p,:]\n    a[p,:] = t', False),
        ('loop indices', 'def f(a):\n    for j in range(2):\n        p = np.argmax(a[:,j])\n        p = p + j - 1\n        t = a[j,:]\n        a[j,:] = a[p,:]\n        a[p,:] = t', True),
        ('rebound vector', 'def f(a):\n    for j in range(2):\n        p = np.argmax(a[:,j])\n        p = np.array([0])\n        t = a[j,:]\n        a[j,:] = a[p,:]\n        a[p,:] = t', False),
    ]
    for name, source, expected in cases:
        rejected = False
        try:
            reject_numpy_slice_view_swaps(ast.parse(source).body, [])
        except NotImplementedError as exc:
            assert 'NumPy slice-view swap' in str(exc)
            rejected = True
        assert rejected == expected, name
    print(f'PASS: {len(cases)} diagnostic boundary cases')


if __name__ == '__main__':
    main()
