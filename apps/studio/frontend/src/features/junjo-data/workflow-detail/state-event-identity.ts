import type { StoreTransition } from '../../store-diagnostics/schemas/store-diagnostics'
import type { JunjoSetStateEvent } from '../../traces/schemas/schemas'

export interface StateEventIdentity {
  storeId: string
  spanId: string
  eventId: string
  sequence: number
}

export interface StateEventSelection extends StateEventIdentity {
  event: JunjoSetStateEvent
}

export function stateEventIdentityKey(identity: StateEventIdentity): string {
  return JSON.stringify([
    identity.storeId,
    identity.spanId,
    identity.eventId,
    identity.sequence,
  ])
}

export function rawStateEventIdentity(
  spanId: string,
  event: JunjoSetStateEvent,
): StateEventIdentity {
  return {
    storeId: event.attributes['junjo.store.id'],
    spanId,
    eventId: event.attributes.id,
    sequence: event.attributes['junjo.store.transition.sequence'],
  }
}

export function transitionStateEventIdentity(
  storeId: string,
  transition: StoreTransition,
): StateEventIdentity {
  return {
    storeId,
    spanId: transition.span_id,
    eventId: transition.event_id,
    sequence: transition.sequence,
  }
}
