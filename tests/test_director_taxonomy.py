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

    def test_planning_prompt_decomposes(self):
        out = tax.compose_worker_prompt({"identifier": "X-4", "prompt": "ship feature",
                                         "labels": ["planning"]})
        self.assertIn("Decompose", out)
        self.assertIn("AGENTS.md", out)


if __name__ == "__main__":
    unittest.main()
