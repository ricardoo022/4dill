"""Tests for the Generator Eval Runner CLI (US-047).

Covers:
  - CLI flag parsing (--agent, --subset, --no-upload, --runs)
  - Dataset loading and subset filtering
  - Local run execution with evaluator integration
  - Metrics printing output
  - E2E: full CLI subprocess with real Generator LLM (requires OPENAI_API_KEY)
"""

import os
import subprocess
import sys
from pathlib import Path

import pytest

from tests.evals.evaluators import subtask_plan_valid
from tests.evals.run_agent_eval import (
    _build_arg_parser,
    _load_examples,
    _print_metrics,
    _run_local,
)

RUNNER_PATH = Path(__file__).parent / "run_agent_eval.py"
REPO_ROOT = Path(__file__).resolve().parents[2]

# Realistic stub plan for SQL injection lab
_STUB_SUBTASKS = [
    {
        "title": "Enumerate login endpoint parameters",
        "description": (
            "Run ffuf against the login form at "
            "https://portswigger.net/web-security/sql-injection/lab-login-bypass "
            "to enumerate hidden parameters and input fields."
        ),
        "fase": "fase-3",
    },
    {
        "title": "Test SQL injection in username and password fields",
        "description": (
            "Probe the login form with SQL injection payloads such as ' OR '1'='1'-- "
            "and admin'-- to identify injectable fields and bypass authentication."
        ),
        "fase": "fase-3",
    },
    {
        "title": "Exploit SQL injection to achieve login bypass",
        "description": (
            "Use a crafted SQL payload in the username field to authenticate as admin "
            "without a valid password, confirming the SQL injection vulnerability."
        ),
        "fase": "fase-3",
    },
]

_STUB_OUTPUT = {"subtasks": _STUB_SUBTASKS, "count": len(_STUB_SUBTASKS)}


def _target_ok(inputs: dict) -> dict:  # noqa: ARG001
    return _STUB_OUTPUT


def _target_fail(inputs: dict) -> dict:  # noqa: ARG001
    raise RuntimeError("OPENAI_API_KEY not set")


# ---------------------------------------------------------------------------
# 1. CLI help
# ---------------------------------------------------------------------------


class TestHelp:
    def test_help_flag_shows_required_flags(self):
        """Tests Required: --help must expose --agent, --subset, --no-upload, --runs."""
        result = subprocess.run(
            [sys.executable, str(RUNNER_PATH), "--help"],
            capture_output=True,
            text=True,
            env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
        )
        assert result.returncode == 0
        assert "--agent" in result.stdout
        assert "--subset" in result.stdout
        assert "--no-upload" in result.stdout
        assert "--runs" in result.stdout


# ---------------------------------------------------------------------------
# 2. Argument parsing
# ---------------------------------------------------------------------------


class TestArgumentParsing:
    def test_argument_parsing_generator_quick_no_upload(self):
        """AC#1-3: --agent generator --subset quick --no-upload all parse correctly."""
        args = _build_arg_parser().parse_args(
            ["--agent", "generator", "--subset", "quick", "--no-upload"]
        )
        assert args.agent == "generator"
        assert args.subset == "quick"
        assert args.no_upload is True

    def test_argument_parsing_defaults(self):
        """AC#2 default subset=quick; AC#3 default no_upload=False; runs=1."""
        args = _build_arg_parser().parse_args(["--agent", "generator"])
        assert args.subset == "quick"
        assert args.no_upload is False
        assert args.runs == 1

    def test_argument_agent_choices_rejects_unknown(self):
        """Failure path: --agent orchestrator must be rejected with SystemExit."""
        with pytest.raises(SystemExit):
            _build_arg_parser().parse_args(["--agent", "orchestrator"])


# ---------------------------------------------------------------------------
# 3. Dataset loading
# ---------------------------------------------------------------------------


class TestLoadExamples:
    def test_load_examples_quick_returns_four_labs(self):
        """🔁 AC#2: _load_examples('quick') returns exactly 4 examples with correct lab IDs."""
        examples = _load_examples("quick")
        assert len(examples) == 4

        expected_ids = {
            "sqli-login-bypass",
            "xss-reflected-html-nothing-encoded",
            "auth-username-enum-different-responses",
            "xxe-file-upload",
        }
        assert {ex["inputs"]["lab_id"] for ex in examples} == expected_ids

    def test_load_examples_quick_all_have_required_inputs(self):
        """Each example must have required input fields and a valid PortSwigger HTTPS URL."""
        examples = _load_examples("quick")
        required = [
            "lab_id",
            "lab_url",
            "expected_vulnerability",
            "expected_backend_type",
            "fase_phase",
        ]
        for ex in examples:
            inp = ex["inputs"]
            for field in required:
                assert field in inp, f"Missing '{field}' in inputs for {inp.get('lab_id')}"
            assert inp["lab_url"].startswith("https://portswigger.net"), (
                f"Unexpected lab_url: {inp['lab_url']}"
            )

    def test_load_examples_unknown_subset_exits(self):
        """Failure path: unknown subset must raise SystemExit(1)."""
        with pytest.raises(SystemExit) as exc_info:
            _load_examples("nonexistent")
        assert exc_info.value.code == 1


# ---------------------------------------------------------------------------
# 4. Local run execution
# ---------------------------------------------------------------------------


class TestRunLocal:
    def test_run_local_collects_evaluator_scores(self):
        """🔁 AC#4: _run_local with valid stub returns score 1.0 for every quick example."""
        examples = _load_examples("quick")
        results = _run_local(_target_ok, examples, [subtask_plan_valid], runs=1)

        assert len(results) == len(examples)
        for r in results:
            assert r["error"] is None, f"Unexpected error for {r['lab_id']}: {r['error']}"
            assert r["scores"].get("subtask_plan_valid") == 1.0, (
                f"Expected score 1.0 for {r['lab_id']}, got {r['scores']}"
            )

    def test_run_local_multiple_runs(self):
        """runs=2 produces 2 × len(examples) result records."""
        examples = _load_examples("quick")
        results = _run_local(_target_ok, examples, [subtask_plan_valid], runs=2)
        assert len(results) == len(examples) * 2

    def test_run_local_handles_target_exception(self):
        """Failure path: raising target stores error string; runner does not crash; score 0.0."""
        examples = [_load_examples("quick")[0]]  # sqli-login-bypass only
        results = _run_local(_target_fail, examples, [subtask_plan_valid], runs=1)

        assert len(results) == 1
        r = results[0]
        assert r["error"] == "OPENAI_API_KEY not set"
        assert r["output"] == {}
        assert r["scores"].get("subtask_plan_valid") == 0.0


# ---------------------------------------------------------------------------
# 5. Metrics printing
# ---------------------------------------------------------------------------


class TestPrintMetrics:
    _RESULTS = [
        {
            "lab_id": "sqli-login-bypass",
            "run": 1,
            "output": _STUB_OUTPUT,
            "error": None,
            "scores": {"subtask_plan_valid": 1.0},
            "elapsed_s": 2.3,
        },
        {
            "lab_id": "xss-reflected-html-nothing-encoded",
            "run": 1,
            "output": {"subtasks": [], "count": 0},
            "error": None,
            "scores": {"subtask_plan_valid": 0.5},
            "elapsed_s": 1.8,
        },
    ]

    def test_print_metrics_shows_final_score(self, capsys):
        """AC#4: _print_metrics must print 'Final score', evaluator name, avg/pass-rate, and 0.750."""
        _print_metrics(self._RESULTS, agent="generator", subset="quick")
        out = capsys.readouterr().out

        assert "Final score" in out, f"'Final score' missing:\n{out}"
        assert "subtask_plan_valid" in out, f"Evaluator name missing:\n{out}"
        assert "avg score" in out, f"'avg score' missing:\n{out}"
        assert "pass rate" in out, f"'pass rate' missing:\n{out}"
        # avg(1.0, 0.5) = 0.75 → formatted as 0.750
        assert "0.750" in out, f"Expected 0.750 in output:\n{out}"


# ---------------------------------------------------------------------------
# 6. E2E: full CLI subprocess with real Generator LLM
# ---------------------------------------------------------------------------


@pytest.mark.e2e
class TestRunnerE2E:
    def test_runner_executes_generator_quick_no_upload(self):
        """Tests Required: `--agent generator --subset quick --no-upload` executes end-to-end.

        Requires OPENAI_API_KEY. Runs the full Generator agent against all 4 quick-subset
        labs and asserts the runner exits 0 and prints a final score.
        """
        assert os.environ.get("OPENAI_API_KEY"), "OPENAI_API_KEY must be set to run e2e runner test"

        result = subprocess.run(
            [
                sys.executable,
                str(RUNNER_PATH),
                "--agent",
                "generator",
                "--subset",
                "quick",
                "--no-upload",
            ],
            capture_output=True,
            text=True,
            timeout=300,
            cwd=str(REPO_ROOT),
            env={**os.environ, "PYTHONPATH": str(REPO_ROOT)},
        )

        assert result.returncode == 0, (
            f"Runner exited {result.returncode}.\n"
            f"STDOUT:\n{result.stdout}\nSTDERR:\n{result.stderr}"
        )
        assert "Final score" in result.stdout, (
            f"'Final score' not in output.\nSTDOUT:\n{result.stdout}"
        )
        assert "subtask_plan_valid" in result.stdout, (
            f"Evaluator metric missing.\nSTDOUT:\n{result.stdout}"
        )
        assert "sqli-login-bypass" in result.stdout, (
            f"Expected lab ID 'sqli-login-bypass' in output.\nSTDOUT:\n{result.stdout}"
        )
