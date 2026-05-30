# Synapse

**Author/Copyright**: Wayhhow

## Project Vision
Synapse is a next-generation, self-iterating AI agent architecture. The core goal of this project is to build a centralized repository of AI skills that supports intelligent routing and, most importantly, self-iteration. Synapse aims to seamlessly integrate new capabilities (skills) and even allow the agent to evaluate and write new skills for itself over time.

## Directory Structure

- `/core`: Contains the foundation classes and global configuration, including the `BaseSkill` abstract base class which enforces standard structure for all skills.
- `/skills`: The central repository for all atomic skills. The router automatically discovers and loads skills from this directory.
- `/router`: Contains the `SkillRouter` which is responsible for intent recognition and dynamically routing user inputs to the appropriate skills.
- `/meta`: Reserved for meta-cognitive tasks, such as evaluating skill effectiveness and generating new skill code.

## Getting Started

### Prerequisites

Install the required dependencies using pip:

```bash
pip install -r requirements.txt
```

## How to Write and Register a New Skill

Writing a new skill in Synapse is designed to be simple and seamlessly integrated due to the auto-discovery mechanism.

1. **Create a new Python file** in the `/skills` directory (e.g., `my_new_skill.py`).
2. **Define your arguments** using a Pydantic `BaseModel`. This is crucial for future LLM Function Calling integration.
3. **Inherit from `BaseSkill`** (found in `core.base`) and implement the required properties and the `async def execute` method.

### Example

```python
import asyncio
from pydantic import BaseModel, Field
from typing import Type
from core.base import BaseSkill

class MySkillArgs(BaseModel):
    query: str = Field(..., description="The query string.")

class MySkillResponse(BaseModel):
    result: str

class MyNewSkill(BaseSkill):
    @property
    def name(self) -> str:
        return "my_new_skill"

    @property
    def description(self) -> str:
        return "A description of what my new skill does, used by the router."

    @property
    def expected_args(self) -> Type[BaseModel]:
        return MySkillArgs

    @property
    def expected_response_type(self) -> Type[BaseModel]:
        return MySkillResponse

    async def execute(self, **kwargs) -> BaseModel:
        # Validate arguments automatically via Pydantic
        args = self.expected_args(**kwargs)

        # Your async logic here
        await asyncio.sleep(0.1)
        return self.expected_response_type(result=f"Processed query: {args.query}")
```

### Registration

**You do not need to manually register your skill.** As soon as the file is saved in the `/skills` directory, the `SkillRouter`'s auto-discovery mechanism will automatically load it upon instantiation.
