from junjo.state import BaseState


class ConcurrentSubFlowState(BaseState):
    poems: list[str] = []
