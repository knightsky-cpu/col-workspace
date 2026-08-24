import httpx
import pytest

import main


@pytest.mark.asyncio
async def test_workspace_route_serves_html_shell() -> None:
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.get("/workspace")

    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert "<h1>Agent Col</h1>" in response.text
    assert "Ask Agent Col for help" in response.text
    assert ">Agent_Col<" not in response.text
    assert "Ask Agent_Col" not in response.text
    assert '<main id="conversation-workspace"' in response.text
    assert 'src="/static/agent-col/app.mjs"' in response.text
    assert 'href="/static/agent-col/styles.css"' in response.text
    assert "data-chat-form" in response.text
    assert 'name="message"' in response.text
    assert "data-chat-transcript" in response.text
    assert "data-chat-status" in response.text
    assert "data-retry-turn" in response.text
    assert 'data-drawer-toggle="left"' in response.text
    assert 'data-drawer-toggle="right"' in response.text
    header = response.text.split("</header>", maxsplit=1)[0]
    assert "data-drawer-toggle" not in header
    supporting_panel = response.text.split(
        '<aside class="supporting-panel"',
        maxsplit=1,
    )[1].split("</aside>", maxsplit=1)[0]
    assert 'data-drawer-toggle="left"' in supporting_panel
    work_panel = response.text.split(
        '<aside class="work-panel"',
        maxsplit=1,
    )[1].split("</aside>", maxsplit=1)[0]
    assert 'data-drawer-toggle="right"' in work_panel
    assert "data-work-list" in response.text
    assert "data-work-detail" in response.text
    assert "data-work-error" in response.text
    assert "data-work-refresh" in response.text
    assert "data-memory-panel" in response.text
    assert "data-memory-refresh" in response.text
    assert "data-memory-error" in response.text
    assert "data-activity-list" in response.text
    assert "https://" not in response.text
    assert "http://" not in response.text


@pytest.mark.asyncio
async def test_workspace_static_assets_are_local() -> None:
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        css_response = await client.get("/static/agent-col/styles.css")
        js_response = await client.get("/static/agent-col/app.mjs")

    assert css_response.status_code == 200
    assert "text/css" in css_response.headers["content-type"]
    assert js_response.status_code == 200
    assert "javascript" in js_response.headers["content-type"]
    assert ".contain-text" in css_response.text
    assert "overflow-wrap: anywhere" in css_response.text
    assert "grid-template-areas" in css_response.text
    assert ".conversation" in css_response.text
    assert "grid-area: conversation" in css_response.text
    collapsed_left = css_response.text.split(
        ".workspace-grid--left-collapsed",
        maxsplit=1,
    )[1].split(".workspace-grid--right-collapsed", maxsplit=1)[0]
    assert ".conversation" not in collapsed_left
    assert ".composer" not in collapsed_left


@pytest.mark.asyncio
async def test_health_route_remains_json_liveness_contract() -> None:
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        response = await client.get("/")

    assert response.status_code == 200
    assert response.json() == {"status": "online"}
