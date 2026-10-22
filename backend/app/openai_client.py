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
