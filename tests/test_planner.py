from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from webpilot.agents.planner import (
    BrowserPlanner,
    PlannerOutputError,
    TestPlan as PlanModel,
)
from webpilot.browser.observation import BrowserObservation


def test_plan_rejects_empty_steps() -> None:
    with pytest.raises(ValidationError):
        PlanModel.model_validate(
            {
                "steps": []
            }
        )


def test_plan_rejects_duplicate_ids() -> None:
    payload = {
        "steps": [
            {
                "id": "step_1",
                "goal": "First",
                "risk_level": "L0",
                "success_criteria": [
                    {
                        "rule": "visible_text_contains",
                        "expected": "A",
                    }
                ],
            },
            {
                "id": "step_1",
                "goal": "Second",
                "risk_level": "L0",
                "success_criteria": [
                    {
                        "rule": "visible_text_contains",
                        "expected": "B",
                    }
                ],
            },
        ]
    }

    with pytest.raises(ValidationError):
        PlanModel.model_validate(
            payload
        )


def test_plan_preserves_order() -> None:
    plan = PlanModel.model_validate(
        {
            "steps": [
                {
                    "id": "step_1",
                    "goal": "First",
                    "risk_level": "L0",
                    "success_criteria": [
                        {
                            "rule": "visible_text_contains",
                            "expected": "First state",
                        }
                    ],
                },
                {
                    "id": "step_2",
                    "goal": "Second",
                    "risk_level": "L0",
                    "success_criteria": [
                        {
                            "rule": "visible_text_contains",
                            "expected": "Second state",
                        }
                    ],
                },
            ]
        }
    )

    assert [
        step.id
        for step in plan.steps
    ] == [
        "step_1",
        "step_2",
    ]


@pytest.mark.parametrize(
    "step_ids",
    [
        ["step_2"],
        ["step_1", "step_3"],
        ["step_2", "step_1"],
    ],
)
def test_plan_rejects_non_consecutive_or_reordered_ids(
    step_ids: list[str],
) -> None:
    with pytest.raises(ValidationError, match="consecutive"):
        PlanModel.model_validate(
            {
                "steps": [
                    {
                        "id": step_id,
                        "goal": f"Goal {index}",
                        "risk_level": "L0",
                        "success_criteria": [
                            {
                                "rule": "visible_text_contains",
                                "expected": f"state {index}",
                            }
                        ],
                    }
                    for index, step_id in enumerate(step_ids, start=1)
                ]
            }
        )


def test_element_text_rule_requires_exact_semantic_target() -> None:
    with pytest.raises(ValidationError, match="both"):
        PlanModel.model_validate(
            {
                "steps": [
                    {
                        "id": "step_1",
                        "goal": "Check a button.",
                        "risk_level": "L0",
                        "success_criteria": [
                            {
                                "rule": "element_text_equals",
                                "expected": "Search",
                                "element_role": "button",
                            }
                        ],
                    }
                ]
            }
        )


def test_element_text_rule_rejects_noninteractive_role() -> None:
    with pytest.raises(ValidationError, match="actionable roles"):
        PlanModel.model_validate(
            {
                "steps": [
                    {
                        "id": "step_1",
                        "goal": "Check a dialog title.",
                        "risk_level": "L0",
                        "success_criteria": [
                            {
                                "rule": "element_text_equals",
                                "expected": "Ready",
                                "element_role": "dialog",
                                "element_name": "title",
                            }
                        ],
                    }
                ]
            }
        )


class FakeLLM:
    async def chat(
        self,
        *,
        messages,
        tools,
    ):
        return SimpleNamespace(
            tool_call=SimpleNamespace(
                name="submit_test_plan",
                arguments={
                    "steps": [
                        {
                            "id": "step_1",
                            "goal": (
                                "Search for laptop "
                                "and reach results"
                            ),
                            "risk_level": "L0",
                            "success_criteria": [
                                {
                                    "rule": (
                                        "visible_text_contains"
                                    ),
                                    "expected": (
                                        "Results for: laptop"
                                    ),
                                }
                            ],
                        }
                    ]
                },
            )
        )


@pytest.mark.asyncio
async def test_planner_accepts_structured_plan() -> None:
    planner = BrowserPlanner(
        FakeLLM()
    )

    plan = await planner.plan(
        goal="Search for laptop",
        target_url="file:///fixture.html",
    )

    assert len(plan.steps) == 1

    assert plan.steps[0].id == "step_1"

    assert (
        plan.steps[0]
        .success_criteria[0]
        .expected
        == "Results for: laptop"
    )


class InvalidFakeLLM:
    async def chat(
        self,
        *,
        messages,
        tools,
    ):
        return SimpleNamespace(
            tool_call=SimpleNamespace(
                name="submit_test_plan",
                arguments={
                    "steps": []
                },
            )
        )


@pytest.mark.asyncio
async def test_planner_rejects_invalid_output() -> None:
    planner = BrowserPlanner(
        InvalidFakeLLM()
    )

    with pytest.raises(
        PlannerOutputError
    ):
        await planner.plan(
            goal="Anything",
            target_url="file:///fixture.html",
        )


class RepairingFakeLLM:
    def __init__(self) -> None:
        self.calls = 0

    async def chat(self, *, messages, tools):
        self.calls += 1
        arguments = {"steps": []}
        if self.calls == 2:
            assert "REPAIR REQUIRED" in messages[-1]["content"]
            arguments = {
                "steps": [
                    {
                        "id": "step_1",
                        "goal": "Confirm readiness.",
                        "risk_level": "L0",
                        "success_criteria": [
                            {
                                "rule": "visible_text_contains",
                                "expected": "Ready",
                            }
                        ],
                    }
                ]
            }
        return SimpleNamespace(
            tool_call=SimpleNamespace(
                name="submit_test_plan",
                arguments=arguments,
            )
        )


@pytest.mark.asyncio
async def test_planner_repairs_one_invalid_structured_output() -> None:
    llm = RepairingFakeLLM()

    plan = await BrowserPlanner(llm).plan(
        goal="Confirm readiness.",
        target_url="file:///fixture.html",
    )

    assert llm.calls == 2
    assert plan.steps[0].success_criteria[0].expected == "Ready"


class SnapshotCompatibilityLLM:
    async def chat(self, *, messages, tools):
        assert "CURRENT BROWSER SNAPSHOT" in messages[-1]["content"]
        rule_enum = (
            tools[0]["function"]["parameters"]["properties"]["steps"]
            ["items"]["properties"]["success_criteria"]["items"]
            ["properties"]["rule"]["enum"]
        )
        assert rule_enum == ["url_contains", "visible_text_contains"]
        return SimpleNamespace(
            tool_call=SimpleNamespace(
                name="submit_test_plan",
                arguments={
                    "steps": [
                        {
                            "id": "step_1",
                            "goal": "Open the help dialog.",
                            "risk_level": "L0",
                            "success_criteria": [
                                {
                                    "rule": "element_text_equals",
                                    "expected": "ShopBench help",
                                    "element_role": "dialog",
                                    "element_name": "title",
                                }
                            ],
                        }
                    ]
                },
            )
        )


@pytest.mark.asyncio
async def test_planner_normalizes_legacy_element_rule_with_snapshot() -> None:
    plan = await BrowserPlanner(SnapshotCompatibilityLLM()).plan(
        goal="Open help.",
        target_url="file:///fixture.html",
        browser_observation=BrowserObservation(
            url="file:///fixture.html",
            title="Fixture",
            visible_text="ShopBench help",
        ),
    )

    criterion = plan.steps[0].success_criteria[0]
    assert criterion.rule == "visible_text_contains"
    assert criterion.expected == "ShopBench help"
    assert criterion.element_role is None
    assert criterion.element_name is None
