from __future__ import annotations

import sys
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

import xp2f_batch


def test_expand_inputs_supports_at_list_files(tmp_path: Path, monkeypatch) -> None:
    src_dir = tmp_path / "src"
    src_dir.mkdir()
    a_py = src_dir / "a.py"
    b_py = src_dir / "b.py"
    skip_txt = src_dir / "skip.txt"
    a_py.write_text("print('a')\n", encoding="utf-8")
    b_py.write_text("print('b')\n", encoding="utf-8")
    skip_txt.write_text("not python\n", encoding="utf-8")

    nested_list = tmp_path / "nested_list.txt"
    nested_list.write_text("src/b.py\n", encoding="utf-8")

    file_list = tmp_path / "file_list.txt"
    file_list.write_text(
        "\n".join(
            [
                "# comment",
                "src/a.py",
                "src/skip.txt",
                "@nested_list.txt",
                "",
            ]
        ),
        encoding="utf-8",
    )

    monkeypatch.chdir(tmp_path)
    expanded = xp2f_batch._expand_inputs(["@file_list.txt"])

    assert expanded == [a_py, b_py]
