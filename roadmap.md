# Roadmap

## Engine
- Refactor the `ToolDebugger` to be like the `ToolCreator` and the `ToolMerger`
- implement checkpoints to recover training run where it stopped
- implement the evaluation pipeline
- consider removing the output of each agents from the context in `training`
- `Training`
  - add a start index for the training cycle
  - accept run name as arg.
- Set-up the optimizer and run it
- log in cost info in the `run` in `mlflow` for the `TrainingModule`

## Experiment

- Run Experiment with existing functions created manually
- Track the scores from eval between each training run

## Backend

- Update the logic to use the models stored locally
- Add an Endpoint to fetch the latest list of models from supabase and update them on the server
- Add an Endpoint to display the existing models, (name, id, project, etc.)
- deploy on `render` to test it with `lovable` at the same time

## Frontend

- Update the code for displaying the models to use the list from the fastapi endpoint
- Add a button/function to refresh the models
