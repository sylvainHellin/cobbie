# Roadmap

**URGENT**
- Something is off in the token counting of the IfcAnswerEngine in the TrainingPipeline: it is not reset for each questions
- Try to understand WHY paralelisme somehow activates when I run the evaluation pipeline as part of the training pipeline. It indeed looks like they are called in paralell, but I can't see why.


## Engine

### Potential improvements

- Instead of providing the history to the `ToolOptimizer`, just send the last trajectory + last output.


## Experiment

- Implement new utilities to query information from training and evaluation runs
- Run Experiment with existing functions created manually
- Track the scores from eval between each training run

## Prototype

### Backend

### Frontend

- check if there is a timeout for the chat interface.
