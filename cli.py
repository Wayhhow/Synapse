import asyncio
import sys

from router import SkillRouter


async def main():
    router = SkillRouter()
    print("Welcome to Synapse! Type your query or 'exit'/'quit' to leave.")

    try:
        while True:
            try:
                user_input = input("> ")
            except EOFError:
                break

            stripped = user_input.strip().lower()
            if stripped in ("exit", "quit"):
                print("Goodbye!")
                break

            result = await router.process_query(user_input)
            print(result)
    except KeyboardInterrupt:
        print("\nInterrupted. Goodbye!")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
