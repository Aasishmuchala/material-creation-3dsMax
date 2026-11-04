"""STRESS SUITE C -- compatibility, packaging, MAXScript lint, Windows path semantics.

Permanent tests; the defects it found (STRESS-C1..C3) are fixed and their tests are regressions.
Tests needing uv / CPython 3.8 / uvx skip (never fail) when those are unavailable.
Write-ups: .router/stress/C_compat.md
"""
import ast
import hashlib
import os
import pathlib
import re
import shutil
import subprocess
import sys
import xml.etree.ElementTree as ET

import pytest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))

UV = shutil.which("uv") or ("/opt/homebrew/bin/uv" if os.path.exists("/opt/homebrew/bin/uv") else None)
UVX = shutil.which("uvx") or ("/opt/homebrew/bin/uvx" if os.path.exists("/opt/homebrew/bin/uvx") else None)


# ---------------------------------------------------------------------------
# MAXScript lexer + linter
# ---------------------------------------------------------------------------
class Tok(object):
    __slots__ = ("kind", "text", "line", "start", "end", "value")

    def __init__(self, kind, text, line, start, end, value=None):
        self.kind, self.text, self.line = kind, text, line
        self.start, self.end, self.value = start, end, value

    def __repr__(self):
        return "Tok(%s,%r,L%d)" % (self.kind, self.text[:20], self.line)


_ESC = {"n": "\n", "r": "\r", "t": "\t", '"': '"', "\\": "\\", "*": "*",
        "?": "?", "%": "%"}


def mxs_unescape(body):
    """MAXScript regular-string unescape: \\n \\r \\t \\" \\\\ \\* \\? \\%."""
    out, i = [], 0
    while i < len(body):
        c = body[i]
        if c == "\\" and i + 1 < len(body):
            n = body[i + 1]
            out.append(_ESC.get(n, "\\" + n))
            i += 2
        else:
            out.append(c)
            i += 1
    return "".join(out)


_OPS = "+-*/=<>!&|~^.:?@$#;,"


def lex(src):
    """Return (tokens, problems). problems: list of (line, message).
    kinds: str, vstr, ident, num, punct, op. Comments are dropped."""
    toks, problems = [], []
    i, n, line = 0, len(src), 1
    while i < n:
        c = src[i]
        if c == "\n":
            line += 1
            i += 1
        elif c in " \t\r\f":
            i += 1
        elif src.startswith("--", i):
            j = src.find("\n", i)
            i = n if j < 0 else j
        elif src.startswith("/*", i):
            j = src.find("*/", i + 2)
            if j < 0:
                problems.append((line, "unterminated /* comment"))
                break
            line += src.count("\n", i, j)
            i = j + 2
        elif src.startswith('@"', i):
            j = src.find('"', i + 2)
            if j < 0:
                problems.append((line, 'unterminated @"..." verbatim string'))
                break
            body = src[i + 2:j]
            if "\n" in body:
                problems.append((line, 'verbatim @"..." literal spans a newline'))
            toks.append(Tok("vstr", src[i:j + 1], line, i, j + 1, body))
            line += body.count("\n")
            i = j + 1
        elif c == '"':
            j, buf = i + 1, []
            while j < n and src[j] != '"':
                if src[j] == "\\" and j + 1 < n:
                    buf.append(src[j:j + 2])
                    j += 2
                else:
                    buf.append(src[j])
                    j += 1
            if j >= n:
                problems.append((line, "unterminated string"))
                break
            raw = "".join(buf)
            toks.append(Tok("str", src[i:j + 1], line, i, j + 1, mxs_unescape(raw)))
            line += raw.count("\n")
            i = j + 1
        elif c in "()[]{}":
            toks.append(Tok("punct", c, line, i, i + 1))
            i += 1
        elif c.isalpha() or c == "_":
            j = i + 1
            while j < n and (src[j].isalnum() or src[j] in "_."):
                j += 1
            toks.append(Tok("ident", src[i:j], line, i, j))
            i = j
        elif c.isdigit():
            j = i + 1
            while j < n and (src[j].isalnum() or src[j] == "."):
                j += 1
            toks.append(Tok("num", src[i:j], line, i, j))
            i = j
        elif c == "'":
            # 'quoted name' literal (e.g. #'foo bar', $'node name'): opaque
            j = src.find("'", i + 1)
            j = n - 1 if j < 0 else j
            toks.append(Tok("ident", src[i:j + 1], line, i, j + 1))
            i = j + 1
        elif c == "\\":
            i += 1   # line continuation
        else:
            j = i + 1
            while j < n and src[j] in _OPS and src[i] in _OPS:
                j += 1
            toks.append(Tok("op", src[i:j], line, i, j))
            i = j
    return toks, problems


def _match(toks, k):
    """Index of the closing token matching the opener at toks[k]."""
    pair = {"(": ")", "[": "]", "{": "}"}[toks[k].text]
    d = 0
    for m in range(k, len(toks)):
        t = toks[m]
        if t.kind == "punct" and t.text == toks[k].text:
            d += 1
        elif t.kind == "punct" and t.text == pair:
            d -= 1
            if d == 0:
                return m
    return None


def check_balance(toks):
    out, stack = [], []
    pairs = {")": "(", "]": "[", "}": "{"}
    for t in toks:
        if t.kind != "punct":
            continue
        if t.text in "([{":
            stack.append(t)
        else:
            if not stack or stack[-1].text != pairs[t.text]:
                out.append((t.line, "unbalanced %r" % t.text))
                if stack and stack[-1].text != pairs[t.text]:
                    stack.pop()
            else:
                stack.pop()
    for t in stack:
        out.append((t.line, "unclosed %r" % t.text))
    return out


_SRCNAME = re.compile(r"getThisScriptFilename|getSourceFileName", re.I)


def check_macro_bodies(toks):
    """getThisScriptFilename/getSourceFileName are undefined when a macroScript
    handler runs at button-click time (only valid while the file is loading)."""
    out = []
    for k, t in enumerate(toks):
        if t.kind == "ident" and t.text.lower() == "macroscript":
            o = next((m for m in range(k + 1, len(toks))
                      if toks[m].kind == "punct" and toks[m].text == "("), None)
            c = _match(toks, o) if o is not None else None
            if c is None:
                continue
            for m in range(o, c):
                u = toks[m]
                if u.kind == "ident" and _SRCNAME.fullmatch(u.text):
                    out.append((u.line, "%s inside macroScript %s body (undefined at click time)"
                                % (u.text, toks[k + 1].text if k + 1 < len(toks) else "?")))
    # macro source generated as a string (matforge_macros.ms)
    for t in toks:
        if t.kind in ("str", "vstr") and re.search(r"macroScript\b", t.value or "") \
                and _SRCNAME.search(t.value or ""):
            out.append((t.line, "generated macroScript source calls getThisScriptFilename/getSourceFileName"))
    return out


def _is_op(t, texts):
    return t.kind == "op" and t.text in texts


def python_payloads(toks, src_text=""):
    """Yield (line, python_source, dynamic_parts) for each `python.Execute <expr>`.
    Literal strings are unescaped; non-literal operands become `__MXS__`."""
    for k, t in enumerate(toks):
        if not (t.kind == "ident" and t.text.lower() == "python.execute"):
            continue
        j = k + 1
        if j >= len(toks):
            continue
        paren = toks[j].kind == "punct" and toks[j].text == "("
        end = _match(toks, j) if paren else None
        if paren:
            j += 1
        parts, dyn, expect_operand = [], [], True
        m = j
        while m < len(toks) and (end is None or m < end):
            u = toks[m]
            if expect_operand:
                if u.kind in ("str", "vstr"):
                    parts.append(u.value)
                else:
                    # swallow one operand (ident / call / parenthesised)
                    parts.append("__MXS__")
                    dyn.append((u.line, u.text))
                    if u.kind == "punct" and u.text in "([":
                        m = _match(toks, m) or m
                    elif u.kind == "ident":
                        # function-call style `f (args)` / `f arg`
                        while m + 1 < len(toks) and toks[m + 1].kind in ("punct",) \
                                and toks[m + 1].text == "(" \
                                and toks[m + 1].start == toks[m].end + 1 \
                                and (end is None or m + 1 < end):
                            m = _match(toks, m + 1) or m
                expect_operand = False
            elif _is_op(u, ("+", "&")):
                expect_operand = True
            else:
                break
            m += 1
        yield t.line, "".join(parts), dyn


def raw_splices(toks):
    """(line, variable) for python.Execute payloads that splice a MAXScript value into r'...'."""
    out = []
    for line, code, dyn in python_payloads(toks):
        if dyn and re.search(r"""\br['"]__MXS__['"]""", code):
            out.append((line, dyn[0][1]))
    return out


def check_python_payloads(toks, src=""):
    out = []
    for line, code, dyn in python_payloads(toks):
        try:
            ast.parse(code, feature_version=(3, 7))
        except SyntaxError as e:
            out.append((line, "python.Execute payload is not valid Python 3.7: %s | %r"
                        % (e.msg, code[:70])))
    # a path spliced into r'...' ends in a backslash -> SyntaxError at runtime, unless trimRight-ed
    for line, var in raw_splices(toks):
        if not re.search(r"\b%s\s*=\s*trimRight" % re.escape(var.lstrip("(")), src):
            out.append((line, "path variable %r spliced into a Python raw string without trimRight "
                        "(breaks if value ends in a backslash)" % var))
    return out


def check_raw_backslash_in_payloads(toks):
    """r'...\\' inside any python payload / generated python string."""
    out = []
    for line, code, _ in python_payloads(toks):
        if re.search(r"""\br(['"])(?:(?!\1).)*\\\1""", code):
            out.append((line, "Python raw string ends in a backslash"))
    return out


_KW_STOP = {"then", "else", "do", "catch", "of", "collect", "in", "to"}


def count_format_args(toks, k):
    """toks[k] is the format string. Return the number of argument expressions that
    follow on the same logical line (statement)."""
    args, depth, prev_op = 0, 0, True
    line = toks[k].line
    prev_end = toks[k].end
    m = k + 1
    while m < len(toks):
        t = toks[m]
        if depth == 0:
            if t.line != line and not prev_op:
                break
            if t.kind == "ident" and t.text.lower() in _KW_STOP:
                break
            if t.kind == "punct" and t.text in ")]}":
                break
            if t.kind == "op" and t.text == ";":
                break
        if t.kind == "punct" and t.text in "([{":
            adjacent_index = (t.text == "[" and t.start == prev_end and not prev_op)
            if depth == 0 and not prev_op and not adjacent_index:
                args += 1
            elif depth == 0 and prev_op:
                args += 1
            c = _match(toks, m)
            if c is None:
                break
            line = toks[c].line
            prev_end, prev_op = toks[c].end, False
            m = c + 1
            continue
        if t.kind == "op" and t.text not in ("#", "$", "."):
            prev_op = True
        else:
            if prev_op:
                if args == 0 or t.kind != "op":
                    pass
            if t.kind in ("str", "vstr", "ident", "num", "op"):
                if not prev_op or args == 0:
                    args += 1
                prev_op = False
        prev_end = t.end
        line = t.line
        m += 1
    return args


def check_format_calls(toks):
    out = []
    for k, t in enumerate(toks):
        if not (t.kind == "ident" and t.text.lower() == "format"):
            continue
        if k + 1 >= len(toks) or toks[k + 1].kind != "str":
            continue
        s = toks[k + 1]
        want = s.value.count("%")
        got = count_format_args(toks, k + 1)
        # a prefix op chain like `"a" + b` after the string is one arg; ignore ambiguous ones
        if got != want:
            out.append((s.line, "format has %d '%%' placeholder(s) but %d visible arg(s): %s"
                        % (want, got, s.text[:50])))
    return out


def lint_mxs(src):
    toks, problems = lex(src)
    problems = list(problems)
    problems += check_balance(toks)
    problems += check_macro_bodies(toks)
    problems += check_python_payloads(toks, src)
    problems += check_raw_backslash_in_payloads(toks)
    problems += check_format_calls(toks)
    return sorted(set(problems))


def mxs_files():
    skip = {".git", "dist", ".specify", "node_modules", "__pycache__"}
    found = []
    for p in sorted(ROOT.rglob("*.ms")):
        if skip.intersection(p.relative_to(ROOT).parts):
            continue
        found.append(p)
    return found


# ---- linter self-tests (positive controls: the linter must catch known-bad input) ----
def test_linter_catches_unbalanced():
    assert any("unclosed" in m for _, m in lint_mxs("fn f = (\n  print 1\n"))
    assert any("unbalanced" in m for _, m in lint_mxs("x = 1)\n"))
    assert lint_mxs('x = "(((" -- ) ( [\n/* ( */ y = (1)\n') == []


def test_linter_catches_multiline_verbatim():
    assert any("verbatim" in m for _, m in lint_mxs('x = @"C:\\a\nb"\n'))
    assert lint_mxs('x = @"C:\\a\\"\n') == []


def test_linter_catches_srcname_in_macro():
    bad = 'macroScript Foo category:"x"\n(\n on execute do (\n  p = getThisScriptFilename()\n )\n)\n'
    assert any("macroScript" in m for _, m in lint_mxs(bad))
    ok = 'here = getThisScriptFilename()\nmacroScript Foo category:"x"\n(\n on execute do (print 1)\n)\n'
    assert lint_mxs(ok) == []


def test_linter_catches_bad_python_payload():
    assert any("not valid Python" in m for _, m in lint_mxs('python.Execute "x = (1,\\n"\n'))
    assert any("not valid Python" in m for _, m in lint_mxs("python.Execute \"print(f'{1}'\"\n"))
    # 3.8+ syntax must be rejected under feature_version 3.7
    assert any("not valid Python" in m for _, m in lint_mxs('python.Execute "(y := 1)"\n'))
    assert lint_mxs('python.Execute "import sys\\nx = 1"\n') == []
    assert any("raw string" in m for _, m in lint_mxs("python.Execute (\"p=r'\" + root + \"'\")\n"))
    assert lint_mxs("root = trimRight x \"\\\\\"\npython.Execute (\"p=r'\" + root + \"'\")\n") == []


def test_linter_format_arity():
    assert any("format" in m for _, m in lint_mxs('format "a % b %\\n" 1\n'))
    assert lint_mxs('format "a % b %\\n" 1 (foo 2)\n') == []
    assert lint_mxs('format "[x] %\\n" d[1]\n') == []
    assert lint_mxs('format "no args\\n"\n') == []


@pytest.mark.parametrize("path", mxs_files(), ids=lambda p: str(p.relative_to(ROOT)))
def test_maxscript_lint(path):
    problems = lint_mxs(path.read_text(encoding="utf-8", errors="replace"))
    assert not problems, "\n".join("%s:%d: %s" % (path.relative_to(ROOT), ln, m)
                                   for ln, m in problems)


def test_wrapper_scripts_do_not_splice_paths_into_python_literals():
    hits = []
    for p in mxs_files():
        toks, _ = lex(p.read_text(encoding="utf-8"))
        hits += ["%s:%d" % (p.relative_to(ROOT), ln) for ln, _ in raw_splices(toks)]
    assert not hits, hits


def test_maxscript_files_found():
    rels = {p.relative_to(ROOT).as_posix() for p in mxs_files()}   # "/" on Windows too
    assert "install_matforge.ms" in rels
    assert any(r.startswith("packaging/") for r in rels)
    assert any(r.startswith("inspector/bundle/") for r in rels)


def test_maxscript_files_utf8_and_crlf_consistent():
    """Max reads .ms as ANSI unless BOM/UTF-8-clean; non-ASCII bytes in a script
    become mojibake. Flag non-ASCII characters in executable (non-comment) text."""
    bad = []
    for p in mxs_files():
        raw = p.read_bytes()
        try:
            txt = raw.decode("utf-8")
        except UnicodeDecodeError:
            bad.append("%s: not valid UTF-8" % p.relative_to(ROOT))
            continue
        toks, _ = lex(txt)
        for t in toks:
            if any(ord(ch) > 127 for ch in t.text):
                bad.append("%s:%d: non-ASCII in code/string %r" % (p.relative_to(ROOT), t.line, t.text[:30]))
    assert not bad, "\n".join(bad)


# ---------------------------------------------------------------------------
# PackageContents.xml validation + idempotent / unicode-path builds
# ---------------------------------------------------------------------------
GUID = re.compile(r"^\{[0-9A-F]{8}-([0-9A-F]{4}-){3}[0-9A-F]{12}\}$")
KNOWN_COMPONENTS_DESC = "post-start-up scripts parts"   # known-good (Inspector's value)


def _load(modname, rel):
    import importlib.util
    spec = importlib.util.spec_from_file_location(modname, str(ROOT / rel))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def validate_package_contents(bundle):
    xml_path = bundle / "PackageContents.xml"
    root = ET.parse(str(xml_path)).getroot()          # raises if not well-formed
    errs = []
    if root.tag != "ApplicationPackage":
        errs.append("root is %r" % root.tag)
    if len(list(root.iter("ApplicationPackage"))) != 1:
        errs.append("expected exactly one ApplicationPackage")
    for a in ("SchemaVersion", "Name", "AppVersion", "ProductCode", "UpgradeCode"):
        if not root.get(a):
            errs.append("missing @%s" % a)
    for a in ("ProductCode", "UpgradeCode"):
        if root.get(a) and not GUID.match(root.get(a)):
            errs.append("%s not a braced upper-case GUID: %s" % (a, root.get(a)))
    if root.get("ProductCode") == root.get("UpgradeCode"):
        errs.append("ProductCode == UpgradeCode")
    comps = list(root.iter("Components"))
    if not comps:
        errs.append("no Components")
    for c in comps:
        if c.get("Description") != KNOWN_COMPONENTS_DESC:
            errs.append("Components@Description=%r" % c.get("Description"))
        req = c.find("RuntimeRequirements")
        if req is None:
            errs.append("no RuntimeRequirements")
        else:
            if int(req.get("SeriesMin")) > int(req.get("SeriesMax")):
                errs.append("SeriesMin > SeriesMax")
            if req.get("OS") != "Win64" or req.get("Platform") != "3ds Max":
                errs.append("RuntimeRequirements OS/Platform %r/%r" % (req.get("OS"), req.get("Platform")))
        entries = c.findall("ComponentEntry")
        if not entries:
            errs.append("no ComponentEntry")
        for e in entries:
            m = e.get("ModuleName") or ""
            if not m.startswith("./Contents/"):
                errs.append("ModuleName %r not under ./Contents/" % m)
            f = bundle / m[2:]
            if not f.is_file():
                errs.append("ModuleName %r missing from bundle" % m)
            elif f.name != pathlib.Path(m).name:      # case-exact (Windows is case-insensitive, Max is not always)
                errs.append("case mismatch %r" % m)
            else:
                names = [x.name for x in f.parent.iterdir()]
                if f.name not in names:
                    errs.append("ModuleName case differs from on-disk name: %r" % m)
    return root, errs


def tree_hashes(bundle):
    out = {}
    for p in sorted(bundle.rglob("*")):
        rel = p.relative_to(bundle).as_posix()
        out[rel] = hashlib.sha256(p.read_bytes()).hexdigest() if p.is_file() else "<dir>"
    return out


def _inspector_sandbox(tmp):
    """Copy inspector/ + matphys/ + forgeui/ so build_bundle.py (hard-wired DIST) can't touch the repo."""
    box = pathlib.Path(tmp) / "repo"
    box.mkdir()
    shutil.copytree(str(ROOT / "inspector"), str(box / "inspector"),
                    ignore=shutil.ignore_patterns("dist", "__pycache__", "*.pyc"))
    shutil.copytree(str(ROOT / "matphys"), str(box / "matphys"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    shutil.copytree(str(ROOT / "forgeui"), str(box / "forgeui"),
                    ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    return box


def _run_inspector_build(box, *extra):
    env = dict(os.environ, PYTHONDONTWRITEBYTECODE="1")
    return subprocess.run([sys.executable, "-B", str(box / "inspector" / "tools" / "build_bundle.py")] + list(extra),
                          cwd=str(box), env=env, capture_output=True, text=True)


@pytest.fixture(scope="module")
def inspector_bundle(tmp_path_factory):
    box = _inspector_sandbox(tmp_path_factory.mktemp("insp"))
    r = _run_inspector_build(box)
    assert r.returncode == 0, r.stderr
    return box / "inspector" / "dist" / "MaterialInspector.bundle"


@pytest.fixture(scope="module")
def matforge_bundle(tmp_path_factory):
    return _load("bmb_c", "tools/build_matforge_bundle.py").build(tmp_path_factory.mktemp("mf"))


def test_source_package_contents_valid():
    for rel in ("packaging/MatForge.bundle", "inspector/bundle/MaterialInspector.bundle"):
        root, errs = validate_package_contents(ROOT / rel)
        # source trees do not hold python; only the startup .ms must exist
        errs = [e for e in errs if "missing from bundle" not in e]
        assert not errs, (rel, errs)


def test_built_package_contents_valid(matforge_bundle, inspector_bundle):
    for b in (matforge_bundle, inspector_bundle):
        root, errs = validate_package_contents(b)
        assert not errs, (str(b), errs)


def test_two_bundles_have_distinct_identity(matforge_bundle, inspector_bundle):
    a, _ = validate_package_contents(matforge_bundle)
    b, _ = validate_package_contents(inspector_bundle)
    for attr in ("ProductCode", "UpgradeCode", "Name"):
        assert a.get(attr) != b.get(attr), attr


def test_matforge_build_idempotent(tmp_path):
    m = _load("bmb_c2", "tools/build_matforge_bundle.py")
    a = tree_hashes(m.build(tmp_path / "a"))
    b = tree_hashes(m.build(tmp_path / "b"))
    again = tree_hashes(m.build(tmp_path / "a"))        # rebuild over an existing bundle
    assert a == b == again
    assert not any("__pycache__" in k or k.endswith(".pyc") for k in a)


def test_matforge_build_unicode_space_destination(tmp_path):
    dest = tmp_path / u"Mat F\u00f6rge \u2713"
    m = _load("bmb_c3", "tools/build_matforge_bundle.py")
    ref = tree_hashes(m.build(tmp_path / "plain"))
    got = tree_hashes(m.build(dest))
    assert got == ref
    r = subprocess.run([sys.executable, "-B", str(ROOT / "tools" / "build_matforge_bundle.py"),
                        "--out", str(dest)], capture_output=True, text=True,
                       env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    assert r.returncode == 0, r.stderr


def test_inspector_build_idempotent(tmp_path):
    box = _inspector_sandbox(tmp_path)
    assert _run_inspector_build(box).returncode == 0
    dist = box / "inspector" / "dist" / "MaterialInspector.bundle"
    a = tree_hashes(dist)
    assert _run_inspector_build(box).returncode == 0
    assert tree_hashes(dist) == a
    assert not any("__pycache__" in k or k.endswith(".pyc") for k in a)
    assert not any(k.split("/")[1:2] == ["tests"] for k in a)


def test_inspector_build_honours_out(tmp_path):
    box = _inspector_sandbox(tmp_path)
    dest = tmp_path / u"Insp \u00e9 \u2713"
    r = _run_inspector_build(box, "--out", str(dest))           # STRESS-C1 regression
    assert r.returncode == 0, r.stdout + r.stderr
    b = dest / "MaterialInspector.bundle"
    assert (b / "PackageContents.xml").is_file(), r.stdout + r.stderr
    assert not (box / "inspector" / "dist").exists()             # source tree untouched
    assert not any("devtools" in p.parts for p in b.rglob("*"))
    assert (b / "Contents" / "scripts" / "material_inspector" / "core").is_dir()


def test_inspector_build_refuses_secrets(tmp_path):
    box = _inspector_sandbox(tmp_path)
    (box / "inspector" / "material_inspector" / "_keys.json").write_text("{}")
    r = _run_inspector_build(box, "--out", str(tmp_path / "o"))
    assert r.returncode == 0                       # ignored by the copy ...
    assert not list((tmp_path / "o").rglob("_keys.json"))
    m = _load("ib_c1", "inspector/tools/build_bundle.py")
    bad = tmp_path / "bad"
    (bad / "Contents" / "tests").mkdir(parents=True)
    with pytest.raises(SystemExit):                # ... and check() would refuse it
        m.check(bad)


def test_bundle_ships_no_secrets_or_tests(matforge_bundle, inspector_bundle):
    bad = ("_keys.json", "_falkey.py", "_omegakey.py")
    for b in (matforge_bundle, inspector_bundle):
        for p in b.rglob("*"):
            assert p.name not in bad, p
            assert "tests" not in p.relative_to(b).parts, p


def test_bundle_sizes_sane(matforge_bundle, inspector_bundle):
    for b, cap in ((matforge_bundle, 2e6), (inspector_bundle, 2e6)):
        total = sum(p.stat().st_size for p in b.rglob("*") if p.is_file())
        assert 1e4 < total < cap, (b, total)


# ---- import isolation ----
_ISOLATE = r"""
import sys, importlib, os
scripts, mockdir, outside = sys.argv[1], sys.argv[2], sys.argv[3]
assert os.getcwd() == "/" or os.name == "nt", os.getcwd()
sys.path[:] = [p for p in sys.path if os.path.abspath(p) != os.path.abspath(outside)]
sys.path.insert(0, scripts)
sys.path.insert(1, mockdir)
mods = sys.argv[4:]
if mods[0] == "--stub":
    import types
    mods = mods[1:]
    stub = types.ModuleType("pymxs")
    stub.runtime = types.SimpleNamespace()
    sys.modules["pymxs"] = stub
else:
    import mock_pymxs
    mock_pymxs.install(renderer="vray")
bad = []
for m in mods:
    try:
        mod = importlib.import_module(m)
    except Exception as e:
        bad.append("%s: %s: %s" % (m, type(e).__name__, e))
        continue
for name, mod in list(sys.modules.items()):
    f = getattr(mod, "__file__", None) or ""
    if name.split(".")[0].startswith(("PySide6", "PySide2", "shiboken6", "shiboken2")) \
            or name.split(".")[0] in ("_virtualenv", "sitecustomize"):
        continue  # real Qt binding and venv bootstrap, not bundle leaks
    if os.sep + "site-packages" + os.sep in f:
        continue  # third-party wheels of an in-repo venv (e.g. .venv-qt), not bundle leaks
    if f and os.path.abspath(f).startswith(os.path.abspath(outside) + os.sep) \
            and not os.path.abspath(f).startswith(os.path.abspath(mockdir)):
        bad.append("%s loaded from outside the bundle: %s" % (name, f))
print("\n".join(bad) if bad else "OK")
"""


def _isolated(tmp_path, bundle, mods, extra_files=()):
    scripts = tmp_path / "scripts"
    shutil.copytree(str(bundle / "Contents" / "scripts"), str(scripts))
    mock = tmp_path / "mock"
    mock.mkdir()
    shutil.copy(str(ROOT / "tests" / "mock_pymxs.py"), str(mock / "mock_pymxs.py"))
    env = {k: v for k, v in os.environ.items() if k != "PYTHONPATH"}
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    drv = tmp_path / "drv.py"
    drv.write_text(_ISOLATE)
    r = subprocess.run([sys.executable, "-I", "-B", str(drv), str(scripts), str(mock), str(ROOT)] + list(mods),
                       cwd="/", env=env, capture_output=True, text=True)
    return r, scripts


def test_matforge_bundle_import_isolation(tmp_path, matforge_bundle):
    r, scripts = _isolated(tmp_path, matforge_bundle,
                           ["matphys", "core.recipes", "maxplugin.builder", "maxplugin.builder_corona",
                            "maxplugin.forge_max", "mfconfig", "run_matforge"])
    # run_matforge may print the Qt-dock fallback notice first; the driver's verdict is the last line
    assert r.stdout.strip().splitlines()[-1] == "OK", r.stdout + r.stderr
    # the shared Qt UI kit must ship inside the bundle
    assert (scripts / "forgeui" / "__init__.py").is_file()


def test_matforge_bundle_forge_max_paths_inside_bundle(tmp_path, matforge_bundle):
    """forgeui / CLI / FAL resolve relative to the bundle, not the repo."""
    code = ("import sys,os;sys.path[:0]=[sys.argv[1],sys.argv[2]];import mock_pymxs;mock_pymxs.install();"
            "import maxplugin.forge_max as f;"
            "print(os.path.join(sys.argv[1], 'forgeui', '__init__.py'), f.CLI, f.FAL, sep='|')")
    scripts = tmp_path / "s"
    shutil.copytree(str(matforge_bundle / "Contents" / "scripts"), str(scripts))
    r = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(scripts), str(ROOT / "tests")],
                       cwd="/", capture_output=True, text=True,
                       env={"PATH": os.environ.get("PATH", ""), "PYTHONDONTWRITEBYTECODE": "1"})
    assert r.returncode == 0, r.stderr
    for p in r.stdout.strip().split("|"):
        assert p.startswith(str(scripts)), p
        assert os.path.isfile(p), p


def test_inspector_bundle_import_isolation(tmp_path, inspector_bundle):
    mods = ["material_inspector.core.rules", "material_inspector.core.physics",
            "material_inspector.core.inspector", "material_inspector.core.report",
            "material_inspector.max_adapter.scene", "material_inspector.max_adapter.fixes"]
    r, _ = _isolated(tmp_path, inspector_bundle, ["--stub"] + mods)
    assert r.stdout.strip() == "OK", r.stdout + r.stderr


def test_inspector_bundle_ui_import_isolation(tmp_path, inspector_bundle):
    r, _ = _isolated(tmp_path, inspector_bundle, ["--stub", "material_inspector.max_adapter.ui"])
    out = r.stdout.strip()
    if "No module named" in out and re.search(r"PySide|PyQt|qtpy", out):
        pytest.skip("Qt binding not installed on this interpreter (adapter UI needs Max's PySide)")
    assert out == "OK", out + r.stderr


# ---------------------------------------------------------------------------
# Real old interpreter + vermin (skip when tools unavailable)
# ---------------------------------------------------------------------------
PY38_FILES = ["tests/test_matphys.py", "tests/test_builder_logic.py", "tests/test_builder_physics.py",
              "tests/test_builder_corona.py", "tests/test_dispatch.py",
              "tests/test_corona_props_consistency.py", "tests/test_packaging.py"]


def test_suites_pass_on_python_38(tmp_path):
    if not UV:
        pytest.skip("uv not installed")
    f = subprocess.run([UV, "python", "find", "3.8"], capture_output=True, text=True)
    if f.returncode != 0:
        pytest.skip("CPython 3.8 not installed (uv python install 3.8)")
    cmd = [UV, "run", "--python", "3.8", "--with", "pytest", "--with", "numpy<1.25", "--with", "Pillow<10.1",
           "python", "-B", "-m", "pytest", "-q", "-p", "no:cacheprovider"] + PY38_FILES
    r = subprocess.run(cmd, cwd=str(ROOT), capture_output=True, text=True, timeout=600,
                       env=dict(os.environ, PYTHONDONTWRITEBYTECODE="1"))
    if r.returncode != 0 and ("No solution found" in r.stderr or "Failed to download" in r.stderr
                              or "error sending request" in r.stderr):
        pytest.skip("could not provision 3.8 deps (offline?)")
    assert r.returncode == 0, r.stdout[-3000:] + r.stderr[-1000:]


def _vermin(args):
    r = subprocess.run([UVX, "vermin"] + args, cwd=str(ROOT), capture_output=True, text=True, timeout=300)
    if r.returncode != 0 and ("Failed to" in r.stderr or "error sending request" in r.stderr):
        pytest.skip("vermin unavailable (offline?)")
    return r


def test_vermin_in_max_code_is_py37():
    if not UVX:
        pytest.skip("uvx not installed")
    r = _vermin(["-t=3.7-", "--no-tips", "--violations", "--eval-annotations", "maxplugin", "matphys",
                 "run_matforge.py", "HEADLESS_SMOKE.py", "MAX_SMOKE.py", "core", "forge_cli.py",
                 "forge_fal.py", "mfconfig.py"])
    assert r.returncode == 0, r.stdout + r.stderr


def test_vermin_inspector_is_le_py311():
    if not UVX:
        pytest.skip("uvx not installed")
    r = _vermin(["-t=3.11-", "--no-tips", "--violations", "inspector/material_inspector"])
    assert r.returncode == 0, r.stdout + r.stderr


# ---------------------------------------------------------------------------
# Windows path semantics (checked statically from any OS)
# ---------------------------------------------------------------------------
PY_RUNTIME = ["maxplugin", "core", "matphys", "mfconfig.py", "forge_cli.py", "forge_fal.py",
              "forge_fal_batch.py", "run_matforge.py", "post_grade.py"]


def _py_files(rels):
    out = []
    for r in rels:
        p = ROOT / r
        out += sorted(p.rglob("*.py")) if p.is_dir() else [p]
    return out


def path_smells(src):
    smells = []
    for n in ast.walk(ast.parse(src)):
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute):
            if n.func.attr == "join" and getattr(n.func.value, "attr", "") == "path":
                for a in n.args:
                    if isinstance(a, ast.Constant) and isinstance(a.value, str) and \
                            ("/" in a.value or "\\" in a.value):
                        smells.append((n.lineno, "os.path.join with embedded separator %r" % a.value))
            if n.func.attr == "replace" and len(n.args) == 2 and all(isinstance(a, ast.Constant) for a in n.args):
                if n.args[0].value == "\\" and n.args[1].value == "/":
                    smells.append((n.lineno, 'replace("\\\\", "/") on a path'))
        if isinstance(n, ast.Attribute) and n.attr == "sep" and getattr(n.value, "id", "") == "os":
            smells.append((n.lineno, "os.sep assumption"))
    return smells


def test_path_smell_detector_positive_control():
    assert path_smells("import os\nos.path.join(a, 'x/y')\n")
    assert path_smells("p.replace('\\\\', '/')\n")
    assert not path_smells("import os\nos.path.join(a, 'x')\n")


def test_no_mixed_separator_path_construction():
    found = []
    for f in _py_files(PY_RUNTIME):
        for ln, m in path_smells(f.read_text(encoding="utf-8")):
            found.append("%s:%d: %s" % (f.relative_to(ROOT), ln, m))
    assert not found, "\n".join(found)


MAX_PATH_BUDGET = 240   # Windows MAX_PATH is 260 incl. NUL; keep 20 chars of slack for the app


def _longest_map_path(name, image_dir):
    """Longest file forge_cli / forge_fal would write for `name` (Windows rules)."""
    import mock_pymxs
    mock_pymxs.install()
    import maxplugin.forge_max as fm
    from core.maps import MAP_FILES
    cleaned = fm._sanitize(name)
    out_dir = pathlib.PureWindowsPath(image_dir) / (cleaned + "_maps")
    names = list(MAP_FILES.values()) + ["manifest.json", "roughness.png.part", "opacity.png.part"]
    return max(len(str(out_dir / n)) for n in names), cleaned


def test_normal_name_path_length_ok():
    n, _ = _longest_map_path("Patio_Teak", r"C:\Users\artist\Documents\Textures\Wood")
    assert n < MAX_PATH_BUDGET


def test_long_material_name_stays_under_max_path():
    n, cleaned = _longest_map_path("A" * 200, r"C:\Users\artist\Documents\Textures\Wood")
    assert n <= MAX_PATH_BUDGET, n                               # STRESS-C2 regression
    assert len(cleaned) <= 48


def test_appdata_unset_fallback(tmp_path):
    """Linux CI: no %APPDATA% -> mfconfig must not crash and falls back to the folder-local file."""
    scripts = tmp_path / "s"
    shutil.copytree(str(ROOT), str(scripts), ignore=shutil.ignore_patterns(
        ".git", "dist", "tests", "inspector", "assets", "docs", "specs", "research_notes", "reports",
        "__pycache__", ".specify", ".router", "sample_maps", "*.png", "*.jpg", "*.pdf"))
    code = ("import os,sys;sys.path.insert(0,sys.argv[1]);os.environ.pop('APPDATA',None);"
            "import mfconfig as m;print(m._user_keys_path());print(m._keys_path(True));"
            "print(m.get_keys_status()['fal_set']);m.save_keys(fal_key='k1');print(m.get_fal_key())")
    env = {k: v for k, v in os.environ.items() if k not in ("APPDATA", "FAL_KEY")}
    r = subprocess.run([sys.executable, "-I", "-B", "-c", code, str(scripts)], cwd="/", env=env,
                       capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    lines = r.stdout.split("\n")
    assert lines[0] == "None"
    assert lines[1] == str(scripts / "_keys.json")
    assert lines[3] == "k1"
    assert (scripts / "_keys.json").is_file()


def test_forge_max_sanitize_is_windows_safe():
    import mock_pymxs
    mock_pymxs.install()
    import maxplugin.forge_max as fm
    for nasty in ('a:b*c?"d<e>f|g', "..\\..\\evil", "../../evil", "  trailing. ", "", "CON", "\u00e9\u00e8\u0928"):
        s = fm._sanitize(nasty)
        assert s and not set(s) & set('\\/:*?"<>| '), (nasty, s)
        assert not s.endswith(".") and ".." not in s
