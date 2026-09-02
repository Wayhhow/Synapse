import argparse
import asyncio
import logging
import os
import uuid

from pydantic import BaseModel as PydanticModel

from router import SkillRouter

# ---------------------------------------------------------------------------
# Terminal colors (ANSI; enabled on Windows 10+ terminals as well)
# ---------------------------------------------------------------------------
if os.name == "nt":
    os.system("")  # enable ANSI escape sequences on modern Windows terminals

C_RESET = "\033[0m"
C_BOLD = "\033[1m"
C_DIM = "\033[2m"
C_CYAN = "\033[36m"
C_GREEN = "\033[32m"
C_YELLOW = "\033[33m"
C_RED = "\033[31m"
C_MAGENTA = "\033[35m"

BANNER = f"""{C_MAGENTA}{C_BOLD}
   ____                       _
  / ___| _   _ _ __  ___ _ __| |___
  \\___ \\| | | | '_ \\/ _ \\ '__| / __|
   ___) | |_| | |_)|  __/ |  | \\__ \\
  |____/ \\__,_| .__/\\___|_|  |_|___/
              |_|{C_RESET}
{C_DIM}  self-evolving agent · skills grow at runtime{C_RESET}
"""

HELP_TEXT = f"""{C_BOLD}Commands{C_RESET}
  {C_CYAN}/help{C_RESET}              show this help
  {C_CYAN}/skills{C_RESET}             list available skills
  {C_CYAN}/stats{C_RESET}              skill health report
  {C_CYAN}/history{C_RESET}            show this session's memory
  {C_CYAN}/clear{C_RESET}              clear this session's memory
  {C_CYAN}/export [dir]{C_RESET}       export skills as SKILL.md folders (default: ./exported_skills)
  {C_CYAN}/exit{C_RESET}              leave (also: Ctrl-D)
Everything else is sent to the agent."""


def _format_result(result) -> str:
    """
    Render skill execution results in a CLI-friendly way (JSON is far more
    legible than raw Pydantic reprs for non-trivial response models).
    """
    if isinstance(result, PydanticModel):
        return result.model_dump_json(indent=2)
    return str(result)


def _print_skills(router: SkillRouter) -> None:
    print(f"{C_BOLD}Available skills ({len(router.skills)}){C_RESET}")
    for skill in router.skills.values():
        desc = skill.description.split("\n")[0]
        print(f"  {C_GREEN}●{C_RESET} {C_BOLD}{skill.name}{C_RESET}{C_DIM} — {desc}{C_RESET}")


def _print_stats(router: SkillRouter) -> None:
    report = router.evaluator.generate_improvement_report()
    if not report:
        print(f"{C_DIM}No skill statistics recorded yet.{C_RESET}")
        return
    print(f"{C_BOLD}Skill health report{C_RESET}")
    for name, info in sorted(report.items(), key=lambda kv: kv[1]["health_score"]):
        score = info["health_score"]
        color = C_GREEN if score >= 70 else (C_YELLOW if score >= 50 else C_RED)
        print(
            f"  {color}{score:5.1f}{C_RESET}  {C_BOLD}{name}{C_RESET}  "
            f"{C_DIM}runs={info['total_executions']} success={info['success_rate']:.0%} "
            f"status={info['status']}{C_RESET}"
        )


def _handle_command(command: str, router: SkillRouter, session_id: str) -> bool:
    """Execute a /slash-command. Returns False when the REPL should exit."""
    parts = command.split(maxsplit=1)
    name = parts[0].lower()
    arg = parts[1].strip() if len(parts) > 1 else ""

    if name in ("/exit", "/quit"):
        return False
    if name == "/help":
        print(HELP_TEXT)
    elif name == "/skills":
        _print_skills(router)
    elif name == "/stats":
        _print_stats(router)
    elif name == "/history":
        history = router.memory.get_history(session_id)
        if not history:
            print(f"{C_DIM}(empty){C_RESET}")
        for m in history:
            role_color = C_CYAN if m["role"] == "user" else C_GREEN
            print(f"  {role_color}{m['role']}{C_RESET}: {m['content'][:200]}")
    elif name == "/clear":
        router.memory.clear(session_id)
        print(f"{C_DIM}Memory cleared.{C_RESET}")
    elif name == "/export":
        from meta.skill_exporter import SkillExporter

        out_dir = arg or "exported_skills"
        exported = SkillExporter(router.skills, router.skills_dir).export(out_dir)
        print(f"{C_GREEN}Exported {len(exported)} skill(s) to '{out_dir}':{C_RESET} {', '.join(exported)}")
    else:
        print(f"{C_YELLOW}Unknown command '{name}'. Type /help for the command list.{C_RESET}")
    return True


async def main():
    logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] %(name)s: %(message)s")
    parser = argparse.ArgumentParser(description="Synapse CLI — a self-evolving agent")
    parser.add_argument("--skills", action="store_true", help="List all registered skills and exit")
    parser.add_argument("--stats", action="store_true", help="Show the skill health report and exit")
    parser.add_argument("--export", metavar="DIR", nargs="?", const="exported_skills",
                        help="Export skills as SKILL.md-standard folders and exit")
    args = parser.parse_args()

    if args.skills or args.stats or args.export:
        router = SkillRouter()
        if args.skills:
            _print_skills(router)
        if args.stats:
            _print_stats(router)
        if args.export:
            from meta.skill_exporter import SkillExporter

            exported = SkillExporter(router.skills, router.skills_dir).export(args.export)
            print(f"Exported {len(exported)} skill(s) to '{args.export}'")
        return

    # Print the banner BEFORE initializing the router so the user sees the
    # welcome message first, and the router's INFO logs (skill discovery, etc.)
    # appear below it rather than above.
    print(BANNER)
    print("Type your query, or /help for commands. 'exit' or Ctrl-D leaves.")
    router = SkillRouter()
    session_id = str(uuid.uuid4())

    try:
        while True:
            try:
                user_input = input(f"{C_BOLD}> {C_RESET}").strip()
            except EOFError:
                break

            if not user_input:
                continue
            lowered = user_input.lower()
            if lowered in ("exit", "quit"):
                break
            if lowered.startswith("/"):
                if not _handle_command(user_input, router, session_id):
                    break
                continue

            events = []
            try:
                async for event in router.process_query_events(user_input, session_id=session_id):
                    if event["type"] == "tool_start":
                        print(f"{C_DIM}  ⚙ running skill '{event['name']}'...{C_RESET}")
                    elif event["type"] == "meta":
                        if event["status"] == "generating":
                            print(f"{C_YELLOW}  🧬 meta-evolution: writing a new skill for '{event['intent']}'...{C_RESET}")
                        elif event["status"] == "ok":
                            print(f"{C_GREEN}  🧬 new skill created{C_RESET}")
                        else:
                            print(f"{C_RED}  🧬 skill generation failed{C_RESET}")
                    elif event["type"] == "final":
                        events = [event]
            except KeyboardInterrupt:
                print(f"\n{C_DIM}(interrupted this query){C_RESET}")
                continue

            for event in events:
                if event["result"] is not None:
                    print(_format_result(event["result"]))
                else:
                    print(event["text"])
    except KeyboardInterrupt:
        pass

    print("Goodbye!")


def main_sync() -> None:
    """Sync entry point for the ``synapse`` console script (pyproject.toml)."""
    asyncio.run(main())


if __name__ == "__main__":
    asyncio.run(main())
