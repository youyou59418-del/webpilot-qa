from __future__ import annotations

from copy import deepcopy
from typing import Any, Literal, Protocol

from webpilot.browser.observation import BrowserObservation

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationError,
    model_validator,
)


RiskLevel = Literal["L0", "L1", "L2", "L3"]

RuleType = Literal[
    "url_contains",
    "visible_text_contains",
    "element_text_equals",
]


# ``element_text_equals`` is verified against ObservationEngine.elements,
# which deliberately contains only actionable controls.  Keeping the accepted
# roles explicit prevents a plan from claiming that a non-observed heading or
# dialog title was semantically verified.
OBSERVABLE_ELEMENT_ROLES = frozenset({
    "button",
    "link",
    "textbox",
    "combobox",
    "checkbox",
    "radio",
    "switch",
    "tab",
    "menuitem",
    "option",
    "slider",
    "spinbutton",
    "listbox",
    "treeitem",
})


class SuccessCriterion(BaseModel):
    model_config = ConfigDict(extra="forbid")

    rule: RuleType

    expected: str = Field(
        min_length=1,
    )

    element_role: str | None = None
    element_name: str | None = None

    @model_validator(mode="after")
    def validate_element_rule(
        self,
    ) -> "SuccessCriterion":
        if self.rule == "element_text_equals":
            if not self.element_role or not self.element_name:
                raise ValueError(
                    "element_text_equals requires both "
                    "element_role and element_name"
                )
            if self.element_role not in OBSERVABLE_ELEMENT_ROLES:
                raise ValueError(
                    "element_text_equals only supports actionable roles "
                    "exposed by ObservationEngine.elements"
                )

        return self


class PlanStep(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str = Field(
        pattern=r"^step_[1-9][0-9]*$"
    )

    goal: str = Field(
        min_length=1,
    )

    success_criteria: list[SuccessCriterion] = Field(
        min_length=1,
    )

    risk_level: RiskLevel = "L0"


class TestPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")

    steps: list[PlanStep] = Field(
        min_length=1,
    )

    @model_validator(mode="after")
    def validate_step_ids(
        self,
    ) -> "TestPlan":
        ids = [
            step.id
            for step in self.steps
        ]

        if len(ids) != len(set(ids)):
            raise ValueError(
                "PlanStep ids must be unique"
            )

        expected_ids = [
            f"step_{index}"
            for index in range(1, len(ids) + 1)
        ]
        if ids != expected_ids:
            raise ValueError(
                "PlanStep ids must be consecutive and ordered: "
                "step_1, step_2, ..."
            )

        return self


PLAN_TOOL_SCHEMA: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "submit_test_plan",
        "description": (
            "Submit the final structured browser test plan."
        ),
        "parameters": {
            "type": "object",
            "additionalProperties": False,
            "properties": {
                "steps": {
                    "type": "array",
                    "minItems": 1,
                    "items": {
                        "type": "object",
                        "additionalProperties": False,
                        "properties": {
                            "id": {
                                "type": "string",
                            },
                            "goal": {
                                "type": "string",
                            },
                            "risk_level": {
                                "type": "string",
                                "enum": [
                                    "L0",
                                    "L1",
                                    "L2",
                                    "L3",
                                ],
                            },
                            "success_criteria": {
                                "type": "array",
                                "minItems": 1,
                                "items": {
                                    "type": "object",
                                    "additionalProperties": False,
                                    "properties": {
                                        "rule": {
                                            "type": "string",
                                            "enum": [
                                                "url_contains",
                                                "visible_text_contains",
                                                "element_text_equals",
                                            ],
                                        },
                                        "expected": {
                                            "type": "string",
                                        },
                                        "element_role": {
                                            "type": "string",
                                        },
                                        "element_name": {
                                            "type": "string",
                                        },
                                    },
                                    "required": [
                                        "rule",
                                        "expected",
                                    ],
                                },
                            },
                        },
                        "required": [
                            "id",
                            "goal",
                            "success_criteria",
                            "risk_level",
                        ],
                    },
                }
            },
            "required": [
                "steps",
            ],
        },
    },
}


def _planning_tool_schema(
    browser_observation: BrowserObservation | None,
) -> dict[str, Any]:
    """Return a model-facing schema suitable for the available evidence.

    A live page snapshot can prove URL and visible-text state directly.  For
    that mode we deliberately omit ``element_text_equals`` from the model
    output contract: the observation layer exposes only actionable elements,
    while page headings, dialogs and tables are verified by visible text.  The
    richer rule remains available to validated plans from other callers.
    """
    if browser_observation is None:
        return PLAN_TOOL_SCHEMA

    schema = deepcopy(PLAN_TOOL_SCHEMA)
    rule_schema = (
        schema["function"]["parameters"]["properties"]["steps"]
        ["items"]["properties"]["success_criteria"]["items"]
        ["properties"]["rule"]
    )
    rule_schema["enum"] = [
        "url_contains",
        "visible_text_contains",
    ]
    return schema


def _normalize_snapshot_plan_arguments(
    arguments: dict[str, Any],
) -> dict[str, Any]:
    """Match a small-model plan to the state evidence it can verify.

    The snapshot mode deliberately asks the model for URL and visible-text
    criteria. Some tool-call decoders still emit an older element rule despite
    that schema. Convert only that unsupported output shape before validation;
    the final verifier still checks the same expected text against fresh page
    state after every action.
    """
    normalized = deepcopy(arguments)
    steps = normalized.get("steps")
    if not isinstance(steps, list):
        return normalized
    for step in steps:
        if not isinstance(step, dict):
            continue
        criteria = step.get("success_criteria")
        if not isinstance(criteria, list):
            continue
        for criterion in criteria:
            if not isinstance(criterion, dict):
                continue
            if criterion.get("rule") == "element_text_equals":
                criterion["rule"] = "visible_text_contains"
                criterion.pop("element_role", None)
                criterion.pop("element_name", None)
    return normalized


def _format_planning_observation(
    observation: BrowserObservation,
) -> str:
    """Bound the read-only page evidence supplied to a small planner model."""
    lines = [
        f"URL: {observation.url}",
        f"Title: {observation.title}",
        "",
        "Interactive elements:",
    ]
    for element in observation.elements[:40]:
        name = element.name or element.text or element.placeholder or ""
        lines.append(
            f'[{element.ref}] {element.role or element.tag} "{name}"'
        )
    if len(observation.elements) > 40:
        lines.append("(additional elements omitted)")
    visible_text = observation.visible_text or ""
    if len(visible_text) > 6000:
        visible_text = visible_text[:6000] + "\n[visible text truncated]"
    lines.extend(["", "Visible text:", visible_text or "(empty)"])
    return "\n".join(lines)


class PlannerOutputError(RuntimeError):
    pass


class LLMClient(Protocol):
    async def chat(
        self,
        *,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
    ) -> Any:
        ...


class BrowserPlanner:
    def __init__(
        self,
        llm: LLMClient,
    ) -> None:
        self.llm = llm

    async def plan(
        self,
        *,
        goal: str,
        target_url: str,
        recovery_context: str | None = None,
        browser_observation: BrowserObservation | None = None,
    ) -> TestPlan:
        system_prompt = """
You are the Planner of WebPilot-QA.

Convert the user's browser testing task into an ordered
structured TestPlan.

Rules:

1. You ONLY plan.
2. You never click, fill, navigate, or execute browser tools.
3. Every step must represent a meaningful verifiable milestone.
4. Do not create one PlanStep for every mouse click.
5. Every step must have at least one deterministic success criterion.
6. Day 4 supports ONLY:
   - url_contains
   - visible_text_contains
   - element_text_equals
7. Never output CSS selectors.
8. Never output XPath.
9. Never output JavaScript.
10. For element_text_equals use semantic role/name.
11. Step ids must be step_1, step_2, step_3...
12. Use submit_test_plan exactly once.
13. If the task contains a BENCHMARK ACCEPTANCE STATE block, it is public
    task data. Use its exact string values in observable success criteria;
    prefer visible_text_contains over invented element roles or names.
14. element_text_equals only supports actionable controls (such as button,
    textbox, combobox, checkbox, or tab). For headings, dialogs, tables,
    or other page content, use visible_text_contains.
15. When a CURRENT BROWSER SNAPSHOT is supplied, the target URL is already
    open. Do not add a navigation step. Use only exact visible strings and
    controls shown by that snapshot or exact public acceptance-state values.
16. Do not create a separate "verify" step when the preceding step's
    success criterion already proves the same state.
17. Step identifiers must be exactly step_1, step_2, step_3 in order.

The plan must be verifiable from the real browser state.
""".strip()

        recovery_note = ""
        if recovery_context:
            recovery_note = f"""
RECOVERY CONTEXT:
{recovery_context}

Create a fresh replacement plan. Do not repeat an invalid assumption.
""".strip()

        observation_note = ""
        if browser_observation is not None:
            observation_note = (
                "\n\nCURRENT BROWSER SNAPSHOT (read-only evidence):\n"
                + _format_planning_observation(browser_observation)
            )

        user_prompt = f"""
TARGET URL:
{target_url}

USER TASK:
{goal}

{recovery_note}{observation_note}

Create the smallest useful sequence of verifiable milestones.
""".strip()

        last_error = ""
        for attempt in range(2):
            repair_note = ""
            if last_error:
                repair_note = (
                    "\n\nREPAIR REQUIRED:\n"
                    f"Your previous plan was invalid: {last_error}\n"
                    "Return a corrected submit_test_plan call only. "
                    "If element_text_equals rejected a dialog, heading, or table, "
                    "replace it with visible_text_contains using the same expected "
                    "text and do not add a redundant verify step."
                )
            reply = await self.llm.chat(
                messages=[
                    {
                        "role": "system",
                        "content": system_prompt,
                    },
                    {
                        "role": "user",
                        "content": user_prompt + repair_note,
                    },
                ],
                tools=[
                    _planning_tool_schema(browser_observation),
                ],
            )

            tool_call = getattr(
                reply,
                "tool_call",
                None,
            )
            if tool_call is None:
                last_error = "Planner returned no structured tool call"
                continue
            if tool_call.name != "submit_test_plan":
                last_error = (
                    "Planner returned unexpected tool: "
                    f"{tool_call.name}"
                )
                continue
            try:
                arguments = tool_call.arguments
                if browser_observation is not None:
                    arguments = _normalize_snapshot_plan_arguments(arguments)
                return TestPlan.model_validate(arguments)
            except ValidationError as exc:
                last_error = "Planner returned invalid TestPlan:\n" + str(exc)

        raise PlannerOutputError(last_error)
