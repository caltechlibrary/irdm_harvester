"""Guards for the harvest steps that call libraries which end the process.

dimcli.login prints "dsl.ini credentials file not found" and exits (status 0)
when it has no credentials. That is a SystemExit, which "except Exception"
does not catch, so harvest.py finished without printing a doi or an error and
the workflow saw nothing wrong. run_step turns it into an ordinary exception
the existing handlers print as a "system error".
"""


class StepEnded(RuntimeError):
    """A library called exit during a harvest step."""


def run_step(name, step, *args, **kwargs):
    """Call step(*args, **kwargs); a SystemExit from it raises StepEnded.

    Any exit counts, status 0 included. Other exceptions, KeyboardInterrupt
    among them, pass through unchanged.
    """
    try:
        return step(*args, **kwargs)
    except SystemExit as e:
        raise StepEnded(f"{name} ended the process (exit {e.code})") from None


def check_no_dimensions(no_dimensions, production):
    """Raise ValueError if -no-dimensions is asked for on a production run.

    Skipping the Dimensions step is for -test, -local and -url runs without a
    key; in production a missing Dimensions step must stay an error.
    """
    if no_dimensions and production:
        raise ValueError(
            "-no-dimensions is for -test, -local and -url runs only; "
            "production always runs the Dimensions step"
        )
