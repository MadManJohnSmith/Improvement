"""Tests del runner DSH independiente de aceptación Host."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import acceptance_reviewer as ar


class FakeClient:
    authenticated = True

    def __init__(self, result_factory, *, write_result=True, running=False,
                 terminal=True, descendants=None, children=None, jobs=None,
                 cancel_running=False, cancel_descendants=None,
                 cancel_children=None, cancel_jobs=None,
                 observations=None, lifecycle_error=None):
        self.result_factory = result_factory
        self.write_result = write_result
        self.running = running
        self.terminal = terminal
        self.descendants = list(descendants or [])
        self.children = list(children or [])
        self.jobs = list(jobs or [])
        self.cancel_running = cancel_running
        self.cancel_descendants = list(cancel_descendants or [])
        self.cancel_children = list(cancel_children or [])
        self.cancel_jobs = list(cancel_jobs or [])
        self.observations = list(observations or [])
        self.lifecycle_error = lifecycle_error
        self.sessions = []
        self.prompts = []
        self.request_ids = []
        self.observation_calls = []
        self.cancel_calls = []

    def create_creator_session(self, *, workspace_path, agent_preset="cordis"):
        sid = f"session-{len(self.sessions) + 1}"
        self.sessions.append((sid, Path(workspace_path), agent_preset))
        return sid

    def send_prompt(self, session_id, prompt, request_id=None):
        self.request_ids.append(request_id)
        self.prompts.append((session_id, prompt))
        if self.write_result:
            _, workspace, _ = next(
                row for row in self.sessions if row[0] == session_id)
            payload = json.loads((workspace / "input.json").read_text())
            result = self.result_factory(payload)
            (workspace / "result.json").write_text(json.dumps(result) + "\n")
        return {"queued": True}

    def creator_observation(self, session_id, cursor=-1):
        self.observation_calls.append((session_id, cursor))
        if self.lifecycle_error is not None:
            error, self.lifecycle_error = self.lifecycle_error, None
            raise error
        if self.observations:
            return self.observations.pop(0)
        events = []
        if self.terminal:
            events = [
                {"seq": 1, "type": "turn/start", "data": {"turn": 7}},
                {"seq": 2, "type": "user/message",
                 "data": {"source": {"rpcId": self.request_ids[-1]}}},
                {"seq": 3, "type": "turn/end",
                 "data": {"turn": 7, "reason": "completed"}},
            ]
        return {
            "cursor": 3 if events else cursor,
            "events": events,
            "running": self.running,
            "descendants": self.descendants,
            "children": self.children,
            "jobs": self.jobs,
        }

    def cancel_session(self, session_id):
        self.cancel_calls.append(session_id)
        self.running = self.cancel_running
        self.descendants = self.cancel_descendants
        self.children = self.cancel_children
        self.jobs = self.cancel_jobs
        return {"accepted": True}


class AcceptanceReviewerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.run_dir = Path(self.tmp.name) / "run"
        generated = self.run_dir / "generated"
        generated.mkdir(parents=True)
        (generated / "mode.json").write_text('{"name":"x"}\n')
        self.digest = ar.tree_digest(generated)
        self.payload = {
            "generation_id": "gen-test",
            "candidate_digest": self.digest,
            "cases": [{"case_id": "A"}],
        }

    @staticmethod
    def result(payload, *, actor="host-evaluator", digest=None):
        row = {"case_id": "A", "verdict": "PASS",
               "evidence": ["candidate/mode.json"], "detail": "ok"}
        if actor == "host-evaluator":
            row["decision"] = "DENY"
        return {
            "schema_version": 1,
            "actor": actor,
            "generation_id": payload["generation_id"],
            "candidate_digest": digest or payload["candidate_digest"],
            "verdict": "PASS",
            "results": [row],
            "summary": "Todo correcto",
        }

    def test_evaluator_binds_session_candidate_and_result(self):
        client = FakeClient(lambda payload: self.result(payload))
        with ar.DshAcceptanceActors(
                self.run_dir, client=client, timeout_seconds=1) as actors:
            observed = actors.evaluate(self.payload, "evalúa")
            workspace = Path(observed["workspace"])
            self.assertEqual(observed["result"]["candidate_digest"], self.digest)
            self.assertTrue((workspace / "candidate" / "mode.json").is_file())
            self.assertEqual(client.sessions[0][2], "standard")
            self.assertTrue(client.prompts[0][1].startswith("evalúa"))
            self.assertIn("Write exactly one final JSON object", client.prompts[0][1])
            self.assertIn('"decision":"ALLOW"|"DENY"|"UNRESOLVED"',
                          client.prompts[0][1])
            self.assertFalse((workspace / "candidate" / "mode.json").stat().st_mode & 0o222)

    def test_evaluator_output_contract_enumerates_all_input_cases(self):
        payload = dict(self.payload)
        case_ids = ([f"PUBLIC-{index}" for index in range(1, 9)]
                    + [f"HOLDOUT-{index}" for index in range(1, 6)])
        payload["cases"] = [{"case_id": case_id} for case_id in case_ids]
        client = FakeClient(lambda received: self.result(received))

        with ar.DshAcceptanceActors(
                self.run_dir, client=client, timeout_seconds=1) as actors:
            actors.evaluate(payload, "evalúa")

        prompt = client.prompts[0][1]
        self.assertIn("input.json.cases requires exactly 13 result objects", prompt)
        self.assertIn(json.dumps(case_ids), prompt)
        self.assertIn("Return every listed\ncase_id exactly once", prompt)

    def test_evaluator_and_reviewer_use_distinct_sessions_and_workspaces(self):
        def factory(payload):
            actor = "host-evaluator" if len(client.prompts) == 1 else "host-independent-reviewer"
            return self.result(payload, actor=actor)
        client = FakeClient(factory)
        with ar.DshAcceptanceActors(
                self.run_dir, client=client, timeout_seconds=1) as actors:
            evaluator = actors.evaluate(self.payload, "eval")
            reviewer = actors.review(self.payload, "review")
            reviewer_root = Path(reviewer["workspace"]) / "candidate"
            self.assertNotIn('"decision":', client.prompts[1][1])
            reviewer_candidate = reviewer_root / "mode.json"
            self.assertTrue(reviewer_candidate.is_file())
            self.assertFalse(reviewer_root.stat().st_mode & 0o222)
            self.assertFalse(reviewer_candidate.stat().st_mode & 0o222)
        self.assertNotEqual(evaluator["session_id"], reviewer["session_id"])
        self.assertNotEqual(evaluator["workspace"], reviewer["workspace"])

    def test_success_waits_for_terminal_session_and_uses_stable_request_id(self):
        client = FakeClient(lambda payload: self.result(payload))
        with ar.DshAcceptanceActors(
                self.run_dir, client=client, timeout_seconds=1) as actors:
            observed = actors.evaluate(self.payload, "evalúa")
        self.assertEqual(observed["result"]["verdict"], "PASS")
        self.assertTrue(client.observation_calls)
        expected = ar.hashlib.sha256(
            f"acceptance:{self.payload['generation_id']}:{self.digest}:host-evaluator".encode()
        ).hexdigest()
        self.assertEqual(client.request_ids, [expected])

    def test_request_turn_correlation_persists_across_observations(self):
        class SplitObservationClient(FakeClient):
            def creator_observation(inner, session_id, cursor=-1):
                inner.observation_calls.append((session_id, cursor))
                if len(inner.observation_calls) == 1:
                    return {
                        "cursor": 10,
                        "events": [
                            {"seq": 10, "type": "turn/start",
                             "data": {"turn": 41}},
                        ],
                        "running": True, "descendants": [], "jobs": [],
                    }
                if len(inner.observation_calls) == 2:
                    return {
                        "cursor": 11,
                        "events": [
                            {"seq": 11, "type": "user/message",
                             "data": {"source": {
                                 "rpcId": inner.request_ids[-1]}}},
                        ],
                        "running": True, "descendants": [], "jobs": [],
                    }
                return {
                    "cursor": 14,
                    "events": [
                        {"seq": 12, "type": "turn/start",
                         "data": {"turn": 42}},
                        {"seq": 13, "type": "turn/end",
                         "data": {"turn": 42, "reason": "completed"}},
                        {"seq": 14, "type": "turn/end",
                         "data": {"turn": 41, "reason": "completed"}},
                    ],
                    "running": False, "descendants": [], "jobs": [],
                }

        client = SplitObservationClient(lambda payload: self.result(payload),
                                        running=True, terminal=False)
        with ar.DshAcceptanceActors(
                self.run_dir, client=client, timeout_seconds=1) as actors:
            observed = actors.evaluate(self.payload, "evalúa")
        self.assertEqual(observed["result"]["verdict"], "PASS")
        self.assertEqual(client.observation_calls[:3],
                         [("session-1", -1), ("session-1", 10),
                          ("session-1", 11)])
        self.assertEqual(client.cancel_calls, [])

    def test_interleaved_other_turn_end_is_not_accepted(self):
        class InterleavedClient(FakeClient):
            def creator_observation(inner, session_id, cursor=-1):
                inner.observation_calls.append((session_id, cursor))
                if inner.cancel_calls:
                    return {
                        "cursor": 4, "events": [], "running": False,
                        "descendants": [], "jobs": [],
                    }
                return {
                    "cursor": 4,
                    "events": [
                        {"seq": 1, "type": "turn/start",
                         "data": {"turn": 5}},
                        {"seq": 2, "type": "user/message",
                         "data": {"source": {
                             "rpcId": inner.request_ids[-1]}}},
                        {"seq": 3, "type": "turn/start",
                         "data": {"turn": 6}},
                        {"seq": 4, "type": "turn/end",
                         "data": {"turn": 6, "reason": "completed"}},
                    ],
                    "running": False, "descendants": [], "jobs": [],
                }

        client = InterleavedClient(lambda payload: self.result(payload),
                                   terminal=False)
        with ar.DshAcceptanceActors(
                self.run_dir, client=client, timeout_seconds=0.01) as actors:
            with self.assertRaisesRegex(ValueError, "cancelada.*running:false"):
                actors.evaluate(self.payload, "evalúa")
        self.assertEqual(client.cancel_calls, ["session-1"])

    def test_timeout_cancels_once_and_requires_running_false(self):
        client = FakeClient(lambda _payload: None, write_result=False,
                            running=True, terminal=False,
                            cancel_running=False)
        with ar.DshAcceptanceActors(
                self.run_dir, client=client, timeout_seconds=0) as actors:
            with self.assertRaisesRegex(ValueError, "cancelada.*running:false"):
                actors.evaluate(self.payload, "evalúa")
        self.assertEqual(client.cancel_calls, ["session-1"])

    def test_cancel_without_quiescence_fails_closed(self):
        client = FakeClient(lambda _payload: None, write_result=False,
                            running=True, terminal=False,
                            cancel_running=True)
        with ar.DshAcceptanceActors(
                self.run_dir, client=client, timeout_seconds=0) as actors:
            with self.assertRaisesRegex(ValueError, "no pudo confirmar cierre"):
                actors.evaluate(self.payload, "evalúa")
        self.assertEqual(client.cancel_calls, ["session-1"])
        self.assertTrue(client.observation_calls)

    def test_result_is_not_accepted_while_session_remains_running(self):
        client = FakeClient(lambda payload: self.result(payload),
                            running=True, terminal=False,
                            cancel_running=False)
        with ar.DshAcceptanceActors(
                self.run_dir, client=client, timeout_seconds=0.01) as actors:
            with self.assertRaisesRegex(ValueError, "cancelada.*running:false"):
                actors.evaluate(self.payload, "evalúa")
        self.assertTrue(client.observation_calls)
        self.assertEqual(client.cancel_calls, ["session-1"])

    def test_active_descendant_prevents_result_acceptance(self):
        client = FakeClient(
            lambda payload: self.result(payload), terminal=True,
            descendants=[{"sessionId": "grandchild-1", "running": True}],
            cancel_descendants=[])
        with ar.DshAcceptanceActors(
                self.run_dir, client=client, timeout_seconds=0.01) as actors:
            with self.assertRaisesRegex(ValueError, "cancelada.*running:false"):
                actors.evaluate(self.payload, "evalúa")
        self.assertEqual(client.cancel_calls, ["session-1"])

    def test_children_remain_compatible_when_descendants_are_absent(self):
        state = {
            "request_id": "request-1", "request_turn": None,
            "open_turn": None, "cursor": -1, "terminal": False,
        }
        observation = {
            "cursor": 3,
            "events": [
                {"seq": 1, "type": "turn/start", "data": {"turn": 7}},
                {"seq": 2, "type": "user/message",
                 "data": {"source": {"rpcId": "request-1"}}},
                {"seq": 3, "type": "turn/end",
                 "data": {"turn": 7, "reason": "completed"}},
            ],
            "running": False,
            "children": [{"sessionId": "child-1", "running": True}],
            "jobs": [],
        }
        lifecycle = ar.DshAcceptanceActors._fold_lifecycle(observation, state)
        self.assertFalse(lifecycle["quiescent"])

    def test_active_job_prevents_result_acceptance(self):
        client = FakeClient(
            lambda payload: self.result(payload), terminal=True,
            jobs=[{"jobId": "job-1", "status": "running"}],
            cancel_jobs=[])
        with ar.DshAcceptanceActors(
                self.run_dir, client=client, timeout_seconds=0.01) as actors:
            with self.assertRaisesRegex(ValueError, "cancelada.*running:false"):
                actors.evaluate(self.payload, "evalúa")
        self.assertEqual(client.cancel_calls, ["session-1"])

    def test_result_without_lifecycle_evidence_fails_closed(self):
        class LegacyClient(FakeClient):
            creator_observation = None

        client = LegacyClient(lambda payload: self.result(payload))
        with ar.DshAcceptanceActors(
                self.run_dir, client=client, timeout_seconds=0.01) as actors:
            with self.assertRaisesRegex(ValueError, "no pudo confirmar cierre"):
                actors.evaluate(self.payload, "evalúa")
        self.assertEqual(client.cancel_calls, ["session-1"])

    def test_tampered_result_does_not_cancel_proven_quiescent_session(self):
        client = FakeClient(lambda payload: self.result(payload, digest="0" * 64))
        with ar.DshAcceptanceActors(
                self.run_dir, client=client, timeout_seconds=1) as actors:
            with self.assertRaisesRegex(ValueError, "Digest"):
                actors.evaluate(self.payload, "evalúa")
        self.assertEqual(client.cancel_calls, [])

    def test_invalid_result_cancels_once_if_session_not_quiescent(self):
        client = FakeClient(lambda payload: self.result(payload, digest="0" * 64),
                            running=True, terminal=True,
                            cancel_running=False)
        with ar.DshAcceptanceActors(
                self.run_dir, client=client, timeout_seconds=0.01) as actors:
            with self.assertRaisesRegex(ValueError, "cancelada.*running:false"):
                actors.evaluate(self.payload, "evalúa")
        self.assertEqual(client.cancel_calls, ["session-1"])

    def test_wrong_actor_does_not_cancel_proven_quiescent_session(self):
        client = FakeClient(lambda payload: self.result(
            payload, actor="host-independent-reviewer"))
        with ar.DshAcceptanceActors(
                self.run_dir, client=client, timeout_seconds=1) as actors:
            with self.assertRaisesRegex(ValueError, "Actor"):
                actors.evaluate(self.payload, "evalúa")
        self.assertEqual(client.cancel_calls, [])

    def test_missing_result_after_quiescence_does_not_cancel_again(self):
        client = FakeClient(lambda _payload: None, write_result=False)
        with ar.DshAcceptanceActors(
                self.run_dir, client=client, timeout_seconds=1) as actors:
            with self.assertRaisesRegex(ValueError, "terminó sin result.json"):
                actors.evaluate(self.payload, "evalúa")
        self.assertEqual(client.cancel_calls, [])

    def test_lifecycle_error_cancels_once_before_raising(self):
        client = FakeClient(lambda payload: self.result(payload),
                            running=True, terminal=False,
                            cancel_running=False,
                            lifecycle_error=RuntimeError("follow roto"))
        with ar.DshAcceptanceActors(
                self.run_dir, client=client, timeout_seconds=1) as actors:
            with self.assertRaisesRegex(ValueError, "Error observando.*follow roto"):
                actors.evaluate(self.payload, "evalúa")
        self.assertEqual(client.cancel_calls, ["session-1"])

    def test_tree_digest_changes_with_content(self):
        before = self.digest
        (self.run_dir / "generated" / "mode.json").chmod(0o600)
        (self.run_dir / "generated" / "mode.json").write_text('{"name":"y"}\n')
        self.assertNotEqual(before, ar.tree_digest(self.run_dir / "generated"))


if __name__ == "__main__":
    unittest.main()
