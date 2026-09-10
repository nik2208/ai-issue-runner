import pytest
from httpx import AsyncClient, ASGITransport
from ai_runner.server.app import create_app
from ai_runner.types import StructuredPlan, AcceptanceCriterion

@pytest.fixture
def app():
    return create_app()

@pytest.mark.asyncio
async def test_server_auth_status(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get("/auth/status")
        assert resp.status_code == 200
        data = resp.json()
        assert "google" in data
        assert "anthropic" in data
        assert "openai" in data

@pytest.mark.asyncio
async def test_server_set_api_key(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.post("/auth/apikey", json={
            "provider": "anthropic",
            "api_key": "sk-ant-test-key"
        })
        assert resp.status_code == 200
        assert resp.json()["auth_mode"] == "api_key"

        status_resp = await client.get("/auth/status")
        assert status_resp.json()["anthropic"]["authenticated"] is True

@pytest.mark.asyncio
async def test_server_job_lifecycle(app, tmp_path):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        plan = StructuredPlan(
            task_id="TEST-JOB-1",
            title="Fast job test",
            summary="Test creating a job via API",
            acceptance_criteria=[
                AcceptanceCriterion(
                    id="echo_test",
                    description="Echo test",
                    command="echo test",
                    expected_exit_code=0
                )
            ]
        )

        resp = await client.post("/api/jobs", json=plan.model_dump(), params={"workspace_dir": str(tmp_path)})
        assert resp.status_code == 200
        job_data = resp.json()
        assert "id" in job_data
        assert job_data["plan"]["task_id"] == "TEST-JOB-1"

        # Query job
        get_resp = await client.get(f"/api/jobs/{job_data['id']}")
        assert get_resp.status_code == 200

@pytest.mark.asyncio
async def test_server_webhook_github_issue(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "action": "opened",
            "issue": {
                "number": 42,
                "title": "Fix memory leak in parser",
                "body": "Parser leaks 50MB when reading large JSON files.",
                "labels": [{"name": "ai-run"}]
            },
            "repository": {"full_name": "org/repo"}
        }

        resp = await client.post(
            "/api/webhook/github",
            json=payload,
            headers={"X-GitHub-Event": "issues"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "enqueued"
        assert "job_id" in data

@pytest.mark.asyncio
async def test_server_webhook_gitea_issue(app):
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        payload = {
            "action": "opened",
            "issue": {
                "number": 105,
                "title": "Gitea bug report: auth token refresh",
                "body": "Token refresh fails on Gitea.",
                "labels": [{"name": "ai-run"}]
            },
            "repository": {"full_name": "gitea-user/my-repo"}
        }

        resp = await client.post(
            "/api/webhook/gitea",
            json=payload,
            headers={"X-Gitea-Event": "issues"}
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "enqueued"
        assert data["task_id"] == "GH-105"
