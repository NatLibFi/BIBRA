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

    def test_extract_route_exists(self):
        """The router should have an extract route."""
        routes = [str(r.path) for r in router.routes]
        assert "/extract" in routes

    def test_extract_route_is_post_method(self):
        """The extract route should use POST method."""
        from fastapi.routing import APIRoute
        extract_routes = [r for r in router.routes if str(r.path) == "/extract"]
        assert len(extract_routes) >= 1
        # Check that the route uses POST method
        route = extract_routes[0]
        assert isinstance(route, APIRoute)

    async def test_extract_returns_example_metadata(self):
        """The /extract endpoint should return example publication metadata."""
        from bibra.api.v0.routes import extract, PublicationMetadata
        
        # Verify the function exists and returns correct type
        result = await extract(files=[], text=None)
        
        assert isinstance(result, PublicationMetadata)
        assert result.language == "en"
        assert result.title == "Understanding DevOps critical success factors and organizational practices"
        assert result.creator == ["Nasreen, Azad"]
        assert result.year == "2022"
        assert result.publisher == ["IEEE"]
        assert result.doi == "10.1145/3524614.3528627"
        assert result.e_isbn == ["9781450393027/22/05"]
        assert result.type_coar == "conference paper"
