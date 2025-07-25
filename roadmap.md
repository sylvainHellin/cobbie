- implement an agent to review the chat history if an error was made to identify the cause of the error:
  - faulty tool
  - missing tool
  - other
  and write a report regarding what has happened and what we should do. It should have access to the ground truth
- add a step in `training` to try to optimize the workflow when answer is correct by implementing a new tool (with access to the ground truth)
