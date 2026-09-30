"""Guarded main return values are evaluated, then discarded, as in Python."""

from pathlib import Path
import subprocess
import sys

import pytest

ROOT = Path(__file__).resolve().parents[1]


@pytest.mark.parametrize("source", [
    "def main() -> int:\n    print('hello world')\n    return 0\nif __name__ == '__main__':\n    main()\n",
    "def main():\n    print('hello')\n    return 7\nif __name__ == '__main__':\n    main()\n",
    "def side_effect():\n    print('return evaluated')\n    return 13\ndef main() -> int:\n    print('before')\n    return side_effect()\nif __name__ == '__main__':\n    main()\n    print('after')\n",
    "def side_effect():\n    print('once')\n    return 3\ndef main() -> int:\n    for i in range(3):\n        if i == 1:\n            return side_effect()\n        print(i)\n    print('wrong')\n    return 0\nif __name__ == '__main__':\n    main()\n",
    "seed = 4\ndef main() -> int:\n    print(seed)\n    return seed + 1\nif __name__ == '__main__':\n    main()\nprint('after guard')\n",
    "xp2f_discarded_main_result = 99\ndef main() -> int:\n    return 7\nif __name__ == '__main__':\n    main()\nprint(xp2f_discarded_main_result)\n",
    "def main() -> int:\n    print('called')\n    return 5\nif __name__ == '__main__':\n    main()\n    print(main())\n",
    "def main() -> float:\n    print('float')\n    return 1.25\nif __name__ == '__main__':\n    main()\n",
    "def fib(n: int) -> int:\n    a = 0\n    b = 1\n    for i in range(n):\n        a, b = b, a + b\n    return a\ndef main() -> int:\n    print(fib(30))\n    return 0\nif __name__ == '__main__':\n    main()\n",
])
def test_main_discarded_result_compile_diff(tmp_path, source):
    script = tmp_path / "xmain_return.py"
    script.write_text(source, encoding="utf-8")
    result = subprocess.run([sys.executable, str(ROOT / "xp2f.py"), str(script), "--compile", "--run-diff"],
                            cwd=tmp_path, capture_output=True, text=True)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "Run diff: MATCH" in result.stdout, result.stdout + result.stderr
