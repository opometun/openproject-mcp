import importlib.util
from pathlib import Path


def test_core_import_guard_passes():
    script = (
        Path(__file__).resolve().parent.parent / "scripts" / "check_core_imports.py"
    )
    spec = importlib.util.spec_from_file_location("check_core_imports", script)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None  # for mypy
    spec.loader.exec_module(module)
    exit_code = module.main()
    assert exit_code == 0, "core import guard failed"
