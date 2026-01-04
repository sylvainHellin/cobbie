# Detailed Specification: Grading Sheet for Human Evaluation

## 1. Overview

Create a CLI tool `scripts/create_grading_sheet.py` that exports evaluation data from MLflow into a structured Excel grading sheet for inter-rater reliability analysis. The tool supports evaluation by 3 judges: LLM-as-a-judge (pre-filled), Human Judge 1, and Human Judge 2.

### Purpose
- Enable manual human evaluation of Cobbie's answers
- Calculate inter-rater reliability (Krippendorff's alpha) between judges
- Compare LLM and human evaluation to validate automated grading
- Support research publication and quality assurance

### Assumptions
- Evaluation data is logged to MLflow with 5 criteria (Abstention, Faithfulness, Completeness, Transparency, Relevance)
- Each criterion follows the BAML schema structure defined in `baml_src/schemas.baml`
- Faithfulness + Completeness determine binary classification (correct/wrong/abstained)
- Human evaluators will use Excel to fill in their grades
- The same evaluation framework applies to both LLM and human judges

---

## 2. Requirements Summary

**Inputs:**
- One or more MLflow evaluation run IDs (32-character hex strings)
- Optional: custom output path for Excel file

**Outputs:**
- Excel file (.xlsx) with 7 sheets:
  1. **Instructions** - Evaluation guidelines and criteria definitions
  2. **LLM Judge** - Pre-filled with LLM's grades
  3. **Human Judge 1** - Empty template for manual entry
  4. **Human Judge 2** - Empty template for manual entry
  5. **Krippendorff's Alpha Summary** - Inter-rater reliability metrics
  6. **Binary Classification Comparison** - Derived classifications across judges
  7. **Agreement Statistics** - Detailed agreement analysis

**Key Features:**
- Data validation dropdowns for human entry (Yes/No/Na)
- Protected cells to prevent accidental edits of metadata
- Formula-based binary classification calculation
- Both combined (3-way) and pairwise Krippendorff's alpha
- Color-coded agreement indicators
- Optional justification field for human evaluators

---

## 3. Data Structure

### 3.1 Evaluation Criteria (from BAML schemas.baml)

1. **Abstention** (Boolean)
   - `true`: System explicitly declined to answer
   - `false`: Answer was provided
   - Examples: "I cannot determine...", "Insufficient information..."

2. **Faithfulness** (Yes/No/Na)
   - Are all claims grounded in valid sources?
   - Category-specific rules:
     - Cat 1: BIM element properties only
     - Cat 2: Simple computations (counting, summing, averaging)
     - Cat 3: Complex geometric computations
     - Cat 4: BIM data + EXPLICITLY STATED assumptions
   - `Na`: Only if abstention is true

3. **Completeness** (Yes/No/Na)
   - Are all relevant facts included?
   - `Na`: If abstention is true OR open-ended question

4. **Transparency** (Yes/No/Na)
   - Are sources/methods explicitly disclosed for each claim?
   - Each claim must cite specific property, method, or assumption
   - `Na`: Only if abstention is true

5. **Relevance** (Yes/No/Na)
   - Does answer directly address the question?
   - Must address correct aspect/property and scope
   - `Na`: Only if abstention is true

### 3.2 Binary Classification Derivation

```
IF abstention = true
  → "abstained"
ELSE IF faithfulness = Yes AND completeness = Yes
  → "correct"
ELSE
  → "wrong"
```

### 3.3 MLflow Data Structure

**Nested Run Hierarchy:**
```
Parent Run: Evaluation_YYYY-MM-DD-HH-MM-SS
├── Parameters: model_name, provider_name, tools
├── Metrics: Aggregated statistics
└── Nested Runs (one per question):
    ├── Run Name: question_{index}_{id}
    ├── Parameters:
    │   ├── question, ground_truth, category, question_id
    │   ├── answer, justification, classification
    │   ├── abstention (bool), faithfulness (str), completeness (str)
    │   └── transparency (str), relevance (str)
    └── Metrics:
        ├── cobbie_duration, verifier_duration
        └── token counts
```

**Data Extraction Pattern** (from analyze_evaluation_runs.py):
```python
# Fetch nested runs
nested_runs = client.search_runs(
    experiment_ids=[experiment_id],
    filter_string=f'tags.mlflow.parentRunId = "{parent_run_id}"',
    max_results=1000
)

# Extract from each run
params = run.data.params
question_id = int(run.info.run_name.split("_")[1])
abstention = params.get("abstention") == "True"
faithfulness = params.get("faithfulness", "Na")
# ... etc
```

---

## 4. Excel Sheet Specifications

### 4.1 Sheet 1: Instructions

**Content:**
- **Section 1: Overview** - Purpose of grading sheet, role of human judges
- **Section 2: Evaluation Framework** - Description of 5 criteria
- **Section 3: Grading Guidelines**
  - How to interpret Yes/No/Na
  - When to use Na (abstention cases, open-ended questions)
  - Numerical tolerance: ±2% for continuous, exact for discrete
- **Section 4: Category Definitions**
  - Cat 1: Direct Property Lookup
  - Cat 2: Aggregation (count, sum, average)
  - Cat 3: Complex Computation (geometry, formulas)
  - Cat 4: Estimation (assumptions required)
- **Section 5: Binary Classification** - How it's derived from criteria
- **Section 6: Workflow** - How to fill out the sheet, save, and submit

**Format:**
- Plain text with headers
- Markdown-style formatting (bold, lists)
- No data entry cells

### 4.2 Sheets 2-4: Judge Sheets (LLM, Human 1, Human 2)

**Column Structure:**

| Column | Header | Type | LLM Sheet | Human Sheets | Description |
|--------|--------|------|-----------|--------------|-------------|
| A | Question ID | Int | Filled | Protected | Database question ID |
| B | Question | Text | Filled | Protected | Question text (wrapped) |
| C | Cobbie's Answer | Text | Filled | Protected | System response (wrapped) |
| D | Ground Truth | Text | Filled | Protected | Reference answer (wrapped) |
| E | Category | Int | Filled | Protected | Category number (1-4) |
| F | Category Name | Text | Filled | Protected | Human-readable category |
| G | Project | Text | Filled | Protected | IFC project name |
| H | Model | Text | Filled | Protected | LLM model used |
| I | **Abstention** | Boolean | Filled | **Editable** | TRUE/FALSE checkbox |
| J | **Faithfulness** | Dropdown | Filled | **Editable** | Yes/No/Na dropdown |
| K | **Completeness** | Dropdown | Filled | **Editable** | Yes/No/Na dropdown |
| L | **Transparency** | Dropdown | Filled | **Editable** | Yes/No/Na dropdown |
| M | **Relevance** | Dropdown | Filled | **Editable** | Yes/No/Na dropdown |
| N | **Justification** | Text | Filled | **Editable** | Optional explanation |
| O | Binary Classification | Formula | Formula | Formula | Derived from I, J, K |

**Cell Formatting:**

*For LLM Judge Sheet:*
- All cells: Read-only display (no protection needed, informational)
- Criterion columns (I-M): Show actual LLM grades
- Binary column (O): Formula-calculated

*For Human Judge Sheets:*
- Columns A-H: Protected (locked, cannot edit)
- Column I (Abstention): Editable checkbox/boolean cell
  - Display format: Checkbox or TRUE/FALSE
  - Data validation: Boolean only
- Columns J-M (Criteria): Editable dropdown cells
  - Data validation: List = "Yes,No,Na"
  - No blank allowed
- Column N (Justification): Editable text cell
  - Word wrap enabled
  - Optional (can be left blank)
- Column O (Binary): Formula (protected)
  ```excel
  =IF(I2, "abstained", IF(AND(J2="Yes", K2="Yes"), "correct", "wrong"))
  ```

**Sheet Protection:**
- Human sheets: Protected with option to select unlocked cells
- No password (easy to unprotect if needed)
- Allows editing only in columns I-N

**Row Heights & Column Widths:**
- Row 1 (header): 30px, bold, background color
- Data rows: Auto-adjust to content, minimum 20px
- Column B (Question): 50 char width, wrap text
- Column C (Answer): 60 char width, wrap text
- Column D (Ground Truth): 50 char width, wrap text
- Columns I-M (Criteria): 12 char width, center align
- Column N (Justification): 40 char width, wrap text

### 4.3 Sheet 5: Krippendorff's Alpha Summary

**Purpose:** Display inter-rater reliability metrics for each criterion

**Table Structure:**

| Criterion | Combined α (3 judges) | LLM-Human1 α | LLM-Human2 α | Human1-Human2 α |
|-----------|----------------------|--------------|--------------|-----------------|
| Abstention | 0.XXX | 0.XXX | 0.XXX | 0.XXX |
| Faithfulness | 0.XXX | 0.XXX | 0.XXX | 0.XXX |
| Completeness | 0.XXX | 0.XXX | 0.XXX | 0.XXX |
| Transparency | 0.XXX | 0.XXX | 0.XXX | 0.XXX |
| Relevance | 0.XXX | 0.XXX | 0.XXX | 0.XXX |
| Binary Classification | 0.XXX | 0.XXX | 0.XXX | 0.XXX |

**Calculation Notes:**
- Alpha values calculated only when human data is present
- Missing values (empty cells in human sheets) handled by Krippendorff's algorithm
- Display "Awaiting human input" if sheets are empty
- Display completion percentage: "Human 1: 45/100 (45%), Human 2: 0/100 (0%)"

**Interpretation Guide:**
```
α > 0.800: Excellent reliability
α 0.667-0.800: Good reliability
α 0.500-0.667: Moderate reliability
α < 0.500: Poor reliability
```

**Color Coding:**
- Green: α ≥ 0.667
- Yellow: 0.500 ≤ α < 0.667
- Red: α < 0.500

### 4.4 Sheet 6: Binary Classification Comparison

**Purpose:** Side-by-side comparison of derived binary classifications

**Table Structure:**

| Question ID | Question (truncated) | LLM Binary | Human1 Binary | Human2 Binary | Agreement |
|-------------|---------------------|------------|---------------|---------------|-----------|
| 909 | What is the height... | correct | correct | wrong | Partial (2/3) |
| 1234 | How many windows... | abstained | abstained | abstained | All Agree |
| ... | ... | ... | ... | ... | ... |

**Agreement Column:**
- "All Agree" - All 3 judges have same classification
- "Partial (2/3)" - 2 out of 3 agree
- "No Agreement" - All 3 disagree

**Color Coding:**
- Green: All Agree
- Yellow: Partial (2/3)
- Red: No Agreement

**Summary Statistics:**
```
Total Questions: 100
All Agree: 67 (67%)
Partial Agreement: 28 (28%)
No Agreement: 5 (5%)
```

### 4.5 Sheet 7: Agreement Statistics

**Purpose:** Detailed agreement analysis per criterion

**Section 1: Percentage Agreement**

| Criterion | LLM-Human1 | LLM-Human2 | Human1-Human2 | Overall (3-way) |
|-----------|------------|------------|---------------|----------------|
| Abstention | 92% (92/100) | 0% (0/0) | 0% (0/0) | 0% (0/100) |
| Faithfulness | 78% (78/100) | - | - | - |
| ... | ... | ... | ... | ... |

**Section 2: Confusion Matrices** (per criterion, pairwise)

Example for Faithfulness (LLM vs Human1):
```
                Human1
           Yes   No   Na
LLM  Yes   45    3    2
     No    5     38   1
     Na    0     1    5
```

**Section 3: Disagreement Patterns**

Table showing questions with highest disagreement:

| Question ID | Criterion | LLM | Human1 | Human2 | Notes |
|-------------|-----------|-----|--------|--------|-------|
| 1234 | Faithfulness | Yes | No | No | Numerical precision issue |
| 5678 | Completeness | No | Yes | Yes | Missing implicit fact |

**Section 4: Category-Level Agreement**

Breakdown of agreement by question category:

| Category | Questions | Avg Agreement | Krippendorff α |
|----------|-----------|---------------|----------------|
| 1 - Direct Property | 25 | 85% | 0.78 |
| 2 - Aggregation | 30 | 72% | 0.65 |
| 3 - Computation | 20 | 68% | 0.61 |
| 4 - Estimation | 25 | 55% | 0.48 |

---

## 5. Implementation Plan

### 5.1 File Structure

**New File:** `scripts/create_grading_sheet.py`

**Key Functions:**

```python
# Data Fetching (reuse patterns from analyze_evaluation_runs.py)
def fetch_nested_runs(client, parent_run_id, experiment_id) -> List
def extract_evaluation_data(run) -> Dict
def fetch_question_data(question_ids) -> Dict

# Data Processing
def build_grading_dataframe(runs, question_data) -> pd.DataFrame
def derive_binary_classification(abstention, faithfulness, completeness) -> str
def encode_criterion_values(values, criterion_type) -> np.array

# Krippendorff's Alpha
def calculate_criterion_alpha(df, criterion, judges) -> Dict[str, float]
def calculate_all_alphas(df) -> pd.DataFrame
def handle_missing_data(values) -> List

# Agreement Statistics
def calculate_percentage_agreement(df, criterion) -> Dict
def create_confusion_matrix(df, criterion, judge1, judge2) -> pd.DataFrame
def identify_disagreement_patterns(df) -> pd.DataFrame
def calculate_category_agreement(df) -> pd.DataFrame

# Excel Creation
def create_instructions_sheet(wb) -> None
def create_judge_sheet(wb, sheet_name, df, judge_prefix, editable) -> None
def create_alpha_summary_sheet(wb, alpha_df) -> None
def create_binary_comparison_sheet(wb, df) -> None
def create_agreement_stats_sheet(wb, df, stats) -> None
def apply_formatting(ws, sheet_type) -> None

# Utilities
def sanitize_for_excel(text) -> str  # Reuse from analyze_evaluation_runs.py
def read_grading_sheet(filepath) -> pd.DataFrame  # For re-reading

# Main
def main():
    # Parse CLI args
    # Fetch MLflow data
    # Build DataFrame
    # Create Excel
    # Save and summarize
```

### 5.2 Dependencies

**Add to pyproject.toml:**
```toml
dependencies = [
    # ... existing ...
    "krippendorff>=0.7.0",  # Inter-rater reliability
    "scikit-learn>=1.6.0",  # Confusion matrices
]
```

**Key Imports:**
```python
# MLflow
import mlflow
from mlflow import MlflowClient

# Data
import pandas as pd
import numpy as np

# Excel
from openpyxl import Workbook
from openpyxl.styles import Font, Alignment, PatternFill, Protection
from openpyxl.worksheet.datavalidation import DataValidation
from openpyxl.formatting.rule import CellIsRule

# Metrics
import krippendorff
from sklearn.metrics import confusion_matrix

# Local
from src.config import DB_PATH, MLFLOW_URI
```

### 5.3 CLI Interface

**Usage:**
```bash
# Basic - single run
uv run scripts/create_grading_sheet.py --run-ids abc123def456

# Multiple runs
uv run scripts/create_grading_sheet.py --run-ids run1 run2 run3

# Custom output path
uv run scripts/create_grading_sheet.py --run-ids abc123 --output reports/my_grading.xlsx

# Re-calculate after human input (future enhancement)
uv run scripts/create_grading_sheet.py --read-from reports/grading_sheet.xlsx
```

**Arguments:**
```python
parser.add_argument(
    "--run-ids",
    nargs="+",
    required=True,
    help="MLflow evaluation run IDs to include"
)
parser.add_argument(
    "--output",
    help="Custom output path (default: reports/grading_sheet_{timestamp}.xlsx)"
)
```

### 5.4 Krippendorff's Alpha Implementation

**Encoding Strategy:**

For **Abstention** (Boolean):
```python
def encode_abstention(value):
    if value is None or pd.isna(value):
        return np.nan  # Missing data
    return 1 if value else 0
```

For **Yes/No/Na Criteria** (Ordinal):
```python
def encode_yesnoNa(value):
    if value is None or pd.isna(value):
        return np.nan  # Missing data
    mapping = {"Yes": 2, "Na": 1, "No": 0}
    return mapping.get(value, np.nan)
```

For **Binary Classification** (Nominal):
```python
def encode_binary(value):
    if value is None or pd.isna(value):
        return np.nan
    mapping = {"correct": 2, "abstained": 1, "wrong": 0}
    return mapping.get(value, np.nan)
```

**Calculation:**
```python
import krippendorff

def calculate_criterion_alpha(df, criterion, judges=['llm', 'human1', 'human2']):
    """
    Calculate Krippendorff's alpha for a criterion across judges.

    Returns:
        {
            'combined': alpha for all judges,
            'llm_human1': pairwise,
            'llm_human2': pairwise,
            'human1_human2': pairwise
        }
    """
    # Build reliability data matrix (judges × questions)
    reliability_data = []
    for judge in judges:
        col_name = f"{judge}_{criterion.lower()}"
        values = df[col_name].apply(encode_function_for_criterion)
        reliability_data.append(values.to_numpy())

    # Combined alpha (all 3 judges)
    combined_alpha = krippendorff.alpha(
        reliability_data,
        level_of_measurement='ordinal' if criterion != 'abstention' else 'nominal'
    )

    # Pairwise alphas
    llm_h1_alpha = krippendorff.alpha(
        [reliability_data[0], reliability_data[1]],
        level_of_measurement='ordinal'
    )
    # ... similar for other pairs

    return {
        'combined': combined_alpha,
        'llm_human1': llm_h1_alpha,
        'llm_human2': llm_h2_alpha,
        'human1_human2': h1_h2_alpha
    }
```

**Handling Missing Data:**
- Krippendorff's alpha natively handles missing data (NaN values)
- Missing = human hasn't filled that cell yet
- Alpha is calculated only over questions where at least 2 judges provided grades
- Report completion rate: "Human 1: 45/100 questions completed (45%)"

---

## 6. Edge Cases & Error Handling

### 6.1 Missing Evaluation Data
- **Issue:** Some questions may not have verifier results in MLflow
- **Solution:** Skip those questions, log warning, report count in summary

### 6.2 Malformed MLflow Data
- **Issue:** Missing parameters or unexpected format
- **Solution:** Use default values (Na for criteria, False for abstention), log warning

### 6.3 Empty Human Sheets
- **Issue:** Initial export has no human data
- **Solution:** Alpha summary shows "Awaiting human input - 0/100 completed"

### 6.4 Partially Complete Human Sheets
- **Issue:** Some humans filled, not all questions
- **Solution:**
  - Calculate alphas only for completed questions
  - Display completion statistics
  - Pairwise comparisons work even if one judge is incomplete

### 6.5 Duplicate Question IDs
- **Issue:** Multiple runs may contain same questions
- **Solution:**
  - Detect duplicates
  - Keep first occurrence, log warning
  - Or: Add suffix to question_id (e.g., 909_run1, 909_run2)

### 6.6 Very Long Text
- **Issue:** Answers exceeding Excel cell limits (32,767 chars)
- **Solution:** Truncate with "...[truncated]", log warning

### 6.7 Special Characters
- **Issue:** Control characters in text (0x00-0x1F)
- **Solution:** Use `sanitize_for_excel()` function (already exists)

### 6.8 No Nested Runs Found
- **Issue:** Run ID is invalid or has no nested question runs
- **Solution:** Print error message, exit gracefully

---

## 7. Output Format

### 7.1 File Naming
**Default Pattern:**
```
reports/grading_sheet_YYYY-MM-DD_HH-MM-SS.xlsx
```

**Custom Path:**
```
reports/my_custom_name.xlsx
```

### 7.2 Console Output

**During Execution:**
```
Fetching data from MLflow...
  Run ID: abc123def456
  Experiment: Evaluation
  Found 100 nested question runs

Building grading DataFrame...
  Questions: 100
  Categories: 1=25, 2=30, 3=20, 4=25

Creating Excel workbook...
  ✓ Instructions sheet
  ✓ LLM Judge sheet (100 questions)
  ✓ Human Judge 1 sheet (empty, ready for input)
  ✓ Human Judge 2 sheet (empty, ready for input)
  ✓ Krippendorff's Alpha Summary (awaiting human input)
  ✓ Binary Classification Comparison
  ✓ Agreement Statistics

Saved to: reports/grading_sheet_2026-01-03_14-30-00.xlsx

Summary:
  Total Questions: 100
  LLM Evaluations: 100 (100%)
  Human 1 Evaluations: 0 (0%)
  Human 2 Evaluations: 0 (0%)

Next steps:
  1. Open the Excel file
  2. Fill in "Human Judge 1" and/or "Human Judge 2" sheets
  3. Save the file
  4. Re-run with --read-from to calculate inter-rater reliability
```

**After Re-Reading (Future Enhancement):**
```
Reading grading sheet from: reports/grading_sheet_2026-01-03_14-30-00.xlsx

Completion Status:
  LLM Judge: 100/100 (100%)
  Human Judge 1: 85/100 (85%)
  Human Judge 2: 100/100 (100%)

Calculating Krippendorff's Alpha...
  Abstention: α=0.892 (excellent)
  Faithfulness: α=0.745 (good)
  Completeness: α=0.678 (good)
  Transparency: α=0.623 (moderate)
  Relevance: α=0.811 (excellent)
  Binary Classification: α=0.756 (good)

Updated file saved to: reports/grading_sheet_2026-01-03_14-30-00_analyzed.xlsx
```

---

## 8. Testing Strategy

### 8.1 Unit Tests
- Test data extraction with mock MLflow runs
- Test encoding functions (abstention: bool→int, criteria: Yes/No/Na→int)
- Test binary classification derivation
- Test sanitization function
- Test alpha calculation with known datasets (verify against manual calculation)

### 8.2 Integration Tests
- Test with actual evaluation run IDs from MLflow
- Verify Excel file structure (7 sheets, correct names)
- Verify data validation rules (dropdowns work)
- Verify formulas (binary classification calculates correctly)
- Verify cell protection (can't edit metadata, can edit criteria)

### 8.3 Manual Testing
1. Generate sheet from real evaluation run
2. Open in Excel, verify:
   - Instructions are clear and complete
   - LLM sheet has all data filled correctly
   - Human sheets are empty with working dropdowns
   - Formulas calculate correctly when cells are filled
   - Protected cells can't be edited
   - Text wrapping displays properly
3. Fill in mock human data manually
4. Re-read and verify alpha calculations

### 8.4 Test Cases

**Test Case 1: Perfect Agreement**
- All 3 judges give same grades → α ≈ 1.0

**Test Case 2: Random Disagreement**
- Random grades → α ≈ 0.0

**Test Case 3: Systematic Disagreement**
- LLM always says "Yes", humans say "No" → α < 0

**Test Case 4: Missing Data**
- Human 1: 50% complete, Human 2: 0% → alphas calculated only for available pairs

**Test Case 5: Multiple Runs**
- Combine data from 3 different evaluation runs → verify no duplicates or correct handling

---

## 9. Success Criteria

### 9.1 Functional Requirements
✅ Fetches evaluation data from MLflow correctly
✅ Enriches with database metadata (questions, categories, projects)
✅ Generates Excel with all 7 sheets
✅ LLM sheet pre-filled with correct grades
✅ Human sheets have data validation dropdowns (Yes/No/Na)
✅ Binary classification formulas compute correctly
✅ Krippendorff's alpha calculates when human data available
✅ Agreement statistics show percentage agreement and confusion matrices

### 9.2 Usability Requirements
✅ Clear instructions for human judges (evaluation criteria, grading guidelines)
✅ Easy to fill out (dropdowns, not manual typing)
✅ Visual feedback (conditional formatting for agreement)
✅ Protected cells prevent accidental edits of metadata
✅ Text wrapping for long questions/answers

### 9.3 Reliability Requirements
✅ Handles missing data gracefully (incomplete human sheets)
✅ Works with multiple run IDs (concatenates data)
✅ Consistent with existing analysis scripts (reuses patterns)
✅ Proper error messages for invalid run IDs
✅ Sanitizes text for Excel compatibility

---

## 10. Critical Files

**Files to Reference:**
- `/Users/sylvainhellin/GitHub/4_phd/cobbie/scripts/analyze_evaluation_runs.py` - Pattern for MLflow data fetching, DataFrame building, Excel export
- `/Users/sylvainhellin/GitHub/4_phd/cobbie/baml_src/schemas.baml` - Schema for AnswerEvaluationResult (criterion definitions)
- `/Users/sylvainhellin/GitHub/4_phd/cobbie/src/agents/answer_verifier.py` - Binary classification derivation logic
- `/Users/sylvainhellin/GitHub/4_phd/cobbie/scripts/run_evaluation.py` - How evaluation data is logged to MLflow
- `/Users/sylvainhellin/GitHub/4_phd/cobbie/src/db/query.py` - Database query patterns for question metadata

**Files to Create:**
- `/Users/sylvainhellin/GitHub/4_phd/cobbie/scripts/create_grading_sheet.py` - Main implementation

**Files to Update:**
- `/Users/sylvainhellin/GitHub/4_phd/cobbie/pyproject.toml` - Add dependencies (krippendorff, scikit-learn)
- `/Users/sylvainhellin/GitHub/4_phd/cobbie/specs/grading_sheet.md` - Replace with this detailed spec

---

## 11. Implementation Notes

### 11.1 Reuse Existing Code
- Copy `fetch_nested_runs()`, `extract_run_data()`, `fetch_question_data()` from analyze_evaluation_runs.py
- Copy `sanitize_for_excel()` utility
- Copy CATEGORY_NAMES constant
- Follow same CLI argument parsing pattern

### 11.2 Data Validation in Excel
```python
from openpyxl.worksheet.datavalidation import DataValidation

# Yes/No/Na dropdown for criteria columns
dv_criteria = DataValidation(
    type="list",
    formula1='"Yes,No,Na"',
    allow_blank=False,
    showErrorMessage=True,
    error="Please select Yes, No, or Na",
    errorTitle="Invalid Entry"
)
ws.add_data_validation(dv_criteria)
dv_criteria.add(f'J2:M{num_rows+1}')  # Faithfulness to Relevance

# Boolean for Abstention (checkbox)
# Excel checkboxes require form controls (not via openpyxl)
# Alternative: Data validation for TRUE/FALSE
dv_bool = DataValidation(
    type="list",
    formula1='"TRUE,FALSE"',
    allow_blank=False
)
ws.add_data_validation(dv_bool)
dv_bool.add(f'I2:I{num_rows+1}')  # Abstention
```

### 11.3 Cell Protection
```python
from openpyxl.styles import Protection

# Unlock editable cells (criteria and justification)
for row in range(2, num_rows + 2):  # Skip header
    for col in ['I', 'J', 'K', 'L', 'M', 'N']:  # Criteria + Justification
        cell = ws[f'{col}{row}']
        cell.protection = Protection(locked=False)

# Protect the sheet (allows editing unlocked cells)
ws.protection.sheet = True
ws.protection.password = None  # No password, easy to unprotect
ws.protection.selectLockedCells = True
ws.protection.selectUnlockedCells = True
```

### 11.4 Conditional Formatting for Agreement
```python
from openpyxl.formatting.rule import CellIsRule
from openpyxl.styles import PatternFill

green_fill = PatternFill(start_color='90EE90', fill_type='solid')
yellow_fill = PatternFill(start_color='FFFF99', fill_type='solid')
red_fill = PatternFill(start_color='FFB6C1', fill_type='solid')

# In Binary Comparison sheet, Agreement column
ws.conditional_formatting.add(
    f'F2:F{num_rows+1}',
    CellIsRule(operator='equal', formula=['"All Agree"'], fill=green_fill)
)
ws.conditional_formatting.add(
    f'F2:F{num_rows+1}',
    CellIsRule(operator='containsText', formula=['"Partial"'], fill=yellow_fill)
)
ws.conditional_formatting.add(
    f'F2:F{num_rows+1}',
    CellIsRule(operator='equal', formula=['"No Agreement"'], fill=red_fill)
)
```

---

## 12. Future Enhancements (Out of Scope for V1)

1. **Re-reading Excel files** - Parse completed human sheets and recalculate metrics

---

## End of Specification

This detailed specification provides all necessary information to implement the grading sheet export tool. The implementation should follow existing patterns from `analyze_evaluation_runs.py`, maintain consistency with the BAML schema definitions, and prioritize usability for human evaluators.

