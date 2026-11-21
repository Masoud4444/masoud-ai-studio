from backend.app.api import post_task, router


def test_post_tasks_route_is_bound_to_task_creation_handler():
    matches = [
        route for route in router.routes
        if getattr(route, "path", None) == "/api/v1/tasks"
        and "POST" in getattr(route, "methods", set())
    ]
    assert len(matches) == 1
    assert matches[0].endpoint is post_task
