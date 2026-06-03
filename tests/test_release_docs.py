from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def test_setup_docs_cover_runtime_configuration_and_safe_workflow():
    text = read("docs/setup.md")

    required = [
        "BAMBUDDY_BASE_URL",
        "BAMBUDDY_API_KEY",
        "PRINT_CONCIERGE_STATE_DB",
        "PRINT_CONCIERGE_BAMBUDDY_MANUAL_START",
        "PRINT_CONCIERGE_PUBLIC_WEB_SEARCH_ENABLED",
        "3DSEARCH",
        "archive/imported trusted",
        "Public-index results must be imported/verified",
        "uv sync",
        "uv run print-concierge search",
        "uv run print-concierge-mcp",
        "request_confirmation",
        "queue_confirmed_print",
        "do not load broad Bambuddy MCP",
    ]
    for item in required:
        assert item in text


def test_security_review_doc_records_findings_and_verification_commands():
    text = read("docs/security-review.md")

    required = [
        "Security Review",
        "No high-severity findings remain open",
        "Threat model",
        "Secrets",
        "Prompt injection",
        "Physical-device safety",
        "archive/imported trusted",
        "uv run pytest",
        "uv build",
        "Residual risks",
    ]
    for item in required:
        assert item in text


def test_github_launch_doc_contains_promotional_language():
    text = read("docs/github-launch.md")

    required = [
        "GitHub repo description",
        "Find it. Pick it. Print it.",
        "safe AI print concierge",
        "Bambuddy",
        "MakerWorld",
        "Printables",
        "import/verify public candidates",
        "Topics",
        "Launch post",
        "README hero copy",
    ]
    for item in required:
        assert item in text
