import asyncio
from typing import Type

from pydantic import BaseModel

from core.base import BaseSkill
from core.sandbox import Sandbox, SandboxResult


# Module-level skill classes so they can be pickled for multiprocessing.

class _SimpleArgs(BaseModel):
    pass


class _SimpleResponse(BaseModel):
    value: str


class SimpleSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "simple_skill"

    @property
    def description(self) -> str:
        return "A simple skill for testing the sandbox."

    @property
    def expected_args(self) -> Type[BaseModel]:
        return _SimpleArgs

    @property
    def expected_response_type(self) -> Type[BaseModel]:
        return _SimpleResponse

    async def execute(self, **kwargs) -> _SimpleResponse:
        return _SimpleResponse(value="hello world")


class _SlowArgs(BaseModel):
    pass


class _SlowResponse(BaseModel):
    value: str


class SlowSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "slow_skill"

    @property
    def description(self) -> str:
        return "A skill that sleeps long enough to trigger a sandbox timeout."

    @property
    def expected_args(self) -> Type[BaseModel]:
        return _SlowArgs

    @property
    def expected_response_type(self) -> Type[BaseModel]:
        return _SlowResponse

    async def execute(self, **kwargs) -> _SlowResponse:
        await asyncio.sleep(20)
        return _SlowResponse(value="should not reach here")


class _ErrorArgs(BaseModel):
    pass


class _ErrorResponse(BaseModel):
    value: str


class ErrorSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "error_skill"

    @property
    def description(self) -> str:
        return "A skill that raises a ValueError during execution."

    @property
    def expected_args(self) -> Type[BaseModel]:
        return _ErrorArgs

    @property
    def expected_response_type(self) -> Type[BaseModel]:
        return _ErrorResponse

    async def execute(self, **kwargs) -> _ErrorResponse:
        raise ValueError("something went wrong")


def test_sandbox_success():
    sandbox = Sandbox(timeout=5)
    skill = SimpleSkill()
    result = sandbox.execute(skill)
    assert isinstance(result, SandboxResult)
    assert result.success is True
    assert result.error is None
    assert isinstance(result.result, _SimpleResponse)
    assert result.result.value == "hello world"


def test_sandbox_timeout():
    sandbox = Sandbox(timeout=1)
    skill = SlowSkill()
    result = sandbox.execute(skill)
    assert isinstance(result, SandboxResult)
    assert result.success is False
    assert result.result is None
    assert result.error is not None
    assert "timed out" in result.error


def test_sandbox_exception():
    sandbox = Sandbox(timeout=5)
    skill = ErrorSkill()
    result = sandbox.execute(skill)
    assert isinstance(result, SandboxResult)
    assert result.success is False
    assert result.result is None
    assert result.error is not None
    assert "something went wrong" in result.error
