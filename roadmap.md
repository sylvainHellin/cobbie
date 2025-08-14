# Roadmap

## Engine

- Clean up the `config` file for the LLM: find a more streamlined approach to name them and handle them (Enum?) - maybe move them to a dedicated file instead of general config. **WIP** : look for all files still containing a reference to LANGUAGE_MODELS
- Created a unified and streamlined way to calculate cost at a `Module` level -- and propagate them back (it should be able to handle different LLM providers with different costs at different module levels.)
- Upgrade dspy to 3.0 -- workout all the breaking changes -- kill the fastapi server first -- update how Prediction are handled.
- Add more tracing data in `mlflow` for the `optimizer`
- Create small util function to calculate the nb of tokens from a specific messages list from mlflow.


## Experiment

- Implement new utilities to query information from training and evaluation runs
- Run Experiment with existing functions created manually
- Track the scores from eval between each training run

## Prototype

### Backend

### Frontend
