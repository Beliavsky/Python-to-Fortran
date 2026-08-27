import atexit
import datetime
import os

_start_dt = datetime.datetime.now()


def _print_run_span():
    # Under pytest-xdist (-n auto/-n N), this module is imported once per
    # worker process in addition to the controller -- only the controller
    # (which has no PYTEST_XDIST_WORKER env var) should print the summary
    # line, or it would be repeated once per worker.
    if "PYTEST_XDIST_WORKER" in os.environ:
        return
    end_dt = datetime.datetime.now()
    if _start_dt.date() == end_dt.date():
        line = (
            f"Started {_start_dt.strftime('%Y-%m-%d %H:%M:%S')}, "
            f"ended {end_dt.strftime('%H:%M:%S')}"
        )
    else:
        line = (
            f"Started {_start_dt.strftime('%Y-%m-%d %H:%M:%S')}, "
            f"ended {end_dt.strftime('%Y-%m-%d %H:%M:%S')}"
        )
    print(line)


# atexit fires after pytest has finished writing its own summary line
# ("137 passed in ... (H:MM:SS)"), so this always ends up as the true last
# line of output, regardless of pytest's internal hook/plugin ordering.
atexit.register(_print_run_span)
