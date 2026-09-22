import sys
import os
import sqlite3
import tempfile
from starlette.testclient import TestClient

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.schema_mapper import (
    Customer360SchemaMapper,
    DataSourceSampler,
    ValueSemanticAnalyzer,
    CANONICAL_FIELDS
)
from app.main import app


def test_column_name_matching():
    print("--- 1. Testing Column Name-based Matching ---")
    mapper = Customer360SchemaMapper()

    test_cases = [
        ("full_name_normalized", "full_name"),
        ("mobile_normalized", "mobile"),
        ("phone_number", "mobile"),
        ("contact_number", "mobile"),
        ("phone", "mobile"),
        ("cell_phone", "mobile"),
        ("cust_email_address", "email"),
        ("client_dob", "dob"),
        ("residential_address", "address"),
        ("district", "city"),
    ]

    for input_col, expected_canonical in test_cases:
        canonical, conf, method = mapper.map_column(input_col)
        print(f"Mapping '{input_col:25}' -> Expected: '{expected_canonical:10}' | Got: '{str(canonical):10}' (Conf: {conf:.2f}, Method: {method})")
        assert canonical == expected_canonical, f"Failed for {input_col}: got {canonical}, expected {expected_canonical}"

    print(" ALL COLUMN MAPPINGS PASSED!\n")


def test_value_semantic_profiler():
    print("--- 2. Testing Value Semantic Analyzer (Cell Value Pattern Profiling) ---")
    analyzer = ValueSemanticAnalyzer()

    profiler_tests = [
        (
            "full_name",
            ["Rahul Sharma", "Priya Singh", "Dr. Jane Miller", "Amit Verma", "Robert Downey Jr", "123 Main St"],
            "full_name"
        ),
        (
            "mobile",
            ["+91 98765 43210", "+1 (555) 234-5678", "9123456789", "555-123-4567", "9811122233"],
            "mobile"
        ),
        (
            "email",
            ["rahul@example.com", "priya.singh@corp.in", "amit.verma@domain.org", "jane@clinic.org", "rdj@marvel.com"],
            "email"
        ),
        (
            "customer_id",
            ["CUST-1001", "CUST-1002", "CUST-1003", "USR_9921", "c0a80101-4b1d-11ec-81d3-0242ac130003"],
            "customer_id"
        ),
        (
            "dob",
            ["1990-05-14", "1995-10-22", "1988-03-15", "1975-08-30", "1992-12-01"],
            "dob"
        ),
        (
            "address",
            ["123 Elm Street Apt 4B", "742 Evergreen Terrace", "Plot 42 Green Glen Layout", "456 Main Avenue Suite 100", "Flat 302 Baker Street"],
            "address"
        ),
        (
            "city",
            ["Bengaluru", "Mumbai", "San Francisco", "London", "New Delhi"],
            "city"
        ),
    ]

    for expected_type, sample_values, expected_canonical in profiler_tests:
        result = analyzer.analyze_samples(sample_values)
        detected = result["best_canonical"]
        conf = result["confidence"]
        reason = result["reasons"][0] if result["reasons"] else ""
        print(f"Sample Data -> Expected: '{expected_canonical:12}' | Detected: '{str(detected):12}' (Conf: {conf:.2f}) | Reason: {reason}")
        assert detected == expected_canonical, f"Failed semantic profiling: expected {expected_canonical}, got {detected}"
        assert conf >= 0.70, f"Confidence too low ({conf}) for {expected_canonical}"

    print(" ALL VALUE SEMANTIC PROFILING TESTS PASSED!\n")


def test_generic_and_obfuscated_headers():
    print("--- 3. Testing Smart Mapper with Generic & Obfuscated Headers ---")
    mapper = Customer360SchemaMapper()

    # Testing generic column names: col_0, col_1, VAR1, etc.
    test_cases = [
        ("col_0", ["Rahul Sharma", "Priya Singh", "Dr. Jane Miller", "Amit Verma"], "full_name"),
        ("col_1", ["+91 98765 43210", "9876543210", "555-123-4567"], "mobile"),
        ("col_2", ["rahul@example.com", "priya@example.com", "amit@example.com"], "email"),
        ("col_3", ["CUST-101", "CUST-102", "CUST-103", "CUST-104"], "customer_id"),
        ("col_4", ["1990-05-14", "1995-10-22", "1988-03-15"], "dob"),
        ("col_5", ["123 Elm Street Apt 4B", "742 Evergreen Terrace"], "address"),
        ("col_6", ["Bengaluru", "Mumbai", "San Francisco", "London"], "city"),
    ]

    for generic_col, samples, expected_canonical in test_cases:
        res = mapper.map_column_smart(generic_col, samples)
        print(f"Generic Header '{generic_col:<6}' -> Canonical: '{str(res['canonical_field']):<12}' (Conf: {res['confidence']:.2f}, Method: {res['method']})")
        assert res["canonical_field"] == expected_canonical, f"Failed for {generic_col}: got {res['canonical_field']}"
        assert res["confidence"] >= 0.75

    print(" GENERIC HEADER MAPPING PASSED!\n")


def test_disambiguation_and_conflict_resolution():
    print("--- 4. Testing Disambiguation & Conflict Resolution ---")
    mapper = Customer360SchemaMapper()

    # Ambiguous header 'contact' with email values
    res1 = mapper.map_column_smart("contact", ["alex@company.com", "sarah@tech.org"])
    print(f"Header 'contact' + Email samples -> Canonical: '{res1['canonical_field']}' (Method: {res1['method']})")
    assert res1["canonical_field"] == "email"

    # Ambiguous header 'contact' with phone values
    res2 = mapper.map_column_smart("contact", ["9876543210", "+91 91234 56789"])
    print(f"Header 'contact' + Phone samples -> Canonical: '{res2['canonical_field']}' (Method: {res2['method']})")
    assert res2["canonical_field"] == "mobile"

    # Mislabeled header 'person_name' containing phone numbers
    res3 = mapper.map_column_smart("person_name", ["+91 9876543210", "555-123-4567", "9811122233"])
    print(f"Mislabeled Header 'person_name' + Phone samples -> Canonical: '{res3['canonical_field']}' (Method: {res3['method']})")
    assert res3["canonical_field"] == "mobile"

    print(" DISAMBIGUATION & CONFLICT RESOLUTION PASSED!\n")


def test_headerless_csv_pipeline():
    print("--- 5. Testing Headerless CSV Dataset Processing & Deduplication ---")
    mapper = Customer360SchemaMapper()

    # Raw CSV with NO headers
    raw_csv = (
        "Rahul Sharma,9876543210,rahul@example.com,Bengaluru,1990-05-14\n"
        "Priya Singh,+91 91234 56789,priya@example.com,Mumbai,1995-10-22\n"
        "Amit Verma,+1 (555) 234-5678,amit@example.com,Delhi,1988-03-15\n"
        "rahul sharma,9876543210,rahul@example.com,Bangalore,1990-05-14\n"
    )

    result = mapper.process_csv_dataset(raw_csv, sample_size=5, deduplicate=True)

    print(f"Has Header Detected: {result['has_header_detected']}")
    assert result["has_header_detected"] is False

    print(f"Detected Columns: {result['columns']}")
    assert len(result["columns"]) == 5

    print("Column Mappings:")
    for col, m in result["column_mappings"].items():
        print(f"  {col} -> {m['canonical_field']} (Conf: {m['confidence']})")

    assert result["column_mappings"]["col_0"]["canonical_field"] == "full_name"
    assert result["column_mappings"]["col_1"]["canonical_field"] == "mobile"
    assert result["column_mappings"]["col_2"]["canonical_field"] == "email"
    assert result["column_mappings"]["col_3"]["canonical_field"] == "city"
    assert result["column_mappings"]["col_4"]["canonical_field"] == "dob"

    print(f"Total rows: {result['total_source_rows']} | Deduped: {result['deduplicated_rows']} | Merged: {result['duplicates_merged']}")
    assert result["total_source_rows"] == 4
    assert result["deduplicated_rows"] == 3
    assert result["duplicates_merged"] == 1

    print(" HEADERLESS CSV PROCESSING & DEDUPLICATION PASSED!\n")


def test_database_sampling_sqlite():
    print("--- 6. Testing Database Sampling (SQLite) ---")
    temp_db = os.path.join(tempfile.gettempdir(), "test_customer360.db")
    conn = sqlite3.connect(temp_db)
    cur = conn.cursor()

    cur.execute("DROP TABLE IF EXISTS test_customers")
    cur.execute("""
        CREATE TABLE test_customers (
            VAR1 TEXT,
            VAR2 TEXT,
            VAR3 TEXT,
            VAR4 TEXT
        )
    """)

    dummy_data = [
        ("CUST-101", "Aarav Patel", "aarav@tech.in", "+91 9876543210"),
        ("CUST-102", "Pooja Hegde", "pooja@studio.com", "9123456789"),
        ("CUST-103", "Vikram Singh", "vikram@finance.org", "+1 555 345 6789"),
        ("CUST-104", "Sarah Connor", "sarah@cyber.co.uk", "+44 7911 123456"),
    ]
    cur.executemany("INSERT INTO test_customers VALUES (?, ?, ?, ?)", dummy_data)
    conn.commit()
    conn.close()

    cols, sample_rows = DataSourceSampler.sample_database(f"sqlite:///{temp_db}", "test_customers", sample_size=4)
    mapper = Customer360SchemaMapper()
    db_mappings = mapper.get_smart_schema_mapping_from_samples(sample_rows, columns=cols)

    for col in cols:
        m = db_mappings[col]
        print(f"DB Col '{col}' -> Canonical: '{m['canonical_field']}' (Conf: {m['confidence']:.2f})")

    assert db_mappings["VAR1"]["canonical_field"] == "customer_id"
    assert db_mappings["VAR2"]["canonical_field"] == "full_name"
    assert db_mappings["VAR3"]["canonical_field"] == "email"
    assert db_mappings["VAR4"]["canonical_field"] == "mobile"

    print(" DATABASE SAMPLING & SMART MAPPING PASSED!\n")


def test_fastapi_endpoints():
    print("--- 7. Testing FastAPI Customer 360 Endpoints ---")
    client = TestClient(app)

    # 1. Canonical fields
    res = client.get("/api/customer360/canonical-fields")
    assert res.status_code == 200
    data = res.json()
    assert "canonical_fields" in data
    assert "full_name" in data["canonical_fields"]
    assert "mobile" in data["canonical_fields"]
    print(" GET /api/customer360/canonical-fields: 200 OK")

    # 2. Map columns with names only
    res = client.post(
        "/api/customer360/map-columns",
        json={"columns": ["full_name_normalized", "contact_number"]}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["mappings"]["full_name_normalized"]["canonical_field"] == "full_name"
    assert data["mappings"]["contact_number"]["canonical_field"] == "mobile"
    print(" POST /api/customer360/map-columns (Column Names): 200 OK")

    # 3. Map columns with generic names + sample rows
    res = client.post(
        "/api/customer360/map-columns",
        json={
            "columns": ["col_0", "col_1"],
            "sample_rows": [
                {"col_0": "Rahul Sharma", "col_1": "+91 9876543210"},
                {"col_0": "Priya Singh", "col_1": "9123456789"}
            ]
        }
    )
    assert res.status_code == 200
    data = res.json()
    assert data["mappings"]["col_0"]["canonical_field"] == "full_name"
    assert data["mappings"]["col_1"]["canonical_field"] == "mobile"
    print(" POST /api/customer360/map-columns (Generic Cols + Sample Rows): 200 OK")

    # 4. Analyze source (headerless CSV)
    csv_raw = "Rahul Sharma,rahul@corp.com\nPriya Singh,priya@corp.com\n"
    res = client.post(
        "/api/customer360/analyze-source",
        json={"csv_content": csv_raw, "sample_size": 5}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["has_header_detected"] is False
    assert data["column_mappings"]["col_0"]["canonical_field"] == "full_name"
    assert data["column_mappings"]["col_1"]["canonical_field"] == "email"
    print(" POST /api/customer360/analyze-source (Headerless CSV): 200 OK")

    # 5. File Upload (headerless CSV)
    files = {"file": ("headerless.csv", csv_raw.encode("utf-8"), "text/csv")}
    res = client.post("/api/customer360/upload", files=files)
    assert res.status_code == 200
    u_data = res.json()
    assert u_data["has_header_detected"] is False
    assert u_data["column_mappings"]["col_0"]["canonical_field"] == "full_name"
    assert u_data["column_mappings"]["col_1"]["canonical_field"] == "email"
    assert len(u_data["records"]) == 2
    print(" POST /api/customer360/upload (Headerless CSV): 200 OK")

    # 6. Database Sampling Endpoint
    temp_db = os.path.join(tempfile.gettempdir(), "test_customer360.db")
    res = client.post(
        "/api/customer360/map-database",
        json={"connection_string": f"sqlite:///{temp_db}", "table_name": "test_customers", "sample_size": 5}
    )
    assert res.status_code == 200
    db_data = res.json()
    assert db_data["column_mappings"]["VAR1"]["canonical_field"] == "customer_id"
    assert db_data["column_mappings"]["VAR3"]["canonical_field"] == "email"
    print(" POST /api/customer360/map-database (SQLite Table): 200 OK")

    print("\n ALL FASTAPI ENDPOINT TESTS PASSED SUCCESSFULLY!")


def main():
    try:
        test_column_name_matching()
        test_value_semantic_profiler()
        test_generic_and_obfuscated_headers()
        test_disambiguation_and_conflict_resolution()
        test_headerless_csv_pipeline()
        test_database_sampling_sqlite()
        test_fastapi_endpoints()
        print("\n" + "=" * 60)
        print("ALL TESTS PASSED! SMART MAPPER IMPLEMENTATION 100% VERIFIED.")
        print("=" * 60)
    except AssertionError as e:
        print(f"\nAssertion Failure: {e}")
        sys.exit(1)
    except Exception as e:
        print(f"\nUnexpected Error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == "__main__":
    main()
