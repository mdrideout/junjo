from junjo import Condition

from run_for_every.sample_workflow.store import SampleWorkflowState


class CounterIsEven(Condition[SampleWorkflowState]):
    def evaluate(self, state: SampleWorkflowState) -> bool:

        # Check the count
        counter = state.counter
        if counter is None:
            return False

        return counter % 2 == 0

    def __str__(self) -> str:
        """
        Custom string representation override for this instance.
        """
        return "CounterIsEven()"



class MatchesCount(Condition[SampleWorkflowState]):

    def __init__(self, count: int):
        self.count = count

    def evaluate(self, state: SampleWorkflowState) -> bool:

        # Check the count
        counter = state.counter
        if counter is None:
            return False

        if counter == self.count:
            return True

        return False

    def __str__(self) -> str:
        """
        Custom string representation override for this instance.
        """
        return f"MatchesCount({self.count})"
