import io
from typing import List, Dict, Any, Optional
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from pydantic import BaseModel, Field

from app.schema_mapper import (
    Customer360SchemaMapper,
    DataSourceSampler,
    ValueSemanticAnalyzer,
    CANONICAL_FIELDS
)

router = APIRouter(prefix="/api/customer360", tags=["Customer 360 Schema Mapper"])
mapper = Customer360SchemaMapper()


# PYDANTIC SCHEMAS

class MapColumnsRequest(BaseModel):
    columns: List[str]
    sample_rows: Optional[List[Dict[str, Any]]] = None

class AnalyzeSourceRequest(BaseModel):
    csv_content: Optional[str] = None
    records: Optional[List[Dict[str, Any]]] = None
    sample_size: int = Field(default=10, ge=3, le=50)

class MapDatabaseRequest(BaseModel):
    connection_string: str = Field(
        default="demo",
        description="SQLAlchemy connection URI (e.g. 'sqlite:///my_data.db', 'postgresql://...', or 'demo' for instant sample data)"
    )
    table_name: str = Field(
        default="demo_customers",
        description="Name of the table to sample (or 'demo_customers')"
    )
    sample_size: int = Field(default=10, ge=3, le=50)

class TransformRequest(BaseModel):
    records: List[Dict[str, Any]] = Field(
        default=[
            {"full_name_normalized": "Rahul Sharma", "contact_no": "+91 98765 43210", "email_id": "rahul@example.com", "city_name": "Bengaluru"},
            {"name": "Rahul Sharma", "mobile": "9876543210", "email": "rahul@example.com", "city": "Bengaluru"}
        ],
        description="List of raw customer records to transform and deduplicate"
    )
    column_mappings: Optional[Dict[str, Any]] = Field(
        default=None,
        description="Optional precomputed column mappings. If omitted, fields are automatically inferred from data samples!"
    )
    deduplicate: bool = True


# ENDPOINTS

@router.get("/canonical-fields")
def get_canonical_fields():
    """Returns the list of Customer 360 canonical target fields and their properties."""
    return {
        "status": "success",
        "canonical_fields": CANONICAL_FIELDS
    }


@router.post("/map-columns")
def map_columns(request: MapColumnsRequest):
    """
    Infers canonical mappings for a list of column names.
    If sample_rows are provided, value semantic profiling is applied.
    """
    if not request.columns:
        raise HTTPException(status_code=400, detail="Column list cannot be empty")

    if request.sample_rows:
        mappings = mapper.get_smart_schema_mapping_from_samples(
            request.sample_rows, columns=request.columns
        )
    else:
        mappings = {col: mapper.map_column_smart(col) for col in request.columns}

    return {
        "status": "success",
        "total_columns": len(request.columns),
        "mappings": mappings
    }


@router.post("/analyze-source")
def analyze_source(request: AnalyzeSourceRequest):
    """
    Analyzes connected CSV data or record sets.
    Samples 5-10 rows, profiles cell values, and returns confidence scores and explanations.
    """
    if request.csv_content:
        result = mapper.process_csv_dataset(
            request.csv_content,
            sample_size=request.sample_size,
            deduplicate=False
        )
        return {
            "status": "success",
            "source_type": "csv",
            "has_header_detected": result["has_header_detected"],
            "columns": result["columns"],
            "sample_rows_analyzed": result["sample_rows_analyzed"],
            "total_rows": result["total_source_rows"],
            "column_mappings": result["column_mappings"],
            "sample_records_preview": result["sample_records_preview"]
        }

    elif request.records:
        effective_sample_size = min(request.sample_size, len(request.records))
        sample_rows = request.records[:effective_sample_size]
        cols = list(sample_rows[0].keys()) if sample_rows else []
        mappings = mapper.get_smart_schema_mapping_from_samples(sample_rows, columns=cols)

        return {
            "status": "success",
            "source_type": "records",
            "columns": cols,
            "sample_rows_analyzed": len(sample_rows),
            "total_rows": len(request.records),
            "column_mappings": mappings,
            "sample_records_preview": [mapper.transform_row_with_mapping(r, mappings) for r in sample_rows[:5]]
        }
    else:
        raise HTTPException(status_code=400, detail="Either csv_content or records must be provided")


@router.post("/map-database")
def map_database(request: MapDatabaseRequest):
    """
    Connects to a SQL database table, samples 5-10 rows randomly,
    and infers canonical schema mappings.
    """
    try:
        columns, sample_rows = DataSourceSampler.sample_database(
            request.connection_string,
            request.table_name,
            sample_size=request.sample_size
        )
        mappings = mapper.get_smart_schema_mapping_from_samples(sample_rows, columns=columns)

        return {
            "status": "success",
            "table_name": request.table_name,
            "sample_rows_analyzed": len(sample_rows),
            "columns": columns,
            "column_mappings": mappings,
            "sample_rows": sample_rows[:5]
        }
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Database connection error: {str(e)}")


@router.post("/upload")
async def upload_csv(
    file: UploadFile = File(...),
    deduplicate: bool = Form(default=True),
    sample_size: int = Form(default=10)
):
   
    try:
        content_bytes = await file.read()
        csv_text = content_bytes.decode("utf-8", errors="replace")

        result = mapper.process_csv_dataset(
            csv_text,
            sample_size=sample_size,
            deduplicate=deduplicate
        )

        return {
            "status": "success",
            "filename": file.filename,
            "has_header_detected": result["has_header_detected"],
            "detected_columns": result["columns"],
            "sample_rows_analyzed": result["sample_rows_analyzed"],
            "total_records": result["total_source_rows"],
            "deduplicated_records_count": result["deduplicated_rows"],
            "duplicates_merged": result["duplicates_merged"],
            "column_mappings": result["column_mappings"],
            "records": result["all_records"]
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error processing CSV: {str(e)}")


@router.post("/transform")
def transform_records(request: TransformRequest):
    
    if not request.records:
        return {"status": "success", "total_input_records": 0, "records": []}

    # Infer mappings if not provided or if dummy placeholder mappings were sent
    has_valid_mapping = False
    if request.column_mappings:
        # Check if mappings contains non-empty definitions
        has_valid_mapping = any(
            isinstance(v, str) or (isinstance(v, dict) and bool(v.get("canonical_field") or v.get("canonical")))
            for v in request.column_mappings.values()
        )

    if not has_valid_mapping:
        cols = list(request.records[0].keys()) if request.records else []
        sample_rows = request.records[:10]
        mappings = mapper.get_smart_schema_mapping_from_samples(sample_rows, columns=cols)
    else:
        mappings = request.column_mappings

    transformed = [mapper.transform_row_with_mapping(r, mappings) for r in request.records]

    duplicates_merged = 0
    final_records = transformed
    if request.deduplicate:
        final_records, duplicates_merged = mapper.deduplicate_records(transformed)

    return {
        "status": "success",
        "total_input_records": len(request.records),
        "deduplicated_records_count": len(final_records),
        "duplicates_merged": duplicates_merged,
        "column_mappings": mappings,
        "records": final_records
    }
