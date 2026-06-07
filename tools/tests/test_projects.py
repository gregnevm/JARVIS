"""project_prompt_block / project_files_block (P1.7)."""
from app.projects import project_files_block, project_prompt_block


def test_project_files_block_empty():
    assert project_files_block([]) == ""


def test_project_files_block_formats():
    block = project_files_block([{"name": "spec.md", "content": "hello"}])
    assert "Файли проєкту" in block
    assert "--- spec.md ---" in block
    assert "hello" in block


def test_project_prompt_block_with_files():
    proj = {
        "name": "Demo",
        "system_prompt": "be brief",
        "files_content": [{"name": "a.txt", "content": "data"}],
    }
    block = project_prompt_block(proj)
    assert "Demo" in block
    assert "be brief" in block
    assert "a.txt" in block
    assert "data" in block
