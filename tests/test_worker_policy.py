import json
import os
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import director.run as run  # noqa: E402
from director.worker import policy  # noqa: E402
from director.worker.app_server import AppServerClient  # noqa: E402


def _write_harness(root: Path, worker_policy) -> None:
    root.mkdir(parents=True, exist_ok=True)
    body = {} if worker_policy is None else {"worker_policy": worker_policy}
    (root / ".harness.json").write_text(json.dumps(body))


class LoadWorkerPolicyTest(unittest.TestCase):
    """M1 — the host policy surface: deny-by-default, fail-loud on malformed."""

    def setUp(self):
        self.root = Path(tempfile.mkdtemp())

    def test_absent_harness_json_is_deny_by_default(self):
        pol = policy.load_worker_policy(self.root)  # no .harness.json written
        self.assertEqual(pol, {"worker_env": [], "network_allowlist": [], "capabilities": []})

    def test_absent_worker_policy_key_is_empty(self):
        _write_harness(self.root, None)  # .harness.json with no worker_policy key
        self.assertEqual(policy.load_worker_policy(self.root)["worker_env"], [])

    def test_present_policy_is_parsed(self):
        _write_harness(self.root, {"worker_env": ["DATABASE_URL"],
                                   "network_allowlist": ["api.example.com"],
                                   "capabilities": ["github.create_pr"]})
        pol = policy.load_worker_policy(self.root)
        self.assertEqual(pol["worker_env"], ["DATABASE_URL"])
        self.assertEqual(pol["network_allowlist"], ["api.example.com"])
        self.assertEqual(pol["capabilities"], ["github.create_pr"])

    def test_malformed_worker_policy_not_object_raises(self):
        _write_harness(self.root, ["not", "an", "object"])
        with self.assertRaises(ValueError):
            policy.load_worker_policy(self.root)

    def test_malformed_worker_env_not_list_of_str_raises(self):
        _write_harness(self.root, {"worker_env": "DATABASE_URL"})  # str, not list
        with self.assertRaises(ValueError):
            policy.load_worker_policy(self.root)
        _write_harness(self.root, {"worker_env": [123]})  # list, not of str
        with self.assertRaises(ValueError):
            policy.load_worker_policy(self.root)


class BuildWorkerEnvTest(unittest.TestCase):
    """M2 — deny-by-default env construction (the enforcement point)."""

    def test_drops_secrets_keeps_base_and_allowlisted(self):
        src = {"PATH": "/bin", "HOME": "/h", "LC_ALL": "C", "LC_SECRET": "sneaky",
               "ALLOWED": "ok", "LINEAR_API_KEY": "sk-secret", "SENTINEL_SECRET": "leak"}
        env = policy.build_worker_env({"worker_env": ["ALLOWED"]}, src)
        self.assertIn("PATH", env)          # base name
        self.assertIn("HOME", env)          # base name
        self.assertIn("LC_ALL", env)        # enumerated locale name
        self.assertIn("ALLOWED", env)       # host-allowlisted
        self.assertNotIn("LINEAR_API_KEY", env)
        self.assertNotIn("SENTINEL_SECRET", env)
        self.assertNotIn("LC_SECRET", env)  # NOT prefix-matched (fail-open fix): an
        #                                     LC_<anything> credential must be dropped

    def test_empty_policy_drops_everything_but_base(self):
        env = policy.build_worker_env({"worker_env": []},
                                      {"PATH": "/bin", "AWS_SECRET_ACCESS_KEY": "x"})
        self.assertEqual(env, {"PATH": "/bin"})


class SpawnEnvIsolationTest(unittest.TestCase):
    """M2 acceptance — a real spawned subprocess does NOT inherit a host secret.

    Encodes the enforced property: before this change `Popen` had no `env=`, so a
    child inherited the full parent env (SENTINEL_SECRET would leak in); the deny-by-
    default construction now passed to `Popen(env=...)` keeps it out."""

    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())

    def test_popen_env_excludes_secret(self):
        out = self.tmp / "child_env.json"
        cmd = [sys.executable, "-c",
               "import os,json,sys,pathlib;"
               "pathlib.Path(sys.argv[1]).write_text(json.dumps(dict(os.environ)))",
               str(out)]
        prior = os.environ.get("SENTINEL_SECRET")
        os.environ["SENTINEL_SECRET"] = "leakme"
        try:
            env = policy.build_worker_env(policy.load_worker_policy(self.tmp))
            client = AppServerClient(cmd, cwd=self.tmp, env=env)
            client.start()
            client._proc.wait(timeout=10)
            client.stop()  # close the stdio pipes
        finally:
            if prior is None:
                os.environ.pop("SENTINEL_SECRET", None)
            else:
                os.environ["SENTINEL_SECRET"] = prior
        child_env = json.loads(out.read_text())
        self.assertNotIn("SENTINEL_SECRET", child_env)  # the secret did NOT leak in
        self.assertIn("PATH", child_env)                # base still present → child runnable

    def test_prepare_defaults_to_deny_by_default_env(self):
        # _prepare with worker_env=None must construct the boundary itself (secure by
        # construction — every real entry point flows through here).
        prior = os.environ.get("SENTINEL_SECRET")
        os.environ["SENTINEL_SECRET"] = "leakme"
        try:
            client = run._prepare(
                {"id": "T", "prompt": "p", "workspace": str(self.tmp / "ws")},
                command=[sys.executable, "-c", "pass"], queue_base=self.tmp / "q",
                workspace_root=self.tmp / "wsroot", timeout_s=5, read_timeout_s=5,
                tool_executor=None, install_skills=False)
        finally:
            if prior is None:
                os.environ.pop("SENTINEL_SECRET", None)
            else:
                os.environ["SENTINEL_SECRET"] = prior
        self.assertIsNotNone(client.env)
        self.assertNotIn("SENTINEL_SECRET", client.env)
        self.assertIn("PATH", client.env)


if __name__ == "__main__":
    unittest.main()
