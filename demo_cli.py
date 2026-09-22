import sys
import os
import argparse
import tempfile
import sqlite3

# Ensure backend root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app.schema_mapper import (
    Customer360SchemaMapper,
    DataSourceSampler,
    ValueSemanticAnalyzer,
    CANONICAL_FIELDS
)


def print_separator(title: str = ""):
    width = 76
    if title:
        padding = (width - len(title) - 2) // 2
        print("\n" + "=" * padding + f" {title} " + "=" * (width - padding - len(title) - 2))
    else:
        print("\n" + "=" * width)


def demo_headerless_csv():
    print_separator("DEMO 1: HEADERLESS CSV (Zero Column Names)")
    print("Input CSV Content (Notice: Absolutely No Headers!):")

    csv_data = (
        "Rahul Sharma,9876543210,rahul@example.com,Bengaluru,1990-05-14\n"
        "Priya Singh,+91 91234 56789,priya@example.com,Mumbai,1995-10-22\n"
        "Amit Verma,+1 (555) 234-5678,amit@example.com,Delhi,1988-03-15\n"
        "Dr. David Miller,555-123-4567,david@hospital.org,San Francisco,1975-08-30\n"
        "rahul sharma,9876543210,rahul@example.com,Bangalore,1990-05-14\n"
        "Jane Doe,+44 7911 123456,jane.doe@tech.co.uk,London,1992-12-01\n"
    )

    for line in csv_data.strip().splitlines()[:3]:
        print(f"  {line}")
    print("  ...")

    mapper = Customer360SchemaMapper()
    result = mapper.process_csv_dataset(csv_data, sample_size=5, deduplicate=True)

    print("\n[Analysis Results]")
    print(f"  Headers Detected : {result['has_header_detected']} (Assigned synthetic col_0..col_4)")
    print(f"  Samples Analyzed : {result['sample_rows_analyzed']} rows")
    print(f"  Input Rows       : {result['total_source_rows']}")
    print(f"  Deduplicated     : {result['deduplicated_rows']} (Merged: {result['duplicates_merged']} duplicate rows)")

    print("\nInferred Column Mappings (Pure Value Pattern Inference):")
    print(f"  {'Column':<10} | {'Canonical Field':<16} | {'Conf':<6} | {'Inferred Type':<18} | {'Reason'}")
    print("  " + "-" * 90)
    for col, m in result["column_mappings"].items():
        reason = m["reasons"][0] if m.get("reasons") else ""
        print(f"  {col:<10} | {str(m['canonical_field']):<16} | {m['confidence']:<6.2f} | {m['inferred_type']:<18} | {reason}")

    print("\nUnified Canonical Customer 360 Records Preview:")
    for i, rec in enumerate(result["sample_records_preview"][:3], 1):
        print(f"  [{i}] Name: {str(rec['full_name']):<18} | Mobile: {str(rec['mobile']):<16} | Email: {str(rec['email']):<22} | City: {str(rec['city'])}")


def demo_obfuscated_headers():
    print_separator("DEMO 2: OBFUSCATED & GENERIC HEADERS (VAR1, VAR2, ...)")
    print("Columns are named VAR1, VAR2, VAR3, VAR4. Traditional header matchers fail completely.")

    sample_rows = [
        {"VAR1": "CUST-90210", "VAR2": "Sanjay Dutt", "VAR3": "sanjay@bollywood.in", "VAR4": "9820011223"},
        {"VAR1": "CUST-90211", "VAR2": "Dr. Ananya Roy", "VAR3": "ananya@health.org", "VAR4": "+91 9988776655"},
        {"VAR1": "CUST-90212", "VAR2": "Michael Scott", "VAR3": "michael@dundermifflin.com", "VAR4": "555-0199"},
        {"VAR1": "CUST-90213", "VAR2": "Deepika Padukone", "VAR3": "deepika@cinema.com", "VAR4": "+91 9811223344"},
        {"VAR1": "CUST-90214", "VAR2": "Jane Smith", "VAR3": "jane@corp.net", "VAR4": "+1 (800) 555-0123"},
    ]

    mapper = Customer360SchemaMapper()
    mappings = mapper.get_smart_schema_mapping_from_samples(sample_rows)

    print("\nInferred Mappings from Cell Value Profiling:")
    print(f"  {'Column':<10} | {'Canonical Field':<16} | {'Confidence':<10} | {'Method':<30}")
    print("  " + "-" * 75)
    for col, m in mappings.items():
        print(f"  {col:<10} | {str(m['canonical_field']):<16} | {m['confidence']:<10.2f} | {m['method']:<30}")


def demo_ambiguity_disambiguation():
    print_separator("DEMO 3: AMBIGUOUS HEADER DISAMBIGUATION ('contact')")
    print("Case A: Column named 'contact' contains EMAIL strings:")
    mapper = Customer360SchemaMapper()

    case_a_samples = ["alex@company.com", "sarah.connor@sky.net", "bruce.wayne@waynecorp.com"]
    mapping_a = mapper.map_column_smart("contact", case_a_samples)
    print(f"  -> Mapped to: '{mapping_a['canonical_field']}' (Conf: {mapping_a['confidence']:.2f})")
    print(f"     Method   : {mapping_a['method']}")
    print(f"     Reason   : {mapping_a['reasons'][0]}")

    print("\nCase B: Column named 'contact' contains PHONE numbers:")
    case_b_samples = ["+91 98765 43210", "+1 (555) 234-5678", "9811122233"]
    mapping_b = mapper.map_column_smart("contact", case_b_samples)
    print(f"  -> Mapped to: '{mapping_b['canonical_field']}' (Conf: {mapping_b['confidence']:.2f})")
    print(f"     Method   : {mapping_b['method']}")
    print(f"     Reason   : {mapping_b['reasons'][0]}")


def demo_database_sampling():
    print_separator("DEMO 4: DATABASE TABLE RANDOM SAMPLING (5-10 Rows)")
    print("Simulating a connected SQL database table with random sampling...")

    # Create in-memory SQLite table
    temp_db_path = os.path.join(tempfile.gettempdir(), "customer_demo.db")
    conn = sqlite3.connect(temp_db_path)
    cur = conn.cursor()

    cur.execute("DROP TABLE IF EXISTS raw_customers")
    cur.execute("""
        CREATE TABLE raw_customers (
            f_id TEXT,
            f_person TEXT,
            f_num TEXT,
            f_mail TEXT,
            f_city TEXT
        )
    """)

    dummy_data = [
        ("CUST-101", "Aarav Patel", "+91 9876543210", "aarav@tech.in", "Ahmedabad"),
        ("CUST-102", "Pooja Hegde", "9123456789", "pooja@studio.com", "Hyderabad"),
        ("CUST-103", "Vikram Singh", "+1 555 345 6789", "vikram@finance.org", "Chandigarh"),
        ("CUST-104", "Sarah Connor", "+44 7911 123456", "sarah@cyber.co.uk", "London"),
        ("CUST-105", "Rohan Mehta", "9820012345", "rohan@startup.io", "Pune"),
        ("CUST-106", "Sneha Rao", "9988776655", "sneha@health.gov", "Bengaluru"),
        ("CUST-107", "Karan Johar", "9811122233", "karan@dharma.in", "Mumbai"),
    ]
    cur.executemany("INSERT INTO raw_customers VALUES (?, ?, ?, ?, ?)", dummy_data)
    conn.commit()
    conn.close()

    # Ingest using DataSourceSampler
    sqlite_uri = f"sqlite:///{temp_db_path}"
    cols, sample_rows = DataSourceSampler.sample_database(sqlite_uri, "raw_customers", sample_size=5)
    print(f"Successfully sampled {len(sample_rows)} random rows from SQLite table 'raw_customers'.")

    mapper = Customer360SchemaMapper()
    db_mappings = mapper.get_smart_schema_mapping_from_samples(sample_rows, columns=cols)

    print("\nInferred Database Schema Mappings:")
    for col, m in db_mappings.items():
        print(f"  DB Column '{col}' -> Canonical: '{m['canonical_field']}' (Confidence: {m['confidence']:.2f}, Type: {m['inferred_type']})")


def process_user_file(file_path: str):
    print_separator(f"PROCESSING CUSTOM FILE: {file_path}")
    if not os.path.exists(file_path):
        print(f"Error: File '{file_path}' does not exist.")
        return

    with open(file_path, "r", encoding="utf-8", errors="replace") as f:
        content = f.read()

    mapper = Customer360SchemaMapper()
    result = mapper.process_csv_dataset(content, sample_size=10, deduplicate=True)

    print(f"Headers Detected : {result['has_header_detected']}")
    print(f"Total Rows       : {result['total_source_rows']}")
    print(f"Deduplicated     : {result['deduplicated_rows']} (Merged: {result['duplicates_merged']})")

    print("\nColumn Mappings:")
    for col, m in result["column_mappings"].items():
        print(f"  {col} -> {m['canonical_field']} (Conf: {m['confidence']:.2f}, Inferred Type: {m['inferred_type']})")


def main():
    parser = argparse.ArgumentParser(description="Customer 360 Smart Schema Mapper CLI Demo")
    parser.add_argument("--file", type=str, help="Path to a custom CSV file to test")
    args = parser.parse_args()

    if args.file:
        process_user_file(args.file)
    else:
        demo_headerless_csv()
        demo_obfuscated_headers()
        demo_ambiguity_disambiguation()
        demo_database_sampling()
        print_separator("DEMO COMPLETED SUCCESSFULLY")


if __name__ == "__main__":
    main()
