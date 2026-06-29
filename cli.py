import argparse
import asyncio
import logging
import sys
import uuid

from router import SkillRouter


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Synapse CLI")
    parser.add_argument("--skills", action="store_true", help="List all registered skills and exit")
    args = parser.parse_args()

    if args.skills:
        router = SkillRouter()
        print("Registered skills:")
        for skill in router.skills.values():
            print(f"  - {skill.name}: {skill.description}")
        print(f"Total: {len(router.skills)} skill(s)")
        return

    # Print the banner BEFORE initializing the router so the user sees the
    # welcome message first, and the router's INFO logs (skill discovery, etc.)
    # appear below it rather than above.
    print("Welcome to Synapse! Type your query or 'exit'/'quit' to leave.")
    router = SkillRouter()
    session_id = str(uuid.uuid4())

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

            result = await router.process_query(user_input, session_id=session_id)
            print(result)
    except KeyboardInterrupt:
        print("\nInterrupted. Goodbye!")
        sys.exit(0)


if __name__ == "__main__":
    asyncio.run(main())
