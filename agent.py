"""
WAT Orchestrator — reads a workflow markdown file, extracts the tool sequence,
and calls each tool script in order, passing accumulated state forward.
"""

import re
import importlib.util
import sys
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

TOOL_DIR = Path(__file__).parent / "tools"

# Maps tool references in workflow steps to tool module filenames
TOOL_ALIASES = {
    "fetch_booking":               "fetch_booking",
    "create_calendar_event":       "create_calendar_event",
    "update_calendar_event":       "update_calendar_event",
    "delete_calendar_event":       "delete_calendar_event",
    "create_drive_folder":         "create_drive_folder",
    "upload_to_drive":             "upload_to_drive",
    "send_email":                  "send_email",
    "update_booking_record":       "update_booking_record",
    "fetch_pending_reminders":     "fetch_pending_reminders",
    "sync_file_to_drive":          "sync_file_to_drive",
    "generate_quote_pdf":          "generate_quote_pdf",
    "upload_quote_to_drive":       "upload_quote_to_drive",
    "fetch_quote_pdf_from_drive":  "fetch_quote_pdf_from_drive",
    "fetch_application":           "fetch_application",
    "score_resume":                "score_resume",
    "update_candidate_record":     "update_candidate_record",
    "create_interview_calendar_event": "create_interview_calendar_event",
    "update_interview_slot":       "update_interview_slot",
}


def load_workflow(workflow_name: str) -> str:
    path = Path(__file__).parent / "workflows" / f"{workflow_name}.md"
    if not path.exists():
        raise FileNotFoundError(f"Workflow not found: {path}")
    return path.read_text()


def parse_steps(workflow_text: str) -> list[dict]:
    """
    Parses numbered steps from the ## Steps section of a workflow markdown.
    Each step must reference a tool in the format: → tools/tool_name.py
    Returns a list of { step_num, description, tool, extra_payload }
    """
    steps = []
    in_steps = False

    for line in workflow_text.splitlines():
        line = line.strip()

        if line.startswith("## Steps"):
            in_steps = True
            continue
        if in_steps and line.startswith("## "):
            break  # End of Steps section
        if not in_steps:
            continue

        # Match numbered step lines: "1. Do something → tools/tool_name.py"
        match = re.match(r"^\d+\.\s+(.+)", line)
        if not match:
            continue

        content = match.group(1)
        tool_match = re.search(r"→\s+tools/(\w+)\.py", content)
        template_match = re.search(r"\(template:\s*(\w+)\)", content)

        if not tool_match:
            continue

        tool_name = tool_match.group(1)
        extra: dict = {}
        if template_match:
            extra["template"] = template_match.group(1)

        steps.append({"description": content, "tool": tool_name, "extra": extra})

    return steps


def import_tool(tool_name: str):
    module_path = TOOL_DIR / f"{tool_name}.py"
    if not module_path.exists():
        raise FileNotFoundError(f"Tool not found: {module_path}")

    spec = importlib.util.spec_from_file_location(tool_name, module_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_workflow(workflow_name: str, payload: dict) -> dict:
    """
    Execute a named workflow with the given initial payload.
    Returns the final accumulated payload after all steps complete.
    """
    logger.info(f"[agent] Starting workflow: {workflow_name}")

    workflow_text = load_workflow(workflow_name)
    steps = parse_steps(workflow_text)

    if not steps:
        logger.warning(f"[agent] No tool steps parsed from workflow: {workflow_name}")
        return payload

    state = dict(payload)

    for i, step in enumerate(steps, 1):
        tool_name = step["tool"]
        logger.info(f"[agent] Step {i}: {step['description']}")

        # Merge any extra params from step (e.g. template name for send_email)
        step_payload = {**state, **step["extra"]}

        try:
            tool = import_tool(tool_name)
            result = tool.run(step_payload)
            if isinstance(result, dict):
                state.update(result)
            logger.info(f"[agent] Step {i} complete: {result}")
        except Exception as e:
            logger.error(f"[agent] Step {i} FAILED ({tool_name}): {e}")
            # Non-fatal for certain tools; re-raise to let main.py decide retry logic
            raise

    logger.info(f"[agent] Workflow complete: {workflow_name}")
    return state
