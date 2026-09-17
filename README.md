# VisionAI FaceShield 🛡️

Sistema de **reconhecimento facial automático** para monitoramento de ambientes: detecta pessoas que circulam no local e **cadastra cada pessoa apenas uma vez** no banco de dados, com dashboard web em tempo real.

---

## Como funciona

1. **Detecção contínua** — InsightFace (ArcFace 512-d) analisa frames das câmeras (USB, RTSP/IP, A9 Wi-Fi, webcam do navegador ou vídeos do YouTube).
2. **Registro único garantido** — um desconhecido só é cadastrado no banco após ser **confirmado em 2+ avistamentos** com qualidade mínima. Um lock serializa todo o pipeline: fontes concorrentes nunca duplicam cadastros.
3. **Reconhecimento instantâneo** — todos os embeddings ficam em cache em memória (matriz NumPy); pessoas conhecidas são identificadas e logadas respeitando o *cooldown* configurável.
4. **Presença real** — sessões de presença no PostgreSQL abrem/fecham automaticamente conforme as pessoas entram e saem do ambiente.
5. **Eventos em tempo real** — o dashboard recebe eventos via SSE: nova pessoa registrada → toast com ação **[Nomear]**.

## Principais recursos

- **InsightFace ArcFace 512-d** com embeddings que evoluem por média móvel (robustez a luz/ângulo)
- **PostgreSQL + pgvector** com fallback transparente para SQLite
- **Múltiplas fontes**: webcam USB do servidor, webcam do navegador, câmeras RTSP/IP (reconexão automática), câmera Wi-Fi A9, vídeos do YouTube (yt-dlp)
- **Agente IA opcional** (OpenAI): insights comportamentais ao vivo + resumo executivo — desativa sozinho sem `OPENAI_API_KEY`
- **Dashboard escuro** com abas Ao Vivo / YouTube / RTSP / Cadastro / Pessoas / Analytics / Logs / Configurações
- **Limpeza automática** de imagens antigas (retenção configurável)

## Estrutura

```
reconhecimento_facial/
├── web_server.py              # App FastAPI (composition root)
├── config.py                  # Configurações centralizadas (.env)
├── core/
│   ├── recognition_service.py # ⭐ Pipeline único: detect→match→register/log (anti-duplicação)
│   ├── face_cache.py          # Cache de embeddings em memória (match vetorizado)
│   ├── presence_service.py    # Sessões de presença no banco
│   ├── events.py              # Barramento de eventos SSE
│   ├── camera_manager.py      # Câmera ao vivo (captura ⟂ inferência desacoplados)
│   ├── youtube_service.py     # Download yt-dlp + análise via pipeline unificado
│   ├── face_engine.py         # Singleton InsightFace
│   ├── rtsp_consumer.py       # Consumidor multithread de câmeras RTSP
│   ├── cleanup.py             # Expurgo periódico de imagens
│   ├── database.py            # Postgres/pgvector + fallback SQLite
│   └── models.py              # Person, VerificationLog, PresenceSession, RTSPStream, AppSettings
├── routers/                   # Endpoints REST/SSE (camada fina)
├── static/                    # Dashboard SPA (vanilla JS + CSS)
├── ai_agent/                  # Agente OpenAI opcional (lazy)
└── data/                      # faces/, frames/ (volume Docker)
```

## Execução com Docker (recomendado)

```bash
cp .env.example .env      # edite se necessário (OPENAI_API_KEY é opcional)
docker compose up -d --build
```

Acesse **http://localhost:8000** (porta ajustável via `APP_PORT` no `.env`).

> ⚠️ No primeiro boot o modelo InsightFace (~330 MB) é baixado uma única vez para o volume `insightface-models`.

Para começar com banco limpo:

```bash
docker compose down -v && docker compose up -d --build
```

### Health checks

```bash
curl http://localhost:8000/health        # {"status":"healthy", ...}
docker compose ps                        # ambos os serviços healthy
```

## Execução local (sem Docker)

```bash
pip install -r requirements.txt
copy .env.example .env           # ajuste DATABASE_URL se tiver Postgres local
python web_server.py
```

Sem PostgreSQL acessível o sistema cai automaticamente para SQLite (`data/faceshield_local.db`).

## API principal

| Método | Rota | Descrição |
|---|---|---|
| `POST` | `/api/v1/verify` | Imagem → detecção + reconhecimento/cadastro |
| `POST` | `/api/v1/persons/register` | Cadastro manual nomeado (base64) |
| `GET/PUT/DELETE` | `/api/v1/persons/{id}` | Perfil, renomear, excluir |
| `GET` | `/api/v1/persons/{id}/logs` | Histórico da pessoa |
| `GET/POST` | `/api/v1/streams` | Câmeras RTSP (+ `/start`, `/stop`) |
| `POST` | `/api/v1/youtube/process` | Análise de vídeo YouTube (SSE) |
| `POST` | `/api/v1/local_camera/analyze_frame` | Webcam do navegador |
| `GET/PUT` | `/api/v1/settings` | Threshold, cooldown, min_sightings, etc. |
| `GET` | `/api/stats` · `/api/logs` · `/api/presence` | Dashboard |
| `GET` | `/api/events` | Eventos em tempo real (SSE) |
| `GET` | `/api/video_feed` | MJPEG ao vivo com HUD |
| `GET` | `/health` | Health check |

Documentação interativa: **http://localhost:8000/docs**

## Configuração (.env)

| Variável | Padrão | Descrição |
|---|---|---|
| `DATABASE_URL` | postgres no host `db` | Conexão asyncpg |
| `SIMILARITY_THRESHOLD` | 0.65 | Distância cosseno máxima p/ considerar a mesma pessoa |
| `MIN_SIGHTINGS` | 2 | Avistamentos antes do cadastro automático |
| `COOLDOWN_MINUTES` | 60 | Intervalo mínimo entre logs da mesma pessoa |
| `PRESENCE_TIMEOUT_SECONDS` | 30 | Ausência de detecção = pessoa saiu |
| `DET_SIZE` | 320 | 320 mais rápido | 640 equilibrado | 1280 melhora rostos distantes (mais lento) |
| `IMAGE_RETENTION_HOURS` | 48 | Expurgo de imagens |
| `OPENAI_API_KEY` | vazio | Ativa insights/resumos do agente IA |

## Testes

```bash
pip install pytest pytest-asyncio
pytest tests/ -v
```
