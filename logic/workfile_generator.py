"""
Workfile Generator Logic Module
===============================
Creates standardized SQL files from raw MySQL Workbench code with proper
headers, JIRA folder management, and backup creation.

Supports: PROCEDURE, FUNCTION, TRIGGER, VIEW

Author: Abhinav Prasad
"""

import os
import re
import glob
from datetime import datetime
from pathlib import Path


# Default configuration
DEFAULT_DEVELOPER = "Abhinav Prasad"
DEFAULT_TEMP_PREFIX = "temp_ap_"


def get_current_date_stamp() -> str:
    """Returns current date in YYYYMMDD format."""
    return datetime.now().strftime("%Y%m%d")


def get_formatted_date() -> str:
    """Returns current date in 'DD Mon YYYY' format for header."""
    return datetime.now().strftime("%d %b %Y")


def detect_sql_type(raw_sql: str) -> tuple[str | None, str | None]:
    """
    Detect the type of SQL object from the CREATE statement.
    Returns: (sql_type, object_name) or (None, None)
    """
    sql = raw_sql.strip()
    
    patterns = [
        (r'CREATE\s+(?:DEFINER\s*=\s*`[^`]+`@`[^`]+`\s+)?PROCEDURE\s+`([^`]+)`', 'PROCEDURE'),
        (r'CREATE\s+(?:DEFINER\s*=\s*`[^`]+`@`[^`]+`\s+)?FUNCTION\s+`([^`]+)`', 'FUNCTION'),
        (r'CREATE\s+(?:DEFINER\s*=\s*`[^`]+`@`[^`]+`\s+)?TRIGGER\s+`([^`]+)`', 'TRIGGER'),
        (
            r'CREATE\s+'
            r'(?:OR\s+REPLACE\s+)?'
            r'(?:ALGORITHM\s*=\s*\S+\s+)?'
            r'(?:DEFINER\s*=\s*\S+\s+)?'
            r'(?:SQL\s+SECURITY\s+\w+\s+)?'
            r'VIEW\s+`([^`]+)`',
            'VIEW'
        ),
    ]
    
    for pattern, sql_type in patterns:
        match = re.search(pattern, sql, re.IGNORECASE)
        if match:
            return sql_type, match.group(1)
    
    return None, None


def remove_definer(raw_sql: str) -> str:
    """Remove the DEFINER clause from CREATE statement."""
    pattern = r'DEFINER\s*=\s*`[^`]+`\s*@\s*`[^`]+`\s*'
    return re.sub(pattern, '', raw_sql, count=1)


def generate_header(sql_type: str, object_name: str, jira_id: str, 
                    developer_name: str = DEFAULT_DEVELOPER,
                    temp_prefix: str = DEFAULT_TEMP_PREFIX,
                    description: str = "") -> str:
    """Generate the header block with USE, DROP statements, and comment block."""
    
    use_stmt = "USE db_ostrum_ltn; -- db_ostrum_ltn; db_ostrum_lgw; db_ostrum_beg; db_ostrum_scl; db_ostrum_dmo; db_ostrum_jfk"
    
    temp_name = f"{temp_prefix}{object_name}"
    
    drop_keywords = {
        'PROCEDURE': 'PROCEDURE',
        'FUNCTION': 'FUNCTION',
        'TRIGGER': 'TRIGGER',
        'VIEW': 'VIEW'
    }
    
    keyword = drop_keywords.get(sql_type, sql_type)
    drop_temp = f"-- DROP {keyword} IF EXISTS {temp_name};"
    drop_orig = f"-- DROP {keyword} IF EXISTS {object_name};"
    
    desc_text = f"OP-{jira_id}"
    if description:
        desc_text += f" {description}"
    
    header = f"""
{use_stmt}

{drop_temp}
{drop_orig}

-- ==================================================================================================== 
-- Created By\t:\t{developer_name} 
-- Created Time\t:\t{get_formatted_date()}
-- Description\t:\t{desc_text}
-- ====================================================================================================

DELIMITER //

"""
    return header


def generate_footer() -> str:
    """Generate the footer with DELIMITER closing."""
    return "\n\nDELIMITER ;"


def process_sql(raw_sql: str, jira_id: str, 
                developer_name: str = DEFAULT_DEVELOPER,
                temp_prefix: str = DEFAULT_TEMP_PREFIX,
                description: str = "") -> tuple[str, str, str]:
    """
    Process the raw SQL code and return the formatted output.
    
    Returns: (processed_sql, object_name, sql_type)
    """
    sql_type, object_name = detect_sql_type(raw_sql)
    
    if not sql_type:
        raise ValueError("Could not detect SQL type. Ensure input starts with CREATE PROCEDURE/FUNCTION/TRIGGER/VIEW")
    
    # Remove DEFINER clause
    processed_sql = remove_definer(raw_sql)
    processed_sql = processed_sql.strip()
    
    # Handle the END statement
    if processed_sql.endswith('END'):
        processed_sql = processed_sql[:-3] + 'END//'
    elif not processed_sql.endswith('//'):
        processed_sql += '//'
    
    # Generate header and footer
    header = generate_header(sql_type, object_name, jira_id, developer_name, temp_prefix, description)
    footer = generate_footer()
    
    result = header + processed_sql + footer
    
    return result, object_name, sql_type


def split_sql_objects(raw_sql: str) -> list[str]:
    """
    Split raw SQL input into individual SQL objects.
    Returns a list of individual SQL code blocks.
    """
    raw_sql = raw_sql.replace('\r\n', '\n').replace('\r', '\n')
    
    create_pattern = (
        r'CREATE\s+'
        r'(?:OR\s+REPLACE\s+)?'
        r'(?:ALGORITHM\s*=\s*\S+\s+)?'
        r'(?:DEFINER\s*=\s*\S+\s+)?'
        r'(?:SQL\s+SECURITY\s+\w+\s+)?'
        r'(?:PROCEDURE|FUNCTION|TRIGGER|VIEW)\s+'
    )
    
    matches = list(re.finditer(create_pattern, raw_sql, re.IGNORECASE))
    create_positions = [m.start() for m in matches]
    
    if not create_positions:
        return [raw_sql.strip()] if raw_sql.strip() else []
    
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


def find_jira_folder(jira_num: str, base_dir: str) -> str | None:
    """Find an existing JIRA folder matching the given number."""
    escaped_base = glob.escape(base_dir)
    
    patterns = [
        f"OP-{jira_num}",
        f"OP - {jira_num}",
        f"OP  - {jira_num}",
        f"OP - {jira_num} [*",
        f"OP  - {jira_num} [*",
    ]
    
    for pattern in patterns:
        search_path = os.path.join(escaped_base, pattern)
        matches = glob.glob(search_path + "*")
        if matches:
            return matches[0]
    
    return None


def create_jira_folder(jira_num: str, base_dir: str, description: str = "") -> str:
    """Create a new JIRA folder."""
    if description:
        folder_name = f"OP - {jira_num} [{description}]"
    else:
        folder_name = f"OP - {jira_num}"
    
    folder_path = os.path.join(base_dir, folder_name)
    os.makedirs(folder_path, exist_ok=True)
    
    return folder_path


def get_next_version_number(folder_path: str, object_name: str, date_stamp: str) -> int:
    """Determine the next version number for the file."""
    pattern = f"{date_stamp}_*{object_name}.sql"
    existing = glob.glob(os.path.join(folder_path, pattern))
    
    if not existing:
        return 1
    
    versions = []
    for filepath in existing:
        filename = os.path.basename(filepath)
        match = re.match(rf'{date_stamp}_(\d+)', filename)
        if match:
            versions.append(int(match.group(1)))
    
    if versions:
        return max(versions) + 1
    return 1


def save_files(processed_sql: str, object_name: str, folder_path: str) -> tuple[str, str]:
    """
    Save the processed SQL to the JIRA folder and create a backup.
    
    Returns: (main_filepath, backup_filepath)
    """
    date_stamp = get_current_date_stamp()
    version = get_next_version_number(folder_path, object_name, date_stamp)
    
    # Main filename
    main_filename = f"{date_stamp}_{version:02d} {object_name}.sql"
    main_filepath = os.path.join(folder_path, main_filename)
    
    with open(main_filepath, 'w', encoding='utf-8') as f:
        f.write(processed_sql)
    
    # Create Backup folder
    backup_folder = os.path.join(folder_path, "Backup")
    os.makedirs(backup_folder, exist_ok=True)
    
    backup_filename = f"{date_stamp}_{version:02d} {object_name} - backup.sql"
    backup_filepath = os.path.join(backup_folder, backup_filename)
    
    with open(backup_filepath, 'w', encoding='utf-8') as f:
        f.write(processed_sql)
    
    return main_filepath, backup_filepath


def process_pasted_content_to_clipboard(raw_text: str, jira_id: str,
                                        developer_name: str = DEFAULT_DEVELOPER,
                                        temp_prefix: str = DEFAULT_TEMP_PREFIX,
                                        description: str = "") -> dict:
    """
    Process pasted SQL content and return the generated output as a string
    (no files are written to disk).

    Args:
        raw_text: The raw SQL content to process
        jira_id: JIRA ticket number (for header comments only)
        developer_name: Name for the header
        temp_prefix: Prefix for temp objects
        description: Description text for the header

    Returns: Dictionary with keys:
        'content'   - str: all generated SQL blocks joined by double newlines
        'processed' - list of {name, type} dicts
        'errors'    - list of error strings
    """
    results = {
        'content': '',
        'processed': [],
        'errors': []
    }

    sql_objects = split_sql_objects(raw_text)

    if not sql_objects:
        results['errors'].append("No valid SQL objects found in input")
        return results

    parts = []
    for i, sql_code in enumerate(sql_objects, 1):
        try:
            processed_sql, object_name, sql_type = process_sql(
                sql_code, jira_id, developer_name, temp_prefix, description
            )
            parts.append(processed_sql)
            results['processed'].append({
                'name': object_name,
                'type': sql_type,
            })
        except Exception as e:
            snippet = sql_code[:50].replace('\n', ' ').strip() + "..."
            results['errors'].append(f"Object {i} ({snippet}): {str(e)}")

    results['content'] = "\n\n".join(parts)
    return results


def process_pasted_content(raw_text: str, jira_id: str, base_folder: str,
                           developer_name: str = DEFAULT_DEVELOPER,
                           temp_prefix: str = DEFAULT_TEMP_PREFIX,
                           description: str = "",
                           create_jira_folder_flag: bool = True) -> dict:
    """
    Process pasted SQL content and save to folder structure.
    
    Args:
        raw_text: The raw SQL content to process
        jira_id: JIRA ticket number (for header, and folder if create_jira_folder_flag=True)
        base_folder: The root folder to work in
        developer_name: Name for the header
        temp_prefix: Prefix for temp objects
        description: Description for folder name and header
        create_jira_folder_flag: If True, create/use JIRA subfolder. If False, save directly to base_folder.
    
    Returns: Dictionary with results
    """
    results = {
        'processed': [],
        'errors': [],
        'folder_path': None,
        'folder_created': False
    }
    
    # Determine output folder
    if create_jira_folder_flag and jira_id:
        # Find or create JIRA folder
        folder_path = find_jira_folder(jira_id, base_folder)
        
        if folder_path:
            results['folder_path'] = folder_path
            results['folder_created'] = False
        else:
            folder_path = create_jira_folder(jira_id, base_folder, description)
            results['folder_path'] = folder_path
            results['folder_created'] = True
    else:
        # Use base folder directly
        folder_path = base_folder
        results['folder_path'] = folder_path
        results['folder_created'] = False
    
    # Split into individual SQL objects
    sql_objects = split_sql_objects(raw_text)
    
    if not sql_objects:
        results['errors'].append("No valid SQL objects found in input")
        return results
    
    for i, sql_code in enumerate(sql_objects, 1):
        try:
            processed_sql, object_name, sql_type = process_sql(
                sql_code, jira_id, developer_name, temp_prefix, description
            )
            
            main_path, backup_path = save_files(processed_sql, object_name, folder_path)
            
            results['processed'].append({
                'name': object_name,
                'type': sql_type,
                'main_file': os.path.basename(main_path),
                'backup_file': os.path.basename(backup_path)
            })
            
        except Exception as e:
            snippet = sql_code[:50].replace('\n', ' ').strip() + "..."
            results['errors'].append(f"Object {i} ({snippet}): {str(e)}")
    
    return results
