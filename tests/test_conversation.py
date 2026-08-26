from langchain_core.messages import AIMessage, HumanMessage, SystemMessage, ToolMessage

from core.conversation import compact_conversation, recent_conversation_context


def test_recent_context_excludes_current_query_and_is_bounded():
    messages = [
        HumanMessage(content="First question", id="h1"),
        AIMessage(content="First answer", id="a1"),
        HumanMessage(content="Current question", id="h2"),
    ]
    context = recent_conversation_context(
        messages, "Current question", "Older summary", max_messages=2, max_chars=100,
    )
    assert context[0] == {"role": "summary", "content": "Older summary"}
    assert [item["content"] for item in context[1:]] == ["First question", "First answer"]
    assert [item["role"] for item in context[1:]] == ["user", "assistant"]


def test_recent_context_filters_tool_system_and_preserves_citations():
    messages = [
        SystemMessage(content="hidden system instruction", id="s1"),
        HumanMessage(content=[{"text": "Show prior auth evidence"}], id="h1"),
        ToolMessage(content="raw tool payload", tool_call_id="tool-1", id="t1"),
        AIMessage(content="Use events, not polling [jira:PA-44].", id="a1"),
        HumanMessage(content="Current question", id="h2"),
    ]
    context = recent_conversation_context(messages, "Current question", max_messages=4, max_chars=500)
    assert [item["role"] for item in context] == ["user", "assistant"]
    assert context[0]["content"] == "Show prior auth evidence"
    assert context[1]["citations"] == ["[jira:PA-44]"]
    assert "raw tool payload" not in str(context)


def test_compaction_summarizes_and_identifies_old_messages_for_removal():
    messages = [HumanMessage(content=f"Question {index}", id=f"h{index}") for index in range(5)]
    summary, removable = compact_conversation(
        messages, "Prior summary", keep_messages=2, max_summary_chars=120,
    )
    assert "Prior summary" in summary
    assert "Question 0" in summary
    assert removable == ["h0", "h1", "h2"]
    assert len(summary) <= 120


def test_compaction_does_not_split_user_assistant_turn_boundary():
    messages = [
        HumanMessage(content="q0", id="h0"), AIMessage(content="a0", id="a0"),
        HumanMessage(content="q1", id="h1"), AIMessage(content="a1", id="a1"),
        HumanMessage(content="q2", id="h2"), AIMessage(content="a2", id="a2"),
        HumanMessage(content="q3", id="h3"), AIMessage(content="a3 [github:x]", id="a3"),
        HumanMessage(content="q4", id="h4"),
    ]
    summary, removable = compact_conversation(messages, keep_messages=6, max_summary_chars=500)
    assert removable == ["h0", "a0"]
    assert "q1" not in summary
    assert "refs=" not in summary


def test_compaction_preserves_citation_references_in_summary():
    messages = [
        HumanMessage(content="old q", id="h0"),
        AIMessage(content="old a [github:AUTH-1]", id="a0"),
        HumanMessage(content="new q", id="h1"),
        AIMessage(content="new a", id="a1"),
    ]
    summary, removable = compact_conversation(messages, keep_messages=2, max_summary_chars=500)
    assert removable == ["h0", "a0"]
    assert "[github:AUTH-1]" in summary
    assert "refs=[github:AUTH-1]" in summary