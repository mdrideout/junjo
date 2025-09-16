from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from typing import ClassVar as _ClassVar, Optional as _Optional

DESCRIPTOR: _descriptor.FileDescriptor

class GetTokenRequest(_message.Message):
    __slots__ = ("api_key",)
    API_KEY_FIELD_NUMBER: _ClassVar[int]
    api_key: str
    def __init__(self, api_key: _Optional[str] = ...) -> None: ...

class GetTokenResponse(_message.Message):
    __slots__ = ("jwt", "expires_at")
    JWT_FIELD_NUMBER: _ClassVar[int]
    EXPIRES_AT_FIELD_NUMBER: _ClassVar[int]
    jwt: str
    expires_at: int
    def __init__(self, jwt: _Optional[str] = ..., expires_at: _Optional[int] = ...) -> None: ...

class ExchangeApiKeyForJwtRequest(_message.Message):
    __slots__ = ("api_key",)
    API_KEY_FIELD_NUMBER: _ClassVar[int]
    api_key: str
    def __init__(self, api_key: _Optional[str] = ...) -> None: ...

class ExchangeApiKeyForJwtResponse(_message.Message):
    __slots__ = ("jwt", "expires_at")
    JWT_FIELD_NUMBER: _ClassVar[int]
    EXPIRES_AT_FIELD_NUMBER: _ClassVar[int]
    jwt: str
    expires_at: int
    def __init__(self, jwt: _Optional[str] = ..., expires_at: _Optional[int] = ...) -> None: ...
