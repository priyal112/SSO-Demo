import csv
import io
import json
from typing import Any, Dict, List, Optional
from fastapi import APIRouter, File, HTTPException, UploadFile
from pydantic import BaseModel, Field

from app.schema_mapper import Customer360SchemaMapper

router = APIRouter(prefix="/api/customer360", tags=["Customer 360"])
mapper = Customer360SchemaMapper()


# -------------------------------------------------------------
# Request & Response Models
# -------------------------------------------------------------
class ColumnMappingRequest(BaseModel):
    columns: List[str] = Field(..., example=["full_name_normalized", "mobile_normalized", "phone_number"])


class ColumnMappingResponse(BaseModel):
    status: str
    canonical_fields: List[str]
    mappings: Dict[str, Dict[str, Any]]


class TransformRecordsRequest(BaseModel):
    records: List[Dict[str, Any]]
    deduplicate: bool = True
    composite_keys: Optional[List[str]] = Field(
        default=["full_name", "mobile"],
        description="Keys used to detect duplicate entries across rows"
    )


class TransformRecordsResponse(BaseModel):
    status: str
    total_input_records: int
    deduplicated_records_count: int
    duplicates_merged: int
    records: List[Dict[str, Any]]


# -------------------------------------------------------------
# Endpoints
# -------------------------------------------------------------
@router.get("/canonical-fields")
async def get_canonical_fields():
    """
    Returns the list of 7 canonical fields supported by Customer 360.
    """
    return {
        "status": "success",
        "canonical_fields": list(mapper.canonical_schema.keys()),
        "schema_details": mapper.canonical_schema,
    }


@router.post("/map-columns", response_model=ColumnMappingResponse)
async def map_columns(payload: ColumnMappingRequest):
    """
    Intelligently maps incoming database or file columns to Customer 360's canonical fields.
    Prevents duplicate schema fields on the frontend (e.g., 'full_name_normalized' -> 'full_name').
    """
    mappings = mapper.get_schema_mapping(payload.columns)
    return ColumnMappingResponse(
        status="success",
        canonical_fields=list(mapper.canonical_schema.keys()),
        mappings=mappings,
    )


@router.post("/transform", response_model=TransformRecordsResponse)
async def transform_records(payload: TransformRecordsRequest):
    """
    Transforms raw records (from DB queries or uploads) into canonical Customer 360 records.
    Merges columns pointing to the same canonical field and prevents duplicate rows.
    """
    raw_records = payload.records
    transformed_records = [mapper.transform_row(row) for row in raw_records]

    if payload.deduplicate:
        final_records, merged_count = mapper.deduplicate_records(
            transformed_records,
            composite_keys=payload.composite_keys
        )
    else:
        final_records = transformed_records
        merged_count = 0

    return TransformRecordsResponse(
        status="success",
        total_input_records=len(raw_records),
        deduplicated_records_count=len(final_records),
        duplicates_merged=merged_count,
        records=final_records,
    )


@router.post("/upload")
async def upload_file_and_map(
    file: UploadFile = File(...),
    deduplicate: bool = True,
):
    """
    Upload a CSV or JSON file from any database/source.
    Auto-maps columns, resolves variations, merges duplicates, and outputs Customer 360 records.
    """
    filename = file.filename.lower()
    content = await file.read()

    rows: List[Dict[str, Any]] = []

    try:
        if filename.endswith(".csv"):
            text_stream = io.StringIO(content.decode("utf-8-sig"))
            reader = csv.DictReader(text_stream)
            rows = [dict(r) for r in reader]
        elif filename.endswith(".json"):
            data = json.loads(content.decode("utf-8"))
            if isinstance(data, list):
                rows = data
            elif isinstance(data, dict) and "records" in data:
                rows = data["records"]
            else:
                rows = [data]
        else:
            raise HTTPException(
                status_code=400,
                detail="Unsupported file format. Please upload a .csv or .json file."
            )
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"Error parsing file content: {str(e)}"
        )

    if not rows:
        return {
            "status": "success",
            "message": "File is empty or contains no records",
            "total_records": 0,
            "records": [],
        }

    # Extract all incoming column names
    source_columns = list(rows[0].keys())
    column_mappings = mapper.get_schema_mapping(source_columns)

    # Transform all rows to canonical Customer 360 fields
    transformed = [mapper.transform_row(r) for r in rows]

    if deduplicate:
        final_records, duplicates_merged = mapper.deduplicate_records(transformed)
    else:
        final_records = transformed
        duplicates_merged = 0

    return {
        "status": "success",
        "file_name": file.filename,
        "detected_columns": source_columns,
        "column_mappings": column_mappings,
        "total_source_rows": len(rows),
        "deduplicated_rows": len(final_records),
        "duplicates_merged": duplicates_merged,
        "records": final_records,
    }
