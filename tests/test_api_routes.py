"""Tests for API routes."""
from bibra.api.v0.routes import router


class TestAPIRoutes:
    """Tests for API v0 routes."""

    def test_root_route_exists(self):
        """The router should have a root route."""
        assert len(router.routes) >= 1

    def test_projects_route_exists(self):
        """The router should have a projects route."""
        routes = [str(r.path) for r in router.routes]
        assert "/projects" in routes

    async def test_list_projects_returns_correct_data(self):
        """The /projects endpoint should return the expected project data."""
        import asyncio
        from bibra.api.v0.routes import list_projects, PROJECTS

        result = await list_projects()
        assert "projects" in result
        assert len(result["projects"]) == len(PROJECTS)
        assert result["projects"][0]["id"] == "project-001"
        assert result["projects"][0]["name"] == "Example Project Alpha"
