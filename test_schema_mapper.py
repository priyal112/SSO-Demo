import sys
from fastapi.testclient import TestClient
from app.main import app
from app.schema_mapper import Customer360SchemaMapper


def test_schema_mapper_unit():
    print("--- 1. Testing Column Mapping ---")
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

    all_passed = True
    for input_col, expected_canonical in test_cases:
        canonical, conf, method = mapper.map_column(input_col)
        print(f"Mapping '{input_col:25}' -> Expected: '{expected_canonical:10}' | Got: '{str(canonical):10}' (Conf: {conf:.2f}, Method: {method})")
        assert canonical == expected_canonical, f"Failed for {input_col}: got {canonical}, expected {expected_canonical}"

    print(" ALL COLUMN MAPPINGS PASSED!\n")

    print("--- 2. Testing Row Merging (Preventing Duplicate Rows for Normalized Fields) ---")
    # Incoming record has BOTH full_name and full_name_normalized, plus mobile_normalized and phone_number
    raw_row = {
        "full_name_normalized": "rahul sharma",
        "full_name": "Rahul Sharma",
        "mobile_normalized": "9876543210",
        "phone_number": "9876543210",
        "city": "Bengaluru",
    }

    transformed = mapper.transform_row(raw_row)
    print(f"Transformed canonical record:\n  {transformed}")

    # Verify that full_name is mapped properly and not duplicated into two separate fields or rows
    assert transformed["full_name"] == "Rahul Sharma"
    assert transformed["mobile"] == "9876543210"
    assert transformed["city"] == "Bengaluru"
    assert "full_name_normalized" not in transformed
    assert "mobile_normalized" not in transformed
    print(" ROW MERGING PASSED! (Both columns merged into single canonical field without duplicating rows)\n")

    print("--- 3. Testing In-Memory Deduplication Engine ---")
    duplicate_rows = [
        {"full_name": "Rahul Sharma", "mobile": "9876543210", "email": "rahul@test.com"},
        {"full_name_normalized": "rahul sharma", "contact_number": "9876543210", "city": "Mumbai"},
        {"full_name": "Priya Singh", "mobile": "9123456789", "city": "Delhi"},
    ]

    transformed_batch = [mapper.transform_row(r) for r in duplicate_rows]
    deduped_records, duplicates_merged = mapper.deduplicate_records(transformed_batch)

    print(f"Input records: {len(duplicate_rows)} | Deduplicated records: {len(deduped_records)} | Merged: {duplicates_merged}")
    assert len(deduped_records) == 2, f"Expected 2 records after deduplication, got {len(deduped_records)}"
    assert duplicates_merged == 1

    # Verify merged attributes (Rahul Sharma should now have both email AND city!)
    rahul_record = next(r for r in deduped_records if "rahul" in r["full_name"].lower())
    assert rahul_record["email"] == "rahul@test.com"
    assert rahul_record["city"] == "Mumbai"
    print(f"Merged Record: {rahul_record}")
    print(" DEDUPLICATION ENGINE PASSED!\n")


def test_api_endpoints():
    print("--- 4. Testing FastAPI Customer 360 Endpoints ---")
    client = TestClient(app)

    # 1. Test canonical fields endpoint
    res = client.get("/api/customer360/canonical-fields")
    assert res.status_code == 200
    canonical_fields = res.json()["canonical_fields"]
    assert "full_name" in canonical_fields
    assert "mobile" in canonical_fields
    print(" GET /api/customer360/canonical-fields: 200 OK")

    # 2. Test map-columns endpoint
    res = client.post(
        "/api/customer360/map-columns",
        json={"columns": ["full_name_normalized", "mobile_normalized", "phone_number", "contact_number"]}
    )
    assert res.status_code == 200
    data = res.json()
    assert data["mappings"]["full_name_normalized"]["canonical_field"] == "full_name"
    assert data["mappings"]["mobile_normalized"]["canonical_field"] == "mobile"
    assert data["mappings"]["phone_number"]["canonical_field"] == "mobile"
    assert data["mappings"]["contact_number"]["canonical_field"] == "mobile"
    print(" POST /api/customer360/map-columns: 200 OK")

    # 3. Test transform endpoint
    res = client.post(
        "/api/customer360/transform",
        json={
            "records": [
                {"full_name_normalized": "rahul sharma", "contact_number": "9876543210"},
                {"full_name": "Rahul Sharma", "mobile": "9876543210", "city": "Pune"}
            ],
            "deduplicate": True
        }
    )
    assert res.status_code == 200
    t_data = res.json()
    assert t_data["total_input_records"] == 2
    assert t_data["deduplicated_records_count"] == 1
    assert t_data["duplicates_merged"] == 1
    print(" POST /api/customer360/transform: 200 OK (2 duplicate rows merged into 1)")

    # 4. Test file upload endpoint
    csv_content = "full_name_normalized,contact_number,email_address\nrahul sharma,9876543210,rahul@example.com\n"
    files = {"file": ("test_data.csv", csv_content.encode("utf-8"), "text/csv")}
    res = client.post("/api/customer360/upload", files=files)
    assert res.status_code == 200
    u_data = res.json()
    assert u_data["column_mappings"]["full_name_normalized"]["canonical_field"] == "full_name"
    assert u_data["column_mappings"]["contact_number"]["canonical_field"] == "mobile"
    assert u_data["records"][0]["full_name"] == "rahul sharma"
    assert u_data["records"][0]["mobile"] == "9876543210"
    print(" POST /api/customer360/upload: 200 OK (CSV file processed and mapped)")

    print("\n ALL FASTAPI ENDPOINT TESTS PASSED SUCCESSFULLY!")


if __name__ == "__main__":
    try:
        test_schema_mapper_unit()
        test_api_endpoints()
        print("\n==========================================")
        print("ALL TESTS PASSED! IMPLEMENTATION COMPLETE.")
        print("==========================================")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
