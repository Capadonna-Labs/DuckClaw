from duckclaw.sql_split import split_sql_statements


def test_split_respects_semicolon_inside_single_quotes():
    sql = "SELECT ';'; SELECT 1"
    parts = split_sql_statements(sql)
    assert len(parts) == 2
    assert "';'" in parts[0]
    assert parts[1] == "SELECT 1"


def test_split_empty_and_strip():
    assert split_sql_statements("  ;  ;; SELECT 1 ; ") == ["", "", "", "SELECT 1", ""]
