from app.services.pipeline_orchestrator import PipelineOrchestrator


class _StubAgent:
    def __init__(self, name: str, result: dict, calls: list[tuple[str, int]]) -> None:
        self.name = name
        self.result = result
        self.calls = calls

    def run(self, limit: int) -> dict:
        self.calls.append((self.name, limit))
        return self.result


def test_run_cycle_stops_after_first_agent_that_did_work(monkeypatch):
    calls: list[tuple[str, int]] = []

    monkeypatch.setattr(
        "app.services.pipeline_orchestrator.build_trailer_finder_agent",
        lambda: _StubAgent("trailer_finder", {"processed": 1, "completed": 1, "failed": 0}, calls),
    )
    monkeypatch.setattr(
        "app.services.pipeline_orchestrator.build_review_script_agent",
        lambda: _StubAgent("review_script", {"processed": 1, "completed": 1, "failed": 0}, calls),
    )
    monkeypatch.setattr("app.services.pipeline_orchestrator.settings.voice_mode", "auto")
    monkeypatch.setattr("app.services.pipeline_orchestrator.settings.source_video_mode", "auto")

    orchestrator = PipelineOrchestrator()
    orchestrator.run_cycle()

    assert calls == [("trailer_finder", 1)]


def test_run_cycle_falls_through_until_first_agent_that_did_work(monkeypatch):
    calls: list[tuple[str, int]] = []

    monkeypatch.setattr(
        "app.services.pipeline_orchestrator.build_trailer_finder_agent",
        lambda: _StubAgent("trailer_finder", {"processed": 0, "completed": 0, "failed": 0}, calls),
    )
    monkeypatch.setattr(
        "app.services.pipeline_orchestrator.build_review_script_agent",
        lambda: _StubAgent("review_script", {"processed": 0, "completed": 0, "failed": 0}, calls),
    )
    monkeypatch.setattr(
        "app.services.pipeline_orchestrator.build_voice_generator_agent",
        lambda: _StubAgent("voice_generator", {"processed": 1, "completed": 1, "failed": 0}, calls),
    )
    monkeypatch.setattr(
        "app.services.pipeline_orchestrator.build_video_downloader_agent",
        lambda: _StubAgent("video_downloader", {"processed": 1, "completed": 1, "failed": 0}, calls),
    )
    monkeypatch.setattr("app.services.pipeline_orchestrator.settings.voice_mode", "auto")
    monkeypatch.setattr("app.services.pipeline_orchestrator.settings.source_video_mode", "auto")

    orchestrator = PipelineOrchestrator()
    orchestrator.run_cycle()

    assert calls == [
        ("trailer_finder", 1),
        ("review_script", 1),
        ("voice_generator", 1),
    ]
