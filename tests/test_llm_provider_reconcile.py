"""reconcile_worker_provider_label: etiqueta alineada con ChatOpenAI real (DeepSeek vs MLX)."""

from duckclaw.integrations.llm_providers import (
    failure_provider_label_for_llm_invoke,
    infer_provider_from_openai_compatible_llm,
    reconcile_worker_provider_label,
)


class _FakeOpenAIClient:
    def __init__(self, base_url: str) -> None:
        self.base_url = base_url


class _FakeChatOpenAILike:
    def __init__(self, base_url: str) -> None:
        self.client = _FakeOpenAIClient(base_url)


def test_infer_deepseek_from_client_base_url() -> None:
    llm = _FakeChatOpenAILike("https://api.deepseek.com/v1")
    assert infer_provider_from_openai_compatible_llm(llm) == "deepseek"


class _NonStrUrl:
    """Simula tipos URL de Pydantic/LangChain que no son ``str`` pero ``str()`` devuelve la URL."""

    def __str__(self) -> str:
        return "https://api.deepseek.com/v1"


class _FakeChatOpenAINonStrBaseUrl:
    def __init__(self) -> None:
        self.base_url = _NonStrUrl()
        self.model_name = "deepseek-chat"


def test_infer_deepseek_when_base_url_attribute_is_not_str() -> None:
    llm = _FakeChatOpenAINonStrBaseUrl()
    assert infer_provider_from_openai_compatible_llm(llm) == "deepseek"


def test_reconcile_overrides_mlx_label_when_url_is_deepseek() -> None:
    llm = _FakeChatOpenAILike("https://api.deepseek.com/v1")
    assert reconcile_worker_provider_label(llm, "mlx", "mlx") == "deepseek"


def test_reconcile_respects_explicit_deepseek() -> None:
    llm = _FakeChatOpenAILike("https://api.deepseek.com/v1")
    assert reconcile_worker_provider_label(llm, "mlx", "deepseek") == "deepseek"


def test_infer_follows_runnable_binding_like_wrapper() -> None:
    """RunnableBinding expone .bound → ChatOpenAI; infer no debe devolver vacío."""
    inner = _FakeChatOpenAILike("https://api.deepseek.com/v1")

    class _LikeBinding:
        __slots__ = ("bound",)

        def __init__(self, b: object) -> None:
            self.bound = b

    assert infer_provider_from_openai_compatible_llm(_LikeBinding(inner)) == "deepseek"


def test_failure_label_prefers_inferred_deepseek_over_mlx_tag() -> None:
    llm = _FakeChatOpenAILike("https://api.deepseek.com/v1")
    assert failure_provider_label_for_llm_invoke(llm, "mlx") == "deepseek"


def test_failure_label_remote_triplet_wins_over_spurious_mlx_infer() -> None:
    """Si infer ve localhost en algún cliente pero /model compiló deepseek, no culpar MLX."""
    llm = _FakeChatOpenAILike("http://127.0.0.1:8080/v1")
    assert failure_provider_label_for_llm_invoke(llm, "deepseek") == "deepseek"


def test_failure_label_remote_wins_over_iotcorelabs_infer() -> None:
    class _FakeIot:
        client = _FakeOpenAIClient("http://127.0.0.1:8080/v1")

    assert failure_provider_label_for_llm_invoke(_FakeIot(), "deepseek") == "deepseek"


def test_failure_label_env_llm_provider_overrides_stale_local_out(monkeypatch) -> None:
    """Si rec/inf dejan out en mlx pero LLM_PROVIDER declara remoto, no culpar MLX."""
    monkeypatch.setenv("DUCKCLAW_LLM_PROVIDER", "mlx")
    monkeypatch.setenv("LLM_PROVIDER", "deepseek")
    llm = _FakeChatOpenAILike("http://127.0.0.1:8080/v1")
    assert failure_provider_label_for_llm_invoke(llm, "mlx") == "deepseek"


class _FakeChatOpenAIModelOnly:
    """Simula ChatOpenAI antes del primer invoke (sin client.base_url poblado)."""

    def __init__(self, model: str) -> None:
        self.model_name = model


def test_infer_deepseek_from_model_when_no_base_url() -> None:
    llm = _FakeChatOpenAIModelOnly("deepseek-chat")
    assert infer_provider_from_openai_compatible_llm(llm) == "deepseek"


def test_failure_label_model_only_deepseek_over_mlx() -> None:
    llm = _FakeChatOpenAIModelOnly("deepseek-chat")
    assert failure_provider_label_for_llm_invoke(llm, "mlx") == "deepseek"


def test_infer_binding_inner_model_only_when_no_url() -> None:
    inner = _FakeChatOpenAIModelOnly("deepseek-chat")

    class _LikeBinding:
        __slots__ = ("bound",)

        def __init__(self, b: object) -> None:
            self.bound = b

    assert infer_provider_from_openai_compatible_llm(_LikeBinding(inner)) == "deepseek"
