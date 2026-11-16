"""The Material Inspector bundle ships the shared forgeui kit and matphys, and no tests."""
import importlib.util
import pathlib

ROOT = pathlib.Path(__file__).resolve().parents[1]


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "inspector_build_bundle", str(ROOT / "tools" / "build_bundle.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_bundle_has_forgeui_and_matphys(tmp_path):
    dist = _load_builder().build(tmp_path)
    scripts = dist / "Contents" / "scripts"
    assert (scripts / "forgeui" / "__init__.py").is_file()
    assert (scripts / "matphys" / "__init__.py").is_file()
    assert not [p for p in dist.rglob("tests") if p.is_dir()]
