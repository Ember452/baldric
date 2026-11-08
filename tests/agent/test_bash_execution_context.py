"""Bash executions are durable messages whose context form is plain text.

Pi stores `bashExecution` as its own message; the provider still receives text.
The conversion lives in `provider_context`, and `exclude_from_context` keeps an
execution in the transcript without sending it to the model.
"""

from __future__ import annotations

from baldric_agent.context_projection import provider_context
from baldric_protocol.messages import BashExecutionMessage, UserMessage, bash_execution_text


def _execution(**overrides: object) -> BashExecutionMessage:
    values: dict[str, object] = {"command": "printf hello", "output": "hello", "exit_code": 0}
    values.update(overrides)
    return BashExecutionMessage(**values)  # type: ignore[arg-type]


def test_an_included_execution_becomes_one_user_message() -> None:
    execution = _execution()

    projected = provider_context([execution])

    assert len(projected) == 1
    assert isinstance(projected[0], UserMessage)
    assert projected[0].content == bash_execution_text(execution)


def test_the_text_is_the_documented_wording() -> None:
    projected = provider_context([_execution()])

    text = projected[0].content  # type: ignore[attr-defined]
    assert "Terminal command executed by the user." in text
    assert "```bash\nprintf hello\n```" in text
    assert "```text\nhello\n```" in text


def test_an_excluded_execution_is_not_sent_to_the_model() -> None:
    projected = provider_context([_execution(exclude_from_context=True)])

    assert projected == []


def test_neighbouring_messages_keep_their_order() -> None:
    first = UserMessage(content="before")
    last = UserMessage(content="after")

    projected = provider_context([first, _execution(), last])

    assert [message.role for message in projected] == ["user", "user", "user"]
    assert projected[0] is first
    assert projected[-1] is last
