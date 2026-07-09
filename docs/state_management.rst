.. _state_management:

##############################################################
State Management
##############################################################

.. meta::
    :description: A deep dive into Junjo's Redux-inspired, immutable state management. Learn how to use BaseState and BaseStore to build predictable and concurrency-safe Python workflows.
    :keywords: junjo, python, state management, redux, immutable state, pydantic, workflow, BaseStore, BaseState

Junjo's state management is designed to be predictable, traceable, and safe for concurrent operations. It is heavily inspired by the principles of Redux, a popular state management library in the JavaScript ecosystem. This page provides a deep dive into how to effectively manage state in your Junjo workflows.

The Core Principles
===================

1.  **Single Source of Truth:** The state of your entire workflow is stored in a single object tree within a single **Store**.
2.  **State is Read-Only:** The only way to change the state is to call a store action method, which commits the change through `set_state` with a partial update. This prevents nodes from directly modifying the state, which could lead to unpredictable behavior.
3.  **Changes are Made with Store Methods:** State modifications are encapsulated within methods in your **Store**. Similar to "reducers" in Redux, these methods are the only place where `set_state` should be called, ensuring that all state changes are predictable and centralized.

BaseState: Defining Your State's Shape
=======================================

The `BaseState` class, which is a Pydantic `BaseModel`, is used to define the structure of your workflow's state. Because it's a Pydantic model, you get all the benefits of type hinting and data validation out of the box.

.. code-block:: python

    from junjo import BaseState

    class ChatWorkflowState(BaseState):
        messages: list[dict] = []
        current_user: str
        is_typing: bool = False
        error_message: str | None = None

In this example, we've defined a state for a chat application. Any workflow that uses this state will have access to these fields, and Pydantic will ensure that the data conforms to the specified types.

Because Junjo uses your state's normal Pydantic serialization for workflow
state telemetry, this is also the place where you control telemetry-facing
serialization behavior. If a field should be excluded, redacted, or truncated
for OpenTelemetry state payloads, implement that at the state model layer.

.. code-block:: python

    from pydantic import Field, field_serializer
    from junjo import BaseState


    class AgentState(BaseState):
        prompt: str
        provider_api_key: str | None = Field(default=None, exclude=True)

        @field_serializer("prompt")
        def serialize_prompt_for_telemetry(self, value: str) -> str:
            if len(value) <= 2000:
                return value
            return value[:2000] + "...[truncated]"

In this example:

- ``provider_api_key`` stays in runtime state but is omitted from serialized
  telemetry state
- ``prompt`` stays complete in runtime state but is truncated in serialized
  telemetry state

Junjo uses runtime field values for state transitions. Pydantic serialization
configuration controls telemetry payloads, but it does not remove or rewrite
live state when later store actions call ``set_state``.

BaseStore: Managing Your State
==============================

The `BaseStore` is the heart of Junjo's state management. It holds the state and provides methods for updating it. You will create a custom store for each workflow that inherits from `BaseStore` and is typed with your custom `BaseState`.

.. code-block:: python

    from junjo import BaseStore

    class ChatWorkflowStore(BaseStore[ChatWorkflowState]):
        async def add_message(self, message: dict) -> None:
            # Get the current messages and append the new one
            new_messages = self._state.messages + [message]
            await self.set_state({"messages": new_messages})

        async def set_is_typing(self, is_typing: bool) -> None:
            await self.set_state({"is_typing": is_typing})

        async def set_error(self, error: str) -> None:
            await self.set_state({"error_message": error})

Inside a store action like `add_message`, reading `self._state` directly to derive the next update is acceptable because actions run on the store and each `set_state` commit is validated and applied against the locked current state; outside of store actions, always read state with `await store.get_state()`.

The `set_state` Method
----------------------

The `set_state` method is the **only** way to update the state in the store. It takes a dictionary of the fields you want to update and their new values.

**Key Behaviors of `set_state`:**
- **Immutable Updates:** `set_state` creates a *copy* of the state with the updates applied. It does not mutate the original state object. This is crucial for preventing side effects and ensuring predictable state transitions.
- **Concurrency-Safe:** All calls to `set_state` are protected by an `asyncio.Lock`, so you can safely call actions from multiple concurrent nodes without worrying about race conditions.
- **Validation:** Before applying the update, `set_state` validates the new state against your Pydantic model. If the update is invalid, it will raise a `ValueError`.
- **Runtime State Semantics:** `set_state` merges updates with runtime field values, not serialized state dumps. Serialization choices such as ``Field(exclude=True)`` and ``field_serializer`` are respected by telemetry output without changing live state.

Using the Store in a Node
=========================

Nodes receive an instance of the store in their `service` method. This allows them to read the current state and dispatch actions to update it.

`get_state()` returns a detached deep snapshot of the current state. You can safely inspect the returned value, but mutating it does not update the store. To change workflow state, always call a store action that delegates to `set_state()`.

.. code-block:: python

    from junjo import Node

    class SendMessageNode(Node[ChatWorkflowStore]):
        async def service(self, store: ChatWorkflowStore) -> None:
            state = await store.get_state()
            user = state.current_user
            
            # In a real app, you would get the message from an external source
            new_message = {"user": user, "text": "Hello, Junjo!"}

            # Dispatch an action to add the message to the state
            await store.add_message(new_message)

By following this pattern, you create a clear and predictable data flow in your application. Nodes don't need to know how the state is updated; they just need to know which actions to call on the store. This separation of concerns makes your code easier to test, debug, and reason about.
