import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import director.worker.authority as auth  # noqa: E402


class ClassifyTest(unittest.TestCase):
    def test_named_query_is_read(self):
        op = auth.classify_operation("query Q($id: String!) { issue(id: $id) { id } }")
        self.assertEqual(op["kind"], "query")
        self.assertTrue(op["parse_ok"])

    def test_anonymous_selection_is_query(self):
        op = auth.classify_operation("{ issues { nodes { id } } }")
        self.assertEqual(op["kind"], "query")

    def test_mutation_root_field_extracted(self):
        op = auth.classify_operation(
            'mutation M($id: String!) { issueUpdate(id: $id, input: { stateId: "s" }) { success } }')
        self.assertEqual(op["kind"], "mutation")
        self.assertEqual(op["root_fields"], ("issueUpdate",))
        self.assertTrue(op["parse_ok"])

    def test_object_value_braces_do_not_break_depth(self):
        # nested object value inside args must NOT be read as a selection set
        op = auth.classify_operation(
            "mutation { issueUpdate(input: { a: { b: 1 } }) { issue { id } } }")
        self.assertEqual(op["root_fields"], ("issueUpdate",))

    def test_multiple_root_fields(self):
        op = auth.classify_operation("mutation { commentCreate(input:{}) { id } issueUpdate(id:1) { id } }")
        self.assertEqual(op["root_fields"], ("commentCreate", "issueUpdate"))

    def test_subscription_detected(self):
        op = auth.classify_operation("subscription S { issues { id } }")
        self.assertEqual(op["kind"], "subscription")

    def test_unbalanced_braces_not_parse_ok(self):
        self.assertFalse(auth.classify_operation("mutation { issueUpdate(id:1) { id } ")["parse_ok"])

    def test_empty_is_unknown(self):
        self.assertEqual(auth.classify_operation("   ")["kind"], "unknown")


class EvasionTest(unittest.TestCase):
    """R4/R5 — the classifier sees the same document the server lexer sees."""

    def test_alias_does_not_hide_field(self):
        op = auth.classify_operation('mutation { safe: issueDelete(id: "x") { success } }')
        self.assertEqual(op["root_fields"], ("issueDelete",))

    def test_keyword_in_comment_ignored(self):
        # the '# mutation issueDelete' comment must not turn a read into a mutation
        op = auth.classify_operation("# mutation issueDelete\nquery { issues { id } }")
        self.assertEqual(op["kind"], "query")

    def test_keyword_and_braces_in_string_ignored(self):
        op = auth.classify_operation(
            'mutation { commentCreate(input: { body: "mutation { issueDelete } }" }) { id } }')
        self.assertEqual(op["kind"], "mutation")
        self.assertEqual(op["root_fields"], ("commentCreate",))

    def test_block_string_ignored(self):
        op = auth.classify_operation(
            'mutation { commentCreate(input: { body: """ } issueDelete { """ }) { id } }')
        self.assertEqual(op["root_fields"], ("commentCreate",))

    def test_mutation_field_under_query_classifies_as_read(self):
        # a mutation field invoked in a query operation cannot execute server-side
        op = auth.classify_operation("{ issueDelete(id: 1) { success } }")
        self.assertEqual(op["kind"], "query")

    def test_fragment_spread_at_mutation_root_is_unresolved(self):
        op = auth.classify_operation("mutation { ...Frag }")
        self.assertFalse(op["parse_ok"])  # cannot resolve the real mutation field -> deny

    def test_inner_field_named_mutation_not_an_operation(self):
        op = auth.classify_operation("query { mutation { id } }")
        self.assertEqual(op["kind"], "query")

    def test_directive_at_root_not_collected_as_field(self):
        op = auth.classify_operation("mutation { issueUpdate(id:1) @include(if: true) { id } }")
        self.assertEqual(op["root_fields"], ("issueUpdate",))


class AuthorizeTest(unittest.TestCase):
    def test_read_allowed(self):
        self.assertTrue(auth.authorize("query { issues { nodes { id } } }")["allowed"])

    def test_anonymous_read_allowed(self):
        self.assertTrue(auth.authorize("{ issues { id } }")["allowed"])

    def test_allowlisted_mutation_allowed(self):
        self.assertTrue(auth.authorize('mutation { issueUpdate(id:"x", input:{stateId:"s"}) { success } }')["allowed"])

    def test_destructive_mutation_denied_and_named(self):
        out = auth.authorize('mutation { issueDelete(id: "x") { success } }')
        self.assertFalse(out["allowed"])
        self.assertIn("issueDelete", out["reason"])

    def test_mixed_mutation_denied_if_any_blocked(self):
        out = auth.authorize("mutation { issueUpdate(id:1){id} issueArchive(id:2){id} }")
        self.assertFalse(out["allowed"])
        self.assertIn("issueArchive", out["reason"])

    def test_subscription_denied(self):
        self.assertFalse(auth.authorize("subscription { issues { id } }")["allowed"])

    def test_unparseable_denied(self):
        self.assertFalse(auth.authorize("mutation { issueUpdate(id:1) {")["allowed"])

    def test_unknown_denied(self):
        self.assertFalse(auth.authorize("")["allowed"])

    def test_custom_allowlist_overrides(self):
        # a tighter allowlist refuses what the default would allow
        out = auth.authorize("mutation { issueUpdate(id:1){id} }",
                             allow_mutations=frozenset({"commentCreate"}))
        self.assertFalse(out["allowed"])
        self.assertIn("issueUpdate", out["reason"])


class DefaultAllowlistTest(unittest.TestCase):
    def test_default_allowlist_is_the_worker_set(self):
        self.assertEqual(auth.DEFAULT_MUTATION_ALLOWLIST, frozenset({
            "issueCreate", "issueUpdate", "commentCreate", "commentUpdate",
            "issueRelationCreate", "attachmentLinkURL", "attachmentLinkGitHubPR",
            "fileUpload"}))

    def test_every_default_mutation_authorizes(self):
        for m in auth.DEFAULT_MUTATION_ALLOWLIST:
            self.assertTrue(auth.authorize("mutation { %s(input:{}) { success } }" % m)["allowed"], m)


if __name__ == "__main__":
    unittest.main()
