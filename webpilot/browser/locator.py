from __future__ import annotations

import inspect
import re
from difflib import SequenceMatcher
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
)


# =========================================================
# Data models
# =========================================================


class ElementSignature(BaseModel):
    """
    Semantic snapshot of an interactive element.

    The old ref is kept only for audit/debugging.
    It is NOT treated as a stable identifier.
    """

    model_config = ConfigDict(
        extra="forbid"
    )

    ref: str | None = None

    tag: str = ""
    role: str = ""

    name: str = ""
    text: str = ""
    placeholder: str = ""

    label: str = ""
    data_testid: str = ""

    structure: str = ""


class HealingCandidate(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    ref: str

    score: float = Field(
        ge=0.0,
        le=1.0,
    )

    reasons: list[str]

    signature: ElementSignature


class HealingResult(BaseModel):
    model_config = ConfigDict(
        extra="forbid"
    )

    original_ref: str | None

    healed_ref: str

    score: float

    margin: float

    candidate_count: int

    reasons: list[str]


# =========================================================
# Exceptions
# =========================================================


class SelfHealingError(RuntimeError):
    pass


class SelfHealingNotFoundError(
    SelfHealingError
):
    pass


class SelfHealingAmbiguousError(
    SelfHealingError
):
    pass


# =========================================================
# Helpers
# =========================================================


def normalize_text(
    value: Any,
) -> str:
    if value is None:
        return ""

    text = str(value)

    text = re.sub(
        r"\s+",
        " ",
        text,
    ).strip()

    return text.casefold()


def semantic_action_key(
    value: str,
) -> str:
    """
    Small deterministic alias normalization.

    Day 6 intentionally does NOT use embeddings.

    This allows common controlled drift such as:
        Login -> Sign in
    """

    text = normalize_text(
        value
    )

    compact = re.sub(
        r"[^a-z0-9]+",
        "",
        text,
    )

    authentication_aliases = {
        "login",
        "logon",
        "signin",
        "signon",
    }

    logout_aliases = {
        "logout",
        "logoff",
        "signout",
    }

    if compact in authentication_aliases:
        return "__AUTH_LOGIN__"

    if compact in logout_aliases:
        return "__AUTH_LOGOUT__"

    return text


def string_similarity(
    left: str,
    right: str,
    *,
    semantic: bool = False,
) -> float:
    left_norm = (
        semantic_action_key(left)
        if semantic
        else normalize_text(left)
    )

    right_norm = (
        semantic_action_key(right)
        if semantic
        else normalize_text(right)
    )

    if not left_norm or not right_norm:
        return 0.0

    if left_norm == right_norm:
        return 1.0

    return SequenceMatcher(
        None,
        left_norm,
        right_norm,
    ).ratio()


async def maybe_await(
    value: Any,
) -> Any:
    if inspect.isawaitable(
        value
    ):
        return await value

    return value


# =========================================================
# Self-Healing Locator
# =========================================================


class SelfHealingLocator:
    """
    Rule-based Self-Healing Locator.

    Candidate scoring priority:

    1. role
    2. accessible name / label
    3. placeholder / text
    4. data-testid
    5. structural context

    No embeddings are used on Day 6.
    """

    def __init__(
        self,
        *,
        min_score: float = 0.55,
        min_margin: float = 0.08,
    ) -> None:
        self.min_score = min_score
        self.min_margin = min_margin

    # -----------------------------------------------------
    # Capture old semantic element state
    # -----------------------------------------------------

    async def capture(
        self,
        *,
        engine: Any,
        element: Any,
    ) -> ElementSignature:
        locator = await maybe_await(
            engine.locator_for(
                element.ref
            )
        )

        label = ""
        data_testid = ""
        structure = ""

        try:
            data_testid = (
                await locator.get_attribute(
                    "data-testid"
                )
                or ""
            )

        except Exception:
            data_testid = ""

        try:
            label = await locator.evaluate(
                """
                (el) => {
                    if (
                        el.labels
                        && el.labels.length
                    ) {
                        return Array.from(
                            el.labels
                        )
                        .map(
                            label =>
                                label.innerText
                                || label.textContent
                                || ""
                        )
                        .join(" ");
                    }

                    const ariaLabel =
                        el.getAttribute(
                            "aria-label"
                        );

                    return ariaLabel || "";
                }
                """
            )

            label = label or ""

        except Exception:
            label = ""

        try:
            structure = await locator.evaluate(
                """
                (el) => {
                    const parts = [];

                    let current = el;

                    let depth = 0;

                    while (
                        current
                        && depth < 4
                    ) {
                        let part =
                            current.tagName
                            ? current.tagName
                                .toLowerCase()
                            : "";

                        const role =
                            current.getAttribute
                            ? current.getAttribute(
                                "role"
                            )
                            : null;

                        if (role) {
                            part +=
                                `[role="${role}"]`;
                        }

                        parts.push(part);

                        current =
                            current.parentElement;

                        depth += 1;
                    }

                    return parts.join(" > ");
                }
                """
            )

            structure = (
                structure
                or ""
            )

        except Exception:
            structure = ""

        return ElementSignature(
            ref=element.ref,
            tag=(
                getattr(
                    element,
                    "tag",
                    "",
                )
                or ""
            ),
            role=(
                getattr(
                    element,
                    "role",
                    "",
                )
                or ""
            ),
            name=(
                getattr(
                    element,
                    "name",
                    "",
                )
                or ""
            ),
            text=(
                getattr(
                    element,
                    "text",
                    "",
                )
                or ""
            ),
            placeholder=(
                getattr(
                    element,
                    "placeholder",
                    "",
                )
                or ""
            ),
            label=label,
            data_testid=data_testid,
            structure=structure,
        )

    # -----------------------------------------------------
    # Score two semantic signatures
    # -----------------------------------------------------

    def score_signatures(
        self,
        old: ElementSignature,
        new: ElementSignature,
    ) -> tuple[
        float,
        list[str],
    ]:
        """
        Score the current candidate against the old
        semantic element signature.

        Important:
        only fields that actually existed in the old
        element participate in the denominator.

        Therefore a sparse element is not penalized
        merely because label / placeholder / testid
        were unavailable.

        Final score is normalized to [0, 1].
        """

        raw_score = 0.0
        available_weight = 0.0

        reasons: list[str] = []

        # -------------------------------------------------
        # Role: 0.25
        # -------------------------------------------------

        if normalize_text(
            old.role
        ):
            available_weight += 0.25

            if (
                normalize_text(
                    old.role
                )
                == normalize_text(
                    new.role
                )
            ):
                raw_score += 0.25

                reasons.append(
                    "role_exact"
                )

        # -------------------------------------------------
        # Accessible name: 0.30
        # -------------------------------------------------

        if normalize_text(
            old.name
        ):
            available_weight += 0.30

            name_score = string_similarity(
                old.name,
                new.name,
                semantic=True,
            )

            raw_score += (
                0.30
                * name_score
            )

            if name_score > 0:
                reasons.append(
                    "name="
                    f"{name_score:.3f}"
                )

        # -------------------------------------------------
        # Label: 0.10
        # -------------------------------------------------

        if normalize_text(
            old.label
        ):
            available_weight += 0.10

            label_score = string_similarity(
                old.label,
                new.label,
                semantic=True,
            )

            raw_score += (
                0.10
                * label_score
            )

            if label_score > 0:
                reasons.append(
                    "label="
                    f"{label_score:.3f}"
                )

        # -------------------------------------------------
        # Placeholder: 0.10
        # -------------------------------------------------

        if normalize_text(
            old.placeholder
        ):
            available_weight += 0.10

            placeholder_score = (
                string_similarity(
                    old.placeholder,
                    new.placeholder,
                )
            )

            raw_score += (
                0.10
                * placeholder_score
            )

            if placeholder_score > 0:
                reasons.append(
                    "placeholder="
                    f"{placeholder_score:.3f}"
                )

        # -------------------------------------------------
        # Visible text: 0.10
        # -------------------------------------------------

        if normalize_text(
            old.text
        ):
            available_weight += 0.10

            text_score = string_similarity(
                old.text,
                new.text,
                semantic=True,
            )

            raw_score += (
                0.10
                * text_score
            )

            if text_score > 0:
                reasons.append(
                    "text="
                    f"{text_score:.3f}"
                )

        # -------------------------------------------------
        # data-testid: 0.05
        # -------------------------------------------------

        if normalize_text(
            old.data_testid
        ):
            available_weight += 0.05

            if (
                normalize_text(
                    old.data_testid
                )
                == normalize_text(
                    new.data_testid
                )
            ):
                raw_score += 0.05

                reasons.append(
                    "data_testid_exact"
                )

        # -------------------------------------------------
        # Structural context: 0.05
        # -------------------------------------------------

        if normalize_text(
            old.structure
        ):
            available_weight += 0.05

            structure_score = (
                string_similarity(
                    old.structure,
                    new.structure,
                )
            )

            raw_score += (
                0.05
                * structure_score
            )

            if structure_score > 0:
                reasons.append(
                    "structure="
                    f"{structure_score:.3f}"
                )

        # -------------------------------------------------
        # HTML tag: 0.05
        # -------------------------------------------------

        if normalize_text(
            old.tag
        ):
            available_weight += 0.05

            if (
                normalize_text(
                    old.tag
                )
                == normalize_text(
                    new.tag
                )
            ):
                raw_score += 0.05

                reasons.append(
                    "tag_exact"
                )

        # -------------------------------------------------
        # Normalize according to fields that existed
        # in the OLD signature.
        # -------------------------------------------------

        if available_weight <= 0:
            return (
                0.0,
                reasons,
            )

        score = (
            raw_score
            / available_weight
        )

        score = min(
            max(
                score,
                0.0,
            ),
            1.0,
        )

        return (
            score,
            reasons,
        )

    # -----------------------------------------------------
    # Rank current observation candidates
    # -----------------------------------------------------

    async def rank_candidates(
        self,
        *,
        engine: Any,
        observation: Any,
        target: ElementSignature,
    ) -> list[HealingCandidate]:
        candidates: list[
            HealingCandidate
        ] = []

        for element in (
            observation.elements
        ):
            try:
                signature = await self.capture(
                    engine=engine,
                    element=element,
                )

            except Exception:
                continue

            score, reasons = (
                self.score_signatures(
                    target,
                    signature,
                )
            )

            candidates.append(
                HealingCandidate(
                    ref=element.ref,
                    score=score,
                    reasons=reasons,
                    signature=signature,
                )
            )

        candidates.sort(
            key=lambda item: (
                item.score
            ),
            reverse=True,
        )

        return candidates

    # -----------------------------------------------------
    # Resolve best current ref
    # -----------------------------------------------------

    async def heal(
        self,
        *,
        engine: Any,
        observation: Any,
        target: ElementSignature,
    ) -> HealingResult:
        candidates = await self.rank_candidates(
            engine=engine,
            observation=observation,
            target=target,
        )

        if not candidates:
            raise SelfHealingNotFoundError(
                "No interactive candidates "
                "exist in the current observation."
            )

        best = candidates[0]

        if (
            best.score
            < self.min_score
        ):
            raise SelfHealingNotFoundError(
                "Best Self-Healing candidate "
                "did not reach the minimum score. "
                f"score={best.score:.3f}, "
                f"minimum={self.min_score:.3f}"
            )

        second_score = (
            candidates[1].score
            if len(candidates) > 1
            else 0.0
        )

        margin = (
            best.score
            - second_score
        )

        if (
            len(candidates) > 1
            and margin
            < self.min_margin
        ):
            raise SelfHealingAmbiguousError(
                "Self-Healing candidate is ambiguous. "
                f"best={best.score:.3f}, "
                f"second={second_score:.3f}, "
                f"margin={margin:.3f}, "
                f"required={self.min_margin:.3f}"
            )

        return HealingResult(
            original_ref=target.ref,
            healed_ref=best.ref,
            score=best.score,
            margin=margin,
            candidate_count=len(
                candidates
            ),
            reasons=best.reasons,
        )
