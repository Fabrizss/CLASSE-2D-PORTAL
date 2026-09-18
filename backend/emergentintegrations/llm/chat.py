from google import genai


class UserMessage:
    def __init__(self, text: str):
        self.text = text


class LlmChat:
    """Compatibility wrapper for the former private Emergent SDK."""

    def __init__(self, api_key, session_id: str, system_message: str):
        self.api_key = api_key
        self.system_message = system_message
        self.model = "gemini-2.5-flash"

    def with_model(self, _provider: str, model: str):
        self.model = model
        return self

    async def send_message(self, message: UserMessage) -> str:
        if not self.api_key:
            raise RuntimeError("EMERGENT_LLM_KEY non configurata")
        client = genai.Client(api_key=self.api_key)
        response = await client.aio.models.generate_content(
            model=self.model,
            contents=message.text,
            config={"system_instruction": self.system_message},
        )
        return response.text or ""
