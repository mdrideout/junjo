from junjo.state import BaseState


class TestSubFlowState(BaseState):
    jokes: list[str] = []
