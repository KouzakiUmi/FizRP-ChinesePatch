"""X2 标准库回归：只使用临时游戏/存档，不探测或写入真实游戏。"""
from contextlib import ExitStack
import copy
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import queue
import subprocess
import sys
import tempfile
import types
import unittest
from unittest import mock
import zipfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tools"))
import build_manifest
import package_additive as package
import patch_launcher as gui
import patch_tool as core


def put(path, data):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


class X2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="fizrp-x2-test-")
        self.base = Path(self.temp.name).resolve()
        self.addCleanup(self.clean_temp)
        self.stack = ExitStack()
        self.addCleanup(self.stack.close)
        self.payload = self.base / "payload"
        self.game = self.base / "game"
        self.data = self.game / core.DATA_DIRNAME
        self.refs = {name: ("original:" + name).encode() for name in core.REFERENCE_FILES}
        for name, data in self.refs.items():
            put(self.data / name, data)
        self.original = b"original asset"
        put(self.data / "sample.assets", self.original)
        self.files = {"sample.assets": b"translated asset",
                      "added.assets": b"added data",
                      "StreamingAssets/aa/StandaloneWindows64/fixture.bundle": b"nested bundle",
                      "winhttp.dll": b"loader",
                      "BepInEx/plugins/FizRPLangMenu.dll": b"plugin"}
        for rel, data in self.files.items():
            put(self.payload / rel, data)
        self.manifest = {
            "mode": "additive", "version": "1.2.2", "name": "test", "game": "test",
            "payload_files": len(self.files), "payload_bytes": sum(map(len, self.files.values())),
            "patch_info": {"payload_files": len(self.files),
                           "reference_hashes": {k: hashlib.sha256(v).hexdigest() for k, v in self.refs.items()}},
            "files": [{"path": rel, "size": len(data), "sha256": hashlib.sha256(data).hexdigest()}
                      for rel, data in sorted(self.files.items())],
        }
        self.manifest_path = self.base / "manifest-additive.json"
        self.write_manifest(self.manifest)
        self.stack.enter_context(mock.patch.object(core, "PAYLOAD_DIR", str(self.payload)))
        self.stack.enter_context(mock.patch.object(core, "MANIFEST", str(self.manifest_path)))
        self.stack.enter_context(mock.patch.dict(os.environ, {"FIZRP_SAVE_ROOT": str(self.base / "saves")}))

    def clean_temp(self):
        # 删除前核对绝对目标就是本测试创建的临时目录。
        target = Path(self.temp.name).resolve()
        assert target == self.base and target.name.startswith("fizrp-x2-test-")
        assert target.parent == Path(tempfile.gettempdir()).resolve()
        self.temp.cleanup()

    def write_manifest(self, doc):
        self.manifest_path.write_text(json.dumps(doc), encoding="utf-8")

    def install(self, **kwargs):
        return core.execute("install", str(self.game), assume_yes=True, seed_save=False, **kwargs)

    def game_snapshot(self):
        return {str(p.relative_to(self.game)): p.read_bytes() for p in self.game.rglob("*") if p.is_file()}

    def test_install_verify_uninstall_roundtrip(self):
        put(self.game / "BepInEx/plugins/Other.dll", b"user plugin")
        before = self.game_snapshot()
        installed = self.install()
        self.assertEqual(installed["exit"], 0, installed)
        self.assertEqual(installed["written"], len(self.files))
        self.assertEqual(installed["loader_written"], 2)
        for rel, data in self.files.items():
            self.assertEqual(Path(core._target_path(str(self.data), rel)).read_bytes(), data)
        self.assertEqual(core.execute("verify", str(self.game))["exit"], 0)
        result = core.execute("uninstall", str(self.game))
        self.assertEqual(result["exit"], 0, result)
        after = {k: v for k, v in self.game_snapshot().items()
                 if not Path(k).parts[0].startswith((core.BACKUP_PREFIX, core.ORIGINAL_PREFIX))}
        self.assertEqual(after, before)

    def test_reinstall_keeps_first_backup(self):
        self.assertEqual(self.install()["exit"], 0)
        self.assertEqual(self.install()["exit"], 0)
        original = self.game / core.ORIGINAL_PREFIX / "sample.assets"
        self.assertEqual(original.read_bytes(), self.original)
        self.assertEqual(core.execute("uninstall", str(self.game))["exit"], 0)
        self.assertEqual((self.data / "sample.assets").read_bytes(), self.original)

    def test_missing_payload_prevents_all_writes_even_with_yes(self):
        target = (self.payload / "sample.assets").resolve()
        self.assertEqual(target.parent, self.payload.resolve())
        target.unlink()
        before = self.game_snapshot()
        result = self.install()
        self.assertEqual(result["exit"], 1)
        self.assertFalse(result["ok"])
        self.assertIn("缺失", result["error"])
        self.assertEqual(self.game_snapshot(), before)

    def test_same_size_corruption_prevents_all_writes(self):
        put(self.payload / "sample.assets", b"X" * len(self.files["sample.assets"]))
        before = self.game_snapshot()
        result = self.install()
        self.assertEqual(result["exit"], 1)
        self.assertIn("哈希", result["error"])
        self.assertEqual(self.game_snapshot(), before)

    def test_extra_payload_prevents_all_writes(self):
        put(self.payload / "extra.assets", b"unexpected")
        before = self.game_snapshot()
        self.assertEqual(self.install()["exit"], 1)
        self.assertEqual(self.game_snapshot(), before)

    def test_missing_or_invalid_manifest_fails_closed(self):
        before = self.game_snapshot()
        for content in ("not json", "{}", "[]"):
            with self.subTest(content=content):
                self.manifest_path.write_text(content, encoding="utf-8")
                self.assertEqual(self.install()["exit"], 1)
                self.assertEqual(core.execute("check")["exit"], 1)
                self.assertEqual(self.game_snapshot(), before)
        self.assertEqual(self.manifest_path.resolve().parent, self.base)
        self.manifest_path.unlink()
        self.assertEqual(self.install()["exit"], 1)

    def test_manifest_schema_rejects_unsafe_or_incomplete_entries(self):
        variants = []
        for path in ("../escape.assets", "/escape", "C:/escape", "a/../escape", "a\\escape", "a./file"):
            doc = copy.deepcopy(self.manifest)
            doc["files"][0]["path"] = path
            variants.append(doc)
        for field, value in (("sha256", ""), ("size", True)):
            doc = copy.deepcopy(self.manifest)
            doc["files"][0][field] = value
            variants.append(doc)
        for mutate in (lambda d: d["patch_info"].pop("reference_hashes"),
                       lambda d: d.update(mode="replace"),
                       lambda d: d.update(payload_files=999),
                       lambda d: d.update(payload_bytes=0),
                       lambda d: d.update(version="../../escape"),
                       lambda d: d["files"][1].update(path=d["files"][0]["path"].upper())):
            doc = copy.deepcopy(self.manifest)
            mutate(doc)
            variants.append(doc)
        for doc in variants:
            with self.subTest(doc=doc):
                with self.assertRaises(RuntimeError):
                    core.validate_manifest(doc)

    def test_gui_precheck_and_execute_use_same_x2_payload(self):
        app = types.SimpleNamespace(events=queue.Queue())
        gui.InstallerApp._precheck_worker(app, "install", str(self.game))
        event = app.events.get_nowait()
        self.assertEqual(event[0], "precheck")
        self.assertEqual(event[2]["mode"], "additive")
        self.assertTrue(event[2]["ok"], event)
        gui.InstallerApp._execute_worker(app, "install", str(self.game), True)
        events = []
        while not app.events.empty():
            events.append(app.events.get_nowait())
        result = next(event[2] for event in events if event[0] == "done")
        self.assertEqual(result["exit"], 0, result)
        self.assertEqual(result["loader_written"], 2)
        self.assertTrue((self.game / "winhttp.dll").is_file())

    def test_io_failure_never_reports_success(self):
        copy2 = core.shutil.copy2
        def fail_loader(src, dst, *args, **kwargs):
            if Path(dst) == self.game / "winhttp.dll":
                raise OSError("simulated locked file")
            return copy2(src, dst, *args, **kwargs)
        with mock.patch.object(core.shutil, "copy2", side_effect=fail_loader):
            result = self.install()
        self.assertEqual(result["exit"], 1)
        self.assertFalse(result["ok"])
        self.assertIn("simulated locked file", result["error"])

    def test_verify_uses_manifest_not_mutated_payload(self):
        self.assertEqual(self.install()["exit"], 0)
        corrupted = b"X" * len(self.files["sample.assets"])
        put(self.payload / "sample.assets", corrupted)
        put(self.data / "sample.assets", corrupted)
        result = core.execute("verify", str(self.game))
        self.assertEqual(result["exit"], 1)
        self.assertFalse(result["ok"])

    def test_zip_check_rejects_stale_installer_and_manifest(self):
        font_license = self.base / "OFL.txt"
        put(font_license, b"test license")
        with mock.patch.multiple(package, PAYLOAD=str(self.payload), MANIFEST=str(self.manifest_path), OFL_SRC=str(font_license)):
            release = self.base / "FizRP-X2-v1.2.2"
            package.write_release(str(release), "1.2.2", self.manifest)
            archive_path = str(release) + ".zip"
            package.write_zip(str(release), archive_path)
            with zipfile.ZipFile(archive_path) as archive:
                contents = {name: archive.read(name) for name in archive.namelist()}
            stale = copy.deepcopy(self.manifest)
            stale["name"] = "old manifest"
            for filename, data in (("patch_tool.py", b"old installer"),
                                   ("manifest-additive.json", json.dumps(stale).encode())):
                with self.subTest(filename=filename):
                    destination = self.base / ("stale-" + filename) / (release.name + ".zip")
                    destination.parent.mkdir()
                    with zipfile.ZipFile(destination, "w") as archive:
                        for name, content in contents.items():
                            archive.writestr(name, data if name == release.name + "/" + filename else content)
                    self.assertTrue(any("stale" in problem for problem in package.verify_zip(str(destination), self.manifest)))

    def test_existing_save_is_never_overwritten(self):
        path = Path(core.save_file_path())
        put(path, b"user save")
        result = {}
        self.assertFalse(core.seed_save_if_absent(result, lambda _: None))
        self.assertEqual(path.read_bytes(), b"user save")

    def test_save_creation_race_is_safe(self):
        path = Path(core.save_file_path())
        real_open = open
        def racing_open(name, mode="r", *args, **kwargs):
            if Path(name) == path and mode == "xb":
                put(path, b"created by game")
            return real_open(name, mode, *args, **kwargs)
        with mock.patch("builtins.open", side_effect=racing_open):
            self.assertFalse(core.seed_save_if_absent({}, lambda _: None))
        self.assertEqual(path.read_bytes(), b"created by game")

    def test_cli_rejects_replacement_option(self):
        with mock.patch("sys.stderr", new=io.StringIO()):
            with self.assertRaises(SystemExit) as exc:
                core.main(["check", "--replacement"])
        self.assertEqual(exc.exception.code, 2)

    def test_manifest_builder_uses_independent_reference(self):
        ref = self.base / "game-reference.json"
        ref.write_text(json.dumps({"reference_hashes": self.manifest["patch_info"]["reference_hashes"]}), encoding="utf-8")
        result = build_manifest.build_manifest(str(self.payload), str(ref))
        self.assertEqual(result["mode"], "additive")
        self.assertEqual(result["patch_info"]["reference_hashes"], self.manifest["patch_info"]["reference_hashes"])
        self.assertNotIn("legacy", result["patch_info"]["patch_info_source"])
        ref.write_text("{}", encoding="utf-8")
        with self.assertRaises(RuntimeError):
            build_manifest.build_manifest(str(self.payload), str(ref))

    def test_source_zip_and_frozen_resource_roots(self):
        source = (ROOT / "tools/patch_tool.py").read_bytes()
        layouts = [(self.base / "source/tools", self.base / "source/dist-additive/payload", None),
                   (self.base / "zip", self.base / "zip/payload", None),
                   (self.base / "frozen", self.base / "bundle/additive-payload", self.base / "bundle")]
        for here, payload, frozen in layouts:
            with self.subTest(layout=here.name):
                put(here / "patch_tool.py", source)
                put(payload / "fixture", b"fixture")
                root = payload.parent.parent if here.name == "tools" else (frozen or here)
                manifest = (root / "dist-additive/manifest-additive.json" if here.name == "tools"
                            else root / "manifest-additive.json")
                put(manifest, b"{}")
                spec = importlib.util.spec_from_file_location("layout_test", here / "patch_tool.py")
                module = importlib.util.module_from_spec(spec)
                with mock.patch.object(sys, "_MEIPASS", str(frozen), create=True) if frozen else ExitStack():
                    spec.loader.exec_module(module)
                self.assertEqual(Path(module.payload_dir()).resolve(), payload.resolve())
                self.assertEqual(Path(module.manifest_path()).resolve(), manifest.resolve())

    def test_generated_zip_runs_own_cli_and_checks_installed_files(self):
        font_license = self.base / "OFL.txt"
        put(font_license, b"test license")
        with mock.patch.multiple(package, PAYLOAD=str(self.payload), MANIFEST=str(self.manifest_path), OFL_SRC=str(font_license)):
            release = self.base / "FizRP-X2-v1.2.2"
            package.write_release(str(release), "1.2.2", self.manifest)
            zip_path = str(release) + ".zip"
            package.write_zip(str(release), zip_path)
            self.assertEqual(package.verify_zip(zip_path, self.manifest), [])
            unpacked = self.base / "unpacked"
            unpacked.mkdir()
            with zipfile.ZipFile(zip_path) as archive:
                self.assertTrue(all(not Path(n).is_absolute() and ".." not in Path(n).parts for n in archive.namelist()))
                archive.extractall(unpacked)
            script = unpacked / release.name / "patch_tool.py"
            env = dict(os.environ, PYTHONIOENCODING="utf-8")
            for args in (["check", "--json"],
                         ["install", "--game-dir", str(self.game), "--yes", "--no-seed-save", "--json"],
                         ["verify", "--game-dir", str(self.game), "--json"],
                         ["uninstall", "--game-dir", str(self.game), "--yes", "--json"]):
                proc = subprocess.run([sys.executable, "-B", str(script)] + args,
                                      cwd=self.base, env=env, capture_output=True, encoding="utf-8")
                self.assertEqual(proc.returncode, 0, proc.stdout + proc.stderr)
                self.assertTrue(json.loads(proc.stdout.splitlines()[-1])["ok"])
            # 仅源码/内嵌清单漂移也必须被打包检查发现。
            with zipfile.ZipFile(zip_path, "a") as archive:
                archive.writestr(release.name + "/unexpected.txt", b"unexpected")
            self.assertTrue(package.verify_zip(zip_path, self.manifest))


if __name__ == "__main__":
    unittest.main()
