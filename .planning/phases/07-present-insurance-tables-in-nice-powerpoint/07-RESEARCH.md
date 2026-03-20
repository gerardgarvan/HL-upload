# Phase 7: Present Insurance Tables in Nice PowerPoint - Research

**Researched:** 2026-03-20
**Domain:** PowerPoint presentation generation using python-pptx
**Confidence:** HIGH

## Summary

Phase 7 involves creating a polished, UF-branded PowerPoint presentation from existing CSV insurance summary tables (Phases 5 and 6) using the python-pptx library. The implementation is presentation-layer only—no new data analysis or processing. The script reads existing CSVs from `reports/` directories and generates a date-stamped `.pptx` file with native PowerPoint tables (not embedded images), styled with UF Health branding (blue #003087, orange #FA4616).

python-pptx is the standard library for programmatic PowerPoint generation in Python. Version 1.0.2 is stable and well-documented with comprehensive support for creating presentations, adding slides, building tables, and applying formatting (colors, fonts, alignment). The library does not require PowerPoint to be installed and produces standard Open XML files (.pptx) compatible with PowerPoint 2007 and later.

The main technical challenges are: (1) manually constructing tables cell-by-cell (no native DataFrame integration), (2) applying UF brand colors to 9 payer category rows without reusing the seaborn Pastel1 palette from Phase 5/6 PNG outputs, and (3) ensuring proper formatting (cell margins, text alignment, font sizing) for professional presentation quality.

**Primary recommendation:** Use python-pptx 1.0.2 with a fresh 16:9 blank presentation (no external template), manually iterate CSV data to populate native tables, apply UF blue/orange color scheme to table rows using `RGBColor.from_string()`, and set standard slide dimensions (10 × 5.625 inches). Leverage existing project patterns (Polars for CSV reading, Path for file handling) and follow the script naming convention (`build_insurance_presentation.py`).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions

**Slide organization:**
- Group by treatment type: all chemo tables together (Phase 5 chemo + Phase 6 chemo), then radiation, then SCT
- Title slide first with presentation title and high-level cohort sizes (total N, chemo N, radiation N, SCT N)
- Overview table (all treatments combined, Phase 5) immediately after title slide, before treatment-specific groups
- No section divider slides — each table slide has a descriptive title that provides context
- No final summary/conclusions slide — presentation ends after the last table

**Visual design:**
- UF Health branded: UF blue (#003087) and orange (#FA4616) color scheme applied to fresh layout (no external template file)
- Native PowerPoint tables (not embedded PNG images) — cells, borders, colors built with python-pptx for editability
- UF-branded table row colors (blue/orange tones) instead of the seaborn Pastel1 palette used in Phase 5/6 PNGs
- Professional, institutional look consistent with UF Health presentations

**Content & annotations:**
- Each table slide has a title and a brief one-line subtitle/caption explaining what the table shows
- Cohort size (N=X) in the subtitle, not the title — keeps titles clean (e.g., title: "Chemotherapy Insurance", subtitle: "N = 1,234 patients")
- Minimal footnotes — small text at bottom only where genuinely needed for key definitions or caveats
- No key findings callouts or narrative beyond subtitle

**Output & workflow:**
- Script integrated into pipeline — reads from reports/ outputs, can be re-run anytime data updates
- Output saved to reports/insurance_tables_YYYY-MM-DD.pptx (date-stamped)
- Uses python-pptx library
- Script location: scripts/build_insurance_presentation.py (follows existing naming convention)

### Claude's Discretion

- Exact UF blue/orange shade mapping to table rows (how to distribute 9 payer categories across the color scheme)
- Font choices and sizes within the UF brand guidelines
- Table cell padding and sizing
- Slide dimensions (standard 16:9 or 4:3)
- Subtitle wording for each table slide

### Deferred Ideas (OUT OF SCOPE)

None — discussion stayed within phase scope

</user_constraints>

## Standard Stack

### Core

| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| python-pptx | 1.0.2 | Create and manipulate PowerPoint (.pptx) files | Industry standard for Python PowerPoint automation; well-documented, stable API; supports Office Open XML format; no PowerPoint installation required |
| polars | (existing) | Read CSV data from Phase 5/6 outputs | Already used throughout project for data operations; fast, memory-efficient DataFrame library |
| pathlib | stdlib | File path handling | Standard library, already used in all project scripts |
| datetime | stdlib | Generate date-stamped filenames | Standard library, used in existing scripts |

### Supporting

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pptx.util | (part of python-pptx) | Length/dimension units (Inches, Pt, Emu) | Required for all sizing operations—slide dimensions, table positioning, font sizes, cell margins |
| pptx.dml.color.RGBColor | (part of python-pptx) | Specify RGB colors for fills and fonts | Required for UF brand colors (#003087, #FA4616) |
| pptx.enum.text.MSO_ANCHOR | (part of python-pptx) | Vertical text alignment in cells | Center text vertically in table cells |
| pptx.enum.text.PP_ALIGN | (part of python-pptx) | Horizontal text alignment in paragraphs | Center text horizontally in header cells |

### Alternatives Considered

| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| python-pptx | python-pptx-interface | Wrapper around python-pptx; adds abstraction layer but no material benefit for table-heavy use case |
| python-pptx | Aspose.Slides | Commercial library with more features but overkill for static table generation; licensing cost |
| Native tables | Embed PNG images | Violates user constraint—must be editable native tables |
| Fresh presentation | Template file | User specified "no external template file"—apply branding via code |
| Manual CSV parsing | PandasToPowerpoint utility | PandasToPowerpoint automates DataFrame → table conversion but doesn't support cell-level color formatting needed for UF brand row colors |

**Installation:**

```bash
pip install python-pptx
# polars, pathlib, datetime already available in project
```

Note: python-pptx has minimal dependencies and installs cleanly on Windows, macOS, Linux. No C extensions, pure Python.

## Architecture Patterns

### Recommended Project Structure

```
scripts/
├── build_insurance_presentation.py  # Phase 7 script (NEW)
├── build_insurance_by_treatment.py  # Phase 5 (existing)
└── build_post_treatment_insurance.py  # Phase 6 (existing)

reports/
├── insurance_by_treatment/          # Phase 5 CSVs (input)
│   ├── chemotherapy_insurance.csv
│   ├── radiation_insurance.csv
│   ├── sct_insurance.csv
│   └── overview_insurance.csv
├── post_treatment_insurance/        # Phase 6 CSVs (input)
│   ├── chemotherapy_post_treatment.csv
│   ├── radiation_post_treatment.csv
│   └── sct_post_treatment.csv
└── insurance_tables_YYYY-MM-DD.pptx  # Phase 7 output (NEW)
```

### Pattern 1: Script Initialization (Standard Project Pattern)

**What:** Load configuration, validate paths, set up output directories
**When to use:** All scripts in this project follow this pattern
**Example:**

```python
"""Build UF-branded PowerPoint presentation from insurance summary tables.

Reads CSVs from reports/insurance_by_treatment/ and reports/post_treatment_insurance/,
produces reports/insurance_tables_YYYY-MM-DD.pptx with native PowerPoint tables.

Usage:
    python scripts/build_insurance_presentation.py [config/paths.toml]
"""

import sys
from pathlib import Path
from datetime import datetime

PROJECT_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_ROOT))

import polars as pl
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor

from src.load.config import load_and_validate_config

def main(config_path: Path | None = None) -> None:
    """Build PowerPoint presentation from Phase 5 and Phase 6 CSV outputs."""
    print("=" * 60)
    print("UF-BRANDED INSURANCE TABLES PRESENTATION")
    print("=" * 60)

    paths = load_and_validate_config(config_path)
    reports_dir = PROJECT_ROOT / "reports"

    # Date-stamped output filename
    date_str = datetime.now().strftime("%Y-%m-%d")
    output_path = reports_dir / f"insurance_tables_{date_str}.pptx"

    # Create presentation
    prs = Presentation()
    # ... build slides ...

    prs.save(str(output_path))
    print(f"\n  Saved: {output_path}")
    print("Done.")

if __name__ == "__main__":
    config_path = Path(sys.argv[1]) if len(sys.argv) > 1 else None
    main(config_path)
```

**Source:** Adapted from existing `build_insurance_by_treatment.py` pattern

### Pattern 2: Setting Slide Dimensions (16:9 Standard)

**What:** Configure presentation for widescreen 16:9 aspect ratio
**When to use:** After creating `Presentation()` object, before adding slides
**Example:**

```python
from pptx import Presentation
from pptx.util import Inches

prs = Presentation()
prs.slide_width = Inches(10)
prs.slide_height = Inches(5.625)  # 10 ÷ 5.625 = 1.778 (16:9 ratio)
```

**Source:** [python-pptx Issue #565](https://github.com/scanny/python-pptx/issues/565)

**Alternatives:**
- 13.333 × 7.5 inches (also 16:9)
- 16 × 9 inches (also 16:9)
- Default 4:3 if not set

**Recommendation:** Use 10 × 5.625 inches (standard widescreen per maintainer Steve Canny)

### Pattern 3: Creating Tables with Proper Dimensions

**What:** Add table to slide with calculated positioning and sizing
**When to use:** Every table slide (8 total: 1 title + 7 data tables)
**Example:**

```python
from pptx.util import Inches

# Add blank slide
blank_slide_layout = prs.slide_layouts[6]  # Layout 6 is typically blank
slide = prs.slides.add_slide(blank_slide_layout)

# Define table dimensions
rows = 10  # 1 header + 9 payer categories
cols = 4   # Payer Category | Primary | First Treatment | Last Treatment
left = Inches(0.5)
top = Inches(1.5)
width = Inches(9.0)
height = Inches(3.5)

# Add table
shape = slide.shapes.add_table(rows, cols, left, top, width, height)
table = shape.table
```

**Source:** [python-pptx User Guide - Working with Tables](https://python-pptx.readthedocs.io/en/latest/user/table.html)

**Key insight:** `add_table()` returns a GraphicFrame shape; access the actual table via `.table` property.

### Pattern 4: Applying UF Brand Colors to Table Cells

**What:** Set cell background fill to UF blue/orange using hex color codes
**When to use:** Header row (blue), payer category rows (blue/orange gradient)
**Example:**

```python
from pptx.dml.color import RGBColor

# UF Health brand colors
UF_BLUE = RGBColor.from_string("003087")
UF_ORANGE = RGBColor.from_string("FA4616")

# Apply to header cell
header_cell = table.cell(0, 0)
header_cell.fill.solid()
header_cell.fill.fore_color.rgb = UF_BLUE

# Apply to data cell (example: Medicare row)
data_cell = table.cell(1, 0)
data_cell.fill.solid()
data_cell.fill.fore_color.rgb = UF_BLUE  # Or UF_ORANGE, or interpolated shade
```

**Sources:**
- [RGBColor API docs](https://python-pptx.readthedocs.io/en/latest/api/dml.html)
- [UF Health Brand Colors](https://creativeservices.ufhealth.org/identity-standards/brand-colors-2/)

**Critical:** Must call `fill.solid()` before setting `fill.fore_color.rgb`, otherwise the color assignment has no effect.

### Pattern 5: Text Formatting in Table Cells

**What:** Set cell text, font size, color, alignment
**When to use:** Every table cell (headers and data)
**Example:**

```python
from pptx.util import Pt
from pptx.enum.text import MSO_ANCHOR, PP_ALIGN
from pptx.dml.color import RGBColor

cell = table.cell(0, 0)
cell.text = "Payer Category"

# Vertical alignment (on cell)
cell.vertical_anchor = MSO_ANCHOR.MIDDLE

# Horizontal alignment, font size, color (on paragraph)
paragraph = cell.text_frame.paragraphs[0]
paragraph.alignment = PP_ALIGN.CENTER
paragraph.font.size = Pt(14)
paragraph.font.bold = True
paragraph.font.color.rgb = RGBColor(255, 255, 255)  # White text on blue header
```

**Sources:**
- [Text formatting docs](https://python-pptx.readthedocs.io/en/latest/user/text.html)
- [MSO_ANCHOR enum](https://python-pptx.readthedocs.io/en/latest/api/enum/MsoVerticalAnchor.html)
- [PP_ALIGN enum](https://python-pptx.readthedocs.io/en/latest/api/enum/PpParagraphAlignment.html)

**Gotcha:** Vertical alignment is a cell property (`cell.vertical_anchor`), but horizontal alignment and font formatting are paragraph properties (`paragraph.alignment`, `paragraph.font`).

### Pattern 6: Cell Margins for Padding

**What:** Set interior margins for text spacing inside cells
**When to use:** Optional—adjust if default padding (0.1" left/right, 0.05" top/bottom) is insufficient
**Example:**

```python
from pptx.util import Inches

cell = table.cell(0, 0)
cell.margin_left = Inches(0.1)
cell.margin_right = Inches(0.1)
cell.margin_top = Inches(0.05)
cell.margin_bottom = Inches(0.05)
```

**Source:** [Table API docs](https://python-pptx.readthedocs.io/en/latest/api/table.html)

**Default values:** Left/right = 0.1", top/bottom = 0.05". Assigning `None` restores defaults.

### Pattern 7: Reading Phase 5/6 CSV Data

**What:** Load formatted CSV tables (N (%) values) using Polars
**When to use:** Beginning of script—read all 7 CSV files before building slides
**Example:**

```python
import polars as pl
from pathlib import Path

reports_dir = PROJECT_ROOT / "reports"

# Phase 5 CSVs (insurance at treatment)
phase5_dir = reports_dir / "insurance_by_treatment"
chemo_phase5 = pl.read_csv(phase5_dir / "chemotherapy_insurance.csv")
radiation_phase5 = pl.read_csv(phase5_dir / "radiation_insurance.csv")
sct_phase5 = pl.read_csv(phase5_dir / "sct_insurance.csv")
overview = pl.read_csv(phase5_dir / "overview_insurance.csv")

# Phase 6 CSVs (post-treatment payer)
phase6_dir = reports_dir / "post_treatment_insurance"
chemo_phase6 = pl.read_csv(phase6_dir / "chemotherapy_post_treatment.csv")
radiation_phase6 = pl.read_csv(phase6_dir / "radiation_post_treatment.csv")
sct_phase6 = pl.read_csv(phase6_dir / "sct_post_treatment.csv")
```

**Note:** CSV structure from Phase 5/6 has formatted strings like `"192 (45.7%)"`. Use these directly for cell text; no additional formatting needed.

### Pattern 8: Adding Title Slide with Cohort Sizes

**What:** First slide with presentation title and high-level stats
**When to use:** First slide after creating presentation
**Example:**

```python
title_slide_layout = prs.slide_layouts[0]  # Layout 0 is typically title slide
slide = prs.slides.add_slide(title_slide_layout)

title = slide.shapes.title
subtitle = slide.placeholders[1]

title.text = "Insurance Coverage Analysis by Treatment Type"
subtitle.text = (
    f"Total Cohort: N = {total_n:,}\n"
    f"Chemotherapy: N = {chemo_n:,}\n"
    f"Radiation: N = {radiation_n:,}\n"
    f"Stem Cell Transplant: N = {sct_n:,}"
)
```

**Source:** [Working with Slides docs](https://python-pptx.readthedocs.io/en/latest/user/slides.html)

**Recommendation:** Extract cohort sizes from CSV row counts or derive from existing Phase 5 CSV metadata.

### Anti-Patterns to Avoid

- **Don't embed PNG images:** User constraint requires native editable tables, not embedded screenshots of Phase 5/6 PNG outputs
- **Don't use seaborn Pastel1 palette:** User constraint specifies UF blue/orange branding, not the Pastel1 colors from Phase 5/6
- **Don't set `text_frame.vertical_anchor`:** This property exists but doesn't work for table cells; use `cell.vertical_anchor` instead
- **Don't forget `fill.solid()` before color assignment:** Common mistake—color changes silently fail without this call
- **Don't use 4:3 default dimensions:** Explicitly set 16:9 dimensions; modern presentations expect widescreen

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| DataFrame → PowerPoint table conversion | Custom iteration logic with complex cell mapping | Manual iteration (despite PandasToPowerpoint existing) | PandasToPowerpoint doesn't support cell-level color formatting needed for UF brand row colors; simpler to iterate rows explicitly |
| Color interpolation for 9 payer categories | Manual RGB math for blue/orange gradient | Hardcode 9 colors (or simple scheme like alternating blue/orange) | Only 9 categories; gradient complexity not worth it; user has discretion on exact color mapping |
| Date formatting in filenames | Custom datetime string manipulation | `datetime.now().strftime("%Y-%m-%d")` | Standard library; already used in project scripts |
| File path handling | String concatenation with `/` or `\\` | pathlib.Path | Cross-platform, already used in project, cleaner API |
| CSV reading | Standard library `csv` module | Polars `pl.read_csv()` | Already used throughout project; faster; better type inference |

**Key insight:** python-pptx requires manual cell-by-cell table construction. While utilities like PandasToPowerpoint exist for basic DataFrame → table conversion, they don't expose fine-grained control over per-row colors needed for UF branding. Accept the explicit iteration loop; it's the standard pattern for formatted tables in python-pptx.

## Common Pitfalls

### Pitfall 1: PowerPoint Repair Prompts on Generated Files

**What goes wrong:** When opening the generated .pptx file, PowerPoint displays "We found a problem with some content" and offers to repair the file. This can remove content from slides or corrupt the presentation.

**Why it happens:** Most commonly caused by:
- Setting cell fill colors incorrectly (forgetting `fill.solid()` before `fill.fore_color.rgb`)
- Invalid color values (e.g., RGB values > 255, malformed hex strings)
- Incorrect table dimensions (rows/columns mismatch with actual data)
- Missing or corrupted image references (not applicable to this phase—tables only)

**How to avoid:**
- Always call `cell.fill.solid()` before assigning `cell.fill.fore_color.rgb`
- Use `RGBColor.from_string()` with validated 6-character hex strings (no `#` prefix)
- Validate table dimensions match data structure before population
- Test generated .pptx files incrementally during development

**Warning signs:**
- PowerPoint prompts "Do you want to recover the presentation?" on open
- Slides appear blank after "repair"
- XML parsing errors in PowerPoint repair log

**Sources:**
- [GitHub Issue #87](https://github.com/scanny/python-pptx/issues/87)
- [GitHub Issue #632](https://github.com/scanny/python-pptx/issues/632)
- [GitHub Issue #692](https://github.com/scanny/python-pptx/issues/692)

**Mitigation:** Build slides incrementally and test after each major change (title slide → first table → subsequent tables).

### Pitfall 2: Text Alignment Not Working as Expected

**What goes wrong:** Setting `cell.text_frame.vertical_anchor = MSO_ANCHOR.MIDDLE` has no effect; text remains top-aligned.

**Why it happens:** Table cells have two vertical anchor properties:
- `cell.vertical_anchor` (CORRECT—controls cell content alignment)
- `cell.text_frame.vertical_anchor` (WRONG—exists but doesn't work for table cells)

Similarly, horizontal alignment must be set on the paragraph, not the cell or text frame.

**How to avoid:**
- Vertical alignment: `cell.vertical_anchor = MSO_ANCHOR.MIDDLE`
- Horizontal alignment: `cell.text_frame.paragraphs[0].alignment = PP_ALIGN.CENTER`

**Warning signs:**
- Text stubbornly stays top-aligned despite setting "vertical_anchor"
- Text won't center horizontally despite trying to set cell-level properties

**Sources:**
- [GitHub Issue #587](https://github.com/scanny/python-pptx/issues/587)
- [GitHub Issue #191](https://github.com/scanny/python-pptx/issues/191)
- [GitHub Issue #340](https://github.com/scanny/python-pptx/issues/340)

### Pitfall 3: Font Size Values Appear Wrong

**What goes wrong:** Setting `font.size = 14` results in tiny text; reading `font.size` returns a large integer like 304800.

**Why it happens:** python-pptx uses EMUs (English Metric Units) internally. 1 point = 12700 EMUs. The `Pt()` utility function converts points to EMUs.

**How to avoid:**
- Always use `Pt()`: `font.size = Pt(14)` (NOT `font.size = 14`)
- When reading, use `.pt` property: `font.size.pt` returns `14.0`

**Warning signs:**
- Text appears microscopic or invisible
- Font size integers are in the hundreds of thousands
- Setting font size to 12 or 14 has no visible effect

**Source:** [Text-related objects API docs](https://python-pptx.readthedocs.io/en/latest/api/text.html)

### Pitfall 4: Table Position/Size Not as Expected

**What goes wrong:** Table appears in wrong location, too large, or off-slide.

**Why it happens:** Position and size parameters use EMUs by default, not inches. Without `Inches()`, values are interpreted as tiny measurements.

**How to avoid:**
- Always use `Inches()` for table positioning and sizing:
  ```python
  shape = slide.shapes.add_table(rows, cols,
      left=Inches(0.5),    # NOT: left=0.5
      top=Inches(1.5),     # NOT: top=1.5
      width=Inches(9.0),   # NOT: width=9.0
      height=Inches(3.5))  # NOT: height=3.5
  ```

**Warning signs:**
- Table is tiny (barely visible)
- Table is off-slide (not visible at all)
- Table overlaps slide title or footer

**Source:** [python-pptx User Guide - Working with Tables](https://python-pptx.readthedocs.io/en/latest/user/table.html)

### Pitfall 5: CSV Data Structure Mismatch

**What goes wrong:** Script assumes CSV has certain columns or structure, but Phase 5/6 outputs differ.

**Why it happens:** Phase 5 outputs have 3 data columns (Primary, First Treatment, Last Treatment); Phase 6 has 1 data column (Post-Treatment). Slide organization requires combining these into 4-column tables per treatment type.

**How to avoid:**
- Validate CSV structure at load time (check column names)
- Handle graceful degradation if expected CSVs missing (per existing project pattern from Phase 5/6 decisions)
- Document expected CSV structure in script docstring

**Warning signs:**
- KeyError when accessing CSV columns
- Empty or malformed table slides
- Misaligned data (wrong column headers)

**Recommendation:** Read both Phase 5 and Phase 6 CSVs for each treatment type, validate structure, then merge into 4-column table rows for slide population.

### Pitfall 6: RGBColor Hex String Format Errors

**What goes wrong:** `RGBColor.from_string("003087")` works, but `RGBColor.from_string("#003087")` fails or produces wrong colors.

**Why it happens:** `RGBColor.from_string()` expects raw hex string without `#` prefix. Including `#` causes parsing errors or silent failures.

**How to avoid:**
- UF_BLUE = `RGBColor.from_string("003087")` ✓ CORRECT
- UF_BLUE = `RGBColor.from_string("#003087")` ✗ WRONG
- Alternative: `RGBColor(0, 48, 135)` using RGB integer values

**Warning signs:**
- Colors appear black or white instead of expected UF blue/orange
- TypeError or ValueError on color assignment
- Generated file triggers PowerPoint repair prompt

**Source:** [RGBColor API docs](https://python-pptx.readthedocs.io/en/latest/api/dml.html)

## Code Examples

Verified patterns from official sources:

### Creating 16:9 Presentation with UF Brand Colors

```python
"""Build UF-branded PowerPoint presentation from insurance summary tables."""

from pathlib import Path
from datetime import datetime

from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor

# UF Health brand colors (official hex codes)
UF_BLUE = RGBColor.from_string("003087")
UF_ORANGE = RGBColor.from_string("FA4616")
WHITE = RGBColor(255, 255, 255)

# Standard 9-category payer order
PAYER_CATEGORIES = [
    "Medicare",
    "Medicaid",
    "Dual eligible",
    "Private",
    "Other government",
    "Self-pay",
    "Other",
    "Unavailable",
    "Unknown",
]

def create_presentation() -> Presentation:
    """Create new 16:9 presentation with standard dimensions."""
    prs = Presentation()
    prs.slide_width = Inches(10)
    prs.slide_height = Inches(5.625)  # 16:9 aspect ratio
    return prs

def add_title_slide(prs: Presentation, cohort_sizes: dict) -> None:
    """Add title slide with presentation title and cohort sizes."""
    title_slide_layout = prs.slide_layouts[0]
    slide = prs.slides.add_slide(title_slide_layout)

    title = slide.shapes.title
    subtitle = slide.placeholders[1]

    title.text = "Insurance Coverage Analysis by Treatment Type"
    subtitle.text = (
        f"Total Cohort: N = {cohort_sizes['total']:,}\n"
        f"Chemotherapy: N = {cohort_sizes['chemo']:,}\n"
        f"Radiation: N = {cohort_sizes['radiation']:,}\n"
        f"Stem Cell Transplant: N = {cohort_sizes['sct']:,}"
    )

def add_table_slide(
    prs: Presentation,
    title: str,
    subtitle: str,
    table_data: list[dict],
    column_headers: list[str],
) -> None:
    """Add slide with UF-branded table.

    Args:
        prs: Presentation object
        title: Slide title (e.g., "Chemotherapy Insurance")
        subtitle: One-line caption (e.g., "N = 1,234 patients")
        table_data: List of row dicts with keys matching column_headers
        column_headers: List of column header strings
    """
    blank_layout = prs.slide_layouts[6]  # Blank slide layout
    slide = prs.slides.add_slide(blank_layout)

    # Add title and subtitle as text boxes
    title_box = slide.shapes.add_textbox(
        Inches(0.5), Inches(0.3), Inches(9.0), Inches(0.5)
    )
    title_frame = title_box.text_frame
    title_para = title_frame.paragraphs[0]
    title_para.text = title
    title_para.font.size = Pt(24)
    title_para.font.bold = True
    title_para.font.color.rgb = UF_BLUE

    subtitle_box = slide.shapes.add_textbox(
        Inches(0.5), Inches(0.8), Inches(9.0), Inches(0.3)
    )
    subtitle_frame = subtitle_box.text_frame
    subtitle_para = subtitle_frame.paragraphs[0]
    subtitle_para.text = subtitle
    subtitle_para.font.size = Pt(14)
    subtitle_para.font.color.rgb = RGBColor(100, 100, 100)  # Gray

    # Create table
    rows = len(table_data) + 1  # +1 for header row
    cols = len(column_headers)
    left = Inches(0.5)
    top = Inches(1.5)
    width = Inches(9.0)
    height = Inches(3.5)

    shape = slide.shapes.add_table(rows, cols, left, top, width, height)
    table = shape.table

    # Format header row
    for col_idx, header_text in enumerate(column_headers):
        cell = table.cell(0, col_idx)
        cell.text = header_text
        cell.fill.solid()
        cell.fill.fore_color.rgb = UF_BLUE
        cell.vertical_anchor = MSO_ANCHOR.MIDDLE

        para = cell.text_frame.paragraphs[0]
        para.alignment = PP_ALIGN.CENTER
        para.font.size = Pt(14)
        para.font.bold = True
        para.font.color.rgb = WHITE

    # Populate data rows with alternating UF blue/orange tones
    for row_idx, row_data in enumerate(table_data, start=1):
        # Determine row color (alternate between blue and orange tones)
        if row_idx % 2 == 1:
            row_color = RGBColor(200, 220, 255)  # Light blue
        else:
            row_color = RGBColor(255, 220, 200)  # Light orange

        for col_idx, header in enumerate(column_headers):
            cell = table.cell(row_idx, col_idx)
            cell.text = str(row_data.get(header, ""))
            cell.fill.solid()
            cell.fill.fore_color.rgb = row_color
            cell.vertical_anchor = MSO_ANCHOR.MIDDLE

            para = cell.text_frame.paragraphs[0]
            if col_idx == 0:
                # First column (Payer Category): left-aligned, bold
                para.alignment = PP_ALIGN.LEFT
                para.font.bold = True
            else:
                # Data columns: center-aligned
                para.alignment = PP_ALIGN.CENTER
            para.font.size = Pt(12)

def main():
    """Build UF-branded PowerPoint presentation."""
    prs = create_presentation()

    # Add title slide
    cohort_sizes = {
        "total": 5000,
        "chemo": 1234,
        "radiation": 2345,
        "sct": 567,
    }
    add_title_slide(prs, cohort_sizes)

    # Example: Add overview table slide
    column_headers = ["Payer Category", "Primary Insurance", "First Treatment", "Last Treatment"]
    table_data = [
        {"Payer Category": "Medicare", "Primary Insurance": "192 (45.7%)",
         "First Treatment": "180 (42.9%)", "Last Treatment": "185 (44.0%)"},
        # ... remaining 8 payer categories ...
    ]
    add_table_slide(
        prs,
        title="Insurance Coverage Overview",
        subtitle="All treatment types combined (N = 5,000)",
        table_data=table_data,
        column_headers=column_headers,
    )

    # Save presentation
    date_str = datetime.now().strftime("%Y-%m-%d")
    output_path = Path(f"reports/insurance_tables_{date_str}.pptx")
    prs.save(str(output_path))
    print(f"Saved: {output_path}")

if __name__ == "__main__":
    main()
```

**Sources:**
- [python-pptx Quickstart](https://python-pptx.readthedocs.io/en/latest/user/quickstart.html)
- [Working with Tables](https://python-pptx.readthedocs.io/en/latest/user/table.html)
- [RGBColor API](https://python-pptx.readthedocs.io/en/latest/api/dml.html)

### Reading Phase 5 and Phase 6 CSVs with Polars

```python
import polars as pl
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]
reports_dir = PROJECT_ROOT / "reports"

# Phase 5: Insurance at treatment (3 columns)
phase5_dir = reports_dir / "insurance_by_treatment"
chemo_at_treatment = pl.read_csv(phase5_dir / "chemotherapy_insurance.csv")
# Expected columns: "Payer Category", "Primary Insurance", "First Chemo", "Last Chemo"

# Phase 6: Post-treatment insurance (1 column)
phase6_dir = reports_dir / "post_treatment_insurance"
chemo_post_treatment = pl.read_csv(phase6_dir / "chemotherapy_post_treatment.csv")
# Expected columns: "Payer Category", "Post-Treatment"

# Merge into 4-column table for slide
# (Approach: iterate rows, combine Phase 5 + Phase 6 by Payer Category)
combined_rows = []
for payer_cat in PAYER_CATEGORIES:
    phase5_row = chemo_at_treatment.filter(
        pl.col("Payer Category") == payer_cat
    ).to_dicts()[0]

    phase6_row = chemo_post_treatment.filter(
        pl.col("Payer Category") == payer_cat
    ).to_dicts()[0]

    combined_rows.append({
        "Payer Category": payer_cat,
        "Primary Insurance": phase5_row["Primary Insurance"],
        "First Chemo": phase5_row["First Chemo"],
        "Last Chemo": phase5_row["Last Chemo"],
        "Post-Treatment": phase6_row["Post-Treatment"],
    })

# combined_rows is now ready for add_table_slide()
```

**Note:** Assumes Phase 5 and Phase 6 CSVs both have 9 rows in `PAYER_CATEGORIES` order. Validate structure before merging.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| python-pptx 0.6.x | python-pptx 1.0.2 | 2023 | Stable 1.0 release; API mostly unchanged from 0.6.x but now marked as production-ready |
| Template-based generation | Programmatic fresh layouts | N/A | User constraint: no external template file; build UF branding via code |
| Pandas for data manipulation | Polars for data manipulation | Project-wide decision | Faster, lower memory; already standardized across all scripts |
| Embedded PNG table images | Native PowerPoint tables | N/A | User constraint: editable tables required |

**Deprecated/outdated:**
- **python-pptx pre-1.0 "beta" versions:** Now stable at 1.0.2; safe for production use
- **PandasToPowerpoint utility for this use case:** Doesn't support per-row color formatting needed for UF branding; simpler to iterate manually

## Open Questions

1. **Exact UF blue/orange color mapping to 9 payer categories**
   - What we know: User has discretion on mapping; must use UF blue (#003087) and orange (#FA4616) tones
   - What's unclear: Gradient interpolation? Alternating pattern? Specific shades for each category?
   - Recommendation: Start with simple alternating pattern (light blue, light orange, repeat) for readability; can refine based on user feedback

2. **Font choices within UF brand guidelines**
   - What we know: UF brand uses specific fonts (requires download per UF template docs); python-pptx uses PowerPoint defaults if fonts not installed
   - What's unclear: Do we specify font names explicitly, or accept defaults?
   - Recommendation: Accept PowerPoint defaults (Calibri, Arial) for simplicity; UF fonts optional. User has discretion.

3. **Table column widths**
   - What we know: Can set `table.columns[idx].width = Inches(x)`
   - What's unclear: Optimal widths for 4 columns (Payer Category wider, data columns equal)?
   - Recommendation: Equal-width columns (9.0" ÷ 4 = 2.25" each) for simplicity; first column could be 2.5", others 2.17" if Payer Category text is long

4. **Footnotes placement and content**
   - What we know: User wants "minimal footnotes—small text at bottom only where genuinely needed"
   - What's unclear: Are any footnotes genuinely needed? (e.g., definition of "Post-Treatment payer"?)
   - Recommendation: Defer to user review; add placeholder function `add_footnote()` but leave content TBD

## Sources

### Primary (HIGH confidence)

- **python-pptx Official Documentation** - [https://python-pptx.readthedocs.io/](https://python-pptx.readthedocs.io/)
  - [Quickstart Guide](https://python-pptx.readthedocs.io/en/latest/user/quickstart.html)
  - [Working with Tables](https://python-pptx.readthedocs.io/en/latest/user/table.html)
  - [Working with Text](https://python-pptx.readthedocs.io/en/latest/user/text.html)
  - [Working with Slides](https://python-pptx.readthedocs.io/en/latest/user/slides.html)
  - [RGBColor API](https://python-pptx.readthedocs.io/en/latest/api/dml.html)
  - [Table API](https://python-pptx.readthedocs.io/en/latest/api/table.html)
  - [Text API](https://python-pptx.readthedocs.io/en/latest/api/text.html)

- **python-pptx GitHub Repository** - [https://github.com/scanny/python-pptx](https://github.com/scanny/python-pptx)
  - [Issue #565 - 16:9 slide dimensions](https://github.com/scanny/python-pptx/issues/565)
  - [Issue #587 - Cell text alignment](https://github.com/scanny/python-pptx/issues/587)
  - [Issue #52 - Table cell background color](https://github.com/scanny/python-pptx/issues/52)

- **UF Health Brand Guidelines** - [https://creativeservices.ufhealth.org/identity-standards/brand-colors-2/](https://creativeservices.ufhealth.org/identity-standards/brand-colors-2/)
  - Official UF colors: Orange #FA4616, Blue #0021A5
  - Note: CONTEXT.md specifies Blue #003087; both are valid UF blues per different sources

### Secondary (MEDIUM confidence)

- **Practical Business Python - Creating PowerPoint Presentations** - [https://pbpython.com/creating-powerpoint.html](https://pbpython.com/creating-powerpoint.html)
  - Best practices for automated PowerPoint generation
  - Template analysis patterns

- **PandasToPowerpoint GitHub** - [https://github.com/robintw/PandasToPowerpoint](https://github.com/robintw/PandasToPowerpoint)
  - DataFrame → table conversion utility (evaluated but not used due to color formatting limitations)

- **Medium Articles on python-pptx Automation** - Various authors
  - [How to Automate PowerPoint Presentations Using Excel Data and Python](https://medium.com/@esersaygin/how-to-automate-powerpoint-presentations-using-excel-data-and-python-2c6fae75fd87)
  - [Introduction to python-pptx](https://medium.com/@p123456dan.mse99/introduction-to-python-pptx-768a0b579f83)

### Tertiary (LOW confidence)

- **GeeksforGeeks python-pptx Tutorial** - General tutorial; less reliable than official docs
- **Various StackOverflow python-pptx questions** - Case-by-case solutions; verify against official docs

## Metadata

**Confidence breakdown:**
- Standard stack: **HIGH** - python-pptx is the de facto standard; version 1.0.2 is stable; official docs comprehensive
- Architecture: **HIGH** - Official docs provide clear patterns; existing project scripts establish conventions
- Pitfalls: **HIGH** - Verified via GitHub issues, official docs, and community reports

**Research date:** 2026-03-20
**Valid until:** ~2026-06-20 (90 days for stable library; python-pptx has slow release cadence, unlikely to change materially)

---

**END OF RESEARCH**
