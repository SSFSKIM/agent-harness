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


class RegistryTest(unittest.TestCase):
    def test_all_five_types_present(self):
        self.assertEqual(set(tax.TAXONOMY), {"planning", "research", "design", "spec", "impl"})

    def test_each_entry_has_required_fields(self):
        for name, entry in tax.TAXONOMY.items():
            for field in ("label", "stage", "methodology_refs", "output",
                          "child_types", "template"):
                self.assertIn(field, entry, f"{name} missing {field}")
            self.assertEqual(entry["label"], name)  # label == type name (D-19)

    def test_child_types_form_pipeline(self):
        # planning -> {research,design,spec}; design -> spec; spec -> impl; leaves are leaves
        self.assertEqual(set(tax.TAXONOMY["planning"]["child_types"]),
                         {"research", "design", "spec"})
        self.assertEqual(tax.TAXONOMY["design"]["child_types"], ["spec"])
        self.assertEqual(tax.TAXONOMY["spec"]["child_types"], ["impl"])
        self.assertEqual(tax.TAXONOMY["research"]["child_types"], [])
        self.assertEqual(tax.TAXONOMY["impl"]["child_types"], [])
        # every child type is itself a known type
        for entry in tax.TAXONOMY.values():
            for c in entry["child_types"]:
                self.assertIn(c, tax.TAXONOMY)


class TicketTypeTest(unittest.TestCase):
    def test_type_from_single_label(self):
        self.assertEqual(tax.ticket_type({"labels": ["spec"]}), "spec")

    def test_untyped_when_no_stage_label(self):
        self.assertIsNone(tax.ticket_type({"labels": ["Feature", "Bug"]}))
        self.assertIsNone(tax.ticket_type({}))

    def test_multi_label_resolves_by_priority(self):
        # carries both spec and impl -> routes to the most specific (latest) stage: impl
        self.assertEqual(tax.ticket_type({"labels": ["spec", "impl"]}), "impl")
        self.assertEqual(tax.ticket_type({"labels": ["planning", "design"]}), "design")


class ComposePromptTest(unittest.TestCase):
    def test_untyped_returns_raw_prompt(self):
        ticket = {"identifier": "X-1", "prompt": "do the thing", "labels": []}
        self.assertEqual(tax.compose_worker_prompt(ticket), "do the thing")

    def test_spec_prompt_references_product_design_and_children(self):
        ticket = {"identifier": "X-2", "prompt": "auth spec", "labels": ["spec"]}
        out = tax.compose_worker_prompt(ticket)
        self.assertIn("product-design", out)         # methodology ref
        self.assertIn("docs/product-specs/", out)    # output path
        self.assertIn("impl", out)                   # decomposes into impl children
        self.assertIn("X-2", out)                    # blocked_by this ticket
        self.assertIn("auth spec", out)              # original task preserved
        self.assertIn("TASK:", out)

    def test_impl_prompt_references_execplan(self):
        out = tax.compose_worker_prompt({"identifier": "X-3", "prompt": "build it",
                                         "labels": ["impl"]})
        self.assertIn("execplan", out)
        self.assertIn("docs/exec-plans/", out)
        self.assertIn("check.py", out)

    def test_impl_prompt_includes_self_qa_and_pr_procedure(self):
        # M1: the impl worker is guided to self-QA (spec/code/tests) and open a PR with a
        # self-description before done — a procedure, not a gate (spec R1/R2/D-46).
        out = tax.compose_worker_prompt({"identifier": "X-5", "prompt": "build it",
                                         "labels": ["impl"]})
        self.assertIn("SELF-QA", out)
        self.assertIn("qa", out)            # references the qa skill
        self.assertIn("PR", out)            # open a PR with a self-description
        self.assertIn("report_outcome(done)", out)

    def test_impl_prompt_includes_the_four_operating_disciplines(self):
        # M2 (slice 1, gap #5): the impl worker is guided through reproduction-first
        # (R4), acceptance mirroring (R5), temp-proof revert (R6), and the PR feedback
        # sweep — pre-handoff + on-arrival (R7).
        out = tax.compose_worker_prompt({"identifier": "X-6", "prompt": "fix it",
                                         "labels": ["impl"]})
        low = out.lower()
        self.assertIn("reproduce", low)                 # R4 reproduction-first
        self.assertIn("validation", low)                # R5 ticket-provided section
        self.assertIn("non-negotiable", low)            # R5 mirrored as non-negotiable
        self.assertIn("revert", low)                    # R6 temp proof edits reverted
        self.assertIn("proof", low)                     # R6
        self.assertIn("feedback sweep", low)            # R7 PR feedback sweep
        self.assertIn("inline", low)                    # R7 all channels incl. inline review
        self.assertIn("already attached", low)          # R7 on-arrival path
        # the existing self-QA + PR block must remain intact (worker-qa spec)
        self.assertIn("SELF-QA", out)
        self.assertIn("report_outcome(done)", out)

    def test_planning_prompt_decomposes(self):
        out = tax.compose_worker_prompt({"identifier": "X-4", "prompt": "ship feature",
                                         "labels": ["planning"]})
        self.assertIn("Decompose", out)
        self.assertIn("AGENTS.md", out)


if __name__ == "__main__":
    unittest.main()
