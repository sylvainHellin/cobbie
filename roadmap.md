# Roadmap

## Engine
- Refactor the `ToolDebugger` to be like the `ToolCreator` and the `ToolMerger`
- implement checkpoints to recover training run where it stopped
- consider removing the output of each agents from the context in `training`
- Set-up the optimizer and run it
- check the logic of the engine: new tools don't seem to be saved anymore


## Experiment

- Run Experiment with existing functions created manually
- Track the scores from eval between each training run

## Backend

- Update the logic to use the models stored locally
- Add an Endpoint to fetch the latest list of models from supabase and update them on the server
- Add an Endpoint to display the existing models, (name, id, project, etc.)
- deploy on `render` to test it with `lovable` at the same time

## Frontend

- URGENT: connect to Chat endpoint from fastapi
- Update the code for displaying the models to use the list from the fastapi endpoint
- Add a button/function to refresh the models
- Fix bug with toggled visibility component
