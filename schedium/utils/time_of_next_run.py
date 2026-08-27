from datetime import datetime

from schedium.job import Job


def time_of_next_run(
    jobs: list[Job],
    after: datetime | None = None,
    *,
    max_iterations: int = 100_000,
) -> datetime | None:
    if after is None:
        after = datetime.now()

    next_runs: list[datetime] = []
    for job in jobs:
        next_run = job.datetime_of_next_run(after, max_iterations=max_iterations)
        if next_run is not None:
            next_runs.append(next_run)
    return min(next_runs) if next_runs else None
