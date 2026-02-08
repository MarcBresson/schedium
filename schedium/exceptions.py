from __future__ import annotations


class NextRunMaxIterationsReached(RuntimeError):
    def __init__(
        self,
        *,
        max_iterations: int,
        trigger_repr: str,
    ) -> None:
        super().__init__(
            "next_window exceeded max_iterations="
            f"{max_iterations} for trigger={trigger_repr}"
        )
        self.max_iterations = max_iterations
        self.trigger_repr = trigger_repr
