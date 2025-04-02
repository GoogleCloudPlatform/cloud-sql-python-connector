# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

from typing import ClassVar as _ClassVar
from typing import Optional as _Optional
from typing import Union as _Union

from google.protobuf import descriptor as _descriptor
from google.protobuf import message as _message
from google.protobuf.internal import enum_type_wrapper as _enum_type_wrapper

from google.api import field_behavior_pb2 as _field_behavior_pb2

DESCRIPTOR: _descriptor.FileDescriptor

class CloudSQLConnectRequest(_message.Message):
    __slots__ = ["protocol_type", "user_agent"]

    class ProtocolType(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = []

    PROTOCOL_TYPE_FIELD_NUMBER: _ClassVar[int]
    PROTOCOL_TYPE_UNSPECIFIED: CloudSQLConnectRequest.ProtocolType
    TCP: CloudSQLConnectRequest.ProtocolType
    UDS: CloudSQLConnectRequest.ProtocolType
    USER_AGENT_FIELD_NUMBER: _ClassVar[int]
    protocol_type: CloudSQLConnectRequest.ProtocolType
    user_agent: str
    def __init__(
        self,
        user_agent: _Optional[str] = ...,
        protocol_type: _Optional[
            _Union[CloudSQLConnectRequest.ProtocolType, str]
        ] = ...,
    ) -> None: ...

class CloudSQLConnectResponse(_message.Message):
    __slots__ = ["error", "response_code"]

    class ResponseCode(int, metaclass=_enum_type_wrapper.EnumTypeWrapper):
        __slots__ = []

    ERROR: CloudSQLConnectResponse.ResponseCode
    ERROR_FIELD_NUMBER: _ClassVar[int]
    OK: CloudSQLConnectResponse.ResponseCode
    RESPONSE_CODE_FIELD_NUMBER: _ClassVar[int]
    RESPONSE_CODE_UNSPECIFIED: CloudSQLConnectResponse.ResponseCode
    error: str
    response_code: CloudSQLConnectResponse.ResponseCode
    def __init__(
        self,
        response_code: _Optional[
            _Union[CloudSQLConnectResponse.ResponseCode, str]
        ] = ...,
        error: _Optional[str] = ...,
    ) -> None: ...
