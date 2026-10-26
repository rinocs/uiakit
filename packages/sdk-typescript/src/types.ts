import type {
  Completed,
  Failure,
  RuntimeEvent as ContractRuntimeEvent,
  Started,
  Text,
} from './generated.ts';

export * from './generated.ts';

type EventEnvelope = Omit<ContractRuntimeEvent, 'event_type' | 'payload'>;

export type AgentStartedEvent = EventEnvelope & {
  event_type: 'agent.started';
  payload: Started;
};

export type ResponseDeltaEvent = EventEnvelope & {
  event_type: 'response.delta';
  payload: Text;
};

export type ResponseCompletedEvent = EventEnvelope & {
  event_type: 'response.completed';
  payload: Completed & { citations?: import('./generated.ts').Citation[] };
};

export type AgentFailedEvent = EventEnvelope & {
  event_type: 'agent.failed';
  payload: Failure;
};

export type AgentCancelledEvent = EventEnvelope & {
  event_type: 'agent.cancelled';
  payload: { code?: string };
};

export type RuntimeEvent =
  | AgentStartedEvent
  | ResponseDeltaEvent
  | ResponseCompletedEvent
  | AgentFailedEvent
  | AgentCancelledEvent;

export type RuntimeEventType = RuntimeEvent['event_type'];
