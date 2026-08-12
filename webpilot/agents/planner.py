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

The plan must be verifiable from the real browser state.
""".strip()

        user_prompt = f"""
TARGET URL:
{target_url}

USER TASK:
{goal}

Create the smallest useful sequence of verifiable milestones.
""".strip()

        reply = await self.llm.chat(
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {
                    "role": "user",
                    "content": user_prompt,
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
            raise PlannerOutputError(
                "Planner returned no structured tool call"
            )

        if tool_call.name != "submit_test_plan":
            raise PlannerOutputError(
                "Planner returned unexpected tool: "
                f"{tool_call.name}"
            )

        try:
            return TestPlan.model_validate(
                tool_call.arguments
            )

        except ValidationError as exc:
            raise PlannerOutputError(
                "Planner returned invalid TestPlan:\n"
                f"{exc}"
            ) from exc
