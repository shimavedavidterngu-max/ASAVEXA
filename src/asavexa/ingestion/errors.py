class IngestionError(Exception):
    """A file or payload could not be read at all (the user gets a plain-English reason, HTTP 400)."""


class UnsupportedFileError(IngestionError):
    pass


class BatchNotImportableError(IngestionError):
    """The batch still has blocking problems, or changed since it was previewed."""


class NoTextError(UnsupportedFileError):
    """A PDF with no text layer (a scan or photo)."""
