"""Tests for plugin external paths and dependency management."""
import os
import json
import tempfile
from pathlib import Path

from plugin.store import (
    PLUGIN_PATH_ENV,
    _external_plugin_dirs,
    _scan_external_plugins,
    install_dependencies,
)
from plugin.loader import _strip_version_spec, check_missing_deps


class TestExternalPluginDirs:
    def test_empty_when_env_not_set(self, monkeypatch):
        monkeypatch.delenv(PLUGIN_PATH_ENV, raising=False)
        assert _external_plugin_dirs() == []

    def test_returns_existing_dirs(self, monkeypatch, tmp_path):
        d1 = tmp_path / "plugins1"
        d1.mkdir()
        d2 = tmp_path / "plugins2"
        d2.mkdir()
        fake = tmp_path / "nonexistent"
        monkeypatch.setenv(PLUGIN_PATH_ENV, f"{d1}{os.pathsep}{d2}{os.pathsep}{fake}")
        result = _external_plugin_dirs()
        assert d1 in result
        assert d2 in result
        assert fake not in result

    def test_ignores_empty_segments(self, monkeypatch, tmp_path):
        d = tmp_path / "p"
        d.mkdir()
        monkeypatch.setenv(PLUGIN_PATH_ENV, f"{os.pathsep}{d}{os.pathsep}")
        result = _external_plugin_dirs()
        assert result == [d]


class TestScanExternalPlugins:
    def test_discovers_plugin_with_manifest(self, monkeypatch, tmp_path):
        plug_dir = tmp_path / "my_plugin"
        plug_dir.mkdir()
        manifest = {"name": "my_plugin", "version": "1.0", "dependencies": []}
        (plug_dir / "manifest.json").write_text(json.dumps(manifest))
        monkeypatch.setenv(PLUGIN_PATH_ENV, str(tmp_path))
        plugins = _scan_external_plugins()
        assert len(plugins) == 1
        assert plugins[0].name == "my_plugin"
        assert plugins[0].scope.value == "external"


class TestStripVersionSpec:
    def test_bare_name(self):
        assert _strip_version_spec("requests") == "requests"

    def test_with_version(self):
        assert _strip_version_spec("requests>=2.28") == "requests"

    def test_with_extras(self):
        assert _strip_version_spec("package[extra]>=1.0") == "package"

    def test_hyphen_to_underscore(self):
        assert _strip_version_spec("my-package>=1.0") == "my_package"


class TestCheckMissingDeps:
    def test_builtin_not_missing(self):
        assert check_missing_deps(["os", "sys", "json"]) == []

    def test_fake_package_missing(self):
        missing = check_missing_deps(["nonexistent_pkg_xyz_12345"])
        assert "nonexistent_pkg_xyz_12345" in missing


class TestInstallDependencies:
    def test_is_callable(self):
        assert callable(install_dependencies)
