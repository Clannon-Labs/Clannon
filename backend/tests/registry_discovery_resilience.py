"""discover() must never crash on a broken capability module.

The registry invariant (registry/CLAUDE.md) is that a broken capability is
recorded and excluded, never fatal. Historically that only held for *decorator-
time* validation (malformed metadata) — a module that raised AT IMPORT time
propagated out of discover() and took the WHOLE roster down (zero capabilities
registered). This pins the import-time isolation: one exploding module is logged,
recorded in import_failures(), and SKIPPED; every other module on both sides of it
still imports. A batch layer dropping in new capability modules depends on exactly
this.
"""

from collections import namedtuple

import registry.capabilities.registration as reg

_ModInfo = namedtuple("_ModInfo", "name")


def test_discover_survives_a_module_that_explodes_at_import(monkeypatch):
    reg.reset_discovery()

    # a synthetic roster per package: two good modules straddling one that raises
    def fake_walk(path, prefix):
        yield _ModInfo(name=prefix + "good_a")
        yield _ModInfo(name=prefix + "boom")
        yield _ModInfo(name=prefix + "good_b")

    imported: list[str] = []
    real_import = reg.importlib.import_module

    def fake_import(name):
        if name in reg._CAPABILITY_PACKAGES:
            return real_import(name)                 # the packages themselves are fine
        if name.endswith(".boom"):
            raise RuntimeError("kaboom at import time")
        imported.append(name)
        return object()                              # a stand-in module; no decorators fire

    monkeypatch.setattr(reg.pkgutil, "walk_packages", fake_walk)
    monkeypatch.setattr(reg.importlib, "import_module", fake_import)

    reg.discover()   # MUST NOT raise — the whole point

    # every good module (on both sides of the boom, in both packages) still imported
    assert [n for n in imported if n.endswith("good_a")], "module before the boom must import"
    assert [n for n in imported if n.endswith("good_b")], "module after the boom must import"
    # the failure is visible, not silently swallowed
    failed = reg.import_failures()
    assert [m for m, _ in failed if m.endswith(".boom")], "the broken module must be recorded"
    assert all("kaboom" in err for m, err in failed if m.endswith(".boom"))

    # restore the real roster for every other test (monkeypatch reverts walk/import)
    reg.reset_discovery()
    reg.discover()


def test_clean_roster_has_no_import_failures():
    # the real capability packages import cleanly today
    reg.reset_discovery()
    reg.discover()
    assert reg.import_failures() == []
