import pytest
from ai_runner.auth.credentials import CredentialStore
from ai_runner.providers.router import ProviderRouter
from ai_runner.providers.base import LLMMessage, ToolDefinition, ToolCall
from ai_runner.providers.google import GoogleProvider
from ai_runner.providers.anthropic import AnthropicProvider
from ai_runner.providers.openai import OpenAIProvider

def test_infer_provider_and_model():
    router = ProviderRouter()
    
    p, m = router.infer_provider_and_model("gemini-2.5-pro")
    assert p == "google" and m == "gemini-2.5-pro"

    p, m = router.infer_provider_and_model("claude-3-7-sonnet")
    assert p == "anthropic" and m == "claude-3-7-sonnet"

    p, m = router.infer_provider_and_model("gpt-4o")
    assert p == "openai" and m == "gpt-4o"

    p, m = router.infer_provider_and_model("ollama/deepseek-r1")
    assert p == "ollama" and m == "deepseek-r1"

def test_google_message_conversion():
    prov = GoogleProvider(token_or_key="dummy", is_oauth=False)
    msgs = [
        LLMMessage(role="system", content="You are a helpful coder."),
        LLMMessage(role="user", content="Write a test function."),
        LLMMessage(role="assistant", content="Here it is:", tool_calls=[
            ToolCall(id="call_1", name="run_bash", arguments={"command": "pytest"})
        ]),
        LLMMessage(role="tool", name="run_bash", content="Exit code 0", tool_call_id="call_1")
    ]
    sys_inst, contents = prov._convert_messages(msgs)
    assert sys_inst == {"parts": [{"text": "You are a helpful coder."}]}
    assert len(contents) == 3
    assert contents[0]["role"] == "user"
    assert contents[1]["role"] == "model"
    assert "functionCall" in contents[1]["parts"][1]
    assert contents[2]["parts"][0]["functionResponse"]["name"] == "run_bash"

def test_anthropic_message_conversion():
    prov = AnthropicProvider(api_key="sk-ant-dummy")
    msgs = [
        LLMMessage(role="system", content="System instruction"),
        LLMMessage(role="user", content="Fix this bug"),
        LLMMessage(role="assistant", content="", tool_calls=[
            ToolCall(id="tc_1", name="edit_file", arguments={"path": "a.py"})
        ]),
        LLMMessage(role="tool", content="File edited", tool_call_id="tc_1")
    ]
    sys_prompt, converted = prov._convert_messages(msgs)
    assert sys_prompt == "System instruction"
    assert len(converted) == 3
    assert converted[1]["content"][0]["type"] == "tool_use"
    assert converted[2]["content"][0]["type"] == "tool_result"

def test_openai_message_conversion():
    prov = OpenAIProvider(api_key="sk-proj-dummy")
    msgs = [
        LLMMessage(role="system", content="You are AI"),
        LLMMessage(role="user", content="Hello")
    ]
    converted = prov._convert_messages(msgs)
    assert len(converted) == 2
    assert converted[0] == {"role": "system", "content": "You are AI"}
    assert converted[1] == {"role": "user", "content": "Hello"}

@pytest.mark.asyncio
async def test_router_with_credentials(tmp_path):
    store = CredentialStore(data_dir=tmp_path)
    store.set_provider("openai", {"api_key": "test_openai_key"})
    store.set_provider("google", {"api_key": "test_google_key"})

    router = ProviderRouter(store=store)
    
    p_google = await router.get_provider("gemini-2.5-pro")
    assert isinstance(p_google, GoogleProvider)
    assert p_google.token_or_key == "test_google_key"

    p_openai = await router.get_provider("gpt-4o")
    assert isinstance(p_openai, OpenAIProvider)
    assert p_openai.api_key == "test_openai_key"

    with pytest.raises(ValueError, match="No credentials found for Anthropic"):
        await router.get_provider("claude-3-7-sonnet")
