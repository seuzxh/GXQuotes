import json

import fetch_all_concept_plates as script


class _FakeFetcher:
    def __init__(self, strict=False):
        assert strict is True

    def get_all_plates(self, plate_type="concept", page_size=100, *,
                       sort_by="change_pct", direction="desc"):
        assert page_size == 50
        assert plate_type in ("industry", "concept", "region", "style")
        row = {
            "code": f"{plate_type}-code",
            "name": f"{plate_type}-name",
            "market": 44,
        }
        row.update({field: None for field in script.PLATE_SORT_FIELDS})
        row.update(price=1843.79, change=2.55, change_pct=0.138)
        row[sort_by] = 123.45
        return [row]


def test_stdout_json(monkeypatch, capsys):
    monkeypatch.setattr(script, "ConceptPlateFetcher", _FakeFetcher)

    assert script.main(["--page-size", "50"]) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["meta"]["count"] == 1
    assert output["meta"]["market"] == 44
    assert output["meta"]["type"] == "concept"
    assert output["meta"]["subtype"] == 1
    assert output["meta"]["sort"] == {"field": "change_pct", "direction": "desc"}
    assert output["meta"]["retrieved_at"].endswith("Z")
    assert output["data"][0]["code"] == "concept-code"
    assert set(script.PLATE_SORT_FIELDS).issubset(output["data"][0])


def test_output_file(monkeypatch, tmp_path, capsys):
    monkeypatch.setattr(script, "ConceptPlateFetcher", _FakeFetcher)
    output_path = tmp_path / "nested" / "plates.json"

    assert script.main(["--page-size", "50", "--output", str(output_path)]) == 0

    output = json.loads(output_path.read_text(encoding="utf-8"))
    assert output["meta"]["count"] == 1
    assert "已写入 1 个 concept 板块" in capsys.readouterr().err


def test_all_types_are_flattened_and_tagged(monkeypatch, capsys):
    monkeypatch.setattr(script, "ConceptPlateFetcher", _FakeFetcher)

    assert script.main(["--type", "all", "--page-size", "50"]) == 0

    output = json.loads(capsys.readouterr().out)
    assert output["meta"]["count"] == 4
    assert output["meta"]["counts"] == {
        "industry": 1,
        "concept": 1,
        "region": 1,
        "style": 1,
    }
    assert [row["type"] for row in output["data"]] == [
        "industry",
        "concept",
        "region",
        "style",
    ]


def test_sort_and_direction_are_forwarded(monkeypatch, capsys):
    calls = []

    class _CapturingFetcher(_FakeFetcher):
        def get_all_plates(self, plate_type="concept", page_size=100, *,
                           sort_by="change_pct", direction="desc"):
            calls.append((plate_type, sort_by, direction))
            return super().get_all_plates(
                plate_type,
                page_size,
                sort_by=sort_by,
                direction=direction,
            )

    monkeypatch.setattr(script, "ConceptPlateFetcher", _CapturingFetcher)

    assert script.main([
        "--type", "style", "--page-size", "50",
        "--sort", "volume_ratio", "--direction", "asc",
    ]) == 0

    output = json.loads(capsys.readouterr().out)
    assert calls == [("style", "volume_ratio", "asc")]
    assert output["meta"]["sort"] == {
        "field": "volume_ratio",
        "direction": "asc",
    }
    assert output["data"][0]["volume_ratio"] == 123.45


def test_missing_gateway_is_actionable(monkeypatch, capsys):
    class _MissingGatewayFetcher:
        def __init__(self, strict=False):
            pass

        def get_all_plates(self, plate_type="concept", page_size=100, **kwargs):
            raise EnvironmentError("missing base url")

    monkeypatch.setattr(script, "ConceptPlateFetcher", _MissingGatewayFetcher)

    assert script.main([]) == 1
    assert "KLINE_API_BASE_URL" in capsys.readouterr().err
