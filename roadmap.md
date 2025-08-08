# Roadmap

## Engine
- Refactor the `ToolDebugger` to be like the `ToolCreator` and the `ToolMerger`
- implement checkpoints to recover training run where it stopped
- consider removing the output of each agents from the context in `training`
- Set-up the optimizer and run it
- implement this `load_optimized_model` for each instance of the engine.
- TBD: optimize the `TrainingModule` and not just the engine? But on which metric? Or potential optimize the individual agents, using the `status` of the output?
- Refactor `TrainingModule` -> split between `TrainingModule` (to process one `qa_pair`, and one to do )


## Experiment

- Run Experiment with existing functions created manually
- Track the scores from eval between each training run

## Backend

- deploy on Render

## Frontend

