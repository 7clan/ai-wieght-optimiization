"""Session014 contracts that do not execute any model-generated code."""

import json
import unittest
from pathlib import Path

from tinycoder.session014 import (ALPHAS, DOCKER_MBPP, DOCKER_WEB, MODEL_ID,
                                  TRACKS, docker_command, select_mbpp, measure)
from tinycoder.session014_fixtures import (make_reference_trajectories, make_web_tasks,
                                           sha256_json)


class FrozenDataTests(unittest.TestCase):
    def test_exact_counts_and_disjoint_test_source(self):
        web, source = make_web_tasks(), make_reference_trajectories()
        self.assertEqual((len(web),len(source)),(50,50))
        self.assertEqual(len(set(x["prompt"] for x in web+source)),100)
        self.assertEqual(len({x["task_id"] for x in web+source}),100)
        self.assertEqual([x["mode"] for x in web].count("ui"),25)
        self.assertEqual([x["mode"] for x in web].count("backend"),25)
        self.assertEqual([x["mode"] for x in source].count("ui"),25)
        self.assertEqual([x["mode"] for x in source].count("backend"),25)
        for task in web+source:
            self.assertTrue(task["reference"].startswith(task["prompt"]))
            self.assertTrue(task["name"] in task["prompt"])
        self.assertEqual(sha256_json(web),sha256_json(make_web_tasks()))

    def test_previous_100_mbpp_task_ids_are_excluded(self):
        data=json.loads(Path("data/session014_excluded_mbpp_ids.json").read_text())
        self.assertEqual(len(set(data["ids"])),100)
        plus={f"Mbpp/{i}":{"task_id":f"Mbpp/{i}","prompt":f"function p{i}"} for i in range(11,300)}
        original={str(i):{} for i in range(11,300)}
        chosen=select_mbpp(plus,original,[],data["ids"],count=50)
        self.assertFalse(set(x["task_id"] for x in chosen)&set(data["ids"]))


class SandboxTests(unittest.TestCase):
    def test_docker_isolation_for_both_languages(self):
        for web,image in ((True,DOCKER_WEB),(False,DOCKER_MBPP)):
            with self.subTest(web=web):
                cmd=docker_command(image,Path("/tmp/s014-in"),Path("/tmp/s014-out"),"isolated",web)
                self.assertIn(image,cmd)
                self.assertEqual(cmd[cmd.index("--network")+1],"none")
                self.assertEqual(cmd[cmd.index("--user")+1],"65534:65534")
                for flag in ("--read-only","--cap-drop","--pids-limit","--memory","--cpus"):
                    self.assertIn(flag,cmd)

    def test_no_model_capacity_change(self):
        self.assertEqual(MODEL_ID,"Qwen/Qwen2.5-Coder-0.5B")
        self.assertEqual(ALPHAS,(0.25,0.75,1.25))
        self.assertEqual(len(TRACKS),8)


class ScoringTests(unittest.TestCase):
    def test_taxonomy_exclusive(self):
        rows=[{"task_id":f"WebUI/{i}","failure_bin":"passed" if i < 2 else "assertion_error",
               "syntax_valid":True,"passed":i < 2} for i in range(5)]
        stats=measure(rows)
        self.assertEqual(stats["execution_passes"],2)
        self.assertEqual(stats["syntax_valid"],5)
        rows[3]["failure_bin"]="passed"
        with self.assertRaises(ValueError):
            measure(rows)


if __name__=="__main__":
    unittest.main()
