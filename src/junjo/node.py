from abc import ABC, abstractmethod
from typing import TYPE_CHECKING, Generic, TypeVar

from jsonpatch import JsonPatch
from nanoid import generate

if TYPE_CHECKING:
    from junjo.store import BaseStore

StoreT = TypeVar("StoreT", bound="BaseStore")

class Node(Generic[StoreT], ABC):
    """
    Base class for all nodes in the junjo graph.

    - The Workflow passes the store to the node's _execute function
    - The action function is expected to carry out side effects on the output
    """

    def __init__(
        self,
    ):
        """Initialize the node"""
        super().__init__()
        self._id = generate()
        self._patches: list[JsonPatch] = []

    def __repr__(self):
        """Returns a string representation of the node."""
        return f"<{type(self).__name__} id={self.id}>"

    @property
    def id(self) -> str:
        """Returns the unique identifier for the node."""
        return self._id

    @property
    def name(self) -> str:
        """Returns the name of the node class instance."""
        return self.__class__.__name__

    @property
    def patches(self) -> list[JsonPatch]:
        """Returns the list of patches that have been applied to the state by this node."""
        return self._patches

    def add_patch(self, patch: JsonPatch) -> None:
        """Adds a patch to the list of patches."""
        self._patches.append(patch)

    @abstractmethod
    async def service(self, store: StoreT) -> None:
        """The main logic of the node.

        Args
            :param store: The store will be passed to this node during execution
        """
        raise NotImplementedError

    async def _execute(self, store: StoreT) -> None:
        """
        Validate the node and execute its service function.
        """

        # Execute the service
        try:
            await self.service(store) # (cannot know store is StoreT here? it works...)
        except Exception as e:
            print(f"Error executing service: {e}")
            return
