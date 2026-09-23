print("Testing AI assistant (text mode)...")

from ai.assistant import Assistant, AssistantError

assistant = Assistant()

print("Type a question (or 'quit' to exit):")

while True:
    question = input("\nYou: ").strip()

    if question.lower() == "quit":
        break

    try:
        answer = assistant.ask(question)
        print(f"Assistant: {answer}")
    except AssistantError as e:
        print(f"[Error - {e.error_type}]: {e}")