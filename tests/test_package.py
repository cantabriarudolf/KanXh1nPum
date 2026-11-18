"""Smoke checks for the packaging wiring.

These are not behaviour tests: they prove that the wheel actually ships the `kx`
package and that its console entry point resolves. If `[tool.hatch.build.targets.wheel]`
or `[project.scripts]` drift, these fail before anything else does.
"""

import importlib.metadata

import kx


def test_version_is_exposed() -> None:
    assert kx.__version__ == "0.1.0"


def test_entry_point_is_installed() -> None:
    entry_points = importlib.metadata.entry_points(group="console_scripts")
    assert any(ep.name == "kx" and ep.value == "kx.cli:main" for ep in entry_points)
