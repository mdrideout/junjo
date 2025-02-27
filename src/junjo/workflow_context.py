
from contextvars import ContextVar
from typing import Generic

from junjo.store import BaseStore, StoreT

StoreContextDict = dict[str, StoreT]


class WorkflowContextManager(Generic[StoreT]):
    """
    Workflow Context

    Contains the context variables for running workflows.
    """

    # Establish initial context variables to store Workflow required data
    _store_dict_var: ContextVar[StoreContextDict] = ContextVar("store_dict")

    # Initialize the context variables
    def __init__(self):
        self._store_dict_var.set({})
        pass

    @classmethod
    def set_store(cls, workflow_id: str, store: BaseStore) -> None:
        """
        Sets the store for a workflow.

        Args:
            workflow_id: The workflow ID.
            store: The store to set.
        """
        store_dict = cls._store_dict_var.get()
        store_dict[workflow_id] = store
        cls._store_dict_var.set(store_dict)

    @classmethod
    def get_store(cls, workflow_id: str) -> BaseStore:
        """
        Returns the store for a workflow.

        Args:
            workflow_id: The workflow ID.

        Returns:
            The store for the workflow.
        """
        store_dict = cls._store_dict_var.get()
        store = store_dict.get(workflow_id)
        if store is None:
            raise ValueError(f"Store not found for workflow {workflow_id}")

        return store

    @classmethod
    def remove_store(cls, workflow_id: str) -> None:
        """
        Removes the store for a workflow.

        Args:
            workflow_id: The workflow ID.
        """
        store_dict = cls._store_dict_var.get()
        store_dict.pop(workflow_id, None)
        cls._store_dict_var.set(store_dict)
