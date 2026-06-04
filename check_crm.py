"""Standalone diagnostic — counts columns vs values in every CRM INSERT.
Run from D:\\SDGNext:  python check_crm.py
"""
import re

with open("app/api/routes/crm.py", encoding="utf-8") as f:
    code = f.read()

print("=" * 60)

# --- Check the MASHUPDATASOURCE common_cols / common_vals ---
cols_m = re.search(r'common_cols\s*=\s*"""(.+?)"""', code, re.DOTALL)
vals_m = re.search(r'common_vals\s*=\s*f"""(.+?)"""', code, re.DOTALL)

if not cols_m or not vals_m:
    print("Could NOT find common_cols/common_vals — file structure differs.")
else:
    cols = [c.strip() for c in cols_m.group(1).replace('\n', ',').split(',') if c.strip()]
    vals_raw = vals_m.group(1).replace('{now}', 'X')
    vals = [v.strip() for v in vals_raw.replace('\n', ',').split(',') if v.strip()]
    status = "MATCH ✓" if len(cols) == len(vals) else f"MISMATCH (off by {len(cols)-len(vals)}) — FILE IS OLD"
    print(f"MASHUPDATASOURCE : cols={len(cols)}  vals={len(vals)}  {status}")

# --- Check the other 3 INSERTs ---
insert_pattern = re.compile(
    r'INSERT\s+INTO\s+\{schema\}\.(\w+)\s*\((.*?)\)\s*VALUES\s*\((.*?)\)',
    re.DOTALL | re.IGNORECASE
)
for m in insert_pattern.finditer(code):
    table = m.group(1)
    if table == "MASHUPDATASOURCE":
        continue  # handled above
    cols_str = m.group(2).replace('{oracle_extra_col}', '').replace('{extra_col}', '')
    vals_str = m.group(3).replace('{oracle_extra_val}', '').replace('{extra_val}', '')
    vals_str = re.sub(r'\{now\}', 'X', vals_str)
    cols = [c.strip() for c in cols_str.replace('\n', ',').split(',') if c.strip()]
    vals = [v.strip() for v in vals_str.replace('\n', ',').split(',') if v.strip()]
    status = "MATCH ✓" if len(cols) == len(vals) else f"MISMATCH (off by {len(cols)-len(vals)})"
    print(f"{table:17s}: cols={len(cols)}  vals={len(vals)}  {status}")

print("=" * 60)