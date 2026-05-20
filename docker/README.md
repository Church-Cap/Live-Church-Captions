# Docker

Docker support is mainly for development and Linux-style testing. Native macOS running is recommended for church use because audio capture is simpler outside Docker.

From the project root:

```bash
cp .env.example .env
docker compose -f docker/docker-compose.yml up --build
```

The compose file builds from the project root and uses `docker/Dockerfile`.
