# Deployment Information

## Public URL
https://day12-ha-tang-cloud-va-deployment-production.up.railway.app

## Platform
Railway

## Test Commands

### Health Check
```bash
curl https://day12-ha-tang-cloud-va-deployment-production.up.railway.app/health
# Expected: {"status": "ok", ...}
```

### Readiness Check
```bash
curl https://day12-ha-tang-cloud-va-deployment-production.up.railway.app/ready
# Expected: {"ready": true}
```

### API Test (with API Key & user_id)
```bash
curl -X POST https://day12-ha-tang-cloud-va-deployment-production.up.railway.app/ask \
  -H "X-API-Key: dev-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test_user", "question": "My name is Alice"}'
```

### Context-Aware Conversation Check
```bash
curl -X POST https://day12-ha-tang-cloud-va-deployment-production.up.railway.app/ask \
  -H "X-API-Key: dev-key-change-me" \
  -H "Content-Type: application/json" \
  -d '{"user_id": "test_user", "question": "What is my name?"}'
```

## Environment Variables Set
- `PORT` (8000)
- `REDIS_URL` (redis://redis:6379/0)
- `AGENT_API_KEY` (dev-key-change-me)
- `ENVIRONMENT` (production)
- `DEBUG` (false)

## Screenshots
- [Deployment dashboard](screenshots/dashboard.png)
- [Service running](screenshots/running.png)
- [Test results](screenshots/test.png)
