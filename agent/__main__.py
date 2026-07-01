from __future__ import annotations

from agent import Conversation, story_agent
from agent.conversation import AgentInput


def main() -> None:
    """Run the agent interactively as a plain command-line chat.

    A minimal REPL around ``story_agent`` driven by a :class:`Conversation`:
    the conversation builds each turn's prompt and history, the REPL runs the
    agent and feeds the reply back. The same Conversation object can be driven
    by any other caller, so the full flow — story generation included — works
    here just the same.

    Run it with ``uv run agent`` (or ``uv run python -m agent``).
    Ctrl-C / Ctrl-D to exit.
    """
    print("Bedtime Story Agent — interactive CLI. Ctrl-C to exit.\n")
    conversation = Conversation()

    def run(agent_input: AgentInput) -> bool:
        """Run one turn; return True once the full story has been delivered."""
        result = story_agent.run_sync(
            agent_input.prompt, message_history=agent_input.message_history
        )
        out = result.output
        conversation.record_response(out.message)
        print(f"\n{out.message}\n")
        if out.story_text:
            print(f"{out.story_text}\n")
            return True
        return False

    run(conversation.opening())

    while True:
        try:
            user_text = input("you > ")
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if run(conversation.reply(user_text)):
            break  # story delivered — conversation complete


if __name__ == "__main__":
    main()
