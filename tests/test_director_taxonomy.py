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

    def test_impl_prompt_gates_once_not_repeatedly(self):
        # F2 context hygiene: the impl worker runs the FULL gate once near completion and
        # iterates with targeted checks — not the whole 685-test gate after every edit.
        out = tax.compose_worker_prompt({"identifier": "X-8", "prompt": "build it",
                                         "labels": ["impl"]})
        low = out.lower()
        self.assertIn("gate cadence", low)
        self.assertIn("targeted", low)
        self.assertIn("once near", low)
        self.assertIn("check.py", out)               # the full gate is still named

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

    def test_child_types_describe_size_split_edge(self):
        # ADR 0004: decomposition is the EXCEPTION (a genuine size split), not a routine
        # per-stage pipeline. child_types describes the size-split edge — a split
        # sub-project starts its own pipeline (spec), planning may recurse, impl splits
        # into impl (only when a build is too large for one plan).
        self.assertEqual(tax.TAXONOMY["planning"]["child_types"], ["spec", "planning"])
        self.assertEqual(tax.TAXONOMY["design"]["child_types"], ["spec"])
        self.assertEqual(tax.TAXONOMY["spec"]["child_types"], ["spec"])
        self.assertEqual(tax.TAXONOMY["research"]["child_types"], [])
        self.assertEqual(tax.TAXONOMY["impl"]["child_types"], ["impl"])
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
        self.assertIn("impl", out)                   # names impl children (now conditional)
        self.assertIn("X-2", out)                    # blocked_by this ticket
        self.assertIn("auth spec", out)              # original task preserved
        self.assertIn("TASK:", out)

    def test_spec_prompt_continues_in_ticket_not_mandatory_handoff(self):
        # ADR 0004: a spec worker continues the build in the SAME ticket; it creates impl
        # children only on a genuine size split, not as a mandatory per-stage hand-off.
        out = tax.compose_worker_prompt({"identifier": "X-2", "prompt": "auth spec",
                                         "labels": ["spec"]})
        low = out.lower()
        self.assertIn("continue in this same ticket", low)
        self.assertIn("independently shippable", low)            # split only on genuine size
        self.assertIn("execplan", low)                           # continues into the build
        self.assertIn("only when", low)                          # child creation is gated
        self.assertNotIn("then create impl child", low)          # mandatory hand-off gone

    def test_design_prompt_continues_in_ticket(self):
        # ADR 0004 symmetry: the design worker also carries the pipeline forward in-ticket,
        # spawning a spec child only when the design splits into shippable sub-projects.
        out = tax.compose_worker_prompt({"identifier": "X-D", "prompt": "shape it",
                                         "labels": ["design"]})
        low = out.lower()
        self.assertIn("continue in this same ticket", low)
        self.assertIn("independently shippable", low)

    def test_impl_prompt_syncs_base_and_resets_on_wrong_approach(self):
        # ADR 0004 / Symphony WORKFLOW.md parity: sync the base to origin/main before
        # substantial work (recorded evidence), and treat an approach-rejected rework as a
        # RESET (close PR, fresh branch, fresh plan), not an incremental patch.
        out = tax.compose_worker_prompt({"identifier": "X-9", "prompt": "build it",
                                         "labels": ["impl"]})
        low = out.lower()
        self.assertIn("origin/main", out)        # sync-before-work + reset both target it
        self.assertIn("sync", low)
        self.assertIn("approach", low)           # approach-rejected rework
        self.assertIn("reset", low)
        self.assertIn("branch fresh", low)       # fresh branch from origin/main
        self.assertIn("fresh execplan", low)     # and a fresh plan

    def test_impl_prompt_references_execplan(self):
        out = tax.compose_worker_prompt({"identifier": "X-3", "prompt": "build it",
                                         "labels": ["impl"]})
        self.assertIn("execplan", out)
        self.assertIn("docs/exec-plans/", out)
        self.assertIn("check.py", out)

    def test_impl_prompt_includes_self_qa_and_pr_procedure(self):
        # M1 (worker-qa) + Slice 4 R4.3: the impl worker still self-QAs INLINE (spec/code
        # self-review + task-specific tests) and opens a PR with a self-description before
        # done — a procedure, not a gate (spec R1/R2/D-46). The standalone `qa` workspace
        # skill was RETIRED (redundant with the execplan completion gate the worker runs);
        # the discipline stays inline, so the prompt no longer points at a separate qa skill.
        out = tax.compose_worker_prompt({"identifier": "X-5", "prompt": "build it",
                                         "labels": ["impl"]})
        self.assertIn("SELF-QA", out)
        self.assertIn("task-specific tests", out)  # the self-QA test discipline, inline
        self.assertIn("PR", out)                    # open a PR with a self-description
        self.assertIn("report_outcome(done)", out)
        self.assertNotIn("`qa` skill", out)         # retired — no standalone qa-skill pointer

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

    def test_impl_sweep_outputs_structured_evidence_and_resolves_threads(self):
        # merge-preservation M1 (R4): the sweep step now instructs explicit thread
        # resolution (a reply alone does not resolve) and ties report_outcome's structured
        # evidence (checks_state / unresolved_threads / acceptance_verified) to the sweep's
        # result, while flagging that the merger re-verifies independently.
        out = tax.compose_worker_prompt({"identifier": "X-7", "prompt": "fix it",
                                         "labels": ["impl"]})
        low = out.lower()
        self.assertIn("resolve each review thread", low)   # explicit thread resolution
        self.assertIn("checks_state", out)                 # structured evidence fields
        self.assertIn("unresolved_threads", out)
        self.assertIn("acceptance_verified", out)
        self.assertIn("re-verifies", low)                  # merger independently re-verifies

    def test_planning_prompt_decomposes_into_subprojects(self):
        # ADR 0004: planning decomposes a large goal into INDEPENDENTLY SHIPPABLE
        # sub-projects (each its own pipeline), NOT into per-stage children — otherwise it
        # would contradict WORKER_PROTOCOL's "do not split a ticket by stage".
        out = tax.compose_worker_prompt({"identifier": "X-4", "prompt": "ship feature",
                                         "labels": ["planning"]})
        low = out.lower()
        self.assertIn("decompose", low)
        self.assertIn("independently shippable", low)   # by sub-project, not stage
        self.assertIn("sub-project", low)
        self.assertNotIn("right next stage", low)       # the old per-stage framing is gone
        self.assertIn("AGENTS.md", out)


if __name__ == "__main__":
    unittest.main()
