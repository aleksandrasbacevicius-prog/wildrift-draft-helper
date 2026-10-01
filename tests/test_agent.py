"""Agent tests with the model and MCP connection faked, so nothing calls the paid API."""

import sys
from types import SimpleNamespace

import pytest

from wildrift import agent, data


class FakeAgent:
    """Stands in for strands.Agent and records how it was built and called."""

    instances: list["FakeAgent"] = []

    def __init__(self, **kwargs):
        self.kwargs = kwargs
        self.prompts = []
        FakeAgent.instances.append(self)

    def __call__(self, prompt):
        self.prompts.append(prompt)
        return "Build: Stridebreaker, Sterak's Gage"


class FakeMCP:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def list_tools_sync(self):
        return ["get_build", "get_matchup"]


@pytest.fixture
def fake_agent(monkeypatch):
    FakeAgent.instances = []
    agent._cache.clear()
    monkeypatch.setattr(agent, "Agent", FakeAgent)
    monkeypatch.setattr(agent, "AnthropicModel", lambda **kwargs: SimpleNamespace(**kwargs))
    monkeypatch.setattr(agent, "_mcp_client", FakeMCP)
    monkeypatch.setattr(agent, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-key")
    yield FakeAgent
    agent._cache.clear()


def test_basic_prompt_and_model(fake_agent):
    result = agent.tailor_build("Darius", ["Garen", "Ahri"], position="baron")
    assert result.startswith("Build:")
    built = fake_agent.instances[0]
    assert built.kwargs["model"].model_id == "claude-haiku-4-5"
    assert built.kwargs["tools"] == ["get_build", "get_matchup"]
    prompt = built.prompts[0]
    assert "I'm playing Darius in the baron position" in prompt
    assert "Enemy team: Garen, Ahri" in prompt and "lane opponent is Garen" in prompt


def test_swaps_and_runes_reach_the_prompt(fake_agent):
    build = data.get_build("Darius")
    keystone = next(r for r, v in data.get_runes().items() if v["kind"] == "keystone" and r != build["runes"][0])
    agent.tailor_build(
        "Darius", ["Garen"], swaps=[(build["core"][0], "triforce")], runes=[keystone, *build["runes"][1:]]
    )
    prompt = fake_agent.instances[0].prompts[0]
    assert f"I replaced {build['core'][0]} with Trinity Force" in prompt
    assert f"I've set my runes to: {keystone}" in prompt


def test_unchanged_runes_are_not_mentioned(fake_agent):
    agent.tailor_build("Darius", ["Garen"], runes=data.get_build("Darius")["runes"])
    assert "set my runes" not in fake_agent.instances[0].prompts[0]


def test_cache_means_repeats_are_free(fake_agent):
    calls = []
    first = agent.tailor_build("Darius", ["Garen", "Ahri"], on_api_call=lambda: calls.append(1))
    second = agent.tailor_build("darius", ["garen", "ahri"], on_api_call=lambda: calls.append(1))
    assert first == second
    assert len(calls) == 1 and len(fake_agent.instances) == 1


def test_different_draft_is_a_new_call(fake_agent):
    calls = []
    agent.tailor_build("Darius", ["Garen"], on_api_call=lambda: calls.append(1))
    agent.tailor_build("Darius", ["Aatrox"], on_api_call=lambda: calls.append(1))
    assert len(calls) == 2


def test_cache_is_bounded(fake_agent, monkeypatch):
    monkeypatch.setattr(agent, "CACHE_SIZE", 2)
    for enemy in ("Garen", "Aatrox", "Ahri"):
        agent.tailor_build("Darius", [enemy])
    assert len(agent._cache) == 2


def test_usage_limit_blocks_before_calling_the_model(fake_agent):
    def limit_reached():
        raise RuntimeError("limit")

    with pytest.raises(RuntimeError, match="limit"):
        agent.tailor_build("Darius", ["Garen"], on_api_call=limit_reached)
    assert fake_agent.instances == []


def test_bad_input_fails_before_any_call(fake_agent):
    calls = []
    with pytest.raises(data.UnknownChampionError):
        agent.tailor_build("Darius", ["Nobody"], on_api_call=lambda: calls.append(1))
    with pytest.raises(data.UnknownItemError):
        agent.tailor_build(
            "Darius", ["Garen"], swaps=[("Stridebreaker", "Not An Item")], on_api_call=lambda: calls.append(1)
        )
    assert calls == [] and fake_agent.instances == []


def test_missing_api_key(fake_agent, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY")
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        agent.tailor_build("Darius", ["Garen"])


def test_tool_call_limit_hook(fake_agent):
    agent.tailor_build("Darius", ["Garen"])
    [hook] = fake_agent.instances[0].kwargs["hooks"]
    events = [SimpleNamespace(cancel_tool=False) for _ in range(agent.MAX_TOOL_CALLS + 1)]
    for event in events:
        hook(event)
    assert all(e.cancel_tool is False for e in events[:-1])
    assert "limit reached" in events[-1].cancel_tool


def test_cli(fake_agent, monkeypatch, capsys):
    monkeypatch.setattr(sys, "argv", ["agent", "Darius", "--enemies", "Garen", "--swap", "Stridebreaker=triforce"])
    agent.main()
    assert "Build:" in capsys.readouterr().out


def test_cli_rejects_bad_swap(fake_agent, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["agent", "Darius", "--enemies", "Garen", "--swap", "triforce"])
    with pytest.raises(SystemExit):
        agent.main()


def test_cli_reports_unknown_champion(fake_agent, monkeypatch):
    monkeypatch.setattr(sys, "argv", ["agent", "Nobody", "--enemies", "Garen"])
    with pytest.raises(SystemExit, match="Error"):
        agent.main()
