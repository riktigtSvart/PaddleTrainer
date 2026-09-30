# Paddle Coach MVP

Első futtatható backend-váz kajak-központú edzéstervező rendszerhez, Polar AccessLink Dynamic API v4 integrációval.

## Mit tartalmaz?

- FastAPI backend
- PostgreSQL + SQLAlchemy async
- Polar OAuth2 connect/callback
- titkosított access/refresh token tárolás
- Polar training-session import
- tervezett edzések + strukturált workout blockok
- Docker Compose PostgreSQL
- Alembic konfiguráció
- Swagger/OpenAPI UI

> Ez egy fejlesztői MVP. A felhasználói auth jelenleg szándékosan egyetlen demo userrel működik. A Polar token refresh és a teljes training-target normalizálás a következő lépés.

## 1. Polar kliens létrehozása

Hozz létre AccessLink klienst a Polar admin felületén, és add meg redirect URL-ként:

`http://localhost:8000/api/v1/integrations/polar/callback`

Szükséges scope-ok:

- `training_sessions:read`
- `training_targets:read`
- `sports:read`

## 2. Környezeti változók

```bash
cp .env.example .env
```

Töltsd ki legalább:

```dotenv
POLAR_CLIENT_ID=...
POLAR_CLIENT_SECRET=...
```

Éles környezethez generálj Fernet kulcsot:

```bash
python -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

és tedd `TOKEN_ENCRYPTION_KEY` alá.

## 3. PostgreSQL indítása

```bash
docker compose up -d db
```

## 4. Backend telepítés

```bash
cd apps/api
python -m venv .venv
source .venv/bin/activate   # Windows: .venv\\Scripts\\activate
pip install -e .[dev]
```

## 5. Adatbázis migrálása

A kezdeti migráció már a repository része:

```bash
alembic upgrade head
```

## 6. API indítása

A repository gyökerében lévő `.env` változókat exportáld, vagy másold az `apps/api/.env` fájlba, majd:

```bash
uvicorn app.main:app --reload --port 8000
```

Swagger:

`http://localhost:8000/docs`

## Fontos endpointok

- `GET /api/v1/health`
- `GET /api/v1/integrations/polar/connect`
- `GET /api/v1/integrations/polar/status`
- `POST /api/v1/integrations/polar/sync?days=30`
- `GET /api/v1/workouts`
- `POST /api/v1/workouts`

### Minta edzés létrehozása

```json
{
  "date": "2026-10-03",
  "sport": "KAYAK",
  "title": "4x8 perc küszöb",
  "duration_sec": 4200,
  "intensity_type": "HR_ZONE",
  "blocks": [
    {
      "position": 0,
      "block_type": "WARMUP",
      "name": "Bemelegítés",
      "duration_sec": 900,
      "intensity_type": "HR_ZONE",
      "intensity_min": 1,
      "intensity_max": 2
    },
    {
      "position": 1,
      "block_type": "REPEAT",
      "name": "4x8 küszöb",
      "repeat_count": 4
    },
    {
      "position": 2,
      "block_type": "COOLDOWN",
      "name": "Levezetés",
      "duration_sec": 600,
      "intensity_type": "HR_ZONE",
      "intensity_min": 1,
      "intensity_max": 1
    }
  ]
}
```

## Polar v4 implementációs megjegyzések

A kód a jelenlegi Dynamic API v4 végpontokra épül:

- OAuth authorize: `https://auth.polar.com/oauth/authorize`
- OAuth token: `https://auth.polar.com/oauth/token`
- Data base URL: `https://www.polaraccesslink.com/v4/data`
- sessions: `/training-sessions/list`
- targets: `/training-target/calendar-targets`
- sport profiles: `/sports/profiles`

Az AccessLink access token 12 órás. A szinkron service lejárat előtt automatikusan refresh tokent kér és frissíti a titkosított tokeneket.

## Következő fejlesztési lépések

1. training target import és normalizálás
2. session -> planned workout matching
4. RPE endpoint
5. heti load endpoint
6. Next.js naptár + workout builder UI
7. recovery/sleep integráció
