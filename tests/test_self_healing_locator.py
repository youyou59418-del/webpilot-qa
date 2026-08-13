import pytest

from webpilot.browser.locator import (
    ElementSignature,
    SelfHealingLocator,
)


def test_exact_semantic_match_scores_high():
    healer = SelfHealingLocator()

    old = ElementSignature(
        ref="e1",
        tag="button",
        role="button",
        name="Login",
        text="Login",
        data_testid="auth-action",
        structure=(
            "button > div > body"
        ),
    )

    new = ElementSignature(
        ref="e7",
        tag="button",
        role="button",
        name="Login",
        text="Login",
        data_testid="auth-action",
        structure=(
            "button > div > body"
        ),
    )

    score, reasons = (
        healer.score_signatures(
            old,
            new,
        )
    )

    assert score >= 0.90
    assert "role_exact" in reasons


def test_login_to_sign_in_is_supported():
    healer = SelfHealingLocator()

    old = ElementSignature(
        ref="e1",
        tag="button",
        role="button",
        name="Login",
        text="Login",
    )

    new = ElementSignature(
        ref="e9",
        tag="button",
        role="button",
        name="Sign in",
        text="Sign in",
    )

    score, reasons = (
        healer.score_signatures(
            old,
            new,
        )
    )

    assert score >= 0.65


def test_unrelated_button_scores_lower():
    healer = SelfHealingLocator()

    old = ElementSignature(
        ref="e1",
        tag="button",
        role="button",
        name="Login",
        text="Login",
    )

    unrelated = ElementSignature(
        ref="e2",
        tag="button",
        role="button",
        name="Delete account",
        text="Delete account",
    )

    score, _ = (
        healer.score_signatures(
            old,
            unrelated,
        )
    )

    assert score < 0.55


@pytest.mark.parametrize(
    ("left", "right"),
    [
        ("Login", "Sign in"),
        ("Log in", "Sign in"),
        ("LOGIN", "signin"),
    ],
)
def test_auth_aliases(
    left,
    right,
):
    healer = SelfHealingLocator()

    old = ElementSignature(
        tag="button",
        role="button",
        name=left,
        text=left,
    )

    new = ElementSignature(
        tag="button",
        role="button",
        name=right,
        text=right,
    )

    score, _ = (
        healer.score_signatures(
            old,
            new,
        )
    )

    assert score >= 0.65
