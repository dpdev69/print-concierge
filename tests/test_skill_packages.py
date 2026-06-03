import json
import re
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]

REQUIRED_FILES = [
    "skills/print-concierge/SKILL.md",
    "skills/print-concierge/references/workflow.md",
    "skills/print-concierge/references/safety.md",
    "skills/print-concierge/agents/openai.yaml",
    "packages/claude/SKILL.md",
    "packages/claude/claude_desktop_config.example.json",
    "packages/codex/print-concierge/SKILL.md",
    "packages/hermes/skill.yaml",
    "packages/hermes/handler.js",
    "packages/openclaw/print-concierge/SKILL.md",
    "docs/installable-skills.md",
]

PACKAGE_PATHS = [
    "skills/print-concierge",
    "packages/claude",
    "packages/codex",
    "packages/hermes",
    "packages/openclaw",
    "docs/installable-skills.md",
]

SECRET_PATTERNS = [
    re.compile(r"sk-[A-Za-z0-9_-]{20,}"),
    re.compile(r"ghp_[A-Za-z0-9]{20,}"),
    re.compile(r"xox[baprs]-[A-Za-z0-9-]{20,}"),
    re.compile(r"AKIA[0-9A-Z]{16}"),
    re.compile(r"-----BEGIN (?:RSA |OPENSSH |EC |DSA )?PRIVATE KEY-----"),
    re.compile(r"(?i)(api[_-]?key|token|secret|password)\s*[:=]\s*['\"]?(?!<|\\$\\{|YOUR_|your_|BAMBUDDY_API_KEY|env:)[A-Za-z0-9_./+=-]{12,}"),
]


def read(path: str) -> str:
    return (ROOT / path).read_text(encoding="utf-8")


def package_texts():
    for package_path in PACKAGE_PATHS:
        path = ROOT / package_path
        if path.is_file():
            yield package_path, path.read_text(encoding="utf-8")
            continue
        for file_path in sorted(path.rglob("*")):
            if file_path.is_file():
                yield str(file_path.relative_to(ROOT)), file_path.read_text(encoding="utf-8")


def test_required_skill_package_files_exist():
    missing = [path for path in REQUIRED_FILES if not (ROOT / path).is_file()]

    assert missing == []
    assert not (ROOT / "skills/print-concierge/README.md").exists()


def test_canonical_skill_has_frontmatter_and_progressive_references():
    skill = read("skills/print-concierge/SKILL.md")

    assert skill.startswith("---\n")
    assert "name: print-concierge" in skill
    assert "description:" in skill
    assert "references/workflow.md" in skill
    assert "references/safety.md" in skill
    assert len(skill.splitlines()) <= 80


def test_skill_packages_contain_core_safety_instructions():
    combined = "\n".join(text for _, text in package_texts()).lower()

    required_phrases = [
        "explicit user confirmation",
        "backend",
        "scoped",
        "queue_print_request",
        "raw queue",
        "exact print job",
        "untrusted",
        "do not expose",
        "least privilege",
        "no direct start",
        "bambuddy credentials",
        "get_public_import_status",
        "import_public_candidate",
    ]

    for phrase in required_phrases:
        assert phrase in combined


def test_skill_packages_include_mcp_command_examples():
    claude_config = json.loads(read("packages/claude/claude_desktop_config.example.json"))
    docs = read("docs/installable-skills.md")
    combined = "\n".join(text for _, text in package_texts())

    assert claude_config["mcpServers"]["print-concierge"]["command"] == "uv"
    assert "print-concierge-mcp" in claude_config["mcpServers"]["print-concierge"]["args"]
    assert "uv run print-concierge-mcp" in combined
    assert "print-concierge-mcp" in docs
    assert "mcpServers" in combined


def test_host_specific_shims_reference_canonical_skill_and_tools():
    expected = {
        "packages/claude/SKILL.md": ["../../skills/print-concierge/SKILL.md", "list_printers", "import_public_candidate", "queue_print_request"],
        "packages/codex/print-concierge/SKILL.md": ["../../../skills/print-concierge/SKILL.md", "create_print_request", "queue_print_request"],
        "packages/hermes/skill.yaml": ["../../skills/print-concierge/SKILL.md", "get_print_request_status", "queue_print_request"],
        "packages/openclaw/print-concierge/SKILL.md": ["../../../skills/print-concierge/SKILL.md", "search_archive_or_models", "queue_print_request"],
    }

    for path, snippets in expected.items():
        text = read(path)
        for snippet in snippets:
            assert snippet in text


def test_skill_packages_do_not_advertise_unimplemented_tools():
    combined = "\n".join(text for _, text in package_texts())

    assert "pause_print" not in combined
    assert "cancel_print" not in combined
    assert "queue_confirmed_print" not in combined
    assert "request_confirmation" not in combined


def test_skill_package_files_do_not_contain_secret_values():
    for path, text in package_texts():
        for pattern in SECRET_PATTERNS:
            assert pattern.search(text) is None, f"{path} matches {pattern.pattern}"
