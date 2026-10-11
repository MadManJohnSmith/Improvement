"""Creator token budget: real-event accounting, JSON resume and overflow.

    python3 -B -m unittest tests.test_creator_budget -v

The bug these tests pin down (DSH X1): the Creator token budget existed on
paper but was fed from nothing, and the fold that was supposed to feed it
looked for usage on the wrong records while stopping the walk at the first
record without usage. Everything here is driven by shapes measured on a real
DSH X3 trace, where usage rides on ``assistant/message`` and cache reads are
billed inside ``totalTokens``.
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import bootstrap
import creator_client as cc


def usage_event(seq, *, turn=1, inp=100, out=50, cache=0):
    """One real ``assistant/message`` record carrying usage (DSH X3 shape)."""
    return {"seq": seq, "type": "assistant/message",
            "data": {"turn": turn, "step": seq,
                     "usage": {"inputTokens": inp, "outputTokens": out,
                               "totalTokens": inp + out + cache,
                               "cacheReadTokens": cache}}}


def observation(*events, running=True, cursor=None, children=(), jobs=()):
    return {"cursor": (cursor if cursor is not None
                       else max((event.get("seq", -1) for event in events),
                                default=-1)),
            "events": list(events), "running": running,
            "children": list(children), "jobs": list(jobs)}


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.project = self.root / "project"
        self.project.mkdir()
        (self.project / "main.py").write_text("print('ok')\n")
        self.workspace = self.root / "workspace"
        result = bootstrap.install(self.project, self.workspace)
        self.run_dir = Path(result["run_dir"])
        self.gen_id = result["generation_id"]

    def fresh_state(self, *, max_tokens=500000):
        prep = cc.CreatorSession(self.run_dir).prepare()
        run_doc = json.loads((self.run_dir / "run.json").read_text())
        run_doc["budget"] = {"max_tokens": max_tokens, "max_seconds": 1800}
        cc._update_json(self.run_dir / "run.json", run_doc)
        state, created = cc._load_or_create_session_state(
            self.run_dir, prep, run_doc, now_fn=lambda: 100.0)
        self.assertTrue(created)
        return state

    def set_budget(self, max_tokens):
        run = json.loads((self.run_dir / "run.json").read_text())
        run["budget"]["max_tokens"] = max_tokens
        cc._update_json(self.run_dir / "run.json", run)

    def make_package(self):
        """Reuse the canonical valid-package fixture from the Creator tests."""
        import importlib
        module = importlib.import_module("tests.test_creator_and_validator")
        return module.CreatorTests.make_package(self)


class RealEventShapes(Base):
    """The fold must read the records DSH really emits, in feed order."""

    def test_turn_open_and_correlation_records_are_processed_before_usage(self):
        """A usage-only page never arrives alone: turn/start opens the turn,
        the user message correlates it, turn/end closes it. Filtering the walk
        at the first record without usage skipped all of them and left the
        supervisor waiting on a turn that was already over."""
        state = {"request_id": "req", "cursor": -1}
        cc._fold_observation(state, observation(
            {"seq": 1, "type": "turn/start", "data": {"turn": 4}},
            {"seq": 2, "type": "user/message",
             "data": {"turn": 4, "source": {"rpcId": "req"}}},
            usage_event(3, turn=4),
            {"seq": 4, "type": "turn/end",
             "data": {"turn": 4, "reason": "completed"}},
            running=False))
        self.assertTrue(state["terminal"])
        self.assertEqual(state["request_turn"], 4)
        self.assertEqual(state["usage_tokens"], 150)

    def test_runtime_context_and_skill_catalog_do_not_cross_correlate(self):
        """Synthetic user/message records (runtime-context, skill-catalog)
        carry no rpcId: adopting them would attribute a turn we never
        started, so a turn/end run must not be mistaken for our completion."""
        state = {"request_id": "req", "cursor": -1}
        cc._fold_observation(state, observation(
            {"seq": 1, "type": "turn/start", "data": {"turn": 1}},
            {"seq": 2, "type": "user/message",
             "data": {"turn": 1, "source": {"rpcId": "req"}}},
            {"seq": 3, "type": "user/message",
             "data": {"turn": 1, "source": {"kind": "runtime-context",
                                             "form": "snapshot",
                                             "sections": []}}},
            {"seq": 4, "type": "user/message",
             "data": {"turn": 2, "source": {"kind": "skill-catalog"}}},
            running=False))
        self.assertEqual(state["request_turn"], 1)
        # The correlated turn has not ended: nothing is terminal yet.
        self.assertFalse(state["terminal"])

    def test_usage_without_durable_seq_fails_closed(self):
        state = {"request_id": "req", "cursor": -1}
        with self.assertRaises(cc.CreatorUsageAmbiguous):
            cc._fold_observation(state, observation(
                {"type": "assistant/message",
                 "data": {"usage": {"inputTokens": 1, "outputTokens": 1,
                                    "totalTokens": 2,
                                    "cacheReadTokens": 0}}}))

    def test_assistant_record_without_usage_is_refused_not_ignored(self):
        """A turn that reports nothing cannot be counted as free."""
        state = {"request_id": "req", "cursor": -1}
        with self.assertRaises(cc.CreatorUsageAmbiguous):
            cc._fold_observation(state, observation(
                {"seq": 5, "type": "assistant/message",
                 "data": {"turn": 1, "message": {"role": "assistant"}}}))

    def test_contradictory_usage_segment_fails_closed(self):
        state = {"request_id": "req", "cursor": -1}
        for bad in ({"inputTokens": 5, "outputTokens": 5, "totalTokens": 3},
                    {"inputTokens": -1, "outputTokens": 1},
                    {"inputTokens": "10", "outputTokens": 2},
                    {"inputTokens": True, "outputTokens": 2},
                    {"inputTokens": 4, "outputTokens": 1,
                     "cacheReadTokens": -2}):
            with self.assertRaises(cc.CreatorUsageAmbiguous):
                cc._fold_observation(dict(state), observation(
                    {"seq": 9, "type": "assistant/message",
                     "data": {"turn": 1, "usage": bad}}))


class IdempotentFolding(Base):
    """One real step bills once, however many times it is re-seen."""

    def test_replayed_page_does_not_double_count(self):
        state = {"request_id": "req", "cursor": -1}
        first = [usage_event(1), usage_event(2), usage_event(3)]
        cc._fold_observation(state, observation(*first))
        self.assertEqual(state["usage_tokens"], 450)
        cc._fold_observation(state, observation(*first, usage_event(4)))
        self.assertEqual(state["usage_tokens"], 600)
        self.assertEqual(state["usage_steps"], 4)

    def test_same_seq_with_different_usage_is_refused_not_silently_preferred(self):
        """Reconciliation by silent preference would hide real spend, so the
        account refuses a step whose price changed under it."""
        state = {"request_id": "req", "cursor": -1}
        cc._fold_observation(state, observation(usage_event(1, inp=10, out=5)))
        with self.assertRaises(cc.CreatorUsageAmbiguous) as ctx:
            cc._fold_observation(state, observation(
                usage_event(1, inp=900, out=5)))
        self.assertIn("seq 1", str(ctx.exception))
        self.assertEqual(state["usage_tokens"], 15)

    def test_json_round_trip_keeps_the_account(self):
        """creator-session.json stringifies keys; the resumed state must
        still match the replayed page instead of starting a second count."""
        state = {"request_id": "req", "cursor": -1}
        cc._fold_observation(state, observation(usage_event(1), usage_event(2)))
        state = json.loads(json.dumps(state))
        cc._fold_observation(state, observation(
            usage_event(1), usage_event(3), usage_event(4)))
        self.assertEqual(state["usage_tokens"], 600)
        self.assertEqual(state["usage_steps"], 4)


class ResumedUsage(Base):
    """Resuming must not relax or restart the budget."""

    def test_resume_accepts_string_keys_from_json(self):
        state = self.fresh_state()
        cc._fold_observation(state, observation(usage_event(1, inp=300, out=100)))
        cc._save_session_state(self.run_dir, state, reason="OBSERVING")
        reloaded, created = cc._load_or_create_session_state(
            self.run_dir, cc.CreatorSession(self.run_dir).prepare(),
            json.loads((self.run_dir / "run.json").read_text()),
            now_fn=lambda: 100.0)
        self.assertFalse(created)
        self.assertEqual(reloaded["usage_tokens"], 400)

    def _run_doc(self):
        return json.loads((self.run_dir / "run.json").read_text())

    def test_resume_recomputes_totals_from_segments(self):
        run_doc = self._run_doc()
        state = self.fresh_state()
        state["usage_by_seq"] = {"7": {"inputTokens": 11, "outputTokens": 4,
                                       "cacheReadTokens": 0,
                                       "totalTokens": 15}}
        state["usage_tokens"] = 0
        reconciled = cc._reconcile_resumed_usage(state, run_doc)
        self.assertEqual(reconciled["usage_tokens"], 15)
        self.assertEqual(reconciled["usage_steps"], 1)
        self.assertEqual(reconciled["usage_cache_read_tokens"], 0)

    def test_resume_rejects_alias_keys_of_the_same_step(self):
        run_doc = self._run_doc()
        state = self.fresh_state()
        state["usage_by_seq"] = {
            "1": {"inputTokens": 1, "outputTokens": 1, "totalTokens": 2},
            "01": {"inputTokens": 2, "outputTokens": 2, "totalTokens": 4}}
        with self.assertRaises(cc.CreatorUsageAmbiguous):
            cc._reconcile_resumed_usage(state, run_doc)

    def test_resume_rejects_non_durable_keys(self):
        run_doc = self._run_doc()
        state = self.fresh_state()
        for key in (-1, True, "x", " 1", "1 "):
            with self.assertRaises(cc.CreatorUsageAmbiguous):
                cc._reconcile_resumed_usage(
                    {**state, "usage_by_seq": {
                        key: {"inputTokens": 1, "outputTokens": 1,
                              "totalTokens": 2}}}, run_doc)


class BillableDefinition(Base):
    """The budget counts what DSH actually bills."""

    def test_cache_reads_count_towards_the_budget(self):
        """X3: 76 of 79 real records report totalTokens above in + out
        because of cacheReadTokens. Summing in + out would undercount most
        of a real run and let it overrun a budget it had already spent."""
        state = {"request_id": "req", "cursor": -1}
        cc._fold_observation(state, observation(
            usage_event(1, inp=1032, out=200, cache=3072),
            usage_event(2, inp=1262, out=1506, cache=3072)))
        self.assertEqual(state["usage_tokens"], 4304 + 5840)
        self.assertEqual(state["usage_cache_read_tokens"], 6144)
        self.assertEqual(state["usage_input_tokens"], 2294)
        self.assertEqual(state["usage_output_tokens"], 1706)

    def test_budget_compares_billable_total_not_partial_spend(self):
        state = {"request_id": "req", "cursor": -1}
        cc._fold_observation(state, observation(
            usage_event(1, inp=100, out=50, cache=900)))
        # 100 + 50 is inside the limit; the billable 1050 is not.
        self.assertEqual(state["usage_input_tokens"] +
                         state["usage_output_tokens"], 150)
        self.assertEqual(state["usage_tokens"], 1050)


class FinalTurnOverflow(Base):
    """A late excess is never an ACTIVE or GENERATED attempt."""

    def _client(self, usage_events, *, cancelled=None, running=True,
                turn_events=False):
        """A DSH fake that replays the recorded pages, in feed order.

        ``turn_events=True`` closes the turn with a correlated ``turn/end``,
        so the run becomes terminal; without it the turn is still running and
        the budget gate is what must speak first.
        """
        class Client:
            authenticated = True
            observations = list(usage_events)
            request_id = None
            def create_creator_session(inner, *, workspace_path,
                                       agent_preset=None, session_id=None):
                return session_id
            def send_prompt(inner, session_id, prompt, request_id=None):
                inner.request_id = request_id
                return {"accepted": True}
            def creator_observation(inner, session_id, cursor=-1):
                if turn_events:
                    events = [
                        {"seq": 1, "type": "turn/start", "data": {"turn": 1}},
                        {"seq": 2, "type": "user/message",
                         "data": {"turn": 1,
                                  "source": {"rpcId": inner.request_id}}},
                        *(inner.observations.pop(0)
                          if inner.observations else []),
                        {"seq": 99, "type": "turn/end",
                         "data": {"turn": 1, "reason": "completed"}},
                    ]
                else:
                    events = inner.observations.pop(0) if inner.observations else []
                # A completed turn is no longer running; otherwise DSH only
                # reports quiescence once cancellation really stops it.
                live = (running and not turn_events and
                        not (cancelled and cancelled[0]))
                return observation(*events, running=live)
            def cancel_session(inner, session_id):
                if cancelled is not None:
                    cancelled[0] = True
                return {"accepted": True}
        return Client()

    def test_final_turn_over_budget_is_retained_not_accepted(self):
        """Quiescence used to be checked first, so a single turn that spent
        past max_tokens was still accepted: cancelling could not help, there
        was no later turn to cancel."""
        self.make_package()
        cancelled = [False]
        client = self._client(
            [[usage_event(1, turn=1, inp=600, out=50)]], cancelled=cancelled,
            turn_events=True)
        self.set_budget(500)
        result = cc.run_creator(
            self.run_dir, client=client, poll_seconds=0,
            cancel_grace_seconds=5, now_fn=lambda: 1000.0,
            sleep_fn=lambda _seconds: None)
        self.assertEqual(result["result"], "RETAINED")
        self.assertIn("tokens", result["reason"])
        self.assertFalse((self.run_dir / "finish.json").exists())
        run = json.loads((self.run_dir / "run.json").read_text())
        self.assertEqual(run["status"], "RETAINED")

    def test_running_session_over_budget_cancels_then_retains(self):
        cancelled = [False]
        client = self._client(
            [[usage_event(1, inp=400, out=50), usage_event(2, inp=400, out=50),
              usage_event(3, inp=400, out=50)]], cancelled=cancelled)
        self.set_budget(500)
        result = cc.run_creator(
            self.run_dir, client=client, poll_seconds=0,
            cancel_grace_seconds=5, now_fn=lambda: 1000.0,
            sleep_fn=lambda _seconds: None)
        self.assertEqual(result["result"], "RETAINED")
        self.assertTrue(cancelled[0])
        state = json.loads(
            (self.run_dir / cc.CREATOR_SESSION_FILE).read_text())
        self.assertEqual(state["usage_tokens"], 1350)

    def test_limit_is_inclusive(self):
        """At exactly max_tokens the attempt is already spent."""
        cancelled = [False]
        client = self._client([[usage_event(1, inp=250, out=250)]],
                              cancelled=cancelled)
        self.set_budget(500)
        result = cc.run_creator(
            self.run_dir, client=client, poll_seconds=0,
            cancel_grace_seconds=5, now_fn=lambda: 1000.0,
            sleep_fn=lambda _seconds: None)
        self.assertEqual(result["result"], "RETAINED")

    def test_within_budget_still_succeeds(self):
        """The reordering must not retain a run that respected the budget."""
        self.make_package()
        client = self._client([[usage_event(1, inp=100, out=50)]],
                              turn_events=True)
        result = cc.run_creator(
            self.run_dir, client=client, poll_seconds=0,
            cancel_grace_seconds=5, now_fn=lambda: 1000.0,
            sleep_fn=lambda _seconds: None)
        self.assertEqual(result["result"], "GENERATED")
        run = json.loads((self.run_dir / "run.json").read_text())
        self.assertEqual(run["status"], "GENERATED")

    def test_a_generated_rerun_without_accounting_is_not_accepted(self):
        """Immutability covers the artifacts, not the budget.

        A run marked GENERATED is returned without observing DSH, so the only
        thing that can check its spend is the persisted account. A state that
        never carried one -- written before accounting existed -- says nothing
        about the limit, and a stale total that disagrees with its own segments
        says nothing trustworthy either: both are refused instead of being read
        as a run that stayed inside the budget.
        """
        self.make_package()
        self.fresh_state(max_tokens=500)
        for recorded in (
                # No account at all: a pre-budget-era state.
                {"usage_accounted": False, "usage_by_seq": {}},
                # An account whose folded total disagrees with its segments.
                {"usage_accounted": True,
                 "usage_by_seq": {"1": {
                     "inputTokens": 400, "outputTokens": 200,
                     "cacheReadTokens": 0, "totalTokens": 600}}},
        ):
            cc._update_json(self.run_dir / cc.CREATOR_SESSION_FILE,
                            {**self._legacy_state(), **recorded})
            run = json.loads((self.run_dir / "run.json").read_text())
            run["status"] = "GENERATED"
            cc._update_json(self.run_dir / "run.json", run)
            result = cc.run_creator(
                self.run_dir, client=self._client([], cancelled=[False]),
                poll_seconds=0, cancel_grace_seconds=1,
                now_fn=lambda: 1000.0, sleep_fn=lambda _seconds: None)
            self.assertEqual(result["result"], "RETAINED", recorded)
            self.assertIn("coste real", result["reason"].lower())
            # The refusal is recorded on the run, so the Host boundary sees it.
            retained = json.loads((self.run_dir / "run.json").read_text())
            self.assertEqual(retained["status"], "RETAINED")

    def _legacy_state(self):
        """The minimum a Creator run persists before any budget existed."""
        prep = json.loads((self.run_dir / "generation-request.json").read_text())
        prep = {"generation_id": prep["generation_id"],
                "prompt_digest": prep["prompt_digest"]}
        return {
            "schema_version": cc.SCHEMA_VERSION,
            "generation_id": prep["generation_id"],
            "session_id": "session-legacy",
            "request_id": "request-legacy",
            "prompt_digest": prep["prompt_digest"],
            "deadline": 9999,
            "max_tokens": 500,
            "usage_steps": 0,
            "cursor": -1,
            "reason": "TERMINAL_QUIESCENT",
            "terminal": True,
            "quiescent": True,
        }

    def test_a_measured_generated_rerun_is_returned_unchanged(self):
        """The same rerun, with a measured account inside the limit, is not
        refused: the gate must not turn immutability into a re-litigation."""
        self.make_package()
        self.fresh_state(max_tokens=500)
        run = json.loads((self.run_dir / "run.json").read_text())
        run["status"] = "GENERATED"
        cc._update_json(self.run_dir / "run.json", run)
        cc._update_json(self.run_dir / cc.CREATOR_SESSION_FILE,
                        {**self._legacy_state(),
                        "usage_accounted": True,
                        "usage_by_seq": {"1": {
                            "inputTokens": 120, "outputTokens": 30,
                            "cacheReadTokens": 0, "totalTokens": 150}}})
        result = cc.run_creator(
            self.run_dir, client=self._client([], cancelled=[False]),
            poll_seconds=0, cancel_grace_seconds=1,
            now_fn=lambda: 1000.0, sleep_fn=lambda _seconds: None)
        self.assertEqual(result["result"], "GENERATED")

    def test_a_resume_whose_limit_disagrees_with_the_run_refuses(self):
        """A limit raised on disk must not silently relax a frozen budget.

        The state freezes the limit the run was created under. If `run.json`
        later declares a different one, whichever value wins is a guess about
        what the operator meant, and guessing upward lets a resumed run spend
        past the ceiling the operator actually set.
        """
        self.make_package()
        self.fresh_state(max_tokens=500000)
        state = json.loads((self.run_dir / cc.CREATOR_SESSION_FILE).read_text())
        run = json.loads((self.run_dir / "run.json").read_text())
        run["budget"]["max_tokens"] = 50
        cc._update_json(self.run_dir / "run.json", run)
        # The direct call refuses; through run_creator the same refusal is
        # surfaced as a retention with the reason, never as a spent turn.
        with self.assertRaises(cc.CreatorUsageAmbiguous):
            cc._reconcile_resumed_usage(state, run)
        result = cc.run_creator(
            self.run_dir, client=self._client([], cancelled=[False]),
            poll_seconds=0, cancel_grace_seconds=1,
            now_fn=lambda: 1000.0, sleep_fn=lambda _seconds: None)
        self.assertEqual(result["result"], "RETAINED")
        self.assertIn("no coincide", result["reason"])
        self.assertFalse((self.run_dir / "finish.json").is_file())

    def test_a_terminal_package_resumed_over_budget_is_not_accepted(self):
        """The path that never enters the loop is gated too.

        `run_creator` adopts a package that already went terminal and
        quiescent -- and one an earlier version finished -- without passing
        through the supervision loop's budget branch. The limit is re-checked
        on the way to GENERATED, so a persisted state cannot reach it over the
        frozen budget.
        """
        self.make_package()
        state = self.fresh_state(max_tokens=50)
        state["usage_by_seq"] = {"1": {"inputTokens": 100, "outputTokens": 50,
                                       "totalTokens": 150, "cacheReadTokens": 0}}
        state["quiescent"] = True
        state["terminal"] = True
        state["reason"] = "TERMINAL_QUIESCENT"
        cc._save_session_state(self.run_dir, state, reason="TERMINAL_QUIESCENT")
        run = json.loads((self.run_dir / "run.json").read_text())
        run["status"] = "GENERATING"
        cc._update_json(self.run_dir / "run.json", run)
        result = cc.run_creator(
            self.run_dir, client=self._client([], cancelled=[False]),
            poll_seconds=0, cancel_grace_seconds=1,
            now_fn=lambda: 1000.0, sleep_fn=lambda _seconds: None)
        self.assertEqual(result["result"], "RETAINED")
        self.assertIn("tokens", result["reason"].lower())
        self.assertFalse((self.run_dir / "finish.json").is_file())
        self.assertFalse((self.run_dir / "static-active.json").is_file())

    def test_resume_inherits_prior_spend_and_still_stops(self):
        """A run reopened after a first poll keeps its billable history."""
        cancelled = [False]
        client = self._client(
            [[usage_event(1, inp=300, out=100),
              usage_event(2, inp=200, out=100)]], cancelled=cancelled)
        self.set_budget(500)
        prep = cc.CreatorSession(self.run_dir).prepare()
        state, _ = cc._load_or_create_session_state(
            self.run_dir, prep,
            json.loads((self.run_dir / "run.json").read_text()),
            now_fn=lambda: 100.0)
        cc._fold_observation(state, observation(usage_event(1, inp=300, out=100)))
        cc._save_session_state(self.run_dir, state, reason="OBSERVING")
        result = cc.run_creator(
            self.run_dir, client=client, poll_seconds=0,
            cancel_grace_seconds=5, now_fn=lambda: 1000.0,
            sleep_fn=lambda _seconds: None)
        self.assertEqual(result["result"], "RETAINED")
        self.assertTrue(cancelled[0])
        state = json.loads(
            (self.run_dir / cc.CREATOR_SESSION_FILE).read_text())
        self.assertEqual(state["usage_tokens"], 700)
        self.assertEqual(state["usage_steps"], 2)

    def test_unquiescent_after_cancel_requires_recovery(self):
        class Client:
            authenticated = True
            def create_creator_session(inner, *, workspace_path,
                                       agent_preset=None, session_id=None):
                return session_id
            def send_prompt(inner, session_id, prompt, request_id=None):
                inner.request_id = request_id
                return {"accepted": True}
            def creator_observation(inner, session_id, cursor=-1):
                return {"cursor": cursor + 1,
                        "events": [usage_event(1, inp=900, out=900)],
                        "running": True,
                        "children": [{"sessionId": "child",
                                      "running": True}], "jobs": []}
            def cancel_session(inner, session_id):
                return {"accepted": True}

        clock = iter([1000.0, 1000.0, 1001.0, 1002.0, 1003.0, 1004.0])
        self.set_budget(100)
        result = cc.run_creator(
            self.run_dir, client=Client(), poll_seconds=0,
            cancel_grace_seconds=1, now_fn=lambda: next(clock),
            sleep_fn=lambda _seconds: None)
        self.assertEqual(result["result"], "RECOVERY_REQUIRED")
        run = json.loads((self.run_dir / "run.json").read_text())
        self.assertEqual(run["status"], "RECOVERY_REQUIRED")

    def test_ambiguous_usage_during_run_retains_rather_than_leaves_active(self):
        """A fold that cannot establish real cost must not leave the run
        ACTIVE: the run is retained with the measured ambiguity."""
        class Client:
            authenticated = True
            def create_creator_session(inner, *, workspace_path,
                                       agent_preset=None, session_id=None):
                return session_id
            def send_prompt(inner, session_id, prompt, request_id=None):
                inner.request_id = request_id
                return {"accepted": True}
            def creator_observation(inner, session_id, cursor=-1):
                return observation(
                    {"seq": 1, "type": "user/message",
                     "data": {"turn": 1,
                              "source": {"rpcId": inner.request_id}}},
                    {"seq": 2, "type": "assistant/message",
                     "data": {"turn": 1, "usage": {"inputTokens": 5}}})
            def cancel_session(inner, session_id):
                return {"accepted": True}

        result = cc.run_creator(
            self.run_dir, client=Client(), poll_seconds=0,
            now_fn=lambda: 1000.0, sleep_fn=lambda _seconds: None)
        self.assertEqual(result["result"], "RETAINED")
        self.assertIn("coste real desconocido", result["reason"])
        run = json.loads((self.run_dir / "run.json").read_text())
        self.assertNotEqual(run["status"], "GENERATING")


if __name__ == "__main__":
    unittest.main()
