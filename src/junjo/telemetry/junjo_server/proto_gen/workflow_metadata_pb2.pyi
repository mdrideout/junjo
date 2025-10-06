from google.protobuf import empty_pb2 as _empty_pb2
from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class CreateWorkflowMetadataRequest(_message.Message):
    __slots__ = ("exec_id", "app_name", "workflow_name", "event_time_nano", "structure")
    EXEC_ID_FIELD_NUMBER: _ClassVar[int]
    APP_NAME_FIELD_NUMBER: _ClassVar[int]
    WORKFLOW_NAME_FIELD_NUMBER: _ClassVar[int]
    EVENT_TIME_NANO_FIELD_NUMBER: _ClassVar[int]
    STRUCTURE_FIELD_NUMBER: _ClassVar[int]
    exec_id: str
    app_name: str
    workflow_name: str
    event_time_nano: int
    structure: str
    def __init__(self, exec_id: _Optional[str] = ..., app_name: _Optional[str] = ..., workflow_name: _Optional[str] = ..., event_time_nano: _Optional[int] = ..., structure: _Optional[str] = ...) -> None: ...
