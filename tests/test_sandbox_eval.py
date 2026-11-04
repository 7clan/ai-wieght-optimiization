import unittest

from tinycoder.sandbox_eval import docker_command


class SandboxCommandTests(unittest.TestCase):
    def test_container_does_not_get_host_network_or_writes(self):
        command = docker_command("/safe/eval", "tinycoder-test")
        self.assertIn("none", command)
        self.assertIn("--read-only", command)
        self.assertIn("no-new-privileges", command)
        self.assertIn("--cap-drop", command)
        self.assertIn("--memory", command)
        self.assertIn("65534:65534", command)
        self.assertIn("type=bind,src=/safe/eval,dst=/work,readonly", command)


if __name__ == "__main__":
    unittest.main()

