import re
from difflib import SequenceMatcher
from typing import Any, Dict, List, Optional, Tuple


class Customer360SchemaMapper:
    """
    Intelligent schema mapper and deduplicator for Customer 360
    Maps various source database/file columns into 7 canonical fields:
    - full_name
    - mobile
    - email
    - customer_id
    - dob
    - address
    - city
    """

    DEFAULT_CANONICAL_SCHEMA = {
        "full_name": [
            "name", "customer_name", "cust_name", "client_name", "user_name",
            "fullname", "full_name", "display_name", "person_name",
            "first_and_last_name", "customer_full_name", "party_name",
            "applicant_name", "account_holder_name"
        ],
        "mobile": [
            "mobile", "phone", "phone_number", "mobile_number",
            "contact", "contact_number", "cell", "cell_phone",
            "cellphone", "telephone", "tel", "mob", "msisdn",
            "mobile_no", "ph_no", "contact_no", "phone_no",
            "primary_phone", "primary_mobile", "user_phone"
        ],
        "email": [
            "email", "email_address", "mail", "e_mail", "customer_email",
            "user_email", "primary_email", "email_id", "cust_email",
            "contact_email"
        ],
        "customer_id": [
            "id", "user_id", "cust_id", "customer_id", "account_id",
            "client_id", "uuid", "member_id", "customer_number",
            "cust_no", "cif", "party_id"
        ],
        "dob": [
            "dob", "date_of_birth", "birth_date", "birthdate",
            "birthday", "born_date", "d_o_b", "dateofbirth"
        ],
        "address": [
            "address", "street_address", "residential_address",
            "full_address", "addr", "address_line_1", "location",
            "residence", "street"
        ],
        "city": [
            "city", "town", "district", "metro_area", "municipality"
        ],
    }

    NOISE_SUFFIXES = [
        "_normalized", "_norm", "_cleaned", "_clean",
        "_standardized", "_std", "_raw", "_val", "_value",
        "_txt", "_str", "_number", "_num", "_no"
    ]

    NOISE_PREFIXES = [
        "cust_", "customer_", "user_", "client_", "tbl_"
    ]

    def __init__(self, custom_schema: Optional[Dict[str, List[str]]] = None):
        self.canonical_schema = custom_schema or self.DEFAULT_CANONICAL_SCHEMA

    def _clean_column_name(self, col: str) -> str:
        """Strip whitespace, lowercase, and convert non-alphanumeric chars to underscores"""
        if not col:
            return ""
        cleaned = col.strip().lower()
        cleaned = re.sub(r'[^a-z0-9_]', '_', cleaned)
        cleaned = re.sub(r'_+', '_', cleaned).strip('_')
        return cleaned

    def _strip_noise(self, col: str) -> str:
        """Strip common suffixes like _normalized, _norm, _cleaned, etc"""
        modified = True
        current = col
        while modified:
            modified = False
            for suffix in self.NOISE_SUFFIXES:
                if current.endswith(suffix):
                    current = current[:-len(suffix)].strip('_')
                    modified = True
                    break
        return current

    def _strip_prefix_noise(self, col: str) -> str:
        """Strip prefixes like cust_, customer_, user_"""
        for prefix in self.NOISE_PREFIXES:
            if col.startswith(prefix) and len(col) > len(prefix):
                return col[len(prefix):].strip('_')
        return col

    def _calculate_similarity(self, a: str, b: str) -> float:
        """Calculate string similarity using SequenceMatcher"""
        return SequenceMatcher(None, a, b).ratio()

    def map_column(self, source_column: str) -> Tuple[Optional[str], float, str]:
        """
        Map incoming column name to one of the 7 canonical fields
        Returns: (canonical_name, confidence_score, detection_method)
        """
        clean_col = self._clean_column_name(source_column)
        if not clean_col:
            return None, 0.0, "unmapped"

        stripped_col = self._strip_noise(clean_col)
        unprefixed_col = self._strip_prefix_noise(stripped_col)

        # Exact match with Canonical Name
        for canonical in self.canonical_schema.keys():
            if clean_col == canonical:
                return canonical, 1.0, "exact_canonical"
            if stripped_col == canonical:
                return canonical, 0.98, "suffix_stripped_canonical"
            if unprefixed_col == canonical:
                return canonical, 0.96, "prefix_stripped_canonical"

        # Exact match with Aliases
        for canonical, aliases in self.canonical_schema.items():
            if clean_col in aliases:
                return canonical, 0.95, "exact_alias"
            if stripped_col in aliases:
                return canonical, 0.94, "suffix_stripped_alias"
            if unprefixed_col in aliases:
                return canonical, 0.92, "prefix_stripped_alias"

        #Keyword / Token / Stemming Match

        tokens = set(clean_col.split('_') + stripped_col.split('_') + unprefixed_col.split('_'))
        for canonical, aliases in self.canonical_schema.items():
            if canonical in tokens:
                return canonical, 0.88, "token_match_canonical"
            for alias in aliases:
                if len(alias) >= 4 and alias in tokens:
                    return canonical, 0.85, "token_match_alias"

        # Special domain keyword rules
        mobile_keywords = {"phone", "mobile", "cell", "contact", "msisdn", "telephone"}
        if tokens & mobile_keywords:
            return "mobile", 0.84, "keyword_heuristics"

        name_keywords = {"name", "fullname", "person"}
        if tokens & name_keywords and "company" not in tokens:
            return "full_name", 0.83, "keyword_heuristics"

        # Stage 4: Fuzzy String Similarity
        best_match: Optional[str] = None
        best_score = 0.0

        for canonical, aliases in self.canonical_schema.items():
            # Test against canonical name
            score = self._calculate_similarity(unprefixed_col, canonical)
            if score > best_score:
                best_score = score
                best_match = canonical

            # Test against all aliases
            for alias in aliases:
                score = self._calculate_similarity(unprefixed_col, alias)
                if score > best_score:
                    best_score = score
                    best_match = canonical

        # Acceptance threshold for fuzzy matching
        if best_score >= 0.75:
            return best_match, round(best_score, 2), "fuzzy_similarity"

        return None, 0.0, "unmapped"

    def get_schema_mapping(self, source_columns: List[str]) -> Dict[str, Dict[str, Any]]:
        """
        Generate schema mapping dictionary for a list of columns.
        """
        mapping = {}
        for col in source_columns:
            canonical, confidence, method = self.map_column(col)
            mapping[col] = {
                "canonical_field": canonical,
                "confidence": confidence,
                "method": method,
            }
        return mapping

    def transform_row(self, raw_row: Dict[str, Any]) -> Dict[str, Any]:
        """
        Transform a single raw row (dict) into a canonical Customer 360 record.
        Merges columns that point to the same canonical field (e.g. full_name and
        full_name_normalized) so that no duplicate rows or duplicate fields are produced.
        """
        canonical_record: Dict[str, Any] = {
            "full_name": None,
            "mobile": None,
            "email": None,
            "customer_id": None,
            "dob": None,
            "address": None,
            "city": None,
            "extra_attributes": {},
        }
        field_confidences: Dict[str, float] = {}

        for src_col, val in raw_row.items():
            # Skip empty or whitespace-only values
            if val is None:
                continue
            str_val = str(val).strip()
            if not str_val:
                continue

            canonical_field, confidence, _ = self.map_column(src_col)

            if canonical_field and confidence >= 0.75:
                existing_val = canonical_record[canonical_field]
                prev_confidence = field_confidences.get(canonical_field, 0.0)

                if existing_val is None:
                    canonical_record[canonical_field] = str_val
                    field_confidences[canonical_field] = confidence
                elif confidence > prev_confidence:
                    # Higher confidence column takes precedence (e.g. 'full_name' 1.0 > 'full_name_normalized' 0.98)
                    canonical_record[canonical_field] = str_val
                    field_confidences[canonical_field] = confidence
                elif confidence == prev_confidence:
                    # Same confidence: prefer properly-cased/richer value over purely lowercase
                    if str(existing_val).islower() and not str_val.islower():
                        canonical_record[canonical_field] = str_val
                    elif len(str_val) > len(str(existing_val)):
                        canonical_record[canonical_field] = str_val
            else:
                # Keep non-canonical columns in extra_attributes without altering the 7 UI fields
                canonical_record["extra_attributes"][src_col] = val

        return canonical_record

    def deduplicate_records(
        self,
        records: List[Dict[str, Any]],
        composite_keys: Optional[List[str]] = None,
    ) -> Tuple[List[Dict[str, Any]], int]:
        """
        Deduplicate records using composite keys (default: ['full_name', 'mobile']).
        If a record matches an existing key, merge missing non-empty fields into the
        existing record instead of producing an extra row.

        Returns: (deduplicated_records, duplicates_merged_count)
        """
        if composite_keys is None:
            composite_keys = ["full_name", "mobile"]

        seen: Dict[str, Dict[str, Any]] = {}
        duplicates_count = 0

        for rec in records:
            # Build unique normalized composite key
            key_parts = []
            for k in composite_keys:
                raw_v = rec.get(k)
                if raw_v is not None:
                    # Normalize text: lowercase, remove non-alphanumerics
                    clean_v = re.sub(r'[^a-z0-9]', '', str(raw_v).strip().lower())
                else:
                    clean_v = ""
                key_parts.append(clean_v)

            # Fallback to email if mobile is missing
            if not key_parts[1] and rec.get("email"):
                key_parts[1] = re.sub(r'[^a-z0-9]', '', str(rec["email"]).strip().lower())

            composite_key = "|".join(key_parts)

            # If key is completely empty, keep record as standalone
            if composite_key.replace("|", "") == "":
                # Fallback to customer_id
                cid = rec.get("customer_id")
                if cid:
                    composite_key = f"cid_{cid}"
                else:
                    seen[f"_anon_{len(seen)}"] = rec
                    continue

            if composite_key in seen:
                # Duplicate detected! Merge attributes into existing record
                duplicates_count += 1
                existing_record = seen[composite_key]
                for field, val in rec.items():
                    if field == "extra_attributes":
                        existing_record["extra_attributes"].update(val)
                    elif existing_record.get(field) is None and val is not None:
                        existing_record[field] = val
            else:
                seen[composite_key] = rec

        return list(seen.values()), duplicates_count
