from __future__ import annotations

from datetime import datetime
from pathlib import Path
import sys
import asyncio
import importlib
from collections.abc import Callable

from fastapi.testclient import TestClient

BASE_DIR = Path(__file__).resolve().parents[1]
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from app_main import app  # noqa: E402
from tests.golden.runner import dump_markdown_report, run_all_cases, to_dict_rows  # noqa: E402


def _ensure_langchain_debug_compat() -> None:
    try:
        langchain = importlib.import_module("langchain")
    except ImportError:
        return
    if not hasattr(langchain, "debug"):
        setattr(langchain, "debug", False)
    if not hasattr(langchain, "verbose"):
        setattr(langchain, "verbose", False)


def _install_fake_llm_for_golden() -> None:
    conftest_module = importlib.import_module("tests.conftest")
    fake_client = conftest_module._FakeLLMClient()
    fake_getter: Callable[[], object] = lambda: fake_client

    service_llm_client_module = importlib.import_module("service.llm.client")
    setattr(service_llm_client_module, "get_llm_client", fake_getter)
    setattr(service_llm_client_module, "llm_client", fake_client)
    setattr(service_llm_client_module, "_module_llm_client", fake_client)

    patch_targets = [
        "agents.nodes.supervisor",
        "agents.nodes.analyst",
        "agents.nodes.writer",
        "agents.subgraphs.researcher",
        "service.qa.engine",
        "service.skill_curator.generators.qa_rule",
        "service.skill_curator.generators.prompt_template",
        "service.skill_curator.generators.source_routing",
        "agents.tools.extract_structured",
    ]
    for module_name in patch_targets:
        module = importlib.import_module(module_name)
        setattr(module, "get_llm_client", fake_getter)


def main() -> int:
    _ensure_langchain_debug_compat()
    if sys.platform == "win32":
        asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())
    _install_fake_llm_for_golden()
    base_dir = BASE_DIR
    cases_dir = base_dir / "tests" / "golden" / "cases"
    report_name = f"golden_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    report_path = base_dir.parents[1] / "docs" / "private" / report_name
    with TestClient(app) as client:
        results = run_all_cases(cases_dir=cases_dir, client=client)
    dump_markdown_report(results=results, report_path=report_path)
    rows = to_dict_rows(results)
    passed = sum(1 for item in rows if bool(item["passed"]))
    print(f"golden_eval_passed={passed}/{len(rows)}")
    print(f"golden_eval_report={report_path}")
    return 0 if passed == len(rows) else 1


if __name__ == "__main__":
    raise SystemExit(main())

