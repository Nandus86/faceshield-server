"""Optional AI analyst (OpenAI) — lazily initialized.

Provides two features when OPENAI_API_KEY is configured:
- Per-detection behavioral insights shown live on the dashboard.
- On-demand executive summary of system activity.

Without an API key everything degrades gracefully: the rest of the
system is unaffected.
"""

import logging
import os
import threading

import config

logger = logging.getLogger(__name__)


class FacialRecognitionAgent:
    """Thin OpenAI-backed analyst with lazy initialization."""

    def __init__(self):
        self._client = None
        self._init_attempted = False
        self._lock = threading.Lock()
        self.enabled = False

    def _ensure_client(self) -> bool:
        if self.enabled:
            return True
        with self._lock:
            if self.enabled:
                return True
            if self._init_attempted:
                return False

            settings = config.get_settings()
            if not settings.AGENT_ENABLED:
                logger.info("Agente de IA desativado nas configurações.")
                self._init_attempted = True
                return False

            api_key = os.getenv("OPENAI_API_KEY", "").strip()
            if not api_key or api_key.startswith("sk-seu"):
                logger.info("OPENAI_API_KEY ausente; insights de IA desativados.")
                self._init_attempted = True
                return False

            try:
                from openai import OpenAI
                self._client = OpenAI(api_key=api_key)
                self._model = os.getenv("OPENAI_MODEL", settings.AGENT_MODEL)
                self.enabled = True
                logger.info("Agente de IA inicializado (modelo=%s).", self._model)
            except Exception as err:
                logger.warning("Falha ao iniciar Agente de IA: %s", err)
            self._init_attempted = True
            return self.enabled

    def _ask(self, system_prompt: str, user_prompt: str) -> str:
        response = self._client.chat.completions.create(
            model=self._model,
            temperature=0.7,
            max_tokens=200,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
        )
        return (response.choices[0].message.content or "").strip()

    def analyze_detection(self, name: str, is_registered: bool) -> dict:
        """Brief insight about one detection event."""
        if not self._ensure_client():
            return {"analysis": "", "insights": [], "alerts": []}
        try:
            status = "cadastrada" if is_registered else "NÃO cadastrada"
            analysis = self._ask(
                "Você é um assistente de reconhecimento facial. Analise a detecção "
                "e forneça um insight breve e útil em português. Use emojis "
                "(✅ ⚠️ 📊 ⏱️). Seja conciso (máximo 2 frases).",
                f"Pessoa '{name}' detectada. Status: {status}.",
            )
            return {"analysis": analysis, "insights": [], "alerts": []}
        except Exception as err:
            logger.debug("Erro na análise LLM: %s", err)
            return {"analysis": "", "insights": [], "alerts": []}

    def get_summary(self) -> str:
        """Executive summary of current activity."""
        if not self._ensure_client():
            return ""
        try:
            return self._ask(
                "Você é um assistente de análise de reconhecimento facial. "
                "Forneça um resumo conciso da situação atual. Use emojis e seja objetivo.",
                "Forneça um resumo da situação atual de visitantes do sistema.",
            )
        except Exception as err:
            logger.debug("Erro ao gerar resumo: %s", err)
            return ""


_agent: FacialRecognitionAgent | None = None


def get_agent() -> FacialRecognitionAgent | None:
    """Module-level accessor returning the agent only when usable."""
    global _agent
    if _agent is None:
        _agent = FacialRecognitionAgent()
    return _agent if _agent._ensure_client() else None
