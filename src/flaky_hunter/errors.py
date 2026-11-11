"""Exception hierarchy for flaky-hunter."""


class FlakyHunterError(Exception):
    """Base class for all flaky-hunter errors."""


class ConfigError(FlakyHunterError):
    """Invalid or unreadable configuration."""


class AdapterError(FlakyHunterError):
    """The runner adapter could not do what was asked."""


class ReportParseError(FlakyHunterError):
    """A test report file could not be parsed."""
