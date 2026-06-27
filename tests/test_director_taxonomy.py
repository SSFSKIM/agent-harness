import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import director.taxonomy as tax  # noqa: E402


class TerminalContractTest(unittest.TestCase):
    def test_contract_names_report_outcome_and_three_statuses(self):
        c = tax.TERMINAL_CONTRACT
        self.assertIn("report_outcome", c)
        for status in ("done", "blocked", "needs_human"):
            self.assertIn(status, c)
        # it must NOT tell the worker to use report_outcome to ask about continuing
        self.assertIn("Do NOT call report_outcome to ask whether to continue", c)

    def test_with_terminal_contract_appends_to_prompt(self):
        out = tax.with_terminal_contract("do the thing")
        self.assertTrue(out.startswith("do the thing"))
        self.assertIn("report_outcome", out)
        self.assertIn("TURN PROTOCOL", out)


class WorkerProtocolTest(unittest.TestCase):
    """The stage-agnostic WORKER PROTOCOL preamble + the single first-turn framing
    seam (graduated-autonomy slice 1, spec R1/R2/R3 + regression R8)."""

    def test_preamble_names_the_two_cross_stage_disciplines(self):
        p = tax.WORKER_PROTOCOL.lower()
        # (1) single living source-of-truth, maintained in place, not scattered
        self.assertIn("source of truth", p)
        self.assertIn("in place", p)
        # (2) no scope-creep -> file a typed child ticket
        self.assertIn("scope", p)
        self.assertIn("child", p)

    def test_preamble_names_single_board_progress_comment(self):
        # slice 2b: ONE canonical board comment, stable marker, edit-in-place not a second
        p = tax.WORKER_PROTOCOL
        self.assertIn("## 🤖 Worker Progress", p)   # the stable find-or-create marker
        low = p.lower()
        self.assertIn("one comment", low)            # single, not fragmented
        self.assertIn("commentcreate", low)
        self.assertIn("commentupdate", low)

    def test_preamble_says_worker_proposes_state_not_sets_it(self):
        # slice 2c reinforcement at the prompt level: the worker never transitions state
        low = tax.WORKER_PROTOCOL.lower()
        self.assertIn("report_outcome", low)
        self.assertIn("issueupdate", low)            # named as not-the-worker's

    def test_preamble_names_proportional_context_discipline(self):
        # F2 (use-all shakedown): orient only as much as the ticket needs (nav is a tool,
        # not a forced step) AND keep context lean (don't re-carry large logs) — the
        # turn-cost lever. A focused change must not survey the whole repo.
        low = tax.WORKER_PROTOCOL.lower()
        self.assertIn("proportional context", low)
        self.assertIn("docs-nav", low)               # nav offered as an on-demand tool
        self.assertIn("re-sent context", low)         # names the dominant cost

    def test_protocol_carries_gate_cadence(self):
        # F2 context hygiene, now in WORKER_PROTOCOL (ADR 0005, host-AGNOSTIC — no hardcoded
        # gate command): full gate once near completion, targeted checks while iterating.
        low = tax.WORKER_PROTOCOL.lower()
        self.assertIn("once near completion", low)
        self.assertIn("targeted", low)
        self.assertIn("host's gate", low)            # generic, not a baked-in `check.py`

    def test_preamble_states_two_trigger_self_contained_issuance(self):
        # ADR 0004: a ticket is a purpose unit; a worker issues a NEW ticket on exactly
        # two triggers (genuine size split / surfaced deferred work incl. in-scope tech
        # debt), and every issued ticket is self-contained (provenance + title + desc +
        # acceptance) so a fresh worker can start from it alone.
        low = tax.WORKER_PROTOCOL.lower()
        self.assertIn("two triggers", low)
        self.assertIn("independently shippable", low)   # the genuine-size trigger
        self.assertIn("tech debt", low)                 # in-scope deferred work
        self.assertIn("acceptance criteria", low)       # self-contained contract
        self.assertIn("provenance", low)                # link parent + source doc
        self.assertIn("self-contained", low)
        # ADR 0007: an issued child must carry the agent-ready dispatch label or the
        # orchestrator's gate will never pick it up.
        self.assertIn("agent-ready", low)

    def test_frame_first_turn_carries_both_blocks_in_order(self):
        out = tax.frame_first_turn("do the thing")
        self.assertTrue(out.startswith("do the thing"))      # prompt comes first
        self.assertIn("WORKER PROTOCOL", out)                # operating disciplines
        self.assertIn("TURN PROTOCOL", out)                  # terminal contract (delegated)
        self.assertIn("report_outcome", out)
        # WORKER PROTOCOL precedes TURN PROTOCOL (spec ordering)
        self.assertLess(out.index("WORKER PROTOCOL"), out.index("TURN PROTOCOL"))

    def test_with_terminal_contract_is_byte_unchanged_by_the_new_seam(self):
        # R8 strict: the new seam delegates to an UNTOUCHED with_terminal_contract,
        # so framing only the terminal block still yields exactly the old shape.
        out = tax.with_terminal_contract("x")
        self.assertNotIn("WORKER PROTOCOL", out)             # it adds only TURN PROTOCOL
        self.assertIn("TURN PROTOCOL", out)


class ImplCraftInProtocolTest(unittest.TestCase):
    """ADR 0005: the implementation craft folded from the retired _IMPL_TEMPLATE now lives in
    WORKER_PROTOCOL (conditional 'when you implement'), so it reaches every worker via
    frame_first_turn on both dispatch paths — host-AGNOSTIC (no execplan/check.py path)."""

    def setUp(self):
        self.raw = tax.WORKER_PROTOCOL
        self.low = self.raw.lower()

    def test_reproduce_sync_acceptance_revert(self):
        self.assertIn("reproduce", self.low)            # reproduction-first
        self.assertIn("origin/main", self.raw)          # sync-before-work
        self.assertIn("validation", self.low)           # acceptance mirroring (ticket section)
        self.assertIn("non-negotiable", self.low)
        self.assertIn("revert", self.low)               # temp proof revert
        self.assertIn("proof", self.low)
        # the RECORDING obligations must survive the fold (codex P2): record reproduction,
        # mirror acceptance as checkboxes, note the proof edit — all in the working doc.
        self.assertIn("working doc", self.low)
        self.assertIn("checkboxes", self.low)
        # host-agnostic: no baked-in methodology path
        self.assertNotIn("plugin/skills/execplan", self.raw)
        self.assertNotIn("check.py", self.raw)

    def test_self_qa_and_pr_self_description(self):
        self.assertIn("self-qa", self.low)
        self.assertIn("task-specific tests", self.low)
        self.assertIn("push", self.low)                 # open the PR with the push skill
        self.assertIn("report_outcome(done)", self.raw)

    def test_pr_feedback_sweep_with_structured_evidence(self):
        self.assertIn("feedback sweep", self.low)
        self.assertIn("inline", self.low)               # all channels incl. inline review
        self.assertIn("resolve", self.low)              # explicit thread resolution
        self.assertIn("checks_state", self.raw)         # structured report_outcome evidence
        self.assertIn("unresolved_threads", self.raw)
        self.assertIn("acceptance_verified", self.raw)
        self.assertIn("re-verifies", self.low)          # merger re-verifies independently

    def test_rework_reset_path(self):
        self.assertIn("approach", self.low)             # approach-rejected rework
        self.assertIn("reset", self.low)
        self.assertIn("branch fresh", self.low)         # fresh branch from origin/main
        self.assertIn("already attached", self.low)     # on-arrival (PR already attached)


if __name__ == "__main__":
    unittest.main()
