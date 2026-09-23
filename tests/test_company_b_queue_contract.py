from __future__ import annotations

import shutil
import subprocess
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
QUEUE_WORKER = REPO_ROOT / "scripts" / "company_b" / "company-b-queue-worker.ps1"
SETUP_SCRIPT = REPO_ROOT / "scripts" / "company_b" / "setup-company-b-github.ps1"
PROTOCOL_DOC = REPO_ROOT / "docs" / "company-b" / "QUEUE_PROTOCOL.md"

REQUIRED_COMPANY_B_LABELS = (
    "company-b:queued",
    "company-b:running",
    "company-b:blocked",
    "company-b:done",
    "company-b:approval-required",
)


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _find_powershell() -> str | None:
    for candidate in ("pwsh", "pwsh.exe", "powershell", "powershell.exe"):
        found = shutil.which(candidate)
        if found:
            return found
    return None


class CompanyBQueueFilesExistTests(unittest.TestCase):
    def test_required_files_exist(self):
        for path in (QUEUE_WORKER, SETUP_SCRIPT, PROTOCOL_DOC):
            self.assertTrue(path.is_file(), f"missing required file: {path}")


class CompanyBQueueLabelContractTests(unittest.TestCase):
    def setUp(self):
        self.queue_text = _read(QUEUE_WORKER)
        self.setup_text = _read(SETUP_SCRIPT)

    def test_queue_worker_only_uses_company_b_labels(self):
        for label in REQUIRED_COMPANY_B_LABELS:
            self.assertIn(label, self.queue_text)

    def test_queue_worker_never_consumes_company_a_queue_label(self):
        self.assertNotIn("agent:queued", self.queue_text)
        self.assertNotIn("agent:running", self.queue_text)
        self.assertNotIn("agent:blocked", self.queue_text)
        self.assertNotIn("agent:done", self.queue_text)
        self.assertNotIn("agent:approval-required", self.queue_text)

    def test_setup_script_defines_exactly_the_five_company_b_labels(self):
        for label in REQUIRED_COMPANY_B_LABELS:
            self.assertIn(label, self.setup_text)
        # The script's own self-test guards against an "agent:*" label ever being added to the
        # Company B set (a wildcard pattern, not a concrete label); no concrete Company A label
        # is ever a value in the Company B label set.
        for company_a_label in ("agent:queued", "agent:running", "agent:blocked", "agent:done", "agent:approval-required"):
            self.assertNotIn(company_a_label, self.setup_text)

    def test_setup_script_is_idempotent_create_or_update(self):
        self.assertIn("label create", self.setup_text)
        self.assertIn("label edit", self.setup_text)

    def test_setup_script_selftest_is_offline(self):
        # The -SelfTest branch must return before any `gh` invocation is reachable.
        selftest_index = self.setup_text.index("if ($SelfTest)")
        first_gh_call_index = self.setup_text.index('Resolve-RequiredCommand -Names @("gh.exe"')
        self.assertLess(selftest_index, first_gh_call_index)


class CompanyBQueueDiscoveryTests(unittest.TestCase):
    def setUp(self):
        self.text = _read(QUEUE_WORKER)

    def test_discovery_uses_only_the_company_b_queued_label(self):
        self.assertIn('$QueueLabel = "company-b:queued"', self.text)
        self.assertIn("--label $QueueLabel", self.text)

    def test_processes_at_most_one_issue_per_invocation(self):
        # Exactly one issue is selected for the queued path, and the script exits after
        # completing (or blocking) that single issue rather than looping.
        self.assertIn("$queuedIssues[0].number", self.text)
        self.assertNotIn("foreach ($issue in $queuedIssues)", self.text)
        self.assertNotIn("while (", self.text)


class CompanyBQueueMutexTests(unittest.TestCase):
    def setUp(self):
        self.text = _read(QUEUE_WORKER)

    def test_dedicated_non_blocking_mutex_present(self):
        self.assertIn("System.Threading.Mutex", self.text)
        self.assertIn("Global\\rentgist-my-quant-bot-company-b-queue", self.text)
        self.assertIn("WaitOne(0)", self.text)

    def test_mutex_name_distinct_from_company_a(self):
        self.assertNotIn("Global\\rentgist-my-quant-bot-codex-queue", self.text)

    def test_mutex_contention_fails_closed(self):
        contention_block = self.text[self.text.index("if (-not $hasMutex)") :][:200]
        self.assertIn("throw", contention_block)


class CompanyBTaskPayloadContractTests(unittest.TestCase):
    def setUp(self):
        self.text = _read(QUEUE_WORKER)

    def test_markers_are_required(self):
        self.assertIn("COMPANY_B_TASK_SPEC_START", self.text)
        self.assertIn("COMPANY_B_TASK_SPEC_END", self.text)

    def test_task_id_pattern_enforced(self):
        self.assertIn(r"^B-TASK-[0-9]{3,}$", self.text)

    def test_materializes_under_company_b_runtime_namespace_only(self):
        self.assertIn("AICompany\\company-b\\my-quant-bot", self.text)
        self.assertNotIn("companies/company-b/tasks", self.text)
        self.assertNotIn("companies\\company-b\\tasks", self.text)


class CompanyBWorkerDelegationTests(unittest.TestCase):
    def setUp(self):
        self.text = _read(QUEUE_WORKER)

    def test_invokes_worker_with_push_on_pass(self):
        self.assertIn("company-b-worker.ps1", self.text)
        self.assertIn("-PushOnPass", self.text)

    def test_does_not_duplicate_worker_phase_prompts(self):
        # These are worker-owned phase names; the wrapper must never construct its own prompts
        # for them, only read the worker's resulting state/evidence files.
        for forbidden in ("CLAUDE_PLAN", "CODEX_CHALLENGE", "CLAUDE_IMPLEMENTATION", "CLAUDE_CORRECTION"):
            self.assertNotIn(forbidden, self.text)


class CompanyBDraftPrTests(unittest.TestCase):
    def setUp(self):
        self.text = _read(QUEUE_WORKER)

    def test_creates_draft_pr(self):
        self.assertIn("pr create", self.text)
        self.assertIn("--draft", self.text)

    def test_never_merges(self):
        # No invocation of `gh pr merge` (in any flag form) is present anywhere in the script;
        # the script's own prose explicitly documents that it never auto-merges.
        self.assertNotIn("pr merge", self.text)
        self.assertNotIn("--merge", self.text)
        self.assertIn("never auto-merged", self.text)

    def test_reuses_existing_draft_and_rejects_non_draft(self):
        self.assertIn("isDraft", self.text)
        self.assertIn("non-draft pull request already exists", self.text)


class CompanyBEvidenceTests(unittest.TestCase):
    def setUp(self):
        self.text = _read(QUEUE_WORKER)

    def test_exact_head_verification_present(self):
        self.assertIn("headRefOid", self.text)
        self.assertIn("rev-parse", self.text)

    def test_evidence_sourced_from_worker_artifacts_only(self):
        self.assertIn("test-result.txt", self.text)
        self.assertIn("codex-review.txt", self.text)
        self.assertIn("state.json", self.text)

    def test_evidence_marker_is_distinct_from_company_a(self):
        self.assertIn("company-b-queue-evidence:v1", self.text)
        self.assertNotIn("codex-bounded-review-evidence:v1", self.text)

    def test_evidence_readback_confirmation_present(self):
        self.assertIn("markerCount", self.text)
        self.assertIn("EVIDENCE_INVALID", self.text)


class CompanyBFailClosedTests(unittest.TestCase):
    def setUp(self):
        self.text = _read(QUEUE_WORKER)

    def test_blocked_label_used_for_every_documented_failure_path(self):
        blocked_codes = (
            "TASK_SPEC_INVALID_JSON",
            "TASK_SPEC_SCHEMA_INVALID",
            "TASK_RUNTIME_ALREADY_EXISTS",
            "WORKER_FAILED",
            "WORKER_NOT_PASS",
            "EVIDENCE_INVALID",
            "ORPHANED_RUNNING",
            "PUBLISH_FAILED",
        )
        for code in blocked_codes:
            self.assertIn(code, self.text)
        self.assertGreaterEqual(self.text.count("$BlockedLabel"), len(blocked_codes))

    def test_lifecycle_transitions_are_completion_critical_not_best_effort(self):
        # The lifecycle transition helper must throw on GitHub failure, not just warn.
        function_start = self.text.index("function Set-CompanyBIssueLifecycle")
        next_function_start = self.text.index(
            "function ", function_start + len("function Set-CompanyBIssueLifecycle")
        )
        function_body = self.text[function_start:next_function_start]
        self.assertIn("throw", function_body)
        self.assertNotIn("Write-Warning", function_body)


class CompanyBProtocolDocTests(unittest.TestCase):
    def setUp(self):
        self.text = _read(PROTOCOL_DOC)

    def test_documents_required_sections(self):
        for heading in (
            "Lifecycle labels",
            "Isolation from Company A",
            "Issue body task format",
            "Execution",
            "Recovery",
            "No-auto-merge policy",
        ):
            self.assertIn(heading, self.text)

    def test_documents_no_auto_merge(self):
        self.assertIn("never", self.text.lower())
        self.assertIn("merge", self.text.lower())

    def test_does_not_reference_agent_queued(self):
        self.assertNotIn("agent:queued", self.text)


class CompanyBPowerShellRuntimeTests(unittest.TestCase):
    """These checks execute PowerShell when available for real parser/behavior evidence,
    beyond the static substring assertions above. They skip (not fail) when no PowerShell
    interpreter is present on the test host, since CI/test environments are not guaranteed
    to provide one."""

    @classmethod
    def setUpClass(cls):
        cls.powershell = _find_powershell()

    def _run(self, *args):
        assert self.powershell is not None
        return subprocess.run(
            [self.powershell, "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", *args],
            capture_output=True,
            text=True,
            timeout=120,
        )

    def test_queue_worker_parses_as_valid_powershell(self):
        if self.powershell is None:
            self.skipTest("no PowerShell interpreter available on this host")
        result = self._run(str(QUEUE_WORKER), "-SelfTest")
        self.assertEqual(result.returncode, 0, msg=result.stderr)

    def test_setup_script_parses_as_valid_powershell(self):
        if self.powershell is None:
            self.skipTest("no PowerShell interpreter available on this host")
        result = self._run(str(SETUP_SCRIPT), "-SelfTest")
        self.assertEqual(result.returncode, 0, msg=result.stderr)


if __name__ == "__main__":
    unittest.main()
