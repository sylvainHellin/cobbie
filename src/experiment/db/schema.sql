-- Schema dump
-- Generated on: 2025-09-26T17:45:14.322791

CREATE TABLE ifc_models (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            project_name TEXT NOT NULL,
            model_name TEXT NOT NULL,
            model_path TEXT NOT NULL,
            model_description TEXT NOT NULL
        );

CREATE TABLE dataset (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            question TEXT NOT NULL,
            ground_truth TEXT NOT NULL,
            ifc_id INTEGER NOT NULL,
            FOREIGN KEY (ifc_id) REFERENCES ifc_models(id)
        );

CREATE TABLE runs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                question_id INTEGER,
                llm TEXT,
                input_tokens INTEGER,
                output_tokens INTEGER,
                duration REAL,
                timestamp timestamp,
                FOREIGN KEY (question_id) REFERENCES dataset(id)
                );

CREATE TABLE logs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
          		run_id INTEGER,
                agent_name TEXT,
                step_number INTEGER,
                timestamp timestamp,
                model_output TEXT,
                action_input_code TEXT,
                action_output TEXT,
                observations TEXT,
                error TEXT,
                duration REAL,
                input_tokens INTEGER,
                output_tokens INTEGER,
                FOREIGN KEY (run_id) REFERENCES runs(id)
                );

CREATE TABLE experiment (id INTEGER PRIMARY KEY AUTOINCREMENT, name TEXT, mlflow_id TEXT, type TEXT, timestamp timestamp);

