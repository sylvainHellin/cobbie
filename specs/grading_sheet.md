# Create an Excel grading sheet for evaluating Cobbies' answers.

The objective is to create a new CLI tool in ../scripts/create_grading_sheet.py to export a grading sheet in Excel for 3 evaluators: llm-as-a-judge, human 1, human 2, and calculates Krippensdorf Krippendorff's alpha between each.

It should take as an argument the run-ids (similar to what is happening in ../scripts/analyze_evaluation_runs.py), and create 3 sheets in the Excel file for each judge, with the value of the LLM already filled.

It should fetch the data from mlflow

For each, we can have similar columns as the ones in the report from the analyze script, but instead of the binary classification, we want to analyze each criterion independantly.
