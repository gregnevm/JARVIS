from app.ps_whitelist import check_ps_whitelist


def test_blocks_pipe_operator(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "ps_whitelist", "Write-Output")
    assert check_ps_whitelist("Write-Output 1 | Remove-Item x") is not None


def test_allows_multistatement_whitelist(monkeypatch):
    from app.config import settings

    monkeypatch.setattr(settings, "ps_whitelist", "Stop-Service,Start-Service")
    assert check_ps_whitelist("Stop-Service x; Start-Service x") is None
