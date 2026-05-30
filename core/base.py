from abc import ABC, abstractmethod
from typing import Type
from pydantic import BaseModel

class BaseSkill(ABC):
    """
    The BaseSkill class is the foundation for all skills in the Synapse project.
    All custom skills must inherit from this class and implement its required properties and methods.
    """

    @property
    @abstractmethod
    def name(self) -> str:
        """The name of the skill."""
        pass

    @property
    @abstractmethod
    def description(self) -> str:
        """A description of the skill, used by LLMs to determine when to route to this skill."""
        pass

    @property
    @abstractmethod
    def expected_args(self) -> Type[BaseModel]:
        """A Pydantic BaseModel class representing the expected arguments for the execute method."""
        pass

    @property
    @abstractmethod
    def expected_response_type(self) -> Type[BaseModel]:
        """A Pydantic BaseModel class representing the expected response type for the execute method."""
        pass

    def validate_args(self, **kwargs) -> BaseModel:
        """
        Validates the provided keyword arguments against the expected_args Pydantic model.
        Returns an instantiated expected_args model populated with the provided kwargs.
        """
        return self.expected_args(**kwargs)

    @property
    def use_sandbox(self) -> bool:
        return True

    @abstractmethod
    async def execute(self, **kwargs) -> BaseModel:
        """
        The main execution logic of the skill.
        The keyword arguments should match the fields of the expected_args Pydantic model.
        Must return an instance of expected_response_type.
        """
        pass
