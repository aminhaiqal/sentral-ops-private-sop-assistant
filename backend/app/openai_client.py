from openai import APIStatusError, OpenAI

from app.config import Settings


class OpenAINotConfigured(RuntimeError):
    pass


def provider_error_message(error: APIStatusError) -> str:
    # Never return the provider's raw message: authentication errors can contain keys.
    if error.status_code == 401:
        return "The server's AI API key was rejected. An administrator needs to check its key and API provider."
    if error.status_code == 403:
        return "The server's AI access was denied. An administrator needs to check its API permissions."
    if error.status_code == 402 or (
        error.status_code == 429
        and error.code
        in {
            "insufficient_quota",
            "credit_balance_exhausted",
            "organization_spend_limit_exceeded",
            "project_spend_limit_exceeded",
            "organization_usage_limit_exceeded",
        }
    ):
        return "AI usage is unavailable. An administrator needs to check the API account's credits and limits."
    return "The AI service is temporarily unavailable. Try again later."


class OpenAIClient:
    def __init__(self, settings: Settings):
        if not settings.openai_api_key:
            raise OpenAINotConfigured(
                "An administrator needs to configure the server's AI API key."
            )
        self.settings = settings
        self.client = OpenAI(api_key=settings.openai_api_key, base_url=settings.openai_base_url)

    def embed_texts(self, texts: list[str]) -> list[list[float]]:
        if not texts:
            return []

        response = self.client.embeddings.create(
            model=self.settings.openai_embedding_model,
            input=texts,
            encoding_format="float",
        )
        return [item.embedding for item in response.data]

    def generate_answer(self, system_prompt: str, user_prompt: str) -> str:
        parameters = {}
        model_name = self.settings.openai_chat_model.removeprefix("openai/")
        if model_name.startswith("gpt-6"):
            effort = self.settings.openai_reasoning_effort
            if effort == "none" and model_name.startswith(("gpt-6-astra", "gpt-6.1-sol")):
                effort = "low"
            parameters["reasoning_effort"] = effort
            if effort == "none":
                parameters["temperature"] = 0.1
        else:
            parameters["temperature"] = 0.1

        response = self.client.chat.completions.create(
            model=self.settings.openai_chat_model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            **parameters,
        )
        return response.choices[0].message.content or ""
