"""Static check: rendered ASL JSON parses and has the expected state names."""

from __future__ import annotations

import json
from pathlib import Path
from string import Template

ASL_DIR = Path(__file__).resolve().parents[2] / "infra" / "scheduler" / "templates"


def _render(template_name: str, **template_vars: object) -> dict:
    raw = (ASL_DIR / template_name).read_text()
    # Terraform's templatefile() uses ${name} substitution; mirror that with
    # string.Template (also ${name}). Note: Terraform also supports ${expr}
    # but our templates use plain variable names, so this is enough.
    rendered = Template(raw).safe_substitute(**{k: str(v) for k, v in template_vars.items()})
    return json.loads(rendered)


def test_cron_pipeline_asl_parses() -> None:
    asl = _render(
        "cron_pipeline.asl.json",
        scraper_base_url="https://scraper.example",
        scraper_connection_arn="arn:aws:events:us-east-1:0:connection/scraper/abc",
        scheduler_lambda_arn="arn:aws:lambda:us-east-1:0:function:scheduler",
        news_digest_arn="arn:aws:lambda:us-east-1:0:function:digest",
        news_editor_arn="arn:aws:lambda:us-east-1:0:function:editor",
        news_email_arn="arn:aws:lambda:us-east-1:0:function:email",
        digest_max_concurrency=10,
        editor_max_concurrency=5,
        email_max_concurrency=2,
        scraper_poll_max_iterations=60,
    )
    assert asl["StartAt"] == "TriggerScraper"
    expected_states = {
        "TriggerScraper",
        "InitPollCount",
        "WaitForScraper",
        "PollScraper",
        "IncrementPollCount",
        "ScraperDone",
        "ScraperFailed",
        "ScraperPollTimeout",
        "ListUnsummarised",
        "DigestMap",
        "ListActiveUsers",
        "EditorMap",
        "ListNewDigests",
        "EmailMap",
    }
    assert expected_states <= set(asl["States"].keys())

    # Each Map state has the right concurrency + tolerance.
    assert asl["States"]["DigestMap"]["MaxConcurrency"] == 10
    assert asl["States"]["DigestMap"]["ToleratedFailurePercentage"] == 100
    assert asl["States"]["EditorMap"]["MaxConcurrency"] == 5
    assert asl["States"]["EmailMap"]["MaxConcurrency"] == 2

    # Scraper failure path is reachable.
    choices = asl["States"]["ScraperDone"]["Choices"]
    assert any(c.get("StringEquals") == "failed" for c in choices)

    # Iteration cap enforced.
    assert any(
        c.get("Variable") == "$.poll_count" and c.get("NumericGreaterThan") == 60 for c in choices
    )


def test_remix_user_asl_parses() -> None:
    asl = _render(
        "remix_user.asl.json",
        news_editor_arn="arn:aws:lambda:us-east-1:0:function:editor",
        news_email_arn="arn:aws:lambda:us-east-1:0:function:email",
    )
    assert asl["StartAt"] == "InvokeEditor"
    assert {"InvokeEditor", "EditorOK", "EditorFailed", "InvokeEmail"} <= set(asl["States"].keys())
    assert asl["States"]["InvokeEditor"]["Type"] == "Task"
    assert asl["States"]["EditorOK"]["Type"] == "Choice"
