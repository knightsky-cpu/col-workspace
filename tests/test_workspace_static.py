import httpx
import pytest

import main


def css_rule(css: str, selector: str) -> str:
    marker = f"{selector} {{"
    blocks = []
    remainder = css
    while marker in remainder:
        _, remainder = remainder.split(marker, maxsplit=1)
        block, remainder = remainder.split("}", maxsplit=1)
        blocks.append(block)
    return "\n".join(blocks)


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
    assert response.headers["cache-control"] == "no-store"
    assert "<h1>Agent Col" in response.text
    assert "data-workspace-indicator" in response.text
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
    assert "Work review" not in response.text
    assert 'aria-label="Artifacts Viewer"' in response.text
    assert "<h2>Artifacts Viewer</h2>" in response.text
    assert "Show Artifacts Viewer" in response.text
    assert "Expand Artifacts Viewer" in response.text
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
    assert "data-left-refresh" in response.text
    assert "data-work-refresh" not in response.text
    assert "data-memory-panel" in response.text
    assert "data-memory-refresh" not in response.text
    assert "data-memory-error" in response.text
    supporting_panel = response.text.split(
        '<aside class="supporting-panel"',
        maxsplit=1,
    )[1].split("</aside>", maxsplit=1)[0]
    assert 'class="supporting-panel__body"' in supporting_panel
    assert "data-activity-list" not in response.text
    assert "data-chats-list" in response.text
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
    assert css_response.headers["cache-control"] == "no-store"
    assert js_response.status_code == 200
    assert "javascript" in js_response.headers["content-type"]
    assert js_response.headers["cache-control"] == "no-store"
    assert ".contain-text" in css_response.text
    assert "overflow-wrap: anywhere" in css_response.text
    assert "grid-template-areas" in css_response.text
    assert ".conversation" in css_response.text
    assert "grid-area: conversation" in css_response.text
    assert "minmax(20rem, 1fr)" in css_response.text
    assert "grid-template-rows: auto minmax(0, 1fr) auto" in css_response.text
    assert ".supporting-panel__body" in css_response.text
    assert ".work-panel__body" in css_response.text
    assert "overflow: auto" in css_response.text
    assert "80vw" in css_response.text
    assert ".workspace-grid--artifacts-expanded" in css_response.text
    assert ".workspace-grid--right-collapsed .conversation" not in css_response.text
    assert ".workspace-grid--right-collapsed .composer" not in css_response.text
    assert ".workspace-grid--right-collapsed .conversation-footer" not in css_response.text
    collapsed_left = css_response.text.split(
        ".workspace-grid--left-collapsed",
        maxsplit=1,
    )[1].split(".workspace-grid--right-collapsed", maxsplit=1)[0]
    assert ".conversation" not in collapsed_left
    assert ".composer" not in collapsed_left
    assert ".conversation-footer" not in collapsed_left


@pytest.mark.asyncio
async def test_workspace_surfaces_have_independent_scroll_ownership() -> None:
    transport = httpx.ASGITransport(app=main.app)
    async with httpx.AsyncClient(
        transport=transport,
        base_url="http://testserver",
    ) as client:
        css_response = await client.get("/static/agent-col/styles.css")

    assert css_response.status_code == 200
    css = css_response.text

    shell_rule = css_rule(css, ".workspace-shell")
    grid_rule = css_rule(css, ".workspace-grid")
    supporting_body_rule = css_rule(css, ".supporting-panel__body")
    transcript_rule = css_rule(css, ".chat-transcript")
    work_body_rule = css_rule(css, ".work-panel__body")

    assert "height: 100vh" in shell_rule
    assert "overflow: hidden" in shell_rule
    assert "flex: 1 1 0" in grid_rule
    assert "height: 0" in grid_rule
    assert "align-items: stretch" in grid_rule

    for surface_rule in (
        supporting_body_rule,
        transcript_rule,
        work_body_rule,
    ):
        assert "min-height: 0" in surface_rule
        assert "overflow-y: auto" in surface_rule
        assert "overscroll-behavior: contain" in surface_rule
        assert "scrollbar-gutter: stable" in surface_rule

    conversation_rule = css_rule(css, ".conversation")
    footer_rule = css_rule(css, ".conversation-footer")
    assert "max-height: 100%" in conversation_rule
    assert "overflow: hidden" in conversation_rule
    assert "position: sticky" not in footer_rule
    assert "position: fixed" not in footer_rule


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
