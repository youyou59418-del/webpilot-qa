from __future__ import annotations

from typing import Any, Literal, Protocol

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

The plan must be verifiable from the real browser state.
""".strip()

        recovery_note = ""
        if recovery_context:
            recovery_note = f"""
RECOVERY CONTEXT:
{recovery_context}

Create a fresh replacement plan. Do not repeat an invalid assumption.
""".strip()

        user_prompt = f"""
TARGET URL:
{target_url}

USER TASK:
{goal}

{recovery_note}

Create the smallest useful sequence of verifiable milestones.
""".strip()

        last_error = ""
        for attempt in range(2):
            repair_note = ""
            if last_error:
                repair_note = (
                    "\n\nREPAIR REQUIRED:\n"
                    f"Your previous plan was invalid: {last_error}\n"
                    "Return a corrected submit_test_plan call only."
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
                    PLAN_TOOL_SCHEMA,
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
                return TestPlan.model_validate(tool_call.arguments)
            except ValidationError as exc:
                last_error = "Planner returned invalid TestPlan:\n" + str(exc)

        raise PlannerOutputError(last_error)
