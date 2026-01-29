TODOs:
- check trace of question question_360_439 (http://127.0.0.1:5000/#/experiments/5/runs/de2fd064cdf1427f848eb84a0f2ec459/traces) - it seems that the system is not kicked to improve the tool even when identified as faulty. Instead, it is directly deleted.
- update the analyze evaluation script: track the number of iteration from Cobbie for answering each question.
- update the ./scripts/run_evaluation.py to have the tool categories in run title
- add a --run-name to the ./scripts/run_evaluation.py script. Check that either --run-name or --continue is passed. Cannot run without one of those (and, cannot run with both.)
- Start with the implementation of the ./specs/tool_flag.md



- Remove other_bim_models_for_testing from the create_helper_function.baml and debug_helper_function.baml
- Check if tools were preloaded
- Allow nested GUIDs in the ground truth generation and generated tools