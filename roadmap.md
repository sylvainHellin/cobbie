# Roadmap

**URGENT**

- implement the `update_run` fn in `query.py`
- implement a function to extract the important data for each span and store it into the db (for a specific `run_id`)
- run the `sqlagencode` for the mlflow sqlite db (store in another file, like mlflow_model). Maybe I don't even need to copy the runs and experiment from one to the other, and just query the mlflow db
- Check the logging of the evaluation script (in wrong experiment ; no traces)
- Something is off in the token counting of the IfcAnswerEngine in the TrainingPipeline: it is not reset for each questions
- Try to understand WHY paralelisme somehow activates when I run the evaluation pipeline as part of the training pipeline. It indeed looks like they are called in paralell, but I can't see why.


## Engine

### Potential improvements

- Instead of providing the history to the `ToolOptimizer`, just send the last trajectory + last output.
- add proper token counting and dspy context setting for the Name Extractor


## Experiment

- Implement new utilities to query information from training and evaluation runs
- Run Experiment with existing functions created manually
- Track the scores from eval between each training run

## Prototype

### Backend

### Frontend

- check if there is a timeout for the chat interface.
