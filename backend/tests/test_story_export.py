from backend.app.story_export import render_fountain


def test_fountain_export_preserves_order_and_screenplay_content():
    text = render_fountain(
        {"title": "The Signal", "logline": "A signal changes everything."},
        [
            {"position": 2, "title": "The reply", "slugline": "ext. tower - night", "summary": "A reply arrives.", "dramatic_purpose": "Raise the stakes", "beats": '["A light flashes"]', "body": "MIRA\nWe have a reply."},
            {"position": 1, "title": "First contact", "slugline": "int. lab - day", "summary": None, "dramatic_purpose": None, "beats": [], "body": "The monitor flickers."},
        ],
    )
    assert text.startswith("Title: The Signal\nLogline: A signal changes everything.")
    assert text.index("INT. LAB - DAY") < text.index("EXT. TOWER - NIGHT")
    assert "[[Dramatic purpose: Raise the stakes]]" in text
    assert "MIRA\nWe have a reply." in text


def test_fountain_export_handles_empty_story_and_malformed_beats():
    text = render_fountain({"title": "  "}, [{"position": 1, "title": "Opening", "beats": "not-json", "body": None}])
    assert text.startswith("Title: Untitled Story")
    assert "[[Scene 1: Opening]]" in text
    assert "not-json" not in text
