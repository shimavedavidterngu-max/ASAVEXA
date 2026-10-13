class EvidenceReviewError(Exception):
    status = 400


class ReviewNotFoundError(EvidenceReviewError):
    status = 404


class ReviewForbiddenError(EvidenceReviewError):
    status = 403


class ReviewStateError(EvidenceReviewError):
    status = 409
