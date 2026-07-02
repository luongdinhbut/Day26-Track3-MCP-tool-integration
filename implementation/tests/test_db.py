from __future__ import annotations

import pytest

from implementation.db import SQLiteAdapter, ValidationError
from implementation.init_db import create_database


@pytest.fixture
def adapter(tmp_path):
    db_path = tmp_path / "lab.sqlite3"
    create_database(db_path, reset=True)
    return SQLiteAdapter(db_path)


def test_search_filters_ordering_and_pagination(adapter):
    result = adapter.search(
        "students",
        filters={"cohort": "A1"},
        columns=["name", "cohort", "score"],
        limit=1,
        order_by="score",
        descending=True,
    )

    assert result["row_count"] == 1
    assert result["rows"][0]["name"] == "Ana Nguyen"
    assert result["rows"][0]["score"] == 92.5


def test_insert_returns_inserted_row(adapter):
    result = adapter.insert(
        "students",
        {
            "name": "Linh Vo",
            "cohort": "A1",
            "email": "linh.vo@example.edu",
            "age": 21,
            "score": 89.0,
        },
    )

    assert result["inserted_id"] > 0
    assert result["row"]["name"] == "Linh Vo"
    assert result["row"]["cohort"] == "A1"


def test_aggregate_average_score_by_cohort(adapter):
    result = adapter.aggregate(
        "students",
        metric="avg",
        column="score",
        group_by="cohort",
    )

    rows = {row["cohort"]: row["value"] for row in result["rows"]}
    assert rows["A1"] == pytest.approx(84.25)
    assert rows["C3"] == pytest.approx(97.0)


def test_validation_rejects_unknown_table(adapter):
    with pytest.raises(ValidationError, match="Unknown table"):
        adapter.search("missing")


def test_validation_rejects_unknown_column(adapter):
    with pytest.raises(ValidationError, match="Unknown column"):
        adapter.search("students", filters={"missing": "value"})


def test_validation_rejects_bad_operator(adapter):
    with pytest.raises(ValidationError, match="Unsupported filter operator"):
        adapter.search(
            "students",
            filters=[{"column": "score", "operator": "between", "value": [80, 90]}],
        )


def test_validation_rejects_empty_insert(adapter):
    with pytest.raises(ValidationError, match="non-empty object"):
        adapter.insert("students", {})


def test_validation_rejects_invalid_aggregate(adapter):
    with pytest.raises(ValidationError, match="requires a numeric column"):
        adapter.aggregate("students", metric="avg", column="name")

