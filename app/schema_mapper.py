import re
import csv
import random
from typing import Dict, List, Any, Optional, Tuple
from datetime import datetime


# CANONICAL TARGET FIELDS & REFERENCE DATA

CANONICAL_FIELDS = {
    "customer_id": {"description": "Unique customer identifier", "aliases": ["cust_id", "client_id", "user_id", "account_id", "id", "uid"]},
    "full_name":   {"description": "Person's full name",          "aliases": ["name", "customer_name", "client_name", "person_name", "display_name"]},
    "mobile":      {"description": "Contact phone number",        "aliases": ["mobile_number", "phone", "phone_number", "contact_number", "cell", "cell_phone", "tel"]},
    "email":       {"description": "Email address",               "aliases": ["email_address", "mail", "cust_email", "user_email"]},
    "dob":         {"description": "Date of birth",               "aliases": ["date_of_birth", "birth_date", "birthdate", "client_dob"]},
    "address":     {"description": "Postal / street address",     "aliases": ["residential_address", "street_address", "postal_address", "home_address"]},
    "city":        {"description": "City / town",                 "aliases": ["town", "district", "municipality", "metro"]}
}

KNOWN_CITIES = {
    "bengaluru", "bangalore", "mumbai", "delhi", "new delhi", "chennai", "kolkata",
    "hyderabad", "pune", "ahmedabad", "jaipur", "surat", "lucknow", "kanpur", "nagpur",
    "indore", "thane", "bhopal", "patna", "vadodara", "ghaziabad", "ludhiana", "agra",
    "nashik", "faridabad", "meerut", "rajkot", "varanasi", "srinagar", "chandigarh",
    "new york", "san francisco", "chicago", "los angeles", "houston", "seattle", "boston",
    "austin", "london", "manchester", "toronto", "vancouver", "sydney", "melbourne",
    "singapore", "dubai", "paris", "berlin", "tokyo"
}

ADDRESS_WORDS = {
    "street", "st", "road", "rd", "avenue", "ave", "boulevard", "blvd", "lane", "ln",
    "drive", "dr", "court", "ct", "suite", "ste", "apartment", "apt", "terrace", "ter",
    "floor", "fl", "building", "bldg", "block", "sector", "layout", "plot", "nagar", "colony"
}


# 1. VALUE SEMANTIC ANALYZER (Checking What the Data Looks Like)

class ValueSemanticAnalyzer:

    # Simple helper checks for a single value:
    @staticmethod
    def is_email(val: str) -> bool:
        s = val.strip()
        # Has an '@', a '.', and standard email characters
        return bool(re.match(r"^[\w\.-]+@[\w\.-]+\.\w+$", s))

    @staticmethod
    def is_phone(val: str) -> bool:
        s = val.strip()
        digits = re.sub(r"\D", "", s)  # Keep only numbers (0-9)
        # Phone numbers typically have 10 to 15 digits and are not dummy sequences
        if 10 <= len(digits) <= 15 and digits != "1234567890" and digits != digits[0] * len(digits):
            return True
        return False

    @staticmethod
    def is_person_name(val: str) -> bool:
        s = val.strip()
        words = s.split()
        # Full names usually have 2 to 4 words
        if 2 <= len(words) <= 4:
            # Must not contain numbers
            no_numbers = not any(char.isdigit() for char in s)
            no_symbols = "@" not in s and "/" not in s
            no_address = not any(w.lower().strip(".,") in ADDRESS_WORDS for w in words)
            return no_numbers and no_symbols and no_address
        return False

    @staticmethod
    def is_identifier(val: str) -> bool:
        s = val.strip()
        # Matches UUIDs or prefixed IDs like CUST-101, USR_9921
        is_uuid = bool(re.match(r"^[0-9a-fA-F-]{36}$", s) and "-" in s)
        is_prefixed = bool(re.match(r"^(CUST|ID|USR|ACC|EMP|CLI)[-_#]?[0-9a-zA-Z]+$", s, re.I))
        return is_uuid or is_prefixed

    @staticmethod
    def is_date_of_birth(val: str) -> bool:
        s = val.strip()
        # Try parsing common date formats
        for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y", "%d-%m-%Y", "%Y/%m/%d"):
            try:
                dt = datetime.strptime(s, fmt)
                # Sanity check: birth year should be between 1910 and 2 years ago
                if 1910 <= dt.year <= (datetime.now().year - 2):
                    return True
            except ValueError:
                continue
        return False

    @staticmethod
    def is_address(val: str) -> bool:
        s = val.strip().lower()
        has_number = any(char.isdigit() for char in s)
        has_street_word = any(w in s for w in ADDRESS_WORDS)
        return has_number and has_street_word and len(s) >= 8

    @staticmethod
    def is_city(val: str) -> bool:
        s = val.strip().lower()
        if s in KNOWN_CITIES:
            return True
        # Single-word proper noun without numbers or address words
        if len(s.split()) == 1 and s.isalpha() and val.strip().istitle() and s not in ADDRESS_WORDS:
            return True
        return False

    @classmethod
    def analyze_samples(cls, values: List[Any]) -> Dict[str, Any]:
        """
        Examines 5-10 sample values in a column.
        Counts how many values match each type, and picks the winner!
        """
        clean_values = [str(v).strip() for v in values if v is not None and str(v).strip() != ""]
        if not clean_values:
            return {"best_canonical": None, "confidence": 0.0, "semantic_type": "unknown", "reasons": ["Empty values"]}

        total = len(clean_values)

        # Count matches for each category
        counts = {
            "email":       sum(1 for v in clean_values if cls.is_email(v)),
            "mobile":      sum(1 for v in clean_values if cls.is_phone(v)),
            "full_name":   sum(1 for v in clean_values if cls.is_person_name(v)),
            "customer_id": sum(1 for v in clean_values if cls.is_identifier(v)),
            "dob":         sum(1 for v in clean_values if cls.is_date_of_birth(v)),
            "address":     sum(1 for v in clean_values if cls.is_address(v)),
            "city":        sum(1 for v in clean_values if cls.is_city(v)),
        }

        # Find the category with the most matches
        best_field, best_count = max(counts.items(), key=lambda item: item[1])
        match_rate = best_count / total

        # Disambiguate: 2-word person names vs city
        if best_field == "city" and counts["full_name"] > 0:
            avg_words = sum(len(v.split()) for v in clean_values) / total
            if avg_words >= 1.8 and not any(v.lower() in KNOWN_CITIES for v in clean_values):
                best_field = "full_name"
                match_rate = counts["full_name"] / total

        if match_rate >= 0.5:
            confidence = round(0.50 + (0.48 * match_rate), 2)
            type_names = {
                "mobile": "phone_number", "email": "email", "full_name": "person_name",
                "customer_id": "identifier", "dob": "date_of_birth", "address": "postal_address", "city": "city_name"
            }
            return {
                "best_canonical": best_field,
                "confidence": confidence,
                "semantic_type": type_names.get(best_field, "text"),
                "reasons": [f"{int(match_rate * 100)}% of sample values match {best_field} patterns."]
            }

        return {"best_canonical": None, "confidence": 0.0, "semantic_type": "unknown", "reasons": ["No clear pattern detected"]}


# 2. DATA SOURCE SAMPLER (Reading CSVs & Databases)

class DataSourceSampler:
    """Reads 5-10 sample rows from CSV files or connected SQL databases."""

    @staticmethod
    def is_generic_or_missing_header(header: str) -> bool:
        """Checks if a column name is generic like col_0, VAR1, F1, or empty."""
        h = header.strip().lower()
        if not h:
            return True
        return bool(re.match(r"^(col_?\d+|var\d+|f_?\d+|attr_?\d+|field_?\d+|\d+)$", h))

    @staticmethod
    def detect_csv_headers(first_line: str) -> bool:
        """Checks if the first row is data (e.g., contains an email or phone) rather than headers."""
        cells = [c.strip() for c in first_line.split(",") if c.strip()]
        for c in cells:
            if ValueSemanticAnalyzer.is_email(c) or ValueSemanticAnalyzer.is_phone(c) or ValueSemanticAnalyzer.is_date_of_birth(c):
                return False  # Contains real data, so NO headers!
        return True

    @classmethod
    def sample_csv(cls, csv_text: str, sample_size: int = 10) -> Dict[str, Any]:
        """Parses CSV and returns 5-10 random sample rows."""
        lines = [line.strip() for line in csv_text.strip().splitlines() if line.strip()]
        if not lines:
            return {"columns": [], "sample_rows": [], "has_header": False, "all_data_rows": []}

        has_header = cls.detect_csv_headers(lines[0])
        reader = list(csv.reader(lines))

        if has_header:
            columns = [c.strip() for c in reader[0]]
            data_rows = reader[1:]
        else:
            num_cols = len(reader[0])
            columns = [f"col_{i}" for i in range(num_cols)]
            data_rows = reader

        all_dict_rows = [dict(zip(columns, row)) for row in data_rows]
        # Pick 5-10 random sample rows
        k = min(sample_size, len(all_dict_rows))
        sample_rows = random.sample(all_dict_rows, k) if len(all_dict_rows) > k else all_dict_rows

        # Collect sample values per column
        column_samples = {col: [r[col] for r in sample_rows if r.get(col)] for col in columns}

        return {
            "columns": columns,
            "sample_rows": sample_rows,
            "column_samples": column_samples,
            "has_header": has_header,
            "total_rows": len(data_rows),
            "all_data_rows": all_dict_rows
        }

    @classmethod
    def sample_database(cls, connection_string: str, table_name: str, sample_size: int = 10) -> Tuple[List[str], List[Dict[str, Any]]]:
        """
        Connects to a SQL database and samples 5-10 random rows.
        Supports:
        - Demo mode: "demo", "string", or "sample" returns a pre-populated sample customer table.
        - SQLite paths: auto-adds 'sqlite:///' if a .db or .sqlite path is given.
        - Any SQLAlchemy URI: sqlite:///, postgresql://, mysql://, etc.
        """
        from sqlalchemy import create_engine, text, inspect
        import tempfile
        import sqlite3
        import os

        conn_str = connection_string.strip()

        # 1. Built-in Demo Database mode (for quick Swagger UI testing)
        if conn_str.lower() in ("demo", "string", "sample", "default", "") or table_name.lower() in ("string", "demo_customers"):
            demo_db_path = os.path.join(tempfile.gettempdir(), "customer360_demo.db")
            conn = sqlite3.connect(demo_db_path)
            cur = conn.cursor()
            cur.execute("DROP TABLE IF EXISTS demo_customers")
            cur.execute("""
                CREATE TABLE demo_customers (
                    f_id TEXT,
                    f_person TEXT,
                    f_num TEXT,
                    f_mail TEXT,
                    f_city TEXT,
                    f_birth TEXT
                )
            """)
            demo_rows = [
                ("CUST-101", "Aarav Patel", "+91 98765 43210", "aarav@tech.in", "Ahmedabad", "1991-04-12"),
                ("CUST-102", "Pooja Hegde", "9123456789", "pooja@studio.com", "Hyderabad", "1994-10-13"),
                ("CUST-103", "Vikram Singh", "+1 (555) 234-5678", "vikram@finance.org", "Chandigarh", "1987-07-25"),
                ("CUST-104", "Dr. Jane Miller", "555-123-4567", "jane@clinic.org", "San Francisco", "1982-11-05"),
                ("CUST-105", "Rohan Mehta", "9820012345", "rohan@startup.io", "Pune", "1993-02-18"),
                ("CUST-106", "Sneha Rao", "9988776655", "sneha@health.gov", "Bengaluru", "1996-08-30"),
            ]
            cur.executemany("INSERT INTO demo_customers VALUES (?, ?, ?, ?, ?, ?)", demo_rows)
            conn.commit()
            conn.close()
            conn_str = f"sqlite:///{demo_db_path}"
            table_name = "demo_customers"

        # 2. Auto-format SQLite file paths (e.g. 'test.db' -> 'sqlite:///test.db')
        elif not ("://" in conn_str):
            if conn_str.endswith(".db") or conn_str.endswith(".sqlite") or os.path.exists(conn_str):
                conn_str = f"sqlite:///{conn_str}"
            else:
                raise ValueError(
                    f"Invalid connection URI: '{connection_string}'. "
                    f"Please provide a valid database URI (e.g. 'sqlite:///my_database.db', "
                    f"'postgresql://user:pass@localhost/dbname', or 'demo' for sample data)."
                )

        engine = create_engine(conn_str)
        inspector = inspect(engine)
        available_tables = inspector.get_table_names()

        if table_name not in available_tables:
            raise ValueError(
                f"Table '{table_name}' was not found in database. "
                f"Available tables: {available_tables if available_tables else 'None'}"
            )

        columns = [col["name"] for col in inspector.get_columns(table_name)]

        with engine.connect() as conn:
            try:
                res = conn.execute(text(f"SELECT * FROM {table_name} ORDER BY RANDOM() LIMIT {sample_size}"))
            except Exception:
                res = conn.execute(text(f"SELECT * FROM {table_name} LIMIT {sample_size}"))
            rows = [dict(row._mapping) for row in res]

        return columns, rows



# 3. SMART ENSEMBLE FIELD MAPPER 

class Customer360SchemaMapper:
   
    def __init__(self):
        self.canonical_fields = CANONICAL_FIELDS
        self.analyzer = ValueSemanticAnalyzer()

    def match_by_column_name(self, col_name: str) -> Tuple[Optional[str], float, str]:
        """Matches a column name against known aliases and keywords."""
        name = re.sub(r"[^a-z0-9]", "", col_name.lower())
        if not name or DataSourceSampler.is_generic_or_missing_header(col_name):
            return None, 0.0, "generic_header"

        # Check exact canonical name or aliases
        for canonical, info in self.canonical_fields.items():
            all_names = [canonical] + info["aliases"]
            for target in all_names:
                t_clean = re.sub(r"[^a-z0-9]", "", target.lower())
                if name == t_clean:
                    return canonical, 0.95, f"exact_alias:{target}"
                if name.startswith(t_clean) or name.endswith(t_clean):
                    return canonical, 0.92, f"suffix_stripped:{target}"

        # Substring keyword fallbacks
        if "mail" in name:     return "email", 0.90, "keyword_mail"
        if "phone" in name or "mob" in name or "contact" in name or "cell" in name: return "mobile", 0.90, "keyword_phone"
        if "name" in name:     return "full_name", 0.85, "keyword_name"
        if "birth" in name or "dob" in name: return "dob", 0.90, "keyword_dob"
        if "city" in name or "district" in name: return "city", 0.85, "keyword_city"
        if "address" in name:  return "address", 0.85, "keyword_address"
        if "id" in name:       return "customer_id", 0.80, "keyword_id"

        return None, 0.0, "no_name_match"

    def map_column_smart(self, column_name: str, sample_values: Optional[List[Any]] = None) -> Dict[str, Any]:
        """
        The Main Brain:
        1. Checks column name.
        2. Checks 5-10 sample cell values.
        3. Decides the best canonical field.
        """
        sample_values = sample_values or []

        # Signal A: What does the header name suggest?
        name_canonical, name_conf, name_method = self.match_by_column_name(column_name)

        # Signal B: What do the sample values look like?
        data_analysis = self.analyzer.analyze_samples(sample_values)
        data_canonical = data_analysis["best_canonical"]
        data_conf = data_analysis["confidence"]
        data_type = data_analysis["semantic_type"]

        # Generic or missing header
        if DataSourceSampler.is_generic_or_missing_header(column_name) or not name_canonical:
            return {
                "source_column": column_name,
                "canonical_field": data_canonical,
                "confidence": data_conf if data_canonical else 0.0,
                "method": f"data_inference_{data_type}" if data_canonical else "unmapped",
                "inferred_type": data_type,
                "reasons": data_analysis["reasons"]
            }

        #No sample data provided -> Use column name
        if not sample_values or not data_canonical:
            return {
                "source_column": column_name,
                "canonical_field": name_canonical,
                "confidence": name_conf,
                "method": f"name_only:{name_method}",
                "inferred_type": "inferred_from_header",
                "reasons": [f"Mapped from column name '{column_name}'"]
            }

        # Both agree!
        if name_canonical == data_canonical:
            return {
                "source_column": column_name,
                "canonical_field": name_canonical,
                "confidence": 1.00,
                "method": "header_and_data_agreement",
                "inferred_type": data_type,
                "reasons": [f"Header '{column_name}' and sample data both agree on '{name_canonical}'."]
            }

        # Disambiguation or Conflict
        # Data evidence takes priority!
        return {
            "source_column": column_name,
            "canonical_field": data_canonical,
            "confidence": data_conf,
            "method": "data_override_header_conflict" if name_canonical != data_canonical else f"data_inference_{data_type}",
            "inferred_type": data_type,
            "reasons": data_analysis["reasons"]
        }

    def map_column(self, column_name: str) -> Tuple[Optional[str], float, str]:
        """Simple mapping using column name only."""
        res = self.map_column_smart(column_name)
        return res["canonical_field"], res["confidence"], res["method"]

    def get_smart_schema_mapping_from_samples(self, sample_rows: List[Dict[str, Any]], columns: Optional[List[str]] = None) -> Dict[str, Dict[str, Any]]:
        """Maps all columns from a set of sample rows."""
        if not sample_rows and not columns:
            return {}
        cols = columns or list(sample_rows[0].keys())
        mappings = {}
        for col in cols:
            samples = [row[col] for row in sample_rows if row.get(col)]
            mappings[col] = self.map_column_smart(col, samples)
        return mappings

    # 4. ROW TRANSFORMATION & DEDUPLICATION

    def transform_row_with_mapping(self, raw_row: Dict[str, Any], column_mappings: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        """Transforms a raw row into a clean Customer 360 record."""
        record = {field: None for field in ["customer_id", "full_name", "mobile", "email", "dob", "address", "city"]}
        record["extra_attributes"] = {}
        mappings = column_mappings or {}

        for col, val in raw_row.items():
            if val is None or str(val).strip() == "":
                continue

            mapping = mappings.get(col)
            canonical = None

            # Support both dict mappings ({"canonical_field": "..."}) and direct string mappings ("full_name")
            if isinstance(mapping, dict):
                canonical = mapping.get("canonical_field") or mapping.get("canonical") or mapping.get("target")
            elif isinstance(mapping, str):
                canonical = mapping.strip()

            # If column wasn't in mappings, infer on-the-fly
            if not canonical:
                inferred = self.map_column_smart(col, [val])
                canonical = inferred.get("canonical_field")

            if canonical and canonical in record:
                if record[canonical] is None:
                    record[canonical] = str(val).strip()
            else:
                record["extra_attributes"][col] = val
        return record

    def deduplicate_records(self, records: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], int]:
        """Merges duplicate customer records that share the same mobile, email, or customer_id."""
        seen = {}
        merged_count = 0

        for r in records:
            key = None
            if r.get("mobile"):
                key = f"m:{re.sub(r'\D', '', str(r['mobile']))[-10:]}"
            elif r.get("email"):
                key = f"e:{str(r['email']).strip().lower()}"
            elif r.get("customer_id"):
                key = f"id:{str(r['customer_id']).strip()}"

            if key and key in seen:
                merged_count += 1
                existing = seen[key]
                # Merge missing fields
                for f in ["full_name", "mobile", "email", "dob", "address", "city"]:
                    if not existing.get(f) and r.get(f):
                        existing[f] = r[f]
            elif key:
                seen[key] = r
            else:
                seen[f"anon_{len(seen)}"] = r

        return list(seen.values()), merged_count

    def process_csv_dataset(self, csv_text: str, sample_size: int = 10, deduplicate: bool = True) -> Dict[str, Any]:
        """End-to-end pipeline: Sample -> Infer -> Transform -> Deduplicate."""
        sample_data = DataSourceSampler.sample_csv(csv_text, sample_size=sample_size)
        cols = sample_data["columns"]
        col_samples = sample_data["column_samples"]
        all_rows = sample_data["all_data_rows"]

        mappings = {col: self.map_column_smart(col, col_samples.get(col, [])) for col in cols}
        transformed = [self.transform_row_with_mapping(r, mappings) for r in all_rows]

        final_records, merged_count = self.deduplicate_records(transformed) if deduplicate else (transformed, 0)

        return {
            "has_header_detected": sample_data["has_header"],
            "columns": cols,
            "sample_rows_analyzed": len(sample_data["sample_rows"]),
            "total_source_rows": len(all_rows),
            "deduplicated_rows": len(final_records),
            "duplicates_merged": merged_count,
            "column_mappings": mappings,
            "sample_records_preview": final_records[:5],
            "all_records": final_records
        }
