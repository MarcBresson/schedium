from __future__ import annotations


class NextRunMaxIterationsReached(RuntimeError):
    def __init__(
        self,
        *,
        max_iterations: int,
        trigger_repr: str,
    ) -> None:
        super().__init__(
            "datetime_of_next_run exceeded max_iterations="
            f"{max_iterations} for trigger={trigger_repr}"
        )
        self.max_iterations = max_iterations
        self.trigger_repr = trigger_repr


class NotATickingTrigger(RuntimeError):
    def __init__(
        self,
        *,
        trigger_repr: str,
    ) -> None:
        super().__init__(
            f"Trigger is not schedulable without a tick source: {trigger_repr}"
        )
        self.trigger_repr = trigger_repr
