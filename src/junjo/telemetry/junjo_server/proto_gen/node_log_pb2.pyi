from google.protobuf import empty_pb2 as _empty_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class CreateNodeLogRequest(_message.Message):
    __slots__ = ("exec_id", "type", "event_time_nano", "state")
    EXEC_ID_FIELD_NUMBER: _ClassVar[int]
    TYPE_FIELD_NUMBER: _ClassVar[int]
    EVENT_TIME_NANO_FIELD_NUMBER: _ClassVar[int]
    STATE_FIELD_NUMBER: _ClassVar[int]
    exec_id: str
    type: str
    event_time_nano: int
    state: str
    def __init__(self, exec_id: _Optional[str] = ..., type: _Optional[str] = ..., event_time_nano: _Optional[int] = ..., state: _Optional[str] = ...) -> None: ...
