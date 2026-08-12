from __future__ import annotations

from typing import Any

from webpilot.recovery.models import (
    FailureEvent,
    FailureType,
)


class FailureClassifier:
    def from_exception(
        self,
        *,
        exc: Exception,
        step_id: str,
        retry_count: int,
        tool_name: str | None = None,
        element_ref: str | None = None,
        current_url: str | None = None,
    ) -> FailureEvent:
        message = str(exc)
        lowered = message.lower()
        class_name = exc.__class__.__name__.lower()

        failure_type = FailureType.UNKNOWN

        if any(
            token in lowered
            for token in (
                "not allowed",
                "forbidden",
                "action forbidden",
            )
        ):
            failure_type = FailureType.ACTION_FORBIDDEN

        elif (
            isinstance(exc, KeyError)
            and element_ref is not None
        ):
            failure_type = FailureType.ELEMENT_NOT_FOUND

        elif any(
            token in lowered
            for token in (
                "unknown element ref",
                "unknown ref",
                "element not found",
                "could not find element",
                "locator not found",
                "invalid element ref",
            )
        ):
            failure_type = FailureType.ELEMENT_NOT_FOUND

        elif any(
            token in lowered
            for token in (
                "not visible",
                "element is hidden",
                "element hidden",
                "outside of the viewport",
            )
        ):
            failure_type = FailureType.ELEMENT_NOT_VISIBLE

        elif any(
            token in lowered
            for token in (
                "execution context was destroyed",
                "because of navigation",
                "page changed",
                "target page has been closed",
                "target closed",
            )
        ):
            failure_type = FailureType.PAGE_CHANGED

        elif (
            "timeout" in class_name
            or "timeout" in lowered
            or "timed out" in lowered
        ):
            failure_type = FailureType.TIMEOUT

        return FailureEvent(
            failure_type=failure_type,
            step_id=step_id,
            message=message,
            tool_name=tool_name,
            element_ref=element_ref,
            retry_count=retry_count,
            current_url=current_url,
        )

    def from_verification(
        self,
        *,
        verification: Any,
        step_id: str,
        retry_count: int,
        current_url: str | None = None,
    ) -> FailureEvent:
        reason = getattr(
            verification,
            "failure_reason",
            None,
        )

        evidence = getattr(verification, "evidence", []) or []
        failed_url_check = any(
            getattr(item, "rule", None) == "url_contains"
            and not getattr(item, "passed", False)
            for item in evidence
        )

        return FailureEvent(
            failure_type=(
                FailureType.WRONG_PAGE
                if failed_url_check
                else FailureType.ASSERTION_FAILED
            ),
            step_id=step_id,
            message=reason or "Verifier returned FAIL",
            retry_count=retry_count,
            current_url=current_url,
        )

    def wrong_page(
        self,
        *,
        step_id: str,
        retry_count: int,
        expected_url: str,
        current_url: str,
    ) -> FailureEvent:
        return FailureEvent(
            failure_type=FailureType.WRONG_PAGE,
            step_id=step_id,
            message=(
                "Current page does not match expected page. "
                f"Expected={expected_url!r}, "
                f"Actual={current_url!r}"
            ),
            retry_count=retry_count,
            current_url=current_url,
        )
