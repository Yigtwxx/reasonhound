"""Tests for the provider interface and the FakeProvider test double."""

from __future__ import annotations

from reasonhound.providers import (
    Completion,
    FakeProvider,
    LLMProvider,
    Message,
    Role,
    StreamEventType,
    ToolCall,
    ToolSpec,
    Usage,
)


def test_fake_provider_satisfies_protocol() -> None:
    assert isinstance(FakeProvider(), LLMProvider)


def test_default_completion() -> None:
    provider = FakeProvider(default_text="hello")
    out = provider.complete([Message(role=Role.USER, content="hi")])
    assert out.text == "hello"
    assert out.tool_calls == ()


def test_scripted_responses_consumed_in_order() -> None:
    scripted = [Completion(text="first"), Completion(text="second")]
    provider = FakeProvider(scripted)
    assert provider.complete([]).text == "first"
    assert provider.complete([]).text == "second"
    assert provider.complete([]).text == "ok"  # falls back to default


def test_calls_are_recorded() -> None:
    provider = FakeProvider()
    tools = [ToolSpec(name="read_file", description="read", input_schema={"type": "object"})]
    provider.complete(
        [Message(role=Role.USER, content="scan")],
        system="you are a hunter",
        tools=tools,
    )
    assert len(provider.calls) == 1
    call = provider.calls[0]
    assert call.system == "you are a hunter"
    assert call.tools[0].name == "read_file"
    assert call.messages[0].content == "scan"


def test_stream_emits_text_then_done() -> None:
    provider = FakeProvider([Completion(text="hi", usage=Usage(input_tokens=3, output_tokens=1))])
    events = list(provider.stream([Message(role=Role.USER, content="x")]))

    text_events = [e for e in events if e.type is StreamEventType.TEXT]
    assert "".join(e.text for e in text_events) == "hi"

    assert events[-1].type is StreamEventType.DONE
    assert events[-1].completion is not None
    assert events[-1].completion.usage.output_tokens == 1


def test_stream_emits_tool_calls() -> None:
    call = ToolCall(id="t1", name="grep", arguments={"pattern": "eval("})
    provider = FakeProvider([Completion(text="", tool_calls=(call,))])
    events = list(provider.stream([]))
    tool_events = [e for e in events if e.type is StreamEventType.TOOL_CALL]
    assert tool_events and tool_events[0].tool_call == call


def test_message_and_toolresult_shapes() -> None:
    msg = Message(role=Role.ASSISTANT, tool_calls=(ToolCall(id="1", name="ls", arguments={}),))
    assert msg.role is Role.ASSISTANT
    assert msg.tool_calls[0].name == "ls"
