"""MatForge.bundle packaging: builds the bundle into a tmp dir and checks it is shippable
(valid PackageContents.xml, no secrets/tests, no user-specific paths, Python 3.7 syntax)."""
import ast
import importlib.util
import pathlib
import xml.etree.ElementTree as ET

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]

# MAXScript / Python files that resolve the MatForge root at runtime
PATH_FILES = ["install_matforge.ms", "matforge_macros.ms", "matforge_panel.ms",
              "matforge_diagnose.ms", "run_matforge.py", "mfconfig.py",
              "maxplugin/forge_max.py",
              "packaging/MatForge.bundle/Contents/scripts/matforge_startup.ms"]
USER_PATHS = ("aasis", "C:\\Users", "C:/Users")


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "build_matforge_bundle", str(ROOT / "tools" / "build_matforge_bundle.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture(scope="module")
def bundle(tmp_path_factory):
    return _load_builder().build(tmp_path_factory.mktemp("dist"))


def _files(bundle):
    return [p for p in bundle.rglob("*") if p.is_file()]


def test_package_contents_xml(bundle):
    root = ET.parse(str(bundle / "PackageContents.xml")).getroot()
    assert root.tag == "ApplicationPackage"
    assert root.get("AutodeskProduct") == "3ds Max"
    assert root.get("ProductType") == "Application"
    for attr in ("SchemaVersion", "Name", "AppVersion", "ProductCode", "UpgradeCode"):
        assert root.get(attr), attr
    comps = root.find("Components")
    assert comps.get("Description") == "post-start-up scripts parts"
    req = comps.find("RuntimeRequirements")
    assert req.get("OS") == "Win64" and req.get("Platform") == "3ds Max"
    assert int(req.get("SeriesMin")) <= 2022 and int(req.get("SeriesMax")) >= 2027
    entry = comps.find("ComponentEntry")
    module = entry.get("ModuleName")
    assert module.startswith("./Contents/scripts/")
    assert (bundle / module[2:]).is_file()


def test_runtime_present(bundle):
    s = bundle / "Contents" / "scripts"
    for rel in ("matphys/__init__.py", "maxplugin/builder_corona.py",
                "maxplugin/forge_max.py", "core/maps.py", "ui/panel.html",
                "run_matforge.py", "forge_cli.py", "forge_fal.py", "mfconfig.py",
                "matforge_macros.ms", "matforge_panel.ms", "matforge_diagnose.ms",
                "matforge_startup.ms"):
        assert (s / rel).is_file(), rel


def test_no_secrets_or_dev_folders(bundle):
    for p in _files(bundle):
        rel = p.relative_to(bundle)
        assert p.name not in ("_keys.json", "_falkey.py", "_omegakey.py"), rel
        assert not {"tests", "research_notes", "reports", ".router", "dist",
                    "__pycache__"}.intersection(rel.parts), rel
        assert p.suffix != ".pyc", rel
        assert not p.name.startswith("test_"), rel


def test_no_user_paths_in_bundle(bundle):
    for p in _files(bundle):
        text = p.read_bytes().decode("utf-8", "replace")
        for needle in USER_PATHS:
            assert needle not in text, "%s contains %r" % (p.relative_to(bundle), needle)


def test_no_user_paths_in_sources():
    for rel in PATH_FILES:
        text = (ROOT / rel).read_text(encoding="utf-8")
        for needle in USER_PATHS:
            assert needle not in text, "%s contains %r" % (rel, needle)


def test_shipped_python_parses_as_py37(bundle):
    pys = [p for p in _files(bundle) if p.suffix == ".py"]
    assert pys
    for p in pys:
        ast.parse(p.read_text(encoding="utf-8"), filename=str(p), feature_version=(3, 7))


def test_macros_bake_resolved_root():
    """Macros carry a literal root built at registration time, never a session global path."""
    src = (ROOT / "matforge_macros.ms").read_text(encoding="utf-8")
    assert "global MatForgeRoot = @\\\"\" + root" in src
    assert "local p = @\\\"\" + root" in src
    for name in ("MatForge_Open", "MatForge_Panel", "MatForge_Diagnose"):
        assert name in src
    for ms in ("install_matforge.ms", "matforge_panel.ms", "matforge_diagnose.ms"):
        assert "getThisScriptFilename()" in (ROOT / ms).read_text(encoding="utf-8"), ms


def test_keys_json_ignored():
    lines = (ROOT / ".gitignore").read_text(encoding="utf-8").splitlines()
    for name in ("_keys.json", "_falkey.py", "_omegakey.py", "dist/"):
        assert name in lines, name


def test_keys_fall_back_to_appdata(tmp_path, monkeypatch):
    import mfconfig
    monkeypatch.setattr(mfconfig, "_KEYS_PATH", str(tmp_path / "bundle" / "_keys.json"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "appdata"))
    user = tmp_path / "appdata" / "MatForge" / "_keys.json"
    assert mfconfig._keys_path(for_write=True) == str(user)
    mfconfig.save_keys(fal_key="k-test", omega_model="m")
    assert user.is_file() and not (tmp_path / "bundle" / "_keys.json").exists()
    assert mfconfig._load()["fal_key"] == "k-test"
    # a folder-local _keys.json (run-from-repo) still wins when present
    local = tmp_path / "bundle" / "_keys.json"
    local.parent.mkdir()
    local.write_text('{"fal_key": "local"}', encoding="utf-8")
    assert mfconfig._keys_path() == str(local)
    assert mfconfig._load()["fal_key"] == "local"


def _root_finder():
    """run_matforge's resolver functions, without running its launcher."""
    tree = ast.parse((ROOT / "run_matforge.py").read_text(encoding="utf-8"))
    tree.body = [n for n in tree.body
                 if isinstance(n, (ast.Import, ast.ImportFrom, ast.FunctionDef))
                 and getattr(n, "name", "") != "_main"]
    ns = {}
    exec(compile(tree, "run_matforge.py", "exec"), ns)   # no __file__ in ns
    return ns


def test_run_matforge_root_without_file(monkeypatch):
    ns = _root_finder()
    monkeypatch.delenv("MATFORGE_ROOT", raising=False)
    monkeypatch.setitem(__import__("sys").modules, "pymxs", None)   # no Max
    with pytest.raises(RuntimeError):
        ns["_find_root"]()
    monkeypatch.setenv("MATFORGE_ROOT", str(ROOT))
    assert ns["_find_root"]() == str(ROOT)
    monkeypatch.delenv("MATFORGE_ROOT")
    ns["MATFORGE_ROOT"] = str(ROOT)          # global set by the .ms caller
    assert ns["_find_root"]() == str(ROOT)
