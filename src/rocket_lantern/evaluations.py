"""Manual match assessments, never an automatic cheating determination."""

from enum import StrEnum

from rocket_lantern.i18n import Text
from rocket_lantern.i18n import text as T


class Evaluation(StrEnum):
    NOT_EVALUATED = "not_evaluated"
    NO_SUSPICION = "no_suspicion"
    POSSIBLE = "possible"
    STRONG = "strong"


def evaluation_label(value: Evaluation) -> Text:
    """Return an explicit translatable label for an assessment."""
    match value:
        case Evaluation.NOT_EVALUATED:
            return T("Non évalué")
        case Evaluation.NO_SUSPICION:
            return T("Aucune suspicion")
        case Evaluation.POSSIBLE:
            return T("Suspicion possible")
        case Evaluation.STRONG:
            return T("Forte suspicion")
    raise ValueError("Unknown match evaluation")
