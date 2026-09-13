---
title: "State Management"
description: "Manage typed application state with explicit actions and atomic patches. Inspect chronological state diffs to diagnose and evaluate AI workflow changes."
---
<!-- migrated-from: sdks/python/docs/state_management.rst; source-hash: sha256:61e738adc3fa58ce2f2b616edb27647a7758bf66b8b46915fadfc7a10e11347f -->
<!-- migrated-keywords: junjo, python, state management, redux, immutable state, pydantic, workflow, BaseStore, BaseState -->

<a id="state-management"></a>
Junjo's state system gives each workflow explicit, typed inputs and state
transitions. Inspired by Redux and the Elm architecture, it separates work in
Nodes from updates in Store actions. This lets you and your coding agent inspect
which operation changed a value and use that evidence to diagnose an unexpected
outcome.

The application Store is live runtime state. Junjo AI Studio reconstructs its
recorded state history from telemetry; Studio does not execute the workflow or
hold the application's active Store.

## The Core Principles

1. **Single Source of Truth:** The state of your entire workflow is stored in a single object tree within a single **Store**.
2. **State is Read-Only:** Application code changes live state by calling a store action method, which commits the change through `set_state` with a partial update. Public reads return detached snapshots; private Store fields must not be mutated directly.
3. **Changes are Made with Store Methods:** State modifications are encapsulated within methods in your **Store**. Similar to "reducers" in Redux, these methods are the only place where `set_state` should be called, ensuring that all state changes are predictable and centralized.

## BaseState: Defining Your State's Shape

The `BaseState` class, which is a Pydantic `BaseModel`, is used to define the structure of your workflow's state. Because it's a Pydantic model, you get all the benefits of type hinting and data validation out of the box.

```python
from junjo import BaseState

class ChatWorkflowState(BaseState):
    messages: list[dict] = []
    current_user: str
    is_typing: bool = False
    error_message: str | None = None
```

In this example, we've defined a state for a chat application. Any workflow that uses this state will have access to these fields, and Pydantic will ensure that the data conforms to the specified types.

Because Junjo uses your state's normal Pydantic serialization for workflow
state telemetry, this is also the place where you control telemetry-facing
serialization behavior. If a field should be excluded, redacted, or truncated
for OpenTelemetry state payloads, implement that at the state model layer.

```python
from pydantic import Field, field_serializer
from junjo import BaseState

class ChatWorkflowState(BaseState):
    prompt: str
    provider_api_key: str | None = Field(default=None, exclude=True)

    @field_serializer("prompt")
    def serialize_prompt_for_telemetry(self, value: str) -> str:
        if len(value) <= 2000:
            return value
        return value[:2000] + "...[truncated]"
```

In this example:

- `provider_api_key` stays in runtime state but is omitted from serialized
  telemetry state
- `prompt` stays complete in runtime state but is truncated in serialized
  telemetry state

Junjo uses runtime field values for state transitions. Pydantic serialization
configuration controls telemetry payloads, but it does not remove or rewrite
live state when later store actions call `set_state`.

## BaseStore: Managing Your State

The `BaseStore` is the heart of Junjo's state management. It holds the state and provides methods for updating it. You will create a custom store for each workflow that inherits from `BaseStore` and is typed with your custom `BaseState`.

```python
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
```

Inside a Store action, `self._state` can be used to derive an update; outside
Store actions, use `await store.get_state()` for a detached snapshot. The Store
lock protects each `set_state` commit, not the entire action method. Do not read
a value, await external work, then assume that value is still current. If
concurrent actions replace the same field, the last committed replacement wins.
Prefer separate output fields for independent concurrent work, or explicitly
coordinate updates that depend on the same prior value.

### The `set_state` Method

The `set_state` method is the **only** way to update the state in the store. It takes a dictionary of the fields you want to update and their new values.

**Key Behaviors of \`set_state\`:**

- **Immutable Updates:** `set_state` merges the patch with runtime fields and creates one owned deep copy before validation. It does not mutate the original state object. This is crucial for preventing side effects and ensuring predictable state transitions.
- **Atomic Commit:** Each `set_state` call is protected by an `asyncio.Lock`. Validation and commit see the latest locked state; code before that call is not automatically locked.
- **Validation:** Before applying the update, `set_state` validates the new state against your Pydantic model. If the update is invalid, it will raise a `ValueError`.
- **Top-Level Patches:** Only supplied fields are replaced. Nested objects are replaced as complete field values, not recursively merged. Patching different output fields preserves the other concurrent results.
- **Runtime State Semantics:** `set_state` merges updates with runtime field values, not serialized state dumps. Serialization choices such as `Field(exclude=True)` and `field_serializer` are respected by telemetry output without changing live state.

## Using the Store in a Node

Nodes receive an instance of the store in their `service` method. This allows them to read the current state and dispatch actions to update it.

`get_state()` returns a detached deep snapshot of the current state. You can safely inspect the returned value, but mutating it does not update the store. To change workflow state, always call a store action that delegates to `set_state()`.

```python
from junjo import Node

class SendMessageNode(Node[ChatWorkflowStore]):
    async def service(self, store: ChatWorkflowStore) -> None:
        state = await store.get_state()
        user = state.current_user

        # In a real app, you would get the message from an external source
        new_message = {"user": user, "text": "Hello, Junjo!"}

        # Dispatch an action to add the message to the state
        await store.add_message(new_message)
```

By following this pattern, you create a clear and predictable data flow in your application. Nodes don't need to know how the state is updated; they just need to know which actions to call on the store. This separation of concerns makes your code easier to test, debug, and reason about.

## Input ownership and mutation mistakes

Store actions keep the same explicit replacement API for nested models:

```python
from pydantic import BaseModel

class Message(BaseModel):
    text: str

class MessageState(BaseState):
    message: Message

class MessageStore(BaseStore[MessageState]):
    async def set_message(self, message: Message) -> None:
        await self.set_state({"message": message})

store = MessageStore(MessageState(message=Message(text="Ready")))
payload = Message(text="Hello")
await store.set_message(payload)

payload.text = "Changed outside the Store"
assert (await store.get_state()).message.text == "Hello"

await store.set_message(Message(text="Updated through an action"))
```

Both incoming values and outgoing snapshots are detached from live Store state.
Mutating the caller's payload or a `get_state()` snapshot normally raises no
exception: it changes only that local object. It does not commit a transition,
validate the Store or emit state-change hooks. Call a named action to commit a
replacement value. This also means reusing a payload across Stores does not
share mutable live state between them.

A patch rejected by Pydantic model validation raises `ValueError` from
`set_state`, with the underlying `ValidationError` as its cause, and leaves the
committed state unchanged. Validation runs on owned candidate values, so a
validator cannot accidentally mutate the caller's input while normalizing or
rejecting that candidate.

Detachment does not freeze Python objects. Application-defined frozen models
retain their own assignment behavior, but freezing a model alone does not make
nested lists immutable. `store._state` is private live state; direct mutation
bypasses the supported API and has no guaranteed exception. Store actions must
also construct replacements rather than mutate private state in place.

## Diagnose the state transition that changed the outcome

With [telemetry configured](/docs/observability/opentelemetry/), Studio can show
the ordered state updates received for a native execution. Trace a wrong refund
decision back to the policy value or eligibility update, then create a
[Node or Workflow evaluation target](/docs/python/evaluation/#declare-one-harness)
for that boundary. Compare the candidate's outcome and state chronology against
the baseline.

A missing transition or excluded field limits what can be reconstructed; inspect
Studio's evidence-integrity diagnostics before treating absent data as proof
that the application never produced it.
