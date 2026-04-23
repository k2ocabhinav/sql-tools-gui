"""
DB Automation Converter Logic Module
=====================================
Converts database objects (procedures, functions, triggers) for 
database automation by adding proper headers, commenting debug calls, 
and wrapping with DELIMITER statements.

Supports: PROCEDURE, FUNCTION, TRIGGER

Author: Abhinav Prasad
"""

import os
import re
from datetime import datetime
from pathlib import Path


# ============================================================================
# REGEX PATTERNS - Match MySQL Workbench "SHOW CREATE" output
# ============================================================================

# Pattern to detect and extract object type and name
# More flexible patterns that work with various DEFINER formats
PROCEDURE_PATTERN = re.compile(
    r"CREATE\s+(?:DEFINER\s*=\s*\S+\s+)?PROCEDURE\s+[`'\"]?(\w+)[`'\"]?",
    re.IGNORECASE
)
FUNCTION_PATTERN = re.compile(
    r"CREATE\s+(?:DEFINER\s*=\s*\S+\s+)?FUNCTION\s+[`'\"]?(\w+)[`'\"]?",
    re.IGNORECASE
)
TRIGGER_PATTERN = re.compile(
    r"CREATE\s+(?:DEFINER\s*=\s*\S+\s+)?TRIGGER\s+[`'\"]?(\w+)[`'\"]?",
    re.IGNORECASE
)

# Debug call pattern (comment out debug lines)
# Matches:
#   CALL sys_log_debug_sp(...)
#   CALL sys_log_debug_v0_sp(...) through CALL sys_log_debug_v9_sp(...)
DEBUG_PATTERN = re.compile(
    r"(?m)^(\s*)(CALL\s+sys_log_debug(?:_v[0-9])?_sp\b.*)$",
    re.IGNORECASE
)

# DELIMITER pattern for splitting files
SPLIT_PATTERN = re.compile(r"DELIMITER\s+\S+", re.IGNORECASE)

# Clean trailing delimiters
CLEAN_END_PATTERN = re.compile(r"\s*(?:\$\$|//|;)\s*$", re.IGNORECASE)

# DEFINER removal pattern - flexible to match various formats
DEFINER_PATTERN = re.compile(r"DEFINER\s*=\s*\S+\s+", re.IGNORECASE)


# ============================================================================
# HEADER GENERATION
# ============================================================================

def get_header(filename_nomen: str, timestamp: str, developer_name: str = "Abhinav Prasad") -> str:
    """Generate the file header with metadata."""
    return f"""
/* 
Filename Nomencalature :- {filename_nomen}

For example: 
V20240829_01__booking_request_details_sp 
V20240829_02__booking_request_details_sp 
*/ 

-- ==================================================================================================== 
-- Created/Modified By    :    {developer_name}
-- Created/Modified Time  :    {timestamp}
-- Description            :     
-- ==================================================================================================== 
"""


# ============================================================================
# DETECTION FUNCTIONS
# ============================================================================

def detect_object_type(content: str) -> tuple[str | None, str | None]:
    """
    Detect the type of SQL object from CREATE statement.
    
    Returns: (object_type, object_name) or (None, None)
    """
    content = content.strip()
    
    # Check PROCEDURE first
    match = PROCEDURE_PATTERN.search(content)
    if match:
        return 'PROCEDURE', match.group(1)
    
    # Check FUNCTION
    match = FUNCTION_PATTERN.search(content)
    if match:
        return 'FUNCTION', match.group(1)
    
    # Check TRIGGER
    match = TRIGGER_PATTERN.search(content)
    if match:
        return 'TRIGGER', match.group(1)
    
    return None, None


# ============================================================================
# PROCESSING FUNCTIONS
# ============================================================================

def process_single_object(content: str, sequence_num: int, date_str: str, 
                          timestamp_str: str, developer_name: str = "Abhinav Prasad") -> tuple[str, str, str, str] | None:
    """
    Process a single SQL object (procedure, function, or trigger).
    
    Returns: (formatted_content, object_name, filename, object_type) or None if invalid
    """
    content = content.strip()
    if not content:
        return None
    
    # Detect object type and name
    obj_type, obj_name = detect_object_type(content)
    if not obj_type or not obj_name:
        return None
    
    # Remove DEFINER clause
    content = DEFINER_PATTERN.sub("", content)
    
    # Fix CREATE spacing (normalize whitespace)
    content = re.sub(rf"CREATE\s+{obj_type}", f"CREATE {obj_type}", content, flags=re.IGNORECASE)
    
    # Comment out Debug Lines (for procedures and functions)
    if obj_type in ('PROCEDURE', 'FUNCTION'):
        content = DEBUG_PATTERN.sub(r"\1-- \2", content)
    
    # Clean trailing delimiters
    content = CLEAN_END_PATTERN.sub("", content)
    
    # Prepare Filename
    new_filename = f"{date_str}_{sequence_num:02d}__{obj_name}.sql"
    
    # Generate Header
    header = get_header(new_filename, timestamp_str, developer_name)
    
    # Generate DROP statement based on type
    drop_stmt = f"DROP {obj_type} IF EXISTS `{obj_name}`;"
    
    # Wrap with Delimiters
    final_script = f"""{header}
{drop_stmt}

DELIMITER //

{content}//

DELIMITER ;"""
    
    return final_script, obj_name, new_filename, obj_type


def split_sql_objects(raw_sql: str) -> list[str]:
    """
    Split raw SQL into individual objects.
    
    Returns: List of SQL code blocks
    """
    raw_sql = raw_sql.replace('\r\n', '\n').replace('\r', '\n')
    
    # First try splitting by DELIMITER statements
    chunks = re.split(SPLIT_PATTERN, raw_sql)
    
    # Filter out empty chunks and chunks without CREATE statements
    result = []
    for chunk in chunks:
        chunk = chunk.strip()
        if chunk and detect_object_type(chunk)[0]:
            result.append(chunk)
    
    if result:
        return result
    
    # Fallback: Try splitting by CREATE statements
    create_pattern = r'CREATE\s+(?:DEFINER\s*=\s*\S+\s+)?(?:PROCEDURE|FUNCTION|TRIGGER)\s+'
    
    matches = list(re.finditer(create_pattern, raw_sql, re.IGNORECASE))
    create_positions = [m.start() for m in matches]
    
    if not create_positions:
        return []
    
    sql_objects = []
    for i, pos in enumerate(create_positions):
        if i + 1 < len(create_positions):
            sql_block = raw_sql[pos:create_positions[i + 1]]
        else:
            sql_block = raw_sql[pos:]
        
        sql_block = sql_block.strip()
        if sql_block:
            sql_objects.append(sql_block)
    
    return sql_objects


def process_pasted_content(raw_text: str, starting_seq: int = 1, 
                           developer_name: str = "Abhinav Prasad") -> list[dict]:
    """
    Process pasted SQL content containing one or more objects.
    
    Returns: List of dictionaries with 'content', 'name', 'filename', 'type', or 'error'
    """
    results = []
    
    now = datetime.now()
    date_str = now.strftime("V%Y%m%d")
    timestamp_str = now.strftime("%d %b %Y")
    
    # Split into individual objects
    sql_objects = split_sql_objects(raw_text)
    
    if not sql_objects:
        return [{'error': 'No valid PROCEDURE, FUNCTION, or TRIGGER found in input'}]
    
    current_seq = starting_seq
    
    for sql_block in sql_objects:
        result = process_single_object(sql_block, current_seq, date_str, 
                                       timestamp_str, developer_name)
        
        if result:
            formatted, obj_name, filename, obj_type = result
            results.append({
                'content': formatted,
                'name': obj_name,
                'filename': filename,
                'type': obj_type,
                'sequence': current_seq
            })
            current_seq += 1
        else:
            snippet = sql_block[:60].replace('\n', ' ')
            results.append({
                'error': f"Could not process: {snippet}..."
            })
    
    return results


def process_folder(input_folder: str, output_folder: str, starting_seq: int = 1,
                   developer_name: str = "Abhinav Prasad") -> dict:
    """
    Process all SQL files from input folder and write to output folder.
    
    Returns: Dictionary with results
    """
    results = {
        'processed': [],
        'errors': []
    }
    
    input_path = Path(input_folder)
    output_path = Path(output_folder)

    if not input_path.exists():
        results['errors'].append(f"Input folder not found: {input_folder}")
        return results

    if not input_path.is_dir():
        results['errors'].append(f"Input path is not a folder: {input_folder}")
        return results

    output_path.mkdir(parents=True, exist_ok=True)

    try:
        sql_files = sorted(
            (f for f in input_path.iterdir() if f.is_file() and f.suffix.lower() == '.sql'),
            key=lambda p: p.name.lower()
        )
    except Exception as e:
        results['errors'].append(f"Could not read input folder {input_folder}: {str(e)}")
        return results
    
    if not sql_files:
        results['errors'].append(f"No .sql files found in {input_folder}")
        return results
    
    now = datetime.now()
    date_str = now.strftime("V%Y%m%d")
    timestamp_str = now.strftime("%d %b %Y")
    
    current_seq = starting_seq
    
    for sql_file in sql_files:
        try:
            with open(sql_file, 'r', encoding='utf-8') as f:
                raw_content = f.read()
            
            # Split file into chunks
            sql_objects = split_sql_objects(raw_content)
            
            for sql_block in sql_objects:
                result = process_single_object(sql_block, current_seq, date_str,
                                               timestamp_str, developer_name)
                
                if result:
                    formatted, obj_name, filename, obj_type = result
                    
                    output_file = output_path / filename
                    with open(output_file, 'w', encoding='utf-8') as f:
                        f.write(formatted)
                    
                    results['processed'].append({
                        'source': sql_file.name,
                        'output': filename,
                        'name': obj_name,
                        'type': obj_type,
                        'sequence': current_seq
                    })
                    current_seq += 1
                    
        except Exception as e:
            results['errors'].append(f"{sql_file.name}: {str(e)}")
    
    return results


def process_pasted_to_files(raw_text: str, output_folder: str, starting_seq: int = 1,
                            developer_name: str = "Abhinav Prasad") -> dict:
    """
    Process pasted content and save each object to a file.
    
    Returns: Dictionary with results
    """
    results = {
        'processed': [],
        'errors': []
    }
    
    output_path = Path(output_folder)
    output_path.mkdir(parents=True, exist_ok=True)
    
    processed_items = process_pasted_content(raw_text, starting_seq, developer_name)
    
    for item in processed_items:
        if 'error' in item:
            results['errors'].append(item['error'])
            continue
        
        try:
            output_file = output_path / item['filename']
            with open(output_file, 'w', encoding='utf-8') as f:
                f.write(item['content'])
            
            results['processed'].append({
                'output': item['filename'],
                'name': item['name'],
                'type': item['type'],
                'sequence': item['sequence']
            })
        except Exception as e:
            results['errors'].append(f"{item['name']}: {str(e)}")
    
    return results
